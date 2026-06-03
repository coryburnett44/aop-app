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
from typing import List, Optional, Literal, Dict

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response, status, UploadFile, File, Form, Header, Query
from fastapi.responses import Response as FastResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict

# ---------- Config ----------
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60 * 24  # 1 day (simpler UX for demo)
REFRESH_TOKEN_DAYS = 7
GRACE_PERIOD_DAYS = 30
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
        "first_name": u.get("first_name", ""),
        "middle_name": u.get("middle_name", ""),
        "last_name": u.get("last_name", ""),
        "line_name": u.get("line_name", ""),
        "intake_line": u.get("intake_line", ""),
        "intake_completed_at": u.get("intake_completed_at", ""),
        "role": u.get("role", "member"),
        "admin_role": u.get("admin_role", "full") if u.get("role") == "admin" else None,
        "bio": u.get("bio", ""),
        "city": u.get("city", ""),
        "phone": u.get("phone", ""),
        "address": u.get("address", ""),
        "state": u.get("state", ""),
        "zip_code": u.get("zip_code", ""),
        "country": u.get("country", ""),
        "chat_email_notifications": u.get("chat_email_notifications", True),
        "chat_sms_notifications": u.get("chat_sms_notifications", True),
        "birthdate": u.get("birthdate", ""),
        "branch_of_service": u.get("branch_of_service", ""),
        "join_date": u.get("join_date") or u.get("created_at"),
        "deceased_at": u.get("deceased_at"),
        "status": status,
        "status_override": u.get("status_override"),
        "interests": u.get("interests", []),
        "avatar_url": u.get("avatar_url", ""),
        "membership_tier": u.get("membership_tier", "standard"),
        "tier_id": u.get("tier_id"),
        "is_lifetime_member": is_lifetime,
        "chapter_id": u.get("chapter_id"),
        "membership_expires_at": None if is_lifetime else u.get("membership_expires_at"),
        "is_expired": is_expired,
        "within_grace": within_grace,
        "email_verified": u.get("email_verified", False),
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

def admin_role_of(u: dict) -> str:
    return (u.get("admin_role") or "full") if u.get("role") == "admin" else ""

def admin_can(user: dict, tab: str) -> bool:
    role = admin_role_of(user)
    return tab in ADMIN_ROLE_TABS.get(role, set())

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
        "tabs": sorted(ADMIN_ROLE_TABS.get(role, set())),
        "chapter_scoped": role == "governor_manager",
        "scoped_chapter_id": user.get("chapter_id") if role == "governor_manager" else None,
    }

# ---------- Models ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1)
    city: Optional[str] = ""
    interests: Optional[List[str]] = []

class PublicApplicationIn(BaseModel):
    """Open-registration application form. Applicant chooses their own password
    up-front; on admin approval, the password is set on the new user account and
    a 'you're approved' email is sent so they can sign in directly."""
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    line_name: str = ""
    intake_line: str = ""
    intake_completed_at: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    country: str = ""

class ApplicationReviewIn(BaseModel):
    action: Literal["approve", "reject"]
    note: Optional[str] = ""

class SetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ProfileUpdateIn(BaseModel):
    name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    line_name: Optional[str] = None
    intake_line: Optional[str] = None
    intake_completed_at: Optional[str] = None
    username: Optional[str] = None
    bio: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    birthdate: Optional[str] = None
    branch_of_service: Optional[str] = None
    interests: Optional[List[str]] = None
    avatar_url: Optional[str] = None
    chat_email_notifications: Optional[bool] = None
    chat_sms_notifications: Optional[bool] = None
    # Social-media handles / URLs (members can update freely)
    facebook_url: Optional[str] = None
    instagram_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    twitter_url: Optional[str] = None
    pinterest_url: Optional[str] = None
    youtube_url: Optional[str] = None
    website_url: Optional[str] = None


class StatusOverrideIn(BaseModel):
    status: Optional[Literal["active", "inactive", "grace", "expired", "deceased"]] = None
    deceased_at: Optional[str] = None

class ChapterIn(BaseModel):
    name: str
    state: str = ""
    region: str = ""
    # legacy aliases
    school: str = ""
    city: str = ""
    founded_year: Optional[int] = None
    description: str = ""
    logo_url: str = ""

class ChapterUpdateIn(BaseModel):
    name: Optional[str] = None
    state: Optional[str] = None
    region: Optional[str] = None
    school: Optional[str] = None
    city: Optional[str] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None

class HoursLogIn(BaseModel):
    hours: float = Field(gt=0, le=1000)
    activity: str = Field(min_length=2)
    date: datetime
    event_type: Literal["aop_related", "other"] = "other"
    agency_name: str = Field(min_length=1)
    host_name: str = Field(min_length=1)
    host_email: EmailStr
    host_phone: str = Field(min_length=4)
    event_id: Optional[str] = None
    # legacy
    description: Optional[str] = None

class AwardGrantIn(BaseModel):
    user_id: str
    reason: str = ""
    granted_at: Optional[str] = None

class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)

class AdminCreateMemberIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    name: Optional[str] = None
    line_name: str = ""
    intake_line: str = ""
    intake_completed_at: str = ""
    username: str = ""
    phone: str = ""
    city: str = ""
    address: str = ""
    state: str = ""
    zip_code: str = ""
    country: str = ""
    birthdate: str = ""
    branch_of_service: str = ""
    role: Literal["member", "admin"] = "member"
    admin_role: Optional[Literal["full", "membership_manager", "operations_manager", "governor_manager"]] = None
    chapter_id: Optional[str] = None
    tier_id: Optional[str] = None
    member_status: Optional[Literal["active", "inactive", "grace", "expired", "deceased"]] = None
    join_date: Optional[datetime] = None

class AdminUpdateMemberIn(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    line_name: Optional[str] = None
    intake_line: Optional[str] = None
    intake_completed_at: Optional[str] = None
    username: Optional[str] = None
    bio: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    birthdate: Optional[str] = None
    branch_of_service: Optional[str] = None
    interests: Optional[List[str]] = None
    avatar_url: Optional[str] = None
    role: Optional[Literal["member", "admin"]] = None
    admin_role: Optional[Literal["full", "membership_manager", "operations_manager", "governor_manager"]] = None
    chapter_id: Optional[str] = None
    tier_id: Optional[str] = None
    membership_expires_at: Optional[datetime] = None
    join_date: Optional[datetime] = None
    member_status: Optional[Literal["active", "inactive", "grace", "expired", "deceased"]] = None
    deceased_at: Optional[str] = None
    new_password: Optional[str] = None

class TransactionIn(BaseModel):
    user_id: str
    type: Literal["renewal", "donation", "credit", "fee", "adjustment"]
    amount: float
    currency: str = "USD"
    description: str = ""
    status: Literal["completed", "pending", "refunded"] = "completed"

class EventIn(BaseModel):
    title: str
    description: str = ""
    location: str = ""
    start_at: datetime
    end_at: Optional[datetime] = None
    capacity: int = 0
    cover_image: str = ""
    category: str = "general"
    price: float = 0.0
    parent_event_id: Optional[str] = None
    allows_ticket_types: bool = False  # if True, admins can assign vip/all_access/general

class EventUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    capacity: Optional[int] = None
    cover_image: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    parent_event_id: Optional[str] = None
    allows_ticket_types: Optional[bool] = None

TicketType = Literal["vip", "all_access", "general", "guest", "speaker", "volunteer"]

class GuestIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: Optional[str] = ""
    phone: Optional[str] = ""
    ticket_type: Optional[TicketType] = "general"

class EventRsvpIn(BaseModel):
    guests: List[GuestIn] = []  # optional: register guests alongside
    ticket_type: Optional[TicketType] = "general"  # ticket type for the member themselves

class NewsIn(BaseModel):
    title: str
    summary: str = ""
    body: str
    cover_image: str = ""
    tags: List[str] = []

class NewsUpdateIn(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    cover_image: Optional[str] = None
    tags: Optional[List[str]] = None

class PageIn(BaseModel):
    slug: str
    title: str
    body: str

class PageUpdateIn(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None

class AIEventReq(BaseModel):
    title: str
    topic: str = ""
    audience: str = "club members"
    tone: str = "friendly"

class AIEmailReq(BaseModel):
    subject: str
    goal: str
    tone: str = "warm"

class ForgotPasswordIn(BaseModel):
    email: EmailStr

class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6)

class VerifyEmailIn(BaseModel):
    token: str

class RoleUpdateIn(BaseModel):
    role: Literal["member", "admin"]

class TierIn(BaseModel):
    name: str
    order: int = 0
    color: str = "#E86A58"
    annual_dues: float = 60.0
    description: str = ""

class TierUpdateIn(BaseModel):
    name: Optional[str] = None
    order: Optional[int] = None
    color: Optional[str] = None
    annual_dues: Optional[float] = None
    description: Optional[str] = None

class AwardIn(BaseModel):
    name: str
    description: str = ""
    icon: str = "trophy"   # lucide-react icon name
    color: str = "#F9D466"

class AwardUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None

class HoursReviewIn(BaseModel):
    status: Literal["approved", "rejected"]
    note: Optional[str] = ""

class AssignChapterIn(BaseModel):
    chapter_id: Optional[str] = None

class AssignTierIn(BaseModel):
    tier_id: Optional[str] = None
    extend_days: Optional[int] = None  # optional: also push out expiry

class PhotoMetaIn(BaseModel):
    title: Optional[str] = ""
    album: Optional[str] = "general"

class DocumentMetaIn(BaseModel):
    title: Optional[str] = ""
    category: Optional[str] = "general"
    description: Optional[str] = ""

# ---------- Auth Routes ----------
@api.post("/auth/register")
async def register(body: RegisterIn, response: Response):
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
    out["verify_link"] = verify_link  # dev: returned so UI can surface; replace with email provider later
    out["access_token"] = at
    out["refresh_token"] = rt
    return out

@api.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.lower()
    xff = request.headers.get("x-forwarded-for", "")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
    identifier = f"{ip}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("count", 0) >= 5:
        locked_until = attempt.get("locked_until")
        if locked_until and datetime.fromisoformat(locked_until) > now_utc():
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"locked_until": iso(now_utc() + timedelta(minutes=15))}},
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await db.login_attempts.delete_one({"identifier": identifier})
    tv = int(user.get("token_version", 0) or 0)
    at = create_access_token(user["id"], user["email"], user.get("role", "member"), tv)
    rt = create_refresh_token(user["id"], tv)
    set_auth_cookies(response, at, rt)
    out = public_user(user)
    # Return tokens in the body so mobile clients (iOS Safari ITP can evict
    # third-party-ish cookies) can store them in localStorage and send them
    # as Authorization: Bearer headers. Cookies still work for non-mobile.
    out["access_token"] = at
    out["refresh_token"] = rt
    return out

@api.post("/auth/logout")
async def logout(response: Response, _: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    return {"ok": True}

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


# ---------- Public registration applications (admin-approval flow) ----------
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


@api.post("/auth/apply")
async def submit_application(body: PublicApplicationIn):
    """Public open-registration: candidate fills out the form. Goes into 'pending'.
    Admin reviews. On approval, a user is created with an unset password and an email
    is sent with a one-time link to set their password."""
    email = body.email.lower().strip()
    # Already a member?
    existing_user = await db.users.find_one({"email": email})
    if existing_user:
        raise HTTPException(status_code=400, detail="An account already exists for this email")
    # Already applied & pending?
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
    # Notify all full admins so they can review immediately.
    try:
        asyncio.create_task(_send_application_admin_notification(doc))
    except Exception as ex:
        logger.warning(f"Failed to schedule admin notification: {ex}")
    return {"ok": True, "application_id": doc["id"]}


async def _send_application_admin_notification(application: dict) -> bool:
    """Email every full admin when a new application is submitted."""
    if not RESEND_API_KEY:
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
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    import html as _h
    name = _h.escape(f"{application.get('first_name', '')} {application.get('last_name', '')}".strip())
    email = _h.escape(application.get("email", ""))
    line = _h.escape(application.get("line_name", "") or "—")
    chapter_state = _h.escape(application.get("state", "") or "—")
    intake = _h.escape(application.get("intake_completed_at", "") or "—")
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
            "from": RESEND_FROM,
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


@api.get("/admin/applications")
async def list_applications(status_filter: Optional[str] = "pending", _: dict = Depends(admin_tab_dep("members"))):
    q: dict = {}
    if status_filter:
        q["status"] = status_filter
    cursor = db.applications.find(q, {"_id": 0}).sort("created_at", -1).limit(500)
    items = await cursor.to_list(500)
    return [application_out(a) for a in items]


async def _send_set_password_email(email: str, name: str, token: str) -> bool:
    if not RESEND_API_KEY or not email:
        return False
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    set_link = f"{frontend}/set-password?token={token}"
    import html as _h
    safe_name = _h.escape(name or "")
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
            "from": RESEND_FROM,
            "to": [email],
            "subject": "Alpha Omega Phi — your application was approved, set your password",
            "html": body,
            "tags": [{"name": "type", "value": "set_password"}],
        })
        return True
    except Exception as e:
        logger.warning(f"Set-password email failed for {email}: {e}")
        return False


async def _send_approval_email(email: str, name: str) -> tuple[bool, str]:
    """Sent when an admin approves an application. The applicant already chose
    their password during apply, so we just welcome them and tell them to log in.
    Returns (ok, detail) — detail is a human-readable failure reason when ok=False."""
    if not RESEND_API_KEY:
        return False, "Resend API key not configured on the server (RESEND_API_KEY)."
    if not email:
        return False, "Applicant has no email address on file."
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    import html as _h
    safe_name = _h.escape(name or "")
    safe_email = _h.escape(email)
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
            "from": RESEND_FROM,
            "to": [email],
            "subject": "Welcome to Alpha Omega Phi",
            "html": body,
            "tags": [{"name": "type", "value": "application_approved"}],
        })
        logger.info(f"Welcome (approval) email sent to {email} from {RESEND_FROM}")
        return True, "sent"
    except Exception as e:
        msg = str(e)
        logger.warning(f"Welcome (approval) email FAILED for {email} (from={RESEND_FROM}): {msg}")
        return False, msg


async def _send_rejection_email(email: str, name: str, note: str) -> bool:
    if not RESEND_API_KEY or not email:
        return False
    import html as _h
    safe_name = _h.escape(name or "")
    safe_note = _h.escape(note or "")
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
            "from": RESEND_FROM,
            "to": [email],
            "subject": "Alpha Omega Phi — application update",
            "html": body,
            "tags": [{"name": "type", "value": "application_rejected"}],
        })
        return True
    except Exception as e:
        logger.warning(f"Rejection email failed for {email}: {e}")
        return False


@api.post("/admin/applications/{app_id}/review")
async def review_application(app_id: str, body: ApplicationReviewIn, admin: dict = Depends(admin_tab_dep("members"))):
    app_doc = await db.applications.find_one({"id": app_id})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")
    if app_doc.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Application is already {app_doc.get('status')}")
    if body.action == "approve":
        # Use the password the applicant chose when applying.
        applicant_password_hash = app_doc.get("password_hash")
        if not applicant_password_hash:
            # Backwards-compat for legacy pending apps with no password — fall back to token flow.
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
        email_ok, email_detail = await _send_approval_email(app_doc["email"], composed_name)
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
    await _send_rejection_email(app_doc["email"], name, body.note or "")
    return {"ok": True}


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


class RefreshIn(BaseModel):
    refresh_token: Optional[str] = None


async def _send_password_reset_email(email: str, name: str, token: str) -> bool:
    if not RESEND_API_KEY or not email:
        return False
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    link = f"{frontend}/reset-password?token={token}"
    import html as _h
    safe_name = _h.escape(name or "")
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
            "from": RESEND_FROM,
            "to": [email],
            "subject": "Reset your Alpha Omega Phi password",
            "html": body,
            "tags": [{"name": "type", "value": "password_reset"}],
        })
        return True
    except Exception as e:
        logger.warning(f"Password reset email failed for {email}: {e}")
        return False


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
        await _send_password_reset_email(email, user.get("name", ""), token)
    return {"ok": True}


@api.post("/auth/reset-password")
async def reset_password(body: ResetPasswordIn):
    t = await db.password_reset_tokens.find_one({"token": body.token, "used": False})
    if not t:
        raise HTTPException(status_code=400, detail="Invalid or already-used reset link.")
    if t.get("expires_at") and t["expires_at"] < iso(now_utc()):
        raise HTTPException(status_code=400, detail="This reset link has expired. Request a new one.")
    await db.users.update_one(
        {"id": t["user_id"]},
        {"$set": {"password_hash": hash_password(body.new_password)}, "$inc": {"token_version": 1}},
    )
    await db.password_reset_tokens.update_one({"token": body.token}, {"$set": {"used": True, "used_at": iso(now_utc())}})
    return {"ok": True}


@api.post("/auth/refresh")
async def refresh(request: Request, response: Response, body: Optional[RefreshIn] = None):
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

# ---------- Profile / Members ----------
@api.get("/members")
async def list_members(q: Optional[str] = None, city: Optional[str] = None):
    query = {}
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"bio": {"$regex": q, "$options": "i"}},
            {"interests": {"$regex": q, "$options": "i"}},
        ]
    if city:
        query["city"] = {"$regex": city, "$options": "i"}
    cursor = db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).limit(200)
    users = await cursor.to_list(200)
    return [public_user(u) for u in users]

