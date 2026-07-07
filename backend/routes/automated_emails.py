"""Automated email campaigns — extracted from server.py for clarity.

Module owns:
  - admin CRUD for automated campaigns (broadcast + system-managed)
  - merge-tag rendering for broadcast campaigns
  - the dues-reminder cadence (30d / 15d / 5d / +1d grace)
  - the admin dues-summary digest
  - the 5-minute background runner
  - built-in Weekly Digest + Annual Dues Reminders seeds

Module-level state (db, resend_sdk, RESEND_API_KEY, helpers …) is initialised
via register(). All helpers read from these module-level names so tests can
monkey-patch `routes.automated_emails.db = fake_db` and have the helpers see
the patched value at call time.

Public surface (paths preserved verbatim):
  GET    /api/automated-emails
  GET    /api/automated-emails/merge-tags
  GET    /api/automated-emails/dues-reminder-defaults
  POST   /api/automated-emails
  PUT    /api/automated-emails/{eid}
  DELETE /api/automated-emails/{eid}
  POST   /api/automated-emails/{eid}/run-now
  POST   /api/automated-emails/{eid}/preview
"""
import asyncio
import os
import uuid
import html as _h
from datetime import datetime, timedelta
from typing import List, Optional, Literal, Dict

from croniter import croniter as _croniter
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field


# ---------- Module-level injected state ----------
# All these are set by register(). Helpers read them on every call so tests
# can monkey-patch the module attributes.
db = None
iso = None
now_utc = None
logger = None
resend_sdk = None
RESEND_API_KEY: str = ""
RESEND_FROM: str = ""
RESEND_REPLY_TO: str = ""
send_bulk_email = None  # callable injected from server.py
send_sms = None  # callable injected from server.py (Brevo/Twilio unified sender)


# ---------- Constants ----------
AUTOMATED_SECTIONS = [
    "events", "photos", "documents", "new_members",
    "my_rsvps", "pending_hours", "birthday_greeting",
]

MERGE_TAGS = [
    {"tag": "{{member_name}}", "desc": "Recipient's first name"},
    {"tag": "{{upcoming_events}}", "desc": "Events in next 7 days"},
    {"tag": "{{new_photos}}", "desc": "New photo albums this week"},
    {"tag": "{{new_documents}}", "desc": "New AOP forms this week"},
    {"tag": "{{new_members}}", "desc": "Members who joined this week"},
    {"tag": "{{my_rsvps}}", "desc": "Recipient's upcoming RSVPs with re-RSVP link"},
    {"tag": "{{pending_hours}}", "desc": "Hours waiting approval (admin recipients only)"},
    {"tag": "{{birthday_greeting}}", "desc": "Personalized birthday wish when applicable"},
]

# Dues-reminder cadence (30d / 15d / 5d before, +1d grace). Each stage fires
# once per dues period — keyed off (user_id, expires_at, stage) in the
# dues_reminders_sent dedupe collection.
DUES_REMINDER_STAGES = [
    {"offset_days": 30, "stage": "before_30", "label": "30 days"},
    {"offset_days": 15, "stage": "before_15", "label": "15 days"},
    {"offset_days": 5,  "stage": "before_5",  "label": "5 days"},
    {"offset_days": -1, "stage": "grace_1",   "label": "Grace period"},
]
DUES_GRACE_DAYS = 15
DUES_REACTIVATION_FEE = 75.00
DUES_CONTACT_EMAIL = "info@alphaomegaphi.org"

DUES_REMINDER_DEFAULT_TEMPLATES = {
    "before_30": {
        "subject": "Your AOP dues renew in 30 days, {{first_name}}",
        "body_html": (
            "<p style=\"font-size:15px;line-height:1.55;color:#333\">Hi {{first_name}}, this is a "
            "friendly heads-up that your Alpha Omega Phi annual dues are due in "
            "<strong>30 days</strong> (on <strong>{{expires_at}}</strong>). Paying early keeps "
            "your access uninterrupted and helps us plan the year's events.</p>"
        ),
    },
    "before_15": {
        "subject": "Reminder: AOP dues due in 15 days, {{first_name}}",
        "body_html": (
            "<p style=\"font-size:15px;line-height:1.55;color:#333\">Hi {{first_name}}, your annual "
            "dues are due in <strong>15 days</strong> (on <strong>{{expires_at}}</strong>). "
            "Please take a moment to renew so we don't have to interrupt your access.</p>"
        ),
    },
    "before_5": {
        "subject": "⏰ Final notice — AOP dues due in 5 days, {{first_name}}",
        "body_html": (
            "<p style=\"font-size:15px;line-height:1.55;color:#333\">Hi {{first_name}}, this is your "
            "<strong>final reminder</strong>: AOP annual dues are due in <strong>5 days</strong> "
            "(on <strong>{{expires_at}}</strong>). Renew now to avoid a lapse in your membership.</p>"
        ),
    },
    "grace_1": {
        "subject": "Your AOP membership has lapsed — {{grace_days}}-day grace period started",
        "body_html": (
            "<p style=\"font-size:15px;line-height:1.55;color:#333\">Hi {{first_name}}, your AOP "
            "annual dues expired yesterday (on <strong>{{expires_at}}</strong>). You're now in a "
            "<strong>{{grace_days}}-day grace period</strong>. If your dues aren't paid by the "
            "end of this window, your account will be moved to <strong>inactive</strong> status "
            "and a <strong>${{reactivation_fee}} reactivation fee</strong> will be added on top "
            "of your annual dues.</p>"
            "<p style=\"font-size:14px;line-height:1.55;color:#333;margin-top:12px\">"
            "<strong>To reactivate after the grace period, you must contact the National office "
            "directly to discuss your reactivation.</strong></p>"
        ),
    },
}


