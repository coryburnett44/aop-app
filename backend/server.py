from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import re
import uuid
import logging
import secrets
import requests
import bcrypt
import jwt
import io
import base64
import qrcode
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal, Dict, Any

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response, status, UploadFile, File, Form, Header, Query
from fastapi.responses import Response as FastResponse, StreamingResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict

# ---------- Config ----------
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60 * 24  # 1 day (simpler UX for demo)
REFRESH_TOKEN_DAYS = 7
GRACE_PERIOD_DAYS = 15
APP_NAME = "clubhaven"
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
_storage_key: Optional[str] = None

mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("clubhaven")

app = FastAPI(title="ClubHaven API")
api = APIRouter(prefix="/api")

# ---------- Utilities ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def format_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()

def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def jwt_secret() -> str:
    return os.environ["JWT_SECRET"]

def create_access_token(user_id: str, email: str, role: str, token_version: int = 0) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "tv": token_version,
        "exp": now_utc() + timedelta(minutes=ACCESS_TOKEN_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str, token_version: int = 0) -> str:
    payload = {"sub": user_id, "tv": token_version, "exp": now_utc() + timedelta(days=REFRESH_TOKEN_DAYS), "type": "refresh"}
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)

def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    # secure=True for production HTTPS preview; samesite='none' would require secure=True
    response.set_cookie("access_token", access_token, httponly=True, secure=True, samesite="none",
                        max_age=ACCESS_TOKEN_MINUTES * 60, path="/")
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=True, samesite="none",
                        max_age=REFRESH_TOKEN_DAYS * 86400, path="/")

def clear_auth_cookies(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")

def public_user(u: dict) -> dict:
    is_lifetime = bool(u.get("is_lifetime_member"))
    exp = u.get("membership_expires_at")
    try:
        exp_dt = datetime.fromisoformat(exp) if exp else None
    except Exception:
        exp_dt = None
    now = now_utc()
    is_expired = (not is_lifetime) and bool(exp_dt and exp_dt < now)
    within_grace = bool(is_expired and exp_dt and (now - exp_dt).days <= GRACE_PERIOD_DAYS)
    # Computed status (manual override wins if set)
    manual = u.get("status_override")
    if manual in ("active", "inactive", "grace", "expired", "deceased"):
        status = manual
    elif u.get("deceased_at"):
        status = "deceased"
    elif is_lifetime:
        status = "active"  # life members never expire
    elif is_expired and not within_grace:
        status = "expired"
    elif within_grace:
        status = "grace"
    else:
        status = "active"
    return {
        "id": u["id"],
        "email": u["email"],
        "username": u.get("username", ""),
        "name": u.get("name", ""),
        "title": u.get("title", ""),
        "first_name": u.get("first_name", ""),
        "middle_name": u.get("middle_name", ""),
        "last_name": u.get("last_name", ""),
        "line_name": u.get("line_name", ""),
        "intake_line": u.get("intake_line", ""),
        "intake_completed_at": u.get("intake_completed_at", ""),
        "role": u.get("role", "member"),
        "admin_role": u.get("admin_role", "full") if u.get("role") == "admin" else None,
        "allowed_tabs": (u.get("allowed_tabs") or []) if u.get("role") == "admin" else [],
        "bio": u.get("bio", ""),
        "city": u.get("city", ""),
        "phone": u.get("phone", ""),
        "address": u.get("address", ""),
        "state": u.get("state", ""),
        "zip_code": u.get("zip_code", ""),
        "country": u.get("country", ""),
        "chat_email_notifications": u.get("chat_email_notifications", True),
        "chat_sms_notifications": u.get("chat_sms_notifications", True),
        "email_opt_out": bool(u.get("email_opt_out", False)),
        "email_prefs": {
            "blasts": (u.get("email_prefs") or {}).get("blasts", True),
            "dues_reminders": (u.get("email_prefs") or {}).get("dues_reminders", True),
        },
        "birthdate": u.get("birthdate", ""),
        "branch_of_service": u.get("branch_of_service", ""),
        "join_date": u.get("join_date") or u.get("created_at"),
        "deceased_at": u.get("deceased_at"),
        "status": status,
        "status_override": u.get("status_override"),
        "interests": u.get("interests", []),
        "marital_status": u.get("marital_status", ""),
        "languages": u.get("languages", []),
        "civilian_degrees": u.get("civilian_degrees", []),
        "assignment_history": u.get("assignment_history", []),
        "custom_fields": u.get("custom_fields") or {},
        "avatar_url": u.get("avatar_url", ""),
        "membership_tier": u.get("membership_tier", "standard"),
        "tier_id": u.get("tier_id"),
        "is_lifetime_member": is_lifetime,
        "chapter_id": u.get("chapter_id"),
        "membership_expires_at": None if is_lifetime else u.get("membership_expires_at"),
        "is_expired": is_expired,
        "within_grace": within_grace,
        "email_verified": u.get("email_verified", False),
        "trust_zeffy": bool(u.get("trust_zeffy")),
        "pending_set_password": bool(u.get("pending_set_password")),
        "created_at": u.get("created_at"),
        # Social media handles (members manage on profile)
        "facebook_url": u.get("facebook_url", ""),
        "instagram_url": u.get("instagram_url", ""),
        "linkedin_url": u.get("linkedin_url", ""),
        "tiktok_url": u.get("tiktok_url", ""),
        "twitter_url": u.get("twitter_url", ""),
        "pinterest_url": u.get("pinterest_url", ""),
        "youtube_url": u.get("youtube_url", ""),
        "website_url": u.get("website_url", ""),
        # If the member changed their intake_completed_at, this carries the pending value
        # until an admin approves it. Frontend shows the saved value (above) plus a pill
        # noting that {pending_intake_completed_at} is awaiting review.
        "pending_intake_completed_at": u.get("pending_intake_completed_at", ""),
        # Outstanding balance surface (anniversary fees, back dues — separate
        # from the annual-dues lifecycle). Total is sum of unpaid line amounts.
        "outstanding_zeffy_url": u.get("outstanding_zeffy_url", ""),
        "outstanding_balance_total": round(
            sum(float(ln.get("amount", 0)) for ln in (u.get("balance_lines") or []) if not ln.get("paid_at")),
            2,
        ),
    }

# ---------- Object Storage ----------
def init_storage() -> Optional[str]:
    global _storage_key
    if _storage_key:
        return _storage_key
    try:
        resp = requests.post(
            f"{STORAGE_URL}/init",
            json={"emergent_key": os.environ.get("EMERGENT_LLM_KEY")},
            timeout=30,
        )
        resp.raise_for_status()
        _storage_key = resp.json().get("storage_key")
        return _storage_key
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
        return None

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if not key:
        raise HTTPException(status_code=503, detail="Storage not available")
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str) -> tuple:
    key = init_storage()
    if not key:
        raise HTTPException(status_code=503, detail="Storage not available")
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

IMAGE_EXT = {"jpg", "jpeg", "png", "gif", "webp"}
DOC_EXT = {"pdf", "doc", "docx", "txt", "csv", "xlsx", "pptx"}

MIME_BY_EXT = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain", "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        # Token version check: if the user reset their password (or admin force-logout),
        # bump `token_version` and every existing JWT becomes invalid immediately.
        tv_token = int(payload.get("tv", 0) or 0)
        tv_user = int(user.get("token_version", 0) or 0)
        if tv_token < tv_user:
            raise HTTPException(status_code=401, detail="Session expired — please sign in again.")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user

# Admin sub-role permissions — UI tabs an admin can access.
# "full" admin has access to everything.
ADMIN_ROLE_TABS: dict[str, set[str]] = {
    "full": {"dashboard", "members", "chapters", "tiers", "events", "hours", "awards", "gear", "causes", "reports", "email", "news", "pages", "documents"},
    "membership_manager": {"dashboard", "members", "chapters", "tiers", "events", "awards", "reports", "email"},
    "operations_manager": {"dashboard", "members", "chapters", "events", "hours", "causes", "reports", "news", "documents"},
    "governor_manager": {"dashboard", "hours", "causes", "reports"},
}

# Canonical list of every admin-console tab key — used for admin_can validation and
# for the UI checkbox grid that lets full admins grant custom per-admin access.
ALL_ADMIN_TABS: set[str] = set(ADMIN_ROLE_TABS["full"])

def admin_role_of(u: dict) -> str:
    return (u.get("admin_role") or "full") if u.get("role") == "admin" else ""

def effective_admin_tabs(user: dict) -> set[str]:
    """Returns the set of admin-tab keys this user is allowed to access.

    Precedence:
      1. Custom per-user `allowed_tabs` list (set by full Admins) — takes priority.
      2. Otherwise fall back to ADMIN_ROLE_TABS[admin_role] defaults.
    """
    if user.get("role") != "admin":
        return set()
    custom = user.get("allowed_tabs")
    if isinstance(custom, list) and len(custom) > 0:
        return {t for t in custom if t in ALL_ADMIN_TABS}
    role = admin_role_of(user)
    return set(ADMIN_ROLE_TABS.get(role, set()))

def admin_can(user: dict, tab: str) -> bool:
    return tab in effective_admin_tabs(user)

async def require_admin_tab(tab: str, user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if not admin_can(user, tab):
        raise HTTPException(status_code=403, detail=f"Your admin role does not have access to {tab}")
    return user

def admin_tab_dep(tab: str):
    """FastAPI dependency factory: returns a Depends-able callable that requires
    the calling user to be an admin with access to the given tab."""
    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        if not admin_can(user, tab):
            raise HTTPException(status_code=403, detail=f"Your admin role does not have access to {tab}")
        return user
    return _dep

async def chapter_scope_user_ids(admin: dict) -> Optional[list]:
    """For Governor Managers, return the list of user_ids in their chapter.
    Returns None for everyone else (no scoping applied)."""
    if admin_role_of(admin) != "governor_manager":
        return None
    cid = admin.get("chapter_id")
    if not cid:
        return []  # Governor without chapter sees nothing
    cursor = db.users.find({"chapter_id": cid}, {"id": 1, "_id": 0})
    return [u["id"] async for u in cursor]

def is_chapter_scoped(admin: dict) -> bool:
    return admin_role_of(admin) == "governor_manager"

@api.get("/admin/permissions")
async def admin_permissions(user: dict = Depends(require_admin)):
    """Return the tabs the current admin can access — used by frontend to gate UI."""
    role = admin_role_of(user)
    return {
        "admin_role": role,
        "tabs": sorted(effective_admin_tabs(user)),
        "chapter_scoped": role == "governor_manager",
        "scoped_chapter_id": user.get("chapter_id") if role == "governor_manager" else None,
        "all_tabs": sorted(ALL_ADMIN_TABS),
        "role_default_tabs": {k: sorted(v) for k, v in ADMIN_ROLE_TABS.items()},
        "has_custom_tabs": isinstance(user.get("allowed_tabs"), list) and len(user.get("allowed_tabs") or []) > 0,
    }

# ---------- Models (extracted to models.py) ----------
from models import (  # noqa: E402
    RegisterIn, PublicApplicationIn, ApplicationReviewIn, SetPasswordIn, LoginIn,
    ProfileUpdateIn, StatusOverrideIn, ChapterIn, ChapterUpdateIn, HoursLogIn,
    AwardGrantIn, ChangePasswordIn, AdminCreateMemberIn, AdminUpdateMemberIn,
    TransactionIn, EventIn, EventUpdateIn, TicketType, GuestIn, EventRsvpIn,
    EventPaymentConfirmIn,
    NewsIn, NewsUpdateIn, PAGE_BLOCK_TYPES, PageBlockIn, PageIn, PageUpdateIn,
    AIEventReq, AIEmailReq, ForgotPasswordIn, ResetPasswordIn, VerifyEmailIn,
    RoleUpdateIn, TierIn, TierUpdateIn, AwardIn, AwardUpdateIn, HoursReviewIn,
    AssignChapterIn, AssignTierIn, PhotoMetaIn, DocumentMetaIn,
)


# ---------- Public registration applications (admin-approval flow) ----------
# /auth/apply, /admin/applications, /admin/applications/{id}/review and the 3
# Resend email helpers are extracted to routes/applications.py.


async def _send_set_password_email(email: str, name: str, token: str) -> bool:
    """Thin pass-through to routes/auth_email_flows.py — the real template lives
    there. We keep this name so the bulk-import + apply-approval code paths in
    server.py don't need to be touched. The function pointer is set after the
    `routes_auth_email_flows.register(...)` call at the bottom of this file."""
    fn = getattr(_send_set_password_email, "_impl", None)
    if fn is None:
        # Module wasn't registered yet (should not happen in production startup).
        logger.warning("[set-password-email] called before routes_auth_email_flows registered")
        return False
    return await fn(email, name, token)


# ---------- Profile / Members ----------
# /members, /members/{id}, /members-new, /members-birthdays, /members/{id}/status
# are registered via routes/members.py (see register call at bottom of file).

@api.put("/members/me")
async def update_me(body: ProfileUpdateIn, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    # If username supplied, ensure uniqueness
    if "username" in updates and updates["username"]:
        existing = await db.users.find_one({"username": updates["username"], "id": {"$ne": user["id"]}})
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")
    # Intake completion date requires admin approval — never write straight to
    # intake_completed_at, instead stash on pending_intake_completed_at. Skip
    # entirely if the value matches what's already saved (no change requested).
    if "intake_completed_at" in updates:
        requested = (updates.pop("intake_completed_at") or "").strip()
        current_saved = (user.get("intake_completed_at") or "").strip()
        if requested != current_saved:
            updates["pending_intake_completed_at"] = requested
    # If first/last names supplied without 'name', recompute display name
    if "first_name" in updates or "last_name" in updates or "middle_name" in updates:
        parts = [
            updates.get("first_name", user.get("first_name", "")),
            updates.get("middle_name", user.get("middle_name", "")),
            updates.get("last_name", user.get("last_name", "")),
        ]
        composed = " ".join(p for p in parts if p).strip()
        if composed and "name" not in updates:
            updates["name"] = composed
    if updates:
        await db.users.update_one({"id": user["id"]}, {"$set": updates})
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return public_user(u)

@api.post("/members/me/renew")
async def renew_membership(user: dict = Depends(get_current_user)):
    """Self-renewal is disabled — members must pay their annual dues via PayPal
    (the dues PayPal capture path extends membership_expires_at by 365 days).
    Returning 410 Gone so old clients see a clear error."""
    raise HTTPException(
        status_code=410,
        detail="Self-renewal without payment is no longer supported. Please pay annual dues via PayPal in your profile.",
    )


# ---------- Admin: Intake completion date review ----------
class IntakeDateReviewIn(BaseModel):
    action: Literal["approve", "reject"]
    note: str = ""


@api.get("/admin/pending-intake-changes")
async def list_pending_intake_changes(_: dict = Depends(admin_tab_dep("members"))):
    """All users with a pending intake_completed_at change awaiting admin review."""
    cursor = db.users.find(
        {"pending_intake_completed_at": {"$nin": [None, ""]}},
        {"_id": 0, "password_hash": 0},
    ).limit(500)
    rows = await cursor.to_list(500)
    return [
        {
            "id": u["id"],
            "name": u.get("name", ""),
            "email": u.get("email", ""),
            "line_name": u.get("line_name", ""),
            "current_intake_completed_at": u.get("intake_completed_at", ""),
            "pending_intake_completed_at": u.get("pending_intake_completed_at", ""),
        }
        for u in rows
    ]


@api.post("/admin/members/{user_id}/intake-completion-review")
async def review_intake_change(user_id: str, body: IntakeDateReviewIn, admin: dict = Depends(admin_tab_dep("members"))):
    u = await db.users.find_one({"id": user_id})
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    pending = u.get("pending_intake_completed_at")
    if not pending:
        raise HTTPException(status_code=400, detail="This member has no pending intake date change.")
    if body.action == "approve":
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"intake_completed_at": pending, "pending_intake_completed_at": ""},
             "$push": {"intake_review_log": {
                 "action": "approved", "value": pending, "note": body.note,
                 "reviewed_by_id": admin["id"], "reviewed_by_name": admin.get("name", ""),
                 "reviewed_at": iso(now_utc()),
             }}},
        )
    else:
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"pending_intake_completed_at": ""},
             "$push": {"intake_review_log": {
                 "action": "rejected", "value": pending, "note": body.note,
                 "reviewed_by_id": admin["id"], "reviewed_by_name": admin.get("name", ""),
                 "reviewed_at": iso(now_utc()),
             }}},
        )
    fresh = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return public_user(fresh)


# ---------- Events ----------
def event_out(e: dict) -> dict:
    return {
        "id": e["id"],
        "title": e["title"],
        "description": e.get("description", ""),
        "location": e.get("location", ""),
        "start_at": e["start_at"],
        "end_at": e.get("end_at"),
        "capacity": e.get("capacity", 0),
        "cover_image": e.get("cover_image", ""),
        "category": e.get("category", "general"),
        "price": e.get("price", 0.0),
        "rsvp_count": e.get("rsvp_count", 0),
        "guest_count": e.get("guest_count", 0),
        "parent_event_id": e.get("parent_event_id"),
        "allows_ticket_types": e.get("allows_ticket_types", False),
        "enabled_ticket_types": e.get("enabled_ticket_types") or [],
        "cancelled": bool(e.get("cancelled")),
        "cancellation_note": e.get("cancellation_note", ""),
        "cancelled_at": e.get("cancelled_at"),
        "cancelled_via_parent": bool(e.get("cancelled_via_parent")),
        "is_paid": bool(e.get("is_paid")),
        "payment_url": e.get("payment_url", ""),
        "payment_amount": float(e.get("payment_amount") or 0.0),
        "external_url": e.get("external_url", ""),
        "external_button_label": e.get("external_button_label", ""),
        "created_at": e.get("created_at"),
    }

# ---------- RSVP / Paid-event approval / Check-in — extracted to routes/rsvps.py ----------
# (registered at end of file). The helpers (_create_rsvp_and_email_ticket,
#  send_rsvp_ticket_email, make_ticket_token, decode_ticket_token,
#  make_qr_png_b64) are exposed on routes_rsvps.register if needed.

# ---------- News — extracted to routes/news.py ----------
# (registered at end of file)


# ---------- CMS Pages — extracted to routes/pages.py ----------
# (registered at end of file)


# ---------- Site Settings — extracted to routes/site_settings.py ----------
# SETTINGS_DOC_ID kept here for backward-compat use elsewhere in this file.
SETTINGS_DOC_ID = "site_settings_v1"


# Back-compat shim — some other code paths may call _ensure_site_settings(); will be wired
# after the route module is registered below.
async def _ensure_site_settings():
    # Patched at module load (see register() at bottom of file).
    raise RuntimeError("_ensure_site_settings not yet wired")


# ---------- AI (Claude Sonnet 4.5) — extracted to routes/ai.py ----------
# (run_claude helper is in routes/ai.py if needed elsewhere)



# ---------- Chapters ----------
# ---------- Chapters — extracted to routes/chapters.py ----------
# (registered at end of file). `chapter_out` is re-exported from server for any
# remaining in-file callers that still build chapter payloads inline.
from routes.chapters import chapter_out  # noqa: E402

# ---------- Membership Tiers — extracted to routes/tiers.py ----------
from routes.tiers import tier_out  # noqa: E402

# ---------- Member admin operations ----------
@api.post("/admin/members")
async def admin_create_member(body: AdminCreateMemberIn, _: dict = Depends(admin_tab_dep("members"))):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    if body.username and await db.users.find_one({"username": body.username}):
        raise HTTPException(status_code=400, detail="Username already taken")
    uid = str(uuid.uuid4())
    created = now_utc()
    composed_name = body.name or " ".join(p for p in [body.first_name, body.middle_name, body.last_name] if p).strip() or email.split("@")[0]
    join_dt = body.join_date or created
    if isinstance(join_dt, datetime):
        join_iso = iso(join_dt)
        exp_iso = iso(join_dt + timedelta(days=365))
    else:
        join_iso = iso(created)
        exp_iso = iso(created + timedelta(days=365))
    doc = {
        "id": uid,
        "email": email,
        "username": body.username,
        "password_hash": hash_password(body.password),
        "name": composed_name,
        "title": body.title or "",
        "first_name": body.first_name,
        "middle_name": body.middle_name,
        "last_name": body.last_name,
        "line_name": body.line_name,
        "intake_line": body.intake_line,
        "intake_completed_at": body.intake_completed_at,
        "phone": body.phone,
        "address": body.address,
        "state": body.state,
        "zip_code": body.zip_code,
        "country": body.country,
        "birthdate": body.birthdate,
        "branch_of_service": body.branch_of_service,
        "role": body.role,
        "bio": "",
        "city": body.city,
        "interests": [],
        "avatar_url": "",
        "membership_tier": "standard",
        "tier_id": body.tier_id,
        "chapter_id": body.chapter_id,
        "status_override": body.member_status,
        "admin_role": (body.admin_role or "full") if body.role == "admin" else None,
        "allowed_tabs": [t for t in (body.allowed_tabs or []) if t in ALL_ADMIN_TABS] if body.role == "admin" else [],
        "join_date": join_iso,
        "membership_expires_at": exp_iso,
        "email_verified": True,
        "created_at": iso(created),
    }
    if body.tier_id:
        tier = await db.tiers.find_one({"id": body.tier_id}, {"_id": 0})
        if tier:
            doc["membership_tier"] = tier.get("name", "standard")
            doc["is_lifetime_member"] = bool(tier.get("is_lifetime"))
            if tier.get("is_lifetime"):
                doc["membership_expires_at"] = None
    await db.users.insert_one(doc)
    # Send welcome email with temp password (best-effort; doesn't block creation if email fails)
    try:
        await send_welcome_email(email, composed_name, body.password)
    except Exception as e:
        logger.warning(f"welcome email failed for {email}: {e}")
    return public_user(doc)


