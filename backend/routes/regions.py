"""Iter 134 — Region → State → Member-count endpoint.

Defines the 4 official AOP regions and their member states. Exposes a
single `GET /api/regions` endpoint that returns each region with a live
count of how many members live in each state, plus a region total.

Members are matched by their `state` field (top-level, per iter 132
findings). State names are normalized case-insensitively so historical
variants like "Fla.", "FL", "Florida" all count under the same bucket.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends


# ---------- Region definitions ----------
#
# NOTE: Each state entry lists every string variant we accept when
# matching members. `name` is the canonical display label; `match` is a
# list of case-insensitive variants (full names, USPS codes, and common
# abbreviations) that all count toward the state's tally.
REGIONS: list[dict] = [
    {
        "id": "central-east",
        "name": "Central-East Region",
        "description": "Wisconsin, Illinois, Indiana, Michigan, Ohio, Kentucky",
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
        "states": [
            {"code": "VA", "name": "Virginia",       "match": ["virginia", "va", "va."]},
            {"code": "WV", "name": "West Virginia",  "match": ["west virginia", "wv", "w.v.", "w. virginia"]},
            {"code": "MD", "name": "Maryland",       "match": ["maryland", "md", "md."]},
            {"code": "DE", "name": "Delaware",       "match": ["delaware", "de", "del."]},
            {"code": "DC", "name": "Washington, D.C.", "match": ["washington, d.c.", "washington d.c.", "washington dc", "d.c.", "dc", "district of columbia"]},
        ],
    },
]


# Lookup table: normalized state variant → (region_id, state_code, state_name)
_STATE_INDEX: dict[str, tuple[str, str, str]] = {}
for _region in REGIONS:
    for _state in _region["states"]:
        for _variant in _state["match"]:
            _STATE_INDEX[_variant.strip().lower()] = (_region["id"], _state["code"], _state["name"])


def region_for_state(raw_state: Optional[str]) -> Optional[dict]:
    """Return `{region_id, state_code, state_name}` or None if the state
    doesn't match any known variant. Used by the Directory region filter
    and any admin analytics that need a canonical bucket."""
    if not raw_state:
        return None
    key = str(raw_state).strip().lower()
    if not key:
        return None
    hit = _STATE_INDEX.get(key)
    if not hit:
        return None
    return {"region_id": hit[0], "state_code": hit[1], "state_name": hit[2]}


def _empty_counts_for(region: dict) -> dict:
    """Fresh count skeleton for a region — every state starts at 0."""
    return {
        "id": region["id"],
        "name": region["name"],
        "description": region["description"],
        "total": 0,
        "states": [
            {"code": s["code"], "name": s["name"], "count": 0}
            for s in region["states"]
        ],
    }


def register(api, *, db, get_current_user):

    @api.get("/regions")
    async def list_regions(_: dict = Depends(get_current_user)):
        """List every region with per-state member counts. Members are
        counted by their top-level `state` field (case-insensitive across
        the accepted variants defined in this module).

        Returns:
        {
          "regions": [
            {
              "id": "...", "name": "...", "description": "...",
              "total": <int>,
              "states": [{ "code": "TX", "name": "Texas", "count": 42 }, ...]
            },
            ...
          ],
          "unassigned_count": <int>,   # members whose state doesn't match any region
        }
        """
        # Aggregate raw state -> count once, then map into region buckets.
        # We do this in Python (not $group) because state values need
        # variant-normalization that MongoDB can't do without a huge $switch.
        pipeline = [
            {"$match": {"state": {"$nin": [None, ""]}}},
            {"$group": {"_id": {"$toLower": {"$trim": {"input": "$state"}}}, "n": {"$sum": 1}}},
        ]
        raw_counts = await db.users.aggregate(pipeline).to_list(2000)
        # Build results.
        regions_out = {r["id"]: _empty_counts_for(r) for r in REGIONS}
        unassigned = 0
        for row in raw_counts:
            key = (row.get("_id") or "").strip().lower()
            n = int(row.get("n") or 0)
            hit = _STATE_INDEX.get(key)
            if not hit:
                unassigned += n
                continue
            rid, scode, _sname = hit
            bucket = regions_out[rid]
            bucket["total"] += n
            for s in bucket["states"]:
                if s["code"] == scode:
                    s["count"] += n
                    break
        return {
            "regions": [regions_out[r["id"]] for r in REGIONS],
            "unassigned_count": unassigned,
        }
