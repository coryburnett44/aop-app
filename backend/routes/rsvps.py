"""RSVP, paid-event-approval, ticket email, and check-in scan routes.

Extracted from server.py. Mirrors the pattern used by the other route modules:
the host process calls `register(api, **deps)` once at startup and we attach
all the endpoints + helper functions to the shared `api` router.

Endpoints registered:
  POST /events/{event_id}/rsvp                       — toggle free RSVP
  POST /events/{event_id}/payment/confirm            — submit Zeffy receipt for paid events
  PUT  /transactions/{tx_id}/approve-event-ticket    — admin approves a pending event-ticket tx
  PUT  /events/{event_id}/rsvp/guests                — edit RSVP guest list in-place
  GET  /me/events                                    — list events the caller has RSVP'd to
  GET  /checkin/lookup/{token}                       — decode a QR token (no auth needed)
  POST /checkin/scan/{token}                         — admin scans the QR to check someone in

The module also exposes `_create_rsvp_and_email_ticket` and
`send_rsvp_ticket_email` on `register` so any back-compat shims in server.py
can keep importing them via `routes_rsvps.register.create_rsvp_and_email_ticket`.
"""
import asyncio
import base64
import io
import os
import uuid
from typing import Optional

import jwt
import qrcode
from fastapi import Depends, HTTPException

from models import EventRsvpIn, EventPaymentConfirmIn, GuestIn