# ---------- Bulk member import (CSV) ----------
# Used to migrate the ClubExpress roster onto AOP. Admin uploads a CSV; we
# create one user per row and extend membership_expires_at = renewal_date + 365d
# (or today + 365d if renewal_date is missing / unparseable).
#
# Accepted CSV columns (case-insensitive, leading/trailing whitespace stripped,
# multiple aliases supported so admin can paste ClubExpress export directly):
#   - Email                                            (required, must be unique)
#   - First Name / FirstName / First
#   - Last Name  / LastName  / Last
#   - Middle Name / MiddleName
#   - Title         (Mr. / Mrs. / Ms. / Miss / Dr. / Prof. / Rev. / Hon. / Mx.)
#   - Phone / Telephone
#   - Address / Street
#   - City
#   - State
#   - Zip / Zip Code / Postal Code
#   - Country
#   - Birthdate / Birth Date / Date of Birth          (any parseable date)
#   - Branch of Service / Military Branch
#   - Renewal Date / Renewal / Expires / Membership Expires
#         → membership_expires_at = renewal_date + 365 days
#   - Join Date / Joined / Member Since
#   - Line Name / Line
#   - Intake Line
#   - Intake Completed At / Intake Date
#   - Username
#
# We never overwrite an existing user (matched by lowercase email). Each row in
# the response includes either {created: true} or {skipped: 'duplicate'|'invalid'}
# plus the original row number so the admin can fix and re-upload.
import csv as _csv
import io as _io
from dateutil import parser as _date_parser

_BULK_COLUMN_ALIASES = {
    "email": ["email", "e-mail", "email address"],
    "title": ["title", "salutation", "honorific"],
    "first_name": ["first name", "firstname", "first", "given name"],
    "middle_name": ["middle name", "middlename", "middle"],
    "last_name": ["last name", "lastname", "last", "surname", "family name"],
    "phone": ["phone", "telephone", "mobile", "cell", "phone number"],
    "address": ["address", "street", "address line 1", "street address"],
    "city": ["city", "town"],
    "state": ["state", "province", "region"],
    "zip_code": ["zip", "zip code", "zipcode", "postal code", "postcode"],
    "country": ["country"],
    "birthdate": ["birthdate", "birth date", "date of birth", "dob"],
    "branch_of_service": ["branch of service", "military branch", "branch", "service branch"],
    "renewal_date": ["renewal date", "renewal", "expires", "expiration", "membership expires", "renew on"],
    "join_date": ["join date", "joined", "member since", "join", "membership start"],
    "line_name": ["line name", "line"],
    "intake_line": ["intake line"],
    "intake_completed_at": ["intake completed at", "intake date", "intake completed", "crossed"],
    "username": ["username", "user name", "screen name"],
    "chapter": ["chapter", "chapter name"],  # resolved by name → id below
}

_TITLE_VALID = {"Mr.", "Mrs.", "Ms.", "Miss", "Dr.", "Prof.", "Rev.", "Hon.", "Mx."}


def _normalize_header(h: str) -> str:
    return (h or "").strip().lower().replace("_", " ")


def _map_row(row: dict) -> dict:
    """Map a CSV row's header keys to our canonical field names."""
    out: dict = {}
    norm = {_normalize_header(k): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
    for canonical, aliases in _BULK_COLUMN_ALIASES.items():
        for a in aliases:
            if a in norm and norm[a]:
                out[canonical] = norm[a]
                break
    return out


def _parse_date(s: str):
    if not s:
        return None
    try:
        dt = _date_parser.parse(str(s))
        if dt.tzinfo is None:
            from datetime import timezone as _tz
            dt = dt.replace(tzinfo=_tz.utc)
        return dt
    except Exception:
        return None


def _normalize_title(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip().rstrip(".")
    candidates = {t.rstrip("."): t for t in _TITLE_VALID}
    return candidates.get(s, candidates.get(s.title(), ""))


@api.post("/admin/members/bulk-import")
async def admin_bulk_import_members(
    file: UploadFile = File(...),
    default_chapter_id: Optional[str] = Form(None),
    dry_run: bool = Form(False),
    send_set_password_emails: bool = Form(True),
    admin: dict = Depends(admin_tab_dep("members")),
):
    """Bulk-import members from a CSV (e.g. exported from ClubExpress).

    - One user per row.
    - membership_expires_at = renewal_date + 365 days (or today + 365 if no renewal_date).
    - Duplicates (matched by lowercase email) are skipped, not overwritten.
    - dry_run=true validates the CSV without inserting anything (useful preview).
    - send_set_password_emails=true (default): each created user gets a one-time
      set-password link (7-day expiry) so they can sign in directly without
      anyone having to share a temp password. Set to false to skip.
    - Returns per-row results so the admin can fix errors and re-upload.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="CSV too large (max 5 MB)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    reader = _csv.DictReader(_io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row")

    # Pre-load chapters once for chapter-name → id resolution
    chapters_list = await db.chapters.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
    chapters_by_name = {(c.get("name") or "").lower().strip(): c["id"] for c in chapters_list}

    results = {"created": [], "skipped": [], "errors": [], "total": 0}
    now = now_utc()

    for idx, raw_row in enumerate(reader, start=2):  # row 1 = header
        results["total"] += 1
        row = _map_row(raw_row)
        email = (row.get("email") or "").lower().strip()
        if not email or "@" not in email:
            results["errors"].append({"row": idx, "email": email, "reason": "missing or invalid email"})
            continue
        # Duplicate guard
        if await db.users.find_one({"email": email}):
            results["skipped"].append({"row": idx, "email": email, "reason": "email already exists"})
            continue

        first = row.get("first_name", "")
        last = row.get("last_name", "")
        middle = row.get("middle_name", "")
        title = _normalize_title(row.get("title", ""))
        composed_name = " ".join(p for p in [first, middle, last] if p).strip() or email.split("@")[0]

        # Resolve chapter — explicit on row, else fallback default
        chapter_id = default_chapter_id
        ch_raw = (row.get("chapter") or "").lower().strip()
        if ch_raw and ch_raw in chapters_by_name:
            chapter_id = chapters_by_name[ch_raw]

        # Date parsing
        renewal_dt = _parse_date(row.get("renewal_date", ""))
        join_dt = _parse_date(row.get("join_date", "")) or now
        if renewal_dt:
            expires_dt = renewal_dt + timedelta(days=365)
        else:
            expires_dt = now + timedelta(days=365)
        birth_dt = _parse_date(row.get("birthdate", ""))

        if dry_run:
            results["created"].append({
                "row": idx,
                "email": email,
                "name": composed_name,
                "membership_expires_at": iso(expires_dt),
                "chapter_id": chapter_id,
            })
            continue

        # Strong temp password — admin can use forgot-password flow to give members access
        temp_password = secrets.token_urlsafe(18)
        uid = str(uuid.uuid4())
        doc = {
            "id": uid,
            "email": email,
            "username": row.get("username", ""),
            "password_hash": hash_password(temp_password),
            "name": composed_name,
            "title": title,
            "first_name": first,
            "middle_name": middle,
            "last_name": last,
            "line_name": row.get("line_name", ""),
            "intake_line": row.get("intake_line", ""),
            "intake_completed_at": row.get("intake_completed_at", ""),
            "phone": row.get("phone", ""),
            "address": row.get("address", ""),
            "city": row.get("city", ""),
            "state": row.get("state", ""),
            "zip_code": row.get("zip_code", ""),
            "country": row.get("country", ""),
            "birthdate": iso(birth_dt) if birth_dt else "",
            "branch_of_service": row.get("branch_of_service", ""),
            "role": "member",
            "bio": "",
            "interests": [],
            "avatar_url": "",
            "membership_tier": "standard",
            "chapter_id": chapter_id,
            "join_date": iso(join_dt),
            "membership_expires_at": iso(expires_dt),
            "email_verified": True,
            "pending_set_password": True,  # flag for admin follow-up
            "imported_from": "clubexpress_csv",
            "imported_at": iso(now),
            "created_at": iso(now),
        }
        try:
            await db.users.insert_one(doc)
            row_result = {
                "row": idx,
                "email": email,
                "name": composed_name,
                "membership_expires_at": iso(expires_dt),
            }
            # Optionally send a one-time set-password email so the new member
            # can sign in without anyone sharing the temp password.
            if send_set_password_emails and RESEND_API_KEY:
                try:
                    token = secrets.token_urlsafe(32)
                    expires_at = now + timedelta(days=7)
                    await db.password_set_tokens.insert_one({
                        "token": token,
                        "user_id": uid,
                        "expires_at": iso(expires_at),
                        "expires_at_dt": expires_at,
                        "used": False,
                        "created_at": iso(now),
                    })
                    sent = await _send_set_password_email(email, composed_name, token)
                    row_result["set_password_email_sent"] = bool(sent)
                except Exception as ex_email:
                    row_result["set_password_email_sent"] = False
                    logger.warning(f"[bulk-import] set-password email failed for {email}: {ex_email}")
            else:
                row_result["set_password_email_sent"] = False
            results["created"].append(row_result)
        except Exception as ex:
            results["errors"].append({"row": idx, "email": email, "reason": f"insert failed: {ex}"})

    results["created_count"] = len(results["created"])
    results["skipped_count"] = len(results["skipped"])
    results["error_count"] = len(results["errors"])
    results["dry_run"] = bool(dry_run)
    results["emails_sent_count"] = sum(1 for r in results["created"] if r.get("set_password_email_sent"))
    logger.info(f"[bulk-import] admin={admin.get('email')} created={results['created_count']} skipped={results['skipped_count']} errors={results['error_count']} emails={results['emails_sent_count']} dry_run={dry_run}")
    return results


@api.get("/admin/members/bulk-import/template")
async def admin_bulk_import_template(_: dict = Depends(admin_tab_dep("members"))):
    """Returns a downloadable CSV template with the expected headers + one
    example row. Admin clicks "Download template" in the bulk-import dialog."""
    headers = [
        "Email", "Title", "First Name", "Middle Name", "Last Name", "Username",
        "Phone", "Address", "City", "State", "Zip Code", "Country",
        "Birthdate", "Branch of Service",
        "Renewal Date", "Join Date",
        "Line Name", "Intake Line", "Intake Completed At",
        "Chapter",
    ]
    example = [
        "jane.doe@example.com", "Ms.", "Jane", "", "Doe", "janed",
        "555-123-4567", "123 Main St", "Houston", "TX", "77001", "USA",
        "1985-04-12", "Army",
        "2026-01-15", "2020-01-15",
        "Theta-3", "Spring 2020", "2020-06-01",
        "Texas",
    ]
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(headers)
    w.writerow(example)
    return FastResponse(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=aop-bulk-import-template.csv"},
    )


@api.post("/admin/members/{user_id}/resend-set-password")
async def admin_resend_set_password(user_id: str, admin: dict = Depends(admin_tab_dep("members"))):
    """Generate a fresh 7-day set-password token for the given user and email them
    a new link. Used when the original bulk-import welcome email was missed or
    the token expired before the member completed onboarding."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Member not found")
    if not user.get("email"):
        raise HTTPException(status_code=400, detail="Member has no email on file")
    if not RESEND_API_KEY:
        raise HTTPException(status_code=503, detail="Email service not configured on the server (RESEND_API_KEY missing).")
    now = now_utc()
    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(days=7)
    # Invalidate any older, still-active tokens for this user so the new one is
    # the only valid link.
    await db.password_set_tokens.update_many(
        {"user_id": user_id, "used": False},
        {"$set": {"used": True, "used_at": iso(now), "invalidated_by": "resend"}},
    )
    await db.password_set_tokens.insert_one({
        "token": token,
        "user_id": user_id,
        "expires_at": iso(expires_at),
        "expires_at_dt": expires_at,
        "used": False,
        "created_at": iso(now),
    })
    # Keep pending_set_password=True until the member actually completes the flow.
    await db.users.update_one({"id": user_id}, {"$set": {"pending_set_password": True}})
    name = user.get("name") or user.get("first_name") or user.get("email")
    sent = await _send_set_password_email(user["email"], name, token)
    logger.info(f"[resend-set-password] admin={admin.get('email')} user={user.get('email')} sent={sent}")
    # Log the attempt so the Email → History tab can surface failures
    await db.password_setup_attempts.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "user_name": user.get("name", ""),
        "email": user["email"],
        "ok": bool(sent),
        "reason": "" if sent else "Resend API rejected or no API key configured",
        "mode": "single",
        "admin_id": admin.get("id"),
        "admin_name": admin.get("name", ""),
        "attempted_at": iso(now),
        "attempted_at_dt": now,
    })
    return {"ok": True, "sent": bool(sent), "email": user["email"]}


@api.post("/admin/members/bulk-resend-set-password")
async def admin_bulk_resend_set_password(admin: dict = Depends(admin_tab_dep("members"))):
    """Send a fresh set-password email to EVERY user currently flagged
    pending_set_password=true. Used during onboarding waves where dozens of
    bulk-imported members haven't completed onboarding. For each user:
      1. Invalidate any older unused tokens (no double-active links).
      2. Mint a new 7-day token.
      3. Send the welcome / set-password email.
    Returns a summary { ok, total, sent, failed, skipped_no_email, members:[…] }.
    """
    if not RESEND_API_KEY:
        raise HTTPException(status_code=503, detail="Email service not configured on the server (RESEND_API_KEY missing).")
    cursor = db.users.find({"pending_set_password": True}, {"_id": 0})
    pending = await cursor.to_list(500)
    now = now_utc()
    summary = {"ok": True, "total": len(pending), "sent": 0, "failed": 0, "skipped_no_email": 0, "members": []}
    attempt_logs: List[dict] = []
    for user in pending:
        email = (user.get("email") or "").strip()
        uid = user.get("id")
        if not email:
            summary["skipped_no_email"] += 1
            summary["members"].append({"id": uid, "name": user.get("name", ""), "email": "", "sent": False, "skipped": True})
            attempt_logs.append({
                "id": str(uuid.uuid4()),
                "user_id": uid,
                "user_name": user.get("name", ""),
                "email": "",
                "ok": False,
                "reason": "Member has no email address on file",
                "mode": "bulk",
                "admin_id": admin.get("id"),
                "admin_name": admin.get("name", ""),
                "attempted_at": iso(now),
                "attempted_at_dt": now,
            })
            continue
        token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(days=7)
        try:
            await db.password_set_tokens.update_many(
                {"user_id": uid, "used": False},
                {"$set": {"used": True, "used_at": iso(now), "invalidated_by": "bulk-resend"}},
            )
            await db.password_set_tokens.insert_one({
                "token": token,
                "user_id": uid,
                "expires_at": iso(expires_at),
                "expires_at_dt": expires_at,
                "used": False,
                "created_at": iso(now),
            })
            name = user.get("name") or user.get("first_name") or email
            sent = await _send_set_password_email(email, name, token)
            if sent:
                summary["sent"] += 1
            else:
                summary["failed"] += 1
            summary["members"].append({"id": uid, "name": user.get("name", ""), "email": email, "sent": bool(sent)})
            attempt_logs.append({
                "id": str(uuid.uuid4()),
                "user_id": uid,
                "user_name": user.get("name", ""),
                "email": email,
                "ok": bool(sent),
                "reason": "" if sent else "Resend API rejected or no API key configured",
                "mode": "bulk",
                "admin_id": admin.get("id"),
                "admin_name": admin.get("name", ""),
                "attempted_at": iso(now),
                "attempted_at_dt": now,
            })
        except Exception as ex:
            summary["failed"] += 1
            summary["members"].append({"id": uid, "name": user.get("name", ""), "email": email, "sent": False, "error": str(ex)})
            attempt_logs.append({
                "id": str(uuid.uuid4()),
                "user_id": uid,
                "user_name": user.get("name", ""),
                "email": email,
                "ok": False,
                "reason": str(ex)[:300],
                "mode": "bulk",
                "admin_id": admin.get("id"),
                "admin_name": admin.get("name", ""),
                "attempted_at": iso(now),
                "attempted_at_dt": now,
            })
            logger.warning(f"[bulk-resend-setpw] failed for {email}: {ex}")
    if attempt_logs:
        await db.password_setup_attempts.insert_many(attempt_logs)
    logger.info(
        f"[bulk-resend-setpw] admin={admin.get('email')} total={summary['total']} "
        f"sent={summary['sent']} failed={summary['failed']} skipped_no_email={summary['skipped_no_email']}"
    )
    return summary


@api.put("/members/{user_id}")
async def admin_update_member(user_id: str, body: AdminUpdateMemberIn, admin: dict = Depends(admin_tab_dep("members"))):
    existing = await db.users.find_one({"id": user_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Member not found")
    # Only full admins may change role / admin_role / tier / membership_expires_at / allowed_tabs
    expires_changing = body.membership_expires_at is not None and (
        iso(body.membership_expires_at) != (existing.get("membership_expires_at") or "")
    )
    tabs_changing = body.allowed_tabs is not None and (
        list(body.allowed_tabs) != list(existing.get("allowed_tabs") or [])
    )
    if (
        (body.role is not None and body.role != existing.get("role"))
        or (body.admin_role is not None and body.admin_role != existing.get("admin_role"))
        or (body.tier_id is not None and body.tier_id != existing.get("tier_id"))
        or expires_changing
        or tabs_changing
    ):
        if admin_role_of(admin) != "full":
            raise HTTPException(status_code=403, detail="Only full Admins may change roles, tiers, custom tab permissions, or the membership expiration date.")
    # Sanitize allowed_tabs: only keep keys that are real admin tabs. An empty list
    # is treated as "remove custom override" (fall back to admin_role defaults).
    if body.allowed_tabs is not None:
        body.allowed_tabs = sorted({t for t in body.allowed_tabs if t in ALL_ADMIN_TABS})
    updates = {k: v for k, v in body.model_dump().items() if v is not None and k not in ("new_password", "member_status")}
    # If role is being downgraded to "member", clear all admin-specific fields so the
    # user no longer carries leftover admin_role / allowed_tabs from a prior promotion.
    if body.role == "member" and existing.get("role") == "admin":
        updates["admin_role"] = None
        updates["allowed_tabs"] = []
    # Status override (member_status maps to status_override; "active" with no expiry issues means clear override)
    if body.member_status is not None:
        updates["status_override"] = body.member_status
        if body.member_status == "deceased" and not (body.deceased_at or existing.get("deceased_at")):
            updates["deceased_at"] = iso(now_utc())
        if body.member_status != "deceased" and existing.get("deceased_at") and not body.deceased_at:
            updates["deceased_at"] = None
    # username uniqueness
    if "username" in updates and updates["username"]:
        clash = await db.users.find_one({"username": updates["username"], "id": {"$ne": user_id}})
        if clash:
            raise HTTPException(status_code=400, detail="Username already taken")
    # email uniqueness
    if "email" in updates and updates["email"]:
        updates["email"] = updates["email"].lower()
        clash = await db.users.find_one({"email": updates["email"], "id": {"$ne": user_id}})
        if clash:
            raise HTTPException(status_code=400, detail="Email already registered")
    # If first/last names changed, recompute display name unless explicit
    if any(k in updates for k in ("first_name", "middle_name", "last_name")) and "name" not in updates:
        parts = [
            updates.get("first_name", existing.get("first_name", "")),
            updates.get("middle_name", existing.get("middle_name", "")),
            updates.get("last_name", existing.get("last_name", "")),
        ]
        composed = " ".join(p for p in parts if p).strip()
        if composed:
            updates["name"] = composed
    # Tier change -> sync display tier + lifetime flag + clear expiration for life members
    if "tier_id" in updates and updates["tier_id"]:
        tier = await db.tiers.find_one({"id": updates["tier_id"]}, {"_id": 0})
        if tier:
            updates["membership_tier"] = tier.get("name", "standard")
            updates["is_lifetime_member"] = bool(tier.get("is_lifetime"))
            if tier.get("is_lifetime"):
                updates["membership_expires_at"] = None
    # Date field
    if "membership_expires_at" in updates and isinstance(updates["membership_expires_at"], datetime):
        updates["membership_expires_at"] = iso(updates["membership_expires_at"])
    # Join date: when admin changes it, recompute membership_expires_at = join_date + 365d
    # unless admin also explicitly set membership_expires_at in the same request.
    if "join_date" in updates and isinstance(updates["join_date"], datetime):
        jd = updates["join_date"]
        updates["join_date"] = iso(jd)
        if "membership_expires_at" not in updates:
            updates["membership_expires_at"] = iso(jd + timedelta(days=365))
    if body.new_password:
        updates["password_hash"] = hash_password(body.new_password)
        # Iter 40: when an admin manually overrides a member's password from the
        # Edit Member dialog, treat onboarding as complete — clear the pending
        # set-password flag so the amber badge / filter no longer surfaces this
        # user. The original /set-password endpoint already does this for the
        # self-serve flow.
        updates["pending_set_password"] = False
    if updates:
        await db.users.update_one({"id": user_id}, {"$set": updates})
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return public_user(u)

@api.delete("/members/{user_id}")
async def admin_delete_member(user_id: str, admin: dict = Depends(admin_tab_dep("members"))):
    """Hard-delete personal data; soft-delete chat messages so other group
    members still see context (sender shown as 'Deleted Member'); KEEP PayPal
    transactions for accounting but anonymize the linked user_name."""
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "name": 1, "email": 1})
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    deleted_name = "Deleted Member"
    # Hard delete personal records
    await db.users.delete_one({"id": user_id})
    await db.rsvps.delete_many({"user_id": user_id})
    await db.checkins.delete_many({"user_id": user_id})
    await db.volunteer_hours.delete_many({"user_id": user_id})
    await db.award_grants.delete_many({"user_id": user_id})
    await db.applications.delete_many({"email": (u.get("email") or "").lower()})
    await db.password_set_tokens.delete_many({"user_id": user_id})
    await db.password_reset_tokens.delete_many({"user_id": user_id})
    await db.photos.delete_many({"uploaded_by": user_id})
    await db.documents.delete_many({"uploaded_by": user_id})
    await db.photo_albums.delete_many({"created_by": user_id, "is_default": {"$ne": True}})
    await db.omega_tributes.delete_many({"user_id": user_id})
    await db.chat_notifications.delete_many({"recipient_id": user_id})
    # Soft-delete chat messages (preserve thread for others)
    await db.chat_messages.update_many(
        {"sender_id": user_id},
        {"$set": {"sender_name": deleted_name, "sender_avatar": "", "body": "(message removed — member deleted)", "attachments": [], "deleted_at": iso(now_utc())}},
    )
    # Remove from conversation members lists
    await db.conversations.update_many({"member_ids": user_id}, {"$pull": {"member_ids": user_id}})
    # Anonymize PayPal transactions (keep for accounting)
    await db.transactions.update_many({"user_id": user_id}, {"$set": {"user_name": deleted_name, "anonymized": True}})
    return {"ok": True, "deleted_user_id": user_id}

