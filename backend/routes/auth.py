"""Core auth routes: register, login, logout, me, refresh.

The "heavier" auth flows (public application submit/review, set-password,
forgot-password, reset-password) remain in server.py because they bundle
email-sending and template logic that's tightly coupled to other server-side
concerns. The 5 routes here are the bread-and-butter auth surface — they
benefit most from extraction since they're heavily exercised and stable.

Registered via `register(api, **deps)` from server.py at module-load time.
"""
import os
import re
import uuid
import logging
import secrets
from datetime import timedelta
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel

from models import RegisterIn, LoginIn


logger = logging.getLogger("clubhaven")


class RefreshIn(BaseModel):
    refresh_token: Optional[str] = None


def register(
    api,
    *,
    db,
    get_current_user,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    set_auth_cookies,
    clear_auth_cookies,
    public_user,
    jwt_secret,
    JWT_ALGORITHM,
    iso,
    now_utc,
):
    """Wire the 5 core /auth routes onto the given api router."""

    @api.post("/auth/register")
    async def auth_register(body: RegisterIn, response: Response):
        email = body.email.lower()
        existing = await db.users.find_one({"email": email})
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        uid = str(uuid.uuid4())
        created = now_utc()
        verify_token = secrets.token_urlsafe(32)
        doc = {
            "id": uid,
            "email": email,
            "password_hash": hash_password(body.password),
            "name": body.name,
            "role": "member",
            "bio": "",
            "city": body.city or "",
            "interests": body.interests or [],
            "avatar_url": "",
            "membership_tier": "standard",
            "membership_expires_at": iso(created + timedelta(days=365)),
            "email_verified": False,
            "created_at": iso(created),
        }
        await db.users.insert_one(doc)
        await db.email_verification_tokens.insert_one({
            "token": verify_token,
            "user_id": uid,
            "expires_at": iso(created + timedelta(days=7)),
        })
        frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
        verify_link = f"{frontend}/verify-email?token={verify_token}"
        logger.info(f"[email-verify] Link for {email}: {verify_link}")
        at = create_access_token(uid, email, "member", int(doc.get("token_version", 0) or 0))
        rt = create_refresh_token(uid, int(doc.get("token_version", 0) or 0))
        set_auth_cookies(response, at, rt)
        out = public_user(doc)
        out["verify_link"] = verify_link
        out["access_token"] = at
        out["refresh_token"] = rt
        return out

    @api.post("/auth/login")
    async def auth_login(body: LoginIn, request: Request, response: Response):
        # Accept either an email address OR a username. We normalize the identifier
        # to lowercase and look up by either field.
        identifier_raw = (body.email or "").strip()
        is_email_form = "@" in identifier_raw
        email = identifier_raw.lower() if is_email_form else ""
        username_lc = identifier_raw.lower() if not is_email_form else ""

        xff = request.headers.get("x-forwarded-for", "")
        ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
        identifier = f"{ip}:{identifier_raw.lower()}"

        # Look the user up FIRST and try the password. A correct password should
        # always succeed even if previous wrong attempts triggered a soft lock
        # (locking out legitimate users with the right credentials is bad UX).
        user = None
        if is_email_form:
            user = await db.users.find_one({"email": email})
        else:
            user = await db.users.find_one({"username": {"$regex": f"^{re.escape(username_lc)}$", "$options": "i"}})

        password_ok = bool(user) and verify_password(body.password, user["password_hash"])

        if not password_ok:
            # Wrong creds — enforce the soft lock and increment.
            attempt = await db.login_attempts.find_one({"identifier": identifier})
            if attempt and attempt.get("count", 0) >= 5:
                locked_until = attempt.get("locked_until")
                from datetime import datetime as _dt
                if locked_until and _dt.fromisoformat(locked_until) > now_utc():
                    raise HTTPException(status_code=429, detail="Too many incorrect attempts. Try again in 15 minutes.")
            await db.login_attempts.update_one(
                {"identifier": identifier},
                {"$inc": {"count": 1}, "$set": {"locked_until": iso(now_utc() + timedelta(minutes=15))}},
                upsert=True,
            )
            raise HTTPException(status_code=401, detail="Invalid email/username or password")

        # Success — clear any prior failed-attempt counter for this identifier.
        await db.login_attempts.delete_one({"identifier": identifier})
        # Per iter96: a successful login is treated as proof the member has
        # a working password, so clear `pending_set_password` if it's still
        # on the record. Admins want the "Pending Password Setup" pill to
        # disappear as soon as the member proves they can sign in.
        if user.get("pending_set_password"):
            await db.users.update_one(
                {"id": user["id"]},
                {"$unset": {"pending_set_password": ""}},
            )
        # Record an open session so admins can see sign-in activity.
        # The login_activity router (registered in server.py) attaches a
        # `_record_login_session` coroutine on the api object — guard the
        # call so unit-test harnesses that don't register that router still
        # work.
        try:
            recorder = getattr(api, "_record_login_session", None)
            if recorder:
                await recorder(user, request)
        except Exception:
            pass
        tv = int(user.get("token_version", 0) or 0)
        at = create_access_token(user["id"], user["email"], user.get("role", "member"), tv)
        rt = create_refresh_token(user["id"], tv)
        set_auth_cookies(response, at, rt)
        out = public_user(user)
        out["access_token"] = at
        out["refresh_token"] = rt
        return out

    @api.post("/auth/logout")
    async def auth_logout(response: Response, user: dict = Depends(get_current_user)):
        clear_auth_cookies(response)
        try:
            recorder = getattr(api, "_record_logout", None)
            if recorder:
                await recorder(user["id"])
        except Exception:
            pass
        return {"ok": True}

    @api.get("/auth/me")
    async def auth_me(user: dict = Depends(get_current_user)):
        return public_user(user)

    @api.post("/auth/refresh")
    async def auth_refresh(request: Request, response: Response, body: Optional[RefreshIn] = None):
        # Accept refresh token via (in priority order):
        # 1. JSON body { refresh_token } — mobile/localStorage path
        # 2. Authorization: Bearer  — non-cookie clients
        # 3. refresh_token cookie — desktop/laptop path
        token = None
        if body and body.refresh_token:
            token = body.refresh_token
        if not token:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
        if not token:
            token = request.cookies.get("refresh_token")
        if not token:
            raise HTTPException(status_code=401, detail="No refresh token")
        try:
            payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
            if payload.get("type") != "refresh":
                raise HTTPException(status_code=401, detail="Invalid token type")
            user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            tv = int(user.get("token_version", 0) or 0)
            tv_token = int(payload.get("tv", 0) or 0)
            if tv_token < tv:
                raise HTTPException(status_code=401, detail="Session expired — please sign in again.")
            at = create_access_token(user["id"], user["email"], user.get("role", "member"), tv)
            rt = create_refresh_token(user["id"], tv)
            set_auth_cookies(response, at, rt)
            return {"ok": True, "access_token": at, "refresh_token": rt}
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
