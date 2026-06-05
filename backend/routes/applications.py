"""Public application submit + admin review (approve/reject) flow.

Extracted from server.py. Owns:
  - POST /auth/apply  — public open-registration with applicant-chosen password
  - GET  /admin/applications  — admin listing
  - POST /admin/applications/{id}/review  — approve (creates user) / reject

Plus the 3 Resend email templates: admin notification, approval welcome, rejection.

Cross-cutting deps injected via register kwargs (db, hash_password, iso, now_utc,
resend SDK, logger, admin_tab_dep, public_user is NOT needed — we return raw
dicts because the review handler returns just {ok, user_id, ...}).
"""
import asyncio
import html as _html
import os
import uuid
from datetime import timedelta
from typing import Optional

from fastapi import Depends, HTTPException

from models import PublicApplicationIn, ApplicationReviewIn


def application_out(a: dict) -> dict:
    return {
        "id": a["id"],
        "first_name": a.get("first_name", ""),
        "last_name": a.get("last_name", ""),
        "name": (a.get("first_name", "") + " " + a.get("last_name", "")).strip(),
        "email": a.get("email", ""),
        "line_name": a.get("line_name", ""),
        "intake_line": a.get("intake_line", ""),
        "intake_completed_at": a.get("intake_completed_at", ""),
        "address": a.get("address", ""),
        "city": a.get("city", ""),
        "state": a.get("state", ""),
        "zip_code": a.get("zip_code", ""),
        "country": a.get("country", ""),
        "status": a.get("status", "pending"),
        "created_at": a.get("created_at"),
        "reviewed_at": a.get("reviewed_at"),
        "reviewed_by": a.get("reviewed_by"),
        "review_note": a.get("review_note", ""),
        "user_id": a.get("user_id"),
    }


