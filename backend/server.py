from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
import secrets
import requests
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response, status, UploadFile, File, Form, Header, Query
from fastapi.responses import Response as FastResponse
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

def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": now_utc() + timedelta(minutes=ACCESS_TOKEN_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": now_utc() + timedelta(days=REFRESH_TOKEN_DAYS), "type": "refresh"}
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
    exp = u.get("membership_expires_at")
    try:
        exp_dt = datetime.fromisoformat(exp) if exp else None
    except Exception:
        exp_dt = None
    now = now_utc()
    is_expired = bool(exp_dt and exp_dt < now)
    within_grace = bool(is_expired and exp_dt and (now - exp_dt).days <= GRACE_PERIOD_DAYS)
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u.get("name", ""),
        "role": u.get("role", "member"),
        "bio": u.get("bio", ""),
        "city": u.get("city", ""),
        "interests": u.get("interests", []),
        "avatar_url": u.get("avatar_url", ""),
        "membership_tier": u.get("membership_tier", "standard"),
        "tier_id": u.get("tier_id"),
        "chapter_id": u.get("chapter_id"),
        "membership_expires_at": u.get("membership_expires_at"),
        "is_expired": is_expired,
        "within_grace": within_grace,
        "email_verified": u.get("email_verified", False),
        "created_at": u.get("created_at"),
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
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user