# ---------- Pydantic models ----------
AutomatedSection = Literal[
    "events", "photos", "documents", "new_members",
    "my_rsvps", "pending_hours", "birthday_greeting",
]


class AutomatedEmailAudienceIn(BaseModel):
    type: Literal["all", "chapter", "tier", "status"] = "all"
    ids: List[str] = Field(default_factory=list, max_length=500)


class AutomatedEmailIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=200)
    body_html: str = Field("", max_length=200_000)
    cron_expression: str = "0 9 * * 1"
    is_active: bool = True
    audience: AutomatedEmailAudienceIn = Field(default_factory=AutomatedEmailAudienceIn)
    sections: Dict[AutomatedSection, bool] = Field(default_factory=dict)
    stage_templates: Dict[str, Dict[str, str]] = Field(default_factory=dict)


# ---------- Helpers (module-level so tests can patch state) ----------
def _automated_email_out(d: dict) -> dict:
    return {
        "id": d["id"],
        "name": d.get("name", ""),
        "subject": d.get("subject", ""),
        "body_html": d.get("body_html", ""),
        "cron_expression": d.get("cron_expression", "0 9 * * 1"),
        "is_active": bool(d.get("is_active", True)),
        "is_builtin": bool(d.get("is_builtin", False)),
        "kind": d.get("kind", "broadcast"),
        "audience": d.get("audience", {"type": "all", "ids": []}),
        "sections": d.get("sections", {}),
        "stage_templates": d.get("stage_templates", {}),
        "last_run_at": d.get("last_run_at"),
        "next_run_at": d.get("next_run_at"),
        "last_sent_count": d.get("last_sent_count", 0),
        "created_by_name": d.get("created_by_name", ""),
        "created_at": d.get("created_at"),
    }


def _next_cron_run(cron_expr: str, base: Optional[datetime] = None) -> Optional[datetime]:
    try:
        c = _croniter(cron_expr, base or now_utc())
        return c.get_next(datetime)
    except Exception as e:
        logger.warning(f"Bad cron expression '{cron_expr}': {e}")
        return None


async def _audience_recipients(audience: dict) -> List[dict]:
    q: dict = {}
    atype = audience.get("type", "all") if audience else "all"
    ids = audience.get("ids", []) if audience else []
    if atype == "chapter" and ids:
        q["chapter_id"] = {"$in": ids}
    elif atype == "tier" and ids:
        q["membership_tier"] = {"$in": ids}
    elif atype == "status" and ids:
        q["status"] = {"$in": ids}
    else:
        q["status"] = {"$ne": "inactive"}
    return await db.users.find(
        q, {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1, "birthday": 1}
    ).to_list(2000)


def _render_subject(subj: str, user: dict) -> str:
    first_name = (user.get("name") or "Member").split(" ")[0]
    return (subj or "").replace("{{member_name}}", _h.escape(first_name))


