"""'Of The Year' awards — annual leadership recognition.

Seven categories, one winner per (category, year):
  - member_of_year, chapter_of_year
  - top_cs_member, top_cs_chapter             (community service)
  - top_fundraising_member, top_fundraising_chapter
  - top_recruiter                              (member only)

Endpoints:
  GET    /of-the-year                  — list all (filter by year/category)
  GET    /of-the-year/current          — enriched current-year winners (home widget)
  POST   /of-the-year                  — admin add (idempotent on category+year via unique idx)
  PUT    /of-the-year/{id}             — admin update
  DELETE /of-the-year/{id}             — admin remove
"""
from typing import Optional
from datetime import datetime as _dt
import uuid

from fastapi import Depends, HTTPException

from models import OfTheYearIn, OfTheYearUpdateIn


CATEGORY_LABELS = {
    "member_of_year": "Member of the Year",
    "chapter_of_year": "Chapter of the Year",
    "top_cs_member": "Top Community Service Member",
    "top_cs_chapter": "Top Community Service Chapter",
    "top_fundraising_member": "Top Fundraising Member",
    "top_fundraising_chapter": "Top Fundraising Chapter",
    "top_recruiter": "Top Member Recruiter",
}
MEMBER_CATEGORIES = {"member_of_year", "top_cs_member", "top_fundraising_member", "top_recruiter"}
CHAPTER_CATEGORIES = {"chapter_of_year", "top_cs_chapter", "top_fundraising_chapter"}


