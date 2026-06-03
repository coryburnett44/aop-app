"""Pages CRUD routes. Registered via register(api, deps) from server.py."""
import uuid
from fastapi import Depends, HTTPException

from models import PageIn, PageUpdateIn, PAGE_BLOCK_TYPES


def page_out(p: dict) -> dict:
    return {
        "id": p["id"],
        "slug": p["slug"],
        "title": p["title"],
        "body": p.get("body", ""),
        "blocks": p.get("blocks") or [],
        "updated_at": p.get("updated_at"),
    }


def _validate_blocks(blocks):
    for b in (blocks or []):
        if b.get("type") not in PAGE_BLOCK_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid block type: {b.get('type')}")


def register(api, *, db, admin_tab_dep, iso, now_utc):
    """Wire the /pages routes onto the given api router using the supplied deps."""

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
        _validate_blocks(doc.get("blocks"))
        doc.update({"id": str(uuid.uuid4()), "updated_at": iso(now_utc())})
        await db.pages.insert_one(doc)
        return page_out(doc)

    @api.put("/pages/{slug}")
    async def update_page(slug: str, body: PageUpdateIn, _: dict = Depends(admin_tab_dep("pages"))):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "blocks" in updates:
            _validate_blocks(updates["blocks"])
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