async def _render_automated_body(campaign: dict, user: dict) -> str:
    body = campaign.get("body_html") or ""
    sections = campaign.get("sections") or {}
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")

    def section_card(title: str, inner: str) -> str:
        return (
            f'<div style="background:#fff;border-radius:14px;padding:16px;margin:12px 0;'
            f'border:1px solid #eee"><div style="font-size:11px;text-transform:uppercase;'
            f'letter-spacing:.16em;color:#C8102E;font-weight:700;margin-bottom:8px">'
            f'{_h.escape(title)}</div>{inner}</div>'
        )

    first_name = (user.get("name") or "Member").split(" ")[0]
    body = body.replace("{{member_name}}", _h.escape(first_name))

    if "{{upcoming_events}}" in body:
        if sections.get("events", True):
            soon = now_utc() + timedelta(days=7)
            evs = await db.events.find(
                {"start_at": {"$gte": iso(now_utc()), "$lte": iso(soon)}, "parent_event_id": {"$in": [None, ""]}},
                {"_id": 0, "id": 1, "title": 1, "start_at": 1, "location": 1},
            ).sort("start_at", 1).to_list(20)
            inner = "".join(
                f'<div style="margin:6px 0"><a href="{frontend}/events/{e["id"]}" '
                f'style="color:#0A2463;font-weight:600;text-decoration:none">{_h.escape(e.get("title",""))}'
                f'</a><div style="font-size:12px;color:#666">{e.get("start_at","")[:10]}'
                f'{" · " + _h.escape(e["location"]) if e.get("location") else ""}</div></div>'
                for e in evs
            ) or '<div style="color:#888;font-size:13px">Nothing on the calendar in the next 7 days.</div>'
            body = body.replace("{{upcoming_events}}", section_card("Upcoming events", inner))
        else:
            body = body.replace("{{upcoming_events}}", "")

    week_ago = iso(now_utc() - timedelta(days=7))
    for tag, enabled, fn in [
        ("{{new_photos}}", "photos",
         lambda: db.photo_albums.find({"created_at": {"$gte": week_ago}, "is_default": {"$ne": True}}, {"_id": 0, "name": 1}).to_list(20)),
        ("{{new_documents}}", "documents",
         lambda: db.documents.find({"created_at": {"$gte": week_ago}, "is_deleted": {"$ne": True}}, {"_id": 0, "title": 1}).to_list(20)),
        ("{{new_members}}", "new_members",
         lambda: db.users.find({"created_at": {"$gte": week_ago}}, {"_id": 0, "name": 1}).to_list(50)),
    ]:
        if tag in body:
            if sections.get(enabled, True):
                items = await fn()
                inner = "".join(
                    f'<div style="margin:4px 0;font-size:13px;color:#333">• '
                    f'{_h.escape(it.get("name") or it.get("title") or "")}</div>'
                    for it in items
                ) or '<div style="color:#888;font-size:13px">Nothing new this week.</div>'
                title = {"photos": "New photo albums", "documents": "New AOP forms", "new_members": "New members this week"}[enabled]
                body = body.replace(tag, section_card(title, inner))
            else:
                body = body.replace(tag, "")

    if "{{my_rsvps}}" in body:
        if sections.get("my_rsvps", True):
            rsvps = await db.rsvps.find({"user_id": user["id"]}, {"_id": 0, "event_id": 1, "ticket_id": 1, "ticket_type": 1}).to_list(20)
            event_ids = [r["event_id"] for r in rsvps]
            evs = await db.events.find(
                {"id": {"$in": event_ids}, "start_at": {"$gte": iso(now_utc())}},
                {"_id": 0, "id": 1, "title": 1, "start_at": 1},
            ).to_list(20)
            ev_by_id = {e["id"]: e for e in evs}
            rows = []
            for r in rsvps:
                e = ev_by_id.get(r["event_id"])
                if not e:
                    continue
                rows.append(
                    f'<div style="margin:6px 0;font-size:13px"><a href="{frontend}/events/{e["id"]}" '
                    f'style="color:#0A2463;font-weight:600">{_h.escape(e["title"])}</a>'
                    f'<div style="color:#666;font-size:12px">{e["start_at"][:10]} · '
                    f'{_h.escape((r.get("ticket_type") or "general").replace("_"," ").title())}</div></div>'
                )
            inner = "".join(rows) or '<div style="color:#888;font-size:13px">You have no upcoming RSVPs.</div>'
            body = body.replace("{{my_rsvps}}", section_card("Your upcoming RSVPs", inner))
        else:
            body = body.replace("{{my_rsvps}}", "")

    if "{{pending_hours}}" in body:
        if sections.get("pending_hours", True) and user.get("role") == "admin":
            n = await db.volunteer_hours.count_documents({"status": "pending"})
            inner = (
                f'<div style="font-size:13px"><strong>{n}</strong> hour log{"s" if n != 1 else ""} '
                f'waiting on approval. <a href="{frontend}/admin" style="color:#C8102E">'
                f'Open the admin queue →</a></div>'
            )
            body = body.replace("{{pending_hours}}", section_card("Hours waiting approval", inner))
        else:
            body = body.replace("{{pending_hours}}", "")

    if "{{birthday_greeting}}" in body:
        if sections.get("birthday_greeting", True):
            bd = user.get("birthday")
            this_week_md = {(now_utc() + timedelta(days=i)).strftime("%m-%d") for i in range(7)}
            if bd and bd[-5:] in this_week_md:
                inner = (
                    f'<div style="font-size:14px">🎂 Happy birthday week, {_h.escape(first_name)}! '
                    f'The whole chapter is celebrating with you. Stop by the chat and share a memory.</div>'
                )
                body = body.replace("{{birthday_greeting}}", section_card("It's your birthday week!", inner))
            else:
                body = body.replace("{{birthday_greeting}}", "")
        else:
            body = body.replace("{{birthday_greeting}}", "")

    return body


def _apply_dues_placeholders(text: str, first_name: str, expires_iso: str) -> str:
    exp_pretty = (expires_iso or "")[:10]
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    pay_link = f"{frontend}/profile"
    repl = {
        "{{first_name}}": first_name or "Member",
        "{{member_name}}": first_name or "Member",
        "{{expires_at}}": exp_pretty,
        "{{grace_days}}": str(DUES_GRACE_DAYS),
        "{{reactivation_fee}}": f"{DUES_REACTIVATION_FEE:,.2f}",
        "{{pay_link}}": pay_link,
        "{{contact_email}}": DUES_CONTACT_EMAIL,
    }
    out = text or ""
    for k, v in repl.items():
        out = out.replace(k, v)
    return out


