"""Volunteer-hours routes.

Owns:
  - POST   /hours                      (log own hours)
  - GET    /hours                      (admin queue, chapter-scoped for Governor)
  - PUT    /hours/{id}/review          (admin approves / rejects / adjusts)
  - DELETE /hours/{id}                 (member or admin)
  - GET    /me/hours                   (filterable by year/quarter/month/status)
  - GET    /me/hours/summary           (year rollup: by_month / by_quarter)
  - POST   /hours/admin                (admin logs hours for ONE member, auto-approved)
  - POST   /hours/admin/bulk           (admin logs SAME hours for many members)
  - POST   /hours/admin/csv            (admin uploads CSV → bulk log + auto-approve)
  - GET    /hours/admin/csv/template   (download a CSV template w/ headers + sample row)

The `hours_out` serializer, `_period_to_range` helper, and chapter-scoping
helpers remain in server.py and are injected.
"""
import csv
import io
from datetime import datetime as _dt
from typing import Optional
import uuid

from fastapi import Depends, HTTPException, UploadFile, File
from fastapi.responses import Response

from models import HoursLogIn, HoursReviewIn, AdminHoursLogIn, AdminHoursBulkLogIn, AdminHoursEditIn


# Formats we try when parsing user-supplied CSV dates. Order matters — try the
# unambiguous ISO forms first, then common US/Excel layouts. If a value can be
# parsed by `_dt.fromisoformat` (handles ISO datetimes with time + offset) we
# still get a usable date regardless.
_DATE_FORMATS = (
    "%Y-%m-%d",          # 2026-06-15
    "%Y/%m/%d",          # 2026/06/15
    "%m/%d/%Y",          # 06/15/2026, 6/15/2026  ← Excel default
    "%m-%d-%Y",          # 06-15-2026
    "%m/%d/%y",          # 6/15/26
    "%m-%d-%y",          # 6-15-26
    "%d-%b-%Y",          # 15-Jun-2026
    "%d-%b-%y",          # 15-Jun-26
    "%d %b %Y",          # 15 Jun 2026
    "%d %B %Y",          # 15 June 2026
    "%b %d, %Y",         # Jun 15, 2026
    "%B %d, %Y",         # June 15, 2026
)
DATE_FORMATS_FOR_HUMANS = "YYYY-MM-DD, MM/DD/YYYY, M/D/YY, 15-Jun-2026"


def _parse_csv_date(raw: str) -> _dt:
    """Best-effort date parser for CSV imports. Tries ISO + common US/Excel
    layouts. Raises ValueError with the accepted-formats list when nothing
    matches so the error message bubbled back to the admin is actionable."""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("date is empty")
    # ISO datetime first — handles "2026-06-15T10:00:00Z" or with offset
    try:
        return _dt.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return _dt.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid date '{raw}'. Accepted formats: {DATE_FORMATS_FOR_HUMANS}")


