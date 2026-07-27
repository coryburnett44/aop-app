"""News CRUD routes. Registered via register(api, deps) from server.py.

Iter 111: multi-image support (`images` list up to 5), layout `template` picker,
and public search via `?q=` on title / summary / body.
"""
import re
import uuid
from typing import Optional

from fastapi import Depends, HTTPException

from models import NewsIn, NewsUpdateIn


def news_out(n: dict) -> dict:
    return {
        "id": n["id"],
        "title": n["title"],
        "summary": n.get("summary", ""),
        "body": n.get("body", ""),
        "body_html": n.get("body_html", "") or "",
        "background_color": n.get("background_color", "") or "",
        "cover_image": n.get("cover_image", ""),
        "images": n.get("images", []) or [],
        "template": n.get("template", "classic"),
        "tags": n.get("tags", []),
        "author_name": n.get("author_name", ""),
        "created_at": n.get("created_at"),
    }


def register(api, *, db, admin_tab_dep, iso, now_utc):
    @api.get("/news")
    async def list_news(q: Optional[str] = None):
        """List news articles, newest first. Optional `q` filters on
        title / summary / body via case-insensitive regex. We escape the
        user input to prevent regex injection but still allow substring
        matches (which is what the member-facing search bar sends)."""
        query: dict = {}
        if q and q.strip():
            safe = re.escape(q.strip())
            query = {
                "$or": [
                    {"title": {"$regex": safe, "$options": "i"}},
                    {"summary": {"$regex": safe, "$options": "i"}},
                    {"body": {"$regex": safe, "$options": "i"}},
                    {"body_html": {"$regex": safe, "$options": "i"}},
                    {"tags": {"$regex": safe, "$options": "i"}},
                ],
            }
        cursor = db.news.find(query, {"_id": 0}).sort("created_at", -1).limit(200)
        items = await cursor.to_list(200)
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
