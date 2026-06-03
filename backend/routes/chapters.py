"""Chapters CRUD routes."""
import re
import uuid
from fastapi import Depends, HTTPException

from models import ChapterIn, ChapterUpdateIn


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


def register(api, *, db, admin_tab_dep, iso, now_utc):

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
