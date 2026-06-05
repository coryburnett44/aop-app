"""Events CRUD routes — list / get / create / update / delete / sub-events / rsvps.

The complex RSVP-creation, ticket payment, guest editing, and check-in flows
remain in server.py because they cross-cut with PayPal capture, Zeffy auto-
approve, Resend ticket emails, and Twilio SMS. The simple read+admin-CRUD subset
extracted here covers the bulk of event lookups served to the frontend.

`event_out` lives in server.py (used by many other endpoints) and is injected
as a kwarg into register().
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException

from models import EventIn, EventUpdateIn


def register(api, *, db, admin_tab_dep, event_out, iso, now_utc):

    @api.get("/events")
    async def list_events(upcoming: bool = False, include_sub_events: bool = False):
        query = {}
        if upcoming:
            query["start_at"] = {"$gte": iso(now_utc())}
        # By default the main /events grid hides sub-events — members reach them
        # by clicking into the parent (umbrella) event. Set include_sub_events=true
        # to flatten the tree (used by Admin/Calendar).
        if not include_sub_events:
            query["parent_event_id"] = {"$in": [None, ""]}
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
    async def create_event(body: EventIn, _: dict = Depends(admin_tab_dep("events"))):
        eid = str(uuid.uuid4())
        doc = body.model_dump()
        doc["start_at"] = iso(doc["start_at"]) if doc.get("start_at") else None
        doc["end_at"] = iso(doc["end_at"]) if doc.get("end_at") else None
        doc.update({"id": eid, "rsvp_count": 0, "created_at": iso(now_utc())})
        await db.events.insert_one(doc)
        return event_out(doc)

    @api.put("/events/{event_id}")
    async def update_event(event_id: str, body: EventUpdateIn, _: dict = Depends(admin_tab_dep("events"))):
        existing = await db.events.find_one({"id": event_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Event not found")
        updates = {}
        for k, v in body.model_dump().items():
            if v is None:
                continue
            if k in ("start_at", "end_at") and isinstance(v, datetime):
                updates[k] = iso(v)
            else:
                updates[k] = v
        # Stamp cancelled_at the first time cancelled flips on; clear it on revert.
        if "cancelled" in updates:
            if updates["cancelled"] and not existing.get("cancelled"):
                updates["cancelled_at"] = iso(now_utc())
            elif not updates["cancelled"]:
                updates["cancelled_at"] = None
                updates["cancellation_note"] = updates.get("cancellation_note", "") or ""
        if updates:
            await db.events.update_one({"id": event_id}, {"$set": updates})
        e = await db.events.find_one({"id": event_id}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Event not found")
        return event_out(e)

    @api.delete("/events/{event_id}")
    async def delete_event(event_id: str, _: dict = Depends(admin_tab_dep("events"))):
        await db.events.delete_one({"id": event_id})
        await db.rsvps.delete_many({"event_id": event_id})
        return {"ok": True}

    @api.get("/events/{event_id}/sub-events")
    async def list_sub_events(event_id: str):
        """List child events under a parent event (e.g. 10-Year anniversary umbrella)."""
        cursor = db.events.find({"parent_event_id": event_id}, {"_id": 0}).sort("start_at", 1).limit(100)
        items = await cursor.to_list(100)
        return [event_out(e) for e in items]

    @api.get("/events/{event_id}/rsvps")
    async def list_rsvps(event_id: str):
        cursor = db.rsvps.find({"event_id": event_id}, {"_id": 0}).limit(500)
        items = await cursor.to_list(500)
        return items
