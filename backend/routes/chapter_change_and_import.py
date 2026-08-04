"""Chapter-change approval flow + CSV import of past event attendance.

Two admin surfaces bundled here because they share the same authorisation
model (chapter-admins can view, only full-access admins can commit) and
because they both flow into existing user/checkin collections.

## Chapter-change approval
  POST   /api/me/chapter-change-request          member submits
  GET    /api/me/chapter-change-request          member sees own pending
  GET    /api/admin/chapter-change-requests      chapter-admins & full-access
  POST   /api/admin/chapter-change-requests/{id}/approve   full-access only
  POST   /api/admin/chapter-change-requests/{id}/deny      full-access only

## Historical event attendance
  POST   /api/admin/checkins/import-csv          full-access only
    Body: multipart/form-data with `file` (text/csv or text/plain).
    Columns accepted (case-insensitive): email OR name, event_name, date.
    Members are matched by email first, then by exact name fallback.
    Returns {inserted: N, skipped: N, errors: [...]}
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import Depends, HTTPException, UploadFile, File
from pydantic import BaseModel


# =========================================================================
# Chapter-change models (module-scope so FastAPI resolves them correctly).
# =========================================================================
class ChapterChangeRequestIn(BaseModel):
    target_chapter_id: str
    reason: Optional[str] = None


# =========================================================================
# CSV import helpers
# =========================================================================
def _norm_header(h: str) -> str:
    return (h or "").strip().lower().replace("-", "_").replace(" ", "_")


def _find_col(headers: List[str], *aliases: str) -> Optional[str]:
    """Locate the first header that matches any alias (case-insensitive)."""
    normed = {_norm_header(h): h for h in headers}
    for alias in aliases:
        key = _norm_header(alias)
        if key in normed:
            return normed[key]
    return None


def _parse_date(raw: str) -> Optional[datetime]:
    """Accept ISO, US (MM/DD/YYYY), or long formats. Returns UTC datetime."""
    if not raw:
        return None
    s = str(raw).strip()
    fmts = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ]
    for f in fmts:
        try:
            return datetime.strptime(s, f).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Last-resort: try fromisoformat which handles many variants.
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def register(
    api,
    *,
    db,
    iso,
    now_utc,
    logger,
    admin_tab_dep,
    get_current_user,
    require_full_admin,
    send_bulk_email=None,
    send_push_best_effort=None,
    frontend_url: str = "",
):
    # ================================================================
    # CHAPTER-CHANGE APPROVAL FLOW
    # ================================================================
    def _req_out(r: dict) -> dict:
        return {
            "id": r["id"],
            "user_id": r.get("user_id"),
            "user_name": r.get("user_name", ""),
            "user_email": r.get("user_email", ""),
            "user_avatar_url": r.get("user_avatar_url", ""),
            "current_chapter_id": r.get("current_chapter_id"),
            "current_chapter_name": r.get("current_chapter_name", ""),
            "target_chapter_id": r.get("target_chapter_id"),
            "target_chapter_name": r.get("target_chapter_name", ""),
            "reason": r.get("reason", ""),
            "status": r.get("status", "pending"),  # pending | approved | denied
            "created_at": r.get("created_at"),
            "decided_at": r.get("decided_at"),
            "decided_by_name": r.get("decided_by_name", ""),
            "decision_note": r.get("decision_note", ""),
        }

    async def _snapshot_chapter(cid: Optional[str]) -> str:
        if not cid:
            return ""
        c = await db.chapters.find_one({"id": cid}, {"_id": 0, "name": 1})
        return (c or {}).get("name", "")

    @api.post("/me/chapter-change-request")
    async def submit_chapter_change(body: ChapterChangeRequestIn, user: dict = Depends(get_current_user)):
        if not body.target_chapter_id:
            raise HTTPException(status_code=400, detail="target_chapter_id is required.")
        target = await db.chapters.find_one({"id": body.target_chapter_id}, {"_id": 0, "name": 1, "id": 1})
        if not target:
            raise HTTPException(status_code=404, detail="Target chapter not found.")
        if user.get("chapter_id") == body.target_chapter_id:
            raise HTTPException(status_code=400, detail="You are already assigned to that chapter.")
        # Reject if a pending request already exists for this member.
        existing = await db.chapter_change_requests.find_one({"user_id": user["id"], "status": "pending"})
        if existing:
            raise HTTPException(status_code=409, detail="You already have a pending chapter change request.")

        current_name = await _snapshot_chapter(user.get("chapter_id"))
        doc = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "user_name": user.get("name", ""),
            "user_email": user.get("email", ""),
            "user_avatar_url": user.get("avatar_url", ""),
            "current_chapter_id": user.get("chapter_id") or None,
            "current_chapter_name": current_name,
            "target_chapter_id": body.target_chapter_id,
            "target_chapter_name": target.get("name", ""),
            "reason": (body.reason or "").strip(),
            "status": "pending",
            "created_at": iso(now_utc()),
        }
        await db.chapter_change_requests.insert_one(doc)

        # Notify chapter admins + full-access admins by email (best-effort).
        if send_bulk_email:
            try:
                admins = await db.users.find(
                    {"role": "admin", "$or": [
                        {"admin_role": "full"},
                        {"admin_role": "governor_manager", "chapter_id": {"$in": [user.get("chapter_id"), body.target_chapter_id]}},
                    ]},
                    {"_id": 0, "id": 1, "email": 1, "name": 1, "admin_role": 1, "chapter_id": 1},
                ).to_list(100)
                subject = f"Chapter change request from {doc['user_name']}"
                body_html = (
                    f"<p><strong>{doc['user_name']}</strong> ({doc['user_email']}) has requested to move "
                    f"from <strong>{current_name or 'Unassigned'}</strong> to <strong>{target.get('name','')}</strong>.</p>"
                    + (f"<blockquote style='border-left:3px solid #ccc;padding-left:12px;color:#444;'>{doc['reason']}</blockquote>" if doc["reason"] else "")
                    + f"<p>Review it in the Admin panel &gt; Members tab.</p>"
                )
                for a in admins:
                    await send_bulk_email(
                        recipient_id=a["id"], to_email=a["email"], subject=subject,
                        html_body=body_html, tags=[{"name": "type", "value": "chapter_change_request"}],
                    )
            except Exception as e:
                logger.warning(f"chapter-change notify failed: {e}")

        return _req_out(doc)

    @api.get("/me/chapter-change-request")
    async def my_chapter_change_request(user: dict = Depends(get_current_user)):
        """Return the member's own current (pending or most-recent) request."""
        doc = await db.chapter_change_requests.find_one(
            {"user_id": user["id"]},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        return _req_out(doc) if doc else None

    @api.delete("/me/chapter-change-request")
    async def cancel_my_chapter_change_request(user: dict = Depends(get_current_user)):
        r = await db.chapter_change_requests.delete_one({"user_id": user["id"], "status": "pending"})
        return {"cancelled": r.deleted_count}

    @api.get("/admin/chapter-change-requests")
    async def list_chapter_change_requests(status: Optional[str] = "pending", user: dict = Depends(admin_tab_dep("members"))):
        """List chapter-change requests. Visible to any admin with `members`
        tab access (so chapter-admins see them) — but only full-access admins
        can approve/deny (enforced on those endpoints). Governor managers
        only see requests where the source OR target chapter matches their
        assigned chapter."""
        query: dict = {}
        if status and status != "all":
            query["status"] = status
        # Governor-manager scoping: filter to requests touching their chapter.
        if user.get("admin_role") == "governor_manager" and user.get("chapter_id"):
            cid = user["chapter_id"]
            query["$or"] = [{"current_chapter_id": cid}, {"target_chapter_id": cid}]
        cursor = db.chapter_change_requests.find(query, {"_id": 0}).sort("created_at", -1)
        rows = await cursor.to_list(500)
        return [_req_out(r) for r in rows]

    async def _decide(req_id: str, admin: dict, approve: bool, note: str = ""):
        r = await db.chapter_change_requests.find_one({"id": req_id}, {"_id": 0})
        if not r:
            raise HTTPException(status_code=404, detail="Request not found.")
        if r.get("status") != "pending":
            raise HTTPException(status_code=409, detail=f"Request is already {r['status']}.")

        decision = "approved" if approve else "denied"
        updates = {
            "status": decision,
            "decided_at": iso(now_utc()),
            "decided_by": admin["id"],
            "decided_by_name": admin.get("name", ""),
            "decision_note": (note or "").strip(),
        }

        if approve:
            # Move the member.
            await db.users.update_one(
                {"id": r["user_id"]},
                {"$set": {"chapter_id": r["target_chapter_id"]}},
            )
            # Best-effort: append to assignment_history for audit trail.
            try:
                await db.users.update_one(
                    {"id": r["user_id"]},
                    {"$push": {"assignment_history": {
                        "at": iso(now_utc()),
                        "action": "chapter_change_approved",
                        "from_chapter_id": r.get("current_chapter_id"),
                        "to_chapter_id": r.get("target_chapter_id"),
                        "by": admin.get("name", ""),
                    }}},
                )
            except Exception:
                pass

        await db.chapter_change_requests.update_one({"id": req_id}, {"$set": updates})
        r.update(updates)

        # Notify the member + governor-managers of BOTH chapters + full-access admins.
        try:
            member_user = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "email": 1, "id": 1, "name": 1})
            audience_ids: set = set()
            audience_emails: dict = {}
            if member_user:
                audience_ids.add(member_user["id"])
                audience_emails[member_user["id"]] = (member_user["email"], member_user.get("name", ""))

            admin_query = {"role": "admin", "$or": [
                {"admin_role": "full"},
                {"admin_role": "governor_manager", "chapter_id": {"$in": [r.get("current_chapter_id"), r.get("target_chapter_id")]}},
            ]}
            async for a in db.users.find(admin_query, {"_id": 0, "id": 1, "email": 1, "name": 1}):
                audience_ids.add(a["id"])
                audience_emails[a["id"]] = (a["email"], a.get("name", ""))

            if send_bulk_email:
                verb = "APPROVED" if approve else "DENIED"
                subject = f"Chapter change {verb}: {r['user_name']}"
                body_html = (
                    f"<p>The chapter change request from <strong>{r['user_name']}</strong> has been "
                    f"<strong>{verb}</strong> by {admin.get('name','')}.</p>"
                    f"<p>From: <strong>{r.get('current_chapter_name','Unassigned')}</strong><br/>"
                    f"To: <strong>{r.get('target_chapter_name','')}</strong></p>"
                    + (f"<blockquote>{updates['decision_note']}</blockquote>" if updates["decision_note"] else "")
                )
                for uid, (email, _name) in audience_emails.items():
                    if not email:
                        continue
                    await send_bulk_email(
                        recipient_id=uid, to_email=email, subject=subject,
                        html_body=body_html, tags=[{"name": "type", "value": f"chapter_change_{decision}"}],
                    )

            if send_push_best_effort and audience_ids:
                await send_push_best_effort(
                    user_ids=list(audience_ids),
                    title=f"Chapter change {decision}",
                    message=f"{r['user_name']}: {r.get('current_chapter_name','?')} → {r.get('target_chapter_name','?')}",
                    url=(frontend_url or "") + "/admin",
                )
        except Exception as e:
            logger.warning(f"chapter-change decision notify failed: {e}")

        return _req_out(r)

    @api.post("/admin/chapter-change-requests/{req_id}/approve")
    async def approve_chapter_change(req_id: str, admin: dict = Depends(require_full_admin)):
        return await _decide(req_id, admin, approve=True)

    @api.post("/admin/chapter-change-requests/{req_id}/deny")
    async def deny_chapter_change(req_id: str, note: str = "", admin: dict = Depends(require_full_admin)):
        return await _decide(req_id, admin, approve=False, note=note)

    # ================================================================
    # CSV IMPORT OF PAST EVENT ATTENDANCE
    # ================================================================
    # Iter 152 flow: upload is a PREVIEW (persists an `import_batches`
    # doc but writes NOTHING to checkins/events yet). Admins review the
    # matched + skipped rows, then click Approve to commit — mirroring
    # the volunteer-hours & causes approval UX.
    async def _parse_csv_batch(file: UploadFile, admin: dict) -> dict:
        content_type = (file.content_type or "").lower()
        if "csv" not in content_type and "text" not in content_type and not (file.filename or "").lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Upload a .csv file.")
        raw = await file.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        email_col = _find_col(headers, "email", "email_address", "member_email")
        name_col = _find_col(headers, "name", "member_name", "full_name")
        event_col = _find_col(headers, "event_name", "event", "event_title", "title")
        date_col = _find_col(headers, "date", "event_date", "attended_on", "attended_at")
        if not event_col or not date_col:
            raise HTTPException(status_code=400, detail=f"CSV must include event_name and date columns. Got: {headers}")
        if not email_col and not name_col:
            raise HTTPException(status_code=400, detail=f"CSV must include email or name column. Got: {headers}")

        # Preload members index for fast lookups.
        users_by_email: dict = {}
        users_by_name: dict = {}
        async for u in db.users.find({}, {"_id": 0, "id": 1, "email": 1, "name": 1}):
            if u.get("email"):
                users_by_email[u["email"].lower().strip()] = u
            if u.get("name"):
                users_by_name[u["name"].lower().strip()] = u

        # Preload existing (event_name+date) → event_id map so the
        # preview shows admins whether the row will create a synthetic
        # event or attach to an existing one.
        events_by_key: dict = {}
        async for e in db.events.find({}, {"_id": 0, "id": 1, "title": 1, "start_at": 1}):
            key = ((e.get("title") or "").strip().lower(), (e.get("start_at") or "")[:10])
            if key[0] and key[1]:
                events_by_key[key] = e["id"]

        existing_checkins: set = set()
        async for c in db.checkins.find({}, {"_id": 0, "event_id": 1, "user_id": 1}):
            existing_checkins.add((c.get("event_id"), c.get("user_id")))

        rows_out: list = []
        counters = {"total": 0, "insert": 0, "skip": 0, "duplicate": 0}
        for i, row in enumerate(reader, start=2):  # start=2 to account for header row
            counters["total"] += 1
            email = ((email_col and row.get(email_col)) or "").strip().lower()
            name = ((name_col and row.get(name_col)) or "").strip()
            event_name = ((row.get(event_col) or "")).strip()
            date_raw = ((row.get(date_col) or "")).strip()

            base = {
                "row": i,
                "email": email,
                "name": name,
                "event_name": event_name,
                "date_raw": date_raw,
                "date_parsed": None,
                "matched_user_id": None,
                "matched_user_name": None,
                "matched_user_email": None,
                "event_id": None,
                "event_is_new": False,
                "action": "skip",
                "skip_reason": "",
            }

            if not event_name or not date_raw:
                base["skip_reason"] = "Missing event_name or date."
                counters["skip"] += 1
                rows_out.append(base); continue
            dt = _parse_date(date_raw)
            if not dt:
                base["skip_reason"] = f"Unparseable date: {date_raw!r}"
                counters["skip"] += 1
                rows_out.append(base); continue
            base["date_parsed"] = dt.date().isoformat()

            u = None
            if email and email in users_by_email:
                u = users_by_email[email]
            elif name and name.lower() in users_by_name:
                u = users_by_name[name.lower()]
            if not u:
                lookup = " / ".join([p for p in [f"email={email!r}" if email else "", f"name={name!r}" if name else ""] if p]) or "(no email or name)"
                base["skip_reason"] = f"No matching member for {lookup}"
                counters["skip"] += 1
                rows_out.append(base); continue

            base["matched_user_id"] = u["id"]
            base["matched_user_name"] = u.get("name", "")
            base["matched_user_email"] = u.get("email", "")

            key = (event_name.lower(), dt.date().isoformat())
            event_id = events_by_key.get(key)
            base["event_id"] = event_id
            base["event_is_new"] = event_id is None

            if event_id and (event_id, u["id"]) in existing_checkins:
                base["action"] = "duplicate"
                base["skip_reason"] = "Member is already checked-in to this event."
                counters["duplicate"] += 1
                rows_out.append(base); continue

            base["action"] = "insert"
            counters["insert"] += 1
            rows_out.append(base)

        batch_doc = {
            "id": str(uuid.uuid4()),
            "created_at": iso(now_utc()),
            "created_by": admin["id"],
            "created_by_name": admin.get("name", ""),
            "filename": file.filename or "attendance.csv",
            "status": "pending",
            "csv_headers": headers,
            "rows": rows_out,
            "summary": counters,
        }
        await db.checkin_import_batches.insert_one(batch_doc)
        # `insert_one` mutates the dict to include `_id` (an ObjectId that
        # isn't JSON-serialisable) — strip it before returning.
        batch_doc.pop("_id", None)
        # Compat: also return legacy `inserted/skipped/errors` fields so an
        # older UI reading this endpoint continues to render a summary until
        # the two-phase UI ships.
        return {
            **batch_doc,
            "batch_id": batch_doc["id"],
            "inserted": 0,
            "skipped": counters["skip"] + counters["duplicate"],
            "errors": [
                {"row": r["row"], "reason": r["skip_reason"]}
                for r in rows_out if r["action"] != "insert"
            ][:200],
        }

    def _batch_out(doc: dict) -> dict:
        # Strip the raw Mongo _id if present but preserve everything else.
        d = {k: v for k, v in doc.items() if k != "_id"}
        d["batch_id"] = d.get("id")
        return d

    @api.post("/admin/checkins/import-csv")
    async def preview_import_checkins_csv(file: UploadFile = File(...), admin: dict = Depends(require_full_admin)):
        """PREVIEW-only: parse the CSV, match members, flag skipped rows +
        reasons, and persist a `checkin_import_batches` row. Nothing is
        written to `checkins`/`events` until the admin explicitly approves
        the batch via `/admin/checkins/import-batches/{id}/approve`."""
        return await _parse_csv_batch(file, admin)

    @api.get("/admin/checkins/import-batches")
    async def list_import_batches(status: Optional[str] = "pending", _: dict = Depends(require_full_admin)):
        q: dict = {}
        if status and status != "all":
            q["status"] = status
        cursor = db.checkin_import_batches.find(q, {"_id": 0}).sort("created_at", -1).limit(50)
        rows = await cursor.to_list(50)
        return [_batch_out(r) for r in rows]

    @api.get("/admin/checkins/import-batches/{batch_id}")
    async def get_import_batch(batch_id: str, _: dict = Depends(require_full_admin)):
        doc = await db.checkin_import_batches.find_one({"id": batch_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Import batch not found.")
        return _batch_out(doc)

    @api.delete("/admin/checkins/import-batches/{batch_id}")
    async def discard_import_batch(batch_id: str, _: dict = Depends(require_full_admin)):
        res = await db.checkin_import_batches.delete_one({"id": batch_id, "status": "pending"})
        if not res.deleted_count:
            raise HTTPException(status_code=404, detail="Pending batch not found (already approved or discarded).")
        return {"discarded": True}

    @api.post("/admin/checkins/import-batches/{batch_id}/approve")
    async def approve_import_batch(batch_id: str, admin: dict = Depends(require_full_admin)):
        """Commit every `action=='insert'` row in the batch. Skipped and
        duplicate rows are left untouched. Idempotent: approving an already-
        approved batch is rejected so we don't double-write."""
        doc = await db.checkin_import_batches.find_one({"id": batch_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Import batch not found.")
        if doc.get("status") != "pending":
            raise HTTPException(status_code=409, detail=f"Batch is already {doc.get('status')}.")

        # Re-check duplicate state at approval time so we don't clobber
        # checkins added between preview & approval.
        existing_checkins: set = set()
        async for c in db.checkins.find({}, {"_id": 0, "event_id": 1, "user_id": 1}):
            existing_checkins.add((c.get("event_id"), c.get("user_id")))
        events_by_key: dict = {}
        async for e in db.events.find({}, {"_id": 0, "id": 1, "title": 1, "start_at": 1}):
            key = ((e.get("title") or "").strip().lower(), (e.get("start_at") or "")[:10])
            if key[0] and key[1]:
                events_by_key[key] = e["id"]

        inserted, duplicate_now = 0, 0
        for r in doc.get("rows") or []:
            if r.get("action") != "insert":
                continue
            uid = r.get("matched_user_id")
            date_iso = r.get("date_parsed")
            event_name = r.get("event_name") or ""
            if not uid or not date_iso or not event_name:
                continue
            key = (event_name.lower(), date_iso)
            event_id = events_by_key.get(key) or r.get("event_id")
            if not event_id:
                event_id = str(uuid.uuid4())
                await db.events.insert_one({
                    "id": event_id,
                    "title": event_name,
                    "start_at": f"{date_iso}T00:00:00+00:00",
                    "end_at": f"{date_iso}T00:00:00+00:00",
                    "location": "",
                    "description": "Imported from historical attendance CSV.",
                    "is_public": False,
                    "created_at": iso(now_utc()),
                    "created_by": admin["id"],
                    "imported": True,
                })
                events_by_key[key] = event_id
            if (event_id, uid) in existing_checkins:
                duplicate_now += 1
                continue
            await db.checkins.insert_one({
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "user_id": uid,
                "user_name": r.get("matched_user_name") or "",
                "checked_in_at": f"{date_iso}T00:00:00+00:00",
                "source": "csv_import",
                "imported_at": iso(now_utc()),
                "batch_id": batch_id,
            })
            existing_checkins.add((event_id, uid))
            inserted += 1

        outcome = {
            "status": "approved",
            "approved_at": iso(now_utc()),
            "approved_by": admin["id"],
            "approved_by_name": admin.get("name", ""),
            "outcome": {"inserted": inserted, "duplicate_at_approval": duplicate_now},
        }
        await db.checkin_import_batches.update_one({"id": batch_id}, {"$set": outcome})
        doc.update(outcome)
        return _batch_out(doc)
