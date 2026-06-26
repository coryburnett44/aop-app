"""Bulk CSV RSVP import routes.

Extracted from routes/rsvps.py to keep the parent file under 1k lines. The
CSV-bulk flow re-uses the shared `_create_rsvp_and_email_ticket` and
`_ensure_not_cancelled` helpers that live in rsvps.py — they're injected here
as kwargs.

Endpoints:
  GET  /api/events/{event_id}/admin-rsvp/csv/template — sample CSV download
  POST /api/events/{event_id}/admin-rsvp/csv          — bulk import (supports dry_run)
"""
import csv
import io
import uuid

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import Response


def register(api, *, db, get_current_user, iso, now_utc, ensure_not_cancelled, create_rsvp_and_email_ticket):
    @api.get("/events/{event_id}/admin-rsvp/csv/template")
    async def admin_rsvp_csv_template(event_id: str, admin: dict = Depends(get_current_user)):
        """Download a small starter CSV showing the columns the bulk RSVP
        importer expects. Includes one illustrative row that the admin should
        delete before uploading."""
        if admin.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admins only")
        headers = ["member_email", "ticket_type", "guests", "guest_ticket_types"]
        sample_with_guests = [
            "member@clubhaven.app", "general",
            "Alex Plus-one; Pat Friend",
            "general; vip",
        ]
        sample_solo = ["maya.patel@clubhaven.app", "vip", "", ""]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        writer.writerow(sample_with_guests)
        writer.writerow(sample_solo)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="aop-rsvp-template.csv"'},
        )

    @api.post("/events/{event_id}/admin-rsvp/csv")
    async def admin_rsvp_csv(
        event_id: str,
        file: UploadFile = File(...),
        dry_run: bool = False,
        send_email: bool = True,
        admin: dict = Depends(get_current_user),
    ):
        """Bulk-import RSVPs (with optional guest names) from a CSV file.
        Required column: member_email. Optional: ticket_type, guests (a
        semicolon-separated list of guest names), guest_ticket_types (a
        parallel semicolon-separated list — defaults to 'general' for each).

        Mirrors the hours CSV pattern: when ?dry_run=true is passed nothing is
        written, the response includes a per-row `preview` array, and confirm
        is a second POST without dry_run. `send_email` is a single global flag
        applied to every row in this batch.

        Rejects when the event is cancelled, paid, external, or is an umbrella
        parent. Members who already have an RSVP are surfaced as errors (the
        same way a duplicate single-row RSVP returns 409 to the admin UI).
        """
        if admin.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admins only")
        e = await db.events.find_one({"id": event_id}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Event not found")
        await ensure_not_cancelled(e, "RSVPs are closed")
        if e.get("is_paid"):
            raise HTTPException(status_code=400, detail="Paid events use the payment-confirm flow, not bulk RSVPs.")
        has_children = await db.events.find_one({"parent_event_id": event_id})
        if has_children:
            raise HTTPException(status_code=400, detail="This event is an umbrella — bulk-RSVP each sub-event individually.")

        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Upload a .csv file")
        raw = await file.read()
        if len(raw) > 1024 * 1024:
            raise HTTPException(status_code=400, detail="CSV too large (max 1 MB)")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw.decode("latin-1")
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Could not decode CSV: {exc}")

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV has no header row")
        normalized = {(h or "").strip().lower(): h for h in reader.fieldnames}
        if "member_email" not in normalized and "email" not in normalized:
            raise HTTPException(status_code=400, detail="CSV must include a 'member_email' column")

        email_key = normalized.get("member_email") or normalized.get("email")
        rows = list(reader)
        if not rows:
            raise HTTPException(status_code=400, detail="CSV has no data rows")
        if len(rows) > 500:
            raise HTTPException(status_code=400, detail="CSV too large (max 500 rows)")

        emails = sorted({(r.get(email_key) or "").strip().lower() for r in rows if (r.get(email_key) or "").strip()})
        users_by_email = {}
        if emails:
            async for u in db.users.find(
                {"email": {"$in": emails}},
                {"_id": 0, "id": 1, "name": 1, "email": 1, "avatar_url": 1},
            ):
                users_by_email[u["email"].lower()] = u
        already = set()
        if users_by_email:
            uids = list({u["id"] for u in users_by_email.values()})
            async for r in db.rsvps.find({"event_id": event_id, "user_id": {"$in": uids}}, {"_id": 0, "user_id": 1}):
                already.add(r["user_id"])

        capacity = int(e.get("capacity") or 0)
        seats_used = int(e.get("rsvp_count") or 0) + int(e.get("guest_count") or 0)

        def opt(row, key_lower):
            real = normalized.get(key_lower)
            if not real:
                return ""
            return (row.get(real) or "").strip()

        preview: list[dict] = []
        errors: list[dict] = []
        ready_docs: list[dict] = []
        running_seats = seats_used

        for idx, row in enumerate(rows, start=2):
            email_raw = (row.get(email_key) or "").strip()
            email = email_raw.lower()
            ticket_type = (opt(row, "ticket_type") or "general").lower()
            guests_csv = opt(row, "guests")
            guest_types_csv = opt(row, "guest_ticket_types")

            def fail(message: str, target_name: str = ""):
                errors.append({"row": idx, "message": message})
                preview.append({
                    "row": idx, "status": "error", "email": email_raw,
                    "member_name": target_name, "ticket_type": ticket_type,
                    "guest_names": [g.strip() for g in guests_csv.split(";") if g.strip()],
                    "message": message,
                })

            if not email:
                fail("Missing member_email")
                continue
            target = users_by_email.get(email)
            if not target:
                fail(f"No member with email {email_raw}")
                continue
            if target["id"] in already:
                fail(f"{target.get('name', email_raw)} already has an RSVP for this event")
                continue
            guest_names = [g.strip() for g in guests_csv.split(";") if g.strip()] if guests_csv else []
            guest_types = [t.strip() for t in guest_types_csv.split(";") if t.strip()] if guest_types_csv else []
            normalized_guests = []
            for i, name in enumerate(guest_names):
                gtt = (guest_types[i] if i < len(guest_types) else "") or "general"
                normalized_guests.append({"name": name, "ticket_type": gtt})
            seats_needed = 1 + len(normalized_guests)
            if capacity > 0 and running_seats + seats_needed > capacity:
                fail(f"Not enough seats — needs {seats_needed}, only {max(capacity - running_seats, 0)} left")
                continue
            if target["id"] in {d["target"]["id"] for d in ready_docs}:
                fail(f"{target.get('name', email_raw)} appears more than once in the file")
                continue
            running_seats += seats_needed
            ready_docs.append({"target": target, "ticket_type": ticket_type, "guests": normalized_guests})
            preview.append({
                "row": idx, "status": "ready", "email": target.get("email", email_raw),
                "member_name": target.get("name", ""),
                "avatar_url": target.get("avatar_url"),
                "ticket_type": ticket_type,
                "guest_names": [g["name"] for g in normalized_guests],
                "seats": seats_needed,
            })

        created_rsvps: list[dict] = []
        if not dry_run and ready_docs:
            for d in ready_docs:
                target = d["target"]
                if send_email:
                    rsvp_doc = await create_rsvp_and_email_ticket(
                        user=target,
                        event=e,
                        ticket_type=d["ticket_type"],
                        guests_raw=d["guests"],
                    )
                    await db.rsvps.update_one(
                        {"id": rsvp_doc["id"]},
                        {"$set": {"created_by_admin": admin["id"], "created_by_admin_name": admin.get("name", "Admin"), "imported_from_csv": file.filename}},
                    )
                else:
                    rsvp_doc = {
                        "id": str(uuid.uuid4()),
                        "event_id": event_id,
                        "user_id": target["id"],
                        "user_name": target.get("name", ""),
                        "ticket_id": str(uuid.uuid4()),
                        "ticket_type": d["ticket_type"],
                        "guests": [
                            {
                                "name": g["name"],
                                "ticket_type": g.get("ticket_type", "general"),
                                "ticket_id": str(uuid.uuid4()),
                                "checked_in_at": None,
                            }
                            for g in d["guests"]
                        ],
                        "payment_tx_id": None,
                        "created_by_admin": admin["id"],
                        "created_by_admin_name": admin.get("name", "Admin"),
                        "email_suppressed": True,
                        "imported_from_csv": file.filename,
                        "created_at": iso(now_utc()),
                    }
                    await db.rsvps.insert_one(rsvp_doc)
                    await db.events.update_one(
                        {"id": event_id},
                        {"$inc": {"rsvp_count": 1, "guest_count": len(rsvp_doc["guests"])}},
                    )
                created_rsvps.append({"user_id": target["id"], "guests": len(rsvp_doc.get("guests") or [])})

        return {
            "dry_run": dry_run,
            "send_email": send_email,
            "created": 0 if dry_run else len(created_rsvps),
            "ready": len(ready_docs),
            "failed": len(errors),
            "total": len(rows),
            "errors": errors[:50],
            "errors_truncated": len(errors) > 50,
            "preview": preview[:200],
            "preview_truncated": len(preview) > 200,
        }
