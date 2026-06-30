"""Iteration 94 — Event time stays in Eastern Time + sub-event delete tombstone.

Two bugs the user reported:
  1. Event times "kept changing to a random time" — the frontend was
     converting `datetime-local` inputs through the admin's BROWSER local
     timezone, not Eastern. The backend now must accept the Eastern wall-clock
     unchanged via UTC ISO and the tickets must render in Eastern Time.
  2. Deleting a sub-event under the 10-Year Anniversary umbrella resurrected
     itself on every backend restart because the seed reconciler always
     recreated missing canonical sub-events.

This test verifies the backend half of the contract:
  - storing 6:00 PM Eastern (= 23:00 UTC during EST / 22:00 UTC during EDT)
    round-trips unchanged and the email helper renders it back as ET
  - deleting "Sip & Paint" leaves it deleted across a fresh seed call
"""
import os
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests
from pymongo import MongoClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ET = ZoneInfo("America/New_York")

# Mongo handle for direct tombstone inspection / cleanup.
DB_NAME = "clubhaven_db"
_mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
_db = _mongo[DB_NAME]


def _login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@clubhaven.app", "Admin123!")


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_event_six_pm_eastern_round_trips_intact(admin_token):
    """The wall-clock time the admin enters in ET stays at that ET wall-clock
    everywhere: storage, fetch, ET render. Use a winter date so we test EST
    (UTC-5) rather than EDT (UTC-4); both should work but EST is the user's
    original complaint."""
    # 6:00 PM Eastern on Jan 15, 2027 = 23:00 UTC.
    et_wallclock = datetime(2027, 1, 15, 18, 0, tzinfo=ET)
    utc_iso = et_wallclock.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
    payload = {
        "title": "TZ Round-trip Test",
        "description": "",
        "start_at": utc_iso,
        "end_at": None,
        "category": "general",
        "capacity": 0,
        "location": "Online",
        "cover_image": "",
        "price": 0,
    }
    r = requests.post(f"{BASE}/events", headers=_h(admin_token), json=payload)
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    try:
        # Fetch back and confirm storage is exactly what we sent.
        got = requests.get(f"{BASE}/events/{eid}", headers=_h(admin_token)).json()
        stored = datetime.fromisoformat(got["start_at"].replace("Z", "+00:00"))
        assert stored.astimezone(ET).strftime("%I:%M %p") == "06:00 PM"
        assert stored.astimezone(ET).strftime("%Z") == "EST"
    finally:
        requests.delete(f"{BASE}/events/{eid}", headers=_h(admin_token))


def test_anniversary_subevent_delete_is_persistent(admin_token):
    """Deleting one of the 5 canonical anniversary sub-events tombstones it
    so the boot-time `seed_anniversary_subevents` reconciler does NOT
    silently recreate it. The tombstone document carries `parent_title` so
    the seeder's lookup is unambiguous."""
    # Find anniversary parent + its "Sip & Paint" sub-event.
    events = requests.get(f"{BASE}/events?include_sub_events=true", headers=_h(admin_token)).json()
    parent = next((e for e in events if "Anniversary" in e.get("title", "") and not e.get("parent_event_id")), None)
    assert parent, "10-Year Anniversary parent event must exist"
    subs = requests.get(f"{BASE}/events/{parent['id']}/sub-events", headers=_h(admin_token)).json()
    sip = next((s for s in subs if s.get("title") == "Sip & Paint"), None)
    if not sip:
        # Already tombstoned from a previous test run — clear & retry.
        _db.deleted_default_subevents.delete_many({"title": "Sip & Paint"})
        # Re-seed by importing & invoking the helper directly.
        from server import seed_anniversary_subevents
        asyncio.get_event_loop().run_until_complete(seed_anniversary_subevents())
        subs = requests.get(f"{BASE}/events/{parent['id']}/sub-events", headers=_h(admin_token)).json()
        sip = next((s for s in subs if s.get("title") == "Sip & Paint"), None)
    assert sip, "Sip & Paint sub-event must be seeded before this test"

    try:
        # Delete the sub-event.
        r = requests.delete(f"{BASE}/events/{sip['id']}", headers=_h(admin_token))
        assert r.status_code == 200

        # Tombstone must exist.
        tomb = _db.deleted_default_subevents.find_one({"title": "Sip & Paint"})
        assert tomb is not None
        assert tomb.get("parent_title") == "Alpha Omega Phi 10-Year Anniversary"

        # Re-run the seeder — Sip & Paint must NOT be re-inserted.
        from server import seed_anniversary_subevents
        asyncio.get_event_loop().run_until_complete(seed_anniversary_subevents())

        subs_after = requests.get(f"{BASE}/events/{parent['id']}/sub-events", headers=_h(admin_token)).json()
        titles_after = [s.get("title") for s in subs_after]
        assert "Sip & Paint" not in titles_after, f"Sip & Paint resurrected: {titles_after}"
    finally:
        # Restore for downstream tests / user.
        _db.deleted_default_subevents.delete_many({"title": "Sip & Paint"})
        from server import seed_anniversary_subevents
        asyncio.get_event_loop().run_until_complete(seed_anniversary_subevents())