@api.put("/members/{user_id}/role")
async def update_member_role(user_id: str, body: RoleUpdateIn, admin: dict = Depends(admin_tab_dep("members"))):
    # Only full admins may change member roles (Operations & Membership Managers cannot)
    if admin_role_of(admin) != "full":
        raise HTTPException(status_code=403, detail="Only full Admins may change member roles")
    await db.users.update_one({"id": user_id}, {"$set": {"role": body.role}})
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    return public_user(u)

@api.put("/members/{user_id}/chapter")
async def assign_chapter(user_id: str, body: AssignChapterIn, _: dict = Depends(admin_tab_dep("members"))):
    update = {"chapter_id": body.chapter_id} if body.chapter_id else {"chapter_id": None}
    await db.users.update_one({"id": user_id}, {"$set": update})
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    return public_user(u)

@api.put("/members/{user_id}/tier")
async def assign_tier(user_id: str, body: AssignTierIn, admin: dict = Depends(admin_tab_dep("members"))):
    # Only full admins may change a member's tier
    if admin_role_of(admin) != "full":
        raise HTTPException(status_code=403, detail="Only full Admins may change member tiers")
    updates: dict = {"tier_id": body.tier_id}
    is_lifetime = False
    if body.tier_id:
        tier = await db.tiers.find_one({"id": body.tier_id}, {"_id": 0})
        if tier:
            updates["membership_tier"] = tier.get("name", "standard")
            is_lifetime = bool(tier.get("is_lifetime"))
    updates["is_lifetime_member"] = is_lifetime
    if is_lifetime:
        # Life members never expire — clear any existing expiration
        updates["membership_expires_at"] = None
    else:
        # If transitioning from lifetime → non-lifetime, re-establish an expiration
        u_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
        if u_doc and (u_doc.get("is_lifetime_member") or not u_doc.get("membership_expires_at")):
            base = now_utc()
            join_iso = u_doc.get("join_date")
            try:
                if join_iso:
                    base = max(base, datetime.fromisoformat(join_iso))
            except Exception:
                pass
            updates["membership_expires_at"] = iso(base + timedelta(days=365))
        if body.extend_days:
            u = await db.users.find_one({"id": user_id})
            if u:
                cur = updates.get("membership_expires_at") or u.get("membership_expires_at")
                try:
                    base = datetime.fromisoformat(cur) if cur else now_utc()
                except Exception:
                    base = now_utc()
                if base < now_utc():
                    base = now_utc()
                updates["membership_expires_at"] = iso(base + timedelta(days=body.extend_days))
    await db.users.update_one({"id": user_id}, {"$set": updates})
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    return public_user(u)

# ---------- Awards ----------
# Moved to routes/awards.py — registered via routes_awards.register(...) at
# the bottom of this file. The `award_out` serializer also lives there now.

# ---------- Volunteer Hours ----------
def hours_out(h: dict) -> dict:
    return {
        "id": h["id"],
        "user_id": h["user_id"],
        "user_name": h.get("user_name", ""),
        "hours": h["hours"],
        "description": h.get("description", "") or h.get("activity", ""),
        "activity": h.get("activity", "") or h.get("description", ""),
        "event_type": h.get("event_type", "other"),
        "agency_name": h.get("agency_name", ""),
        "host_name": h.get("host_name", ""),
        "host_email": h.get("host_email", ""),
        "host_phone": h.get("host_phone", ""),
        "date": h.get("date"),
        "event_id": h.get("event_id"),
        "status": h.get("status", "pending"),
        "reviewed_by": h.get("reviewed_by"),
        "reviewed_by_name": h.get("reviewed_by_name"),
        "reviewed_at": h.get("reviewed_at"),
        "note": h.get("note", ""),
        "hours_adjusted_by": h.get("hours_adjusted_by"),
        "hours_adjusted_by_name": h.get("hours_adjusted_by_name"),
        "hours_adjusted_at": h.get("hours_adjusted_at"),
        "logged_by_admin": h.get("logged_by_admin", False),
        "approved_by": h.get("approved_by"),
        "approved_by_name": h.get("approved_by_name"),
        "approved_at": h.get("approved_at"),
        "imported_from_csv": h.get("imported_from_csv"),
        "csv_row": h.get("csv_row"),
        "created_at": h.get("created_at"),
    }

# /hours, /hours/{id}/review, /me/hours, /me/hours/summary are registered via
# routes/hours.py (see register call at bottom of file).

# ---------- Photos ----------
def photo_out(p: dict) -> dict:
    return {
        "id": p["id"],
        "title": p.get("title", ""),
        "album": p.get("album", "general"),
        "storage_path": p["storage_path"],
        "url": f"/api/files/{p['storage_path']}",
        "uploaded_by": p.get("uploaded_by"),
        "uploaded_by_name": p.get("uploaded_by_name", ""),
        "created_at": p.get("created_at"),
    }

# NOTE: All /photos and /photos/albums routes are registered by
# routes.photos.register(...) toward the bottom of this file. The seed +
# auto-categorize helpers below remain here because they're called at startup
# before route registration runs.

DEFAULT_PHOTO_ALBUMS = [
    "Alpha Line", "Beta Line", "Gamma Line",
    "Book Bag Giveaway", "Dorn VA Community Service",
    "5-Year Anniversary", "7-Year Anniversary", "10-Year Anniversary",
    "Commitment Ceremony 2018", "Commitment Ceremony 2019", "Commitment Ceremony 2020",
    "Commitment Ceremony 2021", "Commitment Ceremony 2022", "Commitment Ceremony 2023",
    "Commitment Ceremony 2024", "Commitment Ceremony 2025", "Commitment Ceremony 2026",
    "Commitment Ceremony 2027", "Commitment Ceremony 2028", "Commitment Ceremony 2029",
    "Commitment Ceremony 2030",
    "Leadership Conference 2018", "Leadership Conference 2019", "Leadership Conference 2020",
    "Leadership Conference 2021", "Leadership Conference 2022", "Leadership Conference 2023",
    "Leadership Conference 2024", "Leadership Conference 2025", "Leadership Conference 2026",
    "Leadership Conference 2027",
    "Golf Tournament 2017", "Golf Tournament 2018", "Golf Tournament 2019",
    "Golf Tournament 2020", "Golf Tournament 2021", "Golf Tournament 2022",
    "Golf Tournament 2023", "Golf Tournament 2024", "Golf Tournament 2025",
    "Golf Tournament 2026", "Golf Tournament 2027",
    "Trendsetters Spirits Conference 2026", "Trendsetters Spirits Conference 2027",
    "Trendsetters Spirits Conference 2028", "Trendsetters Spirits Conference 2029",
    "Trendsetters Spirits Conference 2030",
]


PHOTO_ALBUM_CATEGORIES = ["anniversary", "ceremony", "conference", "tournament", "line", "community", "other"]


def auto_categorize_album(name: str) -> str:
    """Pick a category by keyword-matching the album title."""
    n = (name or "").lower()
    if any(k in n for k in ["anniversary", "10-year", "10 year", "5-year", "7-year"]):
        return "anniversary"
    if "ceremony" in n or "commitment" in n:
        return "ceremony"
    if "conference" in n or "summit" in n:
        return "conference"
    if "tournament" in n or "golf" in n:
        return "tournament"
    if " line" in f" {n}" or n.endswith(" line"):
        return "line"
    if any(k in n for k in ["community", "service", "giveaway", "outreach", "va ", " va", "volunteer"]):
        return "community"
    return "other"


async def seed_default_photo_albums():
    """Insert each canonical album as a row in the photo_albums collection.
    Only inserts new ones; never overwrites custom albums. Idempotent.
    Skips any canonical name listed in `deleted_default_albums` so an admin's
    deletion isn't undone on next boot.
    Also backfills category on every album each boot (cheap, allows recategorizing)."""
    tombstoned = {
        t["name"]
        async for t in db.deleted_default_albums.find({}, {"_id": 0, "name": 1})
    }
    for name in DEFAULT_PHOTO_ALBUMS:
        if name in tombstoned:
            continue
        await db.photo_albums.update_one(
            {"name": name},
            {"$setOnInsert": {
                "id": str(uuid.uuid4()),
                "name": name,
                "is_default": True,
                "created_by": None,
                "created_by_name": "System",
                "category": auto_categorize_album(name),
                "cover_url": "",
                "created_at": iso(now_utc()),
            }},
            upsert=True,
        )
    # Backfill category for any album missing it
    async for a in db.photo_albums.find({"category": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "name": 1}):
        await db.photo_albums.update_one({"id": a["id"]}, {"$set": {"category": auto_categorize_album(a["name"])}})

async def reconcile_pending_set_password():
    """One-shot boot-time reconciliation for the iter78 fix.

    Re-flags members whose `pending_set_password` was incorrectly cleared by the
    old auth-login path. A user is considered "never completed setup" when:
      - They have at least one row in `password_set_tokens` (i.e. a welcome /
        resend email was issued for them), AND
      - None of those rows show evidence of being consumed via /auth/set-password
        (`used=true` AND no `invalidated_by` field).

    Only users currently flagged `pending_set_password=false` are touched.
    Idempotent: subsequent boots are no-ops because re-flagged users won't match
    the "currently false" filter.
    """
    # Build a set of user_ids who *did* consume a token (proves completion).
    consumed_uids = set()
    async for t in db.password_set_tokens.find(
        {"used": True, "invalidated_by": {"$exists": False}},
        {"_id": 0, "user_id": 1},
    ):
        if t.get("user_id"):
            consumed_uids.add(t["user_id"])
    # Users who were issued any token at all.
    issued_uids = set()
    async for t in db.password_set_tokens.find({}, {"_id": 0, "user_id": 1}):
        if t.get("user_id"):
            issued_uids.add(t["user_id"])
    # Re-flag candidates: issued but never consumed AND currently not flagged.
    candidates = issued_uids - consumed_uids
    if not candidates:
        logger.info("[reconcile-pending-setpw] no candidates to re-flag")
        return
    res = await db.users.update_many(
        {"id": {"$in": list(candidates)}, "pending_set_password": {"$ne": True}},
        {"$set": {"pending_set_password": True}},
    )
    if res.modified_count:
        logger.info(f"[reconcile-pending-setpw] re-flagged {res.modified_count} member(s) who never completed /set-password")
    else:
        logger.info("[reconcile-pending-setpw] all candidates already correctly flagged")





# ---------- File proxy (serves both photos and documents) ----------
@api.get("/files/{storage_path:path}")
async def download_file(storage_path: str, user: dict = Depends(get_current_user)):
    # Check DB for existence + soft-delete flag (photos / documents / chat files)
    rec = await db.photos.find_one({"storage_path": storage_path, "is_deleted": {"$ne": True}})
    if not rec:
        rec = await db.documents.find_one({"storage_path": storage_path, "is_deleted": {"$ne": True}})
    if not rec:
        rec = await db.chat_files.find_one({"storage_path": storage_path, "is_deleted": {"$ne": True}})
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data, content_type = get_object(storage_path)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found in storage")
    return FastResponse(content=data, media_type=rec.get("content_type", content_type))


@api.get("/me/activity")
async def my_activity(user: dict = Depends(get_current_user)):
    """Unified timeline: transactions, RSVPs, volunteer hours, awards."""
    activity = []
    # Transactions
    async for t in db.transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1):
        activity.append({
            "kind": "transaction",
            "subtype": t.get("type", "fee"),
            "at": t.get("created_at"),
            "title": t.get("description") or f"{t.get('type', 'fee').title()}",
            "meta": {"amount": t.get("amount", 0), "currency": t.get("currency", "USD"), "status": t.get("status")},
        })
    # RSVPs (events attended)
    async for r in db.rsvps.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1):
        ev = await db.events.find_one({"id": r["event_id"]}, {"_id": 0})
        activity.append({
            "kind": "event",
            "subtype": "rsvp",
            "at": r.get("created_at"),
            "title": f"RSVP — {ev['title'] if ev else 'Event'}",
            "meta": {"event_id": r["event_id"], "event_date": ev.get("start_at") if ev else None},
        })
    # Volunteer hours
    async for h in db.volunteer_hours.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1):
        activity.append({
            "kind": "hours",
            "subtype": h.get("status", "pending"),
            "at": h.get("created_at"),
            "title": f"{h['hours']} hours · {h.get('description', '')}",
            "meta": {"hours": h["hours"], "status": h.get("status"), "date": h.get("date")},
        })
    # Awards
    async for g in db.award_grants.find({"user_id": user["id"]}, {"_id": 0}).sort("granted_at", -1):
        activity.append({
            "kind": "award",
            "subtype": "granted",
            "at": g.get("granted_at"),
            "title": f"Earned: {g['award_name']}",
            "meta": {"award_name": g.get("award_name"), "reason": g.get("reason"), "icon": g.get("award_icon"), "color": g.get("award_color")},
        })
    activity.sort(key=lambda x: x.get("at") or "", reverse=True)
    return activity

# ---------- Admin Dashboard Stats ----------
ANNUAL_DUES_USD = 105.0