def _dues_reminder_email_html(
    member_name: str,
    stage: str,
    expires_iso: str,
    stage_templates: Optional[dict] = None,
) -> tuple[str, str]:
    first_name = (member_name or "Member").split(" ")[0]
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    overrides = (stage_templates or {}).get(stage) or {}
    default = DUES_REMINDER_DEFAULT_TEMPLATES.get(stage) or DUES_REMINDER_DEFAULT_TEMPLATES["before_30"]
    raw_subject = (overrides.get("subject") or default["subject"]).strip()
    raw_body = (overrides.get("body_html") or default["body_html"]).strip()
    subject = _apply_dues_placeholders(raw_subject, first_name, expires_iso)
    intro = _apply_dues_placeholders(raw_body, first_name, expires_iso)
    contact_line = (
        '<p style="font-size:13px;color:#444;margin:14px 0 0">Questions about your renewal? '
        'Reply to this email or contact the National office at '
        f'<a href="mailto:{DUES_CONTACT_EMAIL}" style="color:#C8102E;font-weight:600">{DUES_CONTACT_EMAIL}</a>.</p>'
    )
    pay_btn = (
        f'<a href="{frontend}/profile" '
        'style="display:inline-block;background:#C8102E;color:#fff;border-radius:999px;'
        'padding:12px 22px;text-decoration:none;font-weight:700;font-size:14px;margin-top:14px">'
        'Pay my annual dues →</a>'
    )
    body = f"""<div style="font-family:-apple-system,sans-serif;max-width:640px;margin:0 auto;padding:24px;background:#f7f5f0">
  <h1 style="color:#0A2463;margin:0 0 6px;font-size:24px">Alpha Omega Phi · Annual Dues</h1>
  <div style="height:3px;background:#C8102E;width:54px;margin-bottom:18px"></div>
  {intro}
  <div style="text-align:center">{pay_btn}</div>
  {contact_line}
  <p style="font-size:11px;color:#999;margin-top:22px;border-top:1px solid #e7e5e0;padding-top:14px">
    Alpha Omega Phi Military Fraternity &amp; Sorority, Inc. · 501(c)(3) nonprofit.<br/>
    This is an automated reminder. Once your dues are paid, the next reminder won't fire until the following cycle.
  </p>
</div>"""
    return subject, body

def _dues_reminder_sms_body(member_name: str, stage: str, expires_iso: str) -> str:
    """Short SMS companion for dues reminders — kept under ~320 chars so it
    lands as a single-segment message when possible."""
    first_name = (member_name or "Member").split(" ")[0] or "Member"
    exp_short = (expires_iso or "")[:10]
    stage_line = {
        "before_30": f"Hi {first_name}, AOP annual dues renew in ~30 days (on {exp_short}). Paying early keeps your access uninterrupted.",
        "before_15": f"Hi {first_name}, AOP dues due in ~15 days ({exp_short}). Renew now to avoid interruption.",
        "before_5":  f"Hi {first_name}, final reminder: AOP dues due in ~5 days ({exp_short}). Please renew today.",
        "grace_1":   f"Hi {first_name}, your AOP dues lapsed on {exp_short}. You're in a short grace window — renew ASAP to keep membership active.",
    }.get(stage, f"Hi {first_name}, this is a reminder about your AOP annual dues (expires {exp_short}).")
    return f"{stage_line} Visit your profile to pay. Reply STOP to opt out."




