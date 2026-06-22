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
from datetime import datetime
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
