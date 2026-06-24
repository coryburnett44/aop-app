"""Admin reports + Personnel Brief (JSON + PDF) routes.

Extracted from server.py. Owns:
  - GET /reports/members              (full directory with check-ins + guests enrichment)
  - GET /reports/rsvps                (rsvp report per event / parent event)
  - GET /reports/hours                (filterable hours queue for the reports tab)
  - GET /reports/hours/summary        (aggregated hours by member/chapter/period)
  - GET /reports/donations            (donation transactions list)
  - GET /reports/personnel-brief/{user_id}     (json)
  - GET /reports/personnel-brief/{user_id}/pdf (PDF download)

Plus the two large helpers `_personnel_brief_data` and `_personnel_brief_pdf_response`
which the /me/personnel-brief* member-side endpoints in server.py still call via
the back-compat shim wired by register().

All cross-cutting helpers (public_user, hours_out, tier_out, chapter_out,
is_chapter_scoped, chapter_scope_user_ids, period_to_range, iso, now_utc,
get_object, logger) are injected via register kwargs to keep this module
import-clean and avoid circular imports.
"""
from calendar import monthrange
from datetime import datetime as _dt
from typing import Optional
from io import BytesIO
import urllib.request

from fastapi import Depends, HTTPException, Response

# Category-key → human label map for "Of The Year" honors. Imported from the
# of_the_year module so both Personnel Brief and the OTY admin views stay in
# lockstep when categories evolve.
from routes.of_the_year import CATEGORY_LABELS as OTY_CATEGORY_LABELS