def register(
    api,
    *,
    db,
    admin_tab_dep,
    require_admin,
    get_current_user,
    hours_out,
    is_chapter_scoped,
    chapter_scope_user_ids,
    period_to_range,
    iso,
    now_utc,
):

    @api.post("/hours")
    async def log_hours(body: HoursLogIn, user: dict = Depends(get_current_user)):
        activity_text = body.activity or body.description or ""
        doc = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "user_name": user.get("name", ""),
            "hours": body.hours,
            "description": activity_text,
            "activity": activity_text,
            "event_type": body.event_type,
            "agency_name": body.agency_name,
            "host_name": body.host_name,
            "host_email": body.host_email,
            "host_phone": body.host_phone,
            "date": iso(body.date),
            "event_id": body.event_id,
            "status": "pending",
            "created_at": iso(now_utc()),
        }
        await db.volunteer_hours.insert_one(doc)
        return hours_out(doc)

    @api.post("/hours/admin")
    async def admin_log_hours(body: AdminHoursLogIn, admin: dict = Depends(admin_tab_dep("hours"))):
        """Admin logs hours on behalf of a member. Auto-approved (the admin's
        act of logging IS the approval). Only `user_id`, `hours`, and `date`
        are functionally required — everything else is optional."""
        target = await db.users.find_one({"id": body.user_id}, {"_id": 0, "id": 1, "name": 1, "chapter_id": 1})
        if not target:
            raise HTTPException(status_code=404, detail="Member not found")
        # Chapter-scoped admins (e.g. Governor) can only log for members in their chapter.
        if is_chapter_scoped(admin):
            allowed_ids = await chapter_scope_user_ids(admin)
            if body.user_id not in (allowed_ids or []):
                raise HTTPException(status_code=403, detail="You can only log hours for members in your chapter.")
        activity_text = body.activity or body.description or "Logged by admin"
        doc = {
            "id": str(uuid.uuid4()),
            "user_id": target["id"],
            "user_name": target.get("name", ""),
            "hours": body.hours,
            "description": activity_text,
            "activity": activity_text,
            "event_type": body.event_type,
            "agency_name": body.agency_name or "",
            "host_name": body.host_name or "",
            "host_email": body.host_email or "",
            "host_phone": body.host_phone or "",
            "date": iso(body.date),
            "event_id": body.event_id,
            "status": "approved",
            "approved_at": iso(now_utc()),
            "approved_by": admin["id"],
            "approved_by_name": admin.get("name", "Admin"),
            "logged_by_admin": True,
            "created_at": iso(now_utc()),
        }
        await db.volunteer_hours.insert_one(doc)
        return hours_out(doc)

    @api.post("/hours/admin/bulk")
    async def admin_log_hours_bulk(body: AdminHoursBulkLogIn, admin: dict = Depends(admin_tab_dep("hours"))):
        """Admin logs the SAME volunteer activity for multiple members at once.
        Returns a per-member result list so the frontend can show which inserts
        succeeded and which were rejected (e.g. user not found, out of chapter
        scope). Auto-approved like the single-member variant."""
        # De-dupe user_ids in case the picker sent the same id twice
        unique_ids = list(dict.fromkeys(body.user_ids))
        if not unique_ids:
            raise HTTPException(status_code=400, detail="No members selected")

        # Look up all targets in one round-trip
        targets_cursor = db.users.find(
            {"id": {"$in": unique_ids}},
            {"_id": 0, "id": 1, "name": 1, "chapter_id": 1},
        )
        targets = {t["id"]: t for t in await targets_cursor.to_list(len(unique_ids))}

        # Chapter-scoped admins can only act inside their chapter
        scoped_ids = None
        if is_chapter_scoped(admin):
            scoped_ids = set(await chapter_scope_user_ids(admin) or [])

        activity_text = body.activity or body.description or "Logged by admin"
        ts = iso(now_utc())
        docs: list[dict] = []
        results: list[dict] = []
        for uid in unique_ids:
            target = targets.get(uid)
            if not target:
                results.append({"user_id": uid, "ok": False, "error": "Member not found"})
                continue
            if scoped_ids is not None and uid not in scoped_ids:
                results.append({"user_id": uid, "ok": False, "error": "Out of chapter scope"})
                continue
            doc = {
                "id": str(uuid.uuid4()),
                "user_id": target["id"],
                "user_name": target.get("name", ""),
                "hours": body.hours,
                "description": activity_text,
                "activity": activity_text,
                "event_type": body.event_type,
                "agency_name": body.agency_name or "",
                "host_name": body.host_name or "",
                "host_email": body.host_email or "",
                "host_phone": body.host_phone or "",
                "date": iso(body.date),
                "event_id": body.event_id,
                "status": "approved",
                "approved_at": ts,
                "approved_by": admin["id"],
                "approved_by_name": admin.get("name", "Admin"),
                "logged_by_admin": True,
                "created_at": ts,
            }
            docs.append(doc)
            results.append({"user_id": uid, "ok": True, "name": target.get("name", "")})

        if docs:
            await db.volunteer_hours.insert_many(docs)

        ok_count = sum(1 for r in results if r["ok"])
        fail_count = len(results) - ok_count
        return {
            "created": ok_count,
            "failed": fail_count,
            "total": len(results),
            "results": results,
        }

    @api.get("/hours/admin/csv/template")
    async def admin_csv_template(_: dict = Depends(admin_tab_dep("hours"))):
        """Returns a small CSV template so admins know which headers to use.
        Includes a single illustrative row that the admin should delete before
        uploading, plus a comment line documenting accepted date formats."""
        headers = [
            "member_email", "hours", "date", "activity", "event_type",
            "agency_name", "host_name", "host_email", "host_phone",
        ]
        sample = [
            "member@clubhaven.app", "2.5", "2026-06-15",
            "Trail cleanup at Forest Park", "aop_related",
            "Wounded Warrior Project", "Jane Host",
            "jane@example.org", "555-123-4567",
        ]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        writer.writerow(sample)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="aop-hours-template.csv"'},
        )

    @api.post("/hours/admin/csv")
    async def admin_log_hours_csv(
        file: UploadFile = File(...),
        dry_run: bool = False,
        admin: dict = Depends(admin_tab_dep("hours")),
    ):
        """Bulk-import volunteer hours from a CSV file. Required columns:
        member_email, hours, date. Optional: activity, event_type, agency_name,
        host_name, host_email, host_phone. Every successfully parsed row is
        auto-approved. Rows that fail validation are returned in `errors`
        so the admin can fix and re-upload.

        When `dry_run=true` is passed (querystring or form), nothing is written
        to the database. The response includes a `preview` array with one entry
        per CSV row (status='ready' or 'error', resolved member name, parsed
        values, and an error message when applicable) so admins can sanity-check
        the whole file before committing.
        """
        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Upload a .csv file")
        raw = await file.read()
        # Cap upload size to ~1 MB to keep parsing fast
        if len(raw) > 1024 * 1024:
            raise HTTPException(status_code=400, detail="CSV too large (max 1 MB)")
        try:
            text = raw.decode("utf-8-sig")  # tolerate Excel BOM
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
        if "hours" not in normalized:
            raise HTTPException(status_code=400, detail="CSV must include an 'hours' column")
        if "date" not in normalized:
            raise HTTPException(status_code=400, detail="CSV must include a 'date' column")

        email_key = normalized.get("member_email") or normalized.get("email")
        hours_key = normalized["hours"]
        date_key = normalized["date"]

        # Pre-resolve every email in the file in one DB round-trip
        rows = list(reader)
        if not rows:
            raise HTTPException(status_code=400, detail="CSV has no data rows")
        if len(rows) > 1000:
            raise HTTPException(status_code=400, detail="CSV is too large (max 1000 rows)")

        emails = sorted({(r.get(email_key) or "").strip().lower() for r in rows if (r.get(email_key) or "").strip()})
        users_cursor = db.users.find(
            {"email": {"$in": emails}},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "chapter_id": 1},
        )
        users_by_email = {u["email"].lower(): u for u in await users_cursor.to_list(len(emails) or 1)}

        scoped_ids = None
        if is_chapter_scoped(admin):
            scoped_ids = set(await chapter_scope_user_ids(admin) or [])

        ts = iso(now_utc())
        docs: list[dict] = []
        errors: list[dict] = []
        preview: list[dict] = []

        def opt(row, key_lower):
            real = normalized.get(key_lower)
            if not real:
                return ""
            return (row.get(real) or "").strip()

        def add_error(row_num: int, email: str, member_name: str, message: str, raw_hours: str = "", raw_date: str = "", raw_activity: str = ""):
            errors.append({"row": row_num, "message": message})
            preview.append({
                "row": row_num,
                "status": "error",
                "email": email,
                "member_name": member_name,
                "hours": raw_hours,
                "date": raw_date,
                "activity": raw_activity,
                "message": message,
            })

        for idx, row in enumerate(rows, start=2):  # row 1 is header, so data starts at 2
            email_raw = (row.get(email_key) or "").strip()
            email = email_raw.lower()
            raw_hours = (row.get(hours_key) or "").strip()
            raw_date = (row.get(date_key) or "").strip()
            raw_activity = opt(row, "activity")

            if not email:
                add_error(idx, "", "", "Missing member_email", raw_hours, raw_date, raw_activity)
                continue
            target = users_by_email.get(email)
            if not target:
                add_error(idx, email_raw, "", f"No member with email {email_raw}", raw_hours, raw_date, raw_activity)
                continue
            if scoped_ids is not None and target["id"] not in scoped_ids:
                add_error(idx, email_raw, target.get("name", ""), f"{email_raw} is out of your chapter scope", raw_hours, raw_date, raw_activity)
                continue
            try:
                hours_val = float(raw_hours)
                if hours_val <= 0 or hours_val > 1000:
                    raise ValueError("hours must be > 0 and <= 1000")
            except Exception:
                add_error(idx, email_raw, target.get("name", ""), "Invalid hours value", raw_hours, raw_date, raw_activity)
                continue
            if not raw_date:
                add_error(idx, email_raw, target.get("name", ""), f"Missing date — use {DATE_FORMATS_FOR_HUMANS}", raw_hours, raw_date, raw_activity)
                continue
            try:
                parsed_dt = _parse_csv_date(raw_date)
            except ValueError as exc:
                add_error(idx, email_raw, target.get("name", ""), str(exc), raw_hours, raw_date, raw_activity)
                continue
            event_type = (opt(row, "event_type") or "aop_related").lower()
            if event_type not in ("aop_related", "other"):
                event_type = "aop_related"
            activity_text = raw_activity or "Logged by admin (CSV import)"
            docs.append({
                "id": str(uuid.uuid4()),
                "user_id": target["id"],
                "user_name": target.get("name", ""),
                "hours": hours_val,
                "description": activity_text,
                "activity": activity_text,
                "event_type": event_type,
                "agency_name": opt(row, "agency_name"),
                "host_name": opt(row, "host_name"),
                "host_email": opt(row, "host_email"),
                "host_phone": opt(row, "host_phone"),
                "date": iso(parsed_dt),
                "event_id": None,
                "status": "approved",
                "approved_at": ts,
                "approved_by": admin["id"],
                "approved_by_name": admin.get("name", "Admin"),
                "logged_by_admin": True,
                "imported_from_csv": file.filename,
                "csv_row": idx,
                "created_at": ts,
            })
            preview.append({
                "row": idx,
                "status": "ready",
                "email": target.get("email", email_raw),
                "member_name": target.get("name", ""),
                "hours": hours_val,
                "date": iso(parsed_dt)[:10],
                "activity": activity_text,
            })

        if not dry_run and docs:
            await db.volunteer_hours.insert_many(docs)

        # Avoid sending an unbounded errors[] payload for huge files.
        errors_truncated = errors[:50]
        # Cap preview at 200 rows so very large files don't blow up the response.
        preview_truncated = preview[:200]
        return {
            "dry_run": dry_run,
            "created": 0 if dry_run else len(docs),
            "ready": len(docs),  # number that WOULD be created (or were)
            "failed": len(errors),
            "total": len(rows),
            "errors": errors_truncated,
            "errors_truncated": len(errors) > 50,
            "preview": preview_truncated,
            "preview_truncated": len(preview) > 200,
        }

    @api.get("/hours")
    async def list_hours(status_filter: Optional[str] = None, admin: dict = Depends(require_admin)):
        query: dict = {}
        if status_filter:
            query["status"] = status_filter
        if is_chapter_scoped(admin):
            ids = await chapter_scope_user_ids(admin)
            query["user_id"] = {"$in": ids or []}
        cursor = db.volunteer_hours.find(query, {"_id": 0}).sort("created_at", -1).limit(500)
        items = await cursor.to_list(500)
        return [hours_out(h) for h in items]

    @api.put("/hours/{hours_id}/review")
    async def review_hours(hours_id: str, body: HoursReviewIn, admin: dict = Depends(admin_tab_dep("hours"))):
        """Admin reviews a member's volunteer-hours submission.

        Admin can:
          - Flip status: pending → approved | rejected (and any time after, re-flip).
          - Optionally adjust the recorded hours value (e.g. submitter logged 5, only 4.5 worked).
          - Optionally edit activity / agency / event_type along with approval.
        """
        existing = await db.volunteer_hours.find_one({"id": hours_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Hours entry not found")
        update_doc: dict = {
            "status": body.status,
            "note": body.note or existing.get("note", ""),
            "reviewed_by": admin["id"],
            "reviewed_by_name": admin.get("name", "Admin"),
            "reviewed_at": iso(now_utc()),
        }
        if body.hours is not None:
            update_doc["hours"] = float(body.hours)
            update_doc["hours_adjusted_by"] = admin["id"]
            update_doc["hours_adjusted_by_name"] = admin.get("name", "Admin")
            update_doc["hours_adjusted_at"] = iso(now_utc())
        if body.activity:
            update_doc["activity"] = body.activity
        if body.agency_name:
            update_doc["agency_name"] = body.agency_name
        if body.event_type:
            update_doc["event_type"] = body.event_type
        await db.volunteer_hours.update_one({"id": hours_id}, {"$set": update_doc})
        h = await db.volunteer_hours.find_one({"id": hours_id}, {"_id": 0})
        return hours_out(h)

    @api.put("/hours/{hours_id}")
    async def admin_edit_hours(hours_id: str, body: AdminHoursEditIn, admin: dict = Depends(admin_tab_dep("hours"))):
        """Admin-only full edit of an existing hours record.

        Every field is optional — only keys explicitly supplied in the body are
        written. Status changes accepted here so admins can use a single
        dialog to fix and re-approve. `hours_adjusted_by/_at` is stamped when
        `hours` changes; `reviewed_by/_at` is stamped when `status` changes.
        Returns the fully-refreshed entry."""
        existing = await db.volunteer_hours.find_one({"id": hours_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Hours entry not found")
        patch = body.model_dump(exclude_unset=True)
        if not patch:
            return hours_out(existing)
        update_doc: dict = {}
        now_iso = iso(now_utc())

        # Hours value change → stamp adjustment audit fields.
        if "hours" in patch and patch["hours"] is not None and float(patch["hours"]) != float(existing.get("hours", 0)):
            update_doc["hours"] = float(patch["hours"])
            update_doc["hours_adjusted_by"] = admin["id"]
            update_doc["hours_adjusted_by_name"] = admin.get("name", "Admin")
            update_doc["hours_adjusted_at"] = now_iso

        # Status change → stamp review audit fields (same as /review).
        if "status" in patch and patch["status"] and patch["status"] != existing.get("status"):
            update_doc["status"] = patch["status"]
            update_doc["reviewed_by"] = admin["id"]
            update_doc["reviewed_by_name"] = admin.get("name", "Admin")
            update_doc["reviewed_at"] = now_iso

        # Date — Pydantic gives us a datetime; persist as ISO string to match
        # the rest of the collection.
        if "date" in patch and patch["date"] is not None:
            update_doc["date"] = iso(patch["date"])

        # Free-text and enum fields — copy through if explicitly supplied.
        for key in ("activity", "description", "event_type", "agency_name",
                    "host_name", "host_email", "host_phone", "event_id", "note"):
            if key in patch and patch[key] is not None:
                update_doc[key] = patch[key]

        if update_doc:
            await db.volunteer_hours.update_one({"id": hours_id}, {"$set": update_doc})
        h = await db.volunteer_hours.find_one({"id": hours_id}, {"_id": 0})
        return hours_out(h)

    @api.delete("/hours/{hours_id}")
    async def delete_hours(hours_id: str, user: dict = Depends(get_current_user)):
        h = await db.volunteer_hours.find_one({"id": hours_id})
        if not h:
            raise HTTPException(status_code=404, detail="Not found")
        if h["user_id"] != user["id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not allowed")
        await db.volunteer_hours.delete_one({"id": hours_id})
        return {"ok": True}

    @api.get("/me/hours")
    async def my_hours(
        user: dict = Depends(get_current_user),
        year: Optional[int] = None,
        quarter: Optional[int] = None,
        month: Optional[int] = None,
        status_filter: Optional[str] = None,
    ):
        q: dict = {"user_id": user["id"]}
        if status_filter:
            q["status"] = status_filter
        period_from, period_to = period_to_range(year, quarter, month)
        if period_from:
            q["date"] = {"$gte": period_from, "$lte": period_to}
        cursor = db.volunteer_hours.find(q, {"_id": 0}).sort("date", -1)
        items = await cursor.to_list(500)
        return [hours_out(h) for h in items]

    @api.get("/me/hours/summary")
    async def my_hours_summary(
        user: dict = Depends(get_current_user),
        year: Optional[int] = None,
    ):
        """Per-member rollup: hours by month for the requested year (defaults to current).
        Returns: { year, total_approved, total_pending, by_month: [...], by_quarter: [...] }
        """
        target_year = year or _dt.utcnow().year
        period_from, period_to = period_to_range(target_year, None, None)
        items = await db.volunteer_hours.find(
            {"user_id": user["id"], "date": {"$gte": period_from, "$lte": period_to}},
            {"_id": 0},
        ).to_list(2000)

        by_month = [{
            "label": _dt(target_year, m, 1).strftime("%b"),
            "key": f"{target_year}-{m:02d}",
            "hours": 0.0, "approved_hours": 0.0, "count": 0,
        } for m in range(1, 13)]
        by_quarter = [{
            "label": f"Q{q}",
            "key": f"{target_year}-Q{q}",
            "hours": 0.0, "approved_hours": 0.0, "count": 0,
        } for q in range(1, 5)]

        total_approved = 0.0
        total_pending = 0.0
        for h in items:
            ds = (h.get("date") or "")[:10]
            try:
                dt = _dt.fromisoformat(ds.replace("Z", ""))
            except Exception:
                continue
            hrs = h.get("hours", 0) or 0
            is_approved = h.get("status") == "approved"
            is_pending = h.get("status") == "pending"
            if is_approved:
                total_approved += hrs
            if is_pending:
                total_pending += hrs
            m_idx = dt.month - 1
            by_month[m_idx]["hours"] += hrs
            by_month[m_idx]["count"] += 1
            if is_approved:
                by_month[m_idx]["approved_hours"] += hrs
            q_idx = (dt.month - 1) // 3
            by_quarter[q_idx]["hours"] += hrs
            by_quarter[q_idx]["count"] += 1
            if is_approved:
                by_quarter[q_idx]["approved_hours"] += hrs

        for row in by_month + by_quarter:
            row["hours"] = round(row["hours"], 2)
            row["approved_hours"] = round(row["approved_hours"], 2)

        return {
            "year": target_year,
            "total_approved": round(total_approved, 2),
            "total_pending": round(total_pending, 2),
            "by_month": by_month,
            "by_quarter": by_quarter,
        }