async def _send_admin_dues_summary(campaign: dict, pending_records: list[dict]) -> int:
    """Send the dues-reminder digest to eligible admins.

    Per iter101 the campaign no longer emails members directly — instead
    each cycle sends ONE consolidated dues-reminder email to admins whose
    role is one of:
      - full-access admin (`admin_role in {None, "", "full"}`)
      - operations manager (`admin_role == "operations_manager"`)
      - membership manager (`admin_role == "membership_manager"`)
    Other admin sub-roles (governor_manager, etc.) are skipped — they
    were never the ones chasing renewals in the first place.
    """
    if not RESEND_API_KEY or not pending_records:
        return 0
    # Whitelist of admin_roles that should receive dues reminders. `None`
    # / "" / "full" all map to the top-level "full-access admin" bucket
    # because legacy admins were seeded without an admin_role.
    ELIGIBLE_ADMIN_ROLES = {None, "", "full", "operations_manager", "membership_manager"}
    admin_cursor = db.users.find(
        {
            "role": "admin",
            "email": {"$exists": True, "$ne": ""},
            "email_opt_out": {"$ne": True},
            "email_prefs.dues_reminders": {"$ne": False},
        },
        {"_id": 0, "id": 1, "name": 1, "email": 1, "admin_role": 1},
    )
    admins = []
    async for a in admin_cursor:
        if a.get("admin_role") not in ELIGIBLE_ADMIN_ROLES:
            continue
        email = (a.get("email") or "").strip()
        if email:
            admins.append({"name": a.get("name", "") or email, "email": email})
    if not admins:
        logger.info("Dues reminder: no eligible admin recipients (full-access / operations / membership managers).")
        return 0

    by_stage: dict[str, list[dict]] = {}
    for r in pending_records:
        by_stage.setdefault(r["stage_label"], []).append(r)

    today_label = now_utc().strftime("%b %d, %Y")
    rows_html_parts: list[str] = []
    for label, items in by_stage.items():
        rows_html_parts.append(
            f'<tr><td colspan="3" style="background:#f7f5f0;padding:10px 14px;'
            f'font-weight:700;color:#0A2463;border-bottom:1px solid #e7e5e0;'
            f'text-transform:uppercase;letter-spacing:.08em;font-size:11px">'
            f'{_h.escape(label)} · {len(items)} member{"s" if len(items) != 1 else ""}'
            f'</td></tr>'
        )
        for item in items:
            exp_iso = (item.get("expires_at") or "")[:10]
            try:
                exp_dt = datetime.strptime(exp_iso, "%Y-%m-%d")
                exp_pretty = exp_dt.strftime("%b %d, %Y")
            except Exception:
                exp_pretty = exp_iso or "—"
            rows_html_parts.append(
                f'<tr>'
                f'<td style="padding:10px 14px;border-bottom:1px solid #f0eee9;font-size:14px">'
                f'<div style="font-weight:600;color:#0A2463">{_h.escape(item["member_name"])}</div>'
                f'<div style="font-size:12px;color:#666">{_h.escape(item["member_email"])}</div>'
                f'</td>'
                f'<td style="padding:10px 14px;border-bottom:1px solid #f0eee9;font-size:13px;color:#444;white-space:nowrap">'
                f'{_h.escape(exp_pretty)}'
                f'</td>'
                f'</tr>'
            )

    total = len(pending_records)
    subject = f"AOP dues reminders — {total} member{'s' if total != 1 else ''} to follow up on"
    body_html = f"""<div style="font-family:-apple-system,sans-serif;max-width:680px;margin:0 auto;padding:24px;background:#f7f5f0">
  <h1 style="color:#0A2463;margin:0 0 6px;font-size:22px">Dues Reminder</h1>
  <div style="height:3px;background:#C8102E;width:54px;margin-bottom:14px"></div>
  <p style="color:#444;font-size:14px;margin:0 0 18px;line-height:1.5">
    The following <strong>{total}</strong> member{"s have" if total != 1 else " has"} dues coming due — <strong>{_h.escape(campaign.get("name") or "Dues reminders")}</strong> automated check on {today_label}.
    Please follow up personally to renew their membership.
  </p>
  <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:14px;overflow:hidden;border:1px solid #e7e5e0">
    <thead>
      <tr style="background:#0A2463;color:#fff">
        <th style="text-align:left;padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:.08em">Member</th>
        <th style="text-align:left;padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:.08em">Membership expires</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html_parts)}
    </tbody>
  </table>
  <p style="font-size:11px;color:#999;margin-top:22px;border-top:1px solid #e7e5e0;padding-top:14px">
    You&#39;re receiving this because you&#39;re a full-access admin, operations manager, or membership manager for Alpha Omega Phi. Reminder stages: 30 days, 15 days, 5 days before expiration, and a 1-day grace notice.
  </p>
</div>"""

    delivered = 0
    for admin in admins:
        try:
            await asyncio.to_thread(resend_sdk.Emails.send, {
                "from": RESEND_FROM,
                "to": [admin["email"]],
                "reply_to": RESEND_REPLY_TO,
                "subject": subject,
                "html": body_html,
                "tags": [
                    {"name": "type", "value": "dues_admin_summary"},
                    {"name": "campaign_id", "value": campaign.get("id", "")},
                ],
            })
            delivered += 1
        except Exception as e:
            logger.warning(f"Dues summary delivery failed for admin {admin['email']}: {e}")
    logger.info(f"Dues reminder summary dispatched to {delivered}/{len(admins)} admins (total reminders={total}).")
    return delivered