def register(api, *, db, admin_tab_dep, get_current_user, iso, now_utc, logger):
    def _out(d: dict, *, user: Optional[dict] = None, chapter: Optional[dict] = None) -> dict:
        return {
            "id": d["id"],
            "category": d["category"],
            "category_label": CATEGORY_LABELS.get(d["category"], d["category"]),
            "year": d["year"],
            "user_id": d.get("user_id"),
            "user_name": (user or {}).get("name") if user else d.get("user_name"),
            "user_avatar_url": (user or {}).get("avatar_url") if user else d.get("user_avatar_url"),
            "user_chapter_id": (user or {}).get("chapter_id") if user else d.get("user_chapter_id"),
            "chapter_id": d.get("chapter_id"),
            "chapter_name": (chapter or {}).get("name") if chapter else d.get("chapter_name"),
            "chapter_logo_url": (chapter or {}).get("logo_url") if chapter else d.get("chapter_logo_url"),
            "note": d.get("note") or "",
            "created_at": d.get("created_at"),
            "created_by_name": d.get("created_by_name") or "",
        }

    async def _enrich(rows: list) -> list:
        """Bulk-load referenced users and chapters once, then serialize."""
        uids = [r["user_id"] for r in rows if r.get("user_id")]
        cids = [r["chapter_id"] for r in rows if r.get("chapter_id")]
        users: dict = {}
        chapters: dict = {}
        if uids:
            async for u in db.users.find(
                {"id": {"$in": uids}},
                {"_id": 0, "id": 1, "name": 1, "avatar_url": 1, "chapter_id": 1},
            ):
                users[u["id"]] = u
        if cids:
            async for c in db.chapters.find(
                {"id": {"$in": cids}},
                {"_id": 0, "id": 1, "name": 1, "image_url": 1},
            ):
                chapters[c["id"]] = c
        out = []
        for r in rows:
            u = users.get(r.get("user_id") or "")
            c = chapters.get(r.get("chapter_id") or "")
            out.append(_out(r, user=u, chapter=c))
        return out

    @api.get("/of-the-year/categories")
    async def list_categories(_: dict = Depends(get_current_user)):
        """For the frontend admin editor — labels + which categories take a
        member vs. a chapter as the winner."""
        return [
            {"key": k, "label": v, "target": "chapter" if k in CHAPTER_CATEGORIES else "member"}
            for k, v in CATEGORY_LABELS.items()
        ]

    @api.get("/of-the-year")
    async def list_of_the_year(
        year: Optional[int] = None,
        category: Optional[str] = None,
        _: dict = Depends(get_current_user),
    ):
        q: dict = {}
        if year is not None:
            q["year"] = year
        if category:
            q["category"] = category
        rows = await db.of_the_year_awards.find(q, {"_id": 0}).sort([("year", -1), ("category", 1)]).to_list(500)
        return await _enrich(rows)

    @api.get("/of-the-year/current")
    async def current_winners(_: dict = Depends(get_current_user)):
        """All winners for the current calendar year — used by the home-page
        widget. Returns a dict keyed by category for easy frontend rendering."""
        year = now_utc().year
        rows = await db.of_the_year_awards.find({"year": year}, {"_id": 0}).to_list(50)
        enriched = await _enrich(rows)
        by_cat = {r["category"]: r for r in enriched}
        return {"year": year, "categories": list(CATEGORY_LABELS.keys()), "winners": by_cat,
                "labels": CATEGORY_LABELS}

    @api.post("/of-the-year")
    async def create_of_the_year(body: OfTheYearIn, admin: dict = Depends(admin_tab_dep("awards"))):
        # Enforce that the right target type is supplied for the category.
        if body.category in MEMBER_CATEGORIES and not body.user_id:
            raise HTTPException(status_code=400, detail=f"{CATEGORY_LABELS[body.category]} requires a member.")
        if body.category in CHAPTER_CATEGORIES and not body.chapter_id:
            raise HTTPException(status_code=400, detail=f"{CATEGORY_LABELS[body.category]} requires a chapter.")
        # Block duplicates (one winner per category per year).
        existing = await db.of_the_year_awards.find_one({"category": body.category, "year": body.year})
        if existing:
            raise HTTPException(status_code=400, detail=f"A winner is already recorded for {CATEGORY_LABELS[body.category]} in {body.year}.")
        # Validate the referenced user/chapter exists.
        if body.user_id:
            if not await db.users.find_one({"id": body.user_id}, {"_id": 1}):
                raise HTTPException(status_code=404, detail="Selected member not found.")
        if body.chapter_id:
            if not await db.chapters.find_one({"id": body.chapter_id}, {"_id": 1}):
                raise HTTPException(status_code=404, detail="Selected chapter not found.")
        doc = {
            "id": str(uuid.uuid4()),
            "category": body.category,
            "year": body.year,
            "user_id": body.user_id,
            "chapter_id": body.chapter_id,
            "note": (body.note or "").strip(),
            "created_at": iso(now_utc()),
            "created_by": admin["id"],
            "created_by_name": admin.get("name", "Admin"),
        }
        await db.of_the_year_awards.insert_one(doc)
        return (await _enrich([doc]))[0]

    @api.put("/of-the-year/{aid}")
    async def update_of_the_year(aid: str, body: OfTheYearUpdateIn, _: dict = Depends(admin_tab_dep("awards"))):
        existing = await db.of_the_year_awards.find_one({"id": aid})
        if not existing:
            raise HTTPException(status_code=404, detail="Award not found")
        sets: dict = {}
        if body.year is not None:
            # If the year is changing, make sure no other row already owns the new (category, year) pair.
            if body.year != existing.get("year"):
                clash = await db.of_the_year_awards.find_one({"category": existing["category"], "year": body.year, "id": {"$ne": aid}})
                if clash:
                    raise HTTPException(status_code=400, detail=f"A winner is already recorded for {CATEGORY_LABELS.get(existing['category'])} in {body.year}.")
            sets["year"] = body.year
        if body.user_id is not None:
            if existing["category"] in CHAPTER_CATEGORIES and body.user_id:
                raise HTTPException(status_code=400, detail="This category awards a chapter, not a member.")
            if body.user_id and not await db.users.find_one({"id": body.user_id}, {"_id": 1}):
                raise HTTPException(status_code=404, detail="Selected member not found.")
            sets["user_id"] = body.user_id
        if body.chapter_id is not None:
            if existing["category"] in MEMBER_CATEGORIES and body.chapter_id:
                raise HTTPException(status_code=400, detail="This category awards a member, not a chapter.")
            if body.chapter_id and not await db.chapters.find_one({"id": body.chapter_id}, {"_id": 1}):
                raise HTTPException(status_code=404, detail="Selected chapter not found.")
            sets["chapter_id"] = body.chapter_id
        if body.note is not None:
            sets["note"] = (body.note or "").strip()
        if not sets:
            return (await _enrich([existing]))[0]
        await db.of_the_year_awards.update_one({"id": aid}, {"$set": sets})
        fresh = await db.of_the_year_awards.find_one({"id": aid}, {"_id": 0})
        return (await _enrich([fresh]))[0]

    @api.delete("/of-the-year/{aid}")
    async def delete_of_the_year(aid: str, _: dict = Depends(admin_tab_dep("awards"))):
        r = await db.of_the_year_awards.delete_one({"id": aid})
        if r.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Award not found")
        return {"ok": True}
