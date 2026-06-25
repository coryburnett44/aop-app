"""Events CRUD routes — list / get / create / update / delete / sub-events / rsvps.

The complex RSVP-creation, ticket payment, guest editing, and check-in flows
remain in server.py because they cross-cut with PayPal capture, Zeffy auto-
approve, Resend ticket emails, and Twilio SMS. The simple read+admin-CRUD subset
extracted here covers the bulk of event lookups served to the frontend.

`event_out` lives in server.py (used by many other endpoints) and is injected
as a kwarg into register().
"""
import asyncio
import html as _html
import uuid
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException

from models import EventIn, EventUpdateIn


def register(api, *, db, admin_tab_dep, event_out, iso, now_utc, resend_sdk=None, resend_api_key=None, resend_from=None, logger=None):

    async def _send_cancellation_emails(event: dict, child_events: list = None):
        """Email every RSVP'd member (and their guests with emails) that this
        event has been cancelled. Best-effort — failures are logged but never
        block the API response.

        When the cancelled event is an umbrella (has child_events), the email
        includes the list of cancelled sub-events for clarity.
        """
        if not resend_api_key or not resend_sdk:
            if logger:
                logger.info(f"[cancel-email] skipped (no RESEND_API_KEY) for event={event.get('id')}")
            return
        # Gather every event_id touched (the event itself + its cancelled children).
        affected_ids = [event["id"]] + [c["id"] for c in (child_events or [])]
        rsvps = await db.rsvps.find({"event_id": {"$in": affected_ids}}, {"_id": 0}).to_list(5000)
        # De-dup recipients by email — one umbrella cancellation = one email per
        # member even if they RSVP'd to multiple sub-events.
        recipients: dict = {}
        for r in rsvps:
            u = await db.users.find_one({"id": r.get("user_id")}, {"_id": 0, "email": 1, "name": 1})
            if u and u.get("email"):
                recipients.setdefault(u["email"].lower(), {"name": u.get("name", ""), "is_guest": False})
            for g in (r.get("guests") or []):
                gem = (g.get("email") or "").lower().strip()
                if gem:
                    recipients.setdefault(gem, {"name": g.get("name", ""), "is_guest": True})
        if not recipients:
            if logger:
                logger.info(f"[cancel-email] no RSVP'd recipients for event={event.get('id')}")
            return
        title = event.get("title", "this event")
        note = (event.get("cancellation_note") or "").strip()
        child_lines = ""
        if child_events:
            child_lines = "<ul>" + "".join(
                f"<li>{_html.escape(c.get('title') or 'Untitled')}</li>" for c in child_events
            ) + "</ul>"
        for email, meta in recipients.items():
            salutation = meta["name"] or ("Guest" if meta["is_guest"] else "Member")
            html_body = f"""
              <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#111">
                <h2 style="color:#C8102E;margin-bottom:8px">Event cancelled: {_html.escape(title)}</h2>
                <p>Hi {_html.escape(salutation)},</p>
                <p>We're writing to let you know that <strong>{_html.escape(title)}</strong> has been cancelled.</p>
                {f'<p style="background:#fff3cd;border-left:4px solid #f0ad4e;padding:10px 12px;border-radius:4px"><strong>Note from the team:</strong> {_html.escape(note)}</p>' if note else ''}
                {f'<p>Cancelled sub-events under this umbrella:</p>{child_lines}' if child_lines else ''}
                <p>Any RSVPs you placed for this event have been preserved on the calendar for reference but are no longer required. We'll be in touch with any reschedule plans.</p>
                <p style="color:#555;font-size:12px;margin-top:24px">— Alpha Omega Phi Military Fraternity &amp; Sorority, Inc.</p>
              </div>
            """
            try:
                await asyncio.to_thread(resend_sdk.Emails.send, {
                    "from": resend_from,
                    "to": [email],
                    "subject": f"Cancelled: {title}",
                    "html": html_body,
                })
            except Exception as ex:
                if logger:
                    logger.warning(f"[cancel-email] failed to {email} for event={event.get('id')}: {ex}")
        if logger:
            logger.info(f"[cancel-email] notified {len(recipients)} recipient(s) for event={event.get('id')}")

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
        # Direct admin toggles always clear `cancelled_via_parent` so subsequent
        # parent-uncancel cascades don't revert manual decisions.
        cascade_cancel = False
        cascade_uncancel = False
        if "cancelled" in updates:
            if updates["cancelled"] and not existing.get("cancelled"):
                updates["cancelled_at"] = iso(now_utc())
                updates["cancelled_via_parent"] = False
                cascade_cancel = True
            elif not updates["cancelled"] and existing.get("cancelled"):
                updates["cancelled_at"] = None
                updates["cancellation_note"] = updates.get("cancellation_note", "") or ""
                updates["cancelled_via_parent"] = False
                cascade_uncancel = True
        if updates:
            await db.events.update_one({"id": event_id}, {"$set": updates})

        # Cascade cancellation to sub-events. When a parent (umbrella) event is
        # cancelled, all its children must be cancelled too so members can no
        # longer RSVP to them. Children flipped by the cascade are tagged with
        # `cancelled_via_parent=true` so that un-cancelling the parent only
        # reverts the inherited cancellations and preserves any sub-event the
        # admin had previously cancelled individually.
        if cascade_cancel:
            child_set = {
                "cancelled": True,
                "cancelled_at": updates.get("cancelled_at") or iso(now_utc()),
                "cancelled_via_parent": True,
            }
            note = updates.get("cancellation_note")
            if note:
                child_set["cancellation_note"] = note
            await db.events.update_many(
                {"parent_event_id": event_id, "cancelled": {"$ne": True}},
                {"$set": child_set},
            )
        elif cascade_uncancel:
            await db.events.update_many(
                {"parent_event_id": event_id, "cancelled_via_parent": True},
                {"$set": {
                    "cancelled": False,
                    "cancelled_at": None,
                    "cancelled_via_parent": False,
                    "cancellation_note": "",
                }},
            )

        # Fire-and-forget cancellation email to RSVP'd members + guests.
        # Only on the cancel-on flip, not on un-cancel. Scheduled as a task so
        # the API response isn't held up by Resend latency.
        if cascade_cancel:
            child_events = []
            if cascade_cancel:
                async for c in db.events.find({"parent_event_id": event_id}, {"_id": 0, "id": 1, "title": 1}):
                    child_events.append(c)
            current = await db.events.find_one({"id": event_id}, {"_id": 0})
            try:
                asyncio.create_task(_send_cancellation_emails(current or {**existing, **updates}, child_events))
            except Exception as ex:
                if logger:
                    logger.warning(f"[cancel-email] could not schedule task: {ex}")

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