async def _send_dues_reminders(campaign: dict) -> int:
    if not RESEND_API_KEY:
        logger.info(f"Dues reminders '{campaign.get('name')}' skipped — no RESEND_API_KEY")
        return 0
    today = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    stage_templates = campaign.get("stage_templates") or {}
    total_sent = 0
    sent_records: list[dict] = []
    for stage_def in DUES_REMINDER_STAGES:
        offset = stage_def["offset_days"]
        stage = stage_def["stage"]
        target_day = today + timedelta(days=offset)
        day_start = iso(target_day)
        day_end = iso(target_day + timedelta(days=1))
        cursor = db.users.find(
            {
                "membership_expires_at": {"$gte": day_start, "$lt": day_end},
                "status": {"$ne": "inactive"},
                "is_lifetime_member": {"$ne": True},
                "email": {"$exists": True, "$ne": ""},
                "email_opt_out": {"$ne": True},
                "email_prefs.dues_reminders": {"$ne": False},
            },
            {"_id": 0, "id": 1, "name": 1, "email": 1, "membership_expires_at": 1, "phone": 1, "sms_opt_out": 1},
        )
        async for u in cursor:
            email = (u.get("email") or "").strip()
            if not email:
                continue
            expires = u.get("membership_expires_at") or ""
            already = await db.dues_reminders_sent.find_one(
                {"user_id": u["id"], "expires_at": expires, "stage": stage}, {"_id": 1}
            )
            if already:
                continue
            try:
                subject, body_html = _dues_reminder_email_html(
                    u.get("name", ""), stage, expires, stage_templates=stage_templates,
                )
                await send_bulk_email(
                    to_email=email,
                    subject=subject,
                    html_body=body_html,
                    recipient_id=u["id"],
                    tags=[
                        {"name": "type", "value": "dues_reminder"},
                        {"name": "stage", "value": stage},
                        {"name": "campaign_id", "value": campaign["id"]},
                    ],
                )
                await db.dues_reminders_sent.insert_one({
                    "id": str(uuid.uuid4()),
                    "user_id": u["id"],
                    "user_name": u.get("name", ""),
                    "user_email": email,
                    "expires_at": expires,
                    "stage": stage,
                    "sent_at": iso(now_utc()),
                })
                # Best-effort SMS companion — respects the global SMS kill-switch
                # inside send_sms(). Only fires when the member has a phone,
                # hasn't opted out of SMS, and send_sms was wired at register().
                phone = (u.get("phone") or "").strip()
                if send_sms and phone and not u.get("sms_opt_out"):
                    try:
                        sms_body = _dues_reminder_sms_body(
                            u.get("name", "") or email, stage, expires,
                        )
                        sms_ok = await send_sms(phone, sms_body)
                        if sms_ok:
                            logger.info(f"Dues reminder SMS '{stage}' sent to {phone}")
                    except Exception as sms_e:
                        logger.warning(f"Dues reminder SMS {stage} failed for {phone}: {sms_e}")
                sent_records.append({
                    "stage": stage,
                    "stage_label": stage_def["label"],
                    "member_name": u.get("name", "") or email,
                    "member_email": email,
                    "expires_at": expires,
                })
                total_sent += 1
                logger.info(f"Dues reminder '{stage}' sent to {email} (exp {expires[:10]})")
            except Exception as e:
                logger.warning(f"Dues reminder {stage} failed/skipped for {email}: {e}")
    if total_sent > 0:
        try:
            await _send_admin_dues_summary(campaign, sent_records)
        except Exception as e:
            logger.warning(f"Admin dues summary email failed: {e}")
    return total_sent


async def _send_automated_email(campaign: dict) -> int:
    if (campaign.get("kind") or "broadcast") == "dues_reminders":
        return await _send_dues_reminders(campaign)
    if not RESEND_API_KEY:
        logger.info(f"Automated email '{campaign.get('name')}' skipped — no RESEND_API_KEY")
        return 0
    recipients = await _audience_recipients(campaign.get("audience") or {})
    sent = 0
    for u in recipients:
        email = (u.get("email") or "").strip()
        if not email:
            continue
        try:
            html = await _render_automated_body(campaign, u)
            subject = _render_subject(campaign["subject"], u)
            await asyncio.to_thread(resend_sdk.Emails.send, {
                "from": RESEND_FROM,
                "to": [email],
                "subject": subject,
                "html": html,
                "tags": [{"name": "type", "value": "automated"},
                         {"name": "campaign_id", "value": campaign["id"]}],
            })
            sent += 1
        except Exception as e:
            logger.warning(f"Automated email send failed to {email}: {e}")
    return sent


async def _automated_email_loop():
    """Every 5 minutes, send any campaigns whose `next_run_at` has elapsed."""
    while True:
        try:
            cursor = db.automated_emails.find(
                {"is_active": True, "next_run_at": {"$lte": iso(now_utc())}},
                {"_id": 0},
            )
            async for campaign in cursor:
                logger.info(f"Running automated email campaign '{campaign.get('name')}' (id={campaign['id']})")
                sent = await _send_automated_email(campaign)
                next_run = _next_cron_run(campaign.get("cron_expression", "0 9 * * 1"))
                await db.automated_emails.update_one(
                    {"id": campaign["id"]},
                    {"$set": {
                        "last_run_at": iso(now_utc()),
                        "last_sent_count": sent,
                        "next_run_at": iso(next_run) if next_run else None,
                    }},
                )
        except Exception as e:
            logger.warning(f"Automated email loop error: {e}")
        await asyncio.sleep(300)


async def seed_builtin_automated_emails():
    existing = await db.automated_emails.find_one({"id": "builtin_weekly_digest"})
    if existing:
        return
    # Honor admin override: if an admin previously deleted this built-in,
    # don't silently resurrect it on the next boot.
    if await db.deleted_builtin_automated_emails.find_one({"id": "builtin_weekly_digest"}):
        logger.info("Skipping Weekly Digest seed — tombstoned by an admin.")
        return
    body_html = """<div style="font-family:-apple-system,sans-serif;max-width:640px;margin:0 auto;padding:24px;background:#f7f5f0">
  <h1 style="color:#0A2463;margin:0 0 4px;font-size:28px">Good morning, {{member_name}}</h1>
  <p style="color:#666;font-size:14px">Here's what's happening this week in Alpha Omega Phi.</p>
  {{birthday_greeting}}
  {{my_rsvps}}
  {{upcoming_events}}
  {{new_photos}}
  {{new_documents}}
  {{new_members}}
  {{pending_hours}}
  <p style="font-size:12px;color:#888;margin-top:24px">You're receiving this because you're a member of Alpha Omega Phi. Replies go to info@aop-app.org.</p>
</div>"""
    next_run = _next_cron_run("0 9 * * 1")
    doc = {
        "id": "builtin_weekly_digest",
        "name": "Weekly Digest",
        "subject": "Your AOP weekly digest — {{member_name}}",
        "body_html": body_html,
        "cron_expression": "0 9 * * 1",
        "is_active": True,
        "is_builtin": True,
        "audience": {"type": "all", "ids": []},
        "sections": {s: True for s in AUTOMATED_SECTIONS},
        "last_run_at": None,
        "next_run_at": iso(next_run) if next_run else None,
        "last_sent_count": 0,
        "created_by": None,
        "created_by_name": "System",
        "created_at": iso(now_utc()),
    }
    await db.automated_emails.insert_one(doc)
    logger.info("Seeded built-in Weekly Digest campaign")


