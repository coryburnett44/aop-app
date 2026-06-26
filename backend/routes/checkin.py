"""QR check-in scan/lookup routes.

Extracted from routes/rsvps.py to keep that file under 1k lines. The QR token
encoding/decoding helpers (`make_ticket_token`, `decode_ticket_token`) live in
routes/rsvps.py because they're shared with the ticket-email rendering path;
this module receives the decoder via dependency injection.

Endpoints:
  GET  /api/checkin/lookup/{token}  — decode QR (no auth) for the landing page
  POST /api/checkin/scan/{token}    — admin scans QR to record a check-in
"""
import uuid

from fastapi import Depends, HTTPException


def register(api, *, db, get_current_user, event_out, iso, now_utc, decode_ticket_token):
    @api.get("/checkin/lookup/{token}")
    async def checkin_lookup(token: str):
        """Decode a QR token and return ticket info — used by the
        /checkin/:token landing page to show 'who is this'. Does NOT require
        auth (the page itself enforces admin login before recording the
        check-in)."""
        try:
            payload = decode_ticket_token(token)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid or expired ticket QR")
        event = await db.events.find_one({"id": payload["event_id"]}, {"_id": 0})
        if not event:
            raise HTTPException(status_code=404, detail="Event no longer exists")
        return {
            "event": event_out(event),
            "ticket_id": payload["ticket_id"],
            "kind": payload["kind"],
            "ticket_type": payload.get("ticket_type", "general"),
            "name": payload.get("name", ""),
        }

    @api.post("/checkin/scan/{token}")
    async def checkin_scan(token: str, user: dict = Depends(get_current_user)):
        """Admin scans the QR. Token is decoded → check-in is recorded
        immediately. Idempotent: subsequent scans return the existing check-in
        row with already_checked_in=true."""
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins can scan tickets to check in attendees.")
        try:
            payload = decode_ticket_token(token)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid or expired ticket QR")
        event_id = payload["event_id"]
        ticket_id = payload["ticket_id"]
        ticket_type = payload.get("ticket_type", "general")
        kind = payload["kind"]
        holder_name = payload.get("name", "")
        event = await db.events.find_one({"id": event_id}, {"_id": 0})
        if not event:
            raise HTTPException(status_code=404, detail="Event no longer exists")
        existing = await db.checkins.find_one({"event_id": event_id, "ticket_id": ticket_id}, {"_id": 0})
        if existing:
            return {"already_checked_in": True, "checkin": existing, "event": event_out(event)}
        if kind == "member":
            rsvp = await db.rsvps.find_one({"event_id": event_id, "ticket_id": ticket_id})
            if not rsvp:
                raise HTTPException(status_code=410, detail="This ticket is no longer valid (the member cancelled their RSVP).")
            doc = {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "user_id": rsvp.get("user_id"),
                "user_name": rsvp.get("user_name", holder_name),
                "ticket_id": ticket_id,
                "ticket_type": ticket_type,
                "guest_name": "",
                "checked_in_at": iso(now_utc()),
                "checked_in_by": user["id"],
                "checked_in_by_name": user.get("name", ""),
            }
        else:  # guest
            rsvp = await db.rsvps.find_one({"event_id": event_id, "guests.ticket_id": ticket_id})
            if not rsvp:
                raise HTTPException(status_code=410, detail="This guest ticket is no longer on any RSVP.")
            doc = {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "user_id": None,
                "user_name": holder_name or "Guest",
                "ticket_id": ticket_id,
                "ticket_type": ticket_type,
                "guest_name": holder_name,
                "host_user_id": rsvp.get("user_id"),
                "host_user_name": rsvp.get("user_name", ""),
                "checked_in_at": iso(now_utc()),
                "checked_in_by": user["id"],
                "checked_in_by_name": user.get("name", ""),
            }
        await db.checkins.insert_one(doc)
        doc.pop("_id", None)
        return {"already_checked_in": False, "checkin": doc, "event": event_out(event)}