def register(
    api,
    *,
    db,
    admin_tab_dep,
    get_current_user,
    public_user,
    hours_out,
    tier_out,
    chapter_out,
    is_chapter_scoped,
    chapter_scope_user_ids,
    period_to_range,
    get_object,
    iso,
    now_utc,
    logger,
):

    # ---------- /reports/members ----------
    @api.get("/reports/members")
    async def report_members(
        status_filter: Optional[str] = None,
        chapter_id: Optional[str] = None,
        tier_id: Optional[str] = None,
        role: Optional[str] = None,
        admin: dict = Depends(admin_tab_dep("reports")),
    ):
        q: dict = {}
        if chapter_id:
            q["chapter_id"] = chapter_id
        if tier_id:
            q["tier_id"] = tier_id
        if role:
            q["role"] = role
        if is_chapter_scoped(admin):
            q["chapter_id"] = admin.get("chapter_id") or "__none__"
        cursor = db.users.find(q, {"_id": 0, "password_hash": 0}).sort("created_at", -1)
        users = await cursor.to_list(2000)
        out = [public_user(u) for u in users]
        if status_filter:
            out = [u for u in out if u.get("status") == status_filter]
        for u in out:
            cks = await db.checkins.find({"user_id": u["id"]}, {"_id": 0, "event_id": 1, "event_title": 1, "ticket_type": 1, "checked_in_at": 1}).to_list(500)
            u["events_attended_count"] = len(cks)
            u["events_attended"] = [
                {"event_id": c["event_id"], "title": c.get("event_title", ""), "ticket_type": c.get("ticket_type"), "checked_in_at": c.get("checked_in_at")}
                for c in cks
            ]
            rsvps = await db.rsvps.find({"user_id": u["id"]}, {"_id": 0, "event_id": 1, "guests": 1}).to_list(500)
            all_guests = []
            for r in rsvps:
                for g in (r.get("guests") or []):
                    all_guests.append({"event_id": r["event_id"], "name": g.get("name", ""), "email": g.get("email", ""), "phone": g.get("phone", "")})
            u["guests_registered_count"] = len(all_guests)
            u["guests_registered"] = all_guests
        return out

    # ---------- /reports/rsvps ----------
    @api.get("/reports/rsvps")
    async def report_rsvps(
        event_id: Optional[str] = None,
        parent_event_id: Optional[str] = None,
        admin: dict = Depends(admin_tab_dep("reports")),
    ):
        event_q: dict = {}
        if event_id:
            event_q["id"] = event_id
        elif parent_event_id:
            event_q["$or"] = [{"id": parent_event_id}, {"parent_event_id": parent_event_id}]
        events_for_filter = []
        if event_q:
            events_for_filter = await db.events.find(event_q, {"_id": 0, "id": 1, "title": 1, "start_at": 1}).to_list(200)
            event_ids = [e["id"] for e in events_for_filter]
            if not event_ids:
                return []
            rsvp_q: dict = {"event_id": {"$in": event_ids}}
        else:
            rsvp_q = {}
        if is_chapter_scoped(admin):
            chapter_uids = await chapter_scope_user_ids(admin) or []
            rsvp_q["user_id"] = {"$in": chapter_uids}
        cursor = db.rsvps.find(rsvp_q, {"_id": 0}).sort("created_at", -1).limit(5000)
        rsvps = await cursor.to_list(5000)
        if not events_for_filter:
            all_event_ids = list({r["event_id"] for r in rsvps})
            events_for_filter = await db.events.find({"id": {"$in": all_event_ids}}, {"_id": 0, "id": 1, "title": 1, "start_at": 1}).to_list(2000)
        event_by_id = {e["id"]: e for e in events_for_filter}
        rows = []
        for r in rsvps:
            ev = event_by_id.get(r["event_id"], {})
            ck = await db.checkins.find_one({"event_id": r["event_id"], "user_id": r["user_id"]}, {"_id": 0, "ticket_type": 1, "checked_in_at": 1})
            rows.append({
                "rsvp_id": r["id"],
                "event_id": r["event_id"],
                "event_title": ev.get("title", ""),
                "event_start_at": ev.get("start_at"),
                "user_id": r["user_id"],
                "user_name": r.get("user_name", ""),
                "rsvped_at": r.get("created_at"),
                "guests": r.get("guests", []) or [],
                "guest_count": len(r.get("guests", []) or []),
                "ticket_type": (ck or {}).get("ticket_type"),
                "checked_in_at": (ck or {}).get("checked_in_at"),
            })
        return rows

    # ---------- /reports/hours ----------
    @api.get("/reports/hours")
    async def report_hours(
        status_filter: Optional[str] = None,
        user_id: Optional[str] = None,
        chapter_id: Optional[str] = None,
        event_type: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        year: Optional[int] = None,
        quarter: Optional[int] = None,
        month: Optional[int] = None,
        admin: dict = Depends(admin_tab_dep("reports")),
    ):
        q: dict = {}
        if status_filter:
            q["status"] = status_filter
        if user_id:
            q["user_id"] = user_id
        if event_type:
            q["event_type"] = event_type
        if chapter_id:
            chapter_user_ids = [u["id"] async for u in db.users.find({"chapter_id": chapter_id}, {"id": 1, "_id": 0})]
            q["user_id"] = {"$in": chapter_user_ids or [None]}
        period_from, period_to = period_to_range(year, quarter, month)
        eff_from = from_date or period_from
        eff_to = to_date or period_to
        if eff_from or eff_to:
            q["date"] = {}
            if eff_from:
                q["date"]["$gte"] = eff_from
            if eff_to:
                q["date"]["$lte"] = eff_to
        if is_chapter_scoped(admin):
            scope_ids = await chapter_scope_user_ids(admin)
            if "user_id" in q and isinstance(q["user_id"], dict):
                current = set(q["user_id"].get("$in", []))
                q["user_id"] = {"$in": list(current & set(scope_ids or []))}
            else:
                q["user_id"] = {"$in": scope_ids or []}
        cursor = db.volunteer_hours.find(q, {"_id": 0}).sort("date", -1).limit(2000)
        items = await cursor.to_list(2000)
        return [hours_out(h) for h in items]

    # ---------- /reports/hours/summary ----------
    @api.get("/reports/hours/summary")
    async def report_hours_summary(
        year: Optional[int] = None,
        quarter: Optional[int] = None,
        month: Optional[int] = None,
        chapter_id: Optional[str] = None,
        event_type: Optional[str] = None,
        group_by: str = "member",
        admin: dict = Depends(admin_tab_dep("reports")),
    ):
        period_from, period_to = period_to_range(year, quarter, month)
        q: dict = {"status": "approved"}
        if event_type:
            q["event_type"] = event_type
        if period_from:
            q["date"] = {"$gte": period_from, "$lte": period_to}
        user_filter_ids = None
        if chapter_id:
            user_filter_ids = [u["id"] async for u in db.users.find({"chapter_id": chapter_id}, {"id": 1, "_id": 0})]
            q["user_id"] = {"$in": user_filter_ids or [None]}
        if is_chapter_scoped(admin):
            scope_ids = await chapter_scope_user_ids(admin)
            if user_filter_ids is not None:
                q["user_id"] = {"$in": list(set(user_filter_ids) & set(scope_ids or []))}
            else:
                q["user_id"] = {"$in": scope_ids or []}
        raw_items = await db.volunteer_hours.find(q, {"_id": 0}).to_list(10000)
        totals_q: dict = {}
        if period_from:
            totals_q["date"] = {"$gte": period_from, "$lte": period_to}
        if "user_id" in q:
            totals_q["user_id"] = q["user_id"]
        if event_type:
            totals_q["event_type"] = event_type
        totals_items = await db.volunteer_hours.find(totals_q, {"_id": 0}).to_list(20000)
        totals = {
            "approved_hours": sum(h.get("hours", 0) for h in totals_items if h.get("status") == "approved"),
            "pending_hours": sum(h.get("hours", 0) for h in totals_items if h.get("status") == "pending"),
            "rejected_hours": sum(h.get("hours", 0) for h in totals_items if h.get("status") == "rejected"),
            "approved_count": sum(1 for h in totals_items if h.get("status") == "approved"),
            "pending_count": sum(1 for h in totals_items if h.get("status") == "pending"),
            "rejected_count": sum(1 for h in totals_items if h.get("status") == "rejected"),
        }
        rows: list = []
        if group_by == "member":
            groups: dict = {}
            for h in raw_items:
                uid = h["user_id"]
                groups.setdefault(uid, {"hours": 0.0, "count": 0, "user_name": h.get("user_name", "")})
                groups[uid]["hours"] += h.get("hours", 0)
                groups[uid]["count"] += 1
            uids = list(groups.keys())
            user_docs = await db.users.find({"id": {"$in": uids}}, {"id": 1, "chapter_id": 1, "name": 1, "_id": 0}).to_list(len(uids))
            users_by_id = {u["id"]: u for u in user_docs}
            chap_ids = list({u.get("chapter_id") for u in user_docs if u.get("chapter_id")})
            chap_docs = await db.chapters.find({"id": {"$in": chap_ids}}, {"id": 1, "name": 1, "_id": 0}).to_list(len(chap_ids)) if chap_ids else []
            chaps_by_id = {c["id"]: c for c in chap_docs}
            for uid, g in groups.items():
                udoc = users_by_id.get(uid, {})
                cid = udoc.get("chapter_id")
                rows.append({
                    "user_id": uid,
                    "user_name": udoc.get("name") or g["user_name"],
                    "chapter_id": cid,
                    "chapter_name": chaps_by_id.get(cid, {}).get("name", "") if cid else "",
                    "hours": round(g["hours"], 2),
                    "count": g["count"],
                })
            rows.sort(key=lambda r: r["hours"], reverse=True)
        elif group_by == "chapter":
            uids = list({h["user_id"] for h in raw_items})
            user_docs = await db.users.find({"id": {"$in": uids}}, {"id": 1, "chapter_id": 1, "_id": 0}).to_list(len(uids))
            uid_to_chap = {u["id"]: u.get("chapter_id") for u in user_docs}
            groups2: dict = {}
            for h in raw_items:
                cid = uid_to_chap.get(h["user_id"]) or "unassigned"
                groups2.setdefault(cid, {"hours": 0.0, "count": 0, "members": set()})
                groups2[cid]["hours"] += h.get("hours", 0)
                groups2[cid]["count"] += 1
                groups2[cid]["members"].add(h["user_id"])
            chap_ids = [cid for cid in groups2.keys() if cid and cid != "unassigned"]
            chap_docs = await db.chapters.find({"id": {"$in": chap_ids}}, {"id": 1, "name": 1, "_id": 0}).to_list(len(chap_ids)) if chap_ids else []
            chaps_by_id = {c["id"]: c for c in chap_docs}
            for cid, g in groups2.items():
                rows.append({
                    "chapter_id": cid if cid != "unassigned" else None,
                    "chapter_name": chaps_by_id.get(cid, {}).get("name", "") if cid != "unassigned" else "Unassigned",
                    "hours": round(g["hours"], 2),
                    "count": g["count"],
                    "member_count": len(g["members"]),
                })
            rows.sort(key=lambda r: r["hours"], reverse=True)
        elif group_by == "overall":
            total = sum(h.get("hours", 0) for h in raw_items)
            rows.append({"label": "All hours", "hours": round(total, 2), "count": len(raw_items)})
        else:
            buckets: dict = {}
            for h in raw_items:
                ds = (h.get("date") or "")[:10]
                try:
                    dt = _dt.fromisoformat(ds.replace("Z", ""))
                except Exception:
                    continue
                if group_by == "month":
                    key = f"{dt.year:04d}-{dt.month:02d}"
                    label = dt.strftime("%b %Y")
                elif group_by == "quarter":
                    qn = (dt.month - 1) // 3 + 1
                    key = f"{dt.year:04d}-Q{qn}"
                    label = key
                else:
                    key = f"{dt.year:04d}"
                    label = key
                buckets.setdefault(key, {"label": label, "hours": 0.0, "count": 0})
                buckets[key]["hours"] += h.get("hours", 0)
                buckets[key]["count"] += 1
            rows = [
                {"period_label": v["label"], "period_key": k, "hours": round(v["hours"], 2), "count": v["count"]}
                for k, v in sorted(buckets.items())
            ]
        return {"totals": totals, "rows": rows, "period": {"year": year, "quarter": quarter, "month": month, "from": period_from, "to": period_to}, "group_by": group_by}

    # ---------- /reports/donations ----------
    @api.get("/reports/donations")
    async def report_donations(
        cause_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        user_id: Optional[str] = None,
        chapter_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        year: Optional[int] = None,
        quarter: Optional[int] = None,
        month: Optional[int] = None,
        admin: dict = Depends(admin_tab_dep("reports")),
    ):
        """Donations report — same filter set as `/reports/hours`:
        cause_id, status, user_id, chapter_id, from_date/to_date, year/quarter/month.
        Date filtering is applied against `created_at` (transactions don't have a
        separate `date` field). Returns the raw transactions (still serialized
        without `_id`) so the admin UI keeps the existing column shape.
        """
        q: dict = {"type": "donation"}
        if cause_id:
            q["cause_id"] = cause_id
        if status_filter:
            q["status"] = status_filter
        if user_id:
            q["user_id"] = user_id
        if chapter_id:
            chapter_user_ids = [u["id"] async for u in db.users.find({"chapter_id": chapter_id}, {"id": 1, "_id": 0})]
            # Intersect with any explicit user_id filter so both narrow together
            if "user_id" in q and not isinstance(q["user_id"], dict):
                q["user_id"] = q["user_id"] if q["user_id"] in chapter_user_ids else "__no_match__"
            else:
                q["user_id"] = {"$in": chapter_user_ids or [None]}
        period_from, period_to = period_to_range(year, quarter, month)
        eff_from = from_date or period_from
        eff_to = to_date or period_to
        if eff_from or eff_to:
            q["created_at"] = {}
            if eff_from:
                q["created_at"]["$gte"] = eff_from
            if eff_to:
                # period_to_range returns end-of-day; for from_date/to_date the
                # admin passes a YYYY-MM-DD that we widen to end-of-day so the
                # whole day is included.
                q["created_at"]["$lte"] = eff_to if "T" in eff_to else f"{eff_to}T23:59:59"
        if is_chapter_scoped(admin):
            scope_ids = await chapter_scope_user_ids(admin)
            if "user_id" in q and isinstance(q["user_id"], dict):
                current = set(q["user_id"].get("$in", []))
                q["user_id"] = {"$in": list(current & set(scope_ids or []))}
            else:
                q["user_id"] = {"$in": scope_ids or []}
        items = await db.transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
        return items

    # ---------- /reports/donations/summary ----------
    @api.get("/reports/donations/summary")
    async def report_donations_summary(
        year: Optional[int] = None,
        quarter: Optional[int] = None,
        month: Optional[int] = None,
        chapter_id: Optional[str] = None,
        cause_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        group_by: str = "member",
        admin: dict = Depends(admin_tab_dep("reports")),
    ):
        """Aggregated donations report — mirrors `/reports/hours/summary` but
        sums `amount` instead of `hours`. Returns:
          - `totals`: completed / pending / refunded $ + count buckets
          - `rows`: rows grouped by member, chapter, or month/quarter/year
          - `period`: the date window in effect
        """
        period_from, period_to = period_to_range(year, quarter, month)
        # Status filter applies to the listed rows, NOT to the totals block —
        # we want the totals to surface every donation bucket regardless of
        # which status the admin happens to be focused on right now.
        base_q: dict = {"type": "donation"}
        if cause_id:
            base_q["cause_id"] = cause_id
        if period_from:
            base_q["created_at"] = {
                "$gte": period_from,
                "$lte": period_to if "T" in period_to else f"{period_to}T23:59:59",
            }
        user_filter_ids = None
        if chapter_id:
            user_filter_ids = [u["id"] async for u in db.users.find({"chapter_id": chapter_id}, {"id": 1, "_id": 0})]
            base_q["user_id"] = {"$in": user_filter_ids or [None]}
        if is_chapter_scoped(admin):
            scope_ids = await chapter_scope_user_ids(admin)
            if user_filter_ids is not None:
                base_q["user_id"] = {"$in": list(set(user_filter_ids) & set(scope_ids or []))}
            else:
                base_q["user_id"] = {"$in": scope_ids or []}

        totals_items = await db.transactions.find(base_q, {"_id": 0}).to_list(20000)
        totals = {
            "completed_amount": round(sum(t.get("amount", 0) for t in totals_items if t.get("status") == "completed"), 2),
            "pending_amount": round(sum(t.get("amount", 0) for t in totals_items if t.get("status") == "pending"), 2),
            "refunded_amount": round(sum(t.get("amount", 0) for t in totals_items if t.get("status") == "refunded"), 2),
            "completed_count": sum(1 for t in totals_items if t.get("status") == "completed"),
            "pending_count": sum(1 for t in totals_items if t.get("status") == "pending"),
            "refunded_count": sum(1 for t in totals_items if t.get("status") == "refunded"),
            "donor_count": len({t.get("user_id") for t in totals_items if t.get("status") == "completed" and t.get("user_id")}),
        }

        # For grouped rows we default to status=completed unless the admin
        # explicitly asks for a different status (e.g. drill into pending).
        rows_q = {**base_q, "status": status_filter or "completed"}
        raw_items = await db.transactions.find(rows_q, {"_id": 0}).to_list(10000)
        rows: list = []
        if group_by == "member":
            groups: dict = {}
            for t in raw_items:
                uid = t.get("user_id")
                if not uid:
                    continue
                groups.setdefault(uid, {"amount": 0.0, "count": 0, "user_name": t.get("user_name", "")})
                groups[uid]["amount"] += t.get("amount", 0)
                groups[uid]["count"] += 1
            uids = list(groups.keys())
            user_docs = await db.users.find({"id": {"$in": uids}}, {"id": 1, "chapter_id": 1, "name": 1, "_id": 0}).to_list(len(uids)) if uids else []
            users_by_id = {u["id"]: u for u in user_docs}
            chap_ids = list({u.get("chapter_id") for u in user_docs if u.get("chapter_id")})
            chap_docs = await db.chapters.find({"id": {"$in": chap_ids}}, {"id": 1, "name": 1, "_id": 0}).to_list(len(chap_ids)) if chap_ids else []
            chaps_by_id = {c["id"]: c for c in chap_docs}
            for uid, g in groups.items():
                udoc = users_by_id.get(uid, {})
                cid = udoc.get("chapter_id")
                rows.append({
                    "user_id": uid,
                    "user_name": udoc.get("name") or g["user_name"] or "Anonymous",
                    "chapter_id": cid,
                    "chapter_name": chaps_by_id.get(cid, {}).get("name", "") if cid else "",
                    "amount": round(g["amount"], 2),
                    "count": g["count"],
                })
            rows.sort(key=lambda r: r["amount"], reverse=True)
        elif group_by == "chapter":
            uids = list({t.get("user_id") for t in raw_items if t.get("user_id")})
            user_docs = await db.users.find({"id": {"$in": uids}}, {"id": 1, "chapter_id": 1, "_id": 0}).to_list(len(uids)) if uids else []
            uid_to_chap = {u["id"]: u.get("chapter_id") for u in user_docs}
            groups2: dict = {}
            for t in raw_items:
                cid = uid_to_chap.get(t.get("user_id")) or "unassigned"
                groups2.setdefault(cid, {"amount": 0.0, "count": 0, "members": set()})
                groups2[cid]["amount"] += t.get("amount", 0)
                groups2[cid]["count"] += 1
                if t.get("user_id"):
                    groups2[cid]["members"].add(t["user_id"])
            chap_ids = [cid for cid in groups2.keys() if cid and cid != "unassigned"]
            chap_docs = await db.chapters.find({"id": {"$in": chap_ids}}, {"id": 1, "name": 1, "_id": 0}).to_list(len(chap_ids)) if chap_ids else []
            chaps_by_id = {c["id"]: c for c in chap_docs}
            for cid, g in groups2.items():
                rows.append({
                    "chapter_id": cid if cid != "unassigned" else None,
                    "chapter_name": chaps_by_id.get(cid, {}).get("name", "") if cid != "unassigned" else "Unassigned",
                    "amount": round(g["amount"], 2),
                    "count": g["count"],
                    "member_count": len(g["members"]),
                })
            rows.sort(key=lambda r: r["amount"], reverse=True)
        else:
            # group_by="month" (default for time-bucket view)
            buckets: dict = {}
            for t in raw_items:
                ds = (t.get("created_at") or "")[:10]
                try:
                    dt = _dt.fromisoformat(ds.replace("Z", ""))
                except Exception:
                    continue
                if group_by == "quarter":
                    qn = (dt.month - 1) // 3 + 1
                    key = f"{dt.year:04d}-Q{qn}"
                    label = key
                elif group_by == "year":
                    key = f"{dt.year:04d}"
                    label = key
                else:
                    key = f"{dt.year:04d}-{dt.month:02d}"
                    label = dt.strftime("%b %Y")
                buckets.setdefault(key, {"label": label, "amount": 0.0, "count": 0})
                buckets[key]["amount"] += t.get("amount", 0)
                buckets[key]["count"] += 1
            rows = [
                {"period_label": v["label"], "period_key": k, "amount": round(v["amount"], 2), "count": v["count"]}
                for k, v in sorted(buckets.items())
            ]
        return {"totals": totals, "rows": rows, "period": {"year": year, "quarter": quarter, "month": month, "from": period_from, "to": period_to}, "group_by": group_by}

    # ---------- Personnel Brief data helper ----------
    async def personnel_brief_data(user_id: str) -> dict:
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        member = public_user(u)
        chapter = None
        if u.get("chapter_id"):
            cdoc = await db.chapters.find_one({"id": u["chapter_id"]}, {"_id": 0})
            chapter = chapter_out(cdoc) if cdoc else None
        tier = None
        if u.get("tier_id"):
            tdoc = await db.tiers.find_one({"id": u["tier_id"]}, {"_id": 0})
            tier = tier_out(tdoc) if tdoc else None
        grants = await db.award_grants.find({"user_id": user_id}, {"_id": 0}).sort([("award_name", 1), ("granted_at", 1)]).to_list(200)
        counts: dict = {}
        grouped_by_id: dict = {}
        for g in grants:
            aid = g["award_id"]
            counts[aid] = counts.get(aid, 0) + 1
            if not g.get("ordinal"):
                g["ordinal"] = counts[aid]
            if aid not in grouped_by_id:
                grouped_by_id[aid] = {
                    "award_id": aid,
                    "award_name": g.get("award_name"),
                    "award_icon": g.get("award_icon"),
                    "award_color": g.get("award_color"),
                    "first_granted_at": g.get("granted_at"),
                    "last_granted_at": g.get("granted_at"),
                    "count": 1,
                    "grants": [g],
                }
            else:
                grouped_by_id[aid]["count"] += 1
                grouped_by_id[aid]["last_granted_at"] = g.get("granted_at")
                grouped_by_id[aid]["grants"].append(g)
        for g in grants:
            g["award_count"] = counts.get(g["award_id"], 1)
        grants.sort(key=lambda x: x.get("granted_at", ""), reverse=True)
        awards_grouped = sorted(grouped_by_id.values(), key=lambda x: (x.get("last_granted_at") or ""), reverse=True)

        hours_items = await db.volunteer_hours.find({"user_id": user_id}, {"_id": 0}).sort("date", -1).to_list(500)
        hours_clean = [hours_out(h) for h in hours_items]
        approved_hours = sum(h["hours"] for h in hours_clean if h["status"] == "approved")
        pending_hours = sum(h["hours"] for h in hours_clean if h["status"] == "pending")

        rsvps = await db.rsvps.find({"user_id": user_id}, {"_id": 0}).to_list(500)
        event_ids = [r.get("event_id") for r in rsvps if r.get("event_id")]
        events_attended = []
        if event_ids:
            events_attended = await db.events.find({"id": {"$in": event_ids}}, {"_id": 0}).sort("start_at", -1).to_list(500)
        checkins = await db.checkins.find({"user_id": user_id}, {"_id": 0}).sort("checked_in_at", -1).to_list(500)
        txs = await db.transactions.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
        total_paid = sum(t.get("amount", 0.0) for t in txs if t.get("status") == "completed" and t.get("type") in ("renewal", "donation", "fee", "gear"))

        # "Of The Year" honors earned by this member. We pull every win so the
        # admin Member Card can show the full history; the Personnel Brief PDF
        # only renders the most recent 7 per the product requirement.
        # Chapter names are denormalized on the OTY doc at write time, but for
        # legacy rows that only carry chapter_id we fall back to a one-shot
        # lookup so the PDF/table never shows a bare "—".
        oty_rows = await db.of_the_year_awards.find(
            {"user_id": user_id}, {"_id": 0},
        ).sort([("year", -1), ("category", 1)]).to_list(500)
        missing_chap_ids = [r["chapter_id"] for r in oty_rows if r.get("chapter_id") and not r.get("chapter_name")]
        chap_name_by_id: dict = {}
        if missing_chap_ids:
            async for c in db.chapters.find(
                {"id": {"$in": list(set(missing_chap_ids))}},
                {"_id": 0, "id": 1, "name": 1},
            ):
                chap_name_by_id[c["id"]] = c.get("name", "")
        oty_all = [
            {
                "id": r.get("id"),
                "year": r.get("year"),
                "category": r.get("category"),
                "category_label": OTY_CATEGORY_LABELS.get(r.get("category", ""), r.get("category", "")),
                "chapter_id": r.get("chapter_id"),
                "chapter_name": r.get("chapter_name") or chap_name_by_id.get(r.get("chapter_id", ""), ""),
                "note": r.get("note") or "",
            }
            for r in oty_rows
        ]
        return {
            "member": member,
            "chapter": chapter,
            "tier": tier,
            "awards": grants,
            "awards_grouped": awards_grouped,
            "awards_count": len(grants),
            "awards_distinct_count": len(awards_grouped),
            "of_the_year": oty_all,
            "of_the_year_recent": oty_all[:7],
            "of_the_year_count": len(oty_all),
            "hours": hours_clean,
            "approved_hours": approved_hours,
            "pending_hours": pending_hours,
            "events": events_attended,
            "events_count": len(events_attended),
            "checkins": checkins,
            "rsvps": rsvps,
            "transactions": txs,
            "total_paid": total_paid,
            "generated_at": iso(now_utc()),
        }

    @api.get("/reports/personnel-brief/{user_id}")
    async def personnel_brief(user_id: str, _: dict = Depends(admin_tab_dep("reports"))):
        return await personnel_brief_data(user_id)

    @api.get("/reports/personnel-brief/{user_id}/pdf")
    async def personnel_brief_pdf(user_id: str, _: dict = Depends(admin_tab_dep("reports"))):
        return await personnel_brief_pdf_response(user_id)

    # ---------- Personnel Brief PDF builder ----------
    async def personnel_brief_pdf_response(user_id: str):
        """Build and stream the personnel-brief PDF for the given user id."""
        data = await personnel_brief_data(user_id)
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.55 * inch, rightMargin=0.55 * inch, topMargin=0.55 * inch, bottomMargin=0.5 * inch, title=f"Personnel Brief — {data['member']['name']}")
        styles = getSampleStyleSheet()
        AOP_NAVY = colors.HexColor("#0C1B33")
        h_name = ParagraphStyle("AopName", parent=styles["Heading1"], textColor=AOP_NAVY, fontSize=22, leading=24, spaceAfter=2)
        section = ParagraphStyle("AopSec", parent=styles["Heading2"], textColor=colors.white, backColor=AOP_NAVY, fontSize=12, leading=18, leftIndent=8, rightIndent=8, spaceBefore=12, spaceAfter=6, borderPadding=4)
        body_style = ParagraphStyle("AopBody", parent=styles["BodyText"], fontSize=10, leading=13)
        small = ParagraphStyle("AopSmall", parent=styles["BodyText"], fontSize=8, leading=11, textColor=colors.HexColor("#888888"))

        m = data["member"]
        chapter = data.get("chapter") or {}
        tier = data.get("tier") or {}
        elements: list = []
        current_year = now_utc().year

        avatar_bytes = None
        avatar_src = (m.get("avatar_url") or "").strip()

        def _normalize_image_bytes(raw):
            try:
                from PIL import Image as PILImage
                im = PILImage.open(BytesIO(raw))
                im.load()
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
                out = BytesIO()
                im.save(out, format="PNG")
                out.seek(0)
                return out
            except Exception as ex:
                logger.warning(f"[brief] avatar normalization failed: {ex}")
                return None

        if avatar_src.startswith("/api/files/"):
            try:
                storage_path = avatar_src.split("/api/files/", 1)[1]
                raw, _ct = get_object(storage_path)
                avatar_bytes = _normalize_image_bytes(raw)
            except Exception as ex:
                logger.warning(f"[brief] could not read avatar from storage {avatar_src}: {ex}")
        elif avatar_src.startswith("http"):
            try:
                req = urllib.request.Request(avatar_src, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AlphaOmegaPhi-Brief/1.0)",
                    "Accept": "image/*,*/*;q=0.8",
                })
                with urllib.request.urlopen(req, timeout=6) as r:
                    raw = r.read()
                avatar_bytes = _normalize_image_bytes(raw)
            except Exception as ex:
                logger.warning(f"[brief] avatar fetch failed for {avatar_src}: {ex}")

        photo_cell = ""
        if avatar_bytes:
            try:
                photo_cell = Image(avatar_bytes, width=1.2 * inch, height=1.2 * inch, kind="proportional")
            except Exception as ex:
                logger.warning(f"[brief] avatar render failed: {ex}")
                photo_cell = ""

        title_name = " ".join(p for p in [m.get("title"), m.get("name")] if p) or m.get("name", "—")
        identity_bits = []
        identity_bits.append(Paragraph(f"<b>{title_name}</b>", h_name))
        if m.get("line_name"):
            identity_bits.append(Paragraph(f'<font color="#C8102E"><b>"{m["line_name"]}"</b></font>', body_style))
        if m.get("email"):
            identity_bits.append(Paragraph(m["email"], body_style))
        if m.get("phone"):
            identity_bits.append(Paragraph(m["phone"], body_style))

        header_tbl = Table([[photo_cell, identity_bits]], colWidths=[1.3 * inch, 5.8 * inch])
        header_tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(header_tbl)
        elements.append(Spacer(1, 4))

        def section_table(rows):
            t = Table(rows, colWidths=[1.7 * inch, 5.4 * inch], hAlign="LEFT")
            t.setStyle(TableStyle([
                ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#6c6c6c")),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#222222")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#EFEFEF")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            return t

        def data_table(headers, rows, col_widths):
            if not rows:
                return Paragraph("<i>No entries.</i>", small)
            t = Table([headers] + rows, colWidths=col_widths, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0EBE3")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("TEXTCOLOR", (0, 0), (-1, 0), AOP_NAVY),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#EFEFEF")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            return t

        # §1 Personal Information
        elements.append(Paragraph("§1  Personal Information", section))
        elements.append(section_table([
            ["Address", m.get("address") or "—"],
            ["City", m.get("city") or "—"],
            ["State", m.get("state") or "—"],
            ["Country", m.get("country") or "—"],
            ["Zip code", m.get("zip_code") or "—"],
            ["Marital status", m.get("marital_status") or "—"],
            ["Birthdate", (m.get("birthdate") or "")[:10] or "—"],
            ["Branch of Service", m.get("branch_of_service") or "—"],
        ]))

        # §2 Organization
        elements.append(Paragraph("§2  Organization Information", section))
        elements.append(section_table([
            ["Chapter", chapter.get("name") or "—"],
            ["Region", chapter.get("region") or "—"],
            ["Status", (m.get("status") or "—").upper()],
            ["Tier", tier.get("name") or "—"],
            ["Role", (m.get("role") or "member").title()],
            ["Joined", (m.get("join_date") or "")[:10] or "—"],
            ["Renewal", (m.get("membership_expires_at") or "")[:10] or "—"],
        ]))

        # §3 Civilian Education
        elements.append(Paragraph("§3  Civilian Education", section))
        degrees = list(m.get("civilian_degrees") or [])
        degrees.sort(key=lambda d: (d.get("graduation_year") or 0, d.get("graduation_month") or 0))
        deg_rows = []
        for d in degrees:
            month = d.get("graduation_month")
            month_label = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][month - 1] if month and 1 <= month <= 12 else ""
            grad = f"{month_label} {d.get('graduation_year') or ''}".strip() or "—"
            deg_rows.append([
                d.get("degree_level") or "—",
                d.get("degree_type") or "—",
                d.get("field_of_study") or "—",
                d.get("institution") or "—",
                grad,
            ])
        elements.append(data_table(["Level", "Type", "Field of Study", "Institution", "Graduated"], deg_rows, [1.1 * inch, 0.7 * inch, 1.8 * inch, 2.1 * inch, 1.4 * inch]))

        # §4 Languages
        elements.append(Paragraph("§4  Languages", section))
        langs = list(m.get("languages") or [])
        langs.sort(key=lambda lg: -(lg.get("year_accomplished") or 0))
        lang_rows = []
        for lg in langs:
            lang_rows.append([
                lg.get("language") or "—",
                lg.get("speaking") or "—",
                lg.get("reading") or "—",
                lg.get("writing") or "—",
                str(lg.get("year_accomplished") or "—"),
            ])
        elements.append(data_table(["Language", "Speaking", "Reading", "Writing", "Year"], lang_rows, [1.4 * inch, 1.1 * inch, 1.1 * inch, 1.1 * inch, 0.9 * inch]))

        # §5 Dues
        elements.append(Paragraph("§5  Financial Obligations (Annual Dues)", section))
        dues = [t for t in (data.get("transactions") or []) if t.get("purpose") == "dues" or t.get("type") == "renewal"]
        dues = dues[:5]
        dues_rows = []
        for t in dues:
            dues_rows.append([
                (t.get("created_at") or "")[:10],
                f"${t.get('amount', 0):.2f}",
                (t.get("status") or "—").upper(),
                (t.get("description") or "—")[:55],
            ])
        elements.append(data_table(["Date", "Amount", "Status", "Description"], dues_rows, [1.0 * inch, 0.9 * inch, 1.0 * inch, 3.7 * inch]))

        # §6 Donations
        elements.append(Paragraph("§6  Donations", section))
        donations = [t for t in (data.get("transactions") or []) if t.get("type") == "donation"][:5]
        don_rows = []
        for t in donations:
            don_rows.append([
                (t.get("created_at") or "")[:10],
                (t.get("description") or "General fund")[:55],
                f"${t.get('amount', 0):.2f}",
            ])
        elements.append(data_table(["Date", "Cause", "Amount"], don_rows, [1.1 * inch, 4.4 * inch, 1.1 * inch]))

        # §7 Community Service
        elements.append(Paragraph(f"§7  Community Service ({current_year})", section))
        hours = [h for h in (data.get("hours") or []) if (h.get("date") or "")[:4] == str(current_year)]
        hr_rows = []
        for h in hours:
            hr_rows.append([
                h.get("agency_name") or "—",
                (h.get("event_type") or "other").replace("_", " ").title(),
                f"{h.get('hours', 0):.2f}",
                (h.get("status") or "—").upper(),
                (h.get("date") or "")[:10],
            ])
        elements.append(data_table(["Agency", "Event Type", "Hours", "Status", "Date"], hr_rows, [2.0 * inch, 1.4 * inch, 0.7 * inch, 1.0 * inch, 1.0 * inch]))

        # §8 Awards (grouped, Iter 36)
        elements.append(Paragraph("§8  Awards", section))
        grouped = data.get("awards_grouped")
        if not grouped:
            counts_local: dict = {}
            last_seen: dict = {}
            for g in sorted(data.get("awards") or [], key=lambda x: x.get("granted_at") or ""):
                nm = g.get("award_name") or g.get("name") or "—"
                counts_local[nm] = counts_local.get(nm, 0) + 1
                last_seen[nm] = g.get("granted_at") or last_seen.get(nm, "")
            grouped = [{"award_name": nm, "count": cnt, "last_granted_at": last_seen.get(nm, "")} for nm, cnt in counts_local.items()]
        aw_rows = []
        for row in sorted(grouped, key=lambda x: x.get("last_granted_at") or "", reverse=True):
            nm = row.get("award_name") or "—"
            cnt = int(row.get("count") or 1)
            ordinal_label = {1: "1st Award", 2: "2nd Award", 3: "3rd Award"}.get(cnt, f"{cnt}th Award")
            suffix = f" (× {cnt})" if cnt > 1 else ""
            aw_rows.append([nm, ordinal_label + suffix, (row.get("last_granted_at") or "")[:10]])
        elements.append(data_table(["Award", "Order", "Latest Date"], aw_rows, [3.4 * inch, 1.8 * inch, 1.9 * inch]))

        # §9 Of The Year Honors (most recent 7)
        oty_recent = data.get("of_the_year_recent") or []
        oty_count = int(data.get("of_the_year_count") or 0)
        section_label = (
            f"§9  Of The Year Honors — last 7 of {oty_count}"
            if oty_count > 7 else "§9  Of The Year Honors"
        )
        elements.append(Paragraph(section_label, section))
        if not oty_recent:
            elements.append(Paragraph("No 'Of The Year' honors on record.", small))
        else:
            oty_rows = []
            for o in oty_recent:
                oty_rows.append([
                    str(o.get("year") or "—"),
                    o.get("category_label") or "—",
                    o.get("chapter_name") or "—",
                    o.get("note") or "",
                ])
            elements.append(data_table(
                ["Year", "Category", "Chapter", "Note"],
                oty_rows,
                [0.7 * inch, 2.4 * inch, 1.8 * inch, 2.2 * inch],
            ))

        # §10 Events
        elements.append(Paragraph(f"§10  Events Attended ({current_year} check-ins)", section))
        checkins = [c for c in (data.get("checkins") or []) if (c.get("checked_in_at") or "")[:4] == str(current_year)]
        event_lookup = {e["id"]: e for e in (data.get("events") or [])}
        rsvp_lookup = {}
        for r in (data.get("rsvps") or []):
            rsvp_lookup[r.get("event_id")] = r
        ev_rows = []
        seen_events: set = set()
        for c in checkins:
            eid = c.get("event_id")
            if eid in seen_events:
                continue
            seen_events.add(eid)
            ev = event_lookup.get(eid, {})
            my_rsvp = rsvp_lookup.get(eid, {})
            ev_rows.append([
                ev.get("title") or "—",
                str(len(my_rsvp.get("guests") or [])),
                (c.get("ticket_type") or my_rsvp.get("ticket_type") or "general").replace("_", " ").title(),
                (c.get("checked_in_at") or "")[:10],
            ])
        elements.append(data_table(["Event", "Guests", "Ticket Type", "Check-in Date"], ev_rows, [3.4 * inch, 0.8 * inch, 1.5 * inch, 1.4 * inch]))

        # §11 Assignments
        elements.append(Paragraph("§11  Assignment History", section))
        assignments = list(m.get("assignment_history") or [])
        assignments = sorted(
            assignments,
            key=lambda a: (0 if a.get("is_current") else 1, -1 * int((a.get("start_date") or "").replace("-", "") or 0)),
        )
        asn_rows = []
        for a in assignments:
            end = "Current" if a.get("is_current") else ((a.get("end_date") or "")[:10] or "—")
            asn_rows.append([
                (a.get("start_date") or "")[:10] or "—",
                end,
                a.get("chapter_name") or "—",
                a.get("state") or "—",
                a.get("location") or "—",
                a.get("duty_title") or "—",
                a.get("rank") or "—",
            ])
        elements.append(data_table(
            ["Start", "End", "Chapter", "State", "Location", "Duty Title", "Rank"],
            asn_rows,
            [0.8 * inch, 0.8 * inch, 1.0 * inch, 0.6 * inch, 1.0 * inch, 1.4 * inch, 1.5 * inch],
        ))

        elements.append(Spacer(1, 14))
        elements.append(Paragraph(f"Personnel Brief generated {data['generated_at'][:10]} by the Alpha Omega Phi member portal.", small))

        doc.build(elements)
        buf.seek(0)
        safe_name = (m.get("name") or "member").replace(" ", "_")
        filename = f"personnel-brief-{safe_name}-{data['generated_at'][:10]}.pdf"
        return Response(
            content=buf.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ---------- /reports/dues-reminders ----------
    @api.get("/reports/dues-reminders")
    async def report_dues_reminders(
        stage: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        _: dict = Depends(admin_tab_dep("reports")),
    ):
        """Audit log of dues-reminder emails the system sent.
        Returns one row per (member, dues period, stage) — i.e. every email send.
        Filters: stage (before_30 / before_15 / before_5 / grace_1), and ISO start/end
        on the `sent_at` field. Sorted newest-first."""
        q: dict = {}
        if stage:
            q["stage"] = stage
        if start or end:
            q["sent_at"] = {}
            if start:
                q["sent_at"]["$gte"] = start
            if end:
                q["sent_at"]["$lte"] = end
        cursor = db.dues_reminders_sent.find(q, {"_id": 0}).sort("sent_at", -1).limit(2000)
        rows = await cursor.to_list(2000)
        # Enrich each row with the current member status so the report can flag
        # accounts that have since paid (their `membership_expires_at` will no
        # longer match the row's `expires_at`).
        member_ids = list({r["user_id"] for r in rows})
        users = {}
        if member_ids:
            async for u in db.users.find(
                {"id": {"$in": member_ids}},
                {"_id": 0, "id": 1, "name": 1, "email": 1, "membership_expires_at": 1, "status": 1, "chapter_id": 1, "is_lifetime_member": 1},
            ):
                users[u["id"]] = u
        for r in rows:
            u = users.get(r["user_id"]) or {}
            current_exp = u.get("membership_expires_at") or ""
            r["current_expires_at"] = current_exp
            r["current_status"] = u.get("status") or ""
            r["chapter_id"] = u.get("chapter_id") or ""
            r["is_lifetime_member"] = bool(u.get("is_lifetime_member"))
            # If the member's current expiration is LATER than this row's
            # `expires_at`, they paid after the email went out (the reminder
            # cycle stopped). Surface this for the audit trail.
            r["paid_since"] = bool(current_exp and r.get("expires_at") and current_exp > r["expires_at"])
        return rows

    # ---------- /reports/dues-reminders/summary ----------
    @api.get("/reports/dues-reminders/summary")
    async def report_dues_reminders_summary(
        _: dict = Depends(admin_tab_dep("reports")),
    ):
        """Quick per-stage counts (all-time + last 30 days) so the Reports tab
        can render a compact strip of stat tiles above the audit table."""
        all_time = {}
        last_30 = {}
        thirty_days_ago = iso(now_utc().replace(hour=0, minute=0, second=0, microsecond=0))
        # Use a simple aggregation; collection is small (<10k rows expected).
        pipeline_all = [{"$group": {"_id": "$stage", "n": {"$sum": 1}}}]
        async for row in db.dues_reminders_sent.aggregate(pipeline_all):
            all_time[row["_id"]] = row["n"]
        pipeline_30 = [
            {"$match": {"sent_at": {"$gte": thirty_days_ago}}},
            {"$group": {"_id": "$stage", "n": {"$sum": 1}}},
        ]
        async for row in db.dues_reminders_sent.aggregate(pipeline_30):
            last_30[row["_id"]] = row["n"]
        return {"all_time": all_time, "last_30_days": last_30}

    # ---------- /reports/award-grants ----------
    @api.get("/reports/award-grants")
    async def report_award_grants(
        award_id: Optional[str] = None,
        user_id: Optional[str] = None,
        year: Optional[int] = None,
        _: dict = Depends(admin_tab_dep("reports")),
    ):
        """Every award (ribbon/medal) ever granted to a member, sorted newest
        first. Used by the Admin → Reports → Awards tab so leadership can audit
        who received what, when, and why."""
        q: dict = {}
        if award_id:
            q["award_id"] = award_id
        if user_id:
            q["user_id"] = user_id
        if year is not None:
            # Year filter operates on the granted_at ISO string
            start = f"{year}-01-01T00:00:00"
            end = f"{year + 1}-01-01T00:00:00"
            q["granted_at"] = {"$gte": start, "$lt": end}
        rows = await db.award_grants.find(q, {"_id": 0}).sort("granted_at", -1).limit(2000).to_list(2000)
        # Enrich with current member email + chapter so the audit table is
        # useful even if the member's stored name changed since the grant.
        uids = [r["user_id"] for r in rows if r.get("user_id")]
        users: dict = {}
        if uids:
            async for u in db.users.find(
                {"id": {"$in": uids}},
                {"_id": 0, "id": 1, "name": 1, "email": 1, "chapter_id": 1, "avatar_url": 1},
            ):
                users[u["id"]] = u
        cids = list({(users.get(uid) or {}).get("chapter_id") for uid in uids} - {None, ""})
        chapters: dict = {}
        if cids:
            async for c in db.chapters.find({"id": {"$in": cids}}, {"_id": 0, "id": 1, "name": 1}):
                chapters[c["id"]] = c.get("name", "")
        out = []
        for r in rows:
            u = users.get(r.get("user_id") or "") or {}
            out.append({
                **r,
                "current_user_name": u.get("name", r.get("user_name", "")),
                "user_email": u.get("email", ""),
                "user_avatar_url": u.get("avatar_url"),
                "chapter_name": chapters.get(u.get("chapter_id") or "", ""),
            })
        return out

    # ---------- /reports/of-the-year ----------
    # Local copy of category labels — mirrors routes/of_the_year.CATEGORY_LABELS.
    # Kept here so the reports module doesn't import another routes module.
    _OTY_LABELS = {
        "member_of_year": "Member of the Year",
        "chapter_of_year": "Chapter of the Year",
        "top_cs_member": "Top Community Service Member",
        "top_cs_chapter": "Top Community Service Chapter",
        "top_fundraising_member": "Top Fundraising Member",
        "top_fundraising_chapter": "Top Fundraising Chapter",
        "top_recruiter": "Top Member Recruiter",
    }

    @api.get("/reports/of-the-year")
    async def report_of_the_year(
        year: Optional[int] = None,
        _: dict = Depends(admin_tab_dep("reports")),
    ):
        """All "Of The Year" winners (member-of-the-year, chapter-of-the-year,
        fundraiser-of-the-year, etc.) for the audit table. Plain enriched list
        — newest year first, alphabetical category inside each year."""
        q: dict = {}
        if year is not None:
            q["year"] = year
        rows = await db.of_the_year_awards.find(q, {"_id": 0}).sort([("year", -1), ("category", 1)]).to_list(1000)
        uids = [r["user_id"] for r in rows if r.get("user_id")]
        cids = [r["chapter_id"] for r in rows if r.get("chapter_id")]
        users: dict = {}
        chapters: dict = {}
        if uids:
            async for u in db.users.find({"id": {"$in": uids}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "avatar_url": 1, "chapter_id": 1}):
                users[u["id"]] = u
        if cids:
            async for c in db.chapters.find({"id": {"$in": cids}}, {"_id": 0, "id": 1, "name": 1, "logo_url": 1}):
                chapters[c["id"]] = c
        out = []
        for r in rows:
            u = users.get(r.get("user_id") or "") or {}
            c = chapters.get(r.get("chapter_id") or "") or {}
            out.append({
                **r,
                "category_label": _OTY_LABELS.get(r.get("category", ""), r.get("category", "")),
                "current_user_name": u.get("name", r.get("user_name", "")),
                "user_email": u.get("email", ""),
                "user_avatar_url": u.get("avatar_url"),
                "chapter_name": c.get("name", r.get("chapter_name", "")),
                "chapter_logo_url": c.get("logo_url"),
            })
        return out

    # Expose helpers on register so server.py /me/personnel-brief* can delegate.
    register.personnel_brief_data = personnel_brief_data
    register.personnel_brief_pdf_response = personnel_brief_pdf_response