# ---------- Models ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1)
    city: Optional[str] = ""
    interests: Optional[List[str]] = []

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ProfileUpdateIn(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    city: Optional[str] = None
    interests: Optional[List[str]] = None
    avatar_url: Optional[str] = None

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

class ChapterIn(BaseModel):
    name: str
    school: str = ""
    city: str = ""
    founded_year: Optional[int] = None
    description: str = ""

class ChapterUpdateIn(BaseModel):
    name: Optional[str] = None
    school: Optional[str] = None
    city: Optional[str] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None

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

class AwardGrantIn(BaseModel):
    user_id: str
    reason: str = ""

class HoursLogIn(BaseModel):
    hours: float = Field(gt=0, le=1000)
    description: str = Field(min_length=2)
    date: datetime
    event_id: Optional[str] = None

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
    at = create_access_token(uid, email, "member")
    rt = create_refresh_token(uid)
    set_auth_cookies(response, at, rt)
    out = public_user(doc)
    out["verify_link"] = verify_link  # dev: returned so UI can surface; replace with email provider later
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
    at = create_access_token(user["id"], user["email"], user.get("role", "member"))
    rt = create_refresh_token(user["id"])
    set_auth_cookies(response, at, rt)
    return public_user(user)

@api.post("/auth/logout")
async def logout(response: Response, _: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    return {"ok": True}

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)

@api.post("/auth/refresh")
async def refresh(request: Request, response: Response):
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
        at = create_access_token(user["id"], user["email"], user.get("role", "member"))
        rt = create_refresh_token(user["id"])
        set_auth_cookies(response, at, rt)
        return {"ok": True}
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

@api.put("/members/me")
async def update_me(body: ProfileUpdateIn, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.users.update_one({"id": user["id"]}, {"$set": updates})
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return public_user(u)

@api.post("/members/me/renew")
async def renew_membership(user: dict = Depends(get_current_user)):
    current = user.get("membership_expires_at")
    try:
        base = datetime.fromisoformat(current) if current else now_utc()
    except Exception:
        base = now_utc()
    # Grace period: if expired within grace window, renew from now (don't stack past grace)
    if base < now_utc():
        base = now_utc()
    new_exp = base + timedelta(days=365)
    await db.users.update_one({"id": user["id"]}, {"$set": {"membership_expires_at": iso(new_exp)}})
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return public_user(u)

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
        "created_at": e.get("created_at"),
    }

@api.get("/events")
async def list_events(upcoming: bool = False):
    query = {}
    if upcoming:
        query["start_at"] = {"$gte": iso(now_utc())}
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
async def create_event(body: EventIn, _: dict = Depends(require_admin)):
    eid = str(uuid.uuid4())
    doc = body.model_dump()
    doc["start_at"] = iso(doc["start_at"]) if doc.get("start_at") else None
    doc["end_at"] = iso(doc["end_at"]) if doc.get("end_at") else None
    doc.update({"id": eid, "rsvp_count": 0, "created_at": iso(now_utc())})
    await db.events.insert_one(doc)
    return event_out(doc)

@api.put("/events/{event_id}")
async def update_event(event_id: str, body: EventUpdateIn, _: dict = Depends(require_admin)):
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
async def delete_event(event_id: str, _: dict = Depends(require_admin)):
    await db.events.delete_one({"id": event_id})
    await db.rsvps.delete_many({"event_id": event_id})
    return {"ok": True}

@api.post("/events/{event_id}/rsvp")
async def rsvp_event(event_id: str, user: dict = Depends(get_current_user)):
    e = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    existing = await db.rsvps.find_one({"event_id": event_id, "user_id": user["id"]})
    if existing:
        await db.rsvps.delete_one({"_id": existing["_id"]})
        await db.events.update_one({"id": event_id}, {"$inc": {"rsvp_count": -1}})
        return {"rsvped": False}
    if e.get("capacity", 0) > 0 and e.get("rsvp_count", 0) >= e["capacity"]:
        raise HTTPException(status_code=400, detail="Event is full")
    await db.rsvps.insert_one({
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "user_id": user["id"],
        "user_name": user.get("name", ""),
        "created_at": iso(now_utc()),
    })
    await db.events.update_one({"id": event_id}, {"$inc": {"rsvp_count": 1}})
    return {"rsvped": True}

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
async def create_news(body: NewsIn, admin: dict = Depends(require_admin)):
    nid = str(uuid.uuid4())
    doc = body.model_dump()
    doc.update({"id": nid, "author_name": admin.get("name", "Admin"), "created_at": iso(now_utc())})
    await db.news.insert_one(doc)
    return news_out(doc)

@api.put("/news/{news_id}")
async def update_news(news_id: str, body: NewsUpdateIn, _: dict = Depends(require_admin)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.news.update_one({"id": news_id}, {"$set": updates})
    n = await db.news.find_one({"id": news_id}, {"_id": 0})
    if not n:
        raise HTTPException(status_code=404, detail="News not found")
    return news_out(n)

@api.delete("/news/{news_id}")
async def delete_news(news_id: str, _: dict = Depends(require_admin)):
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
async def create_page(body: PageIn, _: dict = Depends(require_admin)):
    existing = await db.pages.find_one({"slug": body.slug})
    if existing:
        raise HTTPException(status_code=400, detail="Slug already exists")
    doc = body.model_dump()
    doc.update({"id": str(uuid.uuid4()), "updated_at": iso(now_utc())})
    await db.pages.insert_one(doc)
    return page_out(doc)

@api.put("/pages/{slug}")
async def update_page(slug: str, body: PageUpdateIn, _: dict = Depends(require_admin)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates["updated_at"] = iso(now_utc())
    await db.pages.update_one({"slug": slug}, {"$set": updates})
    p = await db.pages.find_one({"slug": slug}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Page not found")
    return page_out(p)

@api.delete("/pages/{slug}")
async def delete_page(slug: str, _: dict = Depends(require_admin)):
    await db.pages.delete_one({"slug": slug})
    return {"ok": True}

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
        "founded_year": c.get("founded_year"),
        "description": c.get("description", ""),
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
async def create_chapter(body: ChapterIn, _: dict = Depends(require_admin)):
    doc = body.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = iso(now_utc())
    await db.chapters.insert_one(doc)
    doc["member_count"] = 0
    return chapter_out(doc)

@api.put("/chapters/{chapter_id}")
async def update_chapter(chapter_id: str, body: ChapterUpdateIn, _: dict = Depends(require_admin)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.chapters.update_one({"id": chapter_id}, {"$set": updates})
    c = await db.chapters.find_one({"id": chapter_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Chapter not found")
    c["member_count"] = await db.users.count_documents({"chapter_id": chapter_id})
    return chapter_out(c)

@api.delete("/chapters/{chapter_id}")
async def delete_chapter(chapter_id: str, _: dict = Depends(require_admin)):
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
async def create_tier(body: TierIn, _: dict = Depends(require_admin)):
    doc = body.model_dump()
    doc["id"] = str(uuid.uuid4())
    await db.tiers.insert_one(doc)
    doc["member_count"] = 0
    return tier_out(doc)

@api.put("/tiers/{tier_id}")
async def update_tier(tier_id: str, body: TierUpdateIn, _: dict = Depends(require_admin)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.tiers.update_one({"id": tier_id}, {"$set": updates})
    t = await db.tiers.find_one({"id": tier_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tier not found")
    t["member_count"] = await db.users.count_documents({"tier_id": tier_id})
    return tier_out(t)

@api.delete("/tiers/{tier_id}")
async def delete_tier(tier_id: str, _: dict = Depends(require_admin)):
    await db.tiers.delete_one({"id": tier_id})
    await db.users.update_many({"tier_id": tier_id}, {"$unset": {"tier_id": ""}})
    return {"ok": True}

# ---------- Member admin operations ----------
@api.put("/members/{user_id}/role")
async def update_member_role(user_id: str, body: RoleUpdateIn, _: dict = Depends(require_admin)):
    await db.users.update_one({"id": user_id}, {"$set": {"role": body.role}})
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    return public_user(u)

@api.put("/members/{user_id}/chapter")
async def assign_chapter(user_id: str, body: AssignChapterIn, _: dict = Depends(require_admin)):
    update = {"chapter_id": body.chapter_id} if body.chapter_id else {"chapter_id": None}
    await db.users.update_one({"id": user_id}, {"$set": update})
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    return public_user(u)

@api.put("/members/{user_id}/tier")
async def assign_tier(user_id: str, body: AssignTierIn, _: dict = Depends(require_admin)):
    updates = {"tier_id": body.tier_id}
    if body.tier_id:
        tier = await db.tiers.find_one({"id": body.tier_id}, {"_id": 0})
        if tier:
            updates["membership_tier"] = tier.get("name", "standard")
    if body.extend_days:
        u = await db.users.find_one({"id": user_id})
        if u:
            cur = u.get("membership_expires_at")
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
async def create_award(body: AwardIn, _: dict = Depends(require_admin)):
    doc = body.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = iso(now_utc())
    await db.awards.insert_one(doc)
    return award_out(doc)

@api.put("/awards/{award_id}")
async def update_award(award_id: str, body: AwardUpdateIn, _: dict = Depends(require_admin)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.awards.update_one({"id": award_id}, {"$set": updates})
    a = await db.awards.find_one({"id": award_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Award not found")
    return award_out(a)

@api.delete("/awards/{award_id}")
async def delete_award(award_id: str, _: dict = Depends(require_admin)):
    await db.awards.delete_one({"id": award_id})
    await db.award_grants.delete_many({"award_id": award_id})
    return {"ok": True}

@api.post("/awards/{award_id}/grant")
async def grant_award(award_id: str, body: AwardGrantIn, admin: dict = Depends(require_admin)):
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
        "granted_at": iso(now_utc()),
    }
    await db.award_grants.insert_one(doc)
    out = dict(doc)
    out.pop("_id", None)
    return out

@api.delete("/awards/grants/{grant_id}")
async def revoke_award(grant_id: str, _: dict = Depends(require_admin)):
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
        "description": h.get("description", ""),
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
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_name": user.get("name", ""),
        "hours": body.hours,
        "description": body.description,
        "date": iso(body.date),
        "event_id": body.event_id,
        "status": "pending",
        "created_at": iso(now_utc()),
    }
    await db.volunteer_hours.insert_one(doc)
    return hours_out(doc)

@api.get("/hours")
async def list_hours(status_filter: Optional[str] = None, _: dict = Depends(require_admin)):
    query = {}
    if status_filter:
        query["status"] = status_filter
    cursor = db.volunteer_hours.find(query, {"_id": 0}).sort("created_at", -1).limit(500)
    items = await cursor.to_list(500)
    return [hours_out(h) for h in items]

@api.get("/me/hours")
async def my_hours(user: dict = Depends(get_current_user)):
    cursor = db.volunteer_hours.find({"user_id": user["id"]}, {"_id": 0}).sort("date", -1)
    items = await cursor.to_list(500)
    return [hours_out(h) for h in items]

@api.put("/hours/{hours_id}/review")
async def review_hours(hours_id: str, body: HoursReviewIn, admin: dict = Depends(require_admin)):
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

@api.get("/photos/albums")
async def list_photo_albums():
    pipeline = [
        {"$match": {"is_deleted": {"$ne": True}}},
        {"$group": {"_id": "$album", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    out = []
    async for d in db.photos.aggregate(pipeline):
        out.append({"album": d["_id"] or "general", "count": d["count"]})
    return out

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
    doc = {
        "id": str(uuid.uuid4()),
        "title": title,
        "album": album or "general",
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

@api.delete("/photos/{photo_id}")
async def delete_photo(photo_id: str, user: dict = Depends(get_current_user)):
    p = await db.photos.find_one({"id": photo_id})
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    if p.get("uploaded_by") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.photos.update_one({"id": photo_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}

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
        "created_at": d.get("created_at"),
    }

@api.get("/documents")
async def list_documents(category: Optional[str] = None):
    query = {"is_deleted": {"$ne": True}}
    if category:
        query["category"] = category
    cursor = db.documents.find(query, {"_id": 0}).sort("created_at", -1).limit(500)
    items = await cursor.to_list(500)
    return [document_out(d) for d in items]

@api.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    category: str = Form("general"),
    description: str = Form(""),
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
async def download_file(storage_path: str, _: dict = Depends(get_current_user)):
    # Check DB for existence + soft-delete flag
    rec = await db.photos.find_one({"storage_path": storage_path, "is_deleted": {"$ne": True}})
    if not rec:
        rec = await db.documents.find_one({"storage_path": storage_path, "is_deleted": {"$ne": True}})
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data, content_type = get_object(storage_path)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found in storage")
    return FastResponse(content=data, media_type=rec.get("content_type", content_type))

# ---------- Admin Dashboard Stats ----------
ANNUAL_DUES_USD = 60.0

@api.get("/admin/stats")
async def admin_stats(_: dict = Depends(require_admin)):
    now = now_utc()
    now_iso = iso(now)
    thirty_days_iso = iso(now + timedelta(days=30))
    month_start_iso = iso(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))

    # Members
    total_members = await db.users.count_documents({})
    new_this_month = await db.users.count_documents({"created_at": {"$gte": month_start_iso}})
    expiring_soon = await db.users.count_documents({
        "membership_expires_at": {"$gte": now_iso, "$lte": thirty_days_iso}
    })
    expired = await db.users.count_documents({"membership_expires_at": {"$lt": now_iso}})
    active_members = total_members - expired

    tier_cursor = db.users.aggregate([{"$group": {"_id": "$membership_tier", "count": {"$sum": 1}}}])
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
        c = await db.users.count_documents({
            "created_at": {"$gte": iso(m_start), "$lt": iso(next_m)}
        })
        growth.append({"month": m_start.strftime("%b"), "members": c})

    # Events
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
    renewals_this_month = await db.users.count_documents({
        "membership_expires_at": {"$gte": iso(now + timedelta(days=360)), "$lte": iso(now + timedelta(days=370))}
    })

    # Expiring memberships list
    exp_cursor = db.users.find(
        {"membership_expires_at": {"$gte": now_iso, "$lte": thirty_days_iso}},
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
    total_grants = await db.award_grants.count_documents({})
    pending_hours = await db.volunteer_hours.count_documents({"status": "pending"})
    approved_hours_agg = db.volunteer_hours.aggregate([
        {"$match": {"status": "approved"}},
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
        {"status": "pending"}, {"_id": 0}
    ).sort("created_at", 1).limit(10)
    hours_to_review = [hours_out(h) async for h in hours_queue_cursor]
    grace_cursor = db.users.find(
        {"membership_expires_at": {"$gte": grace_cutoff_iso, "$lt": now_iso}},
        {"_id": 0, "password_hash": 0},
    ).sort("membership_expires_at", 1).limit(10)
    in_grace = [{
        "id": u["id"], "name": u.get("name"), "email": u.get("email"),
        "expires_at": u.get("membership_expires_at"),
        "tier": u.get("membership_tier"),
    } async for u in grace_cursor]
    new_cursor = db.users.find(
        {"created_at": {"$gte": seven_days_ago_iso}},
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
    # initialize object storage (non-blocking)
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.warning(f"Object storage init skipped: {e}")
    await seed_data()

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
