"""Membership tiers CRUD routes."""
import uuid
from fastapi import Depends, HTTPException

from models import TierIn, TierUpdateIn


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


def register(api, *, db, admin_tab_dep):

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
