"""Awards routes.

Owns:
  - GET    /awards                          (list all awards + counts)
  - GET    /awards/{award_id}/grants        (who has this award, public to members)
  - POST   /awards                          (admin: create)
  - PUT    /awards/{award_id}               (admin: edit)
  - DELETE /awards/{award_id}               (admin: remove award + all grants)
  - POST   /awards/{award_id}/grant         (admin: grant to one member)
  - POST   /awards/{award_id}/grant-bulk    (admin: grant to many at once)
  - DELETE /awards/grants/{grant_id}        (admin: revoke a single grant)
  - PUT    /awards/grants/{grant_id}        (admin: edit reason / back-date)
  - GET    /members/{user_id}/awards        (per-member award grants)
  - GET    /me/awards                       (current user's grants)

The `award_out` serializer is owned here. Helpers (`db`, `get_current_user`,
`admin_tab_dep`, `iso`, `now_utc`) are injected by `register(...)`.
"""
from datetime import datetime, timezone
import uuid

from fastapi import Depends, HTTPException

from models import AwardIn, AwardUpdateIn, AwardGrantIn


def award_out(a: dict) -> dict:
    return {
        "id": a["id"],
        "name": a["name"],
        "description": a.get("description", ""),
        "icon": a.get("icon", "trophy"),
        "color": a.get("color", "#F9D466"),
        "granted_count": a.get("granted_count", 0),
        "granted_distinct_count": a.get("granted_distinct_count", a.get("granted_count", 0)),
    }


