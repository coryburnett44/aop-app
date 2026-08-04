"""Life Member Club + Medallion Club routes.

Two related admin surfaces the user asked for on the Awards page:

  1. **Life Member Club** — a curated list, indexed by induction year. Admins
     can add EITHER an existing member (by user_id) OR a free-text name for
     historical inductees who never had an account. Members can browse
     everyone in the club, grouped by year.

  2. **Medallion Club** — Bronze / Silver / Gold tiered recognition. The
     medallion awards themselves live in the existing `awards` collection
     (so they show up on member profiles, PDFs, etc. exactly like any other
     ribbon). This module only owns the AUTO-ELIGIBILITY computation —
     given the criteria the user supplied (consecutive years of service,
     cumulative community-service hours, national/state events attended,
     and personal fundraising totals) it returns candidates each admin
     can then grant with the existing `POST /awards/{id}/grant` flow.

Public surface:
  GET    /api/life-members
  POST   /api/life-members                (admin)
  PUT    /api/life-members/{id}           (admin)
  DELETE /api/life-members/{id}           (admin)
  GET    /api/awards/medallion-eligibility  (admin)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Body, Depends, HTTPException
from pydantic import BaseModel, Field


class LifeMemberIn(BaseModel):
    user_id: Optional[str] = None          # existing member (preferred)
    name: Optional[str] = None             # OR free-text (historical)
    year: int = Field(..., ge=1900, le=2100)
    month: Optional[int] = Field(None, ge=1, le=12)
    day: Optional[int] = Field(None, ge=1, le=31)
    note: Optional[str] = None             # optional short bio / role


class LifeMemberUpdateIn(BaseModel):
    user_id: Optional[str] = None          # switch member (or "" to make historical)
    name: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = Field(None, ge=1, le=12)
    day: Optional[int] = Field(None, ge=1, le=31)
    note: Optional[str] = None


def _parse_iso_date(iso_str: str):
    if not iso_str:
        return None
    try:
        head = str(iso_str)[:10]
        y, m, d = head.split("-")
        return datetime(int(y), int(m), int(d), tzinfo=timezone.utc).date()
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
):
    # ================================================================
    # Life Member Club
    # ================================================================

    def _life_member_out(doc: dict) -> dict:
        return {
            "id": doc["id"],
            "user_id": doc.get("user_id"),
            "name": doc.get("name", ""),
            "year": doc.get("year"),
            "month": doc.get("month"),
            "day": doc.get("day"),
            "note": doc.get("note", ""),
            "created_at": doc.get("created_at"),
            # Enriched at read-time (see list handler)
            "member_name": doc.get("member_name", ""),
            "member_avatar_url": doc.get("member_avatar_url", ""),
            "member_chapter_name": doc.get("member_chapter_name", ""),
        }

    async def _enrich_life_member(doc: dict) -> dict:
        """Attach member name/avatar/chapter for account-linked entries so
        the frontend doesn't have to fan out N /members/{id} calls."""
        if doc.get("user_id"):
            u = await db.users.find_one(
                {"id": doc["user_id"]},
                {"_id": 0, "name": 1, "first_name": 1, "last_name": 1,
                 "avatar_url": 1, "chapter_id": 1},
            )
            if u:
                full = u.get("name") or f"{u.get('first_name','')} {u.get('last_name','')}".strip()
                doc["member_name"] = full or doc.get("name", "")
                doc["member_avatar_url"] = u.get("avatar_url", "")
                if u.get("chapter_id"):
                    c = await db.chapters.find_one({"id": u["chapter_id"]}, {"_id": 0, "name": 1})
                    if c:
                        doc["member_chapter_name"] = c.get("name", "")
        return doc

    @api.get("/life-members")
    async def list_life_members(_: dict = Depends(get_current_user)):
        docs = await db.life_members.find({}, {"_id": 0}).sort([("year", -1), ("name", 1)]).to_list(2000)
        return [_life_member_out(await _enrich_life_member(d)) for d in docs]

    @api.post("/life-members")
    async def create_life_member(body: LifeMemberIn, _: dict = Depends(admin_tab_dep("awards"))):
        if not body.user_id and not (body.name or "").strip():
            raise HTTPException(status_code=400, detail="Provide either a member or a free-text name.")
        display_name = (body.name or "").strip()
        if body.user_id:
            # Prevent duplicates of the same user_id.
            existing = await db.life_members.find_one({"user_id": body.user_id})
            if existing:
                raise HTTPException(status_code=409, detail="This member is already in the Life Member Club.")
            u = await db.users.find_one({"id": body.user_id}, {"_id": 0, "name": 1, "first_name": 1, "last_name": 1})
            if not u:
                raise HTTPException(status_code=404, detail="Member not found.")
            if not display_name:
                display_name = (u.get("name") or f"{u.get('first_name','')} {u.get('last_name','')}".strip()) or "Member"
        doc = {
            "id": str(uuid.uuid4()),
            "user_id": body.user_id or None,
            "name": display_name,
            "year": int(body.year),
            "month": int(body.month) if body.month else None,
            "day": int(body.day) if body.day else None,
            "note": (body.note or "").strip(),
            "created_at": iso(now_utc()),
        }
        await db.life_members.insert_one(doc)
        doc.pop("_id", None)
        return _life_member_out(await _enrich_life_member(doc))

    @api.put("/life-members/{lm_id}")
    async def update_life_member(lm_id: str, body: LifeMemberUpdateIn, _: dict = Depends(admin_tab_dep("awards"))):
        doc = await db.life_members.find_one({"id": lm_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Life Member entry not found.")
        updates = {}
        # `user_id` semantics: passing an empty string clears the link (turns
        # the entry into a free-text/historical row). Passing a real id
        # switches the linked member (backend re-derives the display name).
        if body.user_id is not None:
            new_uid = (body.user_id or "").strip()
            if new_uid:
                u = await db.users.find_one({"id": new_uid}, {"_id": 0, "id": 1, "name": 1, "first_name": 1, "last_name": 1})
                if not u:
                    raise HTTPException(status_code=404, detail="Selected member not found.")
                # Prevent duplicating an existing membership row.
                other = await db.life_members.find_one({"user_id": new_uid, "id": {"$ne": lm_id}})
                if other:
                    raise HTTPException(status_code=409, detail="This member is already in the Life Member Club.")
                updates["user_id"] = new_uid
                # Refresh the display name to match the new member unless
                # the admin also supplied a `name` override this call.
                if body.name is None:
                    updates["name"] = (u.get("name") or f"{u.get('first_name','')} {u.get('last_name','')}".strip()) or "Member"
            else:
                updates["user_id"] = None
        if body.name is not None and body.name.strip():
            updates["name"] = body.name.strip()
        if body.year is not None:
            if body.year < 1900 or body.year > 2100:
                raise HTTPException(status_code=400, detail="Year must be between 1900 and 2100.")
            updates["year"] = int(body.year)
        # Month/day can be cleared (set to None) by passing 0. We only
        # persist an explicit int change; other values are validated
        # by Pydantic's Field(ge=..., le=...).
        if body.month is not None:
            updates["month"] = int(body.month) if body.month else None
        if body.day is not None:
            updates["day"] = int(body.day) if body.day else None
        if body.note is not None:
            updates["note"] = body.note.strip()
        if updates:
            await db.life_members.update_one({"id": lm_id}, {"$set": updates})
            doc.update(updates)
        doc.pop("_id", None)
        return _life_member_out(await _enrich_life_member(doc))

    @api.delete("/life-members/{lm_id}")
    async def delete_life_member(lm_id: str, _: dict = Depends(admin_tab_dep("awards"))):
        res = await db.life_members.delete_one({"id": lm_id})
        if not res.deleted_count:
            raise HTTPException(status_code=404, detail="Life Member entry not found.")
        return {"ok": True}

    # ================================================================
    # Medallion Club — auto-eligibility
    # ================================================================
    async def _consecutive_years_by_user() -> dict:
        """Compute years-of-consecutive-service per user for the Medallion Club.

        Rule (per user's Iteration 151 clarification):
          - Base the count on the member's `join_date` (or `joined_at` /
            `created_at` fallback).
          - If the member has EVER been inactive — i.e. `status_override`
            is `inactive`/`deceased`, or `status_history` contains any
            'inactive' entry — they do NOT count as having consecutive
            years. Reactivating after paying dues does not restart a fresh
            'consecutive' streak; it simply zeros them out for medallion
            purposes. This is stricter than the ribbon logic (which
            respects reactivation as a new streak start).
        """
        out: dict = {}
        today = datetime.now(timezone.utc).date()

        def _has_inactivity(u: dict) -> bool:
            if (u.get("status_override") or "").lower() in {"inactive", "deceased"}:
                return True
            for entry in u.get("status_history") or []:
                status = (entry.get("status") or entry.get("action") or "").lower()
                if status in {"inactive", "deactivated", "deactivation", "deceased"}:
                    return True
            return False

        async for u in db.users.find(
            {},
            {"_id": 0, "id": 1, "join_date": 1, "joined_at": 1, "created_at": 1,
             "status_history": 1, "status_override": 1},
        ):
            uid = u.get("id")
            # Any history of inactivity zeroes them out.
            if _has_inactivity(u):
                out[uid] = 0
                continue
            start = (
                _parse_iso_date(u.get("join_date") or "")
                or _parse_iso_date(u.get("joined_at") or "")
                or _parse_iso_date(u.get("created_at") or "")
            )
            if not start:
                continue
            years = today.year - start.year - (
                (today.month, today.day) < (start.month, start.day)
            )
            out[uid] = max(0, years)
        return out

    async def _cs_hours_by_user() -> dict:
        """Sum of ALL approved community-service hours per user, all-time
        (Medallion criteria are cumulative, not annual)."""
        out: dict = {}
        async for h in db.volunteer_hours.find(
            {"status": "approved"},
            {"_id": 0, "user_id": 1, "hours": 1},
        ):
            uid = h.get("user_id")
            hrs = float(h.get("hours") or 0)
            if uid:
                out[uid] = out.get(uid, 0.0) + hrs
        return out

    async def _events_attended_by_user() -> dict:
        """Total check-ins per user, all-time. Once the Phase-2 CSV importer
        ships, that data lands in the same `checkins` collection so this
        helper keeps working unchanged."""
        out: dict = {}
        async for c in db.checkins.find({}, {"_id": 0, "user_id": 1}):
            uid = c.get("user_id")
            if uid:
                out[uid] = out.get(uid, 0) + 1
        return out

    async def _fundraised_by_user() -> dict:
        """Sum of completed donation transactions per user, all-time."""
        out: dict = {}
        async for t in db.transactions.find(
            {"status": "completed", "type": "donation"},
            {"_id": 0, "user_id": 1, "amount": 1},
        ):
            uid = t.get("user_id")
            amt = float(t.get("amount") or 0)
            if uid:
                out[uid] = out.get(uid, 0.0) + amt
        return out

    @api.get("/awards/medallion-eligibility")
    async def medallion_eligibility(_: dict = Depends(admin_tab_dep("awards"))):
        """Return the list of members who currently satisfy each Medallion
        tier's criteria. Members are ranked by `criteria_met_count` so the
        admin can grant the strongest candidates first. `already_granted`
        flags members who already hold this Medallion (so the admin doesn't
        double-grant)."""
        # Grab the three medallion awards (identified by medallion_tier field).
        medallion_awards = {}
        async for a in db.awards.find({"medallion_tier": {"$in": ["bronze", "silver", "gold"]}}, {"_id": 0}):
            medallion_awards[a["medallion_tier"]] = a

        # If seed hasn't run yet, return an empty payload.
        if not medallion_awards:
            return {"bronze": [], "silver": [], "gold": []}

        # Pull existing grants per medallion so we can flag `already_granted`
        # AND enforce the "requires prior tier" rule.
        holders_by_tier: dict = {"bronze": set(), "silver": set(), "gold": set()}
        for tier, a in medallion_awards.items():
            async for g in db.award_grants.find({"award_id": a["id"]}, {"_id": 0, "user_id": 1}):
                if g.get("user_id"):
                    holders_by_tier[tier].add(g["user_id"])

        years_map, cs_map, events_map, funds_map = (
            await _consecutive_years_by_user(),
            await _cs_hours_by_user(),
            await _events_attended_by_user(),
            await _fundraised_by_user(),
        )

        # Load user meta for the rows we'll return.
        users_index: dict = {}
        async for u in db.users.find(
            {"status_override": {"$ne": "inactive"}},
            {"_id": 0, "id": 1, "name": 1, "first_name": 1, "last_name": 1,
             "avatar_url": 1, "chapter_id": 1, "email": 1},
        ):
            users_index[u["id"]] = u

        chapter_names: dict = {}
        async for c in db.chapters.find({}, {"_id": 0, "id": 1, "name": 1}):
            chapter_names[c["id"]] = c.get("name", "")

        def _row(uid: str, tier: str, criteria: dict) -> Optional[dict]:
            u = users_index.get(uid) or {}
            years = years_map.get(uid, 0)
            cs = cs_map.get(uid, 0.0)
            events = events_map.get(uid, 0)
            funds = funds_map.get(uid, 0.0)

            met_years = years >= criteria["years"]
            met_cs = cs >= criteria["cs_hours"]
            met_events = events >= criteria["events"]
            met_funds = funds >= criteria["fundraised"]
            required_tier = criteria.get("requires_tier")
            met_prior = (required_tier is None) or (uid in holders_by_tier.get(required_tier, set()))

            met_count = sum([met_years, met_cs, met_events, met_funds, met_prior])
            # Only surface members meeting ALL criteria as "eligible", but
            # also expose partially-qualifying rows so admins can see how
            # close someone is (met_count/5).
            eligible = met_count == 5

            return {
                "user_id": uid,
                "name": u.get("name") or f"{u.get('first_name','')} {u.get('last_name','')}".strip(),
                "email": u.get("email", ""),
                "avatar_url": u.get("avatar_url", ""),
                "chapter_name": chapter_names.get(u.get("chapter_id", ""), ""),
                "years_of_service": years,
                "cs_hours": round(cs, 1),
                "events_attended": events,
                "fundraised": round(funds, 2),
                "criteria_met": {
                    "years": met_years,
                    "cs_hours": met_cs,
                    "events": met_events,
                    "fundraised": met_funds,
                    "prior_tier": met_prior,
                },
                "requires_prior_tier": required_tier,
                "criteria_met_count": met_count,
                "eligible": eligible,
                "already_granted": uid in holders_by_tier[tier],
            }

        result = {}
        for tier in ("bronze", "silver", "gold"):
            a = medallion_awards.get(tier)
            if not a:
                result[tier] = []
                continue
            criteria = a.get("medallion_criteria") or {}
            rows = [
                _row(uid, tier, criteria)
                for uid in users_index.keys()
            ]
            rows = [r for r in rows if r is not None]
            # Sort by (eligible first, then criteria_met_count desc, then name).
            rows.sort(key=lambda r: (
                0 if r["eligible"] else 1,
                -r["criteria_met_count"],
                r["name"].lower(),
            ))
            result[tier] = rows
        return result
