"""Iter 134/135 — Region model + endpoints.

Iter 134 introduced 4 hardcoded regions with per-state member counts.
Iter 135 promotes them to a Mongo-backed CRUD so admins can:
  • Add / edit / delete regions.
  • Assign a Governor to each region (surfaces a spotlight card on the
    public /regions page).
  • Move members between regions regardless of their `state` value via a
    per-user `region_override` field.
  • Click a state on the /regions page to see the exact members who live
    there (or were manually assigned to that region).

The 4 official regions ship as seed defaults on first boot when the
`app_regions` collection is empty.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel


# ---------- Seed defaults ----------
DEFAULT_REGIONS: list[dict] = [
    {
        "id": "central-east",
        "name": "Central-East Region",
        "description": "Wisconsin, Illinois, Indiana, Michigan, Ohio, Kentucky",
        "color": "#0284C7",  # sky-600
        "gradient_from": "#0EA5E9",
        "gradient_to": "#2563EB",
        "emoji": "🌾",
        "governor_user_id": "",
        "order": 1,
        "states": [
            {"code": "WI", "name": "Wisconsin",   "match": ["wisconsin", "wi", "wisc.", "wisc"]},
            {"code": "IL", "name": "Illinois",    "match": ["illinois", "il", "ill.", "ill"]},
            {"code": "IN", "name": "Indiana",     "match": ["indiana", "in", "ind.", "ind"]},
            {"code": "MI", "name": "Michigan",    "match": ["michigan", "mi", "mich.", "mich"]},
            {"code": "OH", "name": "Ohio",        "match": ["ohio", "oh"]},
            {"code": "KY", "name": "Kentucky",    "match": ["kentucky", "ky", "ken."]},
        ],
    },
    {
        "id": "gulf-coast",
        "name": "Gulf Coast Region",
        "description": "Texas, Louisiana, Arkansas, Oklahoma, Mississippi",
        "color": "#EA580C",  # orange-600
        "gradient_from": "#F97316",
        "gradient_to": "#DC2626",
        "emoji": "🌊",
        "governor_user_id": "",
        "order": 2,
        "states": [
            {"code": "TX", "name": "Texas",       "match": ["texas", "tx", "tex."]},
            {"code": "LA", "name": "Louisiana",   "match": ["louisiana", "la", "la."]},
            {"code": "AR", "name": "Arkansas",    "match": ["arkansas", "ar", "ark."]},
            {"code": "OK", "name": "Oklahoma",    "match": ["oklahoma", "ok", "okla."]},
            {"code": "MS", "name": "Mississippi", "match": ["mississippi", "ms", "miss."]},
        ],
    },
    {
        "id": "southeastern",
        "name": "Southeastern Region",
        "description": "North Carolina, South Carolina, Tennessee, Alabama, Georgia, Florida",
        "color": "#059669",  # emerald-600
        "gradient_from": "#10B981",
        "gradient_to": "#0D9488",
        "emoji": "🌴",
        "governor_user_id": "",
        "order": 3,
        "states": [
            {"code": "NC", "name": "North Carolina", "match": ["north carolina", "nc", "n.c.", "n. carolina"]},
            {"code": "SC", "name": "South Carolina", "match": ["south carolina", "sc", "s.c.", "s. carolina"]},
            {"code": "TN", "name": "Tennessee",      "match": ["tennessee", "tn", "tenn."]},
            {"code": "AL", "name": "Alabama",        "match": ["alabama", "al", "ala."]},
            {"code": "GA", "name": "Georgia",        "match": ["georgia", "ga", "ga."]},
            {"code": "FL", "name": "Florida",        "match": ["florida", "fl", "fla."]},
        ],
    },
    {
        "id": "mid-atlantic",
        "name": "Mid-Atlantic Region",
        "description": "Virginia, West Virginia, Maryland, Delaware, Washington, D.C.",
        "color": "#7C3AED",  # violet-600
        "gradient_from": "#8B5CF6",
        "gradient_to": "#4F46E5",
        "emoji": "🏛️",
        "governor_user_id": "",
        "order": 4,
        "states": [
            {"code": "VA", "name": "Virginia",       "match": ["virginia", "va", "va."]},
            {"code": "WV", "name": "West Virginia",  "match": ["west virginia", "wv", "w.v.", "w. virginia"]},
            {"code": "MD", "name": "Maryland",       "match": ["maryland", "md", "md."]},
            {"code": "DE", "name": "Delaware",       "match": ["delaware", "de", "del."]},
            {"code": "DC", "name": "Washington, D.C.", "match": ["washington, d.c.", "washington d.c.", "washington dc", "d.c.", "dc", "district of columbia"]},
        ],
    },
]


# ---------- Pydantic ----------
class RegionStateIn(BaseModel):
    code: str
    name: str
    match: Optional[list[str]] = None  # variants; defaults to [name.lower, code.lower]


class RegionIn(BaseModel):
    name: str
    description: str = ""
    color: str = "#0A2463"
    gradient_from: Optional[str] = None
    gradient_to: Optional[str] = None
    emoji: str = "📍"
    governor_user_id: str = ""
    order: int = 100
    states: list[RegionStateIn] = []


class RegionUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    gradient_from: Optional[str] = None
    gradient_to: Optional[str] = None
    emoji: Optional[str] = None
    governor_user_id: Optional[str] = None
    order: Optional[int] = None
    states: Optional[list[RegionStateIn]] = None


class MemberRegionOverrideIn(BaseModel):
    # Empty string clears the override so the member falls back to their state.
    region_id: str = ""


# ---------- Helpers ----------
def _region_variants(region: dict) -> list[str]:
    """Flatten all state variants for a region into a single lookup list."""
    out: list[str] = []
    for s in region.get("states", []):
        for v in (s.get("match") or [s.get("name", ""), s.get("code", "")]):
            if v:
                out.append(str(v).strip().lower())
    return out


def _build_state_index(regions: list[dict]) -> dict[str, tuple[str, str, str]]:
    """Normalized state variant → (region_id, state_code, state_name)."""
    idx: dict[str, tuple[str, str, str]] = {}
    for r in regions:
        for s in r.get("states", []):
            code = s.get("code") or ""
            name = s.get("name") or ""
            variants = s.get("match") or [name, code]
            for v in variants:
                if v:
                    idx[str(v).strip().lower()] = (r["id"], code, name)
    return idx


def _normalize_states(states) -> list[dict]:
    """Fill in missing `match` variants (name.lower + code.lower + code.lower.)."""
    out = []
    for s in (states or []):
        if hasattr(s, "model_dump"):
            s = s.model_dump()
        code = (s.get("code") or "").strip()
        name = (s.get("name") or "").strip()
        raw_match = s.get("match") or []
        base = {code.lower(), name.lower(), f"{code.lower()}."} if code or name else set()
        merged = sorted({v.strip().lower() for v in (list(raw_match) + list(base)) if v and v.strip()})
        out.append({"code": code, "name": name, "match": merged})
    return out


# ---------- Register ----------
_db_ref = None  # bound in register(), also used by region_for_state helper


async def _load_regions() -> list[dict]:
    """Load regions sorted by order."""
    if _db_ref is None:
        return DEFAULT_REGIONS
    docs = await _db_ref.app_regions.find({}, {"_id": 0}).sort([("order", 1), ("name", 1)]).to_list(200)
    return docs or DEFAULT_REGIONS


async def region_for_state(raw_state: Optional[str]) -> Optional[dict]:
    """Public helper — returns the region a state belongs to. Async now
    because it consults the DB for the latest custom regions."""
    if not raw_state:
        return None
    key = str(raw_state).strip().lower()
    if not key:
        return None
    regions = await _load_regions()
    idx = _build_state_index(regions)
    hit = idx.get(key)
    if not hit:
        return None
    return {"region_id": hit[0], "state_code": hit[1], "state_name": hit[2]}


async def seed_default_regions_if_empty(db):
    """First-boot seed. Skips silently if the collection already has rows
    so admins can safely delete/modify defaults without them coming back."""
    count = await db.app_regions.count_documents({})
    if count > 0:
        return
    await db.app_regions.insert_many([{**r} for r in DEFAULT_REGIONS])


def register(api, *, db, get_current_user, admin_tab_dep, public_user):
    global _db_ref
    _db_ref = db

    # -------- Public/read --------
    @api.get("/regions")
    async def list_regions_endpoint(_: dict = Depends(get_current_user)):
        """List every region with per-state member counts + governor card."""
        regions = await _load_regions()
        idx = _build_state_index(regions)

        # Aggregate raw state → count.
        pipeline = [
            {"$match": {"state": {"$nin": [None, ""]}}},
            {"$group": {"_id": {"$toLower": {"$trim": {"input": "$state"}}}, "n": {"$sum": 1}}},
        ]
        raw_counts = await db.users.aggregate(pipeline).to_list(2000)

        # Also collect per-region OVERRIDES so admin-moved members always
        # count under the region they're assigned to (regardless of state).
        override_agg = await db.users.aggregate([
            {"$match": {"region_override": {"$nin": [None, ""]}}},
            {"$group": {"_id": "$region_override", "n": {"$sum": 1}}},
        ]).to_list(200)
        override_by_region: dict[str, int] = {row["_id"]: int(row["n"]) for row in override_agg}

        # Build result skeleton.
        out = []
        governor_ids = [r.get("governor_user_id") for r in regions if r.get("governor_user_id")]
        governors: dict[str, dict] = {}
        if governor_ids:
            gov_docs = await db.users.find({"id": {"$in": governor_ids}}).to_list(len(governor_ids))
            for gd in gov_docs:
                governors[gd["id"]] = public_user(gd)

        # We need to subtract override-moved members from their original
        # state-derived region so the "total" reflects reality.
        # Strategy: first bucket every state-based user, then for each
        # overridden user we subtract from their state-region and add to
        # the override region.
        # This requires the raw user list — but only for those with an
        # override set. Small subset.
        overridden_users = await db.users.find(
            {"region_override": {"$nin": [None, ""]}},
            {"_id": 0, "id": 1, "state": 1, "region_override": 1},
        ).to_list(2000)

        region_totals: dict[str, int] = {r["id"]: 0 for r in regions}
        state_counts: dict[tuple[str, str], int] = {}
        unassigned = 0
        for row in raw_counts:
            key = (row.get("_id") or "").strip().lower()
            n = int(row.get("n") or 0)
            hit = idx.get(key)
            if not hit:
                unassigned += n
                continue
            rid, scode, _sname = hit
            region_totals[rid] = region_totals.get(rid, 0) + n
            state_counts[(rid, scode)] = state_counts.get((rid, scode), 0) + n

        # Apply overrides: for each overridden user, subtract 1 from
        # (state_region, state_code) and add 1 to override_region.
        for u in overridden_users:
            override_rid = u.get("region_override")
            if not override_rid or override_rid not in region_totals:
                continue
            src = idx.get((u.get("state") or "").strip().lower())
            if src:
                src_rid, src_scode, _ = src
                region_totals[src_rid] = max(0, region_totals.get(src_rid, 0) - 1)
                key = (src_rid, src_scode)
                state_counts[key] = max(0, state_counts.get(key, 0) - 1)
            else:
                # Was previously in unassigned bucket.
                unassigned = max(0, unassigned - 1)
            region_totals[override_rid] = region_totals.get(override_rid, 0) + 1

        for r in regions:
            gov = governors.get(r.get("governor_user_id") or "")
            out.append({
                "id": r["id"],
                "name": r.get("name", ""),
                "description": r.get("description", ""),
                "color": r.get("color", "#0A2463"),
                "gradient_from": r.get("gradient_from", r.get("color", "#0A2463")),
                "gradient_to": r.get("gradient_to", r.get("color", "#0A2463")),
                "emoji": r.get("emoji", "📍"),
                "order": r.get("order", 100),
                "governor_user_id": r.get("governor_user_id") or "",
                "governor": gov,
                "total": region_totals.get(r["id"], 0),
                "states": [
                    {
                        "code": s.get("code", ""),
                        "name": s.get("name", ""),
                        "count": state_counts.get((r["id"], s.get("code", "")), 0),
                    }
                    for s in r.get("states", [])
                ],
            })
        return {"regions": out, "unassigned_count": unassigned}

    @api.get("/regions/{region_id}/members")
    async def list_region_members(
        region_id: str,
        state_code: Optional[str] = None,
        _: dict = Depends(get_current_user),
    ):
        """Members that belong to this region (by state OR by manual
        override). Optionally scoped to a single `state_code` inside the
        region so the frontend can render a "Members in Ohio" drawer."""
        regions = await _load_regions()
        region = next((r for r in regions if r["id"] == region_id), None)
        if not region:
            raise HTTPException(status_code=404, detail="Region not found")

        # Which state variants belong to this region (optionally to a
        # single state within it)?
        if state_code:
            state = next((s for s in region.get("states", []) if s.get("code") == state_code), None)
            if not state:
                raise HTTPException(status_code=404, detail="State not part of this region")
            variants = [v for v in (state.get("match") or [state.get("name", ""), state_code])]
        else:
            variants = _region_variants(region)

        variants_lc = [v.strip().lower() for v in variants if v and v.strip()]

        # Members whose state matches (excluding those overridden into a
        # different region) OR whose region_override == this region.
        # Case-insensitive state match via $regex ^{variant}$.
        import re
        state_conditions = [{"state": re.compile(rf"^{re.escape(v)}$", re.I)} for v in variants_lc]
        query = {
            "$or": [
                # State matches AND (no override OR override is this region).
                {"$and": [
                    {"$or": state_conditions} if state_conditions else {"_no_match": True},
                    {"$or": [
                        {"region_override": {"$in": [None, ""]}},
                        {"region_override": region_id},
                    ]},
                ]},
                # Overridden into this region explicitly (state can be anything).
                {"region_override": region_id, **({"state": re.compile(rf"^{re.escape(state_code)}$", re.I)} if state_code else {})},
            ]
        }
        # If we're scoped to a specific state_code AND the override case
        # requires state match too, that filter's fine. If not scoped, we
        # only need the override branch.
        if not state_conditions:
            query = {"region_override": region_id}
        users = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("name", 1).to_list(2000)
        return {
            "region_id": region_id,
            "state_code": state_code or "",
            "count": len(users),
            "members": [public_user(u) for u in users],
        }

    # -------- Admin CRUD --------
    @api.post("/admin/regions")
    async def create_region(body: RegionIn, admin: dict = Depends(admin_tab_dep("regions"))):
        # Simple slug generator: lowercase name with dashes.
        base_id = "-".join((body.name or "region").lower().split())
        rid = base_id
        i = 2
        while await db.app_regions.find_one({"id": rid}):
            rid = f"{base_id}-{i}"
            i += 1
        doc = {
            "id": rid,
            "name": body.name,
            "description": body.description,
            "color": body.color,
            "gradient_from": body.gradient_from or body.color,
            "gradient_to": body.gradient_to or body.color,
            "emoji": body.emoji,
            "governor_user_id": body.governor_user_id or "",
            "order": body.order,
            "states": _normalize_states(body.states),
        }
        await db.app_regions.insert_one(doc)
        return doc

    @api.put("/admin/regions/{region_id}")
    async def update_region(region_id: str, body: RegionUpdateIn, admin: dict = Depends(admin_tab_dep("regions"))):
        existing = await db.app_regions.find_one({"id": region_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Region not found")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "states" in updates:
            updates["states"] = _normalize_states(updates["states"])
        # Governor picker sends "" to clear.
        if "governor_user_id" in updates and updates["governor_user_id"]:
            # Sanity check the user exists.
            u = await db.users.find_one({"id": updates["governor_user_id"]})
            if not u:
                raise HTTPException(status_code=400, detail="Governor user not found")
        await db.app_regions.update_one({"id": region_id}, {"$set": updates})
        out = await db.app_regions.find_one({"id": region_id}, {"_id": 0})
        return out

    @api.delete("/admin/regions/{region_id}")
    async def delete_region(region_id: str, admin: dict = Depends(admin_tab_dep("regions"))):
        existing = await db.app_regions.find_one({"id": region_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Region not found")
        await db.app_regions.delete_one({"id": region_id})
        # Clear any per-member overrides pointing to it.
        await db.users.update_many({"region_override": region_id}, {"$set": {"region_override": ""}})
        return {"ok": True, "id": region_id}

    @api.put("/admin/members/{user_id}/region")
    async def set_member_region_override(
        user_id: str, body: MemberRegionOverrideIn,
        admin: dict = Depends(admin_tab_dep("members")),
    ):
        u = await db.users.find_one({"id": user_id})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        override = (body.region_id or "").strip()
        if override:
            r = await db.app_regions.find_one({"id": override})
            if not r:
                raise HTTPException(status_code=400, detail="Region not found")
        await db.users.update_one({"id": user_id}, {"$set": {"region_override": override}})
        return {"user_id": user_id, "region_override": override}