def register(
    api,
    *,
    db,
    get_current_user,
    require_admin,
    event_out,
    iso,
    now_utc,
    resend_sdk,
    resend_api_key,
    resend_from,
    jwt_secret,
    jwt_algorithm,
    logger,
):
    # ---------- QR ticket token helpers ----------
    def make_ticket_token(event_id: str, ticket_id: str, kind: str, ticket_type: str, name: str = "") -> str:
        """Signed JWT carried in the QR code. Validated server-side at scan."""
        payload = {
            "event_id": event_id,
            "ticket_id": ticket_id,
            "kind": kind,  # "member" | "guest"
            "ticket_type": ticket_type or "general",
            "name": name or "",
            "iat": int(now_utc().timestamp()),
        }
        return jwt.encode(payload, jwt_secret(), algorithm=jwt_algorithm)

    def decode_ticket_token(token: str) -> dict:
        return jwt.decode(token, jwt_secret(), algorithms=[jwt_algorithm])

    def make_qr_png_b64(payload_url: str) -> str:
        """Return a base64-encoded PNG for inline embedding (data: URI)."""
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
        qr.add_data(payload_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0A2463", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def _ticket_card_html(holder: str, ticket_type: str, qr_png_b64: str, event_title: str, when: str, where: str) -> str:
        pretty = {"vip": "VIP", "all_access": "All Access", "general": "General Admission",
                  "guest": "Guest", "speaker": "Speaker", "volunteer": "Volunteer"}.get(ticket_type, ticket_type.title())
        import html as _h
        return f"""
        <div style="border:2px solid #0A2463;border-radius:18px;padding:20px;margin:14px 0;background:#fff;display:flex;gap:16px;align-items:center">
          <div style="flex-shrink:0">
            <img src="data:image/png;base64,{qr_png_b64}" alt="ticket QR" width="160" height="160" style="display:block;border-radius:6px"/>
          </div>
          <div style="flex:1;font-family:-apple-system,sans-serif;color:#222">
            <div style="font-size:11px;text-transform:uppercase;letter-spacing:.16em;color:#C8102E;font-weight:700">Ticket · {_h.escape(pretty)}</div>
            <div style="font-size:18px;font-weight:800;color:#0A2463;margin-top:4px">{_h.escape(holder)}</div>
            <div style="font-size:13px;color:#444;margin-top:8px">{_h.escape(event_title)}</div>
            <div style="font-size:12px;color:#666;margin-top:2px">{_h.escape(when)}{' · ' + _h.escape(where) if where else ''}</div>
            <div style="font-size:10px;color:#888;margin-top:10px;line-height:1.4">Show this QR at the door. Admin staff will scan it to check you in.</div>
          </div>
        </div>
        """

    async def send_rsvp_ticket_email(member: dict, event: dict, rsvp: dict) -> bool:
        """Email the member their digital ticket(s) — one QR per attendee (member + each guest).
        Idempotent: safe to call again after guest-list edits."""
        if not resend_api_key:
            logger.info(f"RSVP ticket email skipped (no RESEND_API_KEY) for {member.get('email')}")
            return False
        email = (member.get("email") or "").strip()
        if not email:
            return False
        frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
        event_title = event.get("title", "Alpha Omega Phi Event")
        when = ""
        try:
            from datetime import datetime as _dt
            sa = event.get("start_at")
            if sa:
                d = _dt.fromisoformat(sa.replace("Z", "+00:00"))
                when = d.strftime("%A, %b %d, %Y · %I:%M %p UTC")
        except Exception:
            when = event.get("start_at", "")
        where = event.get("location", "")
        cards_html = []
        # Member ticket — backfill missing ticket_id onto the RSVP doc so future
        # re-sends use the same QR (instead of generating a different one each call).
        member_ticket_id = rsvp.get("ticket_id")
        if not member_ticket_id:
            member_ticket_id = str(uuid.uuid4())
            await db.rsvps.update_one({"id": rsvp.get("id")}, {"$set": {"ticket_id": member_ticket_id}})
        member_token = make_ticket_token(event["id"], member_ticket_id, "member", rsvp.get("ticket_type", "general"), member.get("name", ""))
        member_url = f"{frontend}/checkin/{member_token}"
        cards_html.append(_ticket_card_html(member.get("name", "Member"), rsvp.get("ticket_type", "general"),
                                            make_qr_png_b64(member_url), event_title, when, where))
        # Guest tickets — backfill per-guest ticket_id as well.
        guests = rsvp.get("guests", []) or []
        guests_dirty = False
        for g in guests:
            if not g.get("ticket_id"):
                g["ticket_id"] = str(uuid.uuid4())
                guests_dirty = True
            gtoken = make_ticket_token(event["id"], g["ticket_id"], "guest", g.get("ticket_type", "general"), g.get("name", ""))
            gurl = f"{frontend}/checkin/{gtoken}"
            cards_html.append(_ticket_card_html(g.get("name", "Guest"), g.get("ticket_type", "general"), make_qr_png_b64(gurl), event_title, when, where))
        if guests_dirty:
            await db.rsvps.update_one({"id": rsvp.get("id")}, {"$set": {"guests": guests}})
        body = f"""
        <div style="font-family:-apple-system,sans-serif;max-width:640px;margin:0 auto;padding:24px;background:#f7f5f0">
          <h1 style="color:#0A2463;margin:0 0 4px;font-size:26px">You're going! 🎉</h1>
          <div style="color:#666;font-size:13px">RSVP confirmed for <strong>{event_title}</strong></div>
          <div style="background:#fff;border-radius:12px;padding:14px 18px;margin:18px 0;font-size:13px;line-height:1.55">
            <div><strong>When:</strong> {when or 'TBA'}</div>
            <div><strong>Where:</strong> {where or 'TBA'}</div>
            <div><strong>Tickets:</strong> {len(cards_html)} ({1 + len(rsvp.get('guests', []) or [])} attendees total)</div>
          </div>
          {''.join(cards_html)}
          <p style="font-size:12px;color:#888;margin-top:18px;line-height:1.6">Each person needs their own QR ticket at the door. To add or remove guests, head back to <a href="{frontend}/events/{event['id']}" style="color:#C8102E">your RSVP page</a>.</p>
        </div>
        """
        try:
            # CC the AOP events inbox so the National office has a copy of every
            # ticket (including the QR codes). Configurable via EVENTS_INBOX_EMAIL.
            events_inbox = os.environ.get("EVENTS_INBOX_EMAIL", "info@alphaomegaphi.org")
            to_list = [email]
            if events_inbox and events_inbox.lower() != email.lower():
                to_list.append(events_inbox)
            await asyncio.to_thread(resend_sdk.Emails.send, {
                "from": resend_from,
                "to": to_list,
                "subject": f"Your tickets — {event_title}",
                "html": body,
                "tags": [{"name": "type", "value": "rsvp_ticket"}, {"name": "event_id", "value": event["id"]}],
            })
            logger.info(f"RSVP ticket email sent to {email} (+ {events_inbox}) for {event_title} ({len(cards_html)} tickets)")
            return True
        except Exception as e:
            logger.warning(f"RSVP ticket email failed for {email}: {e}")
            return False

    # ---------- RSVP creation helper (shared by free + paid-event paths) ----------
    async def _create_rsvp_and_email_ticket(
        user: dict,
        event: dict,
        ticket_type: str,
        guests_raw: list,
        payment_tx_id: Optional[str] = None,
    ) -> dict:
        """Shared logic: create RSVP doc, increment counters, send ticket email.
        Used by the free-RSVP and the paid-event-after-approval paths."""
        event_id = event["id"]
        guests = []
        for g in (guests_raw or []):
            gd = g.model_dump() if hasattr(g, "model_dump") else dict(g)
            gd["ticket_id"] = str(uuid.uuid4())
            gd["ticket_type"] = (gd.get("ticket_type") or "general")
            gd["checked_in_at"] = None
            guests.append(gd)
        seats_needed = 1 + len(guests)
        if event.get("capacity", 0) > 0 and (event.get("rsvp_count", 0) + event.get("guest_count", 0) + seats_needed) > event["capacity"]:
            raise HTTPException(status_code=400, detail="Event does not have enough seats")
        member_ticket_id = str(uuid.uuid4())
        rsvp_doc = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "user_id": user["id"],
            "user_name": user.get("name", ""),
            "ticket_id": member_ticket_id,
            "ticket_type": ticket_type or "general",
            "guests": guests,
            "payment_tx_id": payment_tx_id,
            "created_at": iso(now_utc()),
        }
        await db.rsvps.insert_one(rsvp_doc)
        await db.events.update_one(
            {"id": event_id},
            {"$inc": {"rsvp_count": 1, "guest_count": len(guests)}},
        )
        try:
            asyncio.create_task(send_rsvp_ticket_email(user, event, rsvp_doc))
        except Exception as ex:
            logger.warning(f"Failed to schedule ticket email: {ex}")
        return rsvp_doc

    # ---------- Routes ----------
    @api.post("/events/{event_id}/rsvp")
    async def rsvp_event(event_id: str, body: Optional[EventRsvpIn] = None, user: dict = Depends(get_current_user)):
        e = await db.events.find_one({"id": event_id}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Event not found")
        if e.get("cancelled"):
            raise HTTPException(
                status_code=400,
                detail="This event has been cancelled — RSVPs are closed.",
            )
        if e.get("is_paid"):
            raise HTTPException(
                status_code=402,
                detail="This event requires payment. Pay via Zeffy and submit your receipt to /events/{id}/payment/confirm.",
            )
        # Parent events (which group sub-events) cannot be RSVP'd directly —
        # members RSVP individually to each sub-event listed underneath.
        has_children = await db.events.find_one({"parent_event_id": event_id})
        if has_children:
            raise HTTPException(
                status_code=400,
                detail="This event is an umbrella — please RSVP to each sub-event below individually.",
            )
        existing = await db.rsvps.find_one({"event_id": event_id, "user_id": user["id"]})
        if existing:
            prev_guests = len(existing.get("guests", []) or [])
            await db.rsvps.delete_one({"_id": existing["_id"]})
            await db.events.update_one(
                {"id": event_id},
                {"$inc": {"rsvp_count": -1, "guest_count": -prev_guests}},
            )
            return {"rsvped": False}
        member_ticket_type = (body.ticket_type if body else None) or "general"
        guests_raw = body.guests if body else []
        rsvp_doc = await _create_rsvp_and_email_ticket(
            user=user,
            event=e,
            ticket_type=member_ticket_type,
            guests_raw=guests_raw,
        )
        return {"rsvped": True, "guests": len(rsvp_doc["guests"]), "ticket_id": rsvp_doc["ticket_id"]}

    @api.post("/events/{event_id}/payment/confirm")
    async def event_payment_confirm(
        event_id: str,
        body: EventPaymentConfirmIn,
        user: dict = Depends(get_current_user),
    ):
        """Member submits the Zeffy receipt # after paying for a paid event.

        Behaviour:
        - Default: creates a PENDING transaction (purpose='event_ticket', event_id) for admin review.
          The RSVP is NOT created and no ticket is emailed until admin approves.
        - If the user has `trust_zeffy=true` AND the receipt matches a known Zeffy format,
          auto-approve immediately: create the RSVP, fire the ticket email, mark tx completed.

        Mirrors the Zeffy dues flow exactly so admins use one mental model for both.
        """
        e = await db.events.find_one({"id": event_id}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Event not found")
        if e.get("cancelled"):
            raise HTTPException(status_code=400, detail="This event has been cancelled — payments are closed.")
        if not e.get("is_paid"):
            raise HTTPException(status_code=400, detail="This event is free — RSVP directly without payment.")
        # Block double-payments: if there's already a pending or completed event_ticket
        # tx for this user+event, surface it instead of creating a duplicate.
        existing_tx = await db.transactions.find_one({
            "user_id": user["id"],
            "event_id": event_id,
            "purpose": "event_ticket",
            "status": {"$in": ["pending", "completed"]},
        })
        if existing_tx:
            raise HTTPException(
                status_code=400,
                detail=f"You already submitted a {existing_tx.get('status')} payment for this event. Check Reports → Event-ticket approvals.",
            )

        from routes.payments import classify_zeffy_receipt
        confirmation = (body.confirmation or "").strip()
        receipt_format = classify_zeffy_receipt(confirmation)
        pattern_ok = receipt_format is not None
        auto_approve = bool(user.get("trust_zeffy")) and pattern_ok

        tx_id = str(uuid.uuid4())
        tx_doc = {
            "id": tx_id,
            "user_id": user["id"],
            "user_name": user.get("name", ""),
            "type": "fee",
            "amount": float(e.get("payment_amount") or 0.0),
            "currency": "USD",
            "description": f"Event ticket: {e.get('title', '')} (ref: {confirmation})",
            "status": "completed" if auto_approve else "pending",
            "purpose": "event_ticket",
            "provider": "zeffy",
            "event_id": event_id,
            "event_title": e.get("title", ""),
            "rsvp_ticket_type": body.ticket_type or "general",
            "rsvp_guests": [g.model_dump() for g in (body.guests or [])],
            "zeffy_confirmation": confirmation,
            "zeffy_receipt_format": receipt_format,
            "zeffy_auto_approved": auto_approve,
            "created_at": iso(now_utc()),
        }
        if auto_approve:
            tx_doc["approved_at"] = iso(now_utc())
            tx_doc["approved_by"] = "system:zeffy-trust"
            tx_doc["approved_by_name"] = "Auto-approval (trusted member)"
        await db.transactions.insert_one(tx_doc)

        if auto_approve:
            rsvp_doc = await _create_rsvp_and_email_ticket(
                user=user,
                event=e,
                ticket_type=tx_doc["rsvp_ticket_type"],
                guests_raw=body.guests or [],
                payment_tx_id=tx_id,
            )
            await db.transactions.update_one({"id": tx_id}, {"$set": {"rsvp_id": rsvp_doc["id"]}})
            return {
                "transaction_id": tx_id,
                "status": "completed",
                "auto_approved": True,
                "rsvp_id": rsvp_doc["id"],
                "ticket_id": rsvp_doc["ticket_id"],
                "message": "🎉 Auto-approved — your ticket is on its way to your inbox.",
            }
        return {
            "transaction_id": tx_id,
            "status": "pending",
            "auto_approved": False,
            "message": "Submitted for admin verification — you'll get your ticket once admin approves your Zeffy receipt.",
        }

    @api.put("/transactions/{tx_id}/approve-event-ticket")
    async def admin_approve_event_ticket(tx_id: str, admin: dict = Depends(require_admin)):
        """Admin approves a pending event_ticket transaction → creates the RSVP and emails the ticket."""
        tx = await db.transactions.find_one({"id": tx_id})
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")
        if tx.get("purpose") != "event_ticket":
            raise HTTPException(status_code=400, detail="Not an event-ticket transaction")
        if tx.get("status") == "completed":
            return {"ok": True, "already": True, "rsvp_id": tx.get("rsvp_id")}
        e = await db.events.find_one({"id": tx.get("event_id")}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Event no longer exists")
        user = await db.users.find_one({"id": tx["user_id"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="Member not found")

        guests_raw = [GuestIn(**g) for g in (tx.get("rsvp_guests") or [])]
        rsvp_doc = await _create_rsvp_and_email_ticket(
            user=user,
            event=e,
            ticket_type=tx.get("rsvp_ticket_type") or "general",
            guests_raw=guests_raw,
            payment_tx_id=tx_id,
        )
        await db.transactions.update_one({"id": tx_id}, {"$set": {
            "status": "completed",
            "approved_at": iso(now_utc()),
            "approved_by": admin["id"],
            "approved_by_name": admin.get("name", "Admin"),
            "rsvp_id": rsvp_doc["id"],
        }})
        return {"ok": True, "rsvp_id": rsvp_doc["id"], "ticket_id": rsvp_doc["ticket_id"]}

    @api.put("/events/{event_id}/rsvp/guests")
    async def update_rsvp_guests(event_id: str, body: EventRsvpIn, user: dict = Depends(get_current_user)):
        """Update the guest list on an existing RSVP without toggling it."""
        rsvp = await db.rsvps.find_one({"event_id": event_id, "user_id": user["id"]})
        if not rsvp:
            raise HTTPException(status_code=404, detail="You have not RSVPed for this event")
        e = await db.events.find_one({"id": event_id}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Event not found")
        if e.get("cancelled"):
            raise HTTPException(status_code=400, detail="This event has been cancelled — guest list is locked.")
        prev_guests = rsvp.get("guests", []) or []
        prev_by_name = {(g.get("name") or "").strip().lower(): g for g in prev_guests}
        new_guests = []
        for g in body.guests:
            gd = g.model_dump()
            key = (gd.get("name") or "").strip().lower()
            old = prev_by_name.get(key)
            gd["ticket_id"] = (old.get("ticket_id") if old else None) or str(uuid.uuid4())
            gd["ticket_type"] = gd.get("ticket_type") or (old.get("ticket_type") if old else "general")
            gd["checked_in_at"] = old.get("checked_in_at") if old else None
            new_guests.append(gd)
        sets = {"guests": new_guests}
        if body.ticket_type:
            sets["ticket_type"] = body.ticket_type
        delta = len(new_guests) - len(prev_guests)
        if e.get("capacity", 0) > 0 and (e.get("rsvp_count", 0) + e.get("guest_count", 0) + delta) > e["capacity"]:
            raise HTTPException(status_code=400, detail="Event does not have enough seats")
        await db.rsvps.update_one({"_id": rsvp["_id"]}, {"$set": sets})
        if delta:
            await db.events.update_one({"id": event_id}, {"$inc": {"guest_count": delta}})
        # Re-send the ticket email so the member has the up-to-date guest QR codes.
        try:
            fresh = await db.rsvps.find_one({"_id": rsvp["_id"]}, {"_id": 0})
            u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
            if u and fresh:
                asyncio.create_task(send_rsvp_ticket_email(u, e, fresh))
        except Exception as ex:
            logger.warning(f"Failed to schedule re-send ticket email: {ex}")
        return {"ok": True, "guests": len(new_guests)}

    @api.get("/me/events")
    async def my_events(user: dict = Depends(get_current_user)):
        rsvps = await db.rsvps.find({"user_id": user["id"]}, {"_id": 0}).to_list(500)
        ids = [r["event_id"] for r in rsvps]
        events = await db.events.find({"id": {"$in": ids}}, {"_id": 0}).to_list(500)
        return [event_out(e) for e in events]

    # ---------- Check-in ----------
    @api.get("/checkin/lookup/{token}")
    async def checkin_lookup(token: str):
        """Decode a QR token and return ticket info — used by the /checkin/:token
        landing page to show 'who is this'. Does NOT require auth (the page itself
        enforces admin login before recording the check-in)."""
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
        """Admin scans the QR. Token is decoded → check-in is recorded immediately.
        Idempotent: subsequent scans return the existing check-in row with already_checked_in=true."""
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

    # Expose helpers on the register fn so back-compat shims in server.py
    # can keep importing them.
    register.create_rsvp_and_email_ticket = _create_rsvp_and_email_ticket
    register.send_rsvp_ticket_email = send_rsvp_ticket_email
    register.make_ticket_token = make_ticket_token
    register.decode_ticket_token = decode_ticket_token
    register.make_qr_png_b64 = make_qr_png_b64
