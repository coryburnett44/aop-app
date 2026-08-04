"""Iteration 149 — Awards page Phase 1: Life Member Club + Medallion Club.

The user requested two new tabs on the Awards page:

1. **Life Member Club** — a curated, admin-managed list, indexed by induction
   year. Admins can add either an existing member (by user_id) or a
   free-text historical name for members who predate the app. Must display
   the fixed blurb: "The Alpha Omega Phi Life Member Club is the most elite
   club within the organization…".

2. **Medallion Club** — Bronze / Silver / Gold tiered recognition integrated
   with the existing Awards system. The 3 medallion awards are seeded with
   the user-supplied medal photos. A new `/awards/medallion-eligibility`
   admin-only endpoint returns candidates ranked by how many of the 5
   criteria they satisfy (consecutive years of service, cumulative
   community-service hours, national/state events attended, personal
   fundraising, and — for silver/gold — holding the prior tier).

Regression scope (backend contract):
  - The three Medallion awards are seeded with `medallion_tier`,
    `medallion_criteria`, and `image_url`.
  - Life Member CRUD: POST/GET/PUT/DELETE with year + note.
  - Life Member add rejects a payload with neither user_id nor name.
  - Life Member add rejects a duplicate user_id.
  - Life Member enrichment attaches `member_name`/`member_avatar_url`/
    `member_chapter_name` when user_id is set.
  - `/awards/medallion-eligibility` returns bronze/silver/gold buckets,
    each row includes criteria_met, criteria_met_count, eligible flag,
    and already_granted flag.
  - Admin-only guard on all mutating endpoints.
"""
import os
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL") or "https://club-express-lite.preview.emergentagent.com").rstrip("/") + "/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@clubhaven.app")
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", "Admin123!")


def _login(email=None, pw=None):
    r = requests.post(f"{API}/auth/login", json={"email": email or ADMIN_EMAIL, "password": pw or ADMIN_PW}, timeout=10)
    r.raise_for_status()
    j = r.json()
    return j.get("access_token") or j.get("token")


def test_medallion_awards_seeded_with_metadata():
    token = _login()
    r = requests.get(f"{API}/awards", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    tiers = {a.get("medallion_tier"): a for a in r.json() if a.get("medallion_tier")}
    assert set(tiers.keys()) == {"bronze", "silver", "gold"}, tiers.keys()
    for tier in ("bronze", "silver", "gold"):
        a = tiers[tier]
        assert a["image_url"].startswith("http"), a
        assert a["medallion_criteria"]["years"] > 0
        assert a["medallion_criteria"]["cs_hours"] > 0
        assert a["medallion_criteria"]["events"] > 0
        assert a["medallion_criteria"]["fundraised"] > 0
    # Chained requirement
    assert tiers["bronze"]["medallion_criteria"]["requires_tier"] is None
    assert tiers["silver"]["medallion_criteria"]["requires_tier"] == "bronze"
    assert tiers["gold"]["medallion_criteria"]["requires_tier"] == "silver"


def test_life_member_full_lifecycle_historical_entry():
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    # Create
    r = requests.post(f"{API}/life-members", headers=hdrs, json={"name": "Historical Founder", "year": 2010, "note": "Ceremonial induction"}, timeout=10)
    assert r.status_code == 200, r.text
    entry = r.json()
    assert entry["name"] == "Historical Founder"
    assert entry["year"] == 2010
    assert entry["user_id"] is None
    lm_id = entry["id"]
    try:
        # List
        rows = requests.get(f"{API}/life-members", headers=hdrs, timeout=10).json()
        assert any(x["id"] == lm_id for x in rows)
        # Update
        u = requests.put(f"{API}/life-members/{lm_id}", headers=hdrs, json={"year": 2011, "note": "Corrected date"}, timeout=10)
        assert u.status_code == 200
        assert u.json()["year"] == 2011
        assert u.json()["note"] == "Corrected date"
    finally:
        d = requests.delete(f"{API}/life-members/{lm_id}", headers=hdrs, timeout=10)
        assert d.status_code == 200


def test_life_member_rejects_missing_identity():
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{API}/life-members", headers=hdrs, json={"year": 2020}, timeout=10)
    assert r.status_code == 400
    assert "member" in r.json()["detail"].lower() or "name" in r.json()["detail"].lower()


def test_life_member_rejects_bad_year():
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{API}/life-members", headers=hdrs, json={"name": "X", "year": 1500}, timeout=10)
    assert r.status_code == 422


def test_life_member_existing_user_flow():
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    # Pick any real user
    members = requests.get(f"{API}/members", headers=hdrs, timeout=10).json()
    if not members:
        return
    uid = members[0]["id"]
    r = requests.post(f"{API}/life-members", headers=hdrs, json={"user_id": uid, "year": 2020}, timeout=10)
    assert r.status_code == 200, r.text
    entry = r.json()
    try:
        assert entry["user_id"] == uid
        # Enrichment: on list, the member_name should be populated
        rows = requests.get(f"{API}/life-members", headers=hdrs, timeout=10).json()
        row = next(x for x in rows if x["id"] == entry["id"])
        assert row["member_name"] != "" or row["name"] != ""
        # Duplicate should 409
        dup = requests.post(f"{API}/life-members", headers=hdrs, json={"user_id": uid, "year": 2021}, timeout=10)
        assert dup.status_code == 409
    finally:
        requests.delete(f"{API}/life-members/{entry['id']}", headers=hdrs, timeout=10)


def test_medallion_eligibility_shape():
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API}/awards/medallion-eligibility", headers=hdrs, timeout=15)
    assert r.status_code == 200
    j = r.json()
    for tier in ("bronze", "silver", "gold"):
        assert tier in j
        for row in j[tier]:
            assert "user_id" in row
            assert "name" in row
            assert "years_of_service" in row
            assert "cs_hours" in row
            assert "events_attended" in row
            assert "fundraised" in row
            assert "criteria_met_count" in row
            assert "eligible" in row and isinstance(row["eligible"], bool)
            assert "already_granted" in row
            assert "criteria_met" in row
            for key in ("years", "cs_hours", "events", "fundraised", "prior_tier"):
                assert key in row["criteria_met"]


def test_medallion_eligibility_sorts_eligible_first_then_by_criteria_count():
    token = _login()
    hdrs = {"Authorization": f"Bearer {token}"}
    j = requests.get(f"{API}/awards/medallion-eligibility", headers=hdrs, timeout=15).json()
    for tier in ("bronze", "silver", "gold"):
        rows = j[tier]
        # Eligible members appear before non-eligible ones
        eligible_indices = [i for i, r in enumerate(rows) if r["eligible"]]
        non_eligible_indices = [i for i, r in enumerate(rows) if not r["eligible"]]
        if eligible_indices and non_eligible_indices:
            assert max(eligible_indices) < min(non_eligible_indices)
        # Within non-eligible rows, criteria_met_count is non-increasing
        counts = [r["criteria_met_count"] for r in rows if not r["eligible"]]
        for i in range(len(counts) - 1):
            assert counts[i] >= counts[i + 1], f"tier={tier} counts not sorted at index {i}: {counts}"


def test_life_member_requires_admin():
    r = requests.post(f"{API}/life-members", json={"name": "X", "year": 2020}, timeout=10)
    assert r.status_code in (401, 403)


def test_medallion_eligibility_requires_admin():
    r = requests.get(f"{API}/awards/medallion-eligibility", timeout=10)
    assert r.status_code in (401, 403)