@api.get("/members/{member_id}")
async def get_member(member_id: str):
    u = await db.users.find_one({"id": member_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    return public_user(u)

@api.get("/members-new")
async def new_members(days: int = 30, limit: int = 8):
    """Members who joined in the last N days."""
    cutoff = iso(now_utc() - timedelta(days=days))
    cursor = db.users.find(
        {"created_at": {"$gte": cutoff}},
        {"_id": 0, "password_hash": 0},
    ).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(limit)
    return [public_user(u) for u in items]

@api.get("/members-birthdays")
async def upcoming_birthdays(days: int = 30, limit: int = 25):
    """Members with birthdays in the next N days (ignoring year)."""
    today = now_utc().date()
    out = []
    cursor = db.users.find(
        {"birthdate": {"$nin": [None, ""]}},
        {"_id": 0, "password_hash": 0},
    )
    async for u in cursor:
        bd_str = u.get("birthdate") or ""
        try:
            # Accept YYYY-MM-DD or full ISO
            bd = datetime.fromisoformat(bd_str.replace("Z", "+00:00")).date() if "T" in bd_str else datetime.strptime(bd_str[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        # Compute next anniversary on/after today
        try:
            this_year = bd.replace(year=today.year)
        except ValueError:  # Feb 29
            this_year = bd.replace(year=today.year, day=28)
        next_bd = this_year if this_year >= today else (
            bd.replace(year=today.year + 1) if bd.month != 2 or bd.day != 29 else bd.replace(year=today.year + 1, day=28)
        )
        delta = (next_bd - today).days
        if 0 <= delta <= days:
            entry = public_user(u)
            entry["next_birthday"] = next_bd.isoformat()
            entry["days_until_birthday"] = delta
            entry["age_turning"] = next_bd.year - bd.year
            out.append(entry)
    out.sort(key=lambda x: x["days_until_birthday"])
    return out[:limit]

@api.put("/members/{user_id}/status")
async def set_member_status(user_id: str, body: StatusOverrideIn, _: dict = Depends(admin_tab_dep("members"))):
    updates: dict = {}
    if body.status is not None:
        updates["status_override"] = body.status
    if body.deceased_at is not None:
        updates["deceased_at"] = body.deceased_at
    elif body.status == "deceased":
        updates["deceased_at"] = iso(now_utc())
    elif body.status and body.status != "deceased":
        updates["deceased_at"] = None
    if updates:
        await db.users.update_one({"id": user_id}, {"$set": updates})
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    return public_user(u)

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

@api.post("/auth/change-password")
async def change_password(body: ChangePasswordIn, user: dict = Depends(get_current_user)):
    full = await db.users.find_one({"id": user["id"]})
    if not full or not verify_password(body.current_password, full["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(body.new_password)}})
    return {"ok": True}

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
        "created_at": e.get("created_at"),
    }

@api.get("/events")
async def list_events(upcoming: bool = False, include_sub_events: bool = False):
    query = {}
    if upcoming:
        query["start_at"] = {"$gte": iso(now_utc())}
    # By default the main /events grid hides sub-events — members reach them
    # by clicking into the parent (umbrella) event. Set include_sub_events=true
    # to flatten the tree (used by Admin/Calendar).
    if not include_sub_events:
        query["parent_event_id"] = {"$in": [None, ""]}
    cursor = db.events.find(query, {"_id": 0}).sort("start_at", 1).limit(200)
    events = await cursor.to_list(200)
    return [event_out(e) for e in events]

@api.get("/events/{event_id}")
async def get_event(event_id: str):
    e = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    return event_out(e)

@api.post("/events")
async def create_event(body: EventIn, _: dict = Depends(admin_tab_dep("events"))):
    eid = str(uuid.uuid4())
    doc = body.model_dump()
    doc["start_at"] = iso(doc["start_at"]) if doc.get("start_at") else None
    doc["end_at"] = iso(doc["end_at"]) if doc.get("end_at") else None
    doc.update({"id": eid, "rsvp_count": 0, "created_at": iso(now_utc())})
    await db.events.insert_one(doc)
    return event_out(doc)

@api.put("/events/{event_id}")
async def update_event(event_id: str, body: EventUpdateIn, _: dict = Depends(admin_tab_dep("events"))):
    updates = {}
    for k, v in body.model_dump().items():
        if v is None:
            continue
        if k in ("start_at", "end_at") and isinstance(v, datetime):
            updates[k] = iso(v)
        else:
            updates[k] = v
    if updates:
        await db.events.update_one({"id": event_id}, {"$set": updates})
    e = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    return event_out(e)

@api.delete("/events/{event_id}")
async def delete_event(event_id: str, _: dict = Depends(admin_tab_dep("events"))):
    await db.events.delete_one({"id": event_id})
    await db.rsvps.delete_many({"event_id": event_id})
    return {"ok": True}

@api.post("/events/{event_id}/rsvp")
async def rsvp_event(event_id: str, body: Optional[EventRsvpIn] = None, user: dict = Depends(get_current_user)):
    e = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    # Parent events (which group sub-events) cannot be RSVP'd directly — members
    # RSVP individually to each sub-event listed underneath. This prevents the
    # awkward "RSVP to the umbrella" UX that confuses everyone.
    has_children = await db.events.find_one({"parent_event_id": event_id})
    if has_children:
        raise HTTPException(
            status_code=400,
            detail="This event is an umbrella — please RSVP to each sub-event below individually.",
        )
    existing = await db.rsvps.find_one({"event_id": event_id, "user_id": user["id"]})
    if existing:
        prev_guests = len(existing.get("guests", []) or [])
        await db.rsvps.delete_one({"_id": existing["_id"]})
        await db.events.update_one(
            {"id": event_id},
            {"$inc": {"rsvp_count": -1, "guest_count": -prev_guests}},
        )
        return {"rsvped": False}
    member_ticket_type = (body.ticket_type if body else None) or "general"
    guests_raw = body.guests if body else []
    guests = []
    for g in guests_raw:
        gd = g.model_dump()
        gd["ticket_id"] = str(uuid.uuid4())
        gd["ticket_type"] = (gd.get("ticket_type") or "general")
        gd["checked_in_at"] = None
        guests.append(gd)
    seats_needed = 1 + len(guests)
    if e.get("capacity", 0) > 0 and (e.get("rsvp_count", 0) + e.get("guest_count", 0) + seats_needed) > e["capacity"]:
        raise HTTPException(status_code=400, detail="Event does not have enough seats")
    member_ticket_id = str(uuid.uuid4())
    rsvp_doc = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "user_id": user["id"],
        "user_name": user.get("name", ""),
        "ticket_id": member_ticket_id,
        "ticket_type": member_ticket_type,
        "guests": guests,
        "created_at": iso(now_utc()),
    }
    await db.rsvps.insert_one(rsvp_doc)
    await db.events.update_one(
        {"id": event_id},
        {"$inc": {"rsvp_count": 1, "guest_count": len(guests)}},
    )
    # Fire-and-forget: email the member their ticket(s) with QR code(s).
    try:
        asyncio.create_task(send_rsvp_ticket_email(user, e, rsvp_doc))
    except Exception as ex:
        logger.warning(f"Failed to schedule ticket email: {ex}")
    return {"rsvped": True, "guests": len(guests), "ticket_id": member_ticket_id}

@api.put("/events/{event_id}/rsvp/guests")
async def update_rsvp_guests(event_id: str, body: EventRsvpIn, user: dict = Depends(get_current_user)):
    """Update the guest list on an existing RSVP without toggling it."""
    rsvp = await db.rsvps.find_one({"event_id": event_id, "user_id": user["id"]})
    if not rsvp:
        raise HTTPException(status_code=404, detail="You have not RSVPed for this event")
    e = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    prev_guests = rsvp.get("guests", []) or []
    prev_by_name = {(g.get("name") or "").strip().lower(): g for g in prev_guests}
    new_guests = []
    for g in body.guests:
        gd = g.model_dump()
        key = (gd.get("name") or "").strip().lower()
        old = prev_by_name.get(key)
        gd["ticket_id"] = (old.get("ticket_id") if old else None) or str(uuid.uuid4())
        gd["ticket_type"] = gd.get("ticket_type") or (old.get("ticket_type") if old else "general")
        gd["checked_in_at"] = old.get("checked_in_at") if old else None
        new_guests.append(gd)
    # Also update member ticket_type if provided
    sets = {"guests": new_guests}
    if body.ticket_type:
        sets["ticket_type"] = body.ticket_type
    delta = len(new_guests) - len(prev_guests)
    if e.get("capacity", 0) > 0 and (e.get("rsvp_count", 0) + e.get("guest_count", 0) + delta) > e["capacity"]:
        raise HTTPException(status_code=400, detail="Event does not have enough seats")
    await db.rsvps.update_one({"_id": rsvp["_id"]}, {"$set": sets})
    if delta:
        await db.events.update_one({"id": event_id}, {"$inc": {"guest_count": delta}})
    # Re-send the ticket email so the member has the up-to-date guest QR codes.
    try:
        fresh = await db.rsvps.find_one({"_id": rsvp["_id"]}, {"_id": 0})
        u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
        if u and fresh:
            asyncio.create_task(send_rsvp_ticket_email(u, e, fresh))
    except Exception as ex:
        logger.warning(f"Failed to schedule re-send ticket email: {ex}")
    return {"ok": True, "guests": len(new_guests)}

@api.get("/events/{event_id}/sub-events")
async def list_sub_events(event_id: str):
    """List child events under a parent event (e.g. 10-Year anniversary umbrella)."""
    cursor = db.events.find({"parent_event_id": event_id}, {"_id": 0}).sort("start_at", 1).limit(100)
    items = await cursor.to_list(100)
    return [event_out(e) for e in items]

@api.get("/events/{event_id}/rsvps")
async def list_rsvps(event_id: str):
    cursor = db.rsvps.find({"event_id": event_id}, {"_id": 0}).limit(500)
    items = await cursor.to_list(500)
    return items

@api.get("/me/events")
async def my_events(user: dict = Depends(get_current_user)):
    rsvps = await db.rsvps.find({"user_id": user["id"]}, {"_id": 0}).to_list(500)
    ids = [r["event_id"] for r in rsvps]
    events = await db.events.find({"id": {"$in": ids}}, {"_id": 0}).to_list(500)
    return [event_out(e) for e in events]


# ---------- QR Ticket helpers (email confirmation + scan-to-check-in) ----------
def make_ticket_token(event_id: str, ticket_id: str, kind: str, ticket_type: str, name: str = "") -> str:
    """Signed JWT carried in the QR code. Validated server-side at scan."""
    payload = {
        "event_id": event_id,
        "ticket_id": ticket_id,
        "kind": kind,  # "member" | "guest"
        "ticket_type": ticket_type or "general",
        "name": name or "",
        "iat": int(now_utc().timestamp()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_ticket_token(token: str) -> dict:
    return jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])


def make_qr_png_b64(payload_url: str) -> str:
    """Return a base64-encoded PNG for inline embedding (data: URI)."""
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(payload_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0A2463", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _ticket_card_html(holder: str, ticket_type: str, qr_png_b64: str, event_title: str, when: str, where: str) -> str:
    pretty = {"vip": "VIP", "all_access": "All Access", "general": "General Admission",
              "guest": "Guest", "speaker": "Speaker", "volunteer": "Volunteer"}.get(ticket_type, ticket_type.title())
    import html as _h
    return f"""
    <div style="border:2px solid #0A2463;border-radius:18px;padding:20px;margin:14px 0;background:#fff;display:flex;gap:16px;align-items:center">
      <div style="flex-shrink:0">
        <img src="data:image/png;base64,{qr_png_b64}" alt="ticket QR" width="160" height="160" style="display:block;border-radius:6px"/>
      </div>
      <div style="flex:1;font-family:-apple-system,sans-serif;color:#222">
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:.16em;color:#C8102E;font-weight:700">Ticket · {_h.escape(pretty)}</div>
        <div style="font-size:18px;font-weight:800;color:#0A2463;margin-top:4px">{_h.escape(holder)}</div>
        <div style="font-size:13px;color:#444;margin-top:8px">{_h.escape(event_title)}</div>
        <div style="font-size:12px;color:#666;margin-top:2px">{_h.escape(when)}{' · ' + _h.escape(where) if where else ''}</div>
        <div style="font-size:10px;color:#888;margin-top:10px;line-height:1.4">Show this QR at the door. Admin staff will scan it to check you in.</div>
      </div>
    </div>
    """


async def send_rsvp_ticket_email(member: dict, event: dict, rsvp: dict) -> bool:
    """Email the member their digital ticket(s) — one QR per attendee (member + each guest).
    Idempotent: safe to call again after guest-list edits."""
    if not RESEND_API_KEY:
        logger.info(f"RSVP ticket email skipped (no RESEND_API_KEY) for {member.get('email')}")
        return False
    email = (member.get("email") or "").strip()
    if not email:
        return False
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    # Build QR cards
    event_title = event.get("title", "Alpha Omega Phi Event")
    when = ""
    try:
        from datetime import datetime as _dt
        sa = event.get("start_at")
        if sa:
            d = _dt.fromisoformat(sa.replace("Z", "+00:00"))
            when = d.strftime("%A, %b %d, %Y · %I:%M %p UTC")
    except Exception:
        when = event.get("start_at", "")
    where = event.get("location", "")
    cards_html = []
    # Member ticket — backfill missing ticket_id onto the RSVP doc so future
    # re-sends use the same QR (instead of generating a different one each call).
    member_ticket_id = rsvp.get("ticket_id")
    if not member_ticket_id:
        member_ticket_id = str(uuid.uuid4())
        await db.rsvps.update_one({"id": rsvp.get("id")}, {"$set": {"ticket_id": member_ticket_id}})
    member_token = make_ticket_token(event["id"], member_ticket_id, "member", rsvp.get("ticket_type", "general"), member.get("name", ""))
    member_url = f"{frontend}/checkin/{member_token}"
    cards_html.append(_ticket_card_html(member.get("name", "Member"), rsvp.get("ticket_type", "general"),
                                        make_qr_png_b64(member_url), event_title, when, where))
    # Guest tickets — backfill per-guest ticket_id as well.
    guests = rsvp.get("guests", []) or []
    guests_dirty = False
    for g in guests:
        if not g.get("ticket_id"):
            g["ticket_id"] = str(uuid.uuid4())
            guests_dirty = True
        gtoken = make_ticket_token(event["id"], g["ticket_id"], "guest", g.get("ticket_type", "general"), g.get("name", ""))
        gurl = f"{frontend}/checkin/{gtoken}"
        cards_html.append(_ticket_card_html(g.get("name", "Guest"), g.get("ticket_type", "general"), make_qr_png_b64(gurl), event_title, when, where))
    if guests_dirty:
        await db.rsvps.update_one({"id": rsvp.get("id")}, {"$set": {"guests": guests}})
    body = f"""
    <div style="font-family:-apple-system,sans-serif;max-width:640px;margin:0 auto;padding:24px;background:#f7f5f0">
      <h1 style="color:#0A2463;margin:0 0 4px;font-size:26px">You're going! 🎉</h1>
      <div style="color:#666;font-size:13px">RSVP confirmed for <strong>{event_title}</strong></div>
      <div style="background:#fff;border-radius:12px;padding:14px 18px;margin:18px 0;font-size:13px;line-height:1.55">
        <div><strong>When:</strong> {when or 'TBA'}</div>
        <div><strong>Where:</strong> {where or 'TBA'}</div>
        <div><strong>Tickets:</strong> {len(cards_html)} ({1 + len(rsvp.get('guests', []) or [])} attendees total)</div>
      </div>
      {''.join(cards_html)}
      <p style="font-size:12px;color:#888;margin-top:18px;line-height:1.6">Each person needs their own QR ticket at the door. To add or remove guests, head back to <a href="{frontend}/events/{event['id']}" style="color:#C8102E">your RSVP page</a>.</p>
    </div>
    """
    try:
        await asyncio.to_thread(resend_sdk.Emails.send, {
            "from": RESEND_FROM,
            "to": [email],
            "subject": f"Your tickets — {event_title}",
            "html": body,
            "tags": [{"name": "type", "value": "rsvp_ticket"}, {"name": "event_id", "value": event["id"]}],
        })
        logger.info(f"RSVP ticket email sent to {email} for {event_title} ({len(cards_html)} tickets)")
        return True
    except Exception as e:
        logger.warning(f"RSVP ticket email failed for {email}: {e}")
        return False


@api.get("/checkin/lookup/{token}")
async def checkin_lookup(token: str):
    """Decode a QR token and return ticket info — used by the /checkin/:token
    landing page to show 'who is this'. Does NOT require auth (the page itself
    enforces admin login before recording the check-in)."""
    try:
        payload = decode_ticket_token(token)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired ticket QR")
    event = await db.events.find_one({"id": payload["event_id"]}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event no longer exists")
    return {
        "event": event_out(event),
        "ticket_id": payload["ticket_id"],
        "kind": payload["kind"],
        "ticket_type": payload.get("ticket_type", "general"),
        "name": payload.get("name", ""),
    }


@api.post("/checkin/scan/{token}")
async def checkin_scan(token: str, user: dict = Depends(get_current_user)):
    """Admin scans the QR. Token is decoded → check-in is recorded immediately.
    Idempotent: subsequent scans return the existing check-in row with already_checked_in=true."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can scan tickets to check in attendees.")
    try:
        payload = decode_ticket_token(token)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired ticket QR")
    event_id = payload["event_id"]
    ticket_id = payload["ticket_id"]
    ticket_type = payload.get("ticket_type", "general")
    kind = payload["kind"]
    holder_name = payload.get("name", "")
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event no longer exists")
    # Look for an existing check-in row tied to this ticket_id
    existing = await db.checkins.find_one({"event_id": event_id, "ticket_id": ticket_id}, {"_id": 0})
    if existing:
        return {"already_checked_in": True, "checkin": existing, "event": event_out(event)}
    if kind == "member":
        # Find the matching member RSVP row
        rsvp = await db.rsvps.find_one({"event_id": event_id, "ticket_id": ticket_id})
        if not rsvp:
            # Token is valid but RSVP was cancelled
            raise HTTPException(status_code=410, detail="This ticket is no longer valid (the member cancelled their RSVP).")
        doc = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "user_id": rsvp.get("user_id"),
            "user_name": rsvp.get("user_name", holder_name),
            "ticket_id": ticket_id,
            "ticket_type": ticket_type,
            "guest_name": "",
            "checked_in_at": iso(now_utc()),
            "checked_in_by": user["id"],
            "checked_in_by_name": user.get("name", ""),
        }
    else:  # guest
        # Find which RSVP this guest belongs to
        rsvp = await db.rsvps.find_one({"event_id": event_id, "guests.ticket_id": ticket_id})
        if not rsvp:
            raise HTTPException(status_code=410, detail="This guest ticket is no longer on any RSVP.")
        doc = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "user_id": None,
            "user_name": holder_name or "Guest",
            "ticket_id": ticket_id,
            "ticket_type": ticket_type,
            "guest_name": holder_name,
            "host_user_id": rsvp.get("user_id"),
            "host_user_name": rsvp.get("user_name", ""),
            "checked_in_at": iso(now_utc()),
            "checked_in_by": user["id"],
            "checked_in_by_name": user.get("name", ""),
        }
    await db.checkins.insert_one(doc)
    doc.pop("_id", None)
    return {"already_checked_in": False, "checkin": doc, "event": event_out(event)}


# ---------- News ----------
def news_out(n: dict) -> dict:
    return {
        "id": n["id"],
        "title": n["title"],
        "summary": n.get("summary", ""),
        "body": n.get("body", ""),
        "cover_image": n.get("cover_image", ""),
        "tags": n.get("tags", []),
        "author_name": n.get("author_name", ""),
        "created_at": n.get("created_at"),
    }

@api.get("/news")
async def list_news():
    cursor = db.news.find({}, {"_id": 0}).sort("created_at", -1).limit(100)
    items = await cursor.to_list(100)
    return [news_out(n) for n in items]

@api.get("/news/{news_id}")
async def get_news(news_id: str):
    n = await db.news.find_one({"id": news_id}, {"_id": 0})
    if not n:
        raise HTTPException(status_code=404, detail="News not found")
    return news_out(n)

@api.post("/news")
async def create_news(body: NewsIn, admin: dict = Depends(admin_tab_dep("news"))):
    nid = str(uuid.uuid4())
    doc = body.model_dump()
    doc.update({"id": nid, "author_name": admin.get("name", "Admin"), "created_at": iso(now_utc())})
    await db.news.insert_one(doc)
    return news_out(doc)

@api.put("/news/{news_id}")
async def update_news(news_id: str, body: NewsUpdateIn, _: dict = Depends(admin_tab_dep("news"))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.news.update_one({"id": news_id}, {"$set": updates})
    n = await db.news.find_one({"id": news_id}, {"_id": 0})
    if not n:
        raise HTTPException(status_code=404, detail="News not found")
    return news_out(n)

@api.delete("/news/{news_id}")
async def delete_news(news_id: str, _: dict = Depends(admin_tab_dep("news"))):
    await db.news.delete_one({"id": news_id})
    return {"ok": True}

# ---------- CMS Pages ----------
def page_out(p: dict) -> dict:
    return {
        "id": p["id"],
        "slug": p["slug"],
        "title": p["title"],
        "body": p.get("body", ""),
        "updated_at": p.get("updated_at"),
    }

@api.get("/pages")
async def list_pages():
    items = await db.pages.find({}, {"_id": 0}).to_list(100)
    return [page_out(p) for p in items]

@api.get("/pages/{slug}")
async def get_page(slug: str):
    p = await db.pages.find_one({"slug": slug}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Page not found")
    return page_out(p)

@api.post("/pages")
async def create_page(body: PageIn, _: dict = Depends(admin_tab_dep("pages"))):
    existing = await db.pages.find_one({"slug": body.slug})
    if existing:
        raise HTTPException(status_code=400, detail="Slug already exists")
    doc = body.model_dump()
    doc.update({"id": str(uuid.uuid4()), "updated_at": iso(now_utc())})
    await db.pages.insert_one(doc)
    return page_out(doc)

@api.put("/pages/{slug}")
async def update_page(slug: str, body: PageUpdateIn, _: dict = Depends(admin_tab_dep("pages"))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates["updated_at"] = iso(now_utc())
    await db.pages.update_one({"slug": slug}, {"$set": updates})
    p = await db.pages.find_one({"slug": slug}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Page not found")
    return page_out(p)

@api.delete("/pages/{slug}")
async def delete_page(slug: str, _: dict = Depends(admin_tab_dep("pages"))):
    await db.pages.delete_one({"slug": slug})
    return {"ok": True}


# ---------- Site Settings (home hero, footer, page-title overrides, nav labels) ----------
SETTINGS_DOC_ID = "site_settings_v1"

DEFAULT_SETTINGS = {
    "id": SETTINGS_DOC_ID,
    "hero_eyebrow": "Alpha Omega Phi Military Fraternity & Sorority, Inc.",
    "hero_headline": "Service. Honor. Brotherhood. Sisterhood.",
    "hero_subtext": "Veterans and service members from every branch — bonded for life.",
    "hero_cta_label": "Become a member",
    "hero_cta_href": "/apply",
    "footer_text": "© Alpha Omega Phi Military Fraternity & Sorority, Inc. — All rights reserved.",
    "footer_links": [
        {"label": "About", "href": "/about"},
        {"label": "Contact", "href": "mailto:info@aop-app.org"},
    ],
    # H1 / nav label overrides keyed by page slug
    "page_titles": {},        # {"directory": "Roster", "documents": "Forms hub"}
    "nav_labels": {},         # {"directory": "Roster"}
    "updated_at": iso(now_utc()),
}


class SiteSettingsIn(BaseModel):
    hero_eyebrow: Optional[str] = Field(None, max_length=300)
    hero_headline: Optional[str] = Field(None, max_length=300)
    hero_subtext: Optional[str] = Field(None, max_length=600)
    hero_cta_label: Optional[str] = Field(None, max_length=120)
    hero_cta_href: Optional[str] = Field(None, max_length=300)
    footer_text: Optional[str] = Field(None, max_length=1000)
    footer_links: Optional[List[Dict[str, str]]] = Field(None, max_length=20)
    page_titles: Optional[Dict[str, str]] = None
    nav_labels: Optional[Dict[str, str]] = None


async def _ensure_site_settings():
    existing = await db.site_settings.find_one({"id": SETTINGS_DOC_ID})
    if not existing:
        await db.site_settings.insert_one(dict(DEFAULT_SETTINGS))


@api.get("/site-settings")
async def get_site_settings():
    await _ensure_site_settings()
    s = await db.site_settings.find_one({"id": SETTINGS_DOC_ID}, {"_id": 0})
    return s


@api.put("/site-settings")
async def update_site_settings(body: SiteSettingsIn, _: dict = Depends(admin_tab_dep("pages"))):
    await _ensure_site_settings()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates["updated_at"] = iso(now_utc())
    await db.site_settings.update_one({"id": SETTINGS_DOC_ID}, {"$set": updates})
    s = await db.site_settings.find_one({"id": SETTINGS_DOC_ID}, {"_id": 0})
    return s

# ---------- AI (Claude Sonnet 4.5) ----------
async def run_claude(system_message: str, user_prompt: str, session_id: str) -> str:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=session_id,
        system_message=system_message,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    msg = UserMessage(text=user_prompt)
    return await chat.send_message(msg)

@api.post("/ai/event-description")
async def ai_event_description(body: AIEventReq, admin: dict = Depends(require_admin)):
    system = ("You are a friendly community manager who writes warm, vivid event descriptions "
              "(120-180 words) for a members club. Avoid hype. Keep it inclusive, concrete, and inviting.")
    prompt = (f"Write a compelling event description.\nEvent title: {body.title}\n"
              f"Topic/details: {body.topic}\nAudience: {body.audience}\nTone: {body.tone}\n"
              "Include a short opening hook, what attendees will do, and a closing CTA line.")
    try:
        text = await run_claude(system, prompt, f"event-desc-{admin['id']}")
        return {"text": text}
    except Exception as e:
        logger.exception("AI event description failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")

@api.post("/ai/draft-email")
async def ai_draft_email(body: AIEmailReq, admin: dict = Depends(require_admin)):
    system = ("You draft warm, concise emails to club members. 150-220 words. Plain-text friendly. "
              "Use a short greeting, two body paragraphs, and a clear CTA.")
    prompt = (f"Subject: {body.subject}\nGoal of the email: {body.goal}\nTone: {body.tone}\n"
              "Start with 'Hi friends,' and sign off as 'The Club Team'.")
    try:
        text = await run_claude(system, prompt, f"email-{admin['id']}")
        return {"text": text}
    except Exception as e:
        logger.exception("AI email draft failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")

# ---------- Chapters ----------
def chapter_out(c: dict) -> dict:
    return {
        "id": c["id"],
        "name": c["name"],
        "school": c.get("school", ""),
        "city": c.get("city", ""),
        "state": c.get("state", ""),
        "region": c.get("region", ""),
        "founded_year": c.get("founded_year"),
        "description": c.get("description", ""),
        "logo_url": c.get("logo_url", ""),
        "member_count": c.get("member_count", 0),
    }

async def with_chapter_counts(chapters):
    out = []
    for c in chapters:
        c["member_count"] = await db.users.count_documents({"chapter_id": c["id"]})
        out.append(chapter_out(c))
    return out

@api.get("/chapters")
async def list_chapters():
    items = await db.chapters.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    return await with_chapter_counts(items)

@api.post("/chapters")
async def create_chapter(body: ChapterIn, _: dict = Depends(admin_tab_dep("chapters"))):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Chapter name is required.")
    existing = await db.chapters.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=400, detail=f"A chapter named '{existing['name']}' already exists.")
    doc = body.model_dump()
    doc["name"] = name
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = iso(now_utc())
    await db.chapters.insert_one(doc)
    doc["member_count"] = 0
    return chapter_out(doc)

@api.put("/chapters/{chapter_id}")
async def update_chapter(chapter_id: str, body: ChapterUpdateIn, _: dict = Depends(admin_tab_dep("chapters"))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.chapters.update_one({"id": chapter_id}, {"$set": updates})
    c = await db.chapters.find_one({"id": chapter_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Chapter not found")
    c["member_count"] = await db.users.count_documents({"chapter_id": chapter_id})
    return chapter_out(c)

@api.delete("/chapters/{chapter_id}")
async def delete_chapter(chapter_id: str, _: dict = Depends(admin_tab_dep("chapters"))):
    await db.chapters.delete_one({"id": chapter_id})
    await db.users.update_many({"chapter_id": chapter_id}, {"$unset": {"chapter_id": ""}})
    return {"ok": True}

# ---------- Membership Tiers ----------
def tier_out(t: dict) -> dict:
    return {
        "id": t["id"],
        "name": t["name"],
        "order": t.get("order", 0),
        "color": t.get("color", "#E86A58"),
        "annual_dues": t.get("annual_dues", 60.0),
        "is_lifetime": bool(t.get("is_lifetime")),
        "description": t.get("description", ""),
        "member_count": t.get("member_count", 0),
    }

@api.get("/tiers")
async def list_tiers():
    items = await db.tiers.find({}, {"_id": 0}).sort("order", 1).to_list(50)
    for t in items:
        t["member_count"] = await db.users.count_documents({"tier_id": t["id"]})
    return [tier_out(t) for t in items]

@api.post("/tiers")
async def create_tier(body: TierIn, _: dict = Depends(admin_tab_dep("tiers"))):
    doc = body.model_dump()
    doc["id"] = str(uuid.uuid4())
    await db.tiers.insert_one(doc)
    doc["member_count"] = 0
    return tier_out(doc)

@api.put("/tiers/{tier_id}")
async def update_tier(tier_id: str, body: TierUpdateIn, _: dict = Depends(admin_tab_dep("tiers"))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.tiers.update_one({"id": tier_id}, {"$set": updates})
    t = await db.tiers.find_one({"id": tier_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tier not found")
    t["member_count"] = await db.users.count_documents({"tier_id": tier_id})
    return tier_out(t)

@api.delete("/tiers/{tier_id}")
async def delete_tier(tier_id: str, _: dict = Depends(admin_tab_dep("tiers"))):
    await db.tiers.delete_one({"id": tier_id})
    await db.users.update_many({"tier_id": tier_id}, {"$unset": {"tier_id": ""}})
    return {"ok": True}

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


@api.put("/members/{user_id}")
async def admin_update_member(user_id: str, body: AdminUpdateMemberIn, admin: dict = Depends(admin_tab_dep("members"))):
    existing = await db.users.find_one({"id": user_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Member not found")
    # Only full admins may change role / admin_role / tier / membership_expires_at
    expires_changing = body.membership_expires_at is not None and (
        iso(body.membership_expires_at) != (existing.get("membership_expires_at") or "")
    )
    if (
        (body.role is not None and body.role != existing.get("role"))
        or (body.admin_role is not None and body.admin_role != existing.get("admin_role"))
        or (body.tier_id is not None and body.tier_id != existing.get("tier_id"))
        or expires_changing
    ):
        if admin_role_of(admin) != "full":
            raise HTTPException(status_code=403, detail="Only full Admins may change roles, tiers, or the membership expiration date.")
    updates = {k: v for k, v in body.model_dump().items() if v is not None and k not in ("new_password", "member_status")}
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
def award_out(a: dict) -> dict:
    return {
        "id": a["id"],
        "name": a["name"],
        "description": a.get("description", ""),
        "icon": a.get("icon", "trophy"),
        "color": a.get("color", "#F9D466"),
        "granted_count": a.get("granted_count", 0),
    }

@api.get("/awards")
async def list_awards():
    items = await db.awards.find({}, {"_id": 0}).to_list(200)
    for a in items:
        a["granted_count"] = await db.award_grants.count_documents({"award_id": a["id"]})
    return [award_out(a) for a in items]

@api.post("/awards")
async def create_award(body: AwardIn, _: dict = Depends(admin_tab_dep("awards"))):
    doc = body.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = iso(now_utc())
    await db.awards.insert_one(doc)
    return award_out(doc)

@api.put("/awards/{award_id}")
async def update_award(award_id: str, body: AwardUpdateIn, _: dict = Depends(admin_tab_dep("awards"))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.awards.update_one({"id": award_id}, {"$set": updates})
    a = await db.awards.find_one({"id": award_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Award not found")
    return award_out(a)

@api.delete("/awards/{award_id}")
async def delete_award(award_id: str, _: dict = Depends(admin_tab_dep("awards"))):
    await db.awards.delete_one({"id": award_id})
    await db.award_grants.delete_many({"award_id": award_id})
    return {"ok": True}

@api.post("/awards/{award_id}/grant")
async def grant_award(award_id: str, body: AwardGrantIn, admin: dict = Depends(admin_tab_dep("awards"))):
    award = await db.awards.find_one({"id": award_id}, {"_id": 0})
    if not award:
        raise HTTPException(status_code=404, detail="Award not found")
    user = await db.users.find_one({"id": body.user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    existing = await db.award_grants.find_one({"award_id": award_id, "user_id": body.user_id})
    if existing:
        raise HTTPException(status_code=400, detail="User already has this award")
    doc = {
        "id": str(uuid.uuid4()),
        "award_id": award_id,
        "award_name": award["name"],
        "award_icon": award.get("icon", "trophy"),
        "award_color": award.get("color", "#F9D466"),
        "user_id": body.user_id,
        "user_name": user.get("name", ""),
        "reason": body.reason,
        "granted_by": admin["id"],
        "granted_by_name": admin.get("name", "Admin"),
        "granted_at": body.granted_at or iso(now_utc()),
    }
    await db.award_grants.insert_one(doc)
    out = dict(doc)
    out.pop("_id", None)
    return out

@api.delete("/awards/grants/{grant_id}")
async def revoke_award(grant_id: str, _: dict = Depends(admin_tab_dep("awards"))):
    res = await db.award_grants.delete_one({"id": grant_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Grant not found")
    return {"ok": True}

@api.get("/members/{user_id}/awards")
async def member_awards(user_id: str):
    cursor = db.award_grants.find({"user_id": user_id}, {"_id": 0}).sort("granted_at", -1)
    return await cursor.to_list(100)

@api.get("/me/awards")
async def my_awards(user: dict = Depends(get_current_user)):
    cursor = db.award_grants.find({"user_id": user["id"]}, {"_id": 0}).sort("granted_at", -1)
    return await cursor.to_list(100)

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
        "created_at": h.get("created_at"),
    }

@api.post("/hours")
async def log_hours(body: HoursLogIn, user: dict = Depends(get_current_user)):
    activity_text = body.activity or body.description or ""
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_name": user.get("name", ""),
        "hours": body.hours,
        "description": activity_text,
        "activity": activity_text,
        "event_type": body.event_type,
        "agency_name": body.agency_name,
        "host_name": body.host_name,
        "host_email": body.host_email,
        "host_phone": body.host_phone,
        "date": iso(body.date),
        "event_id": body.event_id,
        "status": "pending",
        "created_at": iso(now_utc()),
    }
    await db.volunteer_hours.insert_one(doc)
    return hours_out(doc)

@api.get("/hours")
async def list_hours(status_filter: Optional[str] = None, admin: dict = Depends(require_admin)):
    query = {}
    if status_filter:
        query["status"] = status_filter
    if is_chapter_scoped(admin):
        ids = await chapter_scope_user_ids(admin)
        query["user_id"] = {"$in": ids or []}
    cursor = db.volunteer_hours.find(query, {"_id": 0}).sort("created_at", -1).limit(500)
    items = await cursor.to_list(500)
    return [hours_out(h) for h in items]

@api.get("/me/hours")
async def my_hours(user: dict = Depends(get_current_user)):
    cursor = db.volunteer_hours.find({"user_id": user["id"]}, {"_id": 0}).sort("date", -1)
    items = await cursor.to_list(500)
    return [hours_out(h) for h in items]

@api.put("/hours/{hours_id}/review")
async def review_hours(hours_id: str, body: HoursReviewIn, admin: dict = Depends(admin_tab_dep("hours"))):
    await db.volunteer_hours.update_one(
        {"id": hours_id},
        {"$set": {
            "status": body.status,
            "note": body.note or "",
            "reviewed_by": admin["id"],
            "reviewed_by_name": admin.get("name", "Admin"),
            "reviewed_at": iso(now_utc()),
        }},
    )
    h = await db.volunteer_hours.find_one({"id": hours_id}, {"_id": 0})
    if not h:
        raise HTTPException(status_code=404, detail="Hours entry not found")
    return hours_out(h)

@api.delete("/hours/{hours_id}")
async def delete_hours(hours_id: str, user: dict = Depends(get_current_user)):
    h = await db.volunteer_hours.find_one({"id": hours_id})
    if not h:
        raise HTTPException(status_code=404, detail="Not found")
    if h["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.volunteer_hours.delete_one({"id": hours_id})
    return {"ok": True}

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

@api.get("/photos")
async def list_photos(album: Optional[str] = None):
    query = {"is_deleted": {"$ne": True}}
    if album:
        query["album"] = album
    cursor = db.photos.find(query, {"_id": 0}).sort("created_at", -1).limit(500)
    items = await cursor.to_list(500)
    return [photo_out(p) for p in items]

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
    Also backfills category on every album each boot (cheap, allows recategorizing)."""
    for name in DEFAULT_PHOTO_ALBUMS:
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


@api.get("/photos/albums")
async def list_photo_albums(category: Optional[str] = None):
    """Returns every album the chapter has — canonical + admin-created + any
    albums a member auto-created on upload. Pass `?category=anniversary` to filter."""
    q: dict = {}
    if category and category in PHOTO_ALBUM_CATEGORIES:
        q["category"] = category
    albums = await db.photo_albums.find(q, {"_id": 0}).sort([("is_default", -1), ("name", 1)]).to_list(500)
    pipeline = [
        {"$match": {"is_deleted": {"$ne": True}}},
        {"$group": {"_id": "$album", "count": {"$sum": 1}, "first_photo": {"$first": "$storage_path"}}},
    ]
    counts: dict = {}
    first_photos: dict = {}
    async for d in db.photos.aggregate(pipeline):
        key = d["_id"] or "general"
        counts[key] = d["count"]
        first_photos[key] = d.get("first_photo")
    out = []
    for a in albums:
        # Cover precedence: admin-set cover_url > first uploaded photo in album > none
        cover = a.get("cover_url") or ""
        if not cover:
            fp = first_photos.get(a["name"])
            if fp:
                cover = f"/api/files/{fp}"
        out.append({
            "id": a.get("id"),
            "name": a["name"],
            "count": counts.get(a["name"], 0),
            "is_default": a.get("is_default", False),
            "created_by": a.get("created_by"),
            "created_by_name": a.get("created_by_name", ""),
            "category": a.get("category", auto_categorize_album(a["name"])),
            "cover_url": cover,
        })
    return out


class AlbumIn(BaseModel):
    name: str
    category: Optional[str] = None
    cover_url: Optional[str] = None


@api.post("/photos/albums")
async def create_photo_album(body: AlbumIn, user: dict = Depends(get_current_user)):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Album name is required.")
    existing = await db.photo_albums.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=400, detail=f"Album '{existing['name']}' already exists.")
    category = body.category if (body.category in PHOTO_ALBUM_CATEGORIES) else auto_categorize_album(name)
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "is_default": False,
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "category": category,
        "cover_url": (body.cover_url or "").strip(),
        "created_at": iso(now_utc()),
    }
    await db.photo_albums.insert_one(doc)
    return {"id": doc["id"], "name": name, "count": 0, "is_default": False, "created_by_name": user.get("name", ""), "category": category, "cover_url": doc["cover_url"]}


class AlbumUpdateIn(BaseModel):
    category: Optional[str] = None
    cover_url: Optional[str] = None
    cover_photo_id: Optional[str] = None  # alternative: pick a photo by its id


@api.put("/photos/albums/{album_id}")
async def update_photo_album(album_id: str, body: AlbumUpdateIn, user: dict = Depends(get_current_user)):
    a = await db.photo_albums.find_one({"id": album_id})
    if not a:
        raise HTTPException(status_code=404, detail="Album not found")
    is_admin = user.get("role") == "admin"
    is_creator = a.get("created_by") == user["id"]
    if not (is_admin or is_creator):
        raise HTTPException(status_code=403, detail="Only the album creator or an admin can edit this album.")
    updates: dict = {}
    if body.category and body.category in PHOTO_ALBUM_CATEGORIES:
        updates["category"] = body.category
    if body.cover_url is not None:
        updates["cover_url"] = body.cover_url
    if body.cover_photo_id:
        p = await db.photos.find_one({"id": body.cover_photo_id, "album": a["name"]}, {"_id": 0})
        if p:
            updates["cover_url"] = f"/api/files/{p['storage_path']}"
    if updates:
        await db.photo_albums.update_one({"id": album_id}, {"$set": updates})
    fresh = await db.photo_albums.find_one({"id": album_id}, {"_id": 0})
    return {
        "id": fresh.get("id"),
        "name": fresh.get("name"),
        "category": fresh.get("category", "other"),
        "cover_url": fresh.get("cover_url", ""),
    }


@api.delete("/photos/albums/{album_id}")
async def delete_photo_album(album_id: str, user: dict = Depends(get_current_user)):
    """Creator or any admin may delete a custom album. Default albums cannot
    be deleted. Photos inside the album are NOT deleted — their `album` field
    stays so they remain queryable."""
    a = await db.photo_albums.find_one({"id": album_id})
    if not a:
        raise HTTPException(status_code=404, detail="Album not found")
    if a.get("is_default"):
        raise HTTPException(status_code=400, detail="Default albums cannot be deleted.")
    is_admin = user.get("role") == "admin"
    is_creator = a.get("created_by") == user["id"]
    if not (is_admin or is_creator):
        raise HTTPException(status_code=403, detail="Only the album creator or an admin may delete this album.")
    await db.photo_albums.delete_one({"id": album_id})
    return {"ok": True}

@api.post("/photos")
async def upload_photo(
    file: UploadFile = File(...),
    title: str = Form(""),
    album: str = Form("general"),
    user: dict = Depends(get_current_user),
):
    ext = (file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "bin").lower()
    if ext not in IMAGE_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {ext}")
    content_type = file.content_type or MIME_BY_EXT.get(ext, "application/octet-stream")
    path = f"{APP_NAME}/photos/{user['id']}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")
    result = put_object(path, data, content_type)
    album_name = (album or "general").strip() or "general"
    # Auto-create the album row if it doesn't already exist so it shows up in
    # the album list even before another photo is added.
    await db.photo_albums.update_one(
        {"name": album_name},
        {"$setOnInsert": {
            "id": str(uuid.uuid4()),
            "name": album_name,
            "is_default": False,
            "created_by": user["id"],
            "created_by_name": user.get("name", ""),
            "created_at": iso(now_utc()),
        }},
        upsert=True,
    )
    doc = {
        "id": str(uuid.uuid4()),
        "title": title,
        "album": album_name,
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "uploaded_by": user["id"],
        "uploaded_by_name": user.get("name", ""),
        "is_deleted": False,
        "created_at": iso(now_utc()),
    }
    await db.photos.insert_one(doc)
    return photo_out(doc)


@api.post("/photos/bulk")
async def upload_photos_bulk(
    files: List[UploadFile] = File(...),
    album: str = Form("general"),
    user: dict = Depends(get_current_user),
):
    """Upload many photos at once into a single album. Returns
    {uploaded: [...photo_out], failed: [{name, error}]}. Caps total batch at
    50 files / 100 MB."""
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Upload up to 50 photos per batch.")
    album_name = (album or "general").strip() or "general"
    await db.photo_albums.update_one(
        {"name": album_name},
        {"$setOnInsert": {
            "id": str(uuid.uuid4()), "name": album_name, "is_default": False,
            "created_by": user["id"], "created_by_name": user.get("name", ""),
            "created_at": iso(now_utc()),
        }},
        upsert=True,
    )
    uploaded, failed = [], []
    total_bytes = 0
    for f in files:
        try:
            data = await f.read()
            if len(data) > 10 * 1024 * 1024:
                failed.append({"name": f.filename, "error": "Over 10MB"}); continue
            total_bytes += len(data)
            if total_bytes > 100 * 1024 * 1024:
                failed.append({"name": f.filename, "error": "Batch exceeded 100MB"}); continue
            ext = (f.filename.rsplit(".", 1)[-1] if f.filename and "." in f.filename else "bin").lower()
            if ext not in IMAGE_EXT:
                failed.append({"name": f.filename, "error": "Not an image"}); continue
            content_type = f.content_type or MIME_BY_EXT.get(ext, "image/jpeg")
            path = f"{APP_NAME}/photos/{user['id']}/{uuid.uuid4()}.{ext}"
            result = put_object(path, data, content_type)
            doc = {
                "id": str(uuid.uuid4()),
                "title": "",
                "album": album_name,
                "storage_path": result["path"],
                "original_filename": f.filename,
                "content_type": content_type,
                "size": result.get("size", len(data)),
                "uploaded_by": user["id"],
                "uploaded_by_name": user.get("name", ""),
                "is_deleted": False,
                "created_at": iso(now_utc()),
            }
            await db.photos.insert_one(doc)
            uploaded.append(photo_out(doc))
        except Exception as e:
            failed.append({"name": getattr(f, "filename", "unknown"), "error": str(e)})
    return {"uploaded": uploaded, "failed": failed}

@api.delete("/photos/{photo_id}")
async def delete_photo(photo_id: str, user: dict = Depends(get_current_user)):
    p = await db.photos.find_one({"id": photo_id})
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    if p.get("uploaded_by") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.photos.update_one({"id": photo_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}

@api.delete("/photos/{photo_id}")
async def delete_photo(photo_id: str, user: dict = Depends(get_current_user)):
    p = await db.photos.find_one({"id": photo_id})
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    if p.get("uploaded_by") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.photos.update_one({"id": photo_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}

# ---------- Photo bulk download (zip) ----------
import zipfile
from io import BytesIO


class PhotoDownloadIn(BaseModel):
    photo_ids: List[str] = Field(default_factory=list, max_length=500)
    album: Optional[str] = None  # if set, downloads the entire album


def _safe_filename(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._ -]", "_", s or "")[:120]
    return s or "photo"


@api.post("/photos/download-zip")
async def download_photos_zip(body: PhotoDownloadIn, user: dict = Depends(get_current_user)):
    """Build a ZIP of one or more photos (or an entire album) and stream it back."""
    q: dict = {"is_deleted": {"$ne": True}}
    if body.album:
        q["album"] = body.album
    elif body.photo_ids:
        q["id"] = {"$in": body.photo_ids}
    else:
        raise HTTPException(status_code=400, detail="Pick photos or pass an album name.")
    photos = await db.photos.find(q, {"_id": 0}).to_list(500)
    if not photos:
        raise HTTPException(status_code=404, detail="No photos to download.")
    buf = BytesIO()
    used_names: set = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in photos:
            try:
                data, _ct = await asyncio.to_thread(get_object, p["storage_path"])
            except Exception as e:
                logger.warning(f"Skipping photo {p.get('id')} in zip: {e}")
                continue
            ext = (p.get("original_filename") or p["storage_path"]).rsplit(".", 1)[-1].lower()
            base = _safe_filename(p.get("title") or p.get("original_filename") or p["id"])
            name = f"{base}.{ext}" if not base.lower().endswith(f".{ext}") else base
            n = name; i = 2
            while n in used_names:
                stem = name.rsplit(".", 1)[0]
                n = f"{stem} ({i}).{ext}"
                i += 1
            used_names.add(n)
            zf.writestr(n, data)
    buf.seek(0)
    album_label = _safe_filename(body.album or "photos")
    headers = {"Content-Disposition": f'attachment; filename="aop-{album_label}.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)

# ---------- Documents ----------
def document_out(d: dict) -> dict:
    return {
        "id": d["id"],
        "title": d.get("title", d.get("original_filename", "")),
        "category": d.get("category", "general"),
        "description": d.get("description", ""),
        "storage_path": d["storage_path"],
        "url": f"/api/files/{d['storage_path']}",
        "original_filename": d.get("original_filename", ""),
        "content_type": d.get("content_type", ""),
        "size": d.get("size", 0),
        "uploaded_by": d.get("uploaded_by"),
        "uploaded_by_name": d.get("uploaded_by_name", ""),
        "folder_id": d.get("folder_id"),
        "created_at": d.get("created_at"),
    }

@api.get("/documents")
async def list_documents(category: Optional[str] = None, folder_id: Optional[str] = None):
    query: dict = {"is_deleted": {"$ne": True}}
    if category:
        query["category"] = category
    if folder_id == "root":
        query["folder_id"] = {"$in": [None, ""]}
    elif folder_id:
        query["folder_id"] = folder_id
    cursor = db.documents.find(query, {"_id": 0}).sort("created_at", -1).limit(500)
    items = await cursor.to_list(500)
    return [document_out(d) for d in items]


# ---------- Document Folders (2 levels deep) ----------
class DocumentFolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: Optional[str] = None


@api.get("/document-folders")
async def list_document_folders():
    """Return all folders. Frontend can build the 2-level tree from parent_id."""
    folders = await db.document_folders.find({"is_deleted": {"$ne": True}}, {"_id": 0}).sort("name", 1).to_list(500)
    # Live document counts per folder
    counts: dict = {}
    pipeline = [
        {"$match": {"is_deleted": {"$ne": True}, "folder_id": {"$ne": None}}},
        {"$group": {"_id": "$folder_id", "count": {"$sum": 1}}},
    ]
    async for d in db.documents.aggregate(pipeline):
        counts[d["_id"]] = d["count"]
    return [
        {
            "id": f["id"],
            "name": f["name"],
            "parent_id": f.get("parent_id"),
            "created_by_name": f.get("created_by_name", ""),
            "doc_count": counts.get(f["id"], 0),
            "created_at": f.get("created_at"),
        }
        for f in folders
    ]


@api.post("/document-folders")
async def create_document_folder(body: DocumentFolderIn, admin: dict = Depends(admin_tab_dep("documents"))):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Folder name is required.")
    parent_id = body.parent_id or None
    if parent_id:
        parent = await db.document_folders.find_one({"id": parent_id, "is_deleted": {"$ne": True}})
        if not parent:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        if parent.get("parent_id"):
            raise HTTPException(status_code=400, detail="Subfolders cannot have their own subfolders (max 2 levels).")
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "parent_id": parent_id,
        "created_by": admin["id"],
        "created_by_name": admin.get("name", ""),
        "is_deleted": False,
        "created_at": iso(now_utc()),
    }
    await db.document_folders.insert_one(doc)
    return {"id": doc["id"], "name": name, "parent_id": parent_id, "doc_count": 0, "created_by_name": doc["created_by_name"], "created_at": doc["created_at"]}


@api.put("/document-folders/{folder_id}")
async def rename_document_folder(folder_id: str, body: DocumentFolderIn, admin: dict = Depends(admin_tab_dep("documents"))):
    f = await db.document_folders.find_one({"id": folder_id, "is_deleted": {"$ne": True}})
    if not f:
        raise HTTPException(status_code=404, detail="Folder not found")
    await db.document_folders.update_one({"id": folder_id}, {"$set": {"name": body.name.strip()}})
    return {"ok": True}


@api.delete("/document-folders/{folder_id}")
async def delete_document_folder(folder_id: str, admin: dict = Depends(admin_tab_dep("documents"))):
    """Delete a folder. Any subfolders become root-level, any documents become uncategorized."""
    f = await db.document_folders.find_one({"id": folder_id, "is_deleted": {"$ne": True}})
    if not f:
        raise HTTPException(status_code=404, detail="Folder not found")
    await db.document_folders.update_one({"id": folder_id}, {"$set": {"is_deleted": True}})
    await db.document_folders.update_many({"parent_id": folder_id}, {"$set": {"parent_id": None}})
    await db.documents.update_many({"folder_id": folder_id}, {"$set": {"folder_id": None}})
    return {"ok": True}


@api.post("/documents/bulk")
async def upload_documents_bulk(
    files: List[UploadFile] = File(...),
    category: str = Form("general"),
    folder_id: str = Form(""),
    user: dict = Depends(get_current_user),
):
    """Multi-file upload — returns the doc rows that succeeded + the names that failed."""
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="Pick at least one file.")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Max 50 files per batch.")
    folder = None
    if folder_id:
        folder = await db.document_folders.find_one({"id": folder_id, "is_deleted": {"$ne": True}})
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
    uploaded: list = []
    failed: list = []
    for f in files:
        try:
            ext = (f.filename.rsplit(".", 1)[-1] if f.filename and "." in f.filename else "bin").lower()
            if ext not in DOC_EXT and ext not in IMAGE_EXT:
                failed.append({"filename": f.filename, "reason": f"Unsupported type .{ext}"}); continue
            content_type = f.content_type or MIME_BY_EXT.get(ext, "application/octet-stream")
            data = await f.read()
            if len(data) > 25 * 1024 * 1024:
                failed.append({"filename": f.filename, "reason": "File over 25MB"}); continue
            path = f"{APP_NAME}/documents/{user['id']}/{uuid.uuid4()}.{ext}"
            result = put_object(path, data, content_type)
            doc = {
                "id": str(uuid.uuid4()),
                "title": f.filename,
                "category": category or "general",
                "description": "",
                "folder_id": folder_id or None,
                "storage_path": result["path"],
                "original_filename": f.filename,
                "content_type": content_type,
                "size": result.get("size", len(data)),
                "uploaded_by": user["id"],
                "uploaded_by_name": user.get("name", ""),
                "is_deleted": False,
                "created_at": iso(now_utc()),
            }
            await db.documents.insert_one(doc)
            uploaded.append(document_out(doc))
        except Exception as ex:
            logger.warning(f"Doc upload failed for {f.filename}: {ex}")
            failed.append({"filename": f.filename, "reason": str(ex)})
    return {"uploaded": uploaded, "failed": failed}

@api.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    category: str = Form("general"),
    description: str = Form(""),
    folder_id: str = Form(""),
    user: dict = Depends(get_current_user),
):
    ext = (file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "bin").lower()
    if ext not in DOC_EXT and ext not in IMAGE_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
    content_type = file.content_type or MIME_BY_EXT.get(ext, "application/octet-stream")
    path = f"{APP_NAME}/documents/{user['id']}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 25MB)")
    result = put_object(path, data, content_type)
    doc = {
        "id": str(uuid.uuid4()),
        "title": title or file.filename,
        "category": category or "general",
        "description": description,
        "folder_id": folder_id or None,
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "uploaded_by": user["id"],
        "uploaded_by_name": user.get("name", ""),
        "is_deleted": False,
        "created_at": iso(now_utc()),
    }
    await db.documents.insert_one(doc)
    return document_out(doc)

@api.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    d = await db.documents.find_one({"id": doc_id})
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    if d.get("uploaded_by") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.documents.update_one({"id": doc_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}

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

# ---------- Transactions / Payments / Donations ----------
def tx_out(t: dict) -> dict:
    return {
        "id": t["id"],
        "user_id": t["user_id"],
        "user_name": t.get("user_name", ""),
        "type": t.get("type", "fee"),
        "amount": t.get("amount", 0.0),
        "currency": t.get("currency", "USD"),
        "description": t.get("description", ""),
        "status": t.get("status", "completed"),
        "recorded_by": t.get("recorded_by"),
        "recorded_by_name": t.get("recorded_by_name", ""),
        "created_at": t.get("created_at"),
    }

@api.post("/transactions")
async def admin_create_transaction(body: TransactionIn, admin: dict = Depends(require_admin)):
    user = await db.users.find_one({"id": body.user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Member not found")
    doc = body.model_dump()
    doc.update({
        "id": str(uuid.uuid4()),
        "user_name": user.get("name", ""),
        "recorded_by": admin["id"],
        "recorded_by_name": admin.get("name", "Admin"),
        "created_at": iso(now_utc()),
    })
    await db.transactions.insert_one(doc)
    return tx_out(doc)

@api.get("/transactions")
async def admin_list_transactions(user_id: Optional[str] = None, type_filter: Optional[str] = None, admin: dict = Depends(require_admin)):
    query = {}
    if user_id:
        query["user_id"] = user_id
    if type_filter:
        query["type"] = type_filter
    if is_chapter_scoped(admin):
        ids = await chapter_scope_user_ids(admin)
        query["user_id"] = {"$in": ids or []}
    cursor = db.transactions.find(query, {"_id": 0}).sort("created_at", -1).limit(500)
    items = await cursor.to_list(500)
    return [tx_out(t) for t in items]

@api.delete("/transactions/{tx_id}")
async def admin_delete_transaction(tx_id: str, _: dict = Depends(require_admin)):
    res = await db.transactions.delete_one({"id": tx_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}

@api.get("/me/transactions")
async def my_transactions(user: dict = Depends(get_current_user)):
    cursor = db.transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(500)
    items = await cursor.to_list(500)
    return [tx_out(t) for t in items]

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
ANNUAL_DUES_USD = 60.0

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

    tier_cursor = db.users.aggregate([
        {"$match": user_q_extra} if scoped else {"$match": {}},
        {"$group": {"_id": "$membership_tier", "count": {"$sum": 1}}},
    ])
    by_tier = [{"tier": (d["_id"] or "standard"), "count": d["count"]} async for d in tier_cursor]

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

    inbox = {
        "hours_to_review": hours_to_review,
        "in_grace": in_grace,
        "new_members": new_members,
        "total": len(hours_to_review) + len(in_grace) + len(new_members),
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
    await db.award_grants.create_index([("award_id", 1), ("user_id", 1)], unique=True)
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
    await seed_builtin_automated_emails()
    await _ensure_site_settings()
    # Start background tasks
    asyncio.create_task(_chat_digest_loop())
    asyncio.create_task(_automated_email_loop())

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






# ---------- AOP Gear (catalog) ----------
class GearColorImage(BaseModel):
    color: str
    image_url: str = ""


class GearItemIn(BaseModel):
    name: str
    description: str = ""
    price: float = 0.0
    sizes: List[str] = []
    colors: List[str] = []
    color_images: List[GearColorImage] = []  # one image per color (admin tags)
    cover_image: str = ""
    images: List[str] = []
    category: str = "apparel"
    in_stock: bool = True
    sku: str = ""

class GearItemUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    sizes: Optional[List[str]] = None
    colors: Optional[List[str]] = None
    color_images: Optional[List[GearColorImage]] = None
    cover_image: Optional[str] = None
    images: Optional[List[str]] = None
    category: Optional[str] = None
    in_stock: Optional[bool] = None
    sku: Optional[str] = None

def gear_out(g: dict) -> dict:
    return {
        "id": g["id"],
        "name": g["name"],
        "description": g.get("description", ""),
        "price": g.get("price", 0.0),
        "sizes": g.get("sizes", []),
        "colors": g.get("colors", []),
        "color_images": g.get("color_images", []),
        "cover_image": g.get("cover_image", ""),
        "images": g.get("images", []),
        "category": g.get("category", "apparel"),
        "in_stock": g.get("in_stock", True),
        "sku": g.get("sku", ""),
        "created_at": g.get("created_at"),
    }

@api.get("/gear")
async def list_gear(category: Optional[str] = None):
    q = {}
    if category:
        q["category"] = category
    items = await db.gear.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [gear_out(g) for g in items]

@api.get("/gear/{item_id}")
async def get_gear(item_id: str):
    g = await db.gear.find_one({"id": item_id}, {"_id": 0})
    if not g:
        raise HTTPException(status_code=404, detail="Gear item not found")
    return gear_out(g)

@api.post("/gear")
async def create_gear(body: GearItemIn, _: dict = Depends(admin_tab_dep("gear"))):
    doc = body.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = iso(now_utc())
    await db.gear.insert_one(doc)
    return gear_out(doc)

@api.put("/gear/{item_id}")
async def update_gear(item_id: str, body: GearItemUpdateIn, _: dict = Depends(admin_tab_dep("gear"))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.gear.update_one({"id": item_id}, {"$set": updates})
    g = await db.gear.find_one({"id": item_id}, {"_id": 0})
    if not g:
        raise HTTPException(status_code=404, detail="Gear item not found")
    return gear_out(g)

@api.delete("/gear/{item_id}")
async def delete_gear(item_id: str, _: dict = Depends(admin_tab_dep("gear"))):
    await db.gear.delete_one({"id": item_id})
    return {"ok": True}


# ---------- Gear page settings (admin-editable hero/intro) ----------
class GearPageIn(BaseModel):
    hero_image: str = ""
    title: str = ""
    subtitle: str = ""
    intro: str = ""


@api.get("/gear-page")
async def get_gear_page():
    doc = await db.app_settings.find_one({"key": "gear_page"}, {"_id": 0})
    if not doc:
        return {"hero_image": "", "title": "", "subtitle": "", "intro": ""}
    return {
        "hero_image": doc.get("hero_image", ""),
        "title": doc.get("title", ""),
        "subtitle": doc.get("subtitle", ""),
        "intro": doc.get("intro", ""),
        "updated_at": doc.get("updated_at"),
    }


@api.put("/gear-page")
async def set_gear_page(body: GearPageIn, admin: dict = Depends(admin_tab_dep("gear"))):
    await db.app_settings.update_one(
        {"key": "gear_page"},
        {"$set": {
            "key": "gear_page",
            "hero_image": body.hero_image,
            "title": body.title,
            "subtitle": body.subtitle,
            "intro": body.intro,
            "updated_at": iso(now_utc()),
            "updated_by": admin.get("name", ""),
        }},
        upsert=True,
    )
    return {"ok": True, **body.model_dump()}


@api.post("/gear/upload")
async def gear_image_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("gear"))):
    """Admin uploads an image for a gear item (cover, gallery, or per-color photo)."""
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
    fname = (file.filename or "gear.jpg").replace("/", "_")
    ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
    if ext not in IMAGE_EXT:
        raise HTTPException(status_code=400, detail="Only images allowed (jpg, png, gif, webp)")
    content_type = file.content_type or MIME_BY_EXT.get(ext, "image/jpeg")
    file_id = str(uuid.uuid4())
    storage_path = f"gear/{file_id}/{fname}"
    await asyncio.to_thread(put_object, storage_path, data, content_type)
    await db.chat_files.insert_one({
        "id": file_id,
        "filename": fname,
        "storage_path": storage_path,
        "content_type": content_type,
        "size": total,
        "kind": "image",
        "uploaded_by": user["id"],
        "is_deleted": False,
        "created_at": iso(now_utc()),
    })
    return {"url": f"/api/files/{storage_path}", "size": total}


# ---------- Donations / Causes ----------
class CauseIn(BaseModel):
    title: str
    description: str = ""
    goal_amount: float = 0.0
    cover_image: str = ""
    is_active: bool = True
    deadline: Optional[str] = None
    category: str = "general"

class CauseUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    goal_amount: Optional[float] = None
    cover_image: Optional[str] = None
    is_active: Optional[bool] = None
    deadline: Optional[str] = None
    category: Optional[str] = None

class PledgeIn(BaseModel):
    amount: float = Field(gt=0)
    anonymous: bool = False
    note: str = ""

def cause_out(c: dict) -> dict:
    return {
        "id": c["id"],
        "title": c["title"],
        "description": c.get("description", ""),
        "goal_amount": c.get("goal_amount", 0.0),
        "raised_amount": c.get("raised_amount", 0.0),
        "donor_count": c.get("donor_count", 0),
        "cover_image": c.get("cover_image", ""),
        "is_active": c.get("is_active", True),
        "deadline": c.get("deadline"),
        "category": c.get("category", "general"),
        "created_at": c.get("created_at"),
    }

async def recompute_cause_totals(cause_id: str):
    """Sum completed donations against this cause."""
    agg = await db.transactions.aggregate([
        {"$match": {"cause_id": cause_id, "status": "completed", "type": "donation"}},
        {"$group": {"_id": "$cause_id", "raised": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    raised = agg[0]["raised"] if agg else 0.0
    count = agg[0]["count"] if agg else 0
    await db.causes.update_one({"id": cause_id}, {"$set": {"raised_amount": raised, "donor_count": count}})

@api.get("/causes")
async def list_causes(active_only: bool = False):
    q = {"is_active": True} if active_only else {}
    items = await db.causes.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [cause_out(c) for c in items]

@api.get("/causes/{cause_id}")
async def get_cause(cause_id: str):
    c = await db.causes.find_one({"id": cause_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Cause not found")
    return cause_out(c)

@api.post("/causes")
async def create_cause(body: CauseIn, _: dict = Depends(admin_tab_dep("causes"))):
    doc = body.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["raised_amount"] = 0.0
    doc["donor_count"] = 0
    doc["created_at"] = iso(now_utc())
    await db.causes.insert_one(doc)
    return cause_out(doc)

@api.put("/causes/{cause_id}")
async def update_cause(cause_id: str, body: CauseUpdateIn, _: dict = Depends(admin_tab_dep("causes"))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.causes.update_one({"id": cause_id}, {"$set": updates})
    c = await db.causes.find_one({"id": cause_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Cause not found")
    return cause_out(c)

@api.delete("/causes/{cause_id}")
async def delete_cause(cause_id: str, _: dict = Depends(admin_tab_dep("causes"))):
    await db.causes.delete_one({"id": cause_id})
    return {"ok": True}

@api.post("/causes/{cause_id}/pledge")
async def pledge_donation(cause_id: str, body: PledgeIn, user: dict = Depends(get_current_user)):
    """Record a pledge — used when user submits via manual / non-Stripe path.
    For PayPal-captured donations, the capture endpoint also writes the transaction."""
    cause = await db.causes.find_one({"id": cause_id}, {"_id": 0})
    if not cause:
        raise HTTPException(status_code=404, detail="Cause not found")
    tx = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_name": "Anonymous" if body.anonymous else user.get("name", ""),
        "type": "donation",
        "amount": body.amount,
        "currency": "USD",
        "description": f"Donation to {cause['title']}" + (f": {body.note}" if body.note else ""),
        "status": "pending",
        "cause_id": cause_id,
        "anonymous": body.anonymous,
        "method": "pledge",
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(tx)
    return {"transaction_id": tx["id"], "status": "pending"}

@api.get("/causes/{cause_id}/donations")
async def cause_donations(cause_id: str, admin: dict = Depends(admin_tab_dep("causes"))):
    q = {"cause_id": cause_id, "type": "donation"}
    if is_chapter_scoped(admin):
        ids = await chapter_scope_user_ids(admin)
        q["user_id"] = {"$in": ids or []}
    items = await db.transactions.find(
        q,
        {"_id": 0},
    ).sort("created_at", -1).to_list(500)
    return items


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
@api.get("/reports/members")
async def report_members(
    status_filter: Optional[str] = None,
    chapter_id: Optional[str] = None,
    tier_id: Optional[str] = None,
    role: Optional[str] = None,
    admin: dict = Depends(admin_tab_dep("reports")),
):
    q: dict = {}
    if chapter_id:
        q["chapter_id"] = chapter_id
    if tier_id:
        q["tier_id"] = tier_id
    if role:
        q["role"] = role
    if is_chapter_scoped(admin):
        q["chapter_id"] = admin.get("chapter_id") or "__none__"
    cursor = db.users.find(q, {"_id": 0, "password_hash": 0}).sort("created_at", -1)
    users = await cursor.to_list(2000)
    out = [public_user(u) for u in users]
    if status_filter:
        out = [u for u in out if u.get("status") == status_filter]
    # Enrich with attended events + guests they registered
    for u in out:
        # Events attended (check-ins)
        cks = await db.checkins.find({"user_id": u["id"]}, {"_id": 0, "event_id": 1, "event_title": 1, "ticket_type": 1, "checked_in_at": 1}).to_list(500)
        u["events_attended_count"] = len(cks)
        u["events_attended"] = [{"event_id": c["event_id"], "title": c.get("event_title", ""), "ticket_type": c.get("ticket_type"), "checked_in_at": c.get("checked_in_at")} for c in cks]
        # Guests registered across their RSVPs
        rsvps = await db.rsvps.find({"user_id": u["id"]}, {"_id": 0, "event_id": 1, "guests": 1}).to_list(500)
        all_guests = []
        for r in rsvps:
            for g in (r.get("guests") or []):
                all_guests.append({"event_id": r["event_id"], "name": g.get("name", ""), "email": g.get("email", ""), "phone": g.get("phone", "")})
        u["guests_registered_count"] = len(all_guests)
        u["guests_registered"] = all_guests
    return out


@api.get("/reports/rsvps")
async def report_rsvps(
    event_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
    admin: dict = Depends(admin_tab_dep("reports")),
):
    """Report of all RSVPs (members + their guests) for events / sub-events.
    Optional filter by event_id (single event) or parent_event_id (all sub-events under a parent).
    Each row: member, event, RSVP date, ticket_type (from check-in if present), guests list."""
    event_q: dict = {}
    if event_id:
        event_q["id"] = event_id
    elif parent_event_id:
        # parent event itself + all its sub-events
        event_q["$or"] = [{"id": parent_event_id}, {"parent_event_id": parent_event_id}]
    events_for_filter = []
    if event_q:
        events_for_filter = await db.events.find(event_q, {"_id": 0, "id": 1, "title": 1, "start_at": 1}).to_list(200)
        event_ids = [e["id"] for e in events_for_filter]
        if not event_ids:
            return []
        rsvp_q = {"event_id": {"$in": event_ids}}
    else:
        rsvp_q = {}
    # Chapter-scope: limit by users in scope
    if is_chapter_scoped(admin):
        chapter_uids = await chapter_scope_user_ids(admin) or []
        rsvp_q["user_id"] = {"$in": chapter_uids}
    cursor = db.rsvps.find(rsvp_q, {"_id": 0}).sort("created_at", -1).limit(5000)
    rsvps = await cursor.to_list(5000)
    # Build event title cache
    if not events_for_filter:
        all_event_ids = list({r["event_id"] for r in rsvps})
        cur = db.events.find({"id": {"$in": all_event_ids}}, {"_id": 0, "id": 1, "title": 1, "start_at": 1})
        events_for_filter = await cur.to_list(2000)
    event_by_id = {e["id"]: e for e in events_for_filter}
    rows = []
    for r in rsvps:
        ev = event_by_id.get(r["event_id"], {})
        # Look up admin check-in for this user+event to get assigned ticket_type, if any
        ck = await db.checkins.find_one({"event_id": r["event_id"], "user_id": r["user_id"]}, {"_id": 0, "ticket_type": 1, "checked_in_at": 1})
        rows.append({
            "rsvp_id": r["id"],
            "event_id": r["event_id"],
            "event_title": ev.get("title", ""),
            "event_start_at": ev.get("start_at"),
            "user_id": r["user_id"],
            "user_name": r.get("user_name", ""),
            "rsvped_at": r.get("created_at"),
            "guests": r.get("guests", []) or [],
            "guest_count": len(r.get("guests", []) or []),
            "ticket_type": (ck or {}).get("ticket_type"),
            "checked_in_at": (ck or {}).get("checked_in_at"),
        })
    return rows


@api.get("/reports/hours")
async def report_hours(
    status_filter: Optional[str] = None,
    user_id: Optional[str] = None,
    event_type: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    admin: dict = Depends(admin_tab_dep("reports")),
):
    q: dict = {}
    if status_filter:
        q["status"] = status_filter
    if user_id:
        q["user_id"] = user_id
    if event_type:
        q["event_type"] = event_type
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date
    if is_chapter_scoped(admin):
        ids = await chapter_scope_user_ids(admin)
        q["user_id"] = {"$in": ids or []}
    cursor = db.volunteer_hours.find(q, {"_id": 0}).sort("date", -1).limit(2000)
    items = await cursor.to_list(2000)
    return [hours_out(h) for h in items]

@api.get("/reports/donations")
async def report_donations(
    cause_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    admin: dict = Depends(admin_tab_dep("reports")),
):
    q: dict = {"type": "donation"}
    if cause_id:
        q["cause_id"] = cause_id
    if status_filter:
        q["status"] = status_filter
    if is_chapter_scoped(admin):
        ids = await chapter_scope_user_ids(admin)
        q["user_id"] = {"$in": ids or []}
    items = await db.transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return items

@api.get("/reports/personnel-brief/{user_id}")
async def personnel_brief(user_id: str, _: dict = Depends(admin_tab_dep("reports"))):
    """Compiles everything for a printable member brief."""
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    member = public_user(u)

    chapter = None
    if u.get("chapter_id"):
        cdoc = await db.chapters.find_one({"id": u["chapter_id"]}, {"_id": 0})
        chapter = chapter_out(cdoc) if cdoc else None

    tier = None
    if u.get("tier_id"):
        tdoc = await db.tiers.find_one({"id": u["tier_id"]}, {"_id": 0})
        tier = tier_out(tdoc) if tdoc else None

    grants = await db.award_grants.find({"user_id": user_id}, {"_id": 0}).sort("granted_at", -1).to_list(200)
    hours_items = await db.volunteer_hours.find({"user_id": user_id}, {"_id": 0}).sort("date", -1).to_list(500)
    hours_clean = [hours_out(h) for h in hours_items]
    approved_hours = sum(h["hours"] for h in hours_clean if h["status"] == "approved")
    pending_hours = sum(h["hours"] for h in hours_clean if h["status"] == "pending")

    rsvps = await db.rsvps.find({"user_id": user_id}, {"_id": 0}).to_list(500)
    event_ids = [r.get("event_id") for r in rsvps if r.get("event_id")]
    events_attended = []
    if event_ids:
        events_attended = await db.events.find({"id": {"$in": event_ids}}, {"_id": 0}).sort("start_at", -1).to_list(500)

    checkins = await db.checkins.find({"user_id": user_id}, {"_id": 0}).sort("checked_in_at", -1).to_list(500)

    txs = await db.transactions.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    total_paid = sum(t.get("amount", 0.0) for t in txs if t.get("status") == "completed" and t.get("type") in ("renewal", "donation", "fee", "gear"))

    return {
        "member": member,
        "chapter": chapter,
        "tier": tier,
        "awards": grants,
        "awards_count": len(grants),
        "hours": hours_clean,
        "approved_hours": approved_hours,
        "pending_hours": pending_hours,
        "events": events_attended,
        "events_count": len(events_attended),
        "checkins": checkins,
        "transactions": txs,
        "total_paid": total_paid,
        "generated_at": iso(now_utc()),
    }


@api.get("/reports/personnel-brief/{user_id}/pdf")
async def personnel_brief_pdf(user_id: str, admin: dict = Depends(admin_tab_dep("reports"))):
    """Generates a printable PDF version of the personnel brief."""
    # Reuse the same data-gathering as the JSON endpoint by calling it directly.
    data = await personnel_brief(user_id, admin)
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from io import BytesIO

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch, topMargin=0.7 * inch, bottomMargin=0.6 * inch, title=f"Personnel Brief — {data['member']['name']}")
    styles = getSampleStyleSheet()
    AOP_RED = colors.HexColor("#C8102E")
    AOP_NAVY = colors.HexColor("#0C1B33")
    h1 = ParagraphStyle("AopH1", parent=styles["Heading1"], textColor=AOP_RED, fontSize=22, leading=26, spaceAfter=4)
    h2 = ParagraphStyle("AopH2", parent=styles["Heading2"], textColor=AOP_NAVY, fontSize=13, leading=16, spaceBefore=14, spaceAfter=6)
    body_style = ParagraphStyle("AopBody", parent=styles["BodyText"], fontSize=10, leading=14)
    small = ParagraphStyle("AopSmall", parent=styles["BodyText"], fontSize=8, leading=11, textColor=colors.HexColor("#999999"))

    m = data["member"]
    chapter = data.get("chapter") or {}
    tier = data.get("tier") or {}
    elements = []

    # Header
    elements.append(Paragraph(f"<b>{m.get('name', '—')}</b>", h1))
    if m.get("line_name"):
        elements.append(Paragraph(f'<font color="#C8102E"><b>"{m["line_name"]}"</b></font>', body_style))
    sub = " · ".join([s for s in [tier.get("name"), chapter.get("name"), m.get("role", "").upper()] if s])
    if sub:
        elements.append(Paragraph(sub, small))
    elements.append(Paragraph(f"Personnel Brief generated {data['generated_at'][:10]}", small))
    elements.append(Spacer(1, 12))

    # Identity table
    rows = [
        ["Email", m.get("email", "—")],
        ["Phone", m.get("phone", "—")],
        ["Address", ", ".join(x for x in [m.get("address"), m.get("city"), m.get("state"), m.get("zip_code")] if x) or "—"],
        ["Country", m.get("country") or "—"],
        ["Branch of Service", m.get("branch_of_service") or "—"],
        ["Intake Line", m.get("intake_line") or "—"],
        ["Intake Completed", m.get("intake_completed_at") or "—"],
        ["Date Joined", (m.get("join_date") or "")[:10] or "—"],
        ["Membership Expires", (m.get("membership_expires_at") or "")[:10] or "—"],
        ["Status", (m.get("status") or "").upper()],
    ]
    t = Table(rows, colWidths=[1.4 * inch, 4.5 * inch], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#666666")),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#222222")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#EFEFEF")),
    ]))
    elements.append(t)

    # Stats strip
    elements.append(Paragraph("Service Summary", h2))
    stats = Table([
        ["Approved hours", f"{data.get('approved_hours', 0):.1f}", "Awards", str(data.get("awards_count", 0))],
        ["Events attended", str(data.get("events_count", 0)), "Total contributed", f"${data.get('total_paid', 0):.2f}"],
    ], colWidths=[1.4 * inch, 1.6 * inch, 1.4 * inch, 1.6 * inch])
    stats.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F5F0")),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#666666")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#666666")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(stats)

    # Awards
    if data.get("awards"):
        elements.append(Paragraph("Awards & Ribbons", h2))
        for g in data["awards"][:30]:
            elements.append(Paragraph(f"<b>{g.get('award_name') or g.get('name', '—')}</b> &nbsp; <font color='#999999'>{(g.get('granted_at') or '')[:10]}</font>", body_style))
            if g.get("note"):
                elements.append(Paragraph(g["note"], small))
            elements.append(Spacer(1, 4))

    # Hours
    if data.get("hours"):
        elements.append(Paragraph("Volunteer Hours", h2))
        hours_rows = [["Date", "Hours", "Status", "Activity"]]
        for h in data["hours"][:40]:
            hours_rows.append([
                (h.get("date") or "")[:10],
                f"{h.get('hours', 0):.2f}",
                (h.get("status") or "").upper(),
                (h.get("activity") or h.get("description") or "—")[:60],
            ])
        ht = Table(hours_rows, colWidths=[0.9 * inch, 0.7 * inch, 0.9 * inch, 3.5 * inch])
        ht.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0EBE3")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#EFEFEF")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(ht)

    # Events attended
    if data.get("events"):
        elements.append(Paragraph("Events Attended", h2))
        for e in data["events"][:40]:
            when = (e.get("start_at") or "")[:10]
            elements.append(Paragraph(f"<b>{e.get('title', '—')}</b> &nbsp; <font color='#999999'>{when}</font>", body_style))
        elements.append(Spacer(1, 4))

    # Transactions
    if data.get("transactions"):
        elements.append(Paragraph("Transactions", h2))
        tx_rows = [["Date", "Type", "Amount", "Status", "Note"]]
        for t in data["transactions"][:40]:
            tx_rows.append([
                (t.get("created_at") or "")[:10],
                (t.get("type") or "").upper(),
                f"${t.get('amount', 0):.2f}",
                (t.get("status") or ""),
                (t.get("note") or t.get("description") or "")[:50],
            ])
        tx_tbl = Table(tx_rows, colWidths=[0.9 * inch, 0.8 * inch, 0.9 * inch, 0.9 * inch, 2.5 * inch])
        tx_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0EBE3")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#EFEFEF")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(tx_tbl)

    elements.append(Spacer(1, 16))
    elements.append(Paragraph("Generated by the Alpha Omega Phi member portal.", small))

    doc.build(elements)
    buf.seek(0)
    safe_name = (m.get("name") or "member").replace(" ", "_")
    filename = f"personnel-brief-{safe_name}-{data['generated_at'][:10]}.pdf"
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- Seed Phase B sample data (idempotent) ----------
async def seed_phase_b():
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
if RESEND_API_KEY:
    resend_sdk.api_key = RESEND_API_KEY

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


# ---------- Email Blasts (Resend) ----------
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
    # Segment filters
    segment: Literal["all", "active", "lifetime", "alumni", "admins", "tier", "chapter", "custom"] = "active"
    tier_id: Optional[str] = None
    chapter_id: Optional[str] = None
    custom_user_ids: List[str] = []
    test_only: bool = False  # if True, send only to admin

def template_out(t: dict) -> dict:
    return {
        "id": t["id"],
        "name": t["name"],
        "subject": t["subject"],
        "body_html": t["body_html"],
        "description": t.get("description", ""),
        "created_at": t.get("created_at"),
    }

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


async def resolve_segment(body: EmailBlastIn) -> List[dict]:
    q: dict = {}
    if body.segment == "admins":
        q["role"] = "admin"
    elif body.segment == "tier" and body.tier_id:
        q["tier_id"] = body.tier_id
    elif body.segment == "chapter" and body.chapter_id:
        q["chapter_id"] = body.chapter_id
    elif body.segment == "custom" and body.custom_user_ids:
        q["id"] = {"$in": body.custom_user_ids}
    elif body.segment == "active":
        q["status_override"] = {"$ne": "deceased"}
    cursor = db.users.find(q, {"_id": 0, "password_hash": 0}).limit(2000)
    return await cursor.to_list(2000)


def render_template(body_html: str, recipient: dict) -> str:
    """Replace simple variables: {{name}}, {{first_name}}, {{email}}, {{line_name}}.
    HTML-escapes values to prevent XSS via member names."""
    import html as _html
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


@api.post("/email/preview")
async def email_preview(body: EmailBlastIn, user: dict = Depends(admin_tab_dep("email"))):
    """Render the blast for the current admin user as preview (no send)."""
    recipients = await resolve_segment(body)
    sample = recipients[0] if recipients else user
    html = render_template(body.body_html, sample)
    return {
        "subject": body.subject.replace("{{name}}", sample.get("name", "")),
        "html": html,
        "recipient_count": len(recipients),
        "sample_recipient": {"name": sample.get("name", ""), "email": sample.get("email", "")},
    }


@api.post("/email/blast")
async def send_email_blast(body: EmailBlastIn, user: dict = Depends(admin_tab_dep("email"))):
    if not RESEND_API_KEY:
        raise HTTPException(status_code=503, detail="Email service not configured")
    recipients = await resolve_segment(body)
    if body.test_only:
        recipients = [user]
    if not recipients:
        raise HTTPException(status_code=400, detail="Segment has no recipients")

    blast_id = str(uuid.uuid4())
    sent: List[dict] = []
    failed: List[dict] = []

    for r in recipients:
        email = (r.get("email") or "").strip()
        if not email:
            failed.append({"user_id": r.get("id"), "reason": "no email"})
            continue
        try:
            params = {
                "from": RESEND_FROM,
                "to": [email],
                "subject": body.subject.replace("{{name}}", r.get("name", "")),
                "html": render_template(body.body_html, r),
                "tags": [{"name": "blast_id", "value": blast_id}],
            }
            res = await asyncio.to_thread(resend_sdk.Emails.send, params)
            sent.append({"user_id": r.get("id"), "email": email, "resend_id": res.get("id")})
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
        "sent_count": len(sent),
        "failed_count": len(failed),
        "sent_to": [s["email"] for s in sent[:100]],
        "failed": failed[:50],
        "sent_by": user["id"],
        "sent_by_name": user.get("name", "Admin"),
        "sent_at": iso(now_utc()),
    }
    await db.email_blasts.insert_one(log)
    return {"blast_id": blast_id, "sent": len(sent), "failed": len(failed)}


@api.get("/email/blasts")
async def list_email_blasts(_: dict = Depends(admin_tab_dep("email"))):
    items = await db.email_blasts.find({}, {"_id": 0}).sort("sent_at", -1).limit(100).to_list(100)
    return items


class EmailTestSendIn(BaseModel):
    to_email: str
    subject: Optional[str] = None
    body_html: Optional[str] = None
    template_id: Optional[str] = None


@api.post("/email/test-send")
async def email_test_send(body: EmailTestSendIn, admin: dict = Depends(admin_tab_dep("email"))):
    """Send a one-off test email so admins can validate Resend deliverability
    without having to approve a real applicant or queue a blast. If template_id
    is provided, the template's subject + body_html are used (with {{variables}}
    rendered against the admin's own profile as the sample recipient)."""
    to_email = (body.to_email or "").strip()
    if not to_email or "@" not in to_email:
        raise HTTPException(status_code=400, detail="A valid recipient email is required.")
    if not RESEND_API_KEY:
        raise HTTPException(status_code=503, detail="Resend API key not configured on the server (RESEND_API_KEY).")
    import html as _h
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
    # Render {{variables}} against the admin so the preview looks realistic
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
        html_body = render_template(html_body, sample)
    if not subject:
        subject = "Alpha Omega Phi — Test email"
    admin_name = _h.escape(admin.get("name") or "an admin")
    if not html_body:
        html_body = (
            f"""
            <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:32px;color:#222">
              <h1 style="color:#C8102E;margin:0 0 12px;font-size:24px">Resend deliverability check</h1>
              <p style="line-height:1.6">This is a test email sent by <strong>{admin_name}</strong> from the Alpha Omega Phi member portal to confirm that Resend is configured correctly and emails reach inboxes.</p>
              <p style="line-height:1.6">If you can read this in your inbox, the integration is working.</p>
              <p style="font-size:12px;color:#888;margin-top:24px">Sender: <code>{_h.escape(RESEND_FROM)}</code></p>
            </div>
            """
        )
    try:
        resp = await asyncio.to_thread(resend_sdk.Emails.send, {
            "from": RESEND_FROM,
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
        logger.info(f"Test email sent by {admin.get('email')} to {to_email} from {RESEND_FROM} (template={template_name or 'none'})")
        return {
            "ok": True,
            "detail": "Test email accepted by Resend.",
            "to": to_email,
            "from": RESEND_FROM,
            "subject": subject,
            "template_name": template_name,
            "message_id": message_id,
        }
    except Exception as e:
        msg = str(e)
        logger.warning(f"Test email FAILED to {to_email} (from={RESEND_FROM}): {msg}")
        return {
            "ok": False,
            "detail": msg,
            "to": to_email,
            "from": RESEND_FROM,
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
# PHASE D — Chat: conversations, messages, file uploads, WebSocket
# ============================================================
from fastapi import WebSocket, WebSocketDisconnect, UploadFile, File, Form
import jwt as _pyjwt

# Connection manager — in-memory per-user websocket pool
class ChatHub:
    def __init__(self):
        self.connections: dict[str, set[WebSocket]] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.connections.setdefault(user_id, set()).add(ws)

    def disconnect(self, user_id: str, ws: WebSocket):
        if user_id in self.connections:
            self.connections[user_id].discard(ws)
            if not self.connections[user_id]:
                self.connections.pop(user_id, None)

    async def push(self, user_ids: List[str], event: dict):
        dead = []
        for uid in user_ids:
            for ws in list(self.connections.get(uid, set())):
                try:
                    await ws.send_json(event)
                except Exception:
                    dead.append((uid, ws))
        for uid, ws in dead:
            self.disconnect(uid, ws)

chat_hub = ChatHub()


TTL_CHOICES = {"off": 0, "1h": 3600, "24h": 86400, "7d": 604800}
TTL_VALUES = set(TTL_CHOICES.keys())


def _ttl_choice_to_seconds(v: Optional[str]) -> int:
    if not v: return 0
    return TTL_CHOICES.get(v, 0)


# ---------- Pydantic models ----------
class ConversationCreateIn(BaseModel):
    member_ids: List[str]  # other members (the current user is auto-included)
    name: Optional[str] = None
    avatar_url: Optional[str] = None  # group photo (any member can change later)
    type: Optional[Literal["dm", "group"]] = None  # auto-detected if None
    ttl: Optional[Literal["off", "1h", "24h", "7d"]] = "off"

class ConversationUpdateIn(BaseModel):
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    add_member_ids: Optional[List[str]] = None
    remove_member_ids: Optional[List[str]] = None
    ttl: Optional[Literal["off", "1h", "24h", "7d"]] = None

class MessageIn(BaseModel):
    body: str = ""
    attachments: List[dict] = []
    reply_to: Optional[str] = None
    ttl: Optional[Literal["off", "1h", "24h", "7d"]] = None  # override conversation default


def _now_iso():
    return iso(now_utc())


async def _user_brief(user_id: str) -> dict:
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        return {"id": user_id, "name": "Unknown", "avatar_url": ""}
    return {"id": u["id"], "name": u.get("name", ""), "avatar_url": u.get("avatar_url", ""), "email": u.get("email", "")}


async def conversation_out(c: dict, viewer_id: str) -> dict:
    member_briefs = []
    for mid in c.get("member_ids", []):
        member_briefs.append(await _user_brief(mid))
    title = c.get("name")
    avatar = c.get("avatar_url", "")
    if not title:
        if c.get("type") == "dm":
            other = next((m for m in member_briefs if m["id"] != viewer_id), member_briefs[0] if member_briefs else None)
            title = other["name"] if other else "Direct message"
            avatar = avatar or (other.get("avatar_url", "") if other else "")
        else:
            names = [m["name"].split(" ")[0] for m in member_briefs if m["id"] != viewer_id]
            title = ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
    return {
        "id": c["id"],
        "type": c.get("type", "group"),
        "name": title,
        "raw_name": c.get("name"),
        "avatar_url": avatar,
        "members": member_briefs,
        "member_ids": c.get("member_ids", []),
        "created_by": c.get("created_by"),
        "created_at": c.get("created_at"),
        "last_message_at": c.get("last_message_at"),
        "last_message_preview": c.get("last_message_preview", ""),
        "last_read_at": c.get("read_state", {}).get(viewer_id),
        "ttl": c.get("ttl", "off"),
    }


def _is_message_expired(m: dict, viewer_id: str) -> bool:
    """A disappearing message expires {ttl_seconds} after the first time ANY
    recipient (other than the sender) read it."""
    ttl = int(m.get("ttl_seconds") or 0)
    if ttl <= 0:
        return False
    first_seen = m.get("first_read_at")
    if not first_seen:
        return False  # not yet seen by anyone → keep showing
    # Sender always sees their own (until expiry too — keeps semantics symmetrical)
    try:
        seen_at = datetime.fromisoformat(first_seen)
    except Exception:
        return False
    return (now_utc() - seen_at).total_seconds() >= ttl


def message_out(m: dict, viewer_id: str = "") -> dict:
    return {
        "id": m["id"],
        "conversation_id": m["conversation_id"],
        "sender_id": m["sender_id"],
        "sender_name": m.get("sender_name", ""),
        "sender_avatar": m.get("sender_avatar", ""),
        "body": m.get("body", ""),
        "attachments": m.get("attachments", []),
        "reply_to": m.get("reply_to"),
        "created_at": m.get("created_at"),
        "edited_at": m.get("edited_at"),
        "deleted_at": m.get("deleted_at"),
        "ttl_seconds": int(m.get("ttl_seconds") or 0),
        "first_read_at": m.get("first_read_at"),
        "expires_at": m.get("expires_at"),
    }


# ---------- Conversations ----------
@api.get("/conversations")
async def list_conversations(user: dict = Depends(get_current_user)):
    cursor = db.conversations.find(
        {"member_ids": user["id"]},
        {"_id": 0},
    ).sort([("last_message_at", -1), ("created_at", -1)])
    items = await cursor.to_list(500)
    return [await conversation_out(c, user["id"]) for c in items]


@api.post("/conversations")
async def create_conversation(body: ConversationCreateIn, user: dict = Depends(get_current_user)):
    members = list({user["id"], *body.member_ids})
    if len(members) < 2:
        raise HTTPException(status_code=400, detail="Pick at least one other member")
    # Verify all are valid users
    valid = await db.users.count_documents({"id": {"$in": members}})
    if valid != len(members):
        raise HTTPException(status_code=400, detail="Some members not found")
    ctype = body.type or ("dm" if len(members) == 2 else "group")
    if ctype == "dm" and len(members) == 2:
        # Re-use existing DM if one exists
        existing = await db.conversations.find_one({"type": "dm", "member_ids": {"$all": members, "$size": 2}})
        if existing:
            return await conversation_out(existing, user["id"])
    doc = {
        "id": str(uuid.uuid4()),
        "type": ctype,
        "name": body.name,
        "avatar_url": body.avatar_url or "",
        "member_ids": members,
        "created_by": user["id"],
        "ttl": body.ttl or "off",
        "created_at": _now_iso(),
        "last_message_at": _now_iso(),
        "last_message_preview": "",
        "read_state": {user["id"]: _now_iso()},
    }
    await db.conversations.insert_one(doc)
    await chat_hub.push(members, {"type": "conversation:created", "conversation": await conversation_out(doc, user["id"])})
    return await conversation_out(doc, user["id"])


@api.get("/conversations/{cid}")
async def get_conversation(cid: str, user: dict = Depends(get_current_user)):
    c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return await conversation_out(c, user["id"])


@api.put("/conversations/{cid}")
async def update_conversation(cid: str, body: ConversationUpdateIn, user: dict = Depends(get_current_user)):
    c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
    if not c:
        raise HTTPException(status_code=404, detail="Conversation not found")
    sets: dict = {}
    if body.name is not None:
        sets["name"] = body.name
    if body.avatar_url is not None:
        sets["avatar_url"] = body.avatar_url
    if body.ttl is not None:
        sets["ttl"] = body.ttl
    # member changes only allowed in group chats
    if c.get("type") == "group":
        members = set(c.get("member_ids", []))
        if body.add_member_ids:
            members.update(body.add_member_ids)
        if body.remove_member_ids:
            for rid in body.remove_member_ids:
                members.discard(rid)
        members.add(user["id"])  # don't let editor remove themselves here
        if members != set(c.get("member_ids", [])):
            sets["member_ids"] = list(members)
    if sets:
        await db.conversations.update_one({"id": cid}, {"$set": sets})
    c2 = await db.conversations.find_one({"id": cid}, {"_id": 0})
    payload = await conversation_out(c2, user["id"])
    await chat_hub.push(c2.get("member_ids", []), {"type": "conversation:updated", "conversation": payload})
    return payload


@api.post("/conversations/{cid}/leave")
async def leave_conversation(cid: str, user: dict = Depends(get_current_user)):
    c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
    if not c:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if c.get("type") == "dm":
        raise HTTPException(status_code=400, detail="DMs can't be left — use delete")
    new_members = [m for m in c.get("member_ids", []) if m != user["id"]]
    if not new_members:
        await db.conversations.delete_one({"id": cid})
        await db.messages.delete_many({"conversation_id": cid})
        return {"ok": True, "deleted": True}
    await db.conversations.update_one({"id": cid}, {"$set": {"member_ids": new_members}})
    await chat_hub.push(c.get("member_ids", []), {"type": "conversation:member_left", "conversation_id": cid, "user_id": user["id"]})
    return {"ok": True}


@api.delete("/conversations/{cid}")
async def delete_conversation(cid: str, user: dict = Depends(get_current_user)):
    c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
    if not c:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if c.get("created_by") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only the creator or an admin can delete this conversation")
    await db.conversations.delete_one({"id": cid})
    await db.messages.delete_many({"conversation_id": cid})
    await chat_hub.push(c.get("member_ids", []), {"type": "conversation:deleted", "conversation_id": cid})
    return {"ok": True}


@api.post("/conversations/{cid}/read")
async def mark_read(cid: str, user: dict = Depends(get_current_user)):
    c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
    if not c:
        raise HTTPException(status_code=404, detail="Conversation not found")
    now_iso = _now_iso()
    await db.conversations.update_one({"id": cid}, {"$set": {f"read_state.{user['id']}": now_iso}})
    # Stamp first_read_at on any disappearing messages this viewer hasn't seen yet.
    # We only want the FIRST recipient (other than the sender) to start the timer.
    await db.messages.update_many(
        {
            "conversation_id": cid,
            "ttl_seconds": {"$gt": 0},
            "first_read_at": None,
            "sender_id": {"$ne": user["id"]},
        },
        {"$set": {"first_read_at": now_iso}},
    )
    # Cancel any pending email digest notifications for this user+conversation
    await db.chat_notifications.update_many(
        {"recipient_id": user["id"], "conversation_id": cid, "status": "pending"},
        {"$set": {"status": "cancelled", "cancelled_at": now_iso}},
    )
    return {"ok": True}


# ---------- Messages ----------
@api.get("/conversations/{cid}/messages")
async def list_messages(
    cid: str,
    before: Optional[str] = None,
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
    if not c:
        raise HTTPException(status_code=404, detail="Conversation not found")
    q: dict = {"conversation_id": cid, "deleted_at": None}
    if before:
        q["created_at"] = {"$lt": before}
    items = await db.messages.find(q, {"_id": 0}).sort("created_at", -1).limit(min(limit, 100)).to_list(100)
    items.reverse()
    # Drop expired disappearing messages (and best-effort cleanup so DB doesn't bloat)
    keep = []
    expired_ids = []
    for m in items:
        if _is_message_expired(m, user["id"]):
            expired_ids.append(m["id"])
        else:
            keep.append(m)
    if expired_ids:
        # Soft-delete (mirrors how regular deletes work)
        asyncio.create_task(db.messages.update_many(
            {"id": {"$in": expired_ids}},
            {"$set": {"deleted_at": _now_iso(), "body": "", "attachments": []}},
        ))
    return [message_out(m, user["id"]) for m in keep]


@api.post("/conversations/{cid}/messages")
async def send_message(cid: str, body: MessageIn, user: dict = Depends(get_current_user)):
    c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
    if not c:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not body.body.strip() and not body.attachments:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    # Resolve TTL: per-message override > conversation default
    effective_ttl_choice = body.ttl if body.ttl is not None else c.get("ttl", "off")
    ttl_seconds = _ttl_choice_to_seconds(effective_ttl_choice)
    doc = {
        "id": str(uuid.uuid4()),
        "conversation_id": cid,
        "sender_id": user["id"],
        "sender_name": user.get("name", ""),
        "sender_avatar": user.get("avatar_url", ""),
        "body": body.body,
        "attachments": body.attachments,
        "reply_to": body.reply_to,
        "ttl_seconds": ttl_seconds,
        "first_read_at": None,
        "created_at": _now_iso(),
        "edited_at": None,
        "deleted_at": None,
    }
    await db.messages.insert_one(doc)
    preview = body.body if body.body else (f"📎 {body.attachments[0].get('filename', 'Attachment')}" if body.attachments else "")
    await db.conversations.update_one(
        {"id": cid},
        {"$set": {"last_message_at": doc["created_at"], "last_message_preview": preview[:140], f"read_state.{user['id']}": doc["created_at"]}},
    )
    payload = message_out(doc, user["id"])
    await chat_hub.push(c.get("member_ids", []), {"type": "message:new", "message": payload})
    # Queue email digest notifications for offline recipients (debounced 5 min — cancelled when they read)
    try:
        await queue_chat_notifications(c, doc, user)
    except Exception as e:
        logger.warning(f"queue_chat_notifications failed: {e}")
    return payload


@api.delete("/messages/{mid}")
async def delete_message(mid: str, user: dict = Depends(get_current_user)):
    m = await db.messages.find_one({"id": mid})
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    if m["sender_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.messages.update_one({"id": mid}, {"$set": {"deleted_at": _now_iso(), "body": "", "attachments": []}})
    c = await db.conversations.find_one({"id": m["conversation_id"]})
    if c:
        await chat_hub.push(c.get("member_ids", []), {"type": "message:deleted", "message_id": mid, "conversation_id": m["conversation_id"]})
    return {"ok": True}


# ---------- File uploads (chat) ----------
CHAT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB

@api.post("/chat/upload")
async def chat_upload(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    # Read in chunks to enforce size limit without blowing memory
    chunks = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > CHAT_MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"File exceeds {CHAT_MAX_UPLOAD_BYTES // (1024*1024)} MB limit")
        chunks.append(chunk)
    data = b"".join(chunks)
    fname = (file.filename or "file").replace("/", "_")
    ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
    content_type = file.content_type or MIME_BY_EXT.get(ext, "application/octet-stream")
    file_id = str(uuid.uuid4())
    storage_path = f"chat/{user['id']}/{file_id}/{fname}"

    def _put():
        return put_object(storage_path, data, content_type)
    await asyncio.to_thread(_put)

    kind = "image" if ext in IMAGE_EXT else "video" if ext in {"mp4", "mov", "webm", "avi"} else "audio" if ext in {"mp3", "wav", "ogg", "m4a"} else "file"
    rec = {
        "id": file_id,
        "filename": fname,
        "storage_path": storage_path,
        "content_type": content_type,
        "size": total,
        "kind": kind,
        "uploaded_by": user["id"],
        "is_deleted": False,
        "created_at": _now_iso(),
    }
    await db.chat_files.insert_one(rec)
    return {
        "id": file_id,
        "filename": fname,
        "url": f"/api/files/{storage_path}",
        "size": total,
        "content_type": content_type,
        "kind": kind,
    }


# ---------- WebSocket ----------
def _decode_jwt(token: str) -> Optional[dict]:
    try:
        payload = _pyjwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
        return payload
    except Exception:
        return None


@app.websocket("/api/ws/chat")
async def chat_ws(ws: WebSocket):
    # Browser sends cookies automatically for same-origin WS; preview is HTTPS so wss is required
    token = ws.cookies.get("access_token")
    payload = _decode_jwt(token) if token else None
    if not payload or not payload.get("sub"):
        await ws.close(code=4401)
        return
    user_id = payload["sub"]
    u = await db.users.find_one({"id": user_id})
    if not u:
        await ws.close(code=4401)
        return
    await chat_hub.connect(user_id, ws)
    try:
        await ws.send_json({"type": "connected", "user_id": user_id})
        while True:
            # We mostly push from server -> client. Allow ping from client to keep alive.
            msg = await ws.receive_json()
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WS error for {user_id}: {e}")
    finally:
        chat_hub.disconnect(user_id, ws)


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
    """Replace tiers with the canonical AOP list. Members on legacy tiers get
    migrated to 'Regular Member' (the closest default)."""
    # First make sure canonical tiers exist (so we have a default to migrate to)
    for spec in AOP_TIERS:
        existing = await db.tiers.find_one({"name": spec["name"]})
        if existing:
            await db.tiers.update_one({"id": existing["id"]}, {"$set": spec})
        else:
            doc = {**spec, "id": str(uuid.uuid4()), "created_at": iso(now_utc())}
            await db.tiers.insert_one(doc)
    default_tier = await db.tiers.find_one({"name": "Regular Member"})
    default_id = default_tier["id"] if default_tier else None
    # Now remove legacy tiers — migrate any members first
    legacy = await db.tiers.find({"name": {"$nin": AOP_TIER_NAMES}}, {"_id": 0}).to_list(200)
    for t in legacy:
        if default_id:
            await db.users.update_many({"tier_id": t["id"]}, {"$set": {"tier_id": default_id}})
        await db.tiers.delete_one({"id": t["id"]})
        logger.info(f"Removed legacy tier and migrated members: {t['name']}")
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
    """Reconcile AOP-specific Ribbons/Awards: insert missing, refresh on existing.
    Legacy awards (and their grants) are deleted — these were demo seed data."""
    legacy = await db.awards.find({"name": {"$nin": AOP_AWARD_NAMES}}, {"_id": 0}).to_list(200)
    for a in legacy:
        await db.award_grants.delete_many({"award_id": a["id"]})
        await db.awards.delete_one({"id": a["id"]})
        logger.info(f"Removed legacy award and grants: {a['name']}")
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

    # Remove any other anniversary-tagged events that aren't in our canonical list
    stale = db.events.find(
        {
            "$and": [
                {"$or": [
                    {"parent_event_id": parent["id"]},
                    {"category": "anniversary"},
                    {"title": {"$in": list(ANNIVERSARY_LEGACY_TITLES)}},
                ]},
                {"title": {"$nin": list(ANNIVERSARY_ALLOWED_TITLES)}},
            ]
        },
        {"_id": 0, "id": 1, "title": 1},
    )
    async for e in stale:
        await db.events.delete_one({"id": e["id"]})
        await db.rsvps.delete_many({"event_id": e["id"]})
        await db.checkins.delete_many({"event_id": e["id"]})
        logger.info(f"Removed stale anniversary event: {e.get('title')}")

    # Wipe ALL non-anniversary events on startup so the events page is clean.
    # The Anniversary tree (parent + its 5 sub-events) is the only canonical set
    # right now per the chapter. Admins re-seed via the UI when they add real events.
    allowed_ids = {parent["id"]}
    async for sub in db.events.find({"parent_event_id": parent["id"]}, {"_id": 0, "id": 1}):
        allowed_ids.add(sub["id"])
    other = db.events.find({"id": {"$nin": list(allowed_ids)}}, {"_id": 0, "id": 1, "title": 1})
    async for e in other:
        await db.events.delete_one({"id": e["id"]})
        await db.rsvps.delete_many({"event_id": e["id"]})
        await db.checkins.delete_many({"event_id": e["id"]})
        logger.info(f"Removed legacy event: {e.get('title')}")


# ---------- Email Signatures (personal + org-wide) ----------
class SignatureIn(BaseModel):
    name: str
    body_html: str
    kind: Literal["personal", "org"] = "personal"

class SignatureUpdateIn(BaseModel):
    name: Optional[str] = None
    body_html: Optional[str] = None

def signature_out(s: dict) -> dict:
    return {
        "id": s["id"],
        "name": s["name"],
        "body_html": s.get("body_html", ""),
        "kind": s.get("kind", "personal"),
        "owner_id": s.get("owner_id"),
        "created_at": s.get("created_at"),
    }

@api.get("/email/signatures")
async def list_signatures(user: dict = Depends(admin_tab_dep("email"))):
    """Return signatures visible to the current admin: their personal sigs + all org sigs."""
    cursor = db.email_signatures.find(
        {"$or": [{"kind": "org"}, {"kind": "personal", "owner_id": user["id"]}]},
        {"_id": 0},
    ).sort([("kind", 1), ("created_at", -1)])
    items = await cursor.to_list(200)
    return [signature_out(s) for s in items]

@api.post("/email/signatures")
async def create_signature(body: SignatureIn, user: dict = Depends(admin_tab_dep("email"))):
    doc = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "body_html": body.body_html,
        "kind": body.kind,
        "owner_id": user["id"],
        "created_at": iso(now_utc()),
    }
    await db.email_signatures.insert_one(doc)
    return signature_out(doc)

@api.put("/email/signatures/{sid}")
async def update_signature(sid: str, body: SignatureUpdateIn, user: dict = Depends(admin_tab_dep("email"))):
    s = await db.email_signatures.find_one({"id": sid})
    if not s:
        raise HTTPException(status_code=404, detail="Signature not found")
    if s.get("kind") == "personal" and s.get("owner_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.email_signatures.update_one({"id": sid}, {"$set": updates})
    s2 = await db.email_signatures.find_one({"id": sid}, {"_id": 0})
    return signature_out(s2)

@api.delete("/email/signatures/{sid}")
async def delete_signature(sid: str, user: dict = Depends(admin_tab_dep("email"))):
    s = await db.email_signatures.find_one({"id": sid})
    if not s:
        raise HTTPException(status_code=404, detail="Signature not found")
    if s.get("kind") == "personal" and s.get("owner_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.email_signatures.delete_one({"id": sid})
    return {"ok": True}


# ---------- Rich email image upload (reuses chat_files resolver) ----------
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
    if ext not in IMAGE_EXT:
        raise HTTPException(status_code=400, detail="Only images allowed (jpg, png, gif, webp)")
    content_type = file.content_type or MIME_BY_EXT.get(ext, "image/jpeg")
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
        "url": f"/api/files/{storage_path}",
        "size": total,
        "content_type": content_type,
    }


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


# ---------- Chat email digest service (5-min debounce) ----------
CHAT_DIGEST_DELAY_SECONDS = 15 * 60  # 15 minutes per user request (10-20 range)

async def queue_chat_notifications(conv: dict, message: dict, sender: dict):
    """Insert one pending notification per recipient (excluding sender).
    A background task wakes every 60s, sends consolidated emails (+SMS if phone on file)
    for any recipient whose oldest pending notification has aged past CHAT_DIGEST_DELAY_SECONDS,
    and marks them sent. Read-receipts cancel pending notifications. Recipients who have
    opted out of BOTH email and SMS are skipped at queue time."""
    due_at = iso(now_utc() + timedelta(seconds=CHAT_DIGEST_DELAY_SECONDS))
    member_ids = [rid for rid in conv.get("member_ids", []) if rid != sender["id"]]
    if not member_ids:
        return
    # Bulk-fetch recipient prefs to skip fully-opted-out users
    recipients = await db.users.find(
        {"id": {"$in": member_ids}},
        {"_id": 0, "id": 1, "chat_email_notifications": 1, "chat_sms_notifications": 1},
    ).to_list(len(member_ids))
    prefs = {r["id"]: r for r in recipients}
    docs = []
    for rid in member_ids:
        p = prefs.get(rid, {})
        email_on = p.get("chat_email_notifications", True)
        sms_on = p.get("chat_sms_notifications", True)
        if not email_on and not sms_on:
            continue  # fully opted out
        docs.append({
            "id": str(uuid.uuid4()),
            "recipient_id": rid,
            "conversation_id": conv["id"],
            "message_id": message["id"],
            "sender_id": sender["id"],
            "sender_name": sender.get("name", ""),
            "preview": (message.get("body") or "")[:200],
            "status": "pending",
            "due_at": due_at,
            "created_at": _now_iso(),
        })
    if docs:
        await db.chat_notifications.insert_many(docs)


async def _send_chat_digest_email(recipient: dict, conv: dict, notifs: list) -> bool:
    """Send one consolidated email for a recipient + conversation. Returns True on success."""
    if not RESEND_API_KEY:
        return False
    to_email = (recipient.get("email") or "").strip()
    if not to_email:
        return False
    name = recipient.get("name") or recipient.get("first_name") or "there"
    conv_name = conv.get("name") or "your chat"
    count = len(notifs)
    senders = list({n.get("sender_name", "") for n in notifs if n.get("sender_name")})
    senders_label = ", ".join(senders[:3]) + (f" +{len(senders) - 3} others" if len(senders) > 3 else "")
    items_html = "".join(
        f"<li><strong>{(_html_escape(n.get('sender_name', '')))}</strong>: {_html_escape(n.get('preview', ''))}</li>"
        for n in notifs[:10]
    )
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    body_html = f"""
    <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#222">
      <h2 style="color:#C8102E;margin:0 0 12px">You have {count} unread message{'s' if count != 1 else ''}</h2>
      <p>Hi {_html_escape(name)}, you received new messages in <strong>{_html_escape(conv_name)}</strong> from {_html_escape(senders_label) or 'Alpha Omega Phi'}.</p>
      <ul style="background:#f7f5f0;border-radius:12px;padding:16px 16px 16px 32px">{items_html}</ul>
      <p style="margin-top:24px"><a href="{frontend}/chat" style="background:#C8102E;color:#fff;padding:10px 20px;border-radius:999px;text-decoration:none;font-weight:600">Open chat</a></p>
      <p style="font-size:11px;color:#888;margin-top:24px">You receive this email because you didn't open your chat within 5 minutes of receiving a message.</p>
    </div>
    """
    try:
        params = {
            "from": RESEND_FROM,
            "to": [to_email],
            "subject": f"{count} new message{'s' if count != 1 else ''} from Alpha Omega Phi chat",
            "html": body_html,
            "tags": [{"name": "type", "value": "chat_digest"}],
        }
        await asyncio.to_thread(resend_sdk.Emails.send, params)
        return True
    except Exception as e:
        logger.warning(f"Chat digest email failed for {to_email}: {e}")
        return False


def _html_escape(s: str) -> str:
    import html as _h
    return _h.escape(s or "")


async def _chat_digest_loop():
    """Background loop: every 60s, batch pending notifications older than due_at
    by (recipient, conversation), send one consolidated email + SMS (if opted-in)
    per bundle, mark sent."""
    while True:
        try:
            now_iso_s = iso(now_utc())
            # Find candidate notifications
            cursor = db.chat_notifications.find(
                {"status": "pending", "due_at": {"$lte": now_iso_s}}, {"_id": 0}
            ).limit(500)
            items = await cursor.to_list(500)
            # Group by recipient + conversation
            groups: dict = {}
            for n in items:
                key = (n["recipient_id"], n["conversation_id"])
                groups.setdefault(key, []).append(n)
            for (rid, cid), notifs in groups.items():
                recipient = await db.users.find_one({"id": rid}, {"_id": 0, "password_hash": 0})
                conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
                if not recipient or not conv:
                    await db.chat_notifications.update_many(
                        {"id": {"$in": [n["id"] for n in notifs]}},
                        {"$set": {"status": "skipped", "sent_at": _now_iso()}},
                    )
                    continue
                email_on = recipient.get("chat_email_notifications", True)
                sms_on = recipient.get("chat_sms_notifications", True)
                email_sent = False
                sms_sent = False
                if email_on:
                    email_sent = await _send_chat_digest_email(recipient, conv, notifs)
                if sms_on and recipient.get("phone"):
                    sms_sent = await _send_chat_digest_sms(recipient, conv, notifs)
                # Mark sent if EITHER channel made it through; failed only if both failed AND both were attempted
                attempted_any = email_on or (sms_on and recipient.get("phone"))
                if not attempted_any:
                    final = "skipped"  # fully opted-out (shouldn't happen due to queue filter)
                elif email_sent or sms_sent:
                    final = "sent"
                else:
                    final = "failed"
                await db.chat_notifications.update_many(
                    {"id": {"$in": [n["id"] for n in notifs]}},
                    {"$set": {"status": final, "sent_at": _now_iso(), "email_sent": email_sent, "sms_sent": sms_sent}},
                )
        except Exception as e:
            logger.error(f"chat digest loop iteration error: {e}")
        await asyncio.sleep(60)


async def _send_chat_digest_sms(recipient: dict, conv: dict, notifs: list) -> bool:
    """Per user request: short, clear copy. Recipient has phone + sms_on already checked."""
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    body = f"You have a new message in Alpha Omega Phi chat. Open the portal to read it: {frontend.rstrip('/')}/chat"
    return await send_sms(recipient["phone"], body)


# ============================================================
# Automated Emails — admin-defined campaigns with cron schedule
# ============================================================
from croniter import croniter as _croniter

AUTOMATED_SECTIONS = ["events", "photos", "documents", "new_members", "my_rsvps", "pending_hours", "birthday_greeting"]

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


class AutomatedEmailAudienceIn(BaseModel):
    type: Literal["all", "chapter", "tier", "status"] = "all"
    ids: List[str] = Field(default_factory=list, max_length=500)  # chapter ids, tier ids, or status strings depending on `type`


AutomatedSection = Literal["events", "photos", "documents", "new_members", "my_rsvps", "pending_hours", "birthday_greeting"]


class AutomatedEmailIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=200)
    body_html: str = Field("", max_length=200_000)
    cron_expression: str = "0 9 * * 1"  # default: Mondays 9am UTC
    is_active: bool = True
    audience: AutomatedEmailAudienceIn = Field(default_factory=AutomatedEmailAudienceIn)
    sections: Dict[AutomatedSection, bool] = Field(default_factory=dict)


def _next_cron_run(cron_expr: str, base: Optional[datetime] = None) -> Optional[datetime]:
    try:
        c = _croniter(cron_expr, base or now_utc())
        return c.get_next(datetime)
    except Exception as e:
        logger.warning(f"Bad cron expression '{cron_expr}': {e}")
        return None


def _automated_email_out(d: dict) -> dict:
    return {
        "id": d["id"],
        "name": d.get("name", ""),
        "subject": d.get("subject", ""),
        "body_html": d.get("body_html", ""),
        "cron_expression": d.get("cron_expression", "0 9 * * 1"),
        "is_active": bool(d.get("is_active", True)),
        "is_builtin": bool(d.get("is_builtin", False)),
        "audience": d.get("audience", {"type": "all", "ids": []}),
        "sections": d.get("sections", {}),
        "last_run_at": d.get("last_run_at"),
        "next_run_at": d.get("next_run_at"),
        "last_sent_count": d.get("last_sent_count", 0),
        "created_by_name": d.get("created_by_name", ""),
        "created_at": d.get("created_at"),
    }


@api.get("/automated-emails")
async def list_automated_emails(_: dict = Depends(admin_tab_dep("email"))):
    docs = await db.automated_emails.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [_automated_email_out(d) for d in docs]


@api.get("/automated-emails/merge-tags")
async def list_merge_tags(_: dict = Depends(admin_tab_dep("email"))):
    return {"tags": MERGE_TAGS, "sections": AUTOMATED_SECTIONS}


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
async def delete_automated_email(eid: str, _: dict = Depends(admin_tab_dep("email"))):
    e = await db.automated_emails.find_one({"id": eid})
    if not e:
        raise HTTPException(status_code=404, detail="Automated email not found")
    if e.get("is_builtin"):
        raise HTTPException(status_code=400, detail="Built-in automated emails can be disabled but not deleted.")
    await db.automated_emails.delete_one({"id": eid})
    return {"ok": True}


@api.post("/automated-emails/{eid}/run-now")
async def run_automated_email_now(eid: str, admin: dict = Depends(admin_tab_dep("email"))):
    """Manually trigger the campaign (sends to the full audience right now). Useful for testing."""
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
    """Render the email body for the calling admin (uses their merge data)."""
    e = await db.automated_emails.find_one({"id": eid})
    if not e:
        raise HTTPException(status_code=404, detail="Automated email not found")
    rendered = await _render_automated_body(e, admin)
    subject = _render_subject(e["subject"], admin)
    return {"subject": subject, "body_html": rendered}


async def _audience_recipients(audience: dict) -> List[dict]:
    """Resolve audience filter to a list of user dicts with valid emails."""
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
    return await db.users.find(q, {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1, "birthday": 1}).to_list(2000)


def _render_subject(subj: str, user: dict) -> str:
    """Apply merge tags to the email subject line. Mirrors body rendering but
    cheap — subjects only need the recipient's first name."""
    first_name = (user.get("name") or "Member").split(" ")[0]
    import html as _h
    return (subj or "").replace("{{member_name}}", _h.escape(first_name))


async def _render_automated_body(campaign: dict, user: dict) -> str:
    """Replace merge tags in body_html with personalized HTML for `user`."""
    import html as _h
    body = campaign.get("body_html") or ""
    sections = campaign.get("sections") or {}
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")

    def section_card(title: str, inner: str) -> str:
        return f'<div style="background:#fff;border-radius:14px;padding:16px;margin:12px 0;border:1px solid #eee"><div style="font-size:11px;text-transform:uppercase;letter-spacing:.16em;color:#C8102E;font-weight:700;margin-bottom:8px">{_h.escape(title)}</div>{inner}</div>'

    # member_name
    first_name = (user.get("name") or "Member").split(" ")[0]
    body = body.replace("{{member_name}}", _h.escape(first_name))

    # upcoming_events
    if "{{upcoming_events}}" in body:
        if sections.get("events", True):
            soon = now_utc() + timedelta(days=7)
            evs = await db.events.find({"start_at": {"$gte": iso(now_utc()), "$lte": iso(soon)}, "parent_event_id": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "title": 1, "start_at": 1, "location": 1}).sort("start_at", 1).to_list(20)
            inner = "".join(f'<div style="margin:6px 0"><a href="{frontend}/events/{e["id"]}" style="color:#0A2463;font-weight:600;text-decoration:none">{_h.escape(e.get("title",""))}</a><div style="font-size:12px;color:#666">{e.get("start_at","")[:10]}{" · " + _h.escape(e["location"]) if e.get("location") else ""}</div></div>' for e in evs) or '<div style="color:#888;font-size:13px">Nothing on the calendar in the next 7 days.</div>'
            body = body.replace("{{upcoming_events}}", section_card("Upcoming events", inner))
        else:
            body = body.replace("{{upcoming_events}}", "")

    # new_photos / new_documents / new_members — last 7 days
    week_ago = iso(now_utc() - timedelta(days=7))
    for tag, enabled, fn in [
        ("{{new_photos}}", "photos", lambda: db.photo_albums.find({"created_at": {"$gte": week_ago}, "is_default": {"$ne": True}}, {"_id": 0, "name": 1}).to_list(20)),
        ("{{new_documents}}", "documents", lambda: db.documents.find({"created_at": {"$gte": week_ago}, "is_deleted": {"$ne": True}}, {"_id": 0, "title": 1}).to_list(20)),
        ("{{new_members}}", "new_members", lambda: db.users.find({"created_at": {"$gte": week_ago}}, {"_id": 0, "name": 1}).to_list(50)),
    ]:
        if tag in body:
            if sections.get(enabled, True):
                items = await fn()
                inner = "".join(f'<div style="margin:4px 0;font-size:13px;color:#333">• {_h.escape(it.get("name") or it.get("title") or "")}</div>' for it in items) or '<div style="color:#888;font-size:13px">Nothing new this week.</div>'
                title = {"photos": "New photo albums", "documents": "New AOP forms", "new_members": "New members this week"}[enabled]
                body = body.replace(tag, section_card(title, inner))
            else:
                body = body.replace(tag, "")

    # my_rsvps (personal)
    if "{{my_rsvps}}" in body:
        if sections.get("my_rsvps", True):
            rsvps = await db.rsvps.find({"user_id": user["id"]}, {"_id": 0, "event_id": 1, "ticket_id": 1, "ticket_type": 1}).to_list(20)
            event_ids = [r["event_id"] for r in rsvps]
            evs = await db.events.find({"id": {"$in": event_ids}, "start_at": {"$gte": iso(now_utc())}}, {"_id": 0, "id": 1, "title": 1, "start_at": 1}).to_list(20)
            ev_by_id = {e["id"]: e for e in evs}
            rows = []
            for r in rsvps:
                e = ev_by_id.get(r["event_id"])
                if not e: continue
                rows.append(f'<div style="margin:6px 0;font-size:13px"><a href="{frontend}/events/{e["id"]}" style="color:#0A2463;font-weight:600">{_h.escape(e["title"])}</a><div style="color:#666;font-size:12px">{e["start_at"][:10]} · {_h.escape((r.get("ticket_type") or "general").replace("_"," ").title())}</div></div>')
            inner = "".join(rows) or '<div style="color:#888;font-size:13px">You have no upcoming RSVPs.</div>'
            body = body.replace("{{my_rsvps}}", section_card("Your upcoming RSVPs", inner))
        else:
            body = body.replace("{{my_rsvps}}", "")

    # pending_hours (admins only)
    if "{{pending_hours}}" in body:
        if sections.get("pending_hours", True) and user.get("role") == "admin":
            n = await db.volunteer_hours.count_documents({"status": "pending"})
            inner = f'<div style="font-size:13px"><strong>{n}</strong> hour log{"s" if n != 1 else ""} waiting on approval. <a href="{frontend}/admin" style="color:#C8102E">Open the admin queue →</a></div>'
            body = body.replace("{{pending_hours}}", section_card("Hours waiting approval", inner))
        else:
            body = body.replace("{{pending_hours}}", "")

    # birthday
    if "{{birthday_greeting}}" in body:
        if sections.get("birthday_greeting", True):
            bd = user.get("birthday")  # expected MM-DD or YYYY-MM-DD
            this_week_md = {(now_utc() + timedelta(days=i)).strftime("%m-%d") for i in range(7)}
            if bd and bd[-5:] in this_week_md:
                inner = f'<div style="font-size:14px">🎂 Happy birthday week, {_h.escape(first_name)}! The whole chapter is celebrating with you. Stop by the chat and share a memory.</div>'
                body = body.replace("{{birthday_greeting}}", section_card("It's your birthday week!", inner))
            else:
                body = body.replace("{{birthday_greeting}}", "")
        else:
            body = body.replace("{{birthday_greeting}}", "")

    return body


async def _send_automated_email(campaign: dict) -> int:
    """Resolve audience, render per-recipient HTML, send via Resend. Returns count sent."""
    if not RESEND_API_KEY:
        logger.info(f"Automated email '{campaign.get('name')}' skipped — no RESEND_API_KEY")
        return 0
    recipients = await _audience_recipients(campaign.get("audience") or {})
    sent = 0
    for u in recipients:
        email = (u.get("email") or "").strip()
        if not email: continue
        try:
            html = await _render_automated_body(campaign, u)
            subject = _render_subject(campaign["subject"], u)
            await asyncio.to_thread(resend_sdk.Emails.send, {
                "from": RESEND_FROM,
                "to": [email],
                "subject": subject,
                "html": html,
                "tags": [{"name": "type", "value": "automated"}, {"name": "campaign_id", "value": campaign["id"]}],
            })
            sent += 1
        except Exception as e:
            logger.warning(f"Automated email send failed to {email}: {e}")
    return sent


async def _automated_email_loop():
    """Once a minute, send any campaigns whose `next_run_at` has elapsed."""
    while True:
        try:
            cursor = db.automated_emails.find({"is_active": True, "next_run_at": {"$lte": iso(now_utc())}}, {"_id": 0})
            async for campaign in cursor:
                logger.info(f"Running automated email campaign '{campaign.get('name')}' (id={campaign['id']})")
                sent = await _send_automated_email(campaign)
                next_run = _next_cron_run(campaign.get("cron_expression", "0 9 * * 1"))
                await db.automated_emails.update_one(
                    {"id": campaign["id"]},
                    {"$set": {"last_run_at": iso(now_utc()), "last_sent_count": sent, "next_run_at": iso(next_run) if next_run else None}},
                )
        except Exception as e:
            logger.warning(f"Automated email loop error: {e}")
        await asyncio.sleep(60)


async def seed_builtin_automated_emails():
    """Insert the default Weekly Digest campaign if it doesn't exist yet."""
    existing = await db.automated_emails.find_one({"id": "builtin_weekly_digest"})
    if existing:
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


# ---------- Mount ----------
app.include_router(api)

_cors_origins_raw = os.environ.get("CORS_ORIGINS", "*").strip()
_cors_kwargs = {"allow_credentials": True, "allow_methods": ["*"], "allow_headers": ["*"]}
if _cors_origins_raw == "*":
    _cors_kwargs["allow_origin_regex"] = ".*"
else:
    _cors_kwargs["allow_origins"] = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(CORSMiddleware, **_cors_kwargs)

@app.on_event("shutdown")
async def shutdown():
    client.close()
