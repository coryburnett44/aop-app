"""Iter 134 — Regions endpoint tests.

Covers:
  1. GET /api/regions returns all 4 official regions with the expected
     state lists.
  2. Member state values (case-insensitive, USPS codes + full names)
     bucket into the right region.
  3. Members with a state that's not in any region roll into
     `unassigned_count`.
  4. Endpoint requires authentication.
  5. `region_for_state()` helper handles empty / unknown / variant input.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://club-express-lite.preview.emergentagent.com").rstrip("/") + "/api"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return s


def test_regions_endpoint_returns_all_four_regions():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/regions", timeout=15)
    assert r.status_code == 200
    body = r.json()
    ids = [r["id"] for r in body["regions"]]
    assert ids == ["central-east", "gulf-coast", "southeastern", "mid-atlantic"]


def test_region_state_lists_are_complete():
    admin = _login("admin@clubhaven.app", "Admin123!")
    body = admin.get(f"{BASE}/regions", timeout=15).json()
    by_id = {r["id"]: r for r in body["regions"]}
    # Central-East: WI, IL, IN, MI, OH, KY
    assert [s["code"] for s in by_id["central-east"]["states"]] == ["WI", "IL", "IN", "MI", "OH", "KY"]
    # Gulf Coast: TX, LA, AR, OK, MS
    assert [s["code"] for s in by_id["gulf-coast"]["states"]] == ["TX", "LA", "AR", "OK", "MS"]
    # Southeastern: NC, SC, TN, AL, GA, FL
    assert [s["code"] for s in by_id["southeastern"]["states"]] == ["NC", "SC", "TN", "AL", "GA", "FL"]
    # Mid-Atlantic: VA, WV, MD, DE, DC
    assert [s["code"] for s in by_id["mid-atlantic"]["states"]] == ["VA", "WV", "MD", "DE", "DC"]


def test_region_counts_change_when_state_is_set():
    """Set a member's state to Texas (Gulf Coast) and verify the total
    ticks up, then flip to Ohio (Central-East) and verify the movement."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    members = admin.get(f"{BASE}/members?limit=5", timeout=15).json()
    if isinstance(members, dict):
        members = members.get("items", [])
    uid = members[0]["id"]
    orig_state = members[0].get("state", "")

    def region_totals():
        body = admin.get(f"{BASE}/regions", timeout=15).json()
        return {r["id"]: r["total"] for r in body["regions"]}

    try:
        # Move member to Texas.
        admin.put(f"{BASE}/members/{uid}", json={"state": "Texas"}, timeout=15)
        totals_tx = region_totals()
        # Move to Ohio.
        admin.put(f"{BASE}/members/{uid}", json={"state": "Ohio"}, timeout=15)
        totals_oh = region_totals()
        # Gulf Coast total should be strictly greater when the member is in
        # Texas than when they've moved to Ohio.
        assert totals_tx["gulf-coast"] > totals_oh["gulf-coast"]
        assert totals_oh["central-east"] > totals_tx["central-east"]
    finally:
        admin.put(f"{BASE}/members/{uid}", json={"state": orig_state}, timeout=15)


def test_usps_state_codes_and_full_names_both_count():
    """A member listed with 'FL' should count the same as 'Florida' — both
    should show up in the Southeastern total."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    members = admin.get(f"{BASE}/members?limit=5", timeout=15).json()
    if isinstance(members, dict):
        members = members.get("items", [])
    uid = members[0]["id"]
    orig_state = members[0].get("state", "")

    def southeastern_total():
        body = admin.get(f"{BASE}/regions", timeout=15).json()
        return next(r["total"] for r in body["regions"] if r["id"] == "southeastern")

    try:
        admin.put(f"{BASE}/members/{uid}", json={"state": ""}, timeout=15)
        baseline = southeastern_total()
        admin.put(f"{BASE}/members/{uid}", json={"state": "FL"}, timeout=15)
        with_code = southeastern_total()
        admin.put(f"{BASE}/members/{uid}", json={"state": "Florida"}, timeout=15)
        with_name = southeastern_total()
        assert with_code == baseline + 1
        assert with_name == baseline + 1
    finally:
        admin.put(f"{BASE}/members/{uid}", json={"state": orig_state}, timeout=15)


def test_unknown_state_rolls_into_unassigned():
    """A state we don't map (California) should show up in unassigned_count."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    members = admin.get(f"{BASE}/members?limit=5", timeout=15).json()
    if isinstance(members, dict):
        members = members.get("items", [])
    uid = members[0]["id"]
    orig_state = members[0].get("state", "")

    def unassigned():
        return admin.get(f"{BASE}/regions", timeout=15).json()["unassigned_count"]

    try:
        admin.put(f"{BASE}/members/{uid}", json={"state": "Ohio"}, timeout=15)
        baseline_unassigned = unassigned()
        admin.put(f"{BASE}/members/{uid}", json={"state": "California"}, timeout=15)
        after = unassigned()
        assert after == baseline_unassigned + 1
    finally:
        admin.put(f"{BASE}/members/{uid}", json={"state": orig_state}, timeout=15)


def test_regions_endpoint_requires_auth():
    r = requests.get(f"{BASE}/regions", timeout=15)
    assert r.status_code == 401


def test_region_for_state_helper():
    from routes.regions import region_for_state
    # Full names, USPS codes, common abbreviations.
    assert region_for_state("Texas")["region_id"] == "gulf-coast"
    assert region_for_state("TX")["region_id"] == "gulf-coast"
    assert region_for_state("Fla.")["region_id"] == "southeastern"
    assert region_for_state("WASHINGTON, D.C.")["region_id"] == "mid-atlantic"
    assert region_for_state("d.c.")["region_id"] == "mid-atlantic"
    assert region_for_state("N.C.")["region_id"] == "southeastern"
    # Unknown or blank.
    assert region_for_state("California") is None
    assert region_for_state("") is None
    assert region_for_state(None) is None