@api.get("/admin/stats")
async def admin_stats(admin: dict = Depends(require_admin)):
    now = now_utc()
    now_iso = iso(now)
    thirty_days_iso = iso(now + timedelta(days=30))
    month_start_iso = iso(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))

    # Chapter-scoping (Governor Manager sees only their chapter)
    scoped = is_chapter_scoped(admin)
    scope_cid = admin.get("chapter_id") if scoped else None
    user_q_extra: dict = {"chapter_id": scope_cid} if scoped else {}
    if scoped:
        scoped_user_ids = await chapter_scope_user_ids(admin) or []
        hours_q_extra: dict = {"user_id": {"$in": scoped_user_ids}}
    else:
        scoped_user_ids = None
        hours_q_extra = {}

    def uq(extra: dict) -> dict:
        return {**extra, **user_q_extra}

    # Members
    total_members = await db.users.count_documents(uq({}))
    new_this_month = await db.users.count_documents(uq({"created_at": {"$gte": month_start_iso}}))
    expiring_soon = await db.users.count_documents(uq({
        "membership_expires_at": {"$gte": now_iso, "$lte": thirty_days_iso}
    }))
    expired = await db.users.count_documents(uq({"membership_expires_at": {"$lt": now_iso}}))
    active_members = total_members - expired

    # "By membership tier" pie chart: count members grouped by their tier_id,
    # then resolve to the tier's display name. Members with no tier_id (or
    # whose tier_id points to a deleted tier) are excluded — "Standard" /
    # "Lifetime" are NOT tiers, they are status concepts and would confuse the
    # chart if shown alongside real tiers.
    tier_cursor = db.users.aggregate([
        {"$match": user_q_extra} if scoped else {"$match": {}},
        {"$match": {"tier_id": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$tier_id", "count": {"$sum": 1}}},
    ])
    raw_counts = {d["_id"]: d["count"] async for d in tier_cursor}
    tier_names = {
        t["id"]: t.get("name", "")
        async for t in db.tiers.find(
            {"id": {"$in": list(raw_counts.keys())}} if raw_counts else {"id": "__none__"},
            {"_id": 0, "id": 1, "name": 1},
        )
    }
    by_tier = [
        {"tier": tier_names[tid], "count": cnt}
        for tid, cnt in raw_counts.items()
        if tid in tier_names  # drop dangling references to deleted tiers
    ]
    by_tier.sort(key=lambda r: (-r["count"], r["tier"]))

    # Member growth — last 6 calendar months
    growth = []
    current_first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for i in range(5, -1, -1):
        y = current_first.year
        m = current_first.month - i
        while m <= 0:
            m += 12
            y -= 1
        m_start = current_first.replace(year=y, month=m)
        next_m = (m_start + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        c = await db.users.count_documents(uq({
            "created_at": {"$gte": iso(m_start), "$lt": iso(next_m)}
        }))
        growth.append({"month": m_start.strftime("%b"), "members": c})

    # Events (not chapter-scoped — events are org-wide)
    total_events = await db.events.count_documents({})
    upcoming_events = await db.events.count_documents({"start_at": {"$gte": now_iso}})
    past_events = total_events - upcoming_events
    total_rsvps = await db.rsvps.count_documents({})

    top_cursor = db.events.find({}, {"_id": 0}).sort("rsvp_count", -1).limit(5)
    top_events = [event_out(e) async for e in top_cursor]

    upcoming_cursor = db.events.find({"start_at": {"$gte": now_iso}}, {"_id": 0}).sort("start_at", 1).limit(5)
    next_events = [event_out(e) async for e in upcoming_cursor]

    # News / pages
    total_news = await db.news.count_documents({})
    total_pages = await db.pages.count_documents({})

    # Dues (no Stripe yet — estimate)
    active_revenue = round(active_members * ANNUAL_DUES_USD, 2)
    renewals_this_month = await db.users.count_documents(uq({
        "membership_expires_at": {"$gte": iso(now + timedelta(days=360)), "$lte": iso(now + timedelta(days=370))}
    }))

    # Expiring memberships list
    exp_cursor = db.users.find(
        uq({"membership_expires_at": {"$gte": now_iso, "$lte": thirty_days_iso}}),
        {"_id": 0, "password_hash": 0}
    ).sort("membership_expires_at", 1).limit(10)
    expiring_list = [{
        "id": u["id"], "name": u.get("name"), "email": u.get("email"),
        "expires_at": u.get("membership_expires_at"),
        "tier": u.get("membership_tier"),
    } async for u in exp_cursor]

    # Fraternity-specific counters
    total_chapters = await db.chapters.count_documents({})
    total_tiers = await db.tiers.count_documents({})
    total_awards = await db.awards.count_documents({})
    if scoped:
        total_grants = await db.award_grants.count_documents({"user_id": {"$in": scoped_user_ids}})
    else:
        total_grants = await db.award_grants.count_documents({})
    pending_hours = await db.volunteer_hours.count_documents({**hours_q_extra, "status": "pending"})
    approved_hours_agg = db.volunteer_hours.aggregate([
        {"$match": {**hours_q_extra, "status": "approved"}},
        {"$group": {"_id": None, "total": {"$sum": "$hours"}}},
    ])
    approved_hours_total = 0
    async for d in approved_hours_agg:
        approved_hours_total = round(d.get("total", 0), 1)
    total_photos = await db.photos.count_documents({"is_deleted": {"$ne": True}})
    total_documents = await db.documents.count_documents({"is_deleted": {"$ne": True}})

    # Chapter roster
    chapter_rows = []
    async for c in db.chapters.find({}, {"_id": 0}).sort("name", 1):
        count = await db.users.count_documents({"chapter_id": c["id"]})
        chapter_rows.append({"id": c["id"], "name": c["name"], "school": c.get("school", ""), "member_count": count})

    # Pending admin inbox
    seven_days_ago_iso = iso(now - timedelta(days=7))
    grace_cutoff_iso = iso(now - timedelta(days=GRACE_PERIOD_DAYS))
    hours_queue_cursor = db.volunteer_hours.find(
        {**hours_q_extra, "status": "pending"}, {"_id": 0}
    ).sort("created_at", 1).limit(10)
    hours_to_review = [hours_out(h) async for h in hours_queue_cursor]
    grace_cursor = db.users.find(
        uq({"membership_expires_at": {"$gte": grace_cutoff_iso, "$lt": now_iso}}),
        {"_id": 0, "password_hash": 0},
    ).sort("membership_expires_at", 1).limit(10)
    in_grace = [{
        "id": u["id"], "name": u.get("name"), "email": u.get("email"),
        "expires_at": u.get("membership_expires_at"),
        "tier": u.get("membership_tier"),
    } async for u in grace_cursor]
    new_cursor = db.users.find(
        uq({"created_at": {"$gte": seven_days_ago_iso}}),
        {"_id": 0, "password_hash": 0},
    ).sort("created_at", -1).limit(10)
    new_members = [{
        "id": u["id"], "name": u.get("name"), "email": u.get("email"),
        "created_at": u.get("created_at"),
        "tier": u.get("membership_tier"),
    } async for u in new_cursor]

    # Pending Zeffy event-ticket payments awaiting admin review.
    pending_tx_cursor = db.transactions.find(
        {"purpose": "event_ticket", "status": "pending"},
        {"_id": 0},
    ).sort("created_at", 1).limit(20)
    pending_event_tickets = []
    async for t in pending_tx_cursor:
        pending_event_tickets.append({
            "id": t.get("id"),
            "user_id": t.get("user_id"),
            "user_name": t.get("user_name", ""),
            "event_id": t.get("event_id"),
            "event_title": t.get("event_title", ""),
            "amount": t.get("amount", 0),
            "zeffy_confirmation": t.get("zeffy_confirmation", ""),
            "created_at": t.get("created_at"),
        })

    inbox = {
        "hours_to_review": hours_to_review,
        "in_grace": in_grace,
        "new_members": new_members,
        "pending_event_tickets": pending_event_tickets,
        "total": len(hours_to_review) + len(in_grace) + len(new_members) + len(pending_event_tickets),
    }

    return {
        "members": {
            "total": total_members,
            "active": active_members,
            "new_this_month": new_this_month,
            "expiring_soon": expiring_soon,
            "expired": expired,
            "by_tier": by_tier,
            "growth": growth,
            "expiring_list": expiring_list,
        },
        "events": {
            "total": total_events,
            "upcoming": upcoming_events,
            "past": past_events,
            "total_rsvps": total_rsvps,
            "top_by_rsvp": top_events,
            "next_up": next_events,
        },
        "content": {"news": total_news, "pages": total_pages, "photos": total_photos, "documents": total_documents},
        "fraternity": {
            "chapters": total_chapters,
            "chapter_roster": chapter_rows,
            "tiers": total_tiers,
            "awards": total_awards,
            "awards_granted": total_grants,
            "hours_pending": pending_hours,
            "hours_approved_total": approved_hours_total,
        },
        "dues": {
            "annual_fee": ANNUAL_DUES_USD,
            "active_revenue_estimate": active_revenue,
            "renewals_this_month": renewals_this_month,
            "potential_expiring_revenue": round(expiring_soon * ANNUAL_DUES_USD, 2),
        },
        "inbox": inbox,
    }

# ---------- Health ----------
@api.get("/")
async def root():
    return {"service": "ClubHaven API", "status": "ok"}

# ---------- Startup ----------
@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.users.create_index("username", sparse=True)
    await db.transactions.create_index("user_id")
    await db.events.create_index("id", unique=True)
    await db.events.create_index("start_at")
    await db.news.create_index("id", unique=True)
    await db.pages.create_index("slug", unique=True)
    await db.rsvps.create_index([("event_id", 1), ("user_id", 1)], unique=True)
    await db.login_attempts.create_index("identifier")
    await db.chapters.create_index("id", unique=True)
    await db.tiers.create_index("id", unique=True)
    await db.awards.create_index("id", unique=True)
    # Multiple grants of the same award per member are allowed since Iter 36 — drop
    # the legacy unique index on (award_id, user_id) if it exists, then create the
    # non-unique index for lookup performance.
    try:
        await db.award_grants.drop_index("award_id_1_user_id_1")
    except Exception:
        pass
    await db.award_grants.create_index([("award_id", 1), ("user_id", 1)])
    await db.volunteer_hours.create_index("user_id")
    await db.volunteer_hours.create_index("status")
    await db.photos.create_index("id", unique=True)
    await db.documents.create_index("id", unique=True)
    await db.gear.create_index("id", unique=True)
    await db.causes.create_index("id", unique=True)
    await db.checkins.create_index("id", unique=True)
    await db.checkins.create_index([("event_id", 1), ("user_id", 1)])
    await db.conversations.create_index("id", unique=True)
    await db.conversations.create_index("member_ids")
    await db.conversations.create_index("last_message_at")
    await db.messages.create_index("id", unique=True)
    await db.messages.create_index([("conversation_id", 1), ("created_at", -1)])
    await db.chat_files.create_index("id", unique=True)
    await db.chat_files.create_index("storage_path")
    await db.email_signatures.create_index("id", unique=True)
    await db.email_signatures.create_index([("owner_id", 1), ("kind", 1)])
    await db.chat_notifications.create_index("id", unique=True)
    await db.chat_notifications.create_index([("status", 1), ("due_at", 1)])
    await db.applications.create_index("id", unique=True)
    await db.applications.create_index([("status", 1), ("created_at", -1)])
    await db.app_settings.create_index("key", unique=True)
    await db.form_links.create_index("id", unique=True)
    await db.form_links.create_index([("order", 1), ("created_at", 1)])
    await db.password_set_tokens.create_index("token", unique=True)
    await db.password_reset_tokens.create_index("token", unique=True)
    # MongoDB will auto-delete reset tokens 1 minute after they expire.
    # Note: TTL index uses BSON Date, but `expires_at` is stored as ISO string.
    # We store an extra `expires_at_dt` Date field on insert, indexed with expireAfterSeconds=60.
    try:
        await db.password_reset_tokens.create_index("expires_at_dt", expireAfterSeconds=60)
    except Exception as e:
        logger.warning(f"password_reset_tokens TTL index error: {e}")
    await db.omega_tributes.create_index("id", unique=True)
    await db.omega_tributes.create_index("user_id", unique=True)
    # Automated emails
    await db.automated_emails.create_index("id", unique=True)
    await db.automated_emails.create_index([("is_active", 1), ("next_run_at", 1)])
    # Dues-reminder dedupe: one row per (user, dues period end, stage).
    # Pay → membership_expires_at moves → new keys → next cycle's reminders fire.
    await db.dues_reminders_sent.create_index(
        [("user_id", 1), ("expires_at", 1), ("stage", 1)], unique=True
    )
    # Speed up the daily dues-reminder window scan (4 queries/day, each ranging
    # over a 1-day window on `membership_expires_at`). Without this index Mongo
    # would table-scan the whole `users` collection on every campaign run.
    await db.users.create_index([("membership_expires_at", 1), ("status", 1)])
    # 'Of The Year' awards — only one winner per (category, year).
    await db.of_the_year_awards.create_index(
        [("category", 1), ("year", 1)], unique=True
    )
    # initialize object storage (non-blocking)
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.warning(f"Object storage init skipped: {e}")
    await seed_data()
    await seed_phase_b()
    await reconcile_chapters()
    await reconcile_tiers()
    await reconcile_awards()
    await seed_anniversary_subevents()
    await seed_default_photo_albums()
    await reconcile_pending_set_password()
    from routes import automated_emails as routes_automated_emails  # local — registered below
    await routes_automated_emails.register.seed_builtin_automated_emails()
    await routes_automated_emails.register.seed_builtin_dues_reminders()
    from routes import email as _routes_email  # local import to avoid load-time cycle
    await _routes_email.seed_builtin_email_templates(db, iso, now_utc, logger)
    await _ensure_site_settings()
    # Start background tasks
    from routes import chat_digest as _routes_chat_digest
    _routes_chat_digest.register(
        db=db, iso=iso, now_utc=now_utc,
        resend_api_key=RESEND_API_KEY, resend_from=RESEND_FROM,
        resend_sdk=resend_sdk, send_sms=send_sms, logger=logger,
    )
    _routes_chat_digest.start_chat_digest_loop()
    asyncio.create_task(routes_automated_emails.register.automated_email_loop())
    asyncio.create_task(_auto_inactive_loop())

async def seed_data():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@clubhaven.app")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin123!")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        now = now_utc()
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Club Admin",
            "role": "admin",
            "bio": "Running the club, one event at a time.",
            "city": "Portland",
            "interests": ["community", "events"],
            "avatar_url": "https://images.unsplash.com/photo-1760574740271-55e6683afe76?q=80&w=400",
            "membership_tier": "lifetime",
            "membership_expires_at": iso(now + timedelta(days=3650)),
            "created_at": iso(now),
        })
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})

    # Demo data is seeded ONCE per database. After it has run, the flag below
    # prevents re-creating the demo member/sub-members even if the admin
    # deleted them. Without this gate, every production deploy used to
    # resurrect deleted demo members (Iter 35 fix).
    demo_seed_marker = await db.site_settings.find_one({"key": "demo_seed_completed"})
    if demo_seed_marker:
        return

    # Demo member if empty
    demo_email = "member@clubhaven.app"
    if not await db.users.find_one({"email": demo_email}):
        now = now_utc()
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": demo_email,
            "password_hash": hash_password("Member123!"),
            "name": "Riley Chen",
            "role": "member",
            "bio": "Birdwatcher, baker, book clubber.",
            "city": "Portland",
            "interests": ["birding", "baking", "books"],
            "avatar_url": "https://images.unsplash.com/photo-1772723246506-6fd0892fbb9a?q=80&w=400",
            "membership_tier": "standard",
            "membership_expires_at": iso(now + timedelta(days=200)),
            "created_at": iso(now),
        })

    # Additional demo members
    demo_members = [
        {"name": "Maya Patel", "city": "Seattle", "interests": ["hiking", "pottery"],
         "bio": "Weekend trailhead hunter.", "avatar_url": "https://images.pexels.com/photos/8555016/pexels-photo-8555016.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"},
        {"name": "Jordan Reed", "city": "Austin", "interests": ["jazz", "photography"],
         "bio": "Film camera enthusiast.", "avatar_url": "https://images.pexels.com/photos/9969335/pexels-photo-9969335.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"},
        {"name": "Sam Okafor", "city": "Portland", "interests": ["cycling", "cooking"],
         "bio": "Sourdough + singletrack.", "avatar_url": ""},
        {"name": "Harper Liu", "city": "Chicago", "interests": ["chess", "coffee"],
         "bio": "Opens with the Italian Game.", "avatar_url": ""},
    ]
    for m in demo_members:
        email = f"{m['name'].lower().replace(' ', '.')}@clubhaven.app"
        if not await db.users.find_one({"email": email}):
            now = now_utc()
            await db.users.insert_one({
                "id": str(uuid.uuid4()),
                "email": email,
                "password_hash": hash_password("Demo123!"),
                "name": m["name"],
                "role": "member",
                "bio": m["bio"],
                "city": m["city"],
                "interests": m["interests"],
                "avatar_url": m["avatar_url"],
                "membership_tier": "standard",
                "membership_expires_at": iso(now + timedelta(days=300)),
                "created_at": iso(now),
            })

    # Demo events
    if await db.events.count_documents({}) == 0:
        base = now_utc()
        samples = [
            {"title": "Neighborhood Picnic & Potluck", "description": "Bring a dish, meet your neighbors, kids welcome. We'll set up in the south meadow with blankets, games, and live acoustic music from member Jordan Reed.",
             "location": "Laurel Park, South Meadow", "start_at": base + timedelta(days=7, hours=11),
             "end_at": base + timedelta(days=7, hours=15), "capacity": 80, "category": "social",
             "cover_image": "https://images.unsplash.com/photo-1767274083868-d74fb3123d97?q=80&w=1200"},
            {"title": "Book Club: 'The Overstory'", "description": "A warm evening of conversation about Richard Powers' ecological novel. Tea and pastries provided. First-timers welcome — come even if you haven't finished the book.",
             "location": "Clubhouse Library", "start_at": base + timedelta(days=14, hours=19),
             "end_at": base + timedelta(days=14, hours=21), "capacity": 20, "category": "culture",
             "cover_image": "https://images.unsplash.com/photo-1758272133693-d2124dbe00de?q=80&w=1200"},
            {"title": "Sunday Trail Hike", "description": "Moderate 4-mile loop with a coffee stop at the top. Dogs on leash welcome. Carpools organized at the trailhead.",
             "location": "Forest Park, Trail 3", "start_at": base + timedelta(days=3, hours=9),
             "end_at": base + timedelta(days=3, hours=12), "capacity": 30, "category": "outdoors",
             "cover_image": "https://images.unsplash.com/photo-1758272133542-b3107b947fc2?q=80&w=1200"},
        ]
        for s in samples:
            s.update({"id": str(uuid.uuid4()), "price": 0.0, "rsvp_count": 0, "created_at": iso(now_utc())})
            s["start_at"] = iso(s["start_at"])
            s["end_at"] = iso(s["end_at"])
            await db.events.insert_one(s)

    # Demo news
    if await db.news.count_documents({}) == 0:
        now = iso(now_utc())
        articles = [
            {"title": "Welcome to ClubHaven 🌿",
             "summary": "A note from the Club Team about what's new this season.",
             "body": "Spring is here, and we have a packed calendar ahead — from the annual potluck to our new book club. Jump into the Events tab to RSVP. As always, bring a friend; we're stronger together.",
             "cover_image": "https://images.unsplash.com/photo-1767274101063-a735a6849afc?q=80&w=1200",
             "tags": ["announcement"], "author_name": "Club Admin", "created_at": now,
             "id": str(uuid.uuid4())},
            {"title": "Member Spotlight: Jordan Reed",
             "summary": "Our resident film photographer on slow mornings and Portra 400.",
             "body": "Jordan has been capturing our events for three years now. We sat down to talk light, patience, and why the best photos happen when no one's posing.",
             "cover_image": "https://images.pexels.com/photos/9969335/pexels-photo-9969335.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "tags": ["spotlight"], "author_name": "Club Admin", "created_at": now,
             "id": str(uuid.uuid4())},
        ]
        for a in articles:
            await db.news.insert_one(a)

    # Demo pages
    if await db.pages.count_documents({}) == 0:
        now = iso(now_utc())
        await db.pages.insert_one({"id": str(uuid.uuid4()), "slug": "about",
            "title": "About ClubHaven",
            "body": "ClubHaven is a members-run community for neighbors who want to gather, learn, and look out for each other. We host 40+ events a year — from trail hikes and book clubs to potlucks and repair cafes. Membership is $60/year; scholarships available on request.",
            "updated_at": now})
        await db.pages.insert_one({"id": str(uuid.uuid4()), "slug": "contact",
            "title": "Contact",
            "body": "Questions, ideas, or want to host an event? Email hello@clubhaven.app or drop by the clubhouse Tuesdays 6–8pm.",
            "updated_at": now})

    # AOP page content
    aop_about_body = (
        "Alpha Omega Phi Military Fraternity & Sorority, Inc. is a 501(c)(3) co-ed Greek organization for "
        "members of the U.S. Armed Forces — Army, Navy, Air Force, Marines, Coast Guard, and Space Force — "
        "past, present, and future.\n\n"
        "We are united across branches by three pillars: Veteran Assistance, Community Service, and Fellowship. "
        "Chapters across the country host charity balls, fundraisers, food drives, and outreach events that put "
        "service members and their families first.\n\n"
        "This portal is a members-only space for Trendsetters to manage their membership, RSVP to chapter events, "
        "log volunteer hours, view awards, browse the directory, and access fraternity documents and photos."
    )
    aop_contact_body = (
        "National Office: (803) 679-2254\n"
        "Fax: (803) 421-7820\n\n"
        "For chapter or membership inquiries, contact your local chapter leadership. New member onboarding is "
        "handled by chapter admins — outside applicants are directed to the public website at alphaomegaphi.org."
    )
    await db.pages.update_one(
        {"slug": "about"},
        {"$set": {"title": "About Alpha Omega Phi", "body": aop_about_body, "updated_at": iso(now_utc())}},
        upsert=True,
    )
    if not await db.pages.find_one({"slug": "about", "id": {"$exists": True}}):
        await db.pages.update_one({"slug": "about"}, {"$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)
    await db.pages.update_one(
        {"slug": "contact"},
        {"$set": {"title": "Contact", "body": aop_contact_body, "updated_at": iso(now_utc())}},
        upsert=True,
    )
    if not await db.pages.find_one({"slug": "contact", "id": {"$exists": True}}):
        await db.pages.update_one({"slug": "contact"}, {"$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)

    # Default chapters
    if await db.chapters.count_documents({}) == 0:
        seeds = [
            {"name": "Alpha Beta", "school": "University of Oregon", "city": "Eugene", "founded_year": 1912,
             "description": "Founding chapter — keepers of the gavel."},
            {"name": "Gamma Delta", "school": "University of Washington", "city": "Seattle", "founded_year": 1925,
             "description": "Pacific Northwest chapter, known for community service."},
            {"name": "Epsilon Theta", "school": "UC Berkeley", "city": "Berkeley", "founded_year": 1948,
             "description": "West coast chapter with strong alumni network."},
        ]
        for s in seeds:
            s["id"] = str(uuid.uuid4())
            s["created_at"] = iso(now_utc())
            await db.chapters.insert_one(s)

    # Default membership tiers
    if await db.tiers.count_documents({}) == 0:
        tiers = [
            {"name": "Pledge", "order": 1, "color": "#A5C4B4", "annual_dues": 30.0,
             "description": "New initiate — working toward active status."},
            {"name": "Active", "order": 2, "color": "#E86A58", "annual_dues": 60.0,
             "description": "Full member in good standing."},
            {"name": "Alumni", "order": 3, "color": "#F9D466", "annual_dues": 40.0,
             "description": "Graduated members staying connected."},
            {"name": "Lifetime", "order": 4, "color": "#8B9DC3", "annual_dues": 0.0,
             "description": "Paid-in-full lifetime membership."},
            {"name": "Honorary", "order": 5, "color": "#D4A574", "annual_dues": 0.0,
             "description": "Honorary distinction — no dues required."},
        ]
        for t in tiers:
            t["id"] = str(uuid.uuid4())
            await db.tiers.insert_one(t)

    # Default awards
    if await db.awards.count_documents({}) == 0:
        awards = [
            {"name": "Founder's Medal", "description": "For extraordinary service to the chapter.",
             "icon": "medal", "color": "#E86A58"},
            {"name": "Service Star", "description": "50+ volunteer hours in one year.",
             "icon": "star", "color": "#F9D466"},
            {"name": "Brotherhood Award", "description": "Embodies the spirit of the fraternity.",
             "icon": "heart", "color": "#A5C4B4"},
            {"name": "Scholar", "description": "Academic excellence.",
             "icon": "graduation-cap", "color": "#8B9DC3"},
            {"name": "Rookie of the Year", "description": "Outstanding new member.",
             "icon": "sparkles", "color": "#D4A574"},
        ]
        for a in awards:
            a["id"] = str(uuid.uuid4())
            a["created_at"] = iso(now_utc())
            await db.awards.insert_one(a)

    # Assign default chapter + tier to existing members that don't have them
    first_chapter = await db.chapters.find_one({}, {"_id": 0, "id": 1})
    active_tier = await db.tiers.find_one({"name": "Active"}, {"_id": 0, "id": 1, "name": 1})
    lifetime_tier = await db.tiers.find_one({"name": "Lifetime"}, {"_id": 0, "id": 1, "name": 1})
    if first_chapter and active_tier:
        await db.users.update_many(
            {"chapter_id": {"$in": [None, ""]}},
            {"$set": {"chapter_id": first_chapter["id"]}},
        )
        await db.users.update_many(
            {"$and": [{"tier_id": {"$in": [None, ""]}}, {"role": {"$ne": "admin"}}]},
            {"$set": {"tier_id": active_tier["id"], "membership_tier": active_tier["name"]}},
        )
        if lifetime_tier:
            await db.users.update_many(
                {"$and": [{"tier_id": {"$in": [None, ""]}}, {"role": "admin"}]},
                {"$set": {"tier_id": lifetime_tier["id"], "membership_tier": lifetime_tier["name"]}},
            )

    # Mark demo seed as completed so future restarts do NOT re-create deleted demo
    # users / events / news. Admin permanently controls this collection from now on.
    await db.site_settings.update_one(
        {"key": "demo_seed_completed"},
        {"$set": {"key": "demo_seed_completed", "value": True, "completed_at": iso(now_utc())}},
        upsert=True,
    )

# ============================================================
# PHASE B — Omega Chapter, Gear store, Donations, Event Calendar, Check-ins, Reports
# ============================================================

# ---------- Omega Chapter (in memoriam) ----------
# Templates the admin can pick when honoring a member (frontend renders the corresponding layout).
# - biography     -> long-form bio with photo, dates, epitaph
# - memorial-card -> formal portrait with name/dates centered + short tribute quote
# - in-service    -> military brief: rank/branch/service dates + photo + summary
OMEGA_TEMPLATES = ["biography", "memorial-card", "in-service"]
# Background styles (frontend maps to CSS gradients / textures).
OMEGA_BACKGROUNDS = [
    "american-flag",
    "navy-starfield",
    "marble",
    "sepia",
    "solid-red",
    "solid-navy",
    "solid-white",
]


class OmegaTributeIn(BaseModel):
    user_id: str
    template: Literal["biography", "memorial-card", "in-service"] = "biography"
    background: Literal[
        "american-flag", "navy-starfield", "marble", "sepia",
        "solid-red", "solid-navy", "solid-white",
    ] = "navy-starfield"
    cover_image: str = ""  # storage URL for tribute photo (separate from member avatar)
    synopsis: str = ""  # short paragraph (used in 'memorial-card' / 'in-service')
    biography: str = ""  # longer rich text (used in 'biography')
    epitaph: str = ""  # short quote/line displayed prominently
    born_at: str = ""  # YYYY-MM-DD
    passed_at: str = ""  # YYYY-MM-DD
    location: str = ""  # city/state where they were laid to rest, optional
    rank: str = ""  # military rank (in-service template)
    service_dates: str = ""  # free-text service dates e.g. "1998 — 2018"


class OmegaTributeUpdateIn(BaseModel):
    template: Optional[Literal["biography", "memorial-card", "in-service"]] = None
    background: Optional[Literal[
        "american-flag", "navy-starfield", "marble", "sepia",
        "solid-red", "solid-navy", "solid-white",
    ]] = None
    cover_image: Optional[str] = None
    synopsis: Optional[str] = None
    biography: Optional[str] = None
    epitaph: Optional[str] = None
    born_at: Optional[str] = None
    passed_at: Optional[str] = None
    location: Optional[str] = None
    rank: Optional[str] = None
    service_dates: Optional[str] = None


def tribute_out(t: dict, member: Optional[dict] = None) -> dict:
    out = {
        "id": t["id"],
        "user_id": t["user_id"],
        "template": t.get("template", "biography"),
        "background": t.get("background", "navy-starfield"),
        "cover_image": t.get("cover_image", ""),
        "synopsis": t.get("synopsis", ""),
        "biography": t.get("biography", ""),
        "epitaph": t.get("epitaph", ""),
        "born_at": t.get("born_at", ""),
        "passed_at": t.get("passed_at", ""),
        "location": t.get("location", ""),
        "rank": t.get("rank", ""),
        "service_dates": t.get("service_dates", ""),
        "created_at": t.get("created_at"),
        "created_by_name": t.get("created_by_name", ""),
        "updated_at": t.get("updated_at"),
    }
    if member:
        out["member"] = {
            "id": member["id"],
            "name": member.get("name", ""),
            "email": member.get("email", ""),
            "line_name": member.get("line_name", ""),
            "branch_of_service": member.get("branch_of_service", ""),
            "city": member.get("city", ""),
            "state": member.get("state", ""),
            "country": member.get("country", ""),
            "avatar_url": member.get("avatar_url", ""),
            "join_date": member.get("join_date", ""),
            "intake_line": member.get("intake_line", ""),
            "deceased_at": member.get("deceased_at", ""),
        }
    return out


@api.get("/omega")
async def omega_chapter():
    """Returns the Omega list — users who are deceased PLUS any explicit tributes,
    merged so the frontend can render either the legacy auto-card or the new template-based tribute."""
    # 1) Fetch deceased members
    member_cursor = db.users.find(
        {"$or": [{"status_override": "deceased"}, {"deceased_at": {"$nin": [None, ""]}}]},
        {"_id": 0, "password_hash": 0},
    ).sort("deceased_at", -1)
    members = await member_cursor.to_list(500)
    # 2) Fetch tributes
    tribute_cursor = db.omega_tributes.find({}, {"_id": 0}).sort("created_at", -1)
    tributes = await tribute_cursor.to_list(500)
    tributes_by_uid = {t["user_id"]: t for t in tributes}
    # 3) Merge — every deceased member gets an entry; tributes provide template+synopsis
    out = []
    seen = set()
    for m in members:
        seen.add(m["id"])
        t = tributes_by_uid.get(m["id"])
        if t:
            out.append({"type": "tribute", **tribute_out(t, m)})
        else:
            # Legacy member-only card
            pu = public_user(m)
            out.append({
                "type": "member",
                "id": m["id"],
                "user_id": m["id"],
                "template": "biography",
                "background": "navy-starfield",
                "cover_image": "",
                "synopsis": "",
                "biography": "",
                "epitaph": "",
                "born_at": "",
                "passed_at": m.get("deceased_at", ""),
                "location": pu.get("city", ""),
                "rank": "",
                "service_dates": "",
                "member": {
                    "id": m["id"],
                    "name": pu.get("name", ""),
                    "email": pu.get("email", ""),
                    "line_name": pu.get("line_name", ""),
                    "branch_of_service": pu.get("branch_of_service", ""),
                    "city": pu.get("city", ""),
                    "state": pu.get("state", ""),
                    "country": pu.get("country", ""),
                    "avatar_url": pu.get("avatar_url", ""),
                    "join_date": pu.get("join_date", ""),
                    "intake_line": pu.get("intake_line", ""),
                    "deceased_at": pu.get("deceased_at", ""),
                },
            })
    # 4) Tributes for non-deceased members (admin published a tribute manually without setting status)
    for t in tributes:
        if t["user_id"] in seen:
            continue
        m = await db.users.find_one({"id": t["user_id"]}, {"_id": 0, "password_hash": 0})
        if not m:
            continue
        out.append({"type": "tribute", **tribute_out(t, m)})
    # Sort: most recent passed_at / deceased_at first
    def sort_key(x):
        return x.get("passed_at") or (x.get("member") or {}).get("deceased_at") or ""
    out.sort(key=sort_key, reverse=True)
    return out


@api.get("/omega/options")
async def omega_options(_: dict = Depends(get_current_user)):
    """Frontend uses this to populate the template + background pickers."""
    return {"templates": OMEGA_TEMPLATES, "backgrounds": OMEGA_BACKGROUNDS}


@api.post("/omega/tributes")
async def create_tribute(body: OmegaTributeIn, admin: dict = Depends(admin_tab_dep("members"))):
    """Admin creates a tribute for a member. Also flips the member's status to deceased
    if not already so they appear in the Omega Chapter."""
    member = await db.users.find_one({"id": body.user_id})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    existing = await db.omega_tributes.find_one({"user_id": body.user_id})
    if existing:
        raise HTTPException(status_code=400, detail="A tribute already exists for this member — edit it instead.")
    doc = {
        "id": str(uuid.uuid4()),
        **body.model_dump(),
        "created_by": admin["id"],
        "created_by_name": admin.get("name", ""),
        "created_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }
    await db.omega_tributes.insert_one(doc)
    # Mark deceased automatically if not already
    if member.get("status_override") != "deceased":
        set_doc = {"status_override": "deceased"}
        if body.passed_at and not member.get("deceased_at"):
            set_doc["deceased_at"] = body.passed_at
        await db.users.update_one({"id": body.user_id}, {"$set": set_doc})
    return tribute_out(doc, member)


@api.put("/omega/tributes/{tribute_id}")
async def update_tribute(tribute_id: str, body: OmegaTributeUpdateIn, admin: dict = Depends(admin_tab_dep("members"))):
    existing = await db.omega_tributes.find_one({"id": tribute_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Tribute not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates["updated_at"] = iso(now_utc())
    updates["updated_by"] = admin["id"]
    updates["updated_by_name"] = admin.get("name", "")
    await db.omega_tributes.update_one({"id": tribute_id}, {"$set": updates})
    t = await db.omega_tributes.find_one({"id": tribute_id}, {"_id": 0})
    member = await db.users.find_one({"id": t["user_id"]}, {"_id": 0, "password_hash": 0})
    return tribute_out(t, member)


@api.delete("/omega/tributes/{tribute_id}")
async def delete_tribute(tribute_id: str, _: dict = Depends(admin_tab_dep("members"))):
    existing = await db.omega_tributes.find_one({"id": tribute_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Tribute not found")
    await db.omega_tributes.delete_one({"id": tribute_id})
    return {"ok": True}


@api.post("/omega/upload")
async def upload_omega_cover(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("members"))):
    """Admin uploads a tribute cover photo. Returns {url} that can be used as cover_image."""
    chunks: list = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > 15 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Tribute image must be under 15 MB")
        chunks.append(chunk)
    data = b"".join(chunks)
    fname = (file.filename or "tribute.jpg").replace("/", "_")
    ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
    if ext not in IMAGE_EXT:
        raise HTTPException(status_code=400, detail="Only images allowed (jpg, png, gif, webp)")
    content_type = file.content_type or MIME_BY_EXT.get(ext, "image/jpeg")
    file_id = str(uuid.uuid4())
    storage_path = f"omega/{file_id}/{fname}"

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
    return {"url": f"/api/files/{storage_path}", "size": total}


# ---------- Omega Hero (featured banner image at top of /omega) ----------
class OmegaHeroIn(BaseModel):
    image_url: str = ""
    title: str = ""
    caption: str = ""


@api.get("/omega/hero")
async def get_omega_hero():
    doc = await db.app_settings.find_one({"key": "omega_hero"}, {"_id": 0})
    if not doc:
        return {"image_url": "", "title": "", "caption": ""}
    return {
        "image_url": doc.get("image_url", ""),
        "title": doc.get("title", ""),
        "caption": doc.get("caption", ""),
        "updated_at": doc.get("updated_at"),
    }


@api.put("/omega/hero")
async def set_omega_hero(body: OmegaHeroIn, admin: dict = Depends(admin_tab_dep("members"))):
    await db.app_settings.update_one(
        {"key": "omega_hero"},
        {"$set": {
            "key": "omega_hero",
            "image_url": body.image_url,
            "title": body.title,
            "caption": body.caption,
            "updated_at": iso(now_utc()),
            "updated_by": admin.get("name", ""),
        }},
        upsert=True,
    )
    return {"ok": True, "image_url": body.image_url, "title": body.title, "caption": body.caption}


# ---------- AOP Form Links (picture cards linking to a webpage on AOP Forms page) ----------
class FormLinkIn(BaseModel):
    title: str
    description: str = ""
    url: str
    image_url: str = ""
    order: int = 0


class FormLinkUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    order: Optional[int] = None


def _form_link_out(d: dict) -> dict:
    return {
        "id": d["id"],
        "title": d.get("title", ""),
        "description": d.get("description", ""),
        "url": d.get("url", ""),
        "image_url": d.get("image_url", ""),
        "order": d.get("order", 0),
        "created_at": d.get("created_at"),
        "created_by_name": d.get("created_by_name", ""),
    }


@api.get("/form-links")
async def list_form_links():
    rows = await db.form_links.find({}, {"_id": 0}).sort([("order", 1), ("created_at", 1)]).to_list(200)
    return [_form_link_out(r) for r in rows]


@api.post("/form-links")
async def create_form_link(body: FormLinkIn, admin: dict = Depends(admin_tab_dep("members"))):
    if not body.title.strip() or not body.url.strip():
        raise HTTPException(status_code=400, detail="Title and URL are required.")
    doc = {
        "id": str(uuid.uuid4()),
        "title": body.title.strip(),
        "description": body.description.strip(),
        "url": body.url.strip(),
        "image_url": body.image_url.strip(),
        "order": body.order,
        "created_by": admin["id"],
        "created_by_name": admin.get("name", ""),
        "created_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }
    await db.form_links.insert_one(doc)
    return _form_link_out(doc)


@api.put("/form-links/{link_id}")
async def update_form_link(link_id: str, body: FormLinkUpdateIn, _: dict = Depends(admin_tab_dep("members"))):
    existing = await db.form_links.find_one({"id": link_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Form link not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "title" in updates and not str(updates["title"]).strip():
        raise HTTPException(status_code=400, detail="Title cannot be blank.")
    if "url" in updates and not str(updates["url"]).strip():
        raise HTTPException(status_code=400, detail="URL cannot be blank.")
    updates["updated_at"] = iso(now_utc())
    await db.form_links.update_one({"id": link_id}, {"$set": updates})
    out = await db.form_links.find_one({"id": link_id}, {"_id": 0})
    return _form_link_out(out)


@api.delete("/form-links/{link_id}")
async def delete_form_link(link_id: str, _: dict = Depends(admin_tab_dep("members"))):
    existing = await db.form_links.find_one({"id": link_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Form link not found")
    await db.form_links.delete_one({"id": link_id})
    return {"ok": True}


@api.post("/form-links/upload")
async def upload_form_link_image(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("members"))):
    """Admin uploads a picture for a form-link card. Returns {url}."""
    chunks: list = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Image must be under 10 MB")
        chunks.append(chunk)
    data = b"".join(chunks)
    fname = (file.filename or "link.jpg").replace("/", "_")
    ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
    if ext not in IMAGE_EXT:
        raise HTTPException(status_code=400, detail="Only images allowed (jpg, png, gif, webp)")
    content_type = file.content_type or MIME_BY_EXT.get(ext, "image/jpeg")
    file_id = str(uuid.uuid4())
    storage_path = f"form-links/{file_id}/{fname}"
    await asyncio.to_thread(put_object, storage_path, data, content_type)
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
    return {"url": f"/api/files/{storage_path}", "size": total}


# ---------- Generic admin image upload (chapter logo / cause / news / chat group) ----------
async def _upload_image(file: UploadFile, prefix: str, user: dict, max_mb: int = 10) -> dict:
    chunks: list = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Image must be under {max_mb} MB")
        chunks.append(chunk)
    data = b"".join(chunks)
    fname = (file.filename or "image.jpg").replace("/", "_")
    ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
    if ext not in IMAGE_EXT:
        raise HTTPException(status_code=400, detail="Only images allowed (jpg, png, gif, webp)")
    content_type = file.content_type or MIME_BY_EXT.get(ext, "image/jpeg")
    file_id = str(uuid.uuid4())
    storage_path = f"{prefix}/{file_id}/{fname}"
    await asyncio.to_thread(put_object, storage_path, data, content_type)
    await db.chat_files.insert_one({
        "id": file_id, "filename": fname, "storage_path": storage_path,
        "content_type": content_type, "size": total, "kind": "image",
        "uploaded_by": user["id"], "is_deleted": False, "created_at": iso(now_utc()),
    })
    return {"url": f"/api/files/{storage_path}", "size": total}


@api.post("/chapters/upload-logo")
async def chapter_logo_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("chapters"))):
    return await _upload_image(file, "chapter-logos", user)


@api.post("/causes/upload-image")
async def cause_image_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("causes"))):
    return await _upload_image(file, "causes", user)


@api.post("/news/upload-image")
async def news_image_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("news"))):
    return await _upload_image(file, "news", user)


@api.post("/leadership/upload-image")
async def leadership_image_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("pages"))):
    return await _upload_image(file, "leadership", user)


@api.post("/founders/upload-image")
async def founders_image_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("pages"))):
    return await _upload_image(file, "founders", user)


@api.post("/events/upload-cover")
async def events_cover_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("events"))):
    return await _upload_image(file, "events", user)


