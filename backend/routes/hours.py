"""Volunteer-hours routes.

Owns:
  - POST   /hours                      (log own hours)
  - GET    /hours                      (admin queue, chapter-scoped for Governor)
  - PUT    /hours/{id}/review          (admin approves / rejects / adjusts)
  - DELETE /hours/{id}                 (member or admin)
  - GET    /me/hours                   (filterable by year/quarter/month/status)
  - GET    /me/hours/summary           (year rollup: by_month / by_quarter)

The `hours_out` serializer, `_period_to_range` helper, and chapter-scoping
helpers remain in server.py and are injected.
"""
from datetime import datetime as _dt
from typing import Optional
import uuid

from fastapi import Depends, HTTPException

from models import HoursLogIn, HoursReviewIn, AdminHoursLogIn


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
