"""Donations + Causes endpoints.

Extracted from server.py (Iter 60). Owns the full donation/cause surface:

  REST:
    GET    /causes
    GET    /causes/{cause_id}
    POST   /causes
    PUT    /causes/{cause_id}
    DELETE /causes/{cause_id}
    POST   /causes/{cause_id}/pledge
    GET    /causes/{cause_id}/donations
    GET    /donations/admin/csv/template
    POST   /donations/admin/csv
    GET    /leaderboards/top-donors

  Helpers re-exported for use elsewhere in server.py (e.g. the PayPal capture
  flow needs `recompute_cause_totals`):
    cause_out          — serializer
    recompute_cause_totals  — refreshes raised_amount / donor_count

The module is registered onto the `/api` router via `register(api, ...)` at
the bottom of server.py.
"""
import asyncio  # noqa: F401 — present so future async helpers can land here
import uuid
from typing import List, Literal, Optional

from fastapi import Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field


# Module-level references populated by `register(...)` — keeps the helpers
# (`recompute_cause_totals`, `cause_out`) callable from server.py while
# letting them share the same db/iso/now_utc the endpoints use.
_db = None  # type: ignore[assignment]
_iso = None  # type: ignore[assignment]
_now_utc = None  # type: ignore[assignment]


class CauseIn(BaseModel):
    title: str
    description: str = ""
    goal_amount: float = 0.0
    cover_image: str = ""
    is_active: bool = True
    deadline: Optional[str] = None
    category: str = "general"
    # Donation routing: paypal renders the in-app checkout; zeffy opens the
    # admin-supplied external Zeffy form in a new tab (admins reconcile via
    # the bulk-donations CSV importer).
    payment_processor: Literal["paypal", "zeffy"] = "paypal"
    zeffy_url: str = ""


class CauseUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    goal_amount: Optional[float] = None
    cover_image: Optional[str] = None
    is_active: Optional[bool] = None
    deadline: Optional[str] = None
    category: Optional[str] = None
    payment_processor: Optional[Literal["paypal", "zeffy"]] = None
    zeffy_url: Optional[str] = None


class PledgeIn(BaseModel):
    amount: float = Field(gt=0)
    anonymous: bool = False
    note: str = ""


def cause_out(c: dict) -> dict:
    return {
        "id": c["id"],
        "title": c["title"],
        "description": c.get("description", ""),
        "goal_amount": c.get("goal_amount", 0.0),
        "raised_amount": c.get("raised_amount", 0.0),
        "donor_count": c.get("donor_count", 0),
        "cover_image": c.get("cover_image", ""),
        "is_active": c.get("is_active", True),
        "deadline": c.get("deadline"),
        "category": c.get("category", "general"),
        "payment_processor": c.get("payment_processor", "paypal"),
        "zeffy_url": c.get("zeffy_url", ""),
        "created_at": c.get("created_at"),
    }


