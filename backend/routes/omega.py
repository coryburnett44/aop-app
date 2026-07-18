"""Omega Chapter (in memoriam) tributes + featured hero banner.

Endpoints: /omega, /omega/options, /omega/tributes (CRUD), /omega/upload,
/omega/hero (GET+PUT).

Extracted from server.py (iter 128) as part of the ongoing server.py
modularization.
"""
import asyncio
import uuid
from typing import Literal, Optional

from fastapi import Depends, File, HTTPException, UploadFile
from pydantic import BaseModel


OMEGA_TEMPLATES = ["biography", "memorial-card", "in-service"]
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
    cover_image: str = ""
    synopsis: str = ""
    biography: str = ""
    epitaph: str = ""
    born_at: str = ""
    passed_at: str = ""
    location: str = ""
    rank: str = ""
    service_dates: str = ""


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


class OmegaHeroIn(BaseModel):
    image_url: str = ""
    title: str = ""
    caption: str = ""


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


def register(api, *, db, get_current_user, admin_tab_dep, put_object, public_user, iso, now_utc, image_ext, mime_by_ext):

    @api.get("/omega")
    async def omega_chapter():
        """Deceased members + explicit tributes, merged for the frontend."""
        member_cursor = db.users.find(
            {"$or": [{"status_override": "deceased"}, {"deceased_at": {"$nin": [None, ""]}}]},
            {"_id": 0, "password_hash": 0},
        ).sort("deceased_at", -1)
        members = await member_cursor.to_list(500)
        tribute_cursor = db.omega_tributes.find({}, {"_id": 0}).sort("created_at", -1)
        tributes = await tribute_cursor.to_list(500)
        tributes_by_uid = {t["user_id"]: t for t in tributes}
        out = []
        seen = set()
        for m in members:
            seen.add(m["id"])
            t = tributes_by_uid.get(m["id"])
            if t:
                out.append({"type": "tribute", **tribute_out(t, m)})
            else:
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
        for t in tributes:
            if t["user_id"] in seen:
                continue
            m = await db.users.find_one({"id": t["user_id"]}, {"_id": 0, "password_hash": 0})
            if not m:
                continue
            out.append({"type": "tribute", **tribute_out(t, m)})

        def sort_key(x):
            return x.get("passed_at") or (x.get("member") or {}).get("deceased_at") or ""

        out.sort(key=sort_key, reverse=True)
        return out

    @api.get("/omega/options")
    async def omega_options(_: dict = Depends(get_current_user)):
        return {"templates": OMEGA_TEMPLATES, "backgrounds": OMEGA_BACKGROUNDS}

    @api.post("/omega/tributes")
    async def create_tribute(body: OmegaTributeIn, admin: dict = Depends(admin_tab_dep("members"))):
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
        """Admin uploads a tribute cover photo. Returns {url}."""
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
        if ext not in image_ext:
            raise HTTPException(status_code=400, detail="Only images allowed (jpg, png, gif, webp)")
        content_type = file.content_type or mime_by_ext.get(ext, "image/jpeg")
        file_id = str(uuid.uuid4())
        storage_path = f"omega/{file_id}/{fname}"
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