@api.post("/chat/group-photo-upload")
async def chat_group_photo_upload(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Any logged-in user can upload — they'll only be able to attach the
    resulting URL to a conversation they belong to (enforced by /conversations PUT)."""
    return await _upload_image(file, "chat-groups", user, max_mb=8)


# ---------- Schedule a Meeting (admin-editable cards) ----------
class MeetingCardIn(BaseModel):
    name: str
    title: str = ""
    description: str = ""
    image_url: str = ""
    button_label: str = "Book Meeting"
    button_url: str
    order: int = 0


class MeetingCardUpdateIn(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    button_label: Optional[str] = None
    button_url: Optional[str] = None
    order: Optional[int] = None


def _meeting_out(d: dict) -> dict:
    return {
        "id": d["id"],
        "name": d.get("name", ""),
        "title": d.get("title", ""),
        "description": d.get("description", ""),
        "image_url": d.get("image_url", ""),
        "button_label": d.get("button_label", "Book Meeting"),
        "button_url": d.get("button_url", ""),
        "order": d.get("order", 0),
        "created_at": d.get("created_at"),
    }


@api.get("/meeting-cards")
async def list_meeting_cards():
    rows = await db.meeting_cards.find({}, {"_id": 0}).sort([("order", 1), ("created_at", 1)]).to_list(200)
    return [_meeting_out(r) for r in rows]


@api.post("/meeting-cards")
async def create_meeting_card(body: MeetingCardIn, admin: dict = Depends(admin_tab_dep("members"))):
    if not body.name.strip() or not body.button_url.strip():
        raise HTTPException(status_code=400, detail="Name and Book Meeting URL are required.")
    doc = {
        "id": str(uuid.uuid4()),
        "name": body.name.strip(),
        "title": body.title.strip(),
        "description": body.description.strip(),
        "image_url": body.image_url.strip(),
        "button_label": (body.button_label or "Book Meeting").strip(),
        "button_url": body.button_url.strip(),
        "order": body.order,
        "created_by_name": admin.get("name", ""),
        "created_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }
    await db.meeting_cards.insert_one(doc)
    return _meeting_out(doc)


@api.put("/meeting-cards/{card_id}")
async def update_meeting_card(card_id: str, body: MeetingCardUpdateIn, _: dict = Depends(admin_tab_dep("members"))):
    existing = await db.meeting_cards.find_one({"id": card_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Meeting card not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "name" in updates and not str(updates["name"]).strip():
        raise HTTPException(status_code=400, detail="Name cannot be blank.")
    if "button_url" in updates and not str(updates["button_url"]).strip():
        raise HTTPException(status_code=400, detail="Book Meeting URL cannot be blank.")
    updates["updated_at"] = iso(now_utc())
    await db.meeting_cards.update_one({"id": card_id}, {"$set": updates})
    out = await db.meeting_cards.find_one({"id": card_id}, {"_id": 0})
    return _meeting_out(out)


@api.delete("/meeting-cards/{card_id}")
async def delete_meeting_card(card_id: str, _: dict = Depends(admin_tab_dep("members"))):
    existing = await db.meeting_cards.find_one({"id": card_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Meeting card not found")
    await db.meeting_cards.delete_one({"id": card_id})
    return {"ok": True}


@api.post("/meeting-cards/upload-image")
async def meeting_card_image_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("members"))):
    return await _upload_image(file, "meeting-cards", user)






# ---------- AOP Gear (catalog + page settings + uploads) ----------
# Endpoints `/gear`, `/gear/{id}`, `/gear-page`, `/gear/upload` are registered
# via `routes/gear.py` (see register call at bottom of this file). Keeping this
# header here only so the chat/digest sections directly below stay readable.


# ============================================================
# Donations / Causes / Top-Donors leaderboard
# Extracted to routes/donations.py (see register call at bottom of this file).
# The PayPal capture flow below still calls `recompute_cause_totals` through
# the module-level export.
# ============================================================
from routes.donations import recompute_cause_totals, cause_out  # noqa: E402,F401 — re-exported for legacy callsites



# ---------- Event Calendar & Check-In ----------
@api.get("/calendar/events")
async def events_calendar(month: Optional[str] = None):
    """Events for a given YYYY-MM month (defaults to current month)."""
    today = now_utc()
    if month:
        try:
            year, mo = month.split("-")
            year, mo = int(year), int(mo)
        except Exception:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    else:
        year, mo = today.year, today.month
    start = datetime(year, mo, 1, tzinfo=timezone.utc)
    if mo == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, mo + 1, 1, tzinfo=timezone.utc)
    cursor = db.events.find(
        {"start_at": {"$gte": iso(start), "$lt": iso(end)}},
        {"_id": 0},
    ).sort("start_at", 1)
    items = await cursor.to_list(500)
    for e in items:
        e["rsvp_count"] = await db.rsvps.count_documents({"event_id": e["id"]})
        e["checkin_count"] = await db.checkins.count_documents({"event_id": e["id"]})
    return items

class CheckInIn(BaseModel):
    user_id: Optional[str] = None
    guest_name: Optional[str] = None  # for walk-in non-members or a member's invited guest
    # If guest_name is supplied AND host_user_id points at the member who RSVP'd
    # this guest, the check-in record links them so reports can group guests
    # under the inviting member.
    host_user_id: Optional[str] = None
    ticket_type: Literal["vip", "all_access", "general", "guest", "speaker", "volunteer"] = "general"
    note: str = ""

@api.post("/events/{event_id}/check-in")
async def check_in(event_id: str, body: CheckInIn, admin: dict = Depends(admin_tab_dep("events"))):
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not body.user_id and not body.guest_name:
        raise HTTPException(status_code=400, detail="Provide user_id or guest_name")
    if body.user_id:
        existing = await db.checkins.find_one({"event_id": event_id, "user_id": body.user_id})
        if existing:
            raise HTTPException(status_code=400, detail="Already checked in")
        u = await db.users.find_one({"id": body.user_id}, {"_id": 0, "password_hash": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        display = u.get("name", "")
    else:
        # Check duplicate guest check-in on the same event
        gx = await db.checkins.find_one({"event_id": event_id, "user_id": None, "user_name": body.guest_name, "host_user_id": body.host_user_id})
        if gx:
            raise HTTPException(status_code=400, detail="This guest has already been checked in")
        display = body.guest_name
    doc = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "event_title": event.get("title", ""),
        "user_id": body.user_id,
        "user_name": display,
        "host_user_id": body.host_user_id,  # populated only for guest rows
        "is_guest": body.user_id is None,
        "ticket_type": body.ticket_type,
        "note": body.note,
        "checked_in_by": admin["id"],
        "checked_in_by_name": admin.get("name", "Admin"),
        "checked_in_at": iso(now_utc()),
    }
    await db.checkins.insert_one(doc)
    out = dict(doc)
    out.pop("_id", None)
    return out


@api.get("/events/{event_id}/check-in-roster")
async def check_in_roster(event_id: str, _: dict = Depends(admin_tab_dep("events"))):
    """Flat roster for the check-in screen: every RSVP'd member + every guest
    they brought + every already-checked-in walk-in, each with status."""
    event = await db.events.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    rsvps = await db.rsvps.find({"event_id": event_id}, {"_id": 0}).to_list(2000)
    checkins = await db.checkins.find({"event_id": event_id}, {"_id": 0}).to_list(2000)
    checked_in_member_ids = {c["user_id"] for c in checkins if c.get("user_id")}
    checked_in_guest_keys = {(c.get("host_user_id"), c.get("user_name")) for c in checkins if c.get("is_guest")}
    rows = []
    for r in rsvps:
        u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "name": 1, "email": 1, "avatar_url": 1, "line_name": 1})
        rows.append({
            "kind": "member",
            "user_id": r["user_id"],
            "host_user_id": None,
            "name": (u or {}).get("name", r.get("user_name", "")),
            "email": (u or {}).get("email", ""),
            "avatar_url": (u or {}).get("avatar_url", ""),
            "line_name": (u or {}).get("line_name", ""),
            "ticket_type": r.get("ticket_type", "general"),
            "checked_in": r["user_id"] in checked_in_member_ids,
        })
        for g in (r.get("guests") or []):
            gname = g.get("name") if isinstance(g, dict) else str(g)
            rows.append({
                "kind": "guest",
                "user_id": None,
                "host_user_id": r["user_id"],
                "host_name": (u or {}).get("name", r.get("user_name", "")),
                "name": gname,
                "email": (g.get("email") if isinstance(g, dict) else ""),
                "ticket_type": (g.get("ticket_type") if isinstance(g, dict) else "guest"),
                "checked_in": (r["user_id"], gname) in checked_in_guest_keys,
            })
    # Also include any walk-in check-ins not on the RSVP list
    for c in checkins:
        if not c.get("user_id") and not c.get("host_user_id"):
            rows.append({
                "kind": "walkin",
                "user_id": None,
                "host_user_id": None,
                "name": c.get("user_name", ""),
                "ticket_type": c.get("ticket_type", "guest"),
                "checked_in": True,
            })
    return rows

@api.get("/events/{event_id}/check-ins")
async def list_checkins(event_id: str, _: dict = Depends(admin_tab_dep("events"))):
    items = await db.checkins.find({"event_id": event_id}, {"_id": 0}).sort("checked_in_at", -1).to_list(2000)
    return items

@api.delete("/events/{event_id}/check-ins/{checkin_id}")
async def remove_checkin(event_id: str, checkin_id: str, _: dict = Depends(admin_tab_dep("events"))):
    await db.checkins.delete_one({"id": checkin_id, "event_id": event_id})
    return {"ok": True}


# ---------- Reporting & Personnel Brief ----------
def _period_to_range(year, quarter, month):
    """Returns (from_iso, to_iso) inclusive for the requested period. Any param
    can be None. Quarter takes precedence over month if both provided.
    Returns (None, None) when no period given. Used by routes/hours.py and
    routes/reports.py via dependency injection."""
    from calendar import monthrange
    if not year:
        return None, None
    if month:
        m = max(1, min(12, month))
        last = monthrange(year, m)[1]
        return f"{year:04d}-{m:02d}-01T00:00:00Z", f"{year:04d}-{m:02d}-{last:02d}T23:59:59Z"
    if quarter:
        q = max(1, min(4, quarter))
        start_m = (q - 1) * 3 + 1
        end_m = start_m + 2
        last = monthrange(year, end_m)[1]
        return f"{year:04d}-{start_m:02d}-01T00:00:00Z", f"{year:04d}-{end_m:02d}-{last:02d}T23:59:59Z"
    return f"{year:04d}-01-01T00:00:00Z", f"{year:04d}-12-31T23:59:59Z"


# All /reports/* endpoints + the two personnel-brief helpers
# (_personnel_brief_data and _personnel_brief_pdf_response) are extracted to
# routes/reports.py. The back-compat shims below keep the /me/personnel-brief*
# member-side endpoints working — they call the helpers via the function
# pointers set by the routes_reports.register() call at the bottom of this file.
async def _personnel_brief_data(user_id: str) -> dict:
    fn = getattr(_personnel_brief_data, "_impl", None)
    if fn is None:
        raise HTTPException(status_code=503, detail="reports module not registered")
    return await fn(user_id)


async def _personnel_brief_pdf_response(user_id: str):
    fn = getattr(_personnel_brief_pdf_response, "_impl", None)
    if fn is None:
        raise HTTPException(status_code=503, detail="reports module not registered")
    return await fn(user_id)




# ---------- Member-self brief download ----------
# Convenience wrappers so a member can pull their own personnel brief without
# admin privileges. They forward to the admin endpoint with their own user_id.
@api.get("/me/personnel-brief")
async def my_personnel_brief(user: dict = Depends(get_current_user)):
    """Member-side: their own personnel brief JSON."""
    return await _personnel_brief_data(user["id"])


@api.get("/me/personnel-brief/pdf")
async def my_personnel_brief_pdf(user: dict = Depends(get_current_user)):
    """Member-side: their own personnel brief as a PDF download."""
    return await _personnel_brief_pdf_response(user["id"])


@api.get("/me/tax-letter/pdf")
async def my_tax_letter_pdf(
    year: Optional[int] = None,
    user: dict = Depends(get_current_user),
):
    """Member-side: annual tax-donation letter PDF for the given year (defaults to last completed year).

    Sums all approved dues + donations the member paid during the year. Uses
    EIN 82-0794957 and Cory T. Burnett's signature image (`/app/backend/assets/cory_signature.png`).
    """
    if year is None:
        year = now_utc().year - 1  # default to last year for tax purposes
    return await _build_tax_letter_pdf(user, year)


async def _build_tax_letter_pdf(user: dict, year: int):
    """Render the IRS-style tax acknowledgment letter for one member + year."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from io import BytesIO
    import os.path

    # Pull all completed transactions for the year. Dues + donations + fees are
    # all tax-deductible at a 501(c)(3), per the user's spec ("dues and donations
    # given altogether"). Pending or rejected transactions are excluded.
    year_start = f"{year}-01-01"
    year_end = f"{year + 1}-01-01"
    cursor = db.transactions.find({
        "user_id": user["id"],
        "status": "completed",
        "created_at": {"$gte": year_start, "$lt": year_end},
        "type": {"$in": ["renewal", "donation", "fee"]},
    }, {"_id": 0}).sort("created_at", 1)
    txs = await cursor.to_list(500)
    total = sum(float(t.get("amount") or 0) for t in txs)
    dues_total = sum(float(t.get("amount") or 0) for t in txs if t.get("purpose") == "dues" or t.get("type") == "renewal")
    donation_total = sum(float(t.get("amount") or 0) for t in txs if t.get("type") == "donation")

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.85 * inch, rightMargin=0.85 * inch, topMargin=0.9 * inch, bottomMargin=0.75 * inch, title=f"Tax Letter — {user.get('name', '')} {year}")
    styles = getSampleStyleSheet()
    AOP_NAVY = colors.HexColor("#0C1B33")
    header_style = ParagraphStyle("AopHeader", parent=styles["Heading1"], textColor=AOP_NAVY, fontSize=18, leading=22, alignment=1, spaceAfter=4)
    sub_style = ParagraphStyle("AopHeaderSub", parent=styles["BodyText"], fontSize=10, leading=13, textColor=colors.HexColor("#555555"), alignment=1, spaceAfter=18)
    body_style = ParagraphStyle("AopBody", parent=styles["BodyText"], fontSize=11, leading=16)
    small = ParagraphStyle("AopSmall", parent=styles["BodyText"], fontSize=8, leading=11, textColor=colors.HexColor("#888888"))

    elements: list = []
    elements.append(Paragraph("<b>Alpha Omega Phi Military Fraternity &amp; Sorority, Inc.</b>", header_style))
    elements.append(Paragraph("A 501(c)(3) non-profit organization · EIN <b>82-0794957</b>", sub_style))

    today = now_utc().strftime("%B %d, %Y")
    elements.append(Paragraph(today, body_style))
    elements.append(Spacer(1, 14))

    # Donor address block
    elements.append(Paragraph(f"<b>{user.get('name', '')}</b>", body_style))
    if user.get("address"):
        elements.append(Paragraph(user["address"], body_style))
    city_line = ", ".join(p for p in [user.get("city"), user.get("state"), user.get("zip_code")] if p)
    if city_line:
        elements.append(Paragraph(city_line, body_style))
    elements.append(Spacer(1, 18))

    # Salutation + body
    salutation_name = user.get("first_name") or (user.get("name") or "Member").split(" ")[0]
    elements.append(Paragraph(f"Dear {salutation_name},", body_style))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        f"On behalf of Alpha Omega Phi Military Fraternity &amp; Sorority, Inc., thank you "
        f"for your generosity during the {year} calendar year. Your contributions sustain our "
        f"chapters, our veteran-focused community programs, and the mission we share.",
        body_style,
    ))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        "This letter serves as your official acknowledgment of charitable contributions "
        "for tax-reporting purposes. Alpha Omega Phi Military Fraternity &amp; Sorority, Inc. "
        "is a 501(c)(3) tax-exempt organization. <b>EIN: 82-0794957.</b> No goods or services "
        "were provided to you in exchange for these contributions, except for intangible "
        "religious or membership benefits.",
        body_style,
    ))
    elements.append(Spacer(1, 14))

    # Itemized table
    rows = [["Date", "Description", "Type", "Amount"]]
    for t in txs:
        rows.append([
            (t.get("created_at") or "")[:10],
            (t.get("description") or "—")[:55],
            ("Dues" if (t.get("purpose") == "dues" or t.get("type") == "renewal") else (t.get("type") or "—").title()),
            f"${float(t.get('amount') or 0):.2f}",
        ])
    rows.append(["", "", "Total", f"${total:.2f}"])
    item_tbl = Table(rows, colWidths=[0.95 * inch, 3.4 * inch, 0.9 * inch, 1.0 * inch])
    item_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0EBE3")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, 0), AOP_NAVY),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#EFEFEF")),
        ("LINEABOVE", (0, -1), (-1, -1), 0.75, AOP_NAVY),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(item_tbl)
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(
        f"Summary: Annual dues <b>${dues_total:,.2f}</b> · Donations <b>${donation_total:,.2f}</b> · "
        f"<b>Total tax-deductible contributions: ${total:,.2f}</b>.",
        body_style,
    ))
    elements.append(Spacer(1, 18))

    elements.append(Paragraph(
        "Please retain this letter with your tax records. Consult your tax advisor regarding the "
        "deductibility of your contributions. Should you need anything further, contact us at "
        "info@alphaomegaphi.org.",
        body_style,
    ))
    elements.append(Spacer(1, 22))
    elements.append(Paragraph("With sincere thanks,", body_style))

    # Signature image — pulled from bundled assets directory. Aligned to the
    # left margin so it sits directly above the signature block (name, title,
    # organization) rather than floating to the page center.
    sig_path = "/app/backend/assets/cory_signature.png"
    if os.path.isfile(sig_path):
        try:
            elements.append(Spacer(1, 4))
            sig_img = Image(sig_path, width=2.0 * inch, height=0.78 * inch)
            sig_img.hAlign = "LEFT"
            elements.append(sig_img)
        except Exception as ex:
            logger.warning(f"[tax-letter] signature render failed: {ex}")

    elements.append(Paragraph("<b>Cory T. Burnett</b>", body_style))
    elements.append(Paragraph("Co-Founder", body_style))
    elements.append(Paragraph("Alpha Omega Phi Military Fraternity &amp; Sorority, Inc.", body_style))
    elements.append(Spacer(1, 16))
    elements.append(Paragraph(
        f"Tax-acknowledgment letter for the {year} calendar year. Generated {today}. "
        f"This document is auto-produced and certified by the organization records system.",
        small,
    ))

    doc.build(elements)
    buf.seek(0)
    safe_name = (user.get("name") or "member").replace(" ", "_")
    filename = f"aop-tax-letter-{safe_name}-{year}.pdf"
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- Seed Phase B sample data (idempotent) ----------
async def seed_phase_b():
    # Demo gear / causes are seeded ONCE per database. After admin deletes them,
    # subsequent restarts must not resurrect them (Iter 35 fix).
    demo_seed_marker = await db.site_settings.find_one({"key": "demo_seed_completed"})
    if demo_seed_marker:
        return
    if await db.gear.count_documents({}) == 0:
        sample_gear = [
            {"name": "AOP Trendsetter Polo", "description": "Embroidered crest polo in navy. Officer-grade combed cotton.",
             "price": 38.0, "sizes": ["S", "M", "L", "XL", "XXL"], "colors": ["Navy", "White"],
             "cover_image": "https://images.unsplash.com/photo-1586790170083-2f9ceadc732d?w=800",
             "category": "apparel", "in_stock": True, "sku": "AOP-POLO-01"},
            {"name": "Commemorative 10-Year Tee", "description": "Limited edition anniversary t-shirt. 100% combed ringspun cotton.",
             "price": 25.0, "sizes": ["S", "M", "L", "XL", "XXL"], "colors": ["Red", "Navy", "Black"],
             "cover_image": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=800",
             "category": "apparel", "in_stock": True, "sku": "AOP-TEE-10YR"},
            {"name": "AOP Challenge Coin", "description": "Solid metal challenge coin with crest. A collector's piece.",
             "price": 18.0, "sizes": ["One size"], "colors": ["Gold/Navy"],
             "cover_image": "https://images.unsplash.com/photo-1592334873219-42ca023e48ce?w=800",
             "category": "accessory", "in_stock": True, "sku": "AOP-COIN"},
            {"name": "Trendsetters Hoodie", "description": "Heavyweight pullover hoodie with embroidered crest.",
             "price": 55.0, "sizes": ["S", "M", "L", "XL", "XXL"], "colors": ["Navy", "Charcoal"],
             "cover_image": "https://images.unsplash.com/photo-1556821840-3a63f95609a7?w=800",
             "category": "apparel", "in_stock": True, "sku": "AOP-HOOD-01"},
        ]
        for g in sample_gear:
            g["id"] = str(uuid.uuid4())
            g["created_at"] = iso(now_utc())
            g["images"] = []
            await db.gear.insert_one(g)

    if await db.causes.count_documents({}) == 0:
        sample_causes = [
            {"title": "Veteran Family Emergency Fund",
             "description": "Direct grants to AOP brothers, sisters, and families facing crisis — rent, utilities, medical.",
             "goal_amount": 25000.0,
             "cover_image": "https://images.unsplash.com/photo-1532629345422-7515f3d16bb6?w=1200",
             "category": "veteran", "is_active": True},
            {"title": "Trendsetters Scholarship",
             "description": "Yearly scholarship awarded to a high school senior of a service member family.",
             "goal_amount": 10000.0,
             "cover_image": "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=1200",
             "category": "education", "is_active": True},
            {"title": "10-Year Anniversary Gala Fund",
             "description": "Help underwrite the July 27, 2027 anniversary celebration in Atlanta.",
             "goal_amount": 50000.0,
             "cover_image": "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1200",
             "category": "anniversary", "is_active": True},
        ]
        for c in sample_causes:
            c["id"] = str(uuid.uuid4())
            c["raised_amount"] = 0.0
            c["donor_count"] = 0
            c["created_at"] = iso(now_utc())
            await db.causes.insert_one(c)