async def recompute_cause_totals(cause_id: str):
    """Sum completed donations against this cause."""
    agg = await _db.transactions.aggregate([
        {"$match": {"cause_id": cause_id, "status": "completed", "type": "donation"}},
        {"$group": {"_id": "$cause_id", "raised": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    raised = agg[0]["raised"] if agg else 0.0
    count = agg[0]["count"] if agg else 0
    await _db.causes.update_one({"id": cause_id}, {"$set": {"raised_amount": raised, "donor_count": count}})


DONATIONS_CSV_COLUMNS = ["member_email", "full_name", "first_name", "last_name", "amount", "cause", "date", "note", "anonymous", "method"]
DONATIONS_CSV_SAMPLE_ROW = ["member@clubhaven.app", "", "", "", "100.00", "Anniversary Fund", "2026-04-15", "10-year drive", "false", "manual_csv"]


def register(api, *, db, iso, now_utc, get_current_user, admin_tab_dep, is_chapter_scoped, chapter_scope_user_ids):
    """Mount donations endpoints + populate the module-level db/iso/now_utc
    references so the public helpers (`recompute_cause_totals`, `cause_out`)
    stay callable from server.py."""
    global _db, _iso, _now_utc
    _db = db
    _iso = iso
    _now_utc = now_utc

    # ---------- Causes CRUD ----------
    @api.get("/causes")
    async def list_causes(active_only: bool = False):
        q = {"is_active": True} if active_only else {}
        items = await db.causes.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
        return [cause_out(c) for c in items]

    @api.get("/causes/{cause_id}")
    async def get_cause(cause_id: str):
        c = await db.causes.find_one({"id": cause_id}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Cause not found")
        return cause_out(c)

    @api.post("/causes")
    async def create_cause(body: CauseIn, _: dict = Depends(admin_tab_dep("causes"))):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["raised_amount"] = 0.0
        doc["donor_count"] = 0
        doc["created_at"] = iso(now_utc())
        await db.causes.insert_one(doc)
        return cause_out(doc)

    @api.put("/causes/{cause_id}")
    async def update_cause(cause_id: str, body: CauseUpdateIn, _: dict = Depends(admin_tab_dep("causes"))):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.causes.update_one({"id": cause_id}, {"$set": updates})
        c = await db.causes.find_one({"id": cause_id}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Cause not found")
        return cause_out(c)

    @api.delete("/causes/{cause_id}")
    async def delete_cause(cause_id: str, _: dict = Depends(admin_tab_dep("causes"))):
        await db.causes.delete_one({"id": cause_id})
        return {"ok": True}

    @api.post("/causes/{cause_id}/pledge")
    async def pledge_donation(cause_id: str, body: PledgeIn, user: dict = Depends(get_current_user)):
        """Manual pledge submission — for the in-app non-PayPal path. PayPal
        capture writes its own transaction separately."""
        cause = await db.causes.find_one({"id": cause_id}, {"_id": 0})
        if not cause:
            raise HTTPException(status_code=404, detail="Cause not found")
        tx = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "user_name": "Anonymous" if body.anonymous else user.get("name", ""),
            "type": "donation",
            "amount": body.amount,
            "currency": "USD",
            "description": f"Donation to {cause['title']}" + (f": {body.note}" if body.note else ""),
            "status": "pending",
            "cause_id": cause_id,
            "anonymous": body.anonymous,
            "method": "pledge",
            "created_at": iso(now_utc()),
        }
        await db.transactions.insert_one(tx)
        return {"transaction_id": tx["id"], "status": "pending"}

    @api.get("/causes/{cause_id}/donations")
    async def cause_donations(cause_id: str, admin: dict = Depends(admin_tab_dep("causes"))):
        q = {"cause_id": cause_id, "type": "donation"}
        if is_chapter_scoped(admin):
            ids = await chapter_scope_user_ids(admin)
            q["user_id"] = {"$in": ids or []}
        items = await db.transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
        return items

    # ---------- Bulk CSV import ----------
    @api.get("/donations/admin/csv/template")
    async def donations_csv_template(_: dict = Depends(admin_tab_dep("causes"))):
        """Downloadable CSV template: header row + one realistic example row."""
        import csv as _csv
        import io as _io
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(DONATIONS_CSV_COLUMNS)
        w.writerow(DONATIONS_CSV_SAMPLE_ROW)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="donations_template.csv"'},
        )

    @api.post("/donations/admin/csv")
    async def donations_csv_import(
        file: UploadFile = File(...),
        dry_run: bool = True,
        admin: dict = Depends(admin_tab_dep("causes")),
    ):
        """Bulk-create donation transactions from a CSV.

        Columns: `member_email` (required), `amount` (required, > 0),
        `cause` (optional — blank, matched, OR free-text label preserved),
        `date` (optional, flexible parser; defaults to today), `note`,
        `anonymous` (true/false), `method` (free-text, defaults to `manual_csv`).

        `dry_run=true` returns a row-by-row preview (READY/ERROR) without
        writing anything. `dry_run=false` writes `db.transactions` records
        (status=completed, type=donation) and refreshes
        `causes.raised_amount`/`donor_count` for any touched cause.

        Returns `{ok, dry_run, created, failed, total, rows: [...preview...]}`.
        """
        import csv as _csv
        import io as _io
        from routes.hours import _parse_csv_date as _parse_csv_date_local
        from routes._csv_member_lookup import (
            MEMBER_LOOKUP_HEADER_HINT,
            member_lookup_columns_present,
            prefetch_member_lookup,
            resolve_member_for_row,
        )

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
        headers_lower = {h.strip().lower() for h in reader.fieldnames}
        if not member_lookup_columns_present(headers_lower):
            raise HTTPException(status_code=400, detail=MEMBER_LOOKUP_HEADER_HINT)
        if "amount" not in headers_lower:
            raise HTTPException(status_code=400, detail="Missing required column: amount")

        # Pre-cache cause lookup (case-insensitive on title)
        all_causes = await db.causes.find({}, {"_id": 0, "id": 1, "title": 1}).to_list(500)
        cause_by_title = {(c.get("title") or "").strip().lower(): c["id"] for c in all_causes}

        # Pre-cache member resolution for every row in one DB round-trip
        all_rows = list(reader)
        lookup_index = await prefetch_member_lookup(db, all_rows)

        rows_preview: list[dict] = []
        valid_writes: list[dict] = []
        causes_touched: set[str] = set()
        for idx, raw_row in enumerate(all_rows, start=2):  # row 2 = first data row (header is row 1)
            row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items() if k}
            amount_raw = row.get("amount", "")
            cause_title = row.get("cause", "").strip()
            date_raw = row.get("date", "")
            note = row.get("note", "")
            anonymous = row.get("anonymous", "").strip().lower() in ("true", "yes", "1", "y", "t")
            method = row.get("method", "").strip() or "manual_csv"

            res = resolve_member_for_row(raw_row, lookup_index)
            u = res.user

            row_out: dict = {
                "row": idx,
                "member_email": (u.get("email") if u else "") or res.label or row.get("member_email", "") or row.get("email", ""),
                "member_identifier": res.label,
                "amount_raw": amount_raw,
                "cause_title": cause_title,
                "status": "READY",
                "errors": [],
                "warnings": [],
            }

            if res.error:
                row_out["errors"].append(res.error)
            if not amount_raw:
                row_out["errors"].append("amount is required")
            try:
                amount = float(amount_raw)
                if amount <= 0:
                    row_out["errors"].append("amount must be > 0")
            except (TypeError, ValueError):
                row_out["errors"].append(f"amount '{amount_raw}' is not a number")
                amount = 0.0

            # Resolve cause — fully optional. Blank ⇒ unallocated; matched
            # ⇒ linked; unmatched ⇒ unallocated + warning + preserved label.
            resolved_cause_id: Optional[str] = None
            cause_label_for_desc = ""
            if cause_title:
                cid = cause_by_title.get(cause_title.lower())
                if cid:
                    resolved_cause_id = cid
                else:
                    cause_label_for_desc = cause_title
                    row_out["warnings"].append(f"cause '{cause_title}' not found — saved as unallocated")

            # Parse date
            dt = None
            if date_raw:
                try:
                    dt = _parse_csv_date_local(date_raw)
                except Exception as e:
                    row_out["errors"].append(f"date '{date_raw}': {e}")
            if dt is None and not row_out["errors"]:
                dt = now_utc()

            if row_out["errors"]:
                row_out["status"] = "ERROR"
            else:
                row_out["member_name"] = u.get("name", "") if u else ""
                row_out["amount"] = amount
                row_out["date_iso"] = iso(dt) if dt else None
                row_out["cause_id"] = resolved_cause_id
                row_out["matched_by"] = res.matched_by
                desc_parts = []
                if cause_label_for_desc:
                    desc_parts.append(f"Fund: {cause_label_for_desc}")
                if note:
                    desc_parts.append(note)
                desc_parts.append("(CSV import)")
                tx = {
                    "id": str(uuid.uuid4()),
                    "user_id": u["id"],
                    "user_name": "Anonymous" if anonymous else (u.get("name", "") or u.get("email", "") or res.label),
                    "type": "donation",
                    "amount": amount,
                    "currency": "USD",
                    "description": " · ".join(desc_parts),
                    "cause_label": cause_label_for_desc,
                    "status": "completed",
                    "cause_id": resolved_cause_id,
                    "anonymous": anonymous,
                    "method": method,
                    "imported_by": admin["id"],
                    "imported_by_name": admin.get("name", "Admin"),
                    "created_at": row_out["date_iso"] or iso(now_utc()),
                }
                valid_writes.append(tx)
                if resolved_cause_id:
                    causes_touched.add(resolved_cause_id)

            rows_preview.append(row_out)

        created = 0
        failed = sum(1 for r in rows_preview if r["status"] == "ERROR")

        if not dry_run and valid_writes:
            await db.transactions.insert_many(valid_writes)
            created = len(valid_writes)
            for cid in causes_touched:
                await recompute_cause_totals(cid)

        return {
            "ok": True,
            "dry_run": dry_run,
            "created": created,
            "failed": failed,
            "total": len(rows_preview),
            "rows": rows_preview,
        }

    # ---------- /leaderboards/top-donors ----------
    @api.get("/leaderboards/top-donors")
    async def leaderboard_top_donors(period: str = "quarter", user: dict = Depends(get_current_user)):
        """Top 5 chapters + top 5 members by completed donation $ for the period.
        Mirrors `/leaderboards/community-service` shape but reports dollars.
        period ∈ {quarter, month, year, all, q1, q2, q3, q4}.

        `q1`-`q4` are explicit named-quarter shortcuts used by the homepage
        period switcher; they bound the range on both ends so Q1 data
        doesn't leak into Q2 later in the year.
        """
        from datetime import timedelta as _td
        now = now_utc()
        start_iso: Optional[str] = None
        end_iso: Optional[str] = None
        if period in ("q1", "q2", "q3", "q4"):
            q_idx = int(period[1]) - 1
            q_start_month = q_idx * 3 + 1
            q_end_month = q_start_month + 2
            q_start = now.replace(month=q_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
            if q_end_month == 12:
                next_start = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                next_start = now.replace(month=q_end_month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            q_end = next_start - _td(seconds=1)
            start_iso = iso(q_start)
            end_iso = iso(q_end)
            period_label = f"Q{q_idx + 1} {now.year}"
        elif period == "quarter":
            q = (now.month - 1) // 3
            q_start = now.replace(month=q * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            start_iso = iso(q_start)
            period_label = f"Q{q + 1} {now.year}"
        elif period == "month":
            start_iso = iso(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
            period_label = now.strftime("%B %Y")
        elif period == "year":
            start_iso = iso(now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0))
            period_label = str(now.year)
        else:
            period = "all"
            period_label = "All time"

        match: dict = {"type": "donation", "status": "completed"}
        if start_iso and end_iso:
            match["created_at"] = {"$gte": start_iso, "$lte": end_iso}
        elif start_iso:
            match["created_at"] = {"$gte": start_iso}

        # ---- Top members (anonymous excluded for privacy) ----
        member_pipe = [
            {"$match": match},
            {"$match": {"anonymous": {"$ne": True}}},
            {"$group": {"_id": "$user_id", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
            {"$sort": {"total": -1}},
            {"$limit": 5},
        ]
        member_rows = []
        async for r in db.transactions.aggregate(member_pipe):
            if r["_id"]:
                member_rows.append({"user_id": r["_id"], "amount": float(r["total"] or 0), "count": int(r["count"] or 0)})
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

        # ---- Top chapters ----
        chapter_pipe = [
            {"$match": match},
            {"$lookup": {"from": "users", "localField": "user_id", "foreignField": "id", "as": "u"}},
            {"$addFields": {"chapter_id": {"$arrayElemAt": ["$u.chapter_id", 0]}}},
            {"$group": {"_id": "$chapter_id", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
            {"$sort": {"total": -1}},
            {"$limit": 5},
        ]
        chapter_rows = []
        async for r in db.transactions.aggregate(chapter_pipe):
            chapter_rows.append({"chapter_id": r["_id"], "amount": float(r["total"] or 0), "count": int(r["count"] or 0)})
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
        top_chapters = []
        for r in chapter_rows:
            c = chapters.get(r["chapter_id"]) or {}
            top_chapters.append({
                **r,
                "chapter_name": c.get("name") or "Unassigned",
                "logo_url": c.get("logo_url") or None,
                "member_count": int(active_counts.get(r["chapter_id"], 0)),
            })
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
            "top_chapters": top_chapters,
            "top_members": top_members,
        }
