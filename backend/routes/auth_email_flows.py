"""Auth flows that depend on Resend email delivery — set-password, forgot
password, reset-password, change-password. Extracted from server.py to keep the
monolith small and to consolidate Resend email templates in one place.

The bulk-import set-password flow and the public /apply approval path still call
`send_set_password_email` from server.py (so we expose it via register.send_set_password_email).
"""
import asyncio
import html as _html
import os
import secrets
from datetime import timedelta
from typing import Callable

from fastapi import Depends, HTTPException

from models import (
    SetPasswordIn,
    ForgotPasswordIn,
    ResetPasswordIn,
    ChangePasswordIn,
)


def register(
    api,
    *,
    db,
    iso,
    now_utc,
    hash_password,
    verify_password,
    get_current_user,
    resend_sdk,
    resend_api_key: str,
    resend_from: str,
    logger,
):
    """Register the 4 email-driven auth endpoints + their email helpers.

    The helpers are also returned as attributes on `register` so the rest of
    server.py can keep calling them (bulk-import + apply-approval flow).
    """

    def _frontend_url() -> str:
        return os.environ.get("FRONTEND_URL", "http://localhost:3000")

    async def send_set_password_email(email: str, name: str, token: str) -> bool:
        if not resend_api_key or not email:
            return False
        set_link = f"{_frontend_url()}/set-password?token={token}"
        safe_name = _html.escape(name or "")
        body = f"""
        <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:32px;color:#222">
          <h1 style="color:#C8102E;margin:0 0 12px;font-size:28px">Welcome to Alpha Omega Phi, {safe_name}.</h1>
          <p style="line-height:1.6">Your membership application has been <strong>approved</strong>. To finish setting up your account, choose a password using the link below. This link is valid for 7 days and can only be used once.</p>
          <p><a href="{set_link}" style="background:#C8102E;color:#fff;padding:12px 24px;border-radius:999px;text-decoration:none;font-weight:600">Set my password</a></p>
          <p style="font-size:12px;color:#888;margin-top:24px;line-height:1.6">If the button doesn't work, paste this link into your browser:<br><span style="color:#444">{set_link}</span></p>
        </div>
        """
        try:
            await asyncio.to_thread(resend_sdk.Emails.send, {
                "from": resend_from,
                "to": [email],
                "subject": "Alpha Omega Phi — your application was approved, set your password",
                "html": body,
                "tags": [{"name": "type", "value": "set_password"}],
            })
            return True
        except Exception as e:
            logger.warning(f"Set-password email failed for {email}: {e}")
            return False

    async def send_password_reset_email(email: str, name: str, token: str) -> bool:
        if not resend_api_key or not email:
            return False
        link = f"{_frontend_url()}/reset-password?token={token}"
        safe_name = _html.escape(name or "")
        body = f"""
        <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:32px;color:#222">
          <h1 style="color:#C8102E;margin:0 0 12px;font-size:26px">Reset your password</h1>
          <p style="line-height:1.6">Hi {safe_name}, we received a request to reset your Alpha Omega Phi member portal password. This link is valid for <strong>1 hour</strong> and can only be used once.</p>
          <p><a href="{link}" style="background:#C8102E;color:#fff;padding:12px 24px;border-radius:999px;text-decoration:none;font-weight:600">Reset my password</a></p>
          <p style="font-size:12px;color:#888;margin-top:18px;line-height:1.6">If the button doesn't work, paste this URL into your browser:<br><span style="color:#444">{link}</span></p>
          <p style="font-size:12px;color:#888;margin-top:18px;line-height:1.6">If you didn't request this, you can safely ignore this email — your existing password still works.</p>
        </div>
        """
        try:
            await asyncio.to_thread(resend_sdk.Emails.send, {
                "from": resend_from,
                "to": [email],
                "subject": "Reset your Alpha Omega Phi password",
                "html": body,
                "tags": [{"name": "type", "value": "password_reset"}],
            })
            return True
        except Exception as e:
            logger.warning(f"Password reset email failed for {email}: {e}")
            return False

    @api.post("/auth/set-password")
    async def set_password_from_token(body: SetPasswordIn):
        """One-time-token password set after approval. Marks the user as no longer pending."""
        t = await db.password_set_tokens.find_one({"token": body.token, "used": False})
        if not t:
            raise HTTPException(status_code=400, detail="Invalid or already-used token")
        if t.get("expires_at") and t["expires_at"] < iso(now_utc()):
            raise HTTPException(status_code=400, detail="Token has expired")
        await db.users.update_one(
            {"id": t["user_id"]},
            {"$set": {"password_hash": hash_password(body.new_password), "pending_set_password": False}},
        )
        await db.password_set_tokens.update_one({"token": body.token}, {"$set": {"used": True, "used_at": iso(now_utc())}})
        user = await db.users.find_one({"id": t["user_id"]}, {"_id": 0, "password_hash": 0})
        return {"ok": True, "email": user.get("email") if user else None}

    @api.post("/auth/forgot-password")
    async def forgot_password(body: ForgotPasswordIn):
        """Request a password reset link. Always returns ok=true to prevent
        enumeration (the email lookup result isn't leaked back to the caller)."""
        email = body.email.lower().strip()
        user = await db.users.find_one({"email": email})
        if user:
            token = secrets.token_urlsafe(32)
            expires_dt = now_utc() + timedelta(hours=1)
            await db.password_reset_tokens.insert_one({
                "token": token,
                "user_id": user["id"],
                "expires_at": iso(expires_dt),
                "expires_at_dt": expires_dt,  # BSON Date for TTL index
                "used": False,
                "created_at": iso(now_utc()),
            })
            await send_password_reset_email(email, user.get("name", ""), token)
        return {"ok": True}

    @api.post("/auth/reset-password")
    async def reset_password(body: ResetPasswordIn):
        t = await db.password_reset_tokens.find_one({"token": body.token, "used": False})
        if not t:
            raise HTTPException(status_code=400, detail="Invalid or already-used reset link.")
        if t.get("expires_at") and t["expires_at"] < iso(now_utc()):
            raise HTTPException(status_code=400, detail="This reset link has expired. Request a new one.")
        # Resetting a password counts as the member completing onboarding, so
        # clear the pending_set_password flag and bump token_version to log
        # out any active sessions on other devices.
        await db.users.update_one(
            {"id": t["user_id"]},
            {"$set": {"password_hash": hash_password(body.new_password), "pending_set_password": False}, "$inc": {"token_version": 1}},
        )
        await db.password_reset_tokens.update_one({"token": body.token}, {"$set": {"used": True, "used_at": iso(now_utc())}})
        return {"ok": True}

    @api.post("/auth/change-password")
    async def change_password(body: ChangePasswordIn, user: dict = Depends(get_current_user)):
        full = await db.users.find_one({"id": user["id"]})
        if not full or not verify_password(body.current_password, full["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        # If the member is logged in and changes their own password, that also
        # counts as completing the password-setup step — clear the flag.
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"password_hash": hash_password(body.new_password), "pending_set_password": False}},
        )
        return {"ok": True}

    # Expose email senders on `register` so server.py can call them for bulk-import
    # and the apply-approval flow without re-implementing the templates.
    register.send_set_password_email = send_set_password_email
    register.send_password_reset_email = send_password_reset_email