def register(
    api,
    *,
    db,
    admin_tab_dep,
    iso,
    now_utc,
    hash_password,
    resend_sdk,
    resend_api_key: str,
    resend_from: str,
    logger,
):

    def _frontend_url() -> str:
        return os.environ.get("FRONTEND_URL", "http://localhost:3000")

    async def send_application_admin_notification(application: dict) -> bool:
        if not resend_api_key:
            logger.info("Application notification skipped — no RESEND_API_KEY")
            return False
        cursor = db.users.find({"role": "admin"}, {"_id": 0, "email": 1, "name": 1, "admin_role": 1})
        recipients = []
        async for adm in cursor:
            e = (adm.get("email") or "").strip()
            if e and (adm.get("admin_role") or "full") in ("full", "membership_manager"):
                recipients.append(e)
        if not recipients:
            logger.warning("No admin recipients for application notification")
            return False
        frontend = _frontend_url()
        name = _html.escape(f"{application.get('first_name', '')} {application.get('last_name', '')}".strip())
        email = _html.escape(application.get("email", ""))
        line = _html.escape(application.get("line_name", "") or "—")
        chapter_state = _html.escape(application.get("state", "") or "—")
        intake = _html.escape(application.get("intake_completed_at", "") or "—")
        body = f"""
        <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:28px;background:#fff;color:#222">
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:.16em;color:#C8102E;font-weight:700">New application</div>
          <h1 style="color:#0A2463;margin:6px 0 14px;font-size:24px">{name} is requesting access</h1>
          <div style="background:#f7f5f0;border-radius:14px;padding:18px;margin:18px 0;font-size:14px;line-height:1.7">
            <div><strong>Email:</strong> {email}</div>
            <div><strong>Line name:</strong> {line}</div>
            <div><strong>State:</strong> {chapter_state}</div>
            <div><strong>Intake completed:</strong> {intake}</div>
          </div>
          <p><a href="{frontend}/admin" style="background:#C8102E;color:#fff;padding:12px 24px;border-radius:999px;text-decoration:none;font-weight:600">Open Admin → Members</a></p>
          <p style="font-size:12px;color:#888;margin-top:24px;line-height:1.6">Review the pending application card to approve or reject. The applicant has already chosen their password — approving them grants immediate access.</p>
        </div>
        """
        try:
            await asyncio.to_thread(resend_sdk.Emails.send, {
                "from": resend_from,
                "to": recipients,
                "subject": f"[AOP] New application: {name}",
                "html": body,
                "tags": [{"name": "type", "value": "application_admin_notify"}],
            })
            logger.info(f"Admin application notification sent to {len(recipients)} admins")
            return True
        except Exception as e:
            logger.warning(f"Admin application notification failed: {e}")
            return False

    async def send_approval_email(email: str, name: str) -> tuple[bool, str]:
        if not resend_api_key:
            return False, "Resend API key not configured on the server (RESEND_API_KEY)."
        if not email:
            return False, "Applicant has no email address on file."
        frontend = _frontend_url()
        safe_name = _html.escape(name or "")
        safe_email = _html.escape(email)
        body = f"""
        <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:32px;color:#222">
          <h1 style="color:#C8102E;margin:0 0 12px;font-size:28px">Welcome to Alpha Omega Phi, {safe_name}!</h1>
          <p style="line-height:1.6">We are honored to welcome you to <strong>Alpha Omega Phi Military Fraternity &amp; Sorority, Inc.</strong> Your membership application has been <strong>approved</strong> and your member portal is now active.</p>
          <p style="line-height:1.6">You can sign in right away using the email and password you chose when you applied.</p>
          <div style="background:#f7f5f0;border-radius:14px;padding:20px;margin:20px 0">
            <div style="font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:#666;margin-bottom:6px">Your Sign-In</div>
            <div style="font-size:14px;margin:4px 0"><strong>Email:</strong> {safe_email}</div>
            <div style="font-size:14px;margin:4px 0"><strong>Password:</strong> The one you chose when applying.</div>
          </div>
          <p><a href="{frontend}/login" style="background:#C8102E;color:#fff;padding:12px 24px;border-radius:999px;text-decoration:none;font-weight:600">Sign in to the portal</a></p>
          <p style="line-height:1.6;margin-top:24px">Once you log in you can update your profile, RSVP to events, log volunteer hours, view chapter forms, and connect with other Trendsetters in the members-only chat.</p>
          <p style="font-size:12px;color:#888;margin-top:24px;line-height:1.6">Forgot your password? Reach out to your chapter Governor for help.</p>
        </div>
        """
        try:
            await asyncio.to_thread(resend_sdk.Emails.send, {
                "from": resend_from,
                "to": [email],
                "subject": "Welcome to Alpha Omega Phi",
                "html": body,
                "tags": [{"name": "type", "value": "application_approved"}],
            })
            logger.info(f"Welcome (approval) email sent to {email} from {resend_from}")
            return True, "sent"
        except Exception as e:
            msg = str(e)
            logger.warning(f"Welcome (approval) email FAILED for {email} (from={resend_from}): {msg}")
            return False, msg

    async def send_rejection_email(email: str, name: str, note: str) -> bool:
        if not resend_api_key or not email:
            return False
        safe_name = _html.escape(name or "")
        safe_note = _html.escape(note or "")
        body = f"""
        <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:32px;color:#222">
          <h2 style="margin:0 0 12px">Alpha Omega Phi — application update</h2>
          <p style="line-height:1.6">Hi {safe_name}, thank you for applying to Alpha Omega Phi Military Fraternity &amp; Sorority. Unfortunately your application was not approved at this time.</p>
          {f'<blockquote style="border-left:3px solid #C8102E;padding:6px 12px;margin:16px 0;background:#f7f5f0;border-radius:4px">{safe_note}</blockquote>' if safe_note else ''}
          <p style="font-size:12px;color:#888;margin-top:24px">If you believe this was in error, please reach out to your chapter Governor.</p>
        </div>
        """
        try:
            await asyncio.to_thread(resend_sdk.Emails.send, {
                "from": resend_from,
                "to": [email],
                "subject": "Alpha Omega Phi — application update",
                "html": body,
                "tags": [{"name": "type", "value": "application_rejected"}],
            })
            return True
        except Exception as e:
            logger.warning(f"Rejection email failed for {email}: {e}")
            return False

    @api.post("/auth/apply")
    async def submit_application(body: PublicApplicationIn):
        email = body.email.lower().strip()
        existing_user = await db.users.find_one({"email": email})
        if existing_user:
            raise HTTPException(status_code=400, detail="An account already exists for this email")
        existing_app = await db.applications.find_one({"email": email, "status": "pending"})
        if existing_app:
            raise HTTPException(status_code=400, detail="An application is already pending for this email — check back soon")
        doc = {
            "id": str(uuid.uuid4()),
            "first_name": body.first_name.strip(),
            "last_name": body.last_name.strip(),
            "email": email,
            "password_hash": hash_password(body.password),
            "line_name": body.line_name.strip(),
            "intake_line": body.intake_line.strip(),
            "intake_completed_at": body.intake_completed_at.strip(),
            "address": body.address.strip(),
            "city": body.city.strip(),
            "state": body.state.strip(),
            "zip_code": body.zip_code.strip(),
            "country": body.country.strip(),
            "status": "pending",
            "created_at": iso(now_utc()),
        }
        await db.applications.insert_one(doc)
        try:
            asyncio.create_task(send_application_admin_notification(doc))
        except Exception as ex:
            logger.warning(f"Failed to schedule admin notification: {ex}")
        return {"ok": True, "application_id": doc["id"]}

    @api.get("/admin/applications")
    async def list_applications(status_filter: Optional[str] = "pending", _: dict = Depends(admin_tab_dep("members"))):
        q: dict = {}
        if status_filter:
            q["status"] = status_filter
        cursor = db.applications.find(q, {"_id": 0}).sort("created_at", -1).limit(500)
        items = await cursor.to_list(500)
        return [application_out(a) for a in items]

    @api.post("/admin/applications/{app_id}/review")
    async def review_application(app_id: str, body: ApplicationReviewIn, admin: dict = Depends(admin_tab_dep("members"))):
        app_doc = await db.applications.find_one({"id": app_id})
        if not app_doc:
            raise HTTPException(status_code=404, detail="Application not found")
        if app_doc.get("status") != "pending":
            raise HTTPException(status_code=400, detail=f"Application is already {app_doc.get('status')}")
        if body.action == "approve":
            applicant_password_hash = app_doc.get("password_hash")
            if not applicant_password_hash:
                applicant_password_hash = hash_password(str(uuid.uuid4()) + str(uuid.uuid4()))
            composed_name = (app_doc.get("first_name", "") + " " + app_doc.get("last_name", "")).strip() or app_doc["email"].split("@")[0]
            uid = str(uuid.uuid4())
            created = now_utc()
            user_doc = {
                "id": uid,
                "email": app_doc["email"],
                "username": "",
                "password_hash": applicant_password_hash,
                "name": composed_name,
                "first_name": app_doc.get("first_name", ""),
                "middle_name": "",
                "last_name": app_doc.get("last_name", ""),
                "line_name": app_doc.get("line_name", ""),
                "intake_line": app_doc.get("intake_line", ""),
                "intake_completed_at": app_doc.get("intake_completed_at", ""),
                "phone": "",
                "address": app_doc.get("address", ""),
                "city": app_doc.get("city", ""),
                "state": app_doc.get("state", ""),
                "zip_code": app_doc.get("zip_code", ""),
                "country": app_doc.get("country", ""),
                "birthdate": "",
                "branch_of_service": "",
                "role": "member",
                "bio": "",
                "interests": [],
                "avatar_url": "",
                "membership_tier": "standard",
                "tier_id": None,
                "chapter_id": None,
                "status_override": None,
                "admin_role": None,
                "join_date": iso(created),
                "membership_expires_at": iso(created + timedelta(days=365)),
                "email_verified": True,
                "pending_set_password": False,
                "created_at": iso(created),
            }
            await db.users.insert_one(user_doc)
            await db.applications.update_one(
                {"id": app_id},
                {"$set": {
                    "status": "approved",
                    "reviewed_at": iso(now_utc()),
                    "reviewed_by": admin.get("name", "Admin"),
                    "review_note": body.note or "",
                    "user_id": uid,
                }},
            )
            email_ok, email_detail = await send_approval_email(app_doc["email"], composed_name)
            return {
                "ok": True,
                "user_id": uid,
                "welcome_email_sent": email_ok,
                "welcome_email_detail": email_detail if not email_ok else "Welcome email sent.",
            }
        # Reject
        await db.applications.update_one(
            {"id": app_id},
            {"$set": {
                "status": "rejected",
                "reviewed_at": iso(now_utc()),
                "reviewed_by": admin.get("name", "Admin"),
                "review_note": body.note or "",
            }},
        )
        name = (app_doc.get("first_name", "") + " " + app_doc.get("last_name", "")).strip()
        await send_rejection_email(app_doc["email"], name, body.note or "")
        return {"ok": True}

    # Expose senders as attrs in case other code wants them
    register.send_application_admin_notification = send_application_admin_notification
    register.send_approval_email = send_approval_email
    register.send_rejection_email = send_rejection_email
