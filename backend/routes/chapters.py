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
        # Iter 154 — Lieutenant Governor spotlight. Enriched at list-time
        # with `lieutenant_governor: {id, name, avatar_url, bio, title}` if
        # a Lt. Governor is assigned; otherwise the field is omitted.
        "lieutenant_governor_user_id": c.get("lieutenant_governor_user_id") or None,
        "lieutenant_governor": c.get("lieutenant_governor") or None,
    }


def register(api, *, db, admin_tab_dep, iso, now_utc):

    async def _enrich_lt_governor(chapter: dict) -> dict:
        """Attach a compact Lt. Governor object so the public /chapters
        page doesn't need N extra /members/{id} calls to render the
        spotlight."""
        uid = chapter.get("lieutenant_governor_user_id")
        if not uid:
            return chapter
        u = await db.users.find_one(
            {"id": uid},
            {"_id": 0, "id": 1, "name": 1, "first_name": 1, "last_name": 1,
             "avatar_url": 1, "bio": 1, "title": 1, "email": 1},
        )
        if not u:
            return chapter
        full = u.get("name") or f"{u.get('first_name','')} {u.get('last_name','')}".strip() or "Lieutenant Governor"
        chapter["lieutenant_governor"] = {
            "id": u["id"],
            "name": full,
            "avatar_url": u.get("avatar_url", ""),
            "bio": (u.get("bio") or "").strip(),
            "title": u.get("title", ""),
            "email": u.get("email", ""),
        }
        return chapter

    async def with_chapter_counts(chapters):
        out = []
        for c in chapters:
            c["member_count"] = await db.users.count_documents({"chapter_id": c["id"]})
            await _enrich_lt_governor(c)
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
        # Validate the LT. Governor user (if being set) actually exists.
        # Empty string clears the assignment; None means "don't touch".
        if "lieutenant_governor_user_id" in updates:
            lg = updates["lieutenant_governor_user_id"]
            if lg:
                u = await db.users.find_one({"id": lg}, {"_id": 0, "id": 1})
                if not u:
                    raise HTTPException(status_code=400, detail="Selected Lt. Governor member not found.")
        if updates:
            await db.chapters.update_one({"id": chapter_id}, {"$set": updates})
        c = await db.chapters.find_one({"id": chapter_id}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Chapter not found")
        c["member_count"] = await db.users.count_documents({"chapter_id": chapter_id})
        await _enrich_lt_governor(c)
        return chapter_out(c)

    @api.delete("/chapters/{chapter_id}")
    async def delete_chapter(chapter_id: str, _: dict = Depends(admin_tab_dep("chapters"))):
        await db.chapters.delete_one({"id": chapter_id})
        await db.users.update_many({"chapter_id": chapter_id}, {"$unset": {"chapter_id": ""}})
        return {"ok": True}
