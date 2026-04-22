from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
import secrets
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response, status
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict

# ---------- Config ----------
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60 * 24  # 1 day (simpler UX for demo)
REFRESH_TOKEN_DAYS = 7

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
        "membership_expires_at": u.get("membership_expires_at"),
        "created_at": u.get("created_at"),
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

# ---------- Mount ----------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown():
    client.close()
