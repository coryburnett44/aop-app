"""Member Recruitment tracking endpoints.

Owns the recruitment surface: each record links a *recruiter* (existing
member) to a *recruit* (existing member) with a date + optional notes.

  REST — admin console (Admin → Recruitment tab):
    GET    /recruitments              # list w/ optional search
    POST   /recruitments              # add
    PUT    /recruitments/{rid}        # edit
    DELETE /recruitments/{rid}        # delete
    GET    /recruitments/csv/template # header + example row download
    GET    /recruitments/csv/export   # full-table CSV
    POST   /recruitments/csv          # bulk import w/ dry_run preview

  REST — reports tab (mirrors donations/hours/rsvps shape):
    GET    /reports/recruitment            # rows: entries | by_member | by_chapter | by_period
    GET    /reports/recruitment/summary    # summary shell w/ totals + rows

  Public leaderboard:
    GET    /leaderboards/top-recruiters?period=q1|q2|q3|q4|year
"""
import csv as _csv
import io as _io
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field


def _parse_recruitment_date(raw: str) -> datetime:
    """Accept ISO (YYYY-MM-DD, with or without time) and a few common
    US-style variants ('MM/DD/YYYY', 'M/D/YY'). Returns UTC datetime."""
    from datetime import timezone
    s = (raw or "").strip()
    if not s:
        raise ValueError("date is required")
    # Try ISO first (fromisoformat handles most cases)
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            d = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return d
        except ValueError:
            continue
    raise ValueError(f"couldn't parse date '{raw}' (try YYYY-MM-DD)")


def _record_out(r: dict) -> dict:
    return {
        "id": r["id"],
        "recruiter_id": r.get("recruiter_id", ""),
        "recruiter_name": r.get("recruiter_name", ""),
        "recruiter_email": r.get("recruiter_email", ""),
        "recruit_id": r.get("recruit_id", ""),
        "recruit_name": r.get("recruit_name", ""),
        "recruit_email": r.get("recruit_email", ""),
        "chapter_id": r.get("chapter_id"),
        "chapter_name": r.get("chapter_name") or "",
        "date_recruited": r.get("date_recruited", ""),
        "notes": r.get("notes", ""),
        "created_by": r.get("created_by"),
        "created_by_name": r.get("created_by_name", ""),
        "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"),
    }


class RecruitmentIn(BaseModel):
    recruiter_id: str = Field(min_length=1)
    recruit_id: str = Field(min_length=1)
    date_recruited: str = Field(min_length=1)
    notes: str = ""


class RecruitmentUpdateIn(BaseModel):
    recruiter_id: Optional[str] = None
    recruit_id: Optional[str] = None
    date_recruited: Optional[str] = None
    notes: Optional[str] = None


RECRUITMENT_CSV_COLUMNS = [
    "recruiter_email", "recruiter_full_name", "recruiter_first_name", "recruiter_last_name",
    "recruit_email", "recruit_full_name", "recruit_first_name", "recruit_last_name",
    "date_recruited", "notes",
]
RECRUITMENT_CSV_SAMPLE_ROW = [
    "recruiter@example.com", "", "", "",
    "recruit@example.com", "", "", "",
    "2026-02-15", "Met at Annual Convention",
]


# Column aliases we accept for each side of the pair.
_RECRUITER_EMAIL_COLS = ("recruiter_email", "sponsor_email")
_RECRUITER_FULL_COLS = ("recruiter_full_name", "recruiter_name", "sponsor_name")
_RECRUITER_FIRST_COLS = ("recruiter_first_name", "recruiter_firstname")
_RECRUITER_LAST_COLS = ("recruiter_last_name", "recruiter_lastname")

_RECRUIT_EMAIL_COLS = ("recruit_email", "member_email", "new_member_email")
_RECRUIT_FULL_COLS = ("recruit_full_name", "recruit_name", "member_full_name", "member_name", "new_member_name")
_RECRUIT_FIRST_COLS = ("recruit_first_name", "member_first_name", "new_member_first_name")
_RECRUIT_LAST_COLS = ("recruit_last_name", "member_last_name", "new_member_last_name")


def _cell(row: dict, names) -> str:
    for n in names:
        v = row.get(n)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