def register(
    api,
    *,
    db,
    admin_tab_dep,
    get_current_user,
    admin_role_of,
    iso,
    now_utc,
):

    @api.get("/awards")
    async def list_awards():
        items = await db.awards.find({}, {"_id": 0}).to_list(200)
        for a in items:
            a["granted_count"] = await db.award_grants.count_documents({"award_id": a["id"]})
            # Iter 37: distinct recipients (a single member can earn the same award
            # multiple times, so we track both totals + unique-recipient count).
            distinct = await db.award_grants.distinct("user_id", {"award_id": a["id"]})
            a["granted_distinct_count"] = len(distinct)
        return [award_out(a) for a in items]

    @api.get("/awards/{award_id}/grants")
    async def list_award_grants(award_id: str, _: dict = Depends(get_current_user)):
        """Public-to-members list of who has received this award and when. Drives
        the clickable recipient list inside each tile on /awards. Returns minimal
        info: member name, avatar, year granted, ordinal (so repeat grants render
        "2× in 2024"). Sorted by granted_at DESC. Cheap — a single index hit on
        award_grants + one users lookup."""
        grants = await db.award_grants.find(
            {"award_id": award_id},
            {"_id": 0, "user_id": 1, "user_name": 1, "granted_at": 1, "ordinal": 1, "reason": 1},
        ).sort("granted_at", -1).to_list(500)
        if not grants:
            return []
        uids = list({g["user_id"] for g in grants if g.get("user_id")})
        users: dict = {}
        if uids:
            async for u in db.users.find(
                {"id": {"$in": uids}},
                {"_id": 0, "id": 1, "name": 1, "avatar_url": 1},
            ):
                users[u["id"]] = u
        out = []
        for g in grants:
            u = users.get(g.get("user_id") or "") or {}
            granted_at = g.get("granted_at") or ""
            year = ""
            if granted_at:
                # Strings are ISO so the first 4 chars are the year. Avoid parsing
                # full datetimes for a hot list endpoint.
                year = granted_at[:4] if len(granted_at) >= 4 else ""
            out.append({
                "user_id": g.get("user_id"),
                "member_name": u.get("name") or g.get("user_name") or "Former member",
                "avatar_url": u.get("avatar_url"),
                "granted_at": granted_at,
                "year": year,
                "ordinal": g.get("ordinal", 1),
                "reason": g.get("reason", ""),
            })
        return out

    @api.post("/awards")
    async def create_award(body: AwardIn, _: dict = Depends(admin_tab_dep("awards"))):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = iso(now_utc())
        await db.awards.insert_one(doc)
        return award_out(doc)

    @api.put("/awards/{award_id}")
    async def update_award(award_id: str, body: AwardUpdateIn, _: dict = Depends(admin_tab_dep("awards"))):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.awards.update_one({"id": award_id}, {"$set": updates})
        a = await db.awards.find_one({"id": award_id}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=404, detail="Award not found")
        return award_out(a)

    @api.delete("/awards/{award_id}")
    async def delete_award(award_id: str, _: dict = Depends(admin_tab_dep("awards"))):
        await db.awards.delete_one({"id": award_id})
        await db.award_grants.delete_many({"award_id": award_id})
        return {"ok": True}

    @api.post("/awards/{award_id}/grant")
    async def grant_award(award_id: str, body: AwardGrantIn, admin: dict = Depends(admin_tab_dep("awards"))):
        award = await db.awards.find_one({"id": award_id}, {"_id": 0})
        if not award:
            raise HTTPException(status_code=404, detail="Award not found")
        user = await db.users.find_one({"id": body.user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        # Multiple grants of the same award to the same member are allowed (Iter 36).
        # Each grant gets an ordinal so the UI can render "2nd Award", "3rd Award", etc.
        prior_count = await db.award_grants.count_documents({"award_id": award_id, "user_id": body.user_id})
        ordinal = prior_count + 1  # this grant becomes the (prior_count+1)-th
        doc = {
            "id": str(uuid.uuid4()),
            "award_id": award_id,
            "award_name": award["name"],
            "award_icon": award.get("icon", "trophy"),
            "award_color": award.get("color", "#F9D466"),
            "user_id": body.user_id,
            "user_name": user.get("name", ""),
            "reason": body.reason,
            "granted_by": admin["id"],
            "granted_by_name": admin.get("name", "Admin"),
            "granted_at": body.granted_at or iso(now_utc()),
            "ordinal": ordinal,
        }
        await db.award_grants.insert_one(doc)
        out = dict(doc)
        out.pop("_id", None)
        return out

    @api.delete("/awards/grants/{grant_id}")
    async def revoke_award(grant_id: str, _: dict = Depends(admin_tab_dep("awards"))):
        res = await db.award_grants.delete_one({"id": grant_id})
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Grant not found")
        return {"ok": True}

    @api.put("/awards/grants/{grant_id}")
    async def update_award_grant(grant_id: str, body: dict, _: dict = Depends(admin_tab_dep("awards"))):
        """Admin edit of an existing grant — change the reason or back-date it.
        Only `reason` and `granted_at` are editable; the member, award, and
        ordinal are immutable so audit history stays trustworthy."""
        grant = await db.award_grants.find_one({"id": grant_id}, {"_id": 0})
        if not grant:
            raise HTTPException(status_code=404, detail="Grant not found")
        update_doc: dict = {}
        if "reason" in body:
            update_doc["reason"] = (body.get("reason") or "").strip()
        if "granted_at" in body and body["granted_at"]:
            # Accept either an ISO string or a date-only "YYYY-MM-DD".
            gd = str(body["granted_at"])
            if len(gd) == 10 and gd[4] == "-":
                gd = gd + "T00:00:00"
            try:
                datetime.fromisoformat(gd.replace("Z", "+00:00"))
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid granted_at — use ISO or YYYY-MM-DD")
            update_doc["granted_at"] = gd
        if not update_doc:
            return {"ok": True, "no_change": True}
        await db.award_grants.update_one({"id": grant_id}, {"$set": update_doc})
        updated = await db.award_grants.find_one({"id": grant_id}, {"_id": 0})
        return updated

    @api.post("/awards/{award_id}/grant-bulk")
    async def grant_award_bulk(award_id: str, body: dict, admin: dict = Depends(admin_tab_dep("awards"))):
        """Grant the same award to many members in one shot. Each member gets
        their own grant row with its own ordinal — repeat grants (same award to
        same member) are still allowed and the ordinal increments correctly.

        Body: {user_ids: [str], reason?: str, granted_at?: ISO string}
        Returns {created, failed, total, results: [{user_id, name, ok, ordinal?, error?}]}
        """
        award = await db.awards.find_one({"id": award_id}, {"_id": 0})
        if not award:
            raise HTTPException(status_code=404, detail="Award not found")
        user_ids = list(dict.fromkeys((body or {}).get("user_ids") or []))
        if not user_ids:
            raise HTTPException(status_code=400, detail="user_ids is required")
        if len(user_ids) > 200:
            raise HTTPException(status_code=400, detail="Max 200 members per bulk grant")
        reason = ((body or {}).get("reason") or "").strip()
        granted_at = (body or {}).get("granted_at") or iso(now_utc())

        # Look up all targets and prior counts in two round-trips.
        targets: dict = {}
        async for u in db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}):
            targets[u["id"]] = u
        # Count prior grants of this award per user — needed to compute the new ordinal.
        prior_counts: dict = {}
        async for d in db.award_grants.aggregate([
            {"$match": {"award_id": award_id, "user_id": {"$in": user_ids}}},
            {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
        ]):
            prior_counts[d["_id"]] = d["n"]

        docs: list[dict] = []
        results: list[dict] = []
        for uid in user_ids:
            target = targets.get(uid)
            if not target:
                results.append({"user_id": uid, "ok": False, "error": "Member not found"})
                continue
            ordinal = prior_counts.get(uid, 0) + 1
            docs.append({
                "id": str(uuid.uuid4()),
                "award_id": award_id,
                "award_name": award["name"],
                "award_icon": award.get("icon", "trophy"),
                "award_color": award.get("color", "#F9D466"),
                "user_id": uid,
                "user_name": target.get("name", ""),
                "reason": reason,
                "granted_by": admin["id"],
                "granted_by_name": admin.get("name", "Admin"),
                "granted_at": granted_at,
                "ordinal": ordinal,
            })
            results.append({"user_id": uid, "name": target.get("name", ""), "ok": True, "ordinal": ordinal})

        if docs:
            await db.award_grants.insert_many(docs)
        ok_count = sum(1 for r in results if r["ok"])
        return {
            "created": ok_count,
            "failed": len(results) - ok_count,
            "total": len(results),
            "results": results,
        }

    @api.get("/members/{user_id}/awards")
    async def member_awards(user_id: str):
        """Returns every award grant for the user, with each entry carrying its
        ordinal (1st, 2nd, 3rd Award) and an `award_count` total for the same award.

        The UI typically renders awards grouped — one row per distinct award, with
        a "× N" or "(2nd Award)" label — but the raw grants list is returned so
        callers can decide their own grouping.
        """
        cursor = db.award_grants.find({"user_id": user_id}, {"_id": 0}).sort([("award_name", 1), ("granted_at", 1)])
        grants = await cursor.to_list(500)
        # Backfill the ordinal field for older grants that don't have it stored.
        counts: dict = {}
        for g in grants:
            aid = g["award_id"]
            counts[aid] = counts.get(aid, 0) + 1
            if not g.get("ordinal"):
                g["ordinal"] = counts[aid]
        # Add award_count (total grants of this same award to this user) so the UI
        # can render "× 3" without re-counting on the client.
        totals = {aid: total for aid, total in counts.items()}
        for g in grants:
            g["award_count"] = totals.get(g["award_id"], 1)
        # Sort newest first for display
        grants.sort(key=lambda x: x.get("granted_at", ""), reverse=True)
        return grants

    @api.get("/me/awards")
    async def my_awards(user: dict = Depends(get_current_user)):
        """Same shape as /members/{id}/awards — each grant carries `ordinal` (the
        1st/2nd/3rd grant of that award to this member) and `award_count` (total
        grants of that award to this member)."""
        cursor = db.award_grants.find({"user_id": user["id"]}, {"_id": 0}).sort([("award_name", 1), ("granted_at", 1)])
        grants = await cursor.to_list(500)
        counts: dict = {}
        for g in grants:
            aid = g["award_id"]
            counts[aid] = counts.get(aid, 0) + 1
            if not g.get("ordinal"):
                g["ordinal"] = counts[aid]
        for g in grants:
            g["award_count"] = counts.get(g["award_id"], 1)
        grants.sort(key=lambda x: x.get("granted_at", ""), reverse=True)
        return grants


    # ---------- Eligibility computation (Iter 111) ----------
    @api.get("/awards/eligibility")
    async def awards_eligibility(year: int, admin: dict = Depends(admin_tab_dep("awards"))):
        """Full Access admins only. Returns candidate members for each of the
        seven programme awards for the given calendar year (Jan 1 → Dec 31).

        Awards computed:
          - service_ribbon        (1st complete active year, then every 5 years)
          - fundraiser_ribbon     (top donor of the year)
          - community_service     (>= 100 approved volunteer hours in year)
          - ken_thompson          (top weighted-hours member per chapter)
          - recruitment_ribbon    (top recruiter of the year)
          - members_ribbon        (top 3 across hours + recruits + fundraising)
          - chapter_of_the_year   (chapter with highest composite score)
        """
        if admin_role_of(admin) != "full":
            raise HTTPException(status_code=403, detail="Awards eligibility is only visible to Full Access admins.")
        try:
            year_i = int(year)
        except Exception:
            raise HTTPException(status_code=400, detail="year must be an integer")
        if year_i < 2000 or year_i > 2100:
            raise HTTPException(status_code=400, detail="year out of range")

        year_start = f"{year_i}-01-01"
        year_end = f"{year_i}-12-31T23:59:59"

        # ---- Load supporting data in parallel ----
        users_map: dict = {}
        chapters_map: dict = {}
        async for u in db.users.find(
            {"role": {"$ne": "system"}},
            {
                "_id": 0, "id": 1, "name": 1, "chapter_id": 1, "created_at": 1,
                "status_override": 1, "status_history": 1, "auto_inactivated_at": 1,
                "member_status": 1,
            },
        ):
            users_map[u["id"]] = u
        async for c in db.chapters.find({}, {"_id": 0, "id": 1, "name": 1}):
            chapters_map[c["id"]] = c.get("name", "")

        def user_row(uid: str, **extra) -> dict:
            u = users_map.get(uid) or {}
            return {
                "user_id": uid,
                "name": u.get("name", "Unknown"),
                "chapter_id": u.get("chapter_id"),
                "chapter_name": chapters_map.get(u.get("chapter_id") or "", ""),
                **extra,
            }

        # ---- Approved hours in the target year ----
        hours_by_user: dict = {}
        hours_by_chapter: dict = {}
        aop_by_user: dict = {}
        trend_by_user: dict = {}
        other_by_user: dict = {}
        async for h in db.volunteer_hours.find(
            {"status": "approved", "date": {"$gte": year_start, "$lte": year_end}},
            {"_id": 0, "user_id": 1, "hours": 1, "event_type": 1},
        ):
            uid = h.get("user_id")
            if not uid:
                continue
            hrs = float(h.get("hours") or 0)
            hours_by_user[uid] = hours_by_user.get(uid, 0.0) + hrs
            u = users_map.get(uid) or {}
            cid = u.get("chapter_id")
            if cid:
                hours_by_chapter[cid] = hours_by_chapter.get(cid, 0.0) + hrs
            et = (h.get("event_type") or "aop_related").lower()
            if et == "aop_related":
                aop_by_user[uid] = aop_by_user.get(uid, 0.0) + hrs
            elif et == "trendsetters_spirits":
                trend_by_user[uid] = trend_by_user.get(uid, 0.0) + hrs
            else:
                other_by_user[uid] = other_by_user.get(uid, 0.0) + hrs

        # ---- Fundraising (completed donations) ----
        donors_by_user: dict = {}
        donations_amount_by_chapter: dict = {}
        async for t in db.transactions.find(
            {"status": "completed", "type": "donation",
             "created_at": {"$gte": year_start, "$lte": year_end}},
            {"_id": 0, "user_id": 1, "amount": 1},
        ):
            uid = t.get("user_id")
            amt = float(t.get("amount") or 0)
            if uid:
                donors_by_user[uid] = donors_by_user.get(uid, 0.0) + amt
                u = users_map.get(uid) or {}
                cid = u.get("chapter_id")
                if cid:
                    donations_amount_by_chapter[cid] = donations_amount_by_chapter.get(cid, 0.0) + amt

        # ---- Recruits per user ----
        recruits_by_user: dict = {}
        recruits_by_chapter: dict = {}
        async for r in db.recruitments.find(
            {"date_recruited": {"$gte": year_start, "$lte": year_end}},
            {"_id": 0, "recruiter_id": 1},
        ):
            uid = r.get("recruiter_id")
            if not uid:
                continue
            recruits_by_user[uid] = recruits_by_user.get(uid, 0) + 1
            u = users_map.get(uid) or {}
            cid = u.get("chapter_id")
            if cid:
                recruits_by_chapter[cid] = recruits_by_chapter.get(cid, 0) + 1

        # ---- Checkins per chapter ----
        checkins_by_chapter: dict = {}
        async for c in db.checkins.find(
            {"checked_in_at": {"$gte": year_start, "$lte": year_end}},
            {"_id": 0, "user_id": 1},
        ):
            uid = c.get("user_id")
            u = users_map.get(uid or "") or {}
            cid = u.get("chapter_id")
            if cid:
                checkins_by_chapter[cid] = checkins_by_chapter.get(cid, 0) + 1

        # ---- Chapter member counts (at start of year — approximation via
        # current membership minus recruits added during the year) ----
        chapter_member_counts: dict = {}
        for u in users_map.values():
            cid = u.get("chapter_id")
            if not cid:
                continue
            chapter_member_counts[cid] = chapter_member_counts.get(cid, 0) + 1

        # ---- Service Ribbon ----
        def _year_of(iso_str: str) -> int:
            try:
                return int((iso_str or "")[:4])
            except Exception:
                return 0

        def streak_start_year(u: dict) -> int:
            """Year of the member's most recent active-membership start.
            Priority: latest reactivation entry in status_history → falls
            back to created_at."""
            history = u.get("status_history") or []
            # Look for the most recent transition to "active".
            last_active = None
            for h in history:
                if (h.get("status") or "").lower() == "active":
                    at = h.get("at") or ""
                    if not last_active or at > last_active:
                        last_active = at
            if last_active:
                return _year_of(last_active)
            return _year_of(u.get("created_at") or "")

        service_ribbon: list = []
        for uid, u in users_map.items():
            # Skip members currently marked inactive/deceased — they didn't
            # complete an active year.
            override = (u.get("status_override") or "").lower()
            if override in ("inactive", "expired", "deceased"):
                continue
            start_y = streak_start_year(u)
            if not start_y or start_y > year_i:
                continue
            years_complete = year_i - start_y
            if years_complete <= 0:
                continue
            eligible = years_complete == 1 or (years_complete >= 5 and years_complete % 5 == 0)
            if not eligible:
                continue
            service_ribbon.append(user_row(
                uid,
                years_complete=years_complete,
                milestone="1st year" if years_complete == 1 else f"{years_complete}th year",
                streak_start_year=start_y,
            ))
        service_ribbon.sort(key=lambda r: (-r["years_complete"], r["name"]))

        # ---- Fundraiser Ribbon (top donor) ----
        fundraiser_candidates = sorted(
            [(uid, amt) for uid, amt in donors_by_user.items() if amt > 0],
            key=lambda x: -x[1],
        )
        fundraiser_ribbon = [
            user_row(uid, amount=round(amt, 2), rank=i + 1)
            for i, (uid, amt) in enumerate(fundraiser_candidates[:5])
        ]

        # ---- Community Service Ribbon (>= 100 hrs) ----
        community_service = [
            user_row(uid, hours=round(hrs, 2))
            for uid, hrs in hours_by_user.items() if hrs >= 100.0
        ]
        community_service.sort(key=lambda r: -r["hours"])

        # ---- Dr. Ken Thompson — top per chapter by weighted AOP-event hours.
        # Weighted score = 0.90 * AOP + 0.05 * Trendsetters + 0.05 * Other.
        ken_thompson: list = []
        best_per_chapter: dict = {}
        for uid, u in users_map.items():
            cid = u.get("chapter_id")
            if not cid:
                continue
            aop = aop_by_user.get(uid, 0.0)
            trend = trend_by_user.get(uid, 0.0)
            other = other_by_user.get(uid, 0.0)
            if aop + trend + other <= 0:
                continue
            score = 0.90 * aop + 0.05 * trend + 0.05 * other
            cur = best_per_chapter.get(cid)
            if not cur or score > cur[0]:
                best_per_chapter[cid] = (score, uid, aop, trend, other)
        for cid, (score, uid, aop, trend, other) in best_per_chapter.items():
            ken_thompson.append(user_row(
                uid,
                weighted_score=round(score, 2),
                aop_hours=round(aop, 2),
                trendsetters_hours=round(trend, 2),
                other_hours=round(other, 2),
            ))
        ken_thompson.sort(key=lambda r: (r["chapter_name"], -r["weighted_score"]))

        # ---- Recruitment Ribbon ----
        recruit_candidates = sorted(
            [(uid, n) for uid, n in recruits_by_user.items() if n > 0],
            key=lambda x: -x[1],
        )
        recruitment_ribbon = [
            user_row(uid, recruits=n, rank=i + 1)
            for i, (uid, n) in enumerate(recruit_candidates[:5])
        ]

        # ---- Member's Ribbon (top 3 in each of hours/recruits/fundraising) ----
        top_hours = sorted(hours_by_user.items(), key=lambda x: -x[1])[:3]
        top_recruits = sorted(recruits_by_user.items(), key=lambda x: -x[1])[:3]
        top_fund = sorted(donors_by_user.items(), key=lambda x: -x[1])[:3]
        member_bucket: dict = {}
        for uid, hrs in top_hours:
            member_bucket.setdefault(uid, {"categories": []})["categories"].append(f"Hours ({round(hrs, 2)})")
        for uid, n in top_recruits:
            member_bucket.setdefault(uid, {"categories": []})["categories"].append(f"Recruits ({n})")
        for uid, amt in top_fund:
            member_bucket.setdefault(uid, {"categories": []})["categories"].append(f"Fundraising (${round(amt, 2)})")
        members_ribbon = [
            user_row(uid, categories=data["categories"], category_count=len(data["categories"]))
            for uid, data in member_bucket.items()
        ]
        members_ribbon.sort(key=lambda r: (-r["category_count"], r["name"]))

        # ---- Chapter of the Year ----
        chapter_of_the_year: list = []
        for cid, cname in chapters_map.items():
            recs = recruits_by_chapter.get(cid, 0)
            hrs = hours_by_chapter.get(cid, 0.0)
            donation_amount = donations_amount_by_chapter.get(cid, 0.0)
            checkins = checkins_by_chapter.get(cid, 0)
            member_count = chapter_member_counts.get(cid, 0)
            # Denominator = members BEFORE the year's recruits were added.
            base_members = max(1, member_count - recs)
            score = (recs + hrs + donation_amount + checkins) / base_members
            chapter_of_the_year.append({
                "chapter_id": cid,
                "chapter_name": cname,
                "recruits": recs,
                "hours": round(hrs, 2),
                "donation_amount": round(donation_amount, 2),
                "checkins": checkins,
                "base_members": base_members,
                "score": round(score, 2),
            })
        chapter_of_the_year.sort(key=lambda r: -r["score"])

        return {
            "year": year_i,
            "computed_at": iso(now_utc()),
            "service_ribbon": service_ribbon,
            "fundraiser_ribbon": fundraiser_ribbon,
            "community_service_ribbon": community_service,
            "ken_thompson": ken_thompson,
            "recruitment_ribbon": recruitment_ribbon,
            "members_ribbon": members_ribbon,
            "chapter_of_the_year": chapter_of_the_year,
        }
