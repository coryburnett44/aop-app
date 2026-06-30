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
import csv
import io
import os
import uuid
from typing import List, Optional

import jwt
import qrcode
from fastapi import Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel

from models import EventRsvpIn, EventPaymentConfirmIn, GuestIn


class AdminRsvpIn(BaseModel):
    user_id: str
    ticket_type: Optional[str] = "general"
    guests: Optional[List[dict]] = None  # accepts strings or {name, ticket_type} dicts; normalized below
    send_email: bool = True


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

    async def _ensure_not_cancelled(event: dict, action_label: str = "RSVPs are closed") -> None:
        """Block actions on cancelled events. If the event is a sub-event whose
        parent has been cancelled, treat the sub-event as cancelled too — this
        protects against any sub-event that wasn't reached by the cascade in
        events.PUT (e.g. seeded after the parent was cancelled, or a stale
        legacy row missing `cancelled_via_parent`)."""
        if event.get("cancelled"):
            raise HTTPException(status_code=400, detail=f"This event has been cancelled — {action_label}.")
        parent_id = event.get("parent_event_id")
        if parent_id:
            parent = await db.events.find_one({"id": parent_id}, {"_id": 0, "cancelled": 1})
            if parent and parent.get("cancelled"):
                raise HTTPException(status_code=400, detail=f"The parent event has been cancelled — {action_label}.")

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
            # Best-effort: also fire a personal copy to each guest that has an
            # email on file. We don't re-send if `guest.email_sent_at` is
            # already populated so guest-list edits remain idempotent.
            for g in guests:
                gemail = (g.get("email") or "").strip()
                if not gemail or g.get("email_sent_at"):
                    continue
                ok = await _send_single_guest_ticket_email(
                    gemail, g.get("name", ""), g.get("ticket_type", "general"),
                    g.get("ticket_id", ""), event, member,
                )
                if ok:
                    g["email_sent_at"] = iso(now_utc())
                    await db.rsvps.update_one(
                        {"id": rsvp.get("id"), "guests.ticket_id": g.get("ticket_id")},
                        {"$set": {"guests.$.email_sent_at": g["email_sent_at"]}},
                    )
            return True
        except Exception as e:
            logger.warning(f"RSVP ticket email failed for {email}: {e}")
            return False

    async def _send_single_guest_ticket_email(guest_email: str, guest_name: str, guest_ticket_type: str, guest_ticket_id: str, event: dict, host_member: dict) -> bool:
        """Email a SINGLE guest their personal ticket. Triggered when an admin
        adds a guest with an explicit email so the guest receives the QR they
        need at the door without going through the member who RSVP'd."""
        if not resend_api_key:
            logger.info(f"Guest ticket email skipped (no RESEND_API_KEY) for {guest_email}")
            return False
        email = (guest_email or "").strip()
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
        gtoken = make_ticket_token(event["id"], guest_ticket_id, "guest", guest_ticket_type or "general", guest_name or "")
        gurl = f"{frontend}/checkin/{gtoken}"
        card = _ticket_card_html(guest_name or "Guest", guest_ticket_type or "general",
                                 make_qr_png_b64(gurl), event_title, when, where)
        host_label = host_member.get("name", "") or "an Alpha Omega Phi member"
        import html as _h
        body = f"""
        <div style="font-family:-apple-system,sans-serif;max-width:640px;margin:0 auto;padding:24px;background:#f7f5f0">
          <h1 style="color:#0A2463;margin:0 0 4px;font-size:26px">You're on the guest list! 🎟️</h1>
          <div style="color:#666;font-size:13px">{_h.escape(host_label)} added you as their guest for <strong>{_h.escape(event_title)}</strong>.</div>
          <div style="background:#fff;border-radius:12px;padding:14px 18px;margin:18px 0;font-size:13px;line-height:1.55">
            <div><strong>When:</strong> {when or 'TBA'}</div>
            <div><strong>Where:</strong> {where or 'TBA'}</div>
          </div>
          {card}
          <p style="font-size:12px;color:#888;margin-top:18px;line-height:1.6">Show this QR code at the door — staff will scan it to check you in. Questions? Reply to this email or reach out to {_h.escape(host_label)}.</p>
        </div>
        """
        try:
            await asyncio.to_thread(resend_sdk.Emails.send, {
                "from": resend_from,
                "to": [email],
                "subject": f"Your guest ticket — {event_title}",
                "html": body,
                "tags": [{"name": "type", "value": "guest_ticket"}, {"name": "event_id", "value": event["id"]}],
            })
            logger.info(f"Guest ticket email sent to {email} for {event_title}")
            return True
        except Exception as e:
            logger.warning(f"Guest ticket email failed for {email}: {e}")
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
        await _ensure_not_cancelled(e, "RSVPs are closed")
        # Admin-only RSVP lockdown (iter 89): admins can RSVP themselves and
        # members through the admin-rsvp endpoint, but members can't self-RSVP
        # once the organizers flip this flag.
        if e.get("rsvps_closed") and user.get("role") != "admin":
            raise HTTPException(
                status_code=403,
                detail="RSVPs for this event are closed. Please contact an admin to be added to the list.",
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

    @api.post("/events/{event_id}/admin-rsvp")
    async def admin_rsvp_event(
        event_id: str,
        body: AdminRsvpIn,
        admin: dict = Depends(get_current_user),
    ):
        """Admin RSVPs a specific member to an event on their behalf, with
        optional guests. Used when a member is unreachable, RSVP'd verbally,
        or sent guest names to leadership via DM.

        - Idempotent: if the member already has an RSVP for the event, returns
          409 with the current state so the admin can decide to delete + recreate.
        - send_email defaults to True so the member gets their digital ticket(s)
          right away, but admins can suppress it for back-fills (e.g. recording
          historic attendance).
        """
        if admin.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only admins can RSVP on behalf of a member.")
        target_user_id = body.user_id
        if not target_user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        target = await db.users.find_one({"id": target_user_id}, {"_id": 0})
        if not target:
            raise HTTPException(status_code=404, detail="Member not found")
        e = await db.events.find_one({"id": event_id}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Event not found")
        await _ensure_not_cancelled(e, "RSVPs are closed")
        has_children = await db.events.find_one({"parent_event_id": event_id})
        if has_children:
            raise HTTPException(status_code=400, detail="This event is an umbrella — RSVP each sub-event individually.")
        existing = await db.rsvps.find_one({"event_id": event_id, "user_id": target_user_id})
        if existing:
            raise HTTPException(status_code=409, detail=f"{target.get('name', 'Member')} already has an RSVP for this event.")

        ticket_type = (body.ticket_type or "general")
        guests_in = body.guests or []
        # Coerce free-form guest dicts into Pydantic-shaped objects for the
        # shared helper. Allow either name strings or full {name, ticket_type} dicts.
        normalized_guests = []
        for g in guests_in:
            if isinstance(g, str):
                normalized_guests.append({"name": g.strip(), "ticket_type": "general"})
            elif isinstance(g, dict) and g.get("name"):
                normalized_guests.append({
                    "name": str(g["name"]).strip(),
                    "ticket_type": (g.get("ticket_type") or "general"),
                })
        send_email = bool(body.send_email)

        # If we don't want an email, monkey-patch the shared helper's email
        # task scheduling for this call only by short-circuiting the helper's
        # try/except via a sentinel. Simplest: build the RSVP doc inline.
        if not send_email:
            rsvp_doc = {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "user_id": target["id"],
                "user_name": target.get("name", ""),
                "ticket_id": str(uuid.uuid4()),
                "ticket_type": ticket_type,
                "guests": [
                    {
                        "name": g["name"],
                        "ticket_type": g.get("ticket_type", "general"),
                        "ticket_id": str(uuid.uuid4()),
                        "checked_in_at": None,
                    }
                    for g in normalized_guests
                ],
                "payment_tx_id": None,
                "created_by_admin": admin["id"],
                "created_by_admin_name": admin.get("name", "Admin"),
                "email_suppressed": True,
                "created_at": iso(now_utc()),
            }
            if e.get("capacity", 0) > 0 and (e.get("rsvp_count", 0) + e.get("guest_count", 0) + 1 + len(rsvp_doc["guests"])) > e["capacity"]:
                raise HTTPException(status_code=400, detail="Event does not have enough seats")
            await db.rsvps.insert_one(rsvp_doc)
            await db.events.update_one(
                {"id": event_id},
                {"$inc": {"rsvp_count": 1, "guest_count": len(rsvp_doc["guests"])}},
            )
        else:
            rsvp_doc = await _create_rsvp_and_email_ticket(
                user=target,
                event=e,
                ticket_type=ticket_type,
                guests_raw=normalized_guests,
            )
            # Stamp the admin attribution on the doc (helps the Reports tab tell
            # admin-created RSVPs apart from self-service ones at audit time).
            await db.rsvps.update_one(
                {"id": rsvp_doc["id"]},
                {"$set": {
                    "created_by_admin": admin["id"],
                    "created_by_admin_name": admin.get("name", "Admin"),
                }},
            )
            rsvp_doc["created_by_admin"] = admin["id"]
            rsvp_doc["created_by_admin_name"] = admin.get("name", "Admin")
        return {
            "rsvped": True,
            "user_id": target["id"],
            "user_name": target.get("name", ""),
            "ticket_id": rsvp_doc["ticket_id"],
            "guests": len(rsvp_doc.get("guests", []) or []),
            "email_sent": send_email,
        }


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
        await _ensure_not_cancelled(e, "payments are closed")
        if e.get("rsvps_closed") and user.get("role") != "admin":
            raise HTTPException(
                status_code=403,
                detail="RSVPs for this event are closed. Please contact an admin to be added to the list.",
            )
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

    class AdminAddGuestsIn(BaseModel):
        guests: List[dict]  # [{name, email?, phone?, ticket_type?}]
        send_email: bool = True

    @api.post("/events/{event_id}/rsvps/{user_id}/guests")
    async def admin_add_guests_to_rsvp(
        event_id: str,
        user_id: str,
        body: AdminAddGuestsIn,
        admin: dict = Depends(require_admin),
    ):
        """Admin adds one or more guests to an EXISTING member's RSVP.

        Use case: the member already RSVP'd (themselves) but admin learned
        offline that they're bringing +1/+2/+3 guests. Each guest gets a
        per-guest `ticket_id` (uuid) so check-in scans work the same as for
        member-added guests. If a guest has an `email`, they receive their
        own QR ticket email; the member also receives a refreshed ticket
        email containing every QR (one per attendee), so they have the full
        set in one place.

        Capacity-checked: returns 400 if adding these guests would exceed the
        event's seat cap. Idempotent in the sense that already-existing
        guests with the same name are NOT deduped — admins can intentionally
        add two guests with the same name (different ticket_ids).
        """
        e = await db.events.find_one({"id": event_id}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Event not found")
        await _ensure_not_cancelled(e, "guest list is locked")
        rsvp = await db.rsvps.find_one({"event_id": event_id, "user_id": user_id})
        if not rsvp:
            raise HTTPException(status_code=404, detail="That member has not RSVP'd for this event yet. Use 'Admin RSVP' first.")
        member = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not member:
            raise HTTPException(status_code=404, detail="Member not found.")

        # Normalize incoming guest payload — accept either pure strings or
        # full dicts; require at least a name.
        new_guests: list = []
        for g in (body.guests or []):
            if isinstance(g, str):
                name = g.strip()
                if name:
                    new_guests.append({"name": name, "email": "", "phone": "", "ticket_type": "general"})
                continue
            name = str((g or {}).get("name", "")).strip()
            if not name:
                continue
            new_guests.append({
                "name": name,
                "email": str((g or {}).get("email", "") or "").strip(),
                "phone": str((g or {}).get("phone", "") or "").strip(),
                "ticket_type": (g or {}).get("ticket_type") or "general",
            })
        if not new_guests:
            raise HTTPException(status_code=400, detail="At least one guest with a name is required.")

        # Capacity guard — only the NEW guests count against capacity (the
        # member is already counted by their original RSVP).
        delta = len(new_guests)
        if e.get("capacity", 0) > 0 and (e.get("rsvp_count", 0) + e.get("guest_count", 0) + delta) > e["capacity"]:
            raise HTTPException(status_code=400, detail="Event does not have enough seats")

        # Build the persistent guest entries with a uuid ticket_id each.
        existing = list(rsvp.get("guests", []) or [])
        for ng in new_guests:
            ng["ticket_id"] = str(uuid.uuid4())
            ng["checked_in_at"] = None
            ng["added_by_admin"] = admin["id"]
            ng["added_by_admin_name"] = admin.get("name", "Admin")
            ng["added_at"] = iso(now_utc())
            existing.append(ng)
        await db.rsvps.update_one({"_id": rsvp["_id"]}, {"$set": {"guests": existing}})
        await db.events.update_one({"id": event_id}, {"$inc": {"guest_count": delta}})

        # Email path: refresh the member's ticket email (which now also fans
        # out individual guest emails for any guest with an `email` field).
        emails_sent_to_guests: list = []
        member_email_sent = False
        if body.send_email:
            fresh = await db.rsvps.find_one({"_id": rsvp["_id"]}, {"_id": 0})
            if fresh:
                member_email_sent = await send_rsvp_ticket_email(member, e, fresh)
                # Reload after send_rsvp_ticket_email's per-guest email_sent_at stamping.
                fresh2 = await db.rsvps.find_one({"_id": rsvp["_id"]}, {"_id": 0})
                if fresh2:
                    new_ticket_ids = {ng["ticket_id"] for ng in new_guests}
                    for g in (fresh2.get("guests") or []):
                        if g.get("ticket_id") in new_ticket_ids and g.get("email_sent_at"):
                            emails_sent_to_guests.append({"name": g.get("name", ""), "email": g.get("email", "")})

        logger.info(
            f"[admin-add-guests] admin={admin.get('email')} added {delta} guest(s) to "
            f"member={user_id} event={event_id}; email_to_member={member_email_sent}; "
            f"emails_to_guests={len(emails_sent_to_guests)}"
        )
        return {
            "ok": True,
            "added": [{"name": g["name"], "email": g.get("email", ""), "ticket_id": g["ticket_id"], "ticket_type": g["ticket_type"]} for g in new_guests],
            "total_guests": len(existing),
            "member_email_sent": member_email_sent,
            "emails_sent_to_guests": emails_sent_to_guests,
        }

    @api.put("/events/{event_id}/rsvp/guests")
    async def update_rsvp_guests(event_id: str, body: EventRsvpIn, user: dict = Depends(get_current_user)):
        """Update the guest list on an existing RSVP without toggling it."""
        rsvp = await db.rsvps.find_one({"event_id": event_id, "user_id": user["id"]})
        if not rsvp:
            raise HTTPException(status_code=404, detail="You have not RSVPed for this event")
        e = await db.events.find_one({"id": event_id}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Event not found")
        await _ensure_not_cancelled(e, "guest list is locked")
        # When RSVPs are closed, members can no longer modify their own guest
        # list (admins still can via /admin-rsvp + /admin/rsvps/{}/guests).
        if e.get("rsvps_closed") and user.get("role") != "admin":
            raise HTTPException(
                status_code=403,
                detail="RSVPs for this event are closed. Please contact an admin to update your guest list.",
            )
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

    @api.delete("/events/{event_id}/rsvps/{user_id}")
    async def admin_un_rsvp_member(
        event_id: str,
        user_id: str,
        admin: dict = Depends(require_admin),
    ):
        """Admin-side un-RSVP. Removes a member's RSVP from an event entirely
        (including all of their guests) plus any check-in record. Decrements
        the event's `rsvp_count` and `guest_count` counters so the displayed
        attendance numbers stay accurate.

        Side effects intentionally NOT performed:
          * Pending or completed payment transactions are NOT touched. If the
            member paid via Zeffy, the admin reconciles the refund separately.
        Returns `{ok, was_present, guests_removed}` so the UI can confirm the
        action even when the row was already gone (idempotent)."""
        rsvp = await db.rsvps.find_one({"event_id": event_id, "user_id": user_id})
        if not rsvp:
            return {"ok": True, "was_present": False, "guests_removed": 0}
        guest_count = len(rsvp.get("guests", []) or [])
        await db.rsvps.delete_one({"_id": rsvp["_id"]})
        await db.events.update_one(
            {"id": event_id},
            {"$inc": {"rsvp_count": -1, "guest_count": -guest_count}},
        )
        # Wipe any check-in artifacts so we don't show ghost attendees.
        ck_res = await db.checkins.delete_many({"event_id": event_id, "user_id": user_id})
        logger.info(
            f"[admin-un-rsvp] admin={admin.get('email')} removed user={user_id} from event={event_id}: "
            f"guests={guest_count}, checkins_removed={ck_res.deleted_count}"
        )
        return {
            "ok": True,
            "was_present": True,
            "guests_removed": guest_count,
            "checkins_removed": ck_res.deleted_count,
        }

    @api.delete("/events/{event_id}/rsvps/{user_id}/guests/{ticket_id}")
    async def admin_remove_guest(
        event_id: str,
        user_id: str,
        ticket_id: str,
        admin: dict = Depends(require_admin),
    ):
        """Admin removes ONE specific guest from a member's RSVP. The guest is
        identified by their per-guest `ticket_id` (a uuid created when the
        RSVP was made) so we can target precisely even when guests share names.
        Decrements `guest_count` on the event by 1. Also removes any guest
        check-in tied to that ticket so reports stay consistent."""
        rsvp = await db.rsvps.find_one({"event_id": event_id, "user_id": user_id})
        if not rsvp:
            raise HTTPException(status_code=404, detail="No RSVP found for that member.")
        guests = list(rsvp.get("guests", []) or [])
        target = next((g for g in guests if g.get("ticket_id") == ticket_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="Guest not found on this RSVP.")
        new_guests = [g for g in guests if g.get("ticket_id") != ticket_id]
        await db.rsvps.update_one({"_id": rsvp["_id"]}, {"$set": {"guests": new_guests}})
        await db.events.update_one({"id": event_id}, {"$inc": {"guest_count": -1}})
        # Remove the guest's check-in too if present (checkin docs for guests
        # carry the same ticket_id stamped at scan-time).
        ck_res = await db.checkins.delete_many({"event_id": event_id, "ticket_id": ticket_id})
        logger.info(
            f"[admin-remove-guest] admin={admin.get('email')} removed guest ticket={ticket_id} "
            f"from user={user_id}/event={event_id}; checkins_removed={ck_res.deleted_count}"
        )
        return {
            "ok": True,
            "removed_guest": {"name": target.get("name", ""), "ticket_id": ticket_id},
            "remaining_guests": len(new_guests),
            "checkins_removed": ck_res.deleted_count,
        }

    @api.get("/me/events")
    async def my_events(user: dict = Depends(get_current_user)):
        rsvps = await db.rsvps.find({"user_id": user["id"]}, {"_id": 0}).to_list(500)
        ids = [r["event_id"] for r in rsvps]
        events = await db.events.find({"id": {"$in": ids}}, {"_id": 0}).to_list(500)
        return [event_out(e) for e in events]

    # ---------- Check-in ----------

    # Expose helpers on the register fn so back-compat shims in server.py
    # can keep importing them, and so the sub-modules (rsvps_csv, checkin)
    # can call into the shared logic.
    register.create_rsvp_and_email_ticket = _create_rsvp_and_email_ticket
    register.send_rsvp_ticket_email = send_rsvp_ticket_email
    register.make_ticket_token = make_ticket_token
    register.decode_ticket_token = decode_ticket_token
    register.make_qr_png_b64 = make_qr_png_b64
    register.ensure_not_cancelled = _ensure_not_cancelled
