"""Member directory + birthdays + new-members + status-override routes.

Extracted from server.py. The admin CRUD on members (create / update / delete /
role / tier / chapter / bulk-import / pending-intake-review) remains in server.py
because it cross-cuts with PayPal renewal capture, tier reconciliation, cascade
deletes (rsvps/hours/awards/photos/transactions), and the welcome-email flow.

`public_user` is imported from server.py via register() kwargs.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException

from models import StatusOverrideIn


def register(api, *, db, admin_tab_dep, public_user, iso, now_utc):

    @api.get("/members")
    async def list_members(q: Optional[str] = None, city: Optional[str] = None):
        query: dict = {}
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
                bd = (
                    datetime.fromisoformat(bd_str.replace("Z", "+00:00")).date()
                    if "T" in bd_str
                    else datetime.strptime(bd_str[:10], "%Y-%m-%d").date()
                )
            except Exception:
                continue
            try:
                this_year = bd.replace(year=today.year)
            except ValueError:  # Feb 29
                this_year = bd.replace(year=today.year, day=28)
            next_bd = this_year if this_year >= today else (
                bd.replace(year=today.year + 1)
                if bd.month != 2 or bd.day != 29
                else bd.replace(year=today.year + 1, day=28)
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
    async def set_member_status(user_id: str, body: StatusOverrideIn, admin: dict = Depends(admin_tab_dep("members"))):
        existing = await db.users.find_one({"id": user_id}, {"_id": 0, "status_override": 1, "status_history": 1})
        if not existing:
            raise HTTPException(status_code=404, detail="Member not found")
        updates: dict = {}
        if body.status is not None:
            updates["status_override"] = body.status
        if body.deceased_at is not None:
            updates["deceased_at"] = body.deceased_at
        elif body.status == "deceased":
            updates["deceased_at"] = iso(now_utc())
        elif body.status and body.status != "deceased":
            updates["deceased_at"] = None
        # Iter 111: track status changes so Service Ribbon eligibility can
        # tell when a member returned to active status.
        if body.status is not None and body.status != existing.get("status_override"):
            history = list(existing.get("status_history") or [])
            history.append({
                "status": body.status,
                "at": iso(now_utc()),
                "by": admin.get("id"),
                "by_name": admin.get("name", "Admin"),
            })
            updates["status_history"] = history
        if updates:
            await db.users.update_one({"id": user_id}, {"$set": updates})
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        return public_user(u)
