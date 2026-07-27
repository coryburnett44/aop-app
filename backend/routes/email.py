"""Email routes — templates, blasts, drafts, signatures, deliverability, test-send,
webhook, unsubscribe, member email preferences, inline image upload, and the
built-in starter-template seed.

This module owns 24 routes that all share the same Resend integration and the
same admin-tab dependency. Everything is registered via `register(...)` so
server.py can keep its dependency-injection pattern.

The send-pipeline helpers themselves (`send_bulk_email`, `_normalize_email_images`,
`_verify_unsubscribe_token`, etc.) stay in server.py — they're used by other
modules (chat digest, automated emails) too. They're injected in here.
"""
import asyncio
import html as _html
import re
import uuid
from datetime import timedelta
from typing import Optional, List, Literal

from fastapi import Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import RedirectResponse
import os
from pydantic import BaseModel


# ============================================================
# Pydantic models (private to the email module)
# ============================================================
class EmailTemplateIn(BaseModel):
    name: str
    subject: str
    body_html: str
    description: str = ""


class EmailTemplateUpdateIn(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    description: Optional[str] = None


class EmailBlastIn(BaseModel):
    template_id: Optional[str] = None
    subject: str
    body_html: str
    background_color: Optional[str] = ""
    segment: Literal["all", "active", "lifetime", "alumni", "admins", "tier", "chapter", "custom"] = "active"
    tier_id: Optional[str] = None
    chapter_id: Optional[str] = None
    custom_user_ids: List[str] = []
    # Iter 90: ad-hoc email addresses outside the membership roster (vendors,
    # press, sister-chapter officers, etc). Validation is best-effort — any
    # malformed address is silently skipped during resolve_segment.
    external_emails: List[str] = []
    test_only: bool = False
    # Iter 140: also fire a OneSignal push notification alongside the email.
    also_push: bool = False
    push_body: Optional[str] = ""
    push_url: Optional[str] = ""
    # Iter 143: attach documents (PDF, DOCX, images, etc.) — resolved to
    # bytes via chat_files at send time.
    attachment_ids: List[str] = []


class EmailDraftIn(BaseModel):
    name: str = ""
    subject: str = ""
    body_html: str = ""
    background_color: Optional[str] = ""
    segment: str = "active"
    tier_id: Optional[str] = None
    chapter_id: Optional[str] = None
    custom_user_ids: List[str] = []
    external_emails: List[str] = []
    is_autosave: bool = False
    attachment_ids: List[str] = []


class EmailPreferencesIn(BaseModel):
    blasts: Optional[bool] = None
    dues_reminders: Optional[bool] = None
    email_opt_out: Optional[bool] = None


class SmsPreferencesIn(BaseModel):
    """Member-controlled SMS preferences. Mirrors EmailPreferencesIn.

    `sms_opt_out` is the master kill-switch — when True, ALL outbound SMS to
    this member is suppressed regardless of the per-category flags. The per-
    category flag (currently only `dues_reminders`) lets a member silence one
    kind of text without opting out of the platform's other SMS features
    (like video-meeting fan-out notifications).
    """
    dues_reminders: Optional[bool] = None
    sms_opt_out: Optional[bool] = None


class EmailTestSendIn(BaseModel):
    to_email: Optional[str] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    template_id: Optional[str] = None


class SignatureIn(BaseModel):
    name: str
    body_html: str
    kind: Literal["personal", "org"] = "personal"


class SignatureUpdateIn(BaseModel):
    name: Optional[str] = None
    body_html: Optional[str] = None


# ============================================================
# Serializers
# ============================================================
def template_out(t: dict) -> dict:
    return {
        "id": t["id"],
        "name": t["name"],
        "subject": t["subject"],
        "body_html": t["body_html"],
        "description": t.get("description", ""),
        "is_builtin": bool(t.get("is_builtin", False)),
        "created_at": t.get("created_at"),
    }


def _draft_out(d: dict) -> dict:
    return {
        "id": d["id"],
        "name": d.get("name", ""),
        "subject": d.get("subject", ""),
        "body_html": d.get("body_html", ""),
        "segment": d.get("segment", "active"),
        "tier_id": d.get("tier_id"),
        "chapter_id": d.get("chapter_id"),
        "custom_user_ids": d.get("custom_user_ids") or [],
        "external_emails": d.get("external_emails") or [],
        "is_autosave": bool(d.get("is_autosave", False)),
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
    }


def _signature_out(s: dict) -> dict:
    return {
        "id": s["id"],
        "name": s["name"],
        "body_html": s.get("body_html", ""),
        "kind": s.get("kind", "personal"),
        "owner_id": s.get("owner_id"),
        "created_at": s.get("created_at"),
    }


# ============================================================
# Built-in starter templates (seeded on startup)
# ============================================================
BUILTIN_EMAIL_TEMPLATES = [
    {
        "id": "builtin_tpl_announcement",
        "name": "General Announcement",
        "subject": "Important update from Alpha Omega Phi",
        "description": "Clean, brand-styled layout for any organization-wide announcement.",
        "body_html": """<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
  <div style="background:#0A2463;color:#ffffff;padding:20px 28px">
    <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;opacity:.8">Alpha Omega Phi</div>
    <h1 style="margin:4px 0 0;font-size:24px;line-height:1.25">Announcement</h1>
  </div>
  <div style="padding:28px;color:#1f2937;font-size:15px;line-height:1.6">
    <p>Hi {{first_name}},</p>
    <p>Write your announcement here. Keep it short, share the headline first, and finish with a clear call to action.</p>
    <p style="margin:24px 0">
      <a href="https://aop-app.org" style="background:#C8102E;color:#fff;text-decoration:none;padding:12px 22px;border-radius:999px;font-weight:600;display:inline-block">Take action</a>
    </p>
    <p style="color:#6b7280;font-size:13px">In service,<br><strong>The AOP Team</strong></p>
  </div>
</div>""",
    },
    {
        "id": "builtin_tpl_event_reminder",
        "name": "Event Reminder",
        "subject": "Reminder: Your AOP event is coming up",
        "description": "Eye-catching reminder for upcoming chapter events and meetings.",
        "body_html": """<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:0 auto;background:#f7f5f0;padding:28px">
  <div style="background:#ffffff;border-radius:12px;padding:28px;border:1px solid #e5e7eb">
    <div style="display:inline-block;background:#C8102E;color:#fff;font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;padding:4px 10px;border-radius:999px">Event reminder</div>
    <h1 style="font-size:26px;color:#0A2463;margin:14px 0 6px">Hi {{first_name}}, see you there!</h1>
    <p style="color:#4b5563;font-size:15px;line-height:1.6">Don't forget — our upcoming event is right around the corner. Add the details below to your calendar so you don't miss it.</p>
    <table style="margin:18px 0;border-collapse:collapse;width:100%">
      <tr><td style="padding:8px 0;color:#6b7280;font-size:13px;width:90px">When</td><td style="padding:8px 0;font-weight:600">Friday, Date · 7:00 PM</td></tr>
      <tr><td style="padding:8px 0;color:#6b7280;font-size:13px">Where</td><td style="padding:8px 0;font-weight:600">Add location here</td></tr>
      <tr><td style="padding:8px 0;color:#6b7280;font-size:13px">Bring</td><td style="padding:8px 0;font-weight:600">Add gear / attire</td></tr>
    </table>
    <p style="margin:24px 0 0"><a href="https://aop-app.org/events" style="background:#0A2463;color:#fff;text-decoration:none;padding:12px 22px;border-radius:999px;font-weight:600;display:inline-block">View event details</a></p>
  </div>
</div>""",
    },
    {
        "id": "builtin_tpl_dues_reminder",
        "name": "Dues Reminder",
        "subject": "Time to renew your AOP membership",
        "description": "Friendly nudge for members whose dues are approaching renewal.",
        "body_html": """<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
  <div style="background:linear-gradient(135deg,#0A2463 0%,#C8102E 100%);color:#fff;padding:28px;text-align:center">
    <h1 style="margin:0;font-size:24px">Keep your AOP membership active</h1>
    <p style="margin:6px 0 0;opacity:.9;font-size:14px">Your annual dues renewal is coming up</p>
  </div>
  <div style="padding:28px;color:#1f2937;font-size:15px;line-height:1.6">
    <p>Hi {{first_name}},</p>
    <p>Your continued membership keeps every chapter event, volunteer hour, and brotherhood/sisterhood tradition running. Renewing only takes a minute.</p>
    <ul style="padding-left:18px;color:#4b5563">
      <li>Voting privileges in chapter business</li>
      <li>Access to gear store, events, and member directory</li>
      <li>Volunteer hours tracking & awards eligibility</li>
    </ul>
    <p style="margin:24px 0;text-align:center"><a href="https://aop-app.org/dashboard" style="background:#C8102E;color:#fff;text-decoration:none;padding:14px 28px;border-radius:999px;font-weight:700;display:inline-block">Renew dues now</a></p>
    <p style="color:#6b7280;font-size:13px">Questions? Reply directly to this email — we read every one.</p>
  </div>
</div>""",
    },
    {
        "id": "builtin_tpl_welcome",
        "name": "Welcome New Member",
        "subject": "Welcome to Alpha Omega Phi, {{first_name}}!",
        "description": "First-touch welcome message for newly inducted members.",
        "body_html": """<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:0 auto;background:#ffffff">
  <div style="background:#0A2463;color:#fff;padding:32px 28px;text-align:center;border-radius:12px 12px 0 0">
    <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;opacity:.8">Alpha Omega Phi</div>
    <h1 style="margin:8px 0 0;font-size:30px">Welcome aboard</h1>
  </div>
  <div style="padding:32px 28px;color:#1f2937;font-size:15px;line-height:1.7;border:1px solid #e5e7eb;border-top:0;border-radius:0 0 12px 12px">
    <p>{{first_name}},</p>
    <p>It's official — you're a member of Alpha Omega Phi. We're proud to have you in the line and excited to see what you'll bring to the chapter.</p>
    <p style="font-weight:600;margin-top:20px">Here's how to get started:</p>
    <ol style="padding-left:18px">
      <li>Log in to <a href="https://aop-app.org" style="color:#C8102E">aop-app.org</a> and finish your profile.</li>
      <li>Browse upcoming events and RSVP to your first one.</li>
      <li>Say hi in the chapter chat — we're already talking about you.</li>
    </ol>
    <p style="margin:28px 0 0">In brotherhood/sisterhood,<br><strong>Your AOP Family</strong></p>
  </div>
</div>""",
    },
    {
        "id": "builtin_tpl_newsletter",
        "name": "Monthly Newsletter",
        "subject": "AOP Monthly · What you missed",
        "description": "Sectioned newsletter template — drop your monthly highlights inside.",
        "body_html": """<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:680px;margin:0 auto;background:#f7f5f0;padding:24px">
  <div style="background:#ffffff;border-radius:14px;padding:32px;border:1px solid #e5e7eb">
    <div style="border-bottom:3px solid #C8102E;padding-bottom:14px;margin-bottom:20px">
      <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#6b7280">The AOP Monthly</div>
      <h1 style="margin:6px 0 0;font-size:28px;color:#0A2463">This month at Alpha Omega Phi</h1>
    </div>
    <p style="color:#374151;font-size:15px;line-height:1.7">Hi {{first_name}}, here's everything that happened — and what's coming next.</p>
    <h2 style="font-size:18px;color:#0A2463;border-left:4px solid #C8102E;padding-left:10px;margin-top:28px">Recent wins</h2>
    <p style="color:#374151;font-size:14px;line-height:1.7">Replace this with a quick recap of community service hours, fundraising totals, or chapter milestones.</p>
    <h2 style="font-size:18px;color:#0A2463;border-left:4px solid #C8102E;padding-left:10px;margin-top:28px">Coming up</h2>
    <p style="color:#374151;font-size:14px;line-height:1.7">List your next 1–3 events with date, location, and a short why-you-should-come.</p>
    <h2 style="font-size:18px;color:#0A2463;border-left:4px solid #C8102E;padding-left:10px;margin-top:28px">Spotlight</h2>
    <p style="color:#374151;font-size:14px;line-height:1.7">Feature a member, chapter, or initiative. Photos welcome — drag into the editor.</p>
    <p style="margin:28px 0 0;text-align:center"><a href="https://aop-app.org" style="background:#0A2463;color:#fff;text-decoration:none;padding:12px 24px;border-radius:999px;font-weight:600;display:inline-block">Visit the portal</a></p>
  </div>
</div>""",
    },
]


async def seed_builtin_email_templates(db, iso, now_utc, logger):
    """Insert starter email templates if they don't exist yet. Idempotent."""
    for tpl in BUILTIN_EMAIL_TEMPLATES:
        existing = await db.email_templates.find_one({"id": tpl["id"]})
        if existing:
            continue
        doc = {
            **tpl,
            "is_builtin": True,
            "created_at": iso(now_utc()),
        }
        await db.email_templates.insert_one(doc)
        logger.info(f"Seeded built-in email template: {tpl['name']}")


# ============================================================
# Route registration
# ============================================================
def register(
    api,
    *,
    db,
    iso,
    now_utc,
    logger,
    admin_tab_dep,
    get_current_user,
    resend_sdk,
    resend_api_key,
    resend_from,
    resend_reply_to,
    org_mailing_address,
    send_bulk_email,
    normalize_email_images,
    verify_unsubscribe_token,
    put_object,
    image_extensions,
    mime_by_ext,
    get_object,
    send_push_best_effort=None,
):

    # ---------- Helpers used by multiple routes (closure-captured deps) ----------
    _EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")

    def _coerce_external_emails(raw: List[str]) -> List[dict]:
        """Turn a list of arbitrary strings into synthetic recipient dicts the
        blast loop can iterate. Strips whitespace, lowercases, dedupes within
        the list, and silently drops malformed entries."""
        seen: set = set()
        out: List[dict] = []
        for entry in raw or []:
            if not entry or not isinstance(entry, str):
                continue
            for token in re.split(r"[\s,;\n]+", entry.strip()):
                addr = token.strip().lower()
                if not addr or addr in seen or not _EMAIL_RE.match(addr):
                    continue
                seen.add(addr)
                out.append({
                    "id": f"ext:{addr}",
                    "email": addr,
                    "name": addr.split("@")[0],
                    "first_name": "",
                    "last_name": "",
                    "line_name": "",
                    "_external": True,
                })
        return out

    async def resolve_segment(body: EmailBlastIn) -> List[dict]:
        q: dict = {}
        # Iter 90: when segment=custom we MUST honor the explicit list — even if
        # it's empty (otherwise an admin sending to "just these 3 externals" would
        # accidentally blast every active member because the `q` would be empty).
        skip_member_query = False
        if body.segment == "admins":
            q["role"] = "admin"
        elif body.segment == "tier" and body.tier_id:
            q["tier_id"] = body.tier_id
        elif body.segment == "chapter" and body.chapter_id:
            q["chapter_id"] = body.chapter_id
        elif body.segment == "custom":
            if body.custom_user_ids:
                q["id"] = {"$in": body.custom_user_ids}
            else:
                # No member ids picked → only external addresses count.
                skip_member_query = True
        elif body.segment == "active":
            q["status_override"] = {"$ne": "deceased"}
        # test_only blasts bypass opt-out filtering since they only go to the admin
        if not body.test_only:
            q["email_opt_out"] = {"$ne": True}
            q["email_prefs.blasts"] = {"$ne": False}
        if skip_member_query:
            members: List[dict] = []
        else:
            cursor = db.users.find(q, {"_id": 0, "password_hash": 0}).limit(2000)
            members = await cursor.to_list(2000)
        # Iter 90: append external recipients on top of the member roster.
        # External addresses always go through (they're explicit admin-entered
        # opt-ins — no opt-out cookie applies). Dedupe against member emails so
        # admins don't double-send to a member who is also in the external box.
        member_emails = {(u.get("email") or "").lower() for u in members}
        externals = [e for e in _coerce_external_emails(body.external_emails) if e["email"] not in member_emails]
        return members + externals

    def render_variables(body_html: str, recipient: dict) -> str:
        """Replace {{name}}, {{first_name}}, {{last_name}}, {{line_name}}, {{email}}.
        HTML-escapes values to prevent XSS via member names."""
        out = body_html
        for key, val in {
            "name": recipient.get("name", ""),
            "first_name": recipient.get("first_name", ""),
            "last_name": recipient.get("last_name", ""),
            "line_name": recipient.get("line_name", ""),
            "email": recipient.get("email", ""),
        }.items():
            out = out.replace("{{" + key + "}}", _html.escape(val or ""))
        return out

    # ============================================================
    # Templates CRUD
    # ============================================================
    @api.get("/email/templates")
    async def list_email_templates(_: dict = Depends(admin_tab_dep("email"))):
        items = await db.email_templates.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
        return [template_out(t) for t in items]

    @api.post("/email/templates")
    async def create_email_template(body: EmailTemplateIn, _: dict = Depends(admin_tab_dep("email"))):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = iso(now_utc())
        await db.email_templates.insert_one(doc)
        return template_out(doc)

    @api.put("/email/templates/{tid}")
    async def update_email_template(tid: str, body: EmailTemplateUpdateIn, _: dict = Depends(admin_tab_dep("email"))):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.email_templates.update_one({"id": tid}, {"$set": updates})
        t = await db.email_templates.find_one({"id": tid}, {"_id": 0})
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        return template_out(t)

    @api.delete("/email/templates/{tid}")
    async def delete_email_template(tid: str, _: dict = Depends(admin_tab_dep("email"))):
        await db.email_templates.delete_one({"id": tid})
        return {"ok": True}

    # ============================================================
    # Preview & blast send
    # ============================================================
    def _wrap_with_background(html: str, bg: str) -> str:
        """Wrap the message body in a mobile-safe container that sets the
        background color (email clients strip <style>, so we inline it)."""
        color = (bg or "").strip()
        if not color:
            return html
        # Email-client-safe wrapper — table for Outlook, div fallback.
        return (
            f'<div style="background-color:{color};padding:24px 12px;">'
            f'<div style="max-width:640px;margin:0 auto;background-color:{color};">'
            f'{html}'
            f'</div></div>'
        )

    @api.post("/email/preview")
    async def email_preview(body: EmailBlastIn, user: dict = Depends(admin_tab_dep("email"))):
        """Render the blast for the current admin user as preview (no send)."""
        recipients = await resolve_segment(body)
        sample = recipients[0] if recipients else user
        html = normalize_email_images(render_variables(body.body_html, sample))
        html = _wrap_with_background(html, body.background_color or "")
        return {
            "subject": body.subject.replace("{{name}}", sample.get("name", "")),
            "html": html,
            "recipient_count": len(recipients),
            "sample_recipient": {"name": sample.get("name", ""), "email": sample.get("email", "")},
        }

    @api.post("/email/blast")
    async def send_email_blast(body: EmailBlastIn, user: dict = Depends(admin_tab_dep("email"))):
        if not resend_api_key:
            raise HTTPException(status_code=503, detail="Email service not configured")
        recipients = await resolve_segment(body)
        if body.test_only:
            recipients = [user]
        if not recipients:
            raise HTTPException(status_code=400, detail="Segment has no recipients")

        # Load attachments ONCE (not per-recipient) — bytes are base64-encoded
        # and passed to Resend which handles the actual MIME embedding.
        resend_attachments: list[dict] = []
        attachment_summary: list[dict] = []
        if body.attachment_ids:
            import base64
            for aid in body.attachment_ids:
                rec = await db.chat_files.find_one({
                    "id": aid, "kind": "attachment", "is_deleted": {"$ne": True},
                })
                if not rec:
                    continue
                try:
                    data_bytes, ctype = await asyncio.to_thread(get_object, rec["storage_path"])
                except Exception as e:
                    logger.warning(f"attachment {aid} fetch failed: {e}")
                    continue
                resend_attachments.append({
                    "filename": rec.get("filename", "attachment"),
                    "content": base64.b64encode(data_bytes).decode("ascii"),
                    "content_type": rec.get("content_type") or ctype or "application/octet-stream",
                })
                attachment_summary.append({
                    "id": aid,
                    "filename": rec.get("filename"),
                    "size": rec.get("size", 0),
                })

        blast_id = str(uuid.uuid4())
        sent: List[dict] = []
        failed: List[dict] = []

        for r in recipients:
            email = (r.get("email") or "").strip()
            if not email:
                failed.append({"user_id": r.get("id"), "reason": "no email"})
                continue
            try:
                rendered_html = render_variables(body.body_html, r)
                wrapped_html = _wrap_with_background(rendered_html, body.background_color or "")
                res = await send_bulk_email(
                    to_email=email,
                    subject=body.subject.replace("{{name}}", r.get("name", "")),
                    html_body=wrapped_html,
                    recipient_id=r.get("id", ""),
                    tags=[
                        {"name": "blast_id", "value": blast_id},
                        {"name": "type", "value": "blast"},
                    ],
                    attachments=resend_attachments or None,
                )
                sent.append({"user_id": r.get("id"), "email": email, "resend_id": (res or {}).get("id") if isinstance(res, dict) else None})
            except Exception as e:
                logger.error(f"Resend send failed for {email}: {e}")
                failed.append({"user_id": r.get("id"), "email": email, "reason": str(e)[:200]})

        log = {
            "id": blast_id,
            "subject": body.subject,
            "segment": body.segment,
            "tier_id": body.tier_id,
            "chapter_id": body.chapter_id,
            "test_only": body.test_only,
            "background_color": body.background_color or "",
            "attachments": attachment_summary,
            "sent_count": len(sent),
            "failed_count": len(failed),
            "sent_to": [s["email"] for s in sent[:100]],
            "failed": failed[:50],
            "sent_by": user["id"],
            "sent_by_name": user.get("name", "Admin"),
            "sent_at": iso(now_utc()),
        }
        await db.email_blasts.insert_one(log)
        # Optional OneSignal companion push (best-effort, non-blocking).
        if body.also_push and send_push_best_effort is not None and not body.test_only:
            asyncio.create_task(send_push_best_effort(
                db=db, logger=logger, iso=iso, now_utc=now_utc,
                title=body.subject[:60] or "Alpha Omega Phi",
                body=(body.push_body or "").strip()[:180] or "You have a new message from Alpha Omega Phi. Tap to read.",
                url=(body.push_url or "").strip(),
                user_ids=[r["id"] for r in recipients if r.get("id") and not r.get("_external")],
                segment="custom",
                trigger="email_blast",
            ))
        return {"blast_id": blast_id, "sent": len(sent), "failed": len(failed)}

    # ============================================================
    # Member email preferences
    # ============================================================
    @api.get("/me/email-preferences")
    async def get_my_email_preferences(user: dict = Depends(get_current_user)):
        """Master `email_opt_out` overrides every category. UI shows both so the
        member can re-subscribe from Profile without needing the original email."""
        prefs = user.get("email_prefs") or {}
        return {
            "email_opt_out": bool(user.get("email_opt_out", False)),
            "email_opt_out_at": user.get("email_opt_out_at"),
            "email_prefs": {
                "blasts": prefs.get("blasts", True),
                "dues_reminders": prefs.get("dues_reminders", True),
            },
        }

    @api.put("/me/email-preferences")
    async def update_my_email_preferences(body: EmailPreferencesIn, user: dict = Depends(get_current_user)):
        cur_prefs = user.get("email_prefs") or {}
        next_prefs = {
            "blasts": cur_prefs.get("blasts", True),
            "dues_reminders": cur_prefs.get("dues_reminders", True),
        }
        if body.blasts is not None:
            next_prefs["blasts"] = bool(body.blasts)
        if body.dues_reminders is not None:
            next_prefs["dues_reminders"] = bool(body.dues_reminders)

        update_doc: dict = {"email_prefs": next_prefs}
        unset_doc: dict = {}
        if body.email_opt_out is not None:
            update_doc["email_opt_out"] = bool(body.email_opt_out)
            if body.email_opt_out:
                update_doc["email_opt_out_at"] = iso(now_utc())
            else:
                unset_doc["email_opt_out_at"] = ""
        elif (next_prefs["blasts"] or next_prefs["dues_reminders"]) and user.get("email_opt_out"):
            update_doc["email_opt_out"] = False
            unset_doc["email_opt_out_at"] = ""

        mongo_update: dict = {"$set": update_doc}
        if unset_doc:
            mongo_update["$unset"] = unset_doc
        await db.users.update_one({"id": user["id"]}, mongo_update)
        u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
        return {
            "ok": True,
            "email_opt_out": bool(u.get("email_opt_out", False)),
            "email_prefs": u.get("email_prefs") or next_prefs,
        }

    # ============================================================
    # Member SMS preferences (symmetric to email preferences above).
    # Backs the "SMS reminders" toggle in Profile → Notifications.
    # ============================================================
    @api.get("/me/sms-preferences")
    async def get_my_sms_preferences(user: dict = Depends(get_current_user)):
        prefs = user.get("sms_prefs") or {}
        return {
            "phone": user.get("phone") or "",
            "sms_opt_out": bool(user.get("sms_opt_out", False)),
            "sms_opt_out_at": user.get("sms_opt_out_at"),
            "sms_prefs": {
                # Default ON — matches the email-side default so an existing
                # phone number opts you in for dues texts automatically.
                "dues_reminders": prefs.get("dues_reminders", True),
            },
        }

    @api.put("/me/sms-preferences")
    async def update_my_sms_preferences(body: SmsPreferencesIn, user: dict = Depends(get_current_user)):
        cur_prefs = user.get("sms_prefs") or {}
        next_prefs = {
            "dues_reminders": cur_prefs.get("dues_reminders", True),
        }
        if body.dues_reminders is not None:
            next_prefs["dues_reminders"] = bool(body.dues_reminders)

        update_doc: dict = {"sms_prefs": next_prefs}
        unset_doc: dict = {}
        if body.sms_opt_out is not None:
            update_doc["sms_opt_out"] = bool(body.sms_opt_out)
            if body.sms_opt_out:
                update_doc["sms_opt_out_at"] = iso(now_utc())
            else:
                unset_doc["sms_opt_out_at"] = ""
        elif next_prefs["dues_reminders"] and user.get("sms_opt_out"):
            # Auto-clear the master kill-switch if the member re-enables a
            # sub-category — matches the email-side ergonomics.
            update_doc["sms_opt_out"] = False
            unset_doc["sms_opt_out_at"] = ""

        mongo_update: dict = {"$set": update_doc}
        if unset_doc:
            mongo_update["$unset"] = unset_doc
        await db.users.update_one({"id": user["id"]}, mongo_update)
        u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
        return {
            "ok": True,
            "sms_opt_out": bool(u.get("sms_opt_out", False)),
            "sms_prefs": u.get("sms_prefs") or next_prefs,
        }

    # ============================================================
    # Blast history + failed recipients
    # ============================================================
    @api.get("/email/blasts")
    async def list_email_blasts(_: dict = Depends(admin_tab_dep("email"))):
        items = await db.email_blasts.find({}, {"_id": 0}).sort("sent_at", -1).limit(100).to_list(100)
        return items

    @api.get("/email/blasts/{blast_id}/failed")
    async def get_blast_failed_recipients(blast_id: str, _: dict = Depends(admin_tab_dep("email"))):
        b = await db.email_blasts.find_one({"id": blast_id}, {"_id": 0})
        if not b:
            raise HTTPException(status_code=404, detail="Blast not found")
        failed = b.get("failed") or []
        return {
            "blast_id": blast_id,
            "subject": b.get("subject", ""),
            "sent_at": b.get("sent_at"),
            "failed_count": b.get("failed_count", len(failed)),
            "failed": failed,
        }

    # ============================================================
    # Drafts (per admin) — manual saves + auto-save upsert
    # ============================================================
    @api.get("/email/drafts")
    async def list_email_drafts(admin: dict = Depends(admin_tab_dep("email"))):
        items = await db.email_drafts.find(
            {"owner_id": admin["id"]}, {"_id": 0}
        ).sort("updated_at", -1).to_list(100)
        return [_draft_out(d) for d in items]

    @api.post("/email/drafts")
    async def create_email_draft(body: EmailDraftIn, admin: dict = Depends(admin_tab_dep("email"))):
        now = iso(now_utc())
        if body.is_autosave:
            existing = await db.email_drafts.find_one({"owner_id": admin["id"], "is_autosave": True})
            if existing:
                await db.email_drafts.update_one(
                    {"id": existing["id"]},
                    {"$set": {
                        "subject": body.subject,
                        "body_html": body.body_html,
                        "segment": body.segment,
                        "tier_id": body.tier_id,
                        "chapter_id": body.chapter_id,
                        "custom_user_ids": body.custom_user_ids,
                        "external_emails": body.external_emails,
                        "updated_at": now,
                    }},
                )
                d = await db.email_drafts.find_one({"id": existing["id"]}, {"_id": 0})
                return _draft_out(d)
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["owner_id"] = admin["id"]
        doc["created_at"] = now
        doc["updated_at"] = now
        await db.email_drafts.insert_one(doc)
        return _draft_out(doc)

    @api.put("/email/drafts/{draft_id}")
    async def update_email_draft(draft_id: str, body: EmailDraftIn, admin: dict = Depends(admin_tab_dep("email"))):
        d = await db.email_drafts.find_one({"id": draft_id})
        if not d:
            raise HTTPException(status_code=404, detail="Draft not found")
        if d.get("owner_id") != admin["id"]:
            raise HTTPException(status_code=403, detail="Not your draft")
        await db.email_drafts.update_one(
            {"id": draft_id},
            {"$set": {
                "name": body.name,
                "subject": body.subject,
                "body_html": body.body_html,
                "segment": body.segment,
                "tier_id": body.tier_id,
                "chapter_id": body.chapter_id,
                "custom_user_ids": body.custom_user_ids,
                "external_emails": body.external_emails,
                "updated_at": iso(now_utc()),
            }},
        )
        d2 = await db.email_drafts.find_one({"id": draft_id}, {"_id": 0})
        return _draft_out(d2)

    @api.delete("/email/drafts/{draft_id}")
    async def delete_email_draft(draft_id: str, admin: dict = Depends(admin_tab_dep("email"))):
        d = await db.email_drafts.find_one({"id": draft_id})
        if not d:
            return {"ok": True}
        if d.get("owner_id") != admin["id"]:
            raise HTTPException(status_code=403, detail="Not your draft")
        await db.email_drafts.delete_one({"id": draft_id})
        return {"ok": True}

    # ============================================================
    # Password-setup link failures log
    # ============================================================
    @api.get("/email/password-setup-failures")
    async def list_password_setup_failures(days: int = 90, _: dict = Depends(admin_tab_dep("email"))):
        cutoff = now_utc() - timedelta(days=max(1, min(365, days)))
        items = await db.password_setup_attempts.find(
            {"ok": False, "attempted_at_dt": {"$gte": cutoff}}, {"_id": 0}
        ).sort("attempted_at_dt", -1).limit(500).to_list(500)
        for it in items:
            it.pop("attempted_at_dt", None)
        return items

    # ============================================================
    # Public unsubscribe / resubscribe / status (no auth — token-signed)
    # ============================================================
    @api.api_route("/email/unsubscribe", methods=["GET", "POST"])
    async def email_unsubscribe(token: str = ""):
        """Public one-click unsubscribe (no auth). Reached by Gmail/Yahoo bots
        per RFC 8058 AND humans clicking the footer link. Idempotent — 302s to
        a friendly /unsubscribed page either way."""
        base = (os.environ.get("FRONTEND_URL", "https://aop-app.org")).rstrip("/")
        if not token:
            return RedirectResponse(url=f"{base}/unsubscribed?status=invalid", status_code=302)
        user_id = verify_unsubscribe_token(token)
        if not user_id:
            return RedirectResponse(url=f"{base}/unsubscribed?status=invalid", status_code=302)
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"email_opt_out": True, "email_opt_out_at": iso(now_utc())}},
        )
        logger.info(f"email_opt_out=true for user_id={user_id} (unsubscribe link)")
        return RedirectResponse(url=f"{base}/unsubscribed?status=ok&token={token}", status_code=302)

    @api.post("/email/resubscribe")
    async def email_resubscribe(token: str = ""):
        if not token:
            raise HTTPException(status_code=400, detail="Missing token")
        user_id = verify_unsubscribe_token(token)
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid token")
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"email_opt_out": False}, "$unset": {"email_opt_out_at": ""}},
        )
        logger.info(f"email_opt_out=false (resubscribed) user_id={user_id}")
        return {"ok": True, "subscribed": True}

    @api.get("/email/unsubscribe-status")
    async def email_unsubscribe_status(token: str = ""):
        if not token:
            raise HTTPException(status_code=400, detail="Missing token")
        user_id = verify_unsubscribe_token(token)
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid token")
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "email": 1, "name": 1, "email_opt_out": 1, "email_opt_out_at": 1})
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "email": u.get("email", ""),
            "name": u.get("name", ""),
            "opted_out": bool(u.get("email_opt_out", False)),
            "opted_out_at": u.get("email_opt_out_at"),
        }

    # ============================================================
    # Deliverability + test send + webhook
    # ============================================================
    @api.get("/email/deliverability")
    async def email_deliverability(_: dict = Depends(admin_tab_dep("email"))):
        opt_out_count = await db.users.count_documents({"email_opt_out": True})
        total_with_email = await db.users.count_documents({"email": {"$exists": True, "$ne": ""}})
        m = re.search(r"<([^>]+)>", resend_from)
        addr = m.group(1) if m else resend_from
        domain = addr.split("@", 1)[1] if "@" in addr else ""
        return {
            "resend_configured": bool(resend_api_key),
            "from": resend_from,
            "reply_to": resend_reply_to,
            "sending_domain": domain,
            "is_resend_sandbox": "resend.dev" in domain,
            "org_mailing_address": org_mailing_address,
            "opt_out_count": opt_out_count,
            "total_with_email": total_with_email,
            "dns_checklist": [
                {"record": "SPF (TXT)", "value": "Include Resend in your existing SPF or add 'v=spf1 include:_spf.resend.com ~all'", "host": "@"},
                {"record": "DKIM (CNAME/TXT)", "value": "Resend dashboard → Domains → your domain → copy the 3 DKIM CNAME records and add to DNS", "host": "resend._domainkey + 2 more"},
                {"record": "DMARC (TXT)", "value": "v=DMARC1; p=quarantine; rua=mailto:dmarc@" + (domain or "yourdomain.com") + "; pct=100", "host": "_dmarc"},
                {"record": "MX (TXT, optional)", "value": "feedback-loop with Resend for bounce/complaint tracking — configure in Resend dashboard", "host": "@"},
            ],
        }

    @api.post("/email/test-send")
    async def email_test_send(body: EmailTestSendIn, admin: dict = Depends(admin_tab_dep("email"))):
        """One-off test email. If `to_email` is omitted, the email is sent to the
        admin's own address — used by the per-template "Send test to me" button."""
        to_email = (body.to_email or "").strip() or (admin.get("email") or "").strip()
        if not to_email or "@" not in to_email:
            raise HTTPException(status_code=400, detail="A valid recipient email is required.")
        if not resend_api_key:
            raise HTTPException(status_code=503, detail="Resend API key not configured on the server (RESEND_API_KEY).")
        subject = (body.subject or "").strip()
        html_body = (body.body_html or "").strip()
        template_name = ""
        if body.template_id:
            tpl = await db.email_templates.find_one({"id": body.template_id})
            if not tpl:
                raise HTTPException(status_code=404, detail="Template not found")
            if not subject:
                subject = tpl.get("subject", "")
            if not html_body:
                html_body = tpl.get("body_html", "")
            template_name = tpl.get("name", "")
        sample = await db.users.find_one({"id": admin["id"]}, {"_id": 0, "password_hash": 0}) or admin
        if subject:
            for key, val in {
                "name": sample.get("name", ""),
                "first_name": sample.get("first_name", ""),
                "last_name": sample.get("last_name", ""),
                "line_name": sample.get("line_name", ""),
                "email": sample.get("email", ""),
            }.items():
                subject = subject.replace("{{" + key + "}}", val or "")
        if html_body:
            html_body = render_variables(html_body, sample)
        if not subject:
            subject = "Alpha Omega Phi — Test email"
        admin_name = _html.escape(admin.get("name") or "an admin")
        if not html_body:
            html_body = (
                f"""
                <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:32px;color:#222">
                  <h1 style="color:#C8102E;margin:0 0 12px;font-size:24px">Deliverability check</h1>
                  <p style="line-height:1.6">This is a test email sent by <strong>{admin_name}</strong> from the Alpha Omega Phi member portal to confirm that outbound email is configured correctly and reaches inboxes.</p>
                  <p style="line-height:1.6">If you can read this in your inbox, the integration is working.</p>
                  <p style="font-size:12px;color:#888;margin-top:24px">Sender: <code>{_html.escape(resend_from)}</code></p>
                </div>
                """
            )
        try:
            resp = await asyncio.to_thread(resend_sdk.Emails.send, {
                "from": resend_from,
                "to": [to_email],
                "subject": subject,
                "html": html_body,
                "tags": [{"name": "type", "value": "test_send"}],
            })
            message_id = ""
            try:
                message_id = (resp or {}).get("id", "") if isinstance(resp, dict) else getattr(resp, "id", "")
            except Exception:
                message_id = ""
            logger.info(f"Test email sent by {admin.get('email')} to {to_email} from {resend_from} (template={template_name or 'none'})")
            return {
                "ok": True,
                "detail": "Test email accepted by Brevo.",
                "to": to_email,
                "from": resend_from,
                "subject": subject,
                "template_name": template_name,
                "message_id": message_id,
            }
        except Exception as e:
            msg = str(e)
            logger.warning(f"Test email FAILED to {to_email} (from={resend_from}): {msg}")
            return {
                "ok": False,
                "detail": msg,
                "to": to_email,
                "from": resend_from,
                "subject": subject,
                "template_name": template_name,
            }

    @api.post("/email/webhook")
    async def resend_webhook(request: Request):
        """Accept Resend webhook events for opens, deliveries, bounces."""
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Bad JSON")
        event = payload.get("type", "")
        data = payload.get("data", {})
        tags = {t.get("name"): t.get("value") for t in (data.get("tags") or []) if t.get("name")}
        blast_id = tags.get("blast_id")
        if blast_id:
            inc = {}
            if "opened" in event:
                inc["opens"] = 1
            if "delivered" in event:
                inc["deliveries"] = 1
            if "bounced" in event:
                inc["bounces"] = 1
            if "complained" in event:
                inc["complaints"] = 1
            if inc:
                await db.email_blasts.update_one({"id": blast_id}, {"$inc": inc})
        return {"ok": True}

    # ============================================================
    # Email Signatures (personal + org-wide)
    # ============================================================
    @api.get("/email/signatures")
    async def list_signatures(user: dict = Depends(admin_tab_dep("email"))):
        cursor = db.email_signatures.find(
            {"$or": [{"kind": "org"}, {"kind": "personal", "owner_id": user["id"]}]},
            {"_id": 0},
        ).sort([("kind", 1), ("created_at", -1)])
        items = await cursor.to_list(200)
        # Normalize image URLs on read so previews render everywhere — even
        # rows created before Iter 143 that still have `/api/files/email/…`.
        out = []
        for s in items:
            row = _signature_out(s)
            row["body_html"] = normalize_email_images(row.get("body_html") or "")
            out.append(row)
        return out

    def _normalize_signature_html(html: str) -> str:
        """Iter 143: rewrite `/api/files/email/*` → `/api/email/image/*` and
        absolutize `src` at SAVE time so signature previews render correctly
        outside of authenticated admin sessions (Safari with ITP, incognito,
        webhook previews, etc.). This is the same helper `send_bulk_email`
        applies at send time, but running it on save keeps the on-page
        preview and the sent email in lockstep."""
        return normalize_email_images(html or "")

    @api.post("/email/signatures")
    async def create_signature(body: SignatureIn, user: dict = Depends(admin_tab_dep("email"))):
        doc = {
            "id": str(uuid.uuid4()),
            "name": body.name,
            "body_html": _normalize_signature_html(body.body_html),
            "kind": body.kind,
            "owner_id": user["id"],
            "created_at": iso(now_utc()),
        }
        await db.email_signatures.insert_one(doc)
        return _signature_out(doc)

    @api.put("/email/signatures/{sid}")
    async def update_signature(sid: str, body: SignatureUpdateIn, user: dict = Depends(admin_tab_dep("email"))):
        s = await db.email_signatures.find_one({"id": sid})
        if not s:
            raise HTTPException(status_code=404, detail="Signature not found")
        if s.get("kind") == "personal" and s.get("owner_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Not allowed")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "body_html" in updates:
            updates["body_html"] = _normalize_signature_html(updates["body_html"])
        if updates:
            await db.email_signatures.update_one({"id": sid}, {"$set": updates})
        s2 = await db.email_signatures.find_one({"id": sid}, {"_id": 0})
        return _signature_out(s2)

    @api.delete("/email/signatures/{sid}")
    async def delete_signature(sid: str, user: dict = Depends(admin_tab_dep("email"))):
        s = await db.email_signatures.find_one({"id": sid})
        if not s:
            raise HTTPException(status_code=404, detail="Signature not found")
        if s.get("kind") == "personal" and s.get("owner_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Not allowed")
        await db.email_signatures.delete_one({"id": sid})
        return {"ok": True}

    # ============================================================
    # Inline image upload (used by RichEditor in the email composer)
    # ============================================================
    @api.post("/email/upload-image")
    async def email_upload_image(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("email"))):
        """Upload an inline image for use in email composer / signatures.
        Reuses the chat_files collection so /api/files/{path} resolves it."""
        chunks = []
        total = 0
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 25 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="Image must be under 25 MB")
            chunks.append(chunk)
        data = b"".join(chunks)
        fname = (file.filename or "image").replace("/", "_")
        ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
        if ext not in image_extensions:
            raise HTTPException(status_code=400, detail="Only images allowed (jpg, png, gif, webp)")
        content_type = file.content_type or mime_by_ext.get(ext, "image/jpeg")
        file_id = str(uuid.uuid4())
        storage_path = f"email/{user['id']}/{file_id}/{fname}"

        def _put():
            return put_object(storage_path, data, content_type)
        await asyncio.to_thread(_put)

        rec = {
            "id": file_id,
            "filename": fname,
            "storage_path": storage_path,
            "content_type": content_type,
            "size": total,
            "kind": "image",
            "uploaded_by": user["id"],
            "is_deleted": False,
            "created_at": iso(now_utc()),
        }
        await db.chat_files.insert_one(rec)
        return {
            "id": file_id,
            "filename": fname,
            "url": f"/api/email/image/{storage_path}",
            "size": total,
            "content_type": content_type,
        }

    # ============================================================
    # Email attachments (docs — PDF, DOCX, XLSX, etc.)
    # Stored under `email/attachments/*` in the same chat_files
    # collection. Not exposed via a public URL; the bytes are pulled
    # at send time, base64-encoded, and delivered by Resend.
    # ============================================================
    _ATTACHMENT_MAX_MB = 20  # Resend hard-cap is ~40MB per email; keep headroom.
    _ATTACHMENT_ALLOWED_EXT = {
        # docs
        "pdf", "doc", "docx", "odt", "rtf", "txt",
        # sheets
        "xls", "xlsx", "ods", "csv",
        # slides
        "ppt", "pptx", "odp",
        # images (in case an admin wants image-as-attachment vs inline)
        "jpg", "jpeg", "png", "gif", "webp", "heic", "heif",
        # bundles
        "zip",
    }

    @api.post("/email/upload-attachment")
    async def email_upload_attachment(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("email"))):
        """Store a document that will be attached to the next email blast."""
        chunks: list[bytes] = []
        total = 0
        max_bytes = _ATTACHMENT_MAX_MB * 1024 * 1024
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status_code=413, detail=f"Attachment must be under {_ATTACHMENT_MAX_MB} MB")
            chunks.append(chunk)
        data = b"".join(chunks)
        fname = (file.filename or "attachment").replace("/", "_").replace("\\", "_")
        ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
        if ext not in _ATTACHMENT_ALLOWED_EXT:
            raise HTTPException(status_code=400, detail=f"File type .{ext or 'unknown'} isn't supported. Allowed: {', '.join(sorted(_ATTACHMENT_ALLOWED_EXT))}")
        content_type = file.content_type or mime_by_ext.get(ext, "application/octet-stream")
        file_id = str(uuid.uuid4())
        storage_path = f"email/attachments/{user['id']}/{file_id}/{fname}"

        def _put():
            return put_object(storage_path, data, content_type)
        await asyncio.to_thread(_put)

        rec = {
            "id": file_id,
            "filename": fname,
            "storage_path": storage_path,
            "content_type": content_type,
            "size": total,
            "kind": "attachment",
            "uploaded_by": user["id"],
            "is_deleted": False,
            "created_at": iso(now_utc()),
        }
        await db.chat_files.insert_one(rec)
        return {
            "id": file_id,
            "filename": fname,
            "size": total,
            "content_type": content_type,
        }

    @api.get("/email/attachments")
    async def list_recent_attachments(user: dict = Depends(admin_tab_dep("email"))):
        """Recent attachments uploaded by the current admin (useful for
        re-attaching the same file to multiple blasts)."""
        items = await db.chat_files.find(
            {"uploaded_by": user["id"], "kind": "attachment", "is_deleted": {"$ne": True}},
            {"_id": 0, "id": 1, "filename": 1, "size": 1, "content_type": 1, "created_at": 1},
        ).sort("created_at", -1).limit(50).to_list(50)
        return items

    @api.delete("/email/attachments/{attachment_id}")
    async def delete_attachment(attachment_id: str, user: dict = Depends(admin_tab_dep("email"))):
        rec = await db.chat_files.find_one({"id": attachment_id, "kind": "attachment"})
        if not rec:
            raise HTTPException(status_code=404, detail="Attachment not found")
        if rec.get("uploaded_by") != user["id"]:
            raise HTTPException(status_code=403, detail="You can only delete your own attachments")
        await db.chat_files.update_one({"id": attachment_id}, {"$set": {"is_deleted": True}})
        return {"ok": True}