async def seed_builtin_dues_reminders():
    existing = await db.automated_emails.find_one({"id": "builtin_dues_reminders"})
    if existing:
        return
    if await db.deleted_builtin_automated_emails.find_one({"id": "builtin_dues_reminders"}):
        logger.info("Skipping Annual Dues Reminders seed — tombstoned by an admin.")
        return
    next_run = _next_cron_run("0 9 * * *")
    doc = {
        "id": "builtin_dues_reminders",
        "name": "Annual Dues Reminders",
        "subject": "Your AOP annual dues reminder",
        "body_html": "",
        "cron_expression": "0 9 * * *",
        "is_active": True,
        "is_builtin": True,
        "kind": "dues_reminders",
        "audience": {"type": "all", "ids": []},
        "sections": {},
        "last_run_at": None,
        "next_run_at": iso(next_run) if next_run else None,
        "last_sent_count": 0,
        "created_by": None,
        "created_by_name": "System",
        "created_at": iso(now_utc()),
    }
    await db.automated_emails.insert_one(doc)
    logger.info("Seeded built-in Annual Dues Reminders campaign")


# ---------- Wire admin endpoints ----------
def register(
    api,
    *,
    db: object,
    admin_tab_dep,
    iso,
    now_utc,
    logger,
    resend_sdk,
    resend_api_key: str,
    resend_from: str,
    resend_reply_to: str,
    send_bulk_email,
    send_sms=None,
):
    """Bind module-level state and register the admin endpoints."""
    # Bind module-level injected state so the helpers above can read fresh
    # values at call time (allows monkey-patching from tests).
    g = globals()
    g["db"] = db
    g["iso"] = iso
    g["now_utc"] = now_utc
    g["logger"] = logger
    g["resend_sdk"] = resend_sdk
    g["RESEND_API_KEY"] = resend_api_key
    g["RESEND_FROM"] = resend_from
    g["RESEND_REPLY_TO"] = resend_reply_to
    g["send_bulk_email"] = send_bulk_email
    g["send_sms"] = send_sms

    @api.get("/automated-emails")
    async def list_automated_emails(_: dict = Depends(admin_tab_dep("email"))):
        docs = await db.automated_emails.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
        return [_automated_email_out(d) for d in docs]

    @api.get("/automated-emails/merge-tags")
    async def list_merge_tags(_: dict = Depends(admin_tab_dep("email"))):
        return {"tags": MERGE_TAGS, "sections": AUTOMATED_SECTIONS}

    @api.get("/automated-emails/dues-reminder-defaults")
    async def get_dues_reminder_defaults(_: dict = Depends(admin_tab_dep("email"))):
        return {
            "stages": DUES_REMINDER_STAGES,
            "defaults": DUES_REMINDER_DEFAULT_TEMPLATES,
            "placeholders": [
                {"tag": "{{first_name}}", "desc": "Recipient's first name"},
                {"tag": "{{member_name}}", "desc": "Alias of first_name"},
                {"tag": "{{expires_at}}", "desc": "Member's dues expiration date (YYYY-MM-DD)"},
                {"tag": "{{grace_days}}", "desc": f"Grace-period length ({DUES_GRACE_DAYS} days)"},
                {"tag": "{{reactivation_fee}}", "desc": f"Reactivation fee (${DUES_REACTIVATION_FEE:,.2f})"},
                {"tag": "{{pay_link}}", "desc": "Profile URL where members can pay"},
                {"tag": "{{contact_email}}", "desc": "National office contact email"},
            ],
        }

    @api.post("/automated-emails")
    async def create_automated_email(body: AutomatedEmailIn, admin: dict = Depends(admin_tab_dep("email"))):
        if not _croniter.is_valid(body.cron_expression):
            raise HTTPException(status_code=400, detail="Invalid cron expression. Try '0 9 * * 1' for Mondays at 9am UTC.")
        next_run = _next_cron_run(body.cron_expression)
        doc = {
            "id": str(uuid.uuid4()),
            "name": body.name.strip(),
            "subject": body.subject.strip(),
            "body_html": body.body_html,
            "cron_expression": body.cron_expression,
            "is_active": body.is_active,
            "is_builtin": False,
            "audience": body.audience.model_dump(),
            "sections": body.sections or {},
            "last_run_at": None,
            "next_run_at": iso(next_run) if next_run else None,
            "last_sent_count": 0,
            "created_by": admin["id"],
            "created_by_name": admin.get("name", ""),
            "created_at": iso(now_utc()),
        }
        await db.automated_emails.insert_one(doc)
        return _automated_email_out(doc)

    @api.put("/automated-emails/{eid}")
    async def update_automated_email(eid: str, body: AutomatedEmailIn, _: dict = Depends(admin_tab_dep("email"))):
        e = await db.automated_emails.find_one({"id": eid})
        if not e:
            raise HTTPException(status_code=404, detail="Automated email not found")
        if not _croniter.is_valid(body.cron_expression):
            raise HTTPException(status_code=400, detail="Invalid cron expression.")
        next_run = _next_cron_run(body.cron_expression)
        if (e.get("kind") or "broadcast") == "dues_reminders":
            sets = {
                "name": body.name.strip(),
                "is_active": body.is_active,
                "cron_expression": body.cron_expression,
                "next_run_at": iso(next_run) if next_run else None,
                "stage_templates": body.stage_templates or {},
            }
        else:
            sets = {
                "name": body.name.strip(),
                "subject": body.subject.strip(),
                "body_html": body.body_html,
                "cron_expression": body.cron_expression,
                "is_active": body.is_active,
                "audience": body.audience.model_dump(),
                "sections": body.sections or {},
                "next_run_at": iso(next_run) if next_run else None,
            }
        await db.automated_emails.update_one({"id": eid}, {"$set": sets})
        fresh = await db.automated_emails.find_one({"id": eid}, {"_id": 0})
        return _automated_email_out(fresh)

    @api.delete("/automated-emails/{eid}")
    async def delete_automated_email(eid: str, admin: dict = Depends(admin_tab_dep("email"))):
        """Admins have full override authority — they can delete any campaign,
        including built-in ones. Deleted built-ins are tombstoned in
        `deleted_builtin_automated_emails` so the boot-time seeders won't
        silently resurrect them on the next restart."""
        e = await db.automated_emails.find_one({"id": eid})
        if not e:
            raise HTTPException(status_code=404, detail="Automated email not found")
        if e.get("is_builtin"):
            await db.deleted_builtin_automated_emails.update_one(
                {"id": eid},
                {"$setOnInsert": {
                    "id": eid,
                    "name": e.get("name", ""),
                    "kind": e.get("kind", "broadcast"),
                    "deleted_by": admin["id"],
                    "deleted_by_name": admin.get("name", ""),
                    "deleted_at": iso(now_utc()),
                }},
                upsert=True,
            )
        await db.automated_emails.delete_one({"id": eid})
        return {"ok": True}

    @api.post("/automated-emails/{eid}/run-now")
    async def run_automated_email_now(eid: str, admin: dict = Depends(admin_tab_dep("email"))):
        e = await db.automated_emails.find_one({"id": eid})
        if not e:
            raise HTTPException(status_code=404, detail="Automated email not found")
        sent = await _send_automated_email(e)
        next_run = _next_cron_run(e.get("cron_expression", "0 9 * * 1"))
        await db.automated_emails.update_one({"id": eid}, {"$set": {
            "last_run_at": iso(now_utc()),
            "last_sent_count": sent,
            "next_run_at": iso(next_run) if next_run else None,
        }})
        return {"sent": sent}

    @api.post("/automated-emails/{eid}/preview")
    async def preview_automated_email(eid: str, admin: dict = Depends(admin_tab_dep("email"))):
        e = await db.automated_emails.find_one({"id": eid})
        if not e:
            raise HTTPException(status_code=404, detail="Automated email not found")
        if (e.get("kind") or "broadcast") == "dues_reminders":
            preview_exp = iso(now_utc() + timedelta(days=30))
            sample_name = admin.get("name") or "Member"
            stage_templates = e.get("stage_templates") or {}
            parts = []
            for stage_def in DUES_REMINDER_STAGES:
                subj, body = _dues_reminder_email_html(
                    sample_name, stage_def["stage"], preview_exp, stage_templates=stage_templates,
                )
                parts.append(
                    f'<div style="background:#fff;border-bottom:6px solid #f0ebe1;padding:18px 22px;'
                    f'font-family:-apple-system,sans-serif">'
                    f'<div style="font-size:10px;text-transform:uppercase;letter-spacing:.18em;color:#C8102E;font-weight:800">'
                    f'Stage · {stage_def["label"]}</div>'
                    f'<div style="font-size:13px;color:#666;margin-top:4px"><strong>Subject:</strong> {subj}</div>'
                    f'</div>{body}'
                )
            return {"subject": "Annual Dues Reminders — preview of all four stages",
                    "body_html": "".join(parts)}
        rendered = await _render_automated_body(e, admin)
        subject = _render_subject(e["subject"], admin)
        return {"subject": subject, "body_html": rendered}

    # Expose hooks the server.py startup uses (back-compat for the existing
    # register.* attribute pattern used by other modules).
    register.automated_email_loop = _automated_email_loop
    register.seed_builtin_automated_emails = seed_builtin_automated_emails
    register.seed_builtin_dues_reminders = seed_builtin_dues_reminders
