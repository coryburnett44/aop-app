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
from routes._csv_member_lookup import (
    MEMBER_LOOKUP_HEADER_HINT,
    member_lookup_columns_present,
    prefetch_member_lookup,
    resolve_member_for_row,
)


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
    send_push_best_effort=None,
):

    # Iter 122: Only Full Access + Operations Manager can log hours for
    # OTHER members and approve pending entries. Governor Manager and
    # Membership Manager can log for themselves only (via `POST /hours`).
    # Iter 123: This is now overridable per-role via db.app_settings.
    _DEFAULT_HOURS_ROLE_CONFIG = {
        "full":                {"can_manage_others": True,  "default_mode": "for_others"},
        "operations_manager":  {"can_manage_others": True,  "default_mode": "for_others"},
        "governor_manager":    {"can_manage_others": False, "default_mode": "for_myself"},
        "membership_manager":  {"can_manage_others": False, "default_mode": "for_myself"},
    }

    def _fallback_role_entry(role: str) -> dict:
        """Default per-role behavior when no override doc exists."""
        return _DEFAULT_HOURS_ROLE_CONFIG.get(role, {
            # Unknown role → conservative: cannot manage others, self-only.
            "can_manage_others": False,
            "default_mode": "for_myself",
        })

    async def _load_hours_role_config() -> dict:
        """Merge stored overrides on top of the built-in defaults so every
        known role always has an entry, and unknown/new roles fall back
        cleanly."""
        merged = {k: dict(v) for k, v in _DEFAULT_HOURS_ROLE_CONFIG.items()}
        try:
            doc = await db.app_settings.find_one({"key": "hours_role_config"}, {"_id": 0})
        except Exception:
            doc = None
        overrides = (doc or {}).get("roles") or {}
        for role, entry in overrides.items():
            if not isinstance(entry, dict):
                continue
            merged.setdefault(role, {"can_manage_others": False, "default_mode": "for_myself"})
            if "can_manage_others" in entry:
                merged[role]["can_manage_others"] = bool(entry["can_manage_others"])
            if "default_mode" in entry and entry["default_mode"] in ("for_others", "for_myself"):
                merged[role]["default_mode"] = entry["default_mode"]
        return merged

    def _admin_role(u: dict) -> str:
        return (u.get("admin_role") or "full") if u.get("role") == "admin" else ""

    async def _can_manage_hours_for_others(admin: dict) -> bool:
        role = _admin_role(admin)
        if not role:
            return False
        cfg = await _load_hours_role_config()
        return bool(cfg.get(role, _fallback_role_entry(role))["can_manage_others"])

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

    # ============================================================
    # Iter 123: admin-configurable per-role hours behavior.
    # Lets Full Access admins add/edit the {role → can_manage_others,
    # default_mode} map without a code change. New sub-roles (added via
    # admin custom roles) can be granted or denied hours-manage rights
    # entirely from the Admin Settings UI.
    # ============================================================
    @api.get("/hours/role-config")
    async def get_hours_role_config(user: dict = Depends(get_current_user)):
        """Returns the effective per-role hours config. Any authenticated
        user can read it — the frontend uses it to decide whether to show
        the 'Log for others / Log for myself' toggle. Non-admins get a
        trivial payload (their role isn't listed)."""
        cfg = await _load_hours_role_config()
        # Return as a sorted list for deterministic client rendering.
        items = [
            {"role": role, "label": _pretty_role(role), **entry}
            for role, entry in sorted(cfg.items(), key=lambda kv: kv[0])
        ]
        # The `defaults` block is what the frontend uses if the caller's
        # own role isn't listed in the config — matches _fallback_role_entry.
        return {
            "items": items,
            "defaults": {"can_manage_others": False, "default_mode": "for_myself"},
        }

    @api.put("/hours/role-config")
    async def set_hours_role_config(body: dict, admin: dict = Depends(require_admin)):
        """Full Access admin overrides one or more roles. Body shape:
          { roles: { "<role_key>": { can_manage_others: bool, default_mode: "for_others"|"for_myself" }, ... } }
        Missing role keys keep their existing behavior. Passing `null` for a
        role removes its override (falls back to code defaults)."""
        if _admin_role(admin) != "full":
            raise HTTPException(
                status_code=403,
                detail="Only Full Access admins can change the hours role config.",
            )
        roles_in = body.get("roles") if isinstance(body, dict) else None
        if not isinstance(roles_in, dict) or not roles_in:
            raise HTTPException(status_code=400, detail="Provide `roles` object with at least one role update.")
        existing = await db.app_settings.find_one({"key": "hours_role_config"}, {"_id": 0}) or {}
        overrides = dict(existing.get("roles") or {})
        for role, entry in roles_in.items():
            role = str(role or "").strip().lower()
            if not role or " " in role:
                raise HTTPException(status_code=400, detail=f"Invalid role key: {role!r}")
            if entry is None:
                overrides.pop(role, None)
                continue
            if not isinstance(entry, dict):
                raise HTTPException(status_code=400, detail=f"Entry for {role!r} must be an object or null.")
            new_entry: dict = {}
            if "can_manage_others" in entry:
                new_entry["can_manage_others"] = bool(entry["can_manage_others"])
            if "default_mode" in entry:
                mode = entry["default_mode"]
                if mode not in ("for_others", "for_myself"):
                    raise HTTPException(status_code=400, detail=f"default_mode for {role!r} must be 'for_others' or 'for_myself'.")
                new_entry["default_mode"] = mode
            if not new_entry:
                continue
            overrides[role] = {**(overrides.get(role) or {}), **new_entry}
        await db.app_settings.update_one(
            {"key": "hours_role_config"},
            {"$set": {
                "key": "hours_role_config",
                "roles": overrides,
                "updated_at": iso(now_utc()),
                "updated_by": admin.get("name", "") or admin.get("email", ""),
            }},
            upsert=True,
        )
        return await get_hours_role_config(admin)

    def _pretty_role(role: str) -> str:
        """Human-facing label. Falls back to Title Case for unknown roles."""
        return {
            "full": "Full Access",
            "operations_manager": "Operations Manager",
            "governor_manager": "Governor Manager",
            "membership_manager": "Membership Manager",
        }.get(role, role.replace("_", " ").title())

    @api.post("/hours/admin")
    async def admin_log_hours(body: AdminHoursLogIn, admin: dict = Depends(admin_tab_dep("hours"))):
        """Admin logs hours on behalf of a member. Restricted to Full Access
        and Operations Manager admins — Governor Managers and Membership
        Managers must use `POST /hours` to log their own hours."""
        if not await _can_manage_hours_for_others(admin):
            raise HTTPException(
                status_code=403,
                detail="Only Full Access and Operations Manager admins can log hours for other members. Use the personal hours form to log your own.",
            )
        target = await db.users.find_one({"id": body.user_id}, {"_id": 0, "id": 1, "name": 1, "chapter_id": 1})
        if not target:
            raise HTTPException(status_code=404, detail="Member not found")
        # Chapter-scoped admins (e.g. Governor) can only log for members in their chapter.
        if is_chapter_scoped(admin):
            allowed_ids = await chapter_scope_user_ids(admin)
            if body.user_id not in (allowed_ids or []):
                raise HTTPException(status_code=403, detail="You can only log hours for members in your chapter.")
        activity_text = body.activity or body.description or "Logged by admin"
        can_auto_approve = not is_chapter_scoped(admin)
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
            "status": "approved" if can_auto_approve else "pending",
            "logged_by_admin": True,
            "created_at": iso(now_utc()),
        }
        if can_auto_approve:
            doc["approved_at"] = iso(now_utc())
            doc["approved_by"] = admin["id"]
            doc["approved_by_name"] = admin.get("name", "Admin")
        await db.volunteer_hours.insert_one(doc)
        return hours_out(doc)

    @api.post("/hours/admin/bulk")
    async def admin_log_hours_bulk(body: AdminHoursBulkLogIn, admin: dict = Depends(admin_tab_dep("hours"))):
        """Admin logs the SAME volunteer activity for multiple members at once.
        Restricted to Full Access + Operations Manager admins."""
        if not await _can_manage_hours_for_others(admin):
            raise HTTPException(
                status_code=403,
                detail="Only Full Access and Operations Manager admins can log hours for other members.",
            )
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
        can_auto_approve = not is_chapter_scoped(admin)
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
                "status": "approved" if can_auto_approve else "pending",
                "logged_by_admin": True,
                "created_at": ts,
            }
            if can_auto_approve:
                doc["approved_at"] = ts
                doc["approved_by"] = admin["id"]
                doc["approved_by_name"] = admin.get("name", "Admin")
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
        uploading, plus a comment line documenting accepted date formats.

        Member identifier: `member_email` is the preferred key, but admins
        can also use `full_name`, OR `first_name`+`last_name` for rows where
        the on-file email doesn't match what the member uses day-to-day.
        Resolution falls back in that order; ambiguous name matches are
        flagged as errors so the admin can supply an email."""
        headers = [
            "member_email", "full_name", "first_name", "last_name",
            "hours", "date", "activity", "event_type",
            "agency_name", "host_name", "host_email", "host_phone",
        ]
        sample = [
            "member@clubhaven.app", "", "", "",
            "2.5", "2026-06-15",
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
        """Bulk-import volunteer hours from a CSV file. Restricted to Full
        Access + Operations Manager admins.

        Member identifier (any ONE of):
          - `member_email` (preferred, exact case-insensitive)
          - `full_name` (matches `users.name` exactly, case-insensitive)
          - `first_name` + `last_name` (both, exact case-insensitive)
        Resolution falls back in the order above. Ambiguous name matches
        (>1 member with the same name) become row errors and require the
        admin to supply an email.

        Other required columns: hours, date.
        Optional: activity, event_type, agency_name, host_name, host_email,
        host_phone. Every successfully parsed row is auto-approved. Rows
        that fail validation are returned in `errors` so the admin can fix
        and re-upload.

        When `dry_run=true` is passed (querystring or form), nothing is
        written to the database. The response includes a `preview` array
        with one entry per CSV row.
        """
        if not await _can_manage_hours_for_others(admin):
            raise HTTPException(
                status_code=403,
                detail="Only Full Access and Operations Manager admins can bulk-import hours for other members.",
            )
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
        headers_lower = set(normalized.keys())
        if not member_lookup_columns_present(headers_lower):
            raise HTTPException(status_code=400, detail=MEMBER_LOOKUP_HEADER_HINT)
        if "hours" not in normalized:
            raise HTTPException(status_code=400, detail="CSV must include an 'hours' column")
        if "date" not in normalized:
            raise HTTPException(status_code=400, detail="CSV must include a 'date' column")

        hours_key = normalized["hours"]
        date_key = normalized["date"]

        rows = list(reader)
        if not rows:
            raise HTTPException(status_code=400, detail="CSV has no data rows")
        if len(rows) > 1000:
            raise HTTPException(status_code=400, detail="CSV is too large (max 1000 rows)")

        # Pre-resolve every member identifier (email + names) in one DB round-trip
        lookup_index = await prefetch_member_lookup(db, rows)

        scoped_ids = None
        if is_chapter_scoped(admin):
            scoped_ids = set(await chapter_scope_user_ids(admin) or [])

        ts = iso(now_utc())
        can_auto_approve = not is_chapter_scoped(admin)
        docs: list[dict] = []
        errors: list[dict] = []
        preview: list[dict] = []

        def opt(row, key_lower):
            real = normalized.get(key_lower)
            if not real:
                return ""
            return (row.get(real) or "").strip()

        def add_error(row_num: int, ident_label: str, member_name: str, message: str, raw_hours: str = "", raw_date: str = "", raw_activity: str = ""):
            errors.append({"row": row_num, "message": message})
            preview.append({
                "row": row_num,
                "status": "error",
                "email": ident_label,
                "member_name": member_name,
                "hours": raw_hours,
                "date": raw_date,
                "activity": raw_activity,
                "message": message,
            })

        for idx, row in enumerate(rows, start=2):  # row 1 is header, so data starts at 2
            raw_hours = (row.get(hours_key) or "").strip()
            raw_date = (row.get(date_key) or "").strip()
            raw_activity = opt(row, "activity")

            res = resolve_member_for_row(row, lookup_index)
            if res.error or not res.user:
                add_error(idx, res.label, "", res.error or "could not resolve member", raw_hours, raw_date, raw_activity)
                continue
            target = res.user
            ident_label = res.label or target.get("email", "")
            if scoped_ids is not None and target["id"] not in scoped_ids:
                add_error(idx, ident_label, target.get("name", ""), f"{ident_label} is out of your chapter scope", raw_hours, raw_date, raw_activity)
                continue
            try:
                hours_val = float(raw_hours)
                if hours_val <= 0 or hours_val > 1000:
                    raise ValueError("hours must be > 0 and <= 1000")
            except Exception:
                add_error(idx, ident_label, target.get("name", ""), "Invalid hours value", raw_hours, raw_date, raw_activity)
                continue
            if not raw_date:
                add_error(idx, ident_label, target.get("name", ""), f"Missing date — use {DATE_FORMATS_FOR_HUMANS}", raw_hours, raw_date, raw_activity)
                continue
            try:
                parsed_dt = _parse_csv_date(raw_date)
            except ValueError as exc:
                add_error(idx, ident_label, target.get("name", ""), str(exc), raw_hours, raw_date, raw_activity)
                continue
            event_type = (opt(row, "event_type") or "aop_related").lower()
            if event_type not in ("aop_related", "trendsetters_spirits", "other"):
                event_type = "aop_related"
            activity_text = raw_activity or "Logged by admin (CSV import)"
            row_doc = {
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
                "status": "approved" if can_auto_approve else "pending",
                "logged_by_admin": True,
                "imported_from_csv": file.filename,
                "csv_row": idx,
                "created_at": ts,
            }
            if can_auto_approve:
                row_doc["approved_at"] = ts
                row_doc["approved_by"] = admin["id"]
                row_doc["approved_by_name"] = admin.get("name", "Admin")
            docs.append(row_doc)
            preview.append({
                "row": idx,
                "status": "ready",
                "email": target.get("email", ident_label),
                "member_name": target.get("name", ""),
                "matched_by": res.matched_by,
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
        # Iter 122: Only Full Access + Operations Manager admins can review
        # (approve/reject/adjust) hours. Governor Managers and Membership
        # Managers can view the queue for their scope but cannot flip status.
        if not await _can_manage_hours_for_others(admin):
            raise HTTPException(
                status_code=403,
                detail="Only Full Access and Operations Manager admins can review volunteer hours.",
            )
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
        # Companion OneSignal push — only when status flips from something
        # else to "approved" (never on re-approval or rejection).
        if (
            body.status == "approved"
            and existing.get("status") != "approved"
            and send_push_best_effort is not None
        ):
            import os as _os_h
            import asyncio as _asyncio_h
            frontend_url = (_os_h.environ.get("FRONTEND_URL", "https://aop-app.org") or "").rstrip("/")
            hours_val = float(update_doc.get("hours", existing.get("hours", 0)) or 0)
            _asyncio_h.create_task(send_push_best_effort(
                db=db, logger=None, iso=iso, now_utc=now_utc,
                title="✅ Volunteer hours approved",
                body=f"Your {hours_val:g}-hour submission for {existing.get('activity', 'volunteering')} has been approved.",
                url=f"{frontend_url}/hours",
                user_ids=[existing["user_id"]],
                segment="custom",
                trigger="hours_approved",
            ))
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
        # Iter 122: full-edit reserved for Full Access + Operations Manager.
        if not await _can_manage_hours_for_others(admin):
            raise HTTPException(
                status_code=403,
                detail="Only Full Access and Operations Manager admins can edit other members' hours.",
            )
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
        # Same approval-push as /review — only fires on status flip TO approved.
        if (
            update_doc.get("status") == "approved"
            and existing.get("status") != "approved"
            and send_push_best_effort is not None
        ):
            import os as _os_h2
            import asyncio as _asyncio_h2
            frontend_url = (_os_h2.environ.get("FRONTEND_URL", "https://aop-app.org") or "").rstrip("/")
            hours_val = float(update_doc.get("hours", existing.get("hours", 0)) or 0)
            _asyncio_h2.create_task(send_push_best_effort(
                db=db, logger=None, iso=iso, now_utc=now_utc,
                title="✅ Volunteer hours approved",
                body=f"Your {hours_val:g}-hour submission for {existing.get('activity', 'volunteering')} has been approved.",
                url=f"{frontend_url}/hours",
                user_ids=[existing["user_id"]],
                segment="custom",
                trigger="hours_approved",
            ))
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