# ============================================================
# PHASE C — PayPal payments + Resend email blasts
# ============================================================
import httpx
import asyncio
import resend as resend_sdk

PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox").lower()
PAYPAL_BASE = "https://api-m.paypal.com" if PAYPAL_MODE == "live" else "https://api-m.sandbox.paypal.com"
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET", "")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "Alpha Omega Phi <onboarding@resend.dev>")
RESEND_REPLY_TO = os.environ.get("RESEND_REPLY_TO", "info@aop-app.org")
ORG_MAILING_ADDRESS = os.environ.get(
    "ORG_MAILING_ADDRESS",
    "Alpha Omega Phi Military Fraternity & Sorority, Inc."
)
UNSUBSCRIBE_SECRET = os.environ.get("UNSUBSCRIBE_SECRET") or os.environ.get("JWT_SECRET", "")
if RESEND_API_KEY:
    resend_sdk.api_key = RESEND_API_KEY


# ---------- Deliverability helpers ----------
def _html_to_text(html: str) -> str:
    """Cheap HTML→plain-text converter for multipart email. Strips tags,
    decodes a handful of entities, collapses whitespace. Helps deliverability:
    HTML-only emails are a strong spam signal."""
    import re
    import html as _html
    if not html:
        return ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", html)
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = _html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def _unsubscribe_token(user_id: str) -> str:
    """HMAC-signed token tied to a specific user_id. Stable per user."""
    import hmac
    import hashlib
    import base64 as _b64
    secret = (UNSUBSCRIBE_SECRET or "fallback-unsub-secret").encode()
    sig = hmac.new(secret, user_id.encode(), hashlib.sha256).digest()
    blob = user_id.encode() + b"." + _b64.urlsafe_b64encode(sig)[:16]
    return _b64.urlsafe_b64encode(blob).decode().rstrip("=")


def _verify_unsubscribe_token(token: str) -> Optional[str]:
    """Return user_id if token is valid, else None."""
    import hmac
    import hashlib
    import base64 as _b64
    try:
        pad = "=" * (-len(token) % 4)
        blob = _b64.urlsafe_b64decode(token + pad)
        user_id_bytes, sig_b64 = blob.rsplit(b".", 1)
        user_id = user_id_bytes.decode()
        secret = (UNSUBSCRIBE_SECRET or "fallback-unsub-secret").encode()
        expected = _b64.urlsafe_b64encode(
            hmac.new(secret, user_id.encode(), hashlib.sha256).digest()
        )[:16]
        if not hmac.compare_digest(sig_b64, expected):
            return None
        return user_id
    except Exception:
        return None


def _unsubscribe_url_for(user_id: str) -> str:
    base = os.environ.get("FRONTEND_URL", "https://aop-app.org").rstrip("/")
    return f"{base}/api/email/unsubscribe?token={_unsubscribe_token(user_id)}"


def _bulk_email_html_footer(unsubscribe_url: str) -> str:
    import html as _h
    addr = _h.escape(ORG_MAILING_ADDRESS)
    return (
        f'<hr style="border:0;border-top:1px solid #e5e7eb;margin:32px 0 16px">'
        f'<div style="font-size:11px;color:#888;line-height:1.6;text-align:center;'
        f'font-family:-apple-system,sans-serif">'
        f'{addr}<br>'
        f'You received this email because you are a member of Alpha Omega Phi. '
        f'<a href="{unsubscribe_url}" style="color:#888;text-decoration:underline">Unsubscribe</a>'
        f'</div>'
    )


def _bulk_email_text_footer(unsubscribe_url: str) -> str:
    return (
        f"\n\n---\n{ORG_MAILING_ADDRESS}\n"
        f"You received this email because you are a member of Alpha Omega Phi.\n"
        f"Unsubscribe: {unsubscribe_url}\n"
    )


def _normalize_email_images(html: str) -> str:
    """Rewrite <img> tags for email-client compatibility:
      • Resolve relative /api/... URLs to absolute (FRONTEND_URL) so the image
        loads outside the app's origin (Gmail/Outlook proxies need absolute).
      • Strip `class=` attributes — email clients (Gmail in particular) drop
        most CSS classes, so any styling must be inline.
      • Ensure inline style sets max-width:100% and height:auto so wide images
        don't blow past the email column width.
    Idempotent: safe to call on already-normalized HTML.
    """
    import re
    if not html:
        return html
    base = (os.environ.get("FRONTEND_URL", "") or "").rstrip("/")

    def fix(match: "re.Match[str]") -> str:
        tag = match.group(0)
        # Absolute URL rewrite (handles single and double quotes)
        if base:
            tag = re.sub(
                r'(src\s*=\s*)(["\'])(/api/[^"\']+)\2',
                lambda m: f'{m.group(1)}{m.group(2)}{base}{m.group(3)}{m.group(2)}',
                tag,
            )
        # Strip class attribute (CSS classes don't work in email clients)
        tag = re.sub(r'\s+class\s*=\s*"[^"]*"', "", tag)
        tag = re.sub(r"\s+class\s*=\s*'[^']*'", "", tag)
        # Ensure responsive sizing inline
        m = re.search(r'style\s*=\s*"([^"]*)"', tag)
        if m:
            existing = m.group(1)
            additions = []
            if "max-width" not in existing:
                additions.append("max-width:100%")
            if "height" not in existing.lower():
                additions.append("height:auto")
            if additions:
                new_style = existing.rstrip(";").strip()
                if new_style:
                    new_style += ";" + ";".join(additions)
                else:
                    new_style = ";".join(additions)
                tag = tag.replace(m.group(0), f'style="{new_style}"')
        else:
            tag = tag.replace(
                "<img",
                '<img style="max-width:100%;height:auto;display:inline-block"',
                1,
            )
        return tag

    return re.sub(r"<img\b[^>]*>", fix, html)


async def send_bulk_email(
    *,
    to_email: str,
    subject: str,
    html_body: str,
    recipient_id: str,
    tags: Optional[List[dict]] = None,
) -> dict:
    """Send a bulk/marketing email with deliverability hygiene:
      - Multipart HTML + auto-derived plain-text fallback
      - Reply-To header
      - List-Unsubscribe + List-Unsubscribe-Post=One-Click headers
      - Precedence: bulk
      - Visible unsubscribe footer + org mailing address (CAN-SPAM)
    """
    if not RESEND_API_KEY:
        return {"ok": False, "skipped": "RESEND_API_KEY not set"}

    unsub_url = _unsubscribe_url_for(recipient_id)
    safe_html = _normalize_email_images(html_body)
    html_full = safe_html + _bulk_email_html_footer(unsub_url)
    text_full = _html_to_text(safe_html) + _bulk_email_text_footer(unsub_url)

    headers = {
        "List-Unsubscribe": f"<{unsub_url}>, <mailto:{RESEND_REPLY_TO}?subject=unsubscribe>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        "Precedence": "bulk",
        "X-Entity-Ref-ID": _unsubscribe_token(recipient_id)[:32],
    }
    params = {
        "from": RESEND_FROM,
        "to": [to_email],
        "reply_to": RESEND_REPLY_TO,
        "subject": subject,
        "html": html_full,
        "text": text_full,
        "headers": headers,
        "tags": tags or [],
    }
    return await asyncio.to_thread(resend_sdk.Emails.send, params)


# ---------- Twilio SMS (graceful no-op if creds absent) ----------
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")
_twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        from twilio.rest import Client as TwilioClient
        _twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info("Twilio SMS client initialized")
    except Exception as e:
        logger.warning(f"Twilio init failed: {e}")
        _twilio_client = None
else:
    logger.info("Twilio SMS disabled (TWILIO_ACCOUNT_SID/TOKEN not set)")


def _normalize_phone_e164(raw: str) -> Optional[str]:
    """Best-effort E.164 normalization for US-default numbers. Returns None if
    we can't make sense of the input. Accepts: '5551234567', '(555) 123-4567',
    '+15551234567', '1-555-123-4567'."""
    if not raw:
        return None
    digits = "".join(c for c in raw if c.isdigit() or c == "+")
    if digits.startswith("+"):
        digits = "+" + "".join(c for c in digits[1:] if c.isdigit())
        return digits if len(digits) >= 9 else None
    bare = "".join(c for c in digits if c.isdigit())
    if len(bare) == 10:
        return f"+1{bare}"
    if len(bare) == 11 and bare.startswith("1"):
        return f"+{bare}"
    return None


async def send_sms(to_phone: str, body: str) -> bool:
    """Send an SMS via Twilio. Returns True on success, False on any failure
    (missing creds, invalid number, Twilio error). Never raises."""
    if not _twilio_client or not TWILIO_FROM_NUMBER:
        return False
    e164 = _normalize_phone_e164(to_phone)
    if not e164:
        return False
    try:
        def _send():
            return _twilio_client.messages.create(to=e164, from_=TWILIO_FROM_NUMBER, body=body[:1500])
        await asyncio.to_thread(_send)
        return True
    except Exception as e:
        logger.warning(f"SMS send failed to {e164}: {e}")
        return False



async def send_welcome_email(to_email: str, name: str, temp_password: str) -> bool:
    """Send a one-shot welcome email to a newly created member containing their
    temporary password and a clear ask to change it on first login. Best-effort —
    failures are logged, never raised."""
    if not RESEND_API_KEY or not to_email:
        return False
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    import html as _h
    safe_name = _h.escape(name or "")
    safe_email = _h.escape(to_email)
    safe_pwd = _h.escape(temp_password)
    body = f"""
    <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:32px;color:#222">
      <h1 style="color:#C8102E;margin:0 0 16px;font-size:28px">Welcome to Alpha Omega Phi, {safe_name}.</h1>
      <p style="line-height:1.6">You've been added to the Alpha Omega Phi Military Fraternity &amp; Sorority, Inc. member portal. Use the temporary password below to sign in, then please change it from your profile.</p>
      <div style="background:#f7f5f0;border-radius:14px;padding:20px;margin:20px 0">
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:#666;margin-bottom:6px">Sign-in details</div>
        <div style="font-size:14px;margin:4px 0"><strong>Email:</strong> {safe_email}</div>
        <div style="font-size:14px;margin:4px 0"><strong>Temporary password:</strong> <code style="background:#fff;padding:3px 8px;border-radius:6px;border:1px solid #ddd">{safe_pwd}</code></div>
      </div>
      <p style="line-height:1.6"><a href="{frontend}/login" style="background:#C8102E;color:#fff;padding:12px 24px;border-radius:999px;text-decoration:none;font-weight:600">Sign in &amp; change your password</a></p>
      <p style="font-size:12px;color:#888;margin-top:24px;line-height:1.6">For security, please change your password the first time you log in (Profile → Security).</p>
    </div>
    """
    try:
        await asyncio.to_thread(resend_sdk.Emails.send, {
            "from": RESEND_FROM,
            "to": [to_email],
            "subject": "Welcome to Alpha Omega Phi — your temporary password",
            "html": body,
            "tags": [{"name": "type", "value": "welcome"}],
        })
        return True
    except Exception as e:
        logger.warning(f"Welcome email failed for {to_email}: {e}")
        return False

_paypal_token_cache = {"token": None, "expires_at": 0.0}

async def paypal_access_token() -> str:
    import time
    now = time.time()
    if _paypal_token_cache["token"] and _paypal_token_cache["expires_at"] > now + 30:
        return _paypal_token_cache["token"]
    if not PAYPAL_CLIENT_ID or not PAYPAL_SECRET:
        raise HTTPException(status_code=503, detail="PayPal not configured")
    async with httpx.AsyncClient(timeout=20) as cx:
        r = await cx.post(
            f"{PAYPAL_BASE}/v1/oauth2/token",
            auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
        )
        if r.status_code != 200:
            logger.error(f"PayPal token error: {r.status_code} {r.text}")
            raise HTTPException(status_code=502, detail="PayPal auth failed")
        data = r.json()
        _paypal_token_cache["token"] = data["access_token"]
        _paypal_token_cache["expires_at"] = now + float(data.get("expires_in", 3000))
        return data["access_token"]