async def _lookup_member(db, *, email: str, full_name: str, first: str, last: str) -> tuple[Optional[dict], str, str]:
    """Return (user_or_None, matched_by, label). Ambiguity → (None, 'ambiguous', label)."""
    import re
    if email:
        u = await db.users.find_one(
            {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "chapter_id": 1},
        )
        return (u, "email" if u else "email_missing", email)
    if full_name:
        matches = await db.users.find(
            {"name": {"$regex": f"^{re.escape(full_name)}$", "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "chapter_id": 1},
        ).to_list(5)
        if not matches:
            return (None, "full_name_missing", full_name)
        if len(matches) > 1:
            return (None, "ambiguous", full_name)
        return (matches[0], "full_name", full_name)
    if first and last:
        matches = await db.users.find(
            {
                "first_name": {"$regex": f"^{re.escape(first)}$", "$options": "i"},
                "last_name": {"$regex": f"^{re.escape(last)}$", "$options": "i"},
            },
            {"_id": 0, "id": 1, "name": 1, "email": 1, "chapter_id": 1},
        ).to_list(5)
        label = f"{first} {last}"
        if not matches:
            return (None, "first_last_missing", label)
        if len(matches) > 1:
            return (None, "ambiguous", label)
        return (matches[0], "first_last", label)
    return (None, "missing", "")


def register(api, *, db, iso, now_utc, get_current_user, admin_tab_dep, is_chapter_scoped, chapter_scope_user_ids):
    async def _hydrate(u_id: str) -> dict:
        if not u_id:
            return {}
        u = await db.users.find_one({"id": u_id}, {"_id": 0, "id": 1, "name": 1, "email": 1, "chapter_id": 1})
        return u or {}

    async def _build_record(recruiter_id: str, recruit_id: str, date_iso: str, notes: str, admin: dict) -> dict:
        if recruiter_id == recruit_id:
            raise HTTPException(status_code=400, detail="A member cannot recruit themselves.")
        recruiter = await _hydrate(recruiter_id)
        recruit = await _hydrate(recruit_id)
        if not recruiter:
            raise HTTPException(status_code=400, detail="Recruiter not found.")
        if not recruit:
            raise HTTPException(status_code=400, detail="Recruit not found.")
        chapter_id = recruiter.get("chapter_id")
        chapter_name = ""
        if chapter_id:
            c = await db.chapters.find_one({"id": chapter_id}, {"_id": 0, "name": 1})
            chapter_name = (c or {}).get("name") or ""
        return {
            "id": str(uuid.uuid4()),
            "recruiter_id": recruiter["id"],
            "recruiter_name": recruiter.get("name", ""),
            "recruiter_email": recruiter.get("email", ""),
            "recruit_id": recruit["id"],
            "recruit_name": recruit.get("name", ""),
            "recruit_email": recruit.get("email", ""),
            "chapter_id": chapter_id,
            "chapter_name": chapter_name,
            "date_recruited": date_iso,
            "notes": (notes or "").strip(),
            "created_by": admin["id"],
            "created_by_name": admin.get("name", ""),
            "created_at": iso(now_utc()),
            "updated_at": iso(now_utc()),
        }

    # ---------- CRUD ----------
    @api.get("/recruitments")
    async def list_recruitments(
        q: str = "",
        limit: int = Query(500, le=2000, ge=1),
        admin: dict = Depends(admin_tab_dep("recruitment")),
    ):
        """List all recruitment records. `q` filters (case-insensitive) on
        recruiter/recruit name + email + notes."""
        query: dict = {}
        if is_chapter_scoped(admin):
            ids = await chapter_scope_user_ids(admin)
            query["$or"] = [{"recruiter_id": {"$in": ids or []}}, {"recruit_id": {"$in": ids or []}}]
        if q:
            import re
            rx = {"$regex": re.escape(q), "$options": "i"}
            search_or = [
                {"recruiter_name": rx}, {"recruiter_email": rx},
                {"recruit_name": rx}, {"recruit_email": rx},
                {"notes": rx},
            ]
            if "$or" in query:
                # combine with $and so both scope + text-search apply
                query = {"$and": [{"$or": query.pop("$or")}, {"$or": search_or}]}
            else:
                query["$or"] = search_or
        cursor = db.recruitments.find(query, {"_id": 0}).sort("date_recruited", -1).limit(limit)
        return [_record_out(r) async for r in cursor]

    @api.post("/recruitments")
    async def create_recruitment(body: RecruitmentIn, admin: dict = Depends(admin_tab_dep("recruitment"))):
        try:
            dt = _parse_recruitment_date(body.date_recruited)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        doc = await _build_record(body.recruiter_id, body.recruit_id, iso(dt), body.notes, admin)
        # Prevent duplicate recruiter→recruit pair with the same date.
        exists = await db.recruitments.find_one({
            "recruiter_id": doc["recruiter_id"],
            "recruit_id": doc["recruit_id"],
            "date_recruited": doc["date_recruited"],
        })
        if exists:
            raise HTTPException(status_code=409, detail="A recruitment record for that recruiter/recruit pair on that date already exists.")
        await db.recruitments.insert_one(doc)
        return _record_out(doc)

    @api.put("/recruitments/{rid}")
    async def update_recruitment(rid: str, body: RecruitmentUpdateIn, admin: dict = Depends(admin_tab_dep("recruitment"))):
        existing = await db.recruitments.find_one({"id": rid}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Recruitment record not found.")
        updates: dict = {}
        if body.notes is not None:
            updates["notes"] = body.notes.strip()
        if body.date_recruited is not None:
            try:
                updates["date_recruited"] = iso(_parse_recruitment_date(body.date_recruited))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        if body.recruiter_id and body.recruiter_id != existing.get("recruiter_id"):
            recruiter = await _hydrate(body.recruiter_id)
            if not recruiter:
                raise HTTPException(status_code=400, detail="Recruiter not found.")
            updates["recruiter_id"] = recruiter["id"]
            updates["recruiter_name"] = recruiter.get("name", "")
            updates["recruiter_email"] = recruiter.get("email", "")
            updates["chapter_id"] = recruiter.get("chapter_id")
            c_name = ""
            if recruiter.get("chapter_id"):
                c = await db.chapters.find_one({"id": recruiter["chapter_id"]}, {"_id": 0, "name": 1})
                c_name = (c or {}).get("name") or ""
            updates["chapter_name"] = c_name
        if body.recruit_id and body.recruit_id != existing.get("recruit_id"):
            recruit = await _hydrate(body.recruit_id)
            if not recruit:
                raise HTTPException(status_code=400, detail="Recruit not found.")
            updates["recruit_id"] = recruit["id"]
            updates["recruit_name"] = recruit.get("name", "")
            updates["recruit_email"] = recruit.get("email", "")
        # Same-member sanity check
        final_recruiter = updates.get("recruiter_id", existing.get("recruiter_id"))
        final_recruit = updates.get("recruit_id", existing.get("recruit_id"))
        if final_recruiter == final_recruit:
            raise HTTPException(status_code=400, detail="A member cannot recruit themselves.")
        if updates:
            updates["updated_at"] = iso(now_utc())
            await db.recruitments.update_one({"id": rid}, {"$set": updates})
        fresh = await db.recruitments.find_one({"id": rid}, {"_id": 0})
        return _record_out(fresh)

    @api.delete("/recruitments/{rid}")
    async def delete_recruitment(rid: str, _: dict = Depends(admin_tab_dep("recruitment"))):
        r = await db.recruitments.find_one({"id": rid}, {"_id": 0, "id": 1})
        if not r:
            raise HTTPException(status_code=404, detail="Recruitment record not found.")
        await db.recruitments.delete_one({"id": rid})
        return {"ok": True}

    # ---------- CSV ----------
    @api.get("/recruitments/csv/template")
    async def recruitment_csv_template(_: dict = Depends(admin_tab_dep("recruitment"))):
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(RECRUITMENT_CSV_COLUMNS)
        w.writerow(RECRUITMENT_CSV_SAMPLE_ROW)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="recruitment_template.csv"'},
        )

    @api.get("/recruitments/csv/export")
    async def recruitment_csv_export(admin: dict = Depends(admin_tab_dep("recruitment"))):
        query: dict = {}
        if is_chapter_scoped(admin):
            ids = await chapter_scope_user_ids(admin)
            query["$or"] = [{"recruiter_id": {"$in": ids or []}}, {"recruit_id": {"$in": ids or []}}]
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["recruiter_name", "recruiter_email", "recruit_name", "recruit_email",
                    "chapter", "date_recruited", "notes", "created_by"])
        async for r in db.recruitments.find(query, {"_id": 0}).sort("date_recruited", -1):
            w.writerow([
                r.get("recruiter_name", ""),
                r.get("recruiter_email", ""),
                r.get("recruit_name", ""),
                r.get("recruit_email", ""),
                r.get("chapter_name", ""),
                (r.get("date_recruited", "") or "")[:10],
                r.get("notes", ""),
                r.get("created_by_name", ""),
            ])
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="recruitments.csv"'},
        )

    @api.post("/recruitments/csv")
    async def recruitment_csv_import(
        file: UploadFile = File(...),
        dry_run: bool = True,
        admin: dict = Depends(admin_tab_dep("recruitment")),
    ):
        """Bulk-import recruitment records. Row lookup order per side:
        email → full_name → first_name + last_name. Duplicate pair+date
        combinations are skipped as warnings (not errors)."""
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="CSV file is empty")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded")
        reader = _csv.DictReader(_io.StringIO(text))
        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV has no header row")
        headers_lower = {h.strip().lower() for h in reader.fieldnames if h}
        has_recruiter = any(c in headers_lower for c in _RECRUITER_EMAIL_COLS + _RECRUITER_FULL_COLS) or (
            any(c in headers_lower for c in _RECRUITER_FIRST_COLS) and any(c in headers_lower for c in _RECRUITER_LAST_COLS)
        )
        has_recruit = any(c in headers_lower for c in _RECRUIT_EMAIL_COLS + _RECRUIT_FULL_COLS) or (
            any(c in headers_lower for c in _RECRUIT_FIRST_COLS) and any(c in headers_lower for c in _RECRUIT_LAST_COLS)
        )
        if not has_recruiter:
            raise HTTPException(status_code=400, detail=(
                "CSV must identify the recruiter with 'recruiter_email', 'recruiter_full_name', "
                "or both 'recruiter_first_name' + 'recruiter_last_name'."
            ))
        if not has_recruit:
            raise HTTPException(status_code=400, detail=(
                "CSV must identify the recruit with 'recruit_email', 'recruit_full_name', "
                "or both 'recruit_first_name' + 'recruit_last_name'."
            ))
        if not any(c in headers_lower for c in ("date_recruited", "date", "recruited_at")):
            raise HTTPException(status_code=400, detail="Missing required column: date_recruited")

        rows_preview: list[dict] = []
        valid_writes: list[dict] = []
        for idx, raw_row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items() if k}
            recruiter_email = _cell(row, _RECRUITER_EMAIL_COLS)
            recruiter_full = _cell(row, _RECRUITER_FULL_COLS)
            recruiter_first = _cell(row, _RECRUITER_FIRST_COLS)
            recruiter_last = _cell(row, _RECRUITER_LAST_COLS)
            recruit_email = _cell(row, _RECRUIT_EMAIL_COLS)
            recruit_full = _cell(row, _RECRUIT_FULL_COLS)
            recruit_first = _cell(row, _RECRUIT_FIRST_COLS)
            recruit_last = _cell(row, _RECRUIT_LAST_COLS)
            date_raw = _cell(row, ("date_recruited", "date", "recruited_at"))
            notes = row.get("notes", "")

            row_out = {
                "row": idx,
                "recruiter": recruiter_email or recruiter_full or (f"{recruiter_first} {recruiter_last}".strip() or ""),
                "recruit": recruit_email or recruit_full or (f"{recruit_first} {recruit_last}".strip() or ""),
                "date": date_raw,
                "status": "READY",
                "errors": [],
                "warnings": [],
            }

            rec_user, rec_via, rec_label = await _lookup_member(
                db, email=recruiter_email, full_name=recruiter_full,
                first=recruiter_first, last=recruiter_last,
            )
            if rec_via == "missing":
                row_out["errors"].append("recruiter identifier is required")
            elif rec_via == "ambiguous":
                row_out["errors"].append(f"multiple members named '{rec_label}' — add recruiter_email to disambiguate")
            elif not rec_user:
                row_out["errors"].append(f"recruiter '{rec_label}' not found in members")

            new_user, new_via, new_label = await _lookup_member(
                db, email=recruit_email, full_name=recruit_full,
                first=recruit_first, last=recruit_last,
            )
            if new_via == "missing":
                row_out["errors"].append("recruit identifier is required")
            elif new_via == "ambiguous":
                row_out["errors"].append(f"multiple members named '{new_label}' — add recruit_email to disambiguate")
            elif not new_user:
                row_out["errors"].append(f"recruit '{new_label}' not found in members")

            if rec_user and new_user and rec_user["id"] == new_user["id"]:
                row_out["errors"].append("recruiter and recruit are the same member")

            dt = None
            try:
                dt = _parse_recruitment_date(date_raw)
            except ValueError as e:
                row_out["errors"].append(str(e))

            if row_out["errors"]:
                row_out["status"] = "ERROR"
                rows_preview.append(row_out)
                continue

            # Check for existing duplicate
            date_iso = iso(dt)
            already = await db.recruitments.find_one({
                "recruiter_id": rec_user["id"],
                "recruit_id": new_user["id"],
                "date_recruited": date_iso,
            })
            if already:
                row_out["status"] = "SKIP"
                row_out["warnings"].append("duplicate recruiter/recruit/date already recorded — skipped")
                rows_preview.append(row_out)
                continue

            chapter_id = rec_user.get("chapter_id")
            chapter_name = ""
            if chapter_id:
                c = await db.chapters.find_one({"id": chapter_id}, {"_id": 0, "name": 1})
                chapter_name = (c or {}).get("name") or ""

            valid_writes.append({
                "id": str(uuid.uuid4()),
                "recruiter_id": rec_user["id"],
                "recruiter_name": rec_user.get("name", ""),
                "recruiter_email": rec_user.get("email", ""),
                "recruit_id": new_user["id"],
                "recruit_name": new_user.get("name", ""),
                "recruit_email": new_user.get("email", ""),
                "chapter_id": chapter_id,
                "chapter_name": chapter_name,
                "date_recruited": date_iso,
                "notes": notes,
                "created_by": admin["id"],
                "created_by_name": admin.get("name", ""),
                "created_at": iso(now_utc()),
                "updated_at": iso(now_utc()),
            })
            rows_preview.append(row_out)

        created = 0
        failed = sum(1 for r in rows_preview if r["status"] == "ERROR")
        skipped = sum(1 for r in rows_preview if r["status"] == "SKIP")

        if not dry_run and valid_writes:
            await db.recruitments.insert_many(valid_writes)
            created = len(valid_writes)

        return {
            "ok": True,
            "dry_run": dry_run,
            "created": created,
            "failed": failed,
            "skipped": skipped,
            "total": len(rows_preview),
            "rows": rows_preview,
        }

    # ---------- Reports ----------
    def _period_range(year: str, period: str) -> tuple[Optional[str], Optional[str]]:
        """Compute (start_iso, end_iso) for a date_recruited filter. `year='all'`
        clears the year bound; `period='all'` covers the entire year."""
        if year == "all":
            return None, None
        try:
            y = int(year)
        except (TypeError, ValueError):
            return None, None
        if not period or period == "all":
            start = datetime(y, 1, 1)
            end = datetime(y + 1, 1, 1) - timedelta(seconds=1)
        elif period.startswith("q"):
            q = int(period[1])
            start_month = (q - 1) * 3 + 1
            start = datetime(y, start_month, 1)
            if start_month + 3 > 12:
                end = datetime(y + 1, 1, 1) - timedelta(seconds=1)
            else:
                end = datetime(y, start_month + 3, 1) - timedelta(seconds=1)
        elif period.startswith("m"):
            m = int(period[1:])
            start = datetime(y, m, 1)
            if m == 12:
                end = datetime(y + 1, 1, 1) - timedelta(seconds=1)
            else:
                end = datetime(y, m + 1, 1) - timedelta(seconds=1)
        else:
            start = datetime(y, 1, 1)
            end = datetime(y + 1, 1, 1) - timedelta(seconds=1)
        return start.isoformat() + "+00:00", end.isoformat() + "+00:00"

    def _base_match(year: str, period: str, chapter_id: str, scope_user_ids: Optional[list]) -> dict:
        m: dict = {}
        start_iso, end_iso = _period_range(year, period)
        if start_iso and end_iso:
            m["date_recruited"] = {"$gte": start_iso, "$lte": end_iso}
        if chapter_id:
            m["chapter_id"] = chapter_id
        if scope_user_ids is not None:
            m["$or"] = [
                {"recruiter_id": {"$in": scope_user_ids}},
                {"recruit_id": {"$in": scope_user_ids}},
            ]
        return m

    @api.get("/reports/recruitment")
    async def report_recruitment_entries(
        year: str = "all",
        period: str = "all",
        chapter_id: str = "",
        admin: dict = Depends(admin_tab_dep("reports")),
    ):
        scope_ids = await chapter_scope_user_ids(admin) if is_chapter_scoped(admin) else None
        match = _base_match(year, period, chapter_id, scope_ids)
        rows = await db.recruitments.find(match, {"_id": 0}).sort("date_recruited", -1).to_list(5000)
        return [_record_out(r) for r in rows]

    @api.get("/reports/recruitment/summary")
    async def report_recruitment_summary(
        year: str = "all",
        period: str = "all",
        chapter_id: str = "",
        group_by: str = "recruiter",  # recruiter | chapter | month
        admin: dict = Depends(admin_tab_dep("reports")),
    ):
        scope_ids = await chapter_scope_user_ids(admin) if is_chapter_scoped(admin) else None
        match = _base_match(year, period, chapter_id, scope_ids)

        # Totals
        total = await db.recruitments.count_documents(match)
        distinct_recruiters = len(await db.recruitments.distinct("recruiter_id", match))

        rows: list[dict] = []
        if group_by == "recruiter":
            pipe = [
                {"$match": match},
                {"$group": {
                    "_id": "$recruiter_id",
                    "name": {"$first": "$recruiter_name"},
                    "email": {"$first": "$recruiter_email"},
                    "chapter_id": {"$first": "$chapter_id"},
                    "chapter_name": {"$first": "$chapter_name"},
                    "count": {"$sum": 1},
                }},
                {"$sort": {"count": -1, "name": 1}},
            ]
            async for r in db.recruitments.aggregate(pipe):
                rows.append({
                    "user_id": r["_id"],
                    "user_name": r.get("name") or "Unknown",
                    "user_email": r.get("email") or "",
                    "chapter_id": r.get("chapter_id"),
                    "chapter_name": r.get("chapter_name") or "Unassigned",
                    "count": int(r.get("count") or 0),
                })
        elif group_by == "chapter":
            pipe = [
                {"$match": match},
                {"$group": {
                    "_id": "$chapter_id",
                    "chapter_name": {"$first": "$chapter_name"},
                    "count": {"$sum": 1},
                    "recruiters": {"$addToSet": "$recruiter_id"},
                }},
                {"$sort": {"count": -1}},
            ]
            async for r in db.recruitments.aggregate(pipe):
                rows.append({
                    "chapter_id": r["_id"],
                    "chapter_name": r.get("chapter_name") or "Unassigned",
                    "count": int(r.get("count") or 0),
                    "recruiter_count": len(r.get("recruiters") or []),
                })
        else:  # month
            pipe = [
                {"$match": match},
                {"$group": {
                    "_id": {"$substr": ["$date_recruited", 0, 7]},  # YYYY-MM
                    "count": {"$sum": 1},
                }},
                {"$sort": {"_id": 1}},
            ]
            async for r in db.recruitments.aggregate(pipe):
                rows.append({
                    "period_label": r["_id"],
                    "count": int(r.get("count") or 0),
                })

        return {
            "totals": {
                "total_recruits": total,
                "distinct_recruiters": distinct_recruiters,
            },
            "rows": rows,
        }

    # ---------- Homepage leaderboard ----------
    @api.get("/leaderboards/top-recruiters")
    async def leaderboard_top_recruiters(period: str = "quarter", user: dict = Depends(get_current_user)):
        """Top 5 recruiters + top 5 chapters by recruitment count.
        period ∈ {q1, q2, q3, q4, year}. Mirrors top-donors / community-service
        shape so the homepage widget can share styling."""
        now = now_utc()
        start_iso: Optional[str] = None
        end_iso: Optional[str] = None
        period_label = ""
        if period in ("q1", "q2", "q3", "q4"):
            q_idx = int(period[1]) - 1
            q_start_month = q_idx * 3 + 1
            q_start = now.replace(month=q_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
            if q_start_month + 2 == 12:
                next_start = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                next_start = now.replace(month=q_start_month + 3, day=1, hour=0, minute=0, second=0, microsecond=0)
            start_iso = iso(q_start)
            end_iso = iso(next_start - timedelta(seconds=1))
            period_label = f"Q{q_idx + 1} {now.year}"
        elif period == "year":
            start_iso = iso(now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0))
            end_iso = iso(now.replace(year=now.year + 1, month=1, day=1) - timedelta(seconds=1))
            period_label = str(now.year)
        else:
            # Default to current quarter
            q = (now.month - 1) // 3
            q_start_month = q * 3 + 1
            q_start = now.replace(month=q_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
            start_iso = iso(q_start)
            period_label = f"Q{q + 1} {now.year}"

        match: dict = {}
        if start_iso and end_iso:
            match["date_recruited"] = {"$gte": start_iso, "$lte": end_iso}
        elif start_iso:
            match["date_recruited"] = {"$gte": start_iso}

        # Top members (recruiters)
        member_pipe = [
            {"$match": match},
            {"$group": {"_id": "$recruiter_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        member_rows = []
        async for r in db.recruitments.aggregate(member_pipe):
            if r["_id"]:
                member_rows.append({"user_id": r["_id"], "count": int(r["count"] or 0)})
        uids = [r["user_id"] for r in member_rows]
        users: dict = {}
        if uids:
            async for u in db.users.find(
                {"id": {"$in": uids}},
                {"_id": 0, "id": 1, "name": 1, "avatar_url": 1, "chapter_id": 1},
            ):
                users[u["id"]] = u
        top_members = []
        for r in member_rows:
            u = users.get(r["user_id"]) or {}
            top_members.append({
                **r,
                "user_name": u.get("name", "Unknown"),
                "avatar_url": u.get("avatar_url"),
                "chapter_id": u.get("chapter_id"),
                "chapter_name": None,
            })

        # Top chapters
        chapter_pipe = [
            {"$match": match},
            {"$group": {"_id": "$chapter_id",
                        "chapter_name": {"$first": "$chapter_name"},
                        "count": {"$sum": 1},
                        "recruiters": {"$addToSet": "$recruiter_id"}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        chapter_rows = []
        async for r in db.recruitments.aggregate(chapter_pipe):
            chapter_rows.append({
                "chapter_id": r["_id"],
                "count": int(r.get("count") or 0),
                "chapter_name": r.get("chapter_name") or "Unassigned",
                "recruiter_count": len(r.get("recruiters") or []),
            })
        # Enrich w/ chapter logos + active member counts
        cids = [r["chapter_id"] for r in chapter_rows if r["chapter_id"]]
        chapters: dict = {}
        active_counts: dict = {}
        if cids:
            async for c in db.chapters.find({"id": {"$in": cids}}, {"_id": 0, "id": 1, "name": 1, "logo_url": 1}):
                chapters[c["id"]] = c
            async for row in db.users.aggregate([
                {"$match": {"chapter_id": {"$in": cids}, "status": {"$ne": "inactive"}}},
                {"$group": {"_id": "$chapter_id", "n": {"$sum": 1}}},
            ]):
                active_counts[row["_id"]] = row["n"]
        for cr in chapter_rows:
            cinfo = chapters.get(cr["chapter_id"]) or {}
            cr["logo_url"] = cinfo.get("logo_url") or None
            cr["member_count"] = int(active_counts.get(cr["chapter_id"], 0))
            # Prefer denormalized chapter_name unless empty then fall back to chapters lookup
            if not cr["chapter_name"] or cr["chapter_name"] == "Unassigned":
                cr["chapter_name"] = cinfo.get("name") or "Unassigned"

        # Backfill chapter_name on top_members
        if top_members:
            more_cids = [m["chapter_id"] for m in top_members if m.get("chapter_id") and m["chapter_id"] not in chapters]
            if more_cids:
                async for c in db.chapters.find({"id": {"$in": more_cids}}, {"_id": 0, "id": 1, "name": 1, "logo_url": 1}):
                    chapters[c["id"]] = c
            for m in top_members:
                m["chapter_name"] = (chapters.get(m.get("chapter_id") or "") or {}).get("name") or "Unassigned"

        return {
            "period": period,
            "period_label": period_label,
            "top_chapters": chapter_rows,
            "top_members": top_members,
        }
