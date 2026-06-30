"""Iteration 95 — Member self-edits branch of service from Profile, admin sees same value.

The backend `ProfileUpdateIn` model already exposed `branch_of_service`, so
this test just exercises the round-trip + verifies the admin's member list
reflects the member's self-update. The frontend now drives this via a
canonical dropdown (Army / Air Force / Marine Corps / Navy / Coast Guard /
Space Force) — backend stays free-text for backwards compatibility with
legacy values.
"""
import os

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
BRANCHES = ["Army", "Air Force", "Marine Corps", "Navy", "Coast Guard", "Space Force"]


def _login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def member_token():
    return _login("member@clubhaven.app", "Member123!")


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@clubhaven.app", "Admin123!")


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.mark.parametrize("branch", BRANCHES)
def test_member_can_set_each_canonical_branch(member_token, admin_token, branch):
    # Member updates their own branch_of_service via /members/me.
    r = requests.put(
        f"{BASE}/members/me",
        headers=_h(member_token),
        json={"branch_of_service": branch},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("branch_of_service") == branch

    # Admin sees the same value in the member list.
    me = requests.get(f"{BASE}/auth/me", headers=_h(member_token)).json()
    listing = requests.get(f"{BASE}/members", headers=_h(admin_token)).json()
    row = next((x for x in listing if x["id"] == me["id"]), None)
    assert row is not None
    assert row.get("branch_of_service") == branch


def test_member_can_clear_branch(member_token):
    # Set then clear — empty string should round-trip.
    requests.put(f"{BASE}/members/me", headers=_h(member_token), json={"branch_of_service": "Navy"})
    r = requests.put(f"{BASE}/members/me", headers=_h(member_token), json={"branch_of_service": ""})
    assert r.status_code == 200
    assert r.json().get("branch_of_service") in ("", None)


def test_legacy_freeform_value_still_accepted(member_token):
    """Old data in production may have free-form strings (e.g. "Marines",
    "USAF") — confirm the backend still accepts non-canonical input so we
    don't break import scripts or legacy admin edits."""
    r = requests.put(f"{BASE}/members/me", headers=_h(member_token), json={"branch_of_service": "USAF"})
    assert r.status_code == 200
    assert r.json().get("branch_of_service") == "USAF"
    # Restore a canonical value for the next test run.
    requests.put(f"{BASE}/members/me", headers=_h(member_token), json={"branch_of_service": "Army"})