# ---------- PayPal — Public client config ----------
@api.get("/payments/paypal/client-id")
async def paypal_public_config():
    return {
        "client_id": PAYPAL_CLIENT_ID,
        "mode": PAYPAL_MODE,
        "enabled": bool(PAYPAL_CLIENT_ID and PAYPAL_SECRET),
    }


# ---------- PayPal — Create order ----------
class PayPalOrderIn(BaseModel):
    purpose: Literal["donation", "gear", "event", "dues"]
    amount: float = Field(gt=0)
    currency: str = "USD"
    cause_id: Optional[str] = None
    gear_id: Optional[str] = None
    event_id: Optional[str] = None
    quantity: int = 1
    note: str = ""
    anonymous: bool = False
    # Gear variant selections (color/size). Surfaced on receipts so the
    # admin fulfilling the order knows exactly what to ship.
    gear_color: Optional[str] = None
    gear_size: Optional[str] = None

@api.post("/payments/paypal/orders")
async def paypal_create_order(body: PayPalOrderIn, user: dict = Depends(get_current_user)):
    desc = body.note or body.purpose
    if body.purpose == "donation" and body.cause_id:
        c = await db.causes.find_one({"id": body.cause_id}, {"_id": 0})
        if c:
            desc = f"Donation: {c['title']}"
    if body.purpose == "gear" and body.gear_id:
        g = await db.gear.find_one({"id": body.gear_id}, {"_id": 0})
        if g:
            variant_parts = [body.gear_color, body.gear_size]
            variant = " · ".join([v for v in variant_parts if v])
            desc = f"AOP Gear: {g['name']}" + (f" ({variant})" if variant else "") + (f" ×{body.quantity}" if body.quantity > 1 else "")
    if body.purpose == "event" and body.event_id:
        e = await db.events.find_one({"id": body.event_id}, {"_id": 0})
        if e:
            desc = f"Event: {e['title']}"

    token = await paypal_access_token()
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": str(uuid.uuid4()),
            "description": desc[:127],
            "custom_id": f"{body.purpose}:{user['id']}",
            "amount": {"currency_code": body.currency, "value": f"{body.amount:.2f}"},
        }],
        "application_context": {
            "brand_name": "Alpha Omega Phi",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "PAY_NOW",
        },
    }
    async with httpx.AsyncClient(timeout=20) as cx:
        r = await cx.post(
            f"{PAYPAL_BASE}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code not in (200, 201):
            logger.error(f"PayPal create-order failed: {r.status_code} {r.text}")
            raise HTTPException(status_code=502, detail="PayPal order creation failed")
        order = r.json()

    # Persist a pending transaction now (we'll mark completed on capture)
    tx_id = str(uuid.uuid4())
    tx_type = {"donation": "donation", "gear": "gear", "event": "fee", "dues": "renewal"}.get(body.purpose, "fee")
    tx = {
        "id": tx_id,
        "user_id": user["id"],
        "user_name": "Anonymous" if body.anonymous else user.get("name", ""),
        "type": tx_type,
        "amount": float(body.amount),
        "currency": body.currency,
        "description": desc,
        "status": "pending",
        "method": "paypal",
        "paypal_order_id": order["id"],
        "purpose": body.purpose,
        "cause_id": body.cause_id,
        "gear_id": body.gear_id,
        "gear_color": body.gear_color,
        "gear_size": body.gear_size,
        "event_id": body.event_id,
        "quantity": body.quantity,
        "anonymous": body.anonymous,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(tx)
    return {"order_id": order["id"], "transaction_id": tx_id, "status": order.get("status")}


# ---------- PayPal — Capture order ----------
@api.post("/payments/paypal/orders/{order_id}/capture")
async def paypal_capture_order(order_id: str, user: dict = Depends(get_current_user)):
    token = await paypal_access_token()
    async with httpx.AsyncClient(timeout=20) as cx:
        r = await cx.post(
            f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        if r.status_code not in (200, 201):
            logger.error(f"PayPal capture failed: {r.status_code} {r.text}")
            raise HTTPException(status_code=502, detail="PayPal capture failed")
        cap = r.json()

    status_ok = cap.get("status") == "COMPLETED"
    tx = await db.transactions.find_one({"paypal_order_id": order_id, "user_id": user["id"]})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    new_status = "completed" if status_ok else "pending"
    updates = {"status": new_status, "captured_at": iso(now_utc()), "paypal_capture": cap}
    await db.transactions.update_one({"id": tx["id"]}, {"$set": updates})

    if status_ok:
        # Side-effects per purpose
        if tx.get("purpose") == "donation" and tx.get("cause_id"):
            await recompute_cause_totals(tx["cause_id"])
        if tx.get("purpose") == "dues":
            # extend membership by 365 days from current expiry (or now)
            u = await db.users.find_one({"id": user["id"]})
            cur = u.get("membership_expires_at") if u else None
            try:
                base = datetime.fromisoformat(cur) if cur else now_utc()
            except Exception:
                base = now_utc()
            if base < now_utc():
                base = now_utc()
            await db.users.update_one({"id": user["id"]}, {"$set": {"membership_expires_at": iso(base + timedelta(days=365))}})
    return {"transaction_id": tx["id"], "status": new_status, "paypal_status": cap.get("status")}


# ---------- Email Blasts, Templates, Drafts, Unsubscribe, Test-send, Webhook ----------
# Extracted to routes/email.py — registered at the bottom of this file via routes_email.register(...).
# The helpers _normalize_email_images, send_bulk_email, _verify_unsubscribe_token stay here
# (they're shared with chat-digest and automated-emails services).




# ============================================================
# PHASE D — Chat: conversations, messages, file uploads, WebSocket
# Extracted to routes/chat.py (see register call at bottom of file).
# The chat-email-digest service below still imports chat_hub from that module
# to check who is currently connected.
# ============================================================
from fastapi import WebSocket, WebSocketDisconnect, UploadFile, File, Form  # noqa: F401,E402
import jwt as _pyjwt  # noqa: F401,E402
from routes.chat import chat_hub  # noqa: E402 — singleton used by digest service


# ============================================================
# PHASE E — Fixed chapters + Email signatures + Rich email images
# ============================================================

# Canonical AOP chapter list (idempotent reconciliation)
AOP_CHAPTERS = [
    {"name": "Texas", "region": "South", "state": "TX", "description": "Texas chapter."},
    {"name": "Florida", "region": "South", "state": "FL", "description": "Florida chapter."},
    {"name": "Tri-South", "region": "South", "state": "Multi", "description": "Tri-South chapter — covers GA, AL, MS, LA, SC, NC."},
    {"name": "DMV", "region": "Mid-Atlantic", "state": "Multi", "description": "DMV chapter — DC, Maryland, Virginia."},
]

async def reconcile_chapters():
    """Ensure the four canonical AOP chapters exist with the right region/state.
    Existing chapters with names matching AOP_CHAPTERS are updated; others are
    deleted unless they have members assigned (those are kept to preserve refs)."""
    legacy_to_remove = ["Alpha Beta", "Epsilon Theta", "Gamma Delta", "Texas Bravo"]
    for legacy_name in legacy_to_remove:
        legacy = await db.chapters.find_one({"name": legacy_name})
        if not legacy:
            continue
        # Null-out chapter on any members assigned to this legacy chapter
        await db.users.update_many({"chapter_id": legacy["id"]}, {"$unset": {"chapter_id": ""}})
        await db.chapters.delete_one({"id": legacy["id"]})
        logger.info(f"Removed legacy chapter: {legacy_name}")

    for spec in AOP_CHAPTERS:
        existing = await db.chapters.find_one({"name": spec["name"]})
        if existing:
            await db.chapters.update_one(
                {"id": existing["id"]},
                {"$set": {"region": spec["region"], "state": spec["state"], "description": spec["description"]}},
            )
        else:
            doc = {
                **spec,
                "id": str(uuid.uuid4()),
                "school": "",
                "city": "",
                "founded_year": None,
                "created_at": iso(now_utc()),
            }
            await db.chapters.insert_one(doc)


# ---------- AOP canonical Tiers ----------
AOP_TIERS = [
    {"name": "Regular Member", "order": 1, "color": "#22C55E", "annual_dues": 100.0, "is_lifetime": False,
     "description": "Full membership in the Organization."},
    {"name": "Associate Member", "order": 2, "color": "#3B82F6", "annual_dues": 100.0, "is_lifetime": False,
     "description": "Member who has a family member serving or who has served in the military."},
    {"name": "Honorary Member", "order": 3, "color": "#F59E0B", "annual_dues": 100.0, "is_lifetime": False,
     "description": "Member selected by the Founders or National Leadership to be a member due to their dedication. Exempted from Intake."},
    {"name": "Life Member Candidate", "order": 4, "color": "#A855F7", "annual_dues": 100.0, "is_lifetime": False,
     "description": "Active member working toward Life Member status — must accumulate the required years of service. Standard annual dues apply during candidacy."},
    {"name": "Silver Life Member", "order": 5, "color": "#9CA3AF", "annual_dues": 0.0, "is_lifetime": True,
     "description": "Member who served a minimum of four years in the organization and is the elite member of the organization. Lifetime membership — no renewal."},
    {"name": "Gold Life Member", "order": 6, "color": "#D4AF37", "annual_dues": 0.0, "is_lifetime": True,
     "description": "Member who served a minimum of 15 years in the organization and is the elite member of the organization. Lifetime membership — no renewal."},
    {"name": "Founder", "order": 7, "color": "#0A2463", "annual_dues": 0.0, "is_lifetime": True,
     "description": "Founding member of Alpha Omega Phi Military Fraternity & Sorority, Inc. Lifetime membership — no renewal."},
]
AOP_TIER_NAMES = [t["name"] for t in AOP_TIERS]

async def reconcile_tiers():
    """Ensure the canonical AOP tiers exist with up-to-date defaults. Admin-
    added custom tiers (e.g. 'Junior Member') are PRESERVED — we never delete
    non-canonical tiers anymore (Iter 35 fix: previous behavior wiped admin
    tiers on every production deploy)."""
    for spec in AOP_TIERS:
        existing = await db.tiers.find_one({"name": spec["name"]})
        if existing:
            await db.tiers.update_one({"id": existing["id"]}, {"$set": spec})
        else:
            doc = {**spec, "id": str(uuid.uuid4()), "created_at": iso(now_utc())}
            await db.tiers.insert_one(doc)
    # Backfill: ensure existing members on lifetime tiers have is_lifetime_member=true and no expiration.
    lifetime_tiers = await db.tiers.find({"is_lifetime": True}, {"_id": 0, "id": 1}).to_list(20)
    lifetime_tier_ids = [t["id"] for t in lifetime_tiers]
    if lifetime_tier_ids:
        res = await db.users.update_many(
            {"tier_id": {"$in": lifetime_tier_ids}},
            {"$set": {"is_lifetime_member": True, "membership_expires_at": None}},
        )
        if res.modified_count:
            logger.info(f"Backfilled {res.modified_count} lifetime members (cleared expiration)")
    # Inverse: ensure non-lifetime members don't carry a stray is_lifetime_member=true
    non_lifetime_tier_ids = await db.tiers.distinct("id", {"$or": [{"is_lifetime": {"$ne": True}}, {"is_lifetime": {"$exists": False}}]})
    if non_lifetime_tier_ids:
        await db.users.update_many(
            {"tier_id": {"$in": non_lifetime_tier_ids}, "is_lifetime_member": True},
            {"$set": {"is_lifetime_member": False}},
        )


# ---------- AOP canonical Awards ----------
AOP_AWARDS = [
    {"order": 1, "name": "Life Membership Ribbon", "icon": "ribbon", "color": "#9CA3AF",
     "description": "Life Membership Award Ribbon is the highest achievement award in the organization. It is for members who are financially current in paying dues for four consistent years, and have been a significant part of the organization. They are in the top 15% of all members in the organization. These members were nominated by the Founders or designated personnel based on their service in the organization. They completed taskings within one year after their acceptance of becoming a life member, according to the Bylaws. These members are considered the elite members of the organization."},
    {"order": 2, "name": "Founder's Lifetime Achievement Ribbon", "icon": "ribbon", "color": "#D4AF37",
     "description": "The Founder's Award is the second highest achievement award in the organization. It is presented to a member who has been an exceptional leader and positive member of the organization. This member demonstrated an aptitude for, and commitment to professional growth and provided leadership that is impactful, effective, motivational, and consistent. The member encouraged personal and professional development in preparation for future leadership opportunities. The member provided effective and sustained service to AOP and its membership and has significantly enhanced its mission and goals. They made executive decisions that resulted in a positive impact in the organization. This person has made tremendous leaps and bounds to improve the quality of the organization."},
    {"order": 3, "name": "Pauline Tate Dedication Ribbon", "icon": "ribbon", "color": "#C8102E",
     "description": "The Pauline Tate Dedication Award is the third highest award in the organization. It is a special award for a member that goes beyond the call of duty meeting the expectations of the mission. They presented ideas to enhance the progress of the organization. Hard work pays off by the fruit of their labor. They are the member of many tasks and completes them knowing they put their all into it. This person is loyal to the commitment they signed up for. This award is very special to the organization because you can see the desire in their eyes that they want the organization to thrive in society."},
    {"order": 4, "name": "Member's Ribbon", "icon": "ribbon", "color": "#0A2463",
     "description": "The Member's Ribbon is awarded to the member who has been an exceptional leader and positive member of the organization. They provided effective and sustained service to AOP and its membership and has significantly enhanced its mission and goals. The member has also been an active member of the organization and completed their minimum community service hours within the year."},
    {"order": 5, "name": "Recruitment Ribbon", "icon": "ribbon", "color": "#22C55E",
     "description": "The Recruitment Ribbon is awarded to the member who recruited the most members to join the organization within any given year. The recruits must have completed the Intake Course and attended the Induction Ceremony."},
    {"order": 6, "name": "Master Instructor Ribbon", "icon": "ribbon", "color": "#7C3AED",
     "description": "The Master Instructor Ribbon is awarded to the member who instructed 15 or more Intake Courses with a graduation rate of 90% or higher."},
    {"order": 7, "name": "Instructor Ribbon", "icon": "ribbon", "color": "#A78BFA",
     "description": "The Instructor Ribbon is awarded to the member who instructed five (5) or more Intake Courses with a graduation rate of 85% or higher."},
    {"order": 8, "name": "National Leadership Ribbon", "icon": "ribbon", "color": "#1E3A8A",
     "description": "The National Leadership Ribbon is awarded to the members who served actively and honorably in a national leadership position for one term. The positions considered are President, Vice President, Secretary, Treasurer, Directors, or Chiefs."},
    {"order": 9, "name": "State Leadership Ribbon", "icon": "ribbon", "color": "#3B82F6",
     "description": "The State Leadership Ribbon is awarded to the members who served actively and honorably in a state leadership position for one term. The positions considered are Governor, Lieutenant Governor, Secretary, Treasurer, and Manager positions, such as Membership, Community Service, or Marketing."},
    {"order": 10, "name": "Community Service Ribbon", "icon": "ribbon", "color": "#10B981",
     "description": "The Community Service Ribbon is awarded to the members with the most organization-related community service hours in a year."},
    {"order": 11, "name": "Fundraiser Ribbon", "icon": "ribbon", "color": "#F59E0B",
     "description": "The Fundraiser Ribbon is awarded to the member who raised the most money during a National Fundraiser event in any given year."},
    {"order": 12, "name": "Joint Planning Ribbon", "icon": "ribbon", "color": "#06B6D4",
     "description": "The Joint Planning Ribbon is awarded to the members who was part of a committee or board to plan a joint event that involves organizations within the Federation of Military Greek Letter Organizations."},
    {"order": 13, "name": "Organization Planning Ribbon", "icon": "ribbon", "color": "#0891B2",
     "description": "The Organization Planning Ribbon is awarded to the members who was part of a planning committee within the organization to plan a conference or major event."},
    {"order": 14, "name": "Service Ribbon", "icon": "ribbon", "color": "#64748B",
     "description": "The Service Ribbon is awarded to AOP members who have actively served in the organization for one year. Afterwards, the ribbon is awarded for every five (5) years of consecutive service within the organization. There cannot be a break-in-service within the five years."},
    {"order": 15, "name": "Alpha Omega Phi Ribbon", "icon": "ribbon", "color": "#C8102E",
     "description": "The Alpha Omega Phi Ribbon is automatically awarded to members who completed the Intake Course and attended the Induction / Commitment Ceremony."},
    {"order": 16, "name": "Federation Ribbon", "icon": "ribbon", "color": "#A16207",
     "description": "The Federation Participation Ribbon is awarded to AOP members who attended a Federation event."},
]
AOP_AWARD_NAMES = [a["name"] for a in AOP_AWARDS]

async def reconcile_awards():
    """Ensure the canonical AOP-specific Ribbons/Awards exist with up-to-date
    descriptions. Admin-added custom awards (and their grants) are PRESERVED —
    we never delete non-canonical awards anymore (Iter 35 fix: previous behavior
    wiped admin-added awards + their grants on every production deploy)."""
    for spec in AOP_AWARDS:
        existing = await db.awards.find_one({"name": spec["name"]})
        if existing:
            await db.awards.update_one({"id": existing["id"]}, {"$set": spec})
        else:
            doc = {**spec, "id": str(uuid.uuid4()), "created_at": iso(now_utc())}
            await db.awards.insert_one(doc)


# ---------- 10-Year Anniversary umbrella event + 5 sub-events ----------
ANNIVERSARY_PARENT_TITLE = "Alpha Omega Phi 10-Year Anniversary"
# Per user: 29-31 July 2027.
# Day 1 (29 Jul): Transportation Buses to Sip and Paint, Sip and Paint
# Day 2 (30 Jul): Banquet
# Day 3 (31 Jul): Transportation Buses to Top Golf, Top Golf
ANNIVERSARY_START = datetime(2027, 7, 29, 0, 0, 0, tzinfo=timezone.utc)
ANNIVERSARY_END = datetime(2027, 7, 31, 23, 59, 59, tzinfo=timezone.utc)
ANNIVERSARY_SUB_EVENTS = [
    {"title": "Transportation to Sip & Paint", "category": "transportation", "allows_ticket_types": True, "day_offset": 0, "hour": 16},
    {"title": "Sip & Paint",                   "category": "social",         "allows_ticket_types": True, "day_offset": 0, "hour": 18},
    {"title": "Sneaker Ball Banquet",          "category": "formal",         "allows_ticket_types": True, "day_offset": 1, "hour": 18},
    {"title": "Transportation to Top Golf",    "category": "transportation", "allows_ticket_types": True, "day_offset": 2, "hour": 11},
    {"title": "Top Golf",                      "category": "social",         "allows_ticket_types": True, "day_offset": 2, "hour": 13},
]
# Legacy titles that the seeder needs to clean up if they still exist from earlier names.
ANNIVERSARY_LEGACY_TITLES = {
    "Transportation Buses to Sip and Paint",
    "Sip and Paint",
    "Banquet",
    "Transportation Buses to Top Golf",
}
ANNIVERSARY_ALLOWED_TITLES = {ANNIVERSARY_PARENT_TITLE, *(s["title"] for s in ANNIVERSARY_SUB_EVENTS)}

async def seed_anniversary_subevents():
    """Reconcile the 10-Year Anniversary umbrella (29-31 July 2027) and its 5 sub-events.
    - Parent event blocks all three days (start 29 Jul, end 31 Jul).
    - Sub-events are placed on their assigned days (29 / 30 / 31 July).
    - Any anniversary-titled event that is NOT in the canonical list is removed.
    - Existing parent/sub events are updated (idempotent re-run on every startup)."""
    parent = await db.events.find_one({"title": ANNIVERSARY_PARENT_TITLE})
    parent_updates = {
        "description": "Three-day 10-year anniversary celebration for Alpha Omega Phi Military Fraternity & Sorority, Inc. — Sip & Paint, Banquet, Top Golf and transportation, 29-31 July 2027.",
        "location": "Multiple venues",
        "start_at": iso(ANNIVERSARY_START),
        "end_at": iso(ANNIVERSARY_END),
        "category": "anniversary",
        "parent_event_id": None,
        "allows_ticket_types": False,
    }
    if not parent:
        parent_doc = {
            "id": str(uuid.uuid4()),
            "title": ANNIVERSARY_PARENT_TITLE,
            **parent_updates,
            "capacity": 0,
            "cover_image": "",
            "price": 0.0,
            "rsvp_count": 0,
            "guest_count": 0,
            "created_at": iso(now_utc()),
        }
        await db.events.insert_one(parent_doc)
        parent = parent_doc
        logger.info("Seeded 10-Year Anniversary parent event (29-31 Jul 2027)")
    else:
        await db.events.update_one({"id": parent["id"]}, {"$set": parent_updates})

    # Reconcile sub-events: insert missing, update existing.
    for spec in ANNIVERSARY_SUB_EVENTS:
        sub_start = ANNIVERSARY_START.replace(hour=spec["hour"]) + timedelta(days=spec["day_offset"])
        sub_end = sub_start + timedelta(hours=3)
        sub_updates = {
            "title": spec["title"],
            "description": f"Part of the {ANNIVERSARY_PARENT_TITLE} — 29-31 July 2027.",
            "location": "TBD",
            "start_at": iso(sub_start),
            "end_at": iso(sub_end),
            "category": spec["category"],
            "parent_event_id": parent["id"],
            "allows_ticket_types": spec["allows_ticket_types"],
        }
        existing = await db.events.find_one({"title": spec["title"], "parent_event_id": parent["id"]})
        if existing:
            await db.events.update_one({"id": existing["id"]}, {"$set": sub_updates})
        else:
            doc = {
                "id": str(uuid.uuid4()),
                **sub_updates,
                "capacity": 0,
                "cover_image": "",
                "price": 0.0,
                "rsvp_count": 0,
                "guest_count": 0,
                "created_at": iso(now_utc()),
            }
            await db.events.insert_one(doc)
            logger.info(f"Seeded sub-event: {spec['title']} ({sub_start.date()})")

    # NOTE: This function used to also DELETE any "stale anniversary event" and
    # WIPE all non-anniversary events from the events collection on every startup.
    # That destroyed admin-created events on every production deploy and has been
    # removed (Iter 35). Admin can delete unwanted events from the UI.


# ---------- Email Signatures + inline image upload ----------
# Extracted to routes/email.py.




# ---------- Avatar upload (member self-service) ----------
@api.post("/members/me/avatar")
async def upload_my_avatar(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Member uploads a new avatar from their phone/laptop or camera capture.
    Stores in object storage, registers in chat_files (so /api/files/ resolves it),
    and persists the new URL on the user record."""
    chunks: list = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Avatar must be under 10 MB")
        chunks.append(chunk)
    data = b"".join(chunks)
    fname = (file.filename or "avatar.jpg").replace("/", "_")
    ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
    if ext not in IMAGE_EXT:
        raise HTTPException(status_code=400, detail="Only images allowed (jpg, png, gif, webp)")
    content_type = file.content_type or MIME_BY_EXT.get(ext, "image/jpeg")
    file_id = str(uuid.uuid4())
    storage_path = f"avatars/{user['id']}/{file_id}/{fname}"

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
    avatar_url = f"/api/files/{storage_path}"
    await db.users.update_one({"id": user["id"]}, {"$set": {"avatar_url": avatar_url}})
    return {"avatar_url": avatar_url, "size": total}


# ============================================================
# Chat email digest service — extracted to routes/chat_digest.py.
# This stub re-exports the queue helper so legacy callsites + routes/chat.py
# continue to work via the same import path.
# ============================================================
from routes.chat_digest import (  # noqa: E402,F401 — re-exported for legacy callsites
    queue_chat_notifications,
    CHAT_DIGEST_DELAY_SECONDS,
)



# ============================================================
# Automated Emails — extracted to routes/automated_emails.py.
# That module owns the campaigns CRUD, dues-reminder cadence, admin
# dues-summary digest, and the 5-minute background runner.
# Seed + loop hooks are wired up in startup() further below.
# ============================================================

# (legacy placeholder so subsequent code keeps its line ranges roughly stable)
_AUTOMATED_SECTIONS_LEGACY_MARKER = True


async def _auto_inactive_loop():
    """Once an hour, find members whose grace period has fully elapsed and flip
    them to `status_override="inactive"`. Lifetime members and already-inactive
    members are skipped. The check runs hourly (not daily) so a member who's
    14 days past expiration in the morning flips to inactive on day 15 within
    the hour — keeps the user experience honest about the deadline."""
    while True:
        try:
            cutoff_iso = iso(now_utc() - timedelta(days=GRACE_PERIOD_DAYS))
            q = {
                "is_lifetime_member": {"$ne": True},
                "membership_expires_at": {"$lt": cutoff_iso, "$exists": True, "$nin": [None, ""]},
                "status_override": {"$nin": ["inactive", "deceased"]},
            }
            result = await db.users.update_many(
                q,
                {"$set": {"status_override": "inactive", "auto_inactivated_at": iso(now_utc())}},
            )
            if result.modified_count:
                logger.info(f"[auto-inactive] flipped {result.modified_count} member(s) to inactive (15-day grace elapsed)")
        except Exception as e:
            logger.warning(f"Auto-inactive loop error: {e}")
        await asyncio.sleep(3600)


# ---------- Built-in starter email templates ----------
# Now lives in routes/email.py (BUILTIN_EMAIL_TEMPLATES + seed_builtin_email_templates).
# The startup hook in this file calls routes_email.seed_builtin_email_templates(db, iso, now_utc, logger).







# ---------- Register extracted route modules (must come before include_router) ----------
from routes import pages as routes_pages  # noqa: E402
from routes import site_settings as routes_site_settings  # noqa: E402
from routes import ai as routes_ai  # noqa: E402
from routes import news as routes_news  # noqa: E402
from routes import chapters as routes_chapters  # noqa: E402
from routes import tiers as routes_tiers  # noqa: E402
from routes import payments as routes_payments  # noqa: E402
from routes import auth as routes_auth  # noqa: E402
from routes import auth_email_flows as routes_auth_email_flows  # noqa: E402
from routes import events as routes_events  # noqa: E402
from routes import photos as routes_photos  # noqa: E402
from routes import documents as routes_documents  # noqa: E402
from routes import members as routes_members  # noqa: E402
from routes import applications as routes_applications  # noqa: E402
from routes import hours as routes_hours  # noqa: E402
from routes import reports as routes_reports  # noqa: E402
from routes import rsvps as routes_rsvps  # noqa: E402
from routes import gear as routes_gear  # noqa: E402
from routes import chat as routes_chat  # noqa: E402
from routes import donations as routes_donations  # noqa: E402
from routes import awards as routes_awards  # noqa: E402
from routes import email as routes_email  # noqa: E402

routes_pages.register(api, db=db, admin_tab_dep=admin_tab_dep, iso=iso, now_utc=now_utc)
routes_site_settings.register(api, db=db, admin_tab_dep=admin_tab_dep, iso=iso, now_utc=now_utc)
routes_ai.register(api, require_admin=require_admin)
routes_news.register(api, db=db, admin_tab_dep=admin_tab_dep, iso=iso, now_utc=now_utc)
routes_chapters.register(api, db=db, admin_tab_dep=admin_tab_dep, iso=iso, now_utc=now_utc)
routes_tiers.register(api, db=db, admin_tab_dep=admin_tab_dep)
routes_gear.register(
    api,
    db=db,
    admin_tab_dep=admin_tab_dep,
    iso=iso,
    now_utc=now_utc,
    put_object=put_object,
    image_ext=IMAGE_EXT,
    mime_by_ext=MIME_BY_EXT,
)
routes_chat.register(
    api,
    app,
    db=db,
    iso=iso,
    now_utc=now_utc,
    get_current_user=get_current_user,
    jwt_secret=jwt_secret,
    JWT_ALGORITHM=JWT_ALGORITHM,
    queue_chat_notifications=queue_chat_notifications,
    put_object=put_object,
    image_ext=IMAGE_EXT,
    mime_by_ext=MIME_BY_EXT,
    logger=logger,
)
routes_donations.register(
    api,
    db=db,
    iso=iso,
    now_utc=now_utc,
    get_current_user=get_current_user,
    admin_tab_dep=admin_tab_dep,
    is_chapter_scoped=is_chapter_scoped,
    chapter_scope_user_ids=chapter_scope_user_ids,
)
routes_awards.register(
    api,
    db=db,
    admin_tab_dep=admin_tab_dep,
    get_current_user=get_current_user,
    iso=iso,
    now_utc=now_utc,
)
routes_email.register(
    api,
    db=db,
    iso=iso,
    now_utc=now_utc,
    logger=logger,
    admin_tab_dep=admin_tab_dep,
    get_current_user=get_current_user,
    resend_sdk=resend_sdk,
    resend_api_key=RESEND_API_KEY,
    resend_from=RESEND_FROM,
    resend_reply_to=RESEND_REPLY_TO,
    org_mailing_address=ORG_MAILING_ADDRESS,
    send_bulk_email=send_bulk_email,
    normalize_email_images=_normalize_email_images,
    verify_unsubscribe_token=_verify_unsubscribe_token,
    put_object=put_object,
    image_extensions=IMAGE_EXT,
    mime_by_ext=MIME_BY_EXT,
)

# Automated email campaigns (broadcast + dues-reminder cadence). The seed +
# loop hooks attached to register.* are invoked from startup().
from routes import automated_emails as routes_automated_emails  # noqa: E402
routes_automated_emails.register(
    api,
    db=db,
    admin_tab_dep=admin_tab_dep,
    iso=iso,
    now_utc=now_utc,
    logger=logger,
    resend_sdk=resend_sdk,
    resend_api_key=RESEND_API_KEY,
    resend_from=RESEND_FROM,
    resend_reply_to=RESEND_REPLY_TO,
    send_bulk_email=send_bulk_email,
)
routes_payments.register(
    api,
    db=db,
    get_current_user=get_current_user,
    require_admin=require_admin,
    is_chapter_scoped=is_chapter_scoped,
    chapter_scope_user_ids=chapter_scope_user_ids,
    iso=iso,
    now_utc=now_utc,
)
routes_auth.register(
    api,
    db=db,
    get_current_user=get_current_user,
    hash_password=hash_password,
    verify_password=verify_password,
    create_access_token=create_access_token,
    create_refresh_token=create_refresh_token,
    set_auth_cookies=set_auth_cookies,
    clear_auth_cookies=clear_auth_cookies,
    public_user=public_user,
    jwt_secret=jwt_secret,
    JWT_ALGORITHM=JWT_ALGORITHM,
    iso=iso,
    now_utc=now_utc,
)

# Patch the back-compat _ensure_site_settings shim to delegate to the route module
_ensure_site_settings = routes_site_settings.register.ensure

routes_auth_email_flows.register(
    api,
    db=db,
    iso=iso,
    now_utc=now_utc,
    hash_password=hash_password,
    verify_password=verify_password,
    get_current_user=get_current_user,
    resend_sdk=resend_sdk,
    resend_api_key=RESEND_API_KEY,
    resend_from=RESEND_FROM,
    logger=logger,
)
# Wire the back-compat _send_set_password_email shim to the extracted helper so
# bulk-import + apply-approval + resend-link paths keep working.
_send_set_password_email._impl = routes_auth_email_flows.register.send_set_password_email

routes_events.register(api, db=db, admin_tab_dep=admin_tab_dep, event_out=event_out, iso=iso, now_utc=now_utc, resend_sdk=resend_sdk, resend_api_key=RESEND_API_KEY, resend_from=RESEND_FROM, logger=logger)
routes_photos.register(
    api,
    db=db,
    get_current_user=get_current_user,
    photo_out=photo_out,
    put_object=put_object,
    get_object=get_object,
    iso=iso,
    now_utc=now_utc,
    logger=logger,
    image_ext=IMAGE_EXT,
    mime_by_ext=MIME_BY_EXT,
    app_name=APP_NAME,
    photo_album_categories=PHOTO_ALBUM_CATEGORIES,
    auto_categorize_album=auto_categorize_album,
)
routes_documents.register(
    api,
    db=db,
    get_current_user=get_current_user,
    admin_tab_dep=admin_tab_dep,
    put_object=put_object,
    iso=iso,
    now_utc=now_utc,
    logger=logger,
    doc_ext=DOC_EXT,
    image_ext=IMAGE_EXT,
    mime_by_ext=MIME_BY_EXT,
    app_name=APP_NAME,
)
routes_members.register(api, db=db, admin_tab_dep=admin_tab_dep, public_user=public_user, iso=iso, now_utc=now_utc)
routes_applications.register(
    api,
    db=db,
    admin_tab_dep=admin_tab_dep,
    iso=iso,
    now_utc=now_utc,
    hash_password=hash_password,
    resend_sdk=resend_sdk,
    resend_api_key=RESEND_API_KEY,
    resend_from=RESEND_FROM,
    logger=logger,
)
routes_hours.register(
    api,
    db=db,
    admin_tab_dep=admin_tab_dep,
    require_admin=require_admin,
    get_current_user=get_current_user,
    hours_out=hours_out,
    is_chapter_scoped=is_chapter_scoped,
    chapter_scope_user_ids=chapter_scope_user_ids,
    period_to_range=_period_to_range,
    iso=iso,
    now_utc=now_utc,
)
routes_reports.register(
    api,
    db=db,
    admin_tab_dep=admin_tab_dep,
    get_current_user=get_current_user,
    public_user=public_user,
    hours_out=hours_out,
    tier_out=tier_out,
    chapter_out=chapter_out,
    is_chapter_scoped=is_chapter_scoped,
    chapter_scope_user_ids=chapter_scope_user_ids,
    period_to_range=_period_to_range,
    get_object=get_object,
    iso=iso,
    now_utc=now_utc,
    logger=logger,
)
# Wire back-compat helper shims used by /me/personnel-brief* in server.py.
_personnel_brief_data._impl = routes_reports.register.personnel_brief_data
_personnel_brief_pdf_response._impl = routes_reports.register.personnel_brief_pdf_response

routes_rsvps.register(
    api,
    db=db,
    get_current_user=get_current_user,
    require_admin=require_admin,
    event_out=event_out,
    iso=iso,
    now_utc=now_utc,
    resend_sdk=resend_sdk,
    resend_api_key=RESEND_API_KEY,
    resend_from=RESEND_FROM,
    jwt_secret=jwt_secret,
    jwt_algorithm=JWT_ALGORITHM,
    logger=logger,
)

# Sub-modules of rsvps. They consume helpers exposed on routes_rsvps.register
# (ensure_not_cancelled, create_rsvp_and_email_ticket, decode_ticket_token) —
# kept in the parent module to avoid duplicating the QR / email pipeline.
from routes import rsvps_csv as routes_rsvps_csv  # noqa: E402
from routes import checkin as routes_checkin  # noqa: E402
routes_rsvps_csv.register(
    api,
    db=db,
    get_current_user=get_current_user,
    iso=iso,
    now_utc=now_utc,
    ensure_not_cancelled=routes_rsvps.register.ensure_not_cancelled,
    create_rsvp_and_email_ticket=routes_rsvps.register.create_rsvp_and_email_ticket,
)
routes_checkin.register(
    api,
    db=db,
    get_current_user=get_current_user,
    event_out=event_out,
    iso=iso,
    now_utc=now_utc,
    decode_ticket_token=routes_rsvps.register.decode_ticket_token,
)

from routes import of_the_year as routes_of_the_year  # noqa: E402
routes_of_the_year.register(
    api,
    db=db,
    admin_tab_dep=admin_tab_dep,
    get_current_user=get_current_user,
    iso=iso,
    now_utc=now_utc,
    logger=logger,
)

from routes import balances as routes_balances  # noqa: E402
routes_balances.register(
    api,
    db=db,
    get_current_user=get_current_user,
    admin_tab_dep=admin_tab_dep,
    require_admin=require_admin,
    iso=iso,
    now_utc=now_utc,
)


# ---------- /leaderboards/community-service ----------
# Restored after the server.py refactor. Returns top 5 chapters + top 5 members
# by approved volunteer hours for the requested period.
@api.get("/leaderboards/community-service")
async def leaderboard_community_service(period: str = "quarter", user: dict = Depends(get_current_user)):
    """period ∈ {quarter, month, year, all}. Returns:
      {period, period_label, top_chapters: [...top 5], top_members: [...top 5]}"""
    now = now_utc()
    start_iso: Optional[str] = None
    if period == "quarter":
        q = (now.month - 1) // 3
        q_start = now.replace(month=q * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        start_iso = iso(q_start)
        period_label = f"Q{q + 1} {now.year}"
    elif period == "month":
        start_iso = iso(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
        period_label = now.strftime("%B %Y")
    elif period == "year":
        start_iso = iso(now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0))
        period_label = str(now.year)
    else:
        period = "all"
        period_label = "All time"

    match: dict = {"status": "approved"}
    if start_iso:
        match["date"] = {"$gte": start_iso}

    # ---- Top members ----
    member_pipe = [
        {"$match": match},
        {"$group": {"_id": "$user_id", "hours": {"$sum": "$hours"}, "count": {"$sum": 1}}},
        {"$sort": {"hours": -1}},
        {"$limit": 5},
    ]
    member_rows = []
    async for r in db.volunteer_hours.aggregate(member_pipe):
        member_rows.append({"user_id": r["_id"], "hours": float(r["hours"] or 0), "count": int(r["count"] or 0)})
    # Enrich with name / avatar / chapter
    uids = [r["user_id"] for r in member_rows if r["user_id"]]
    users: dict = {}
    if uids:
        async for u in db.users.find(
            {"id": {"$in": uids}},
            {"_id": 0, "id": 1, "name": 1, "avatar_url": 1, "chapter_id": 1},
        ):
            users[u["id"]] = u
    top_members = []
    for r in member_rows:
        u = users.get(r["user_id"]) or {}
        top_members.append({
            **r,
            "user_name": u.get("name", "Unknown"),
            "avatar_url": u.get("avatar_url"),
            "chapter_id": u.get("chapter_id"),
            "chapter_name": None,  # filled below
        })

    # ---- Top chapters ----
    chapter_pipe = [
        {"$match": match},
        {"$lookup": {"from": "users", "localField": "user_id", "foreignField": "id", "as": "u"}},
        {"$addFields": {"chapter_id": {"$arrayElemAt": ["$u.chapter_id", 0]}}},
        {"$group": {"_id": "$chapter_id", "hours": {"$sum": "$hours"}, "count": {"$sum": 1}}},
        {"$sort": {"hours": -1}},
        {"$limit": 5},
    ]
    chapter_rows = []
    async for r in db.volunteer_hours.aggregate(chapter_pipe):
        chapter_rows.append({"chapter_id": r["_id"], "hours": float(r["hours"] or 0), "count": int(r["count"] or 0)})
    # Enrich with chapter name + active member count
    cids = [r["chapter_id"] for r in chapter_rows if r["chapter_id"]]
    chapters: dict = {}
    if cids:
        async for c in db.chapters.find({"id": {"$in": cids}}, {"_id": 0, "id": 1, "name": 1, "logo_url": 1}):
            chapters[c["id"]] = c
        # Bulk member counts via aggregation — one pass instead of N queries.
        active_counts = {}
        async for row in db.users.aggregate([
            {"$match": {"chapter_id": {"$in": cids}, "status": {"$ne": "inactive"}}},
            {"$group": {"_id": "$chapter_id", "n": {"$sum": 1}}},
        ]):
            active_counts[row["_id"]] = row["n"]
    else:
        active_counts = {}
    top_chapters = []
    for r in chapter_rows:
        c = chapters.get(r["chapter_id"]) or {}
        top_chapters.append({
            **r,
            "chapter_name": c.get("name") or "Unassigned",
            "logo_url": c.get("logo_url") or None,
            "member_count": int(active_counts.get(r["chapter_id"], 0)),
        })
    # Backfill chapter_name + logo on top_members
    if top_members:
        more_cids = [m["chapter_id"] for m in top_members if m.get("chapter_id") and m["chapter_id"] not in chapters]
        if more_cids:
            async for c in db.chapters.find({"id": {"$in": more_cids}}, {"_id": 0, "id": 1, "name": 1, "logo_url": 1}):
                chapters[c["id"]] = c
        for m in top_members:
            m["chapter_name"] = (chapters.get(m.get("chapter_id") or "") or {}).get("name") or "Unassigned"

    return {
        "period": period,
        "period_label": period_label,
        "top_chapters": top_chapters,
        "top_members": top_members,
    }


# ---------- Mount ----------
app.include_router(api)


# ---------- Health probe (Kubernetes liveness/readiness) ----------
@app.get("/health")
async def health():
    """Lightweight health check for the Kubernetes liveness/readiness probes.
    Returns 200 OK as long as the app process is up. Avoids hitting the DB so
    a transient Mongo blip doesn't kill the pod."""
    return {"status": "ok"}

_cors_origins_raw = os.environ.get("CORS_ORIGINS", "*").strip()
_cors_kwargs = {"allow_credentials": True, "allow_methods": ["*"], "allow_headers": ["*"]}
if _cors_origins_raw == "*":
    _cors_kwargs["allow_origin_regex"] = ".*"
else:
    _cors_kwargs["allow_origins"] = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(CORSMiddleware, **_cors_kwargs)


# ---------- Inactive-member API guard ----------
# When a member's status is "inactive" (manually set, or auto-flipped 15 days
# after dues expiry by `_auto_inactive_loop`), they should only be able to
# touch the Home page + their own Profile. The frontend hides nav links, but
# we also enforce here so a curl/script can't reach the rest of the API.
#
# Allow-listed paths cover: auth (login/logout/refresh), the calling user's
# own profile + email prefs, public reads needed to render Home (chapters,
# news, causes list, recent photos public feed), unsubscribe links, and the
# inline file fetch used by avatars/profile photos.
INACTIVE_ALLOWED_PREFIXES = (
    "/api/auth/",            # login, logout, refresh, /me
    "/api/me/",              # own profile, email prefs
    "/api/files/",           # served images (avatars on Home / Profile)
    "/api/photos/",          # photo gallery — public read
    "/api/news",             # Home news feed
    "/api/chapters",         # Home chapter list
    "/api/causes",           # Home & Profile may reference cause titles
    "/api/email/unsubscribe", # public token-signed link
    "/api/email/resubscribe",
    "/api/email/unsubscribe-status",
    "/api/health",           # liveness / version
)
INACTIVE_ALLOWED_EXACT = {
    "/api/auth/me",
    "/api/auth/logout",
    "/api/me",
}


def _is_path_allowed_for_inactive(path: str) -> bool:
    if path in INACTIVE_ALLOWED_EXACT:
        return True
    return any(path.startswith(p) for p in INACTIVE_ALLOWED_PREFIXES)


@app.middleware("http")
async def block_inactive_member_writes(request: Request, call_next):
    """Reject API calls from members whose status is `inactive` for any path
    outside the Home + Profile allow-list. Always lets non-API requests through
    (those are static asset serves), and never blocks admins."""
    path = request.url.path
    # Fast-path: anything that isn't /api/* is the React bundle / static files.
    if not path.startswith("/api/"):
        return await call_next(request)
    # Allow-listed paths never trigger a token lookup — keeps unauthenticated
    # public endpoints (login, public causes) cheap.
    if _is_path_allowed_for_inactive(path):
        return await call_next(request)
    # Peek at the access token without raising — unauthenticated requests stay
    # unaffected (their handler returns the appropriate 401).
    token = request.cookies.get("access_token") or ""
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        return await call_next(request)
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
        user_id = payload.get("sub")
        if not user_id:
            return await call_next(request)
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "role": 1, "status_override": 1})
        if not u:
            return await call_next(request)
        if u.get("role") == "admin":  # admins are never blocked
            return await call_next(request)
        if u.get("status_override") == "inactive":
            return JSONResponse(
                status_code=403,
                content={"detail": "Your membership is inactive. Please contact a chapter officer to restore access."},
            )
    except Exception:
        # Any decode failure: defer to the normal auth flow.
        pass
    return await call_next(request)


@app.on_event("shutdown")
async def shutdown():
    client.close()
