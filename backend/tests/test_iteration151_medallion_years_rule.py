"""Iteration 151 — Medallion 'consecutive years' rule clarification.

User rule (verbatim): "For the Medallion Club, all members that have been
in the organization since or before 4 August 2023 without a record of
inactivity has three consecutive years of service. Those members who were
inactive and paid dues afterwards will not count as having consecutive
years. Go off of the members' join date."

Concretely — the medallion `years_of_service` value for each member should be:

  - Based on the member's `join_date` (or `joined_at` / `created_at` fallback),
    NOT the last reactivation entry.
  - **Zero** if the member has EVER been inactive (either
    `status_override == 'inactive'`/`deceased`, or any 'inactive'/
    'deactivation'/'deceased' entry in `status_history`). A subsequent
    reactivation does NOT restart their consecutive-years clock.

This test seeds three synthetic users and asserts the exact numeric output.
"""
import os
import time
import uuid
from datetime import datetime, timezone

import requests

API = (os.environ.get("REACT_APP_BACKEND_URL") or "https://club-express-lite.preview.emergentagent.com").rstrip("/") + "/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@clubhaven.app")
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", "Admin123!")


def _login():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=10)
    r.raise_for_status()
    return r.json().get("access_token") or r.json().get("token")


def _seed_and_measure():
    """Insert three synthetic users directly into MongoDB and return their
    ids. We hit Mongo directly because the medallion criteria depend on
    specific fields (`join_date`, `status_history`) that aren't exposed
    on the admin create-member API in preview."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def seed():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        seed_ids = []
        # 1. Joined Aug 1, 2023, never inactive → 3 consecutive years.
        never_inactive = str(uuid.uuid4())
        await db.users.insert_one({
            "id": never_inactive,
            "email": f"iter151-never-{never_inactive[:8]}@test.local",
            "name": "Iter151 Never Inactive",
            "role": "member",
            "join_date": "2023-08-01",
            "joined_at": "2023-08-01T00:00:00Z",
            "created_at": "2023-08-01T00:00:00Z",
            "status_history": [],
            "chapter_id": None,
        })
        seed_ids.append(("never_inactive", never_inactive))

        # 2. Joined Aug 1, 2020, was inactive at some point → zero years.
        was_inactive = str(uuid.uuid4())
        await db.users.insert_one({
            "id": was_inactive,
            "email": f"iter151-was-{was_inactive[:8]}@test.local",
            "name": "Iter151 Was Inactive",
            "role": "member",
            "join_date": "2020-08-01",
            "joined_at": "2020-08-01T00:00:00Z",
            "created_at": "2020-08-01T00:00:00Z",
            "status_history": [
                {"at": "2022-01-01T00:00:00Z", "status": "inactive"},
                {"at": "2023-06-01T00:00:00Z", "status": "active"},
            ],
            "chapter_id": None,
        })
        seed_ids.append(("was_inactive", was_inactive))

        # 3. Joined Feb 2024, never inactive → ~2 consecutive years (as of
        # early Aug 2026). Regardless of exact count, must be non-zero
        # and < 3.
        two_year = str(uuid.uuid4())
        await db.users.insert_one({
            "id": two_year,
            "email": f"iter151-two-{two_year[:8]}@test.local",
            "name": "Iter151 Two Year",
            "role": "member",
            "join_date": "2024-02-01",
            "joined_at": "2024-02-01T00:00:00Z",
            "created_at": "2024-02-01T00:00:00Z",
            "status_history": [],
            "chapter_id": None,
        })
        seed_ids.append(("two_year", two_year))

        client.close()
        return dict(seed_ids)

    async def teardown(ids):
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.users.delete_many({"id": {"$in": list(ids.values())}})
        client.close()

    ids = asyncio.run(seed())
    return ids, lambda: asyncio.run(teardown(ids))


def test_medallion_consecutive_years_matches_user_rule():
    ids, cleanup = _seed_and_measure()
    try:
        token = _login()
        hdrs = {"Authorization": f"Bearer {token}"}
        j = requests.get(f"{API}/awards/medallion-eligibility", headers=hdrs, timeout=15).json()
        bronze_by_uid = {r["user_id"]: r for r in j["bronze"]}

        never = bronze_by_uid.get(ids["never_inactive"])
        was = bronze_by_uid.get(ids["was_inactive"])
        two = bronze_by_uid.get(ids["two_year"])

        assert never is not None, "never-inactive user missing from bronze list"
        assert was is not None, "was-inactive user missing from bronze list"
        assert two is not None, "two-year user missing from bronze list"

        # Rule 1: joined 2023-08-01 without inactivity → >= 3 years.
        # (Today is Aug 2026 or later; running earlier will still give >= 3
        # once the 3-year anniversary passes. Test is defensive.)
        today = datetime.now(timezone.utc).date()
        joined_2023 = datetime(2023, 8, 1, tzinfo=timezone.utc).date()
        expected_never = today.year - joined_2023.year - (
            (today.month, today.day) < (joined_2023.month, joined_2023.day)
        )
        assert never["years_of_service"] == expected_never, f"got {never['years_of_service']}, expected {expected_never}"

        # Rule 2: ever-inactive → 0 regardless of join date or reactivation.
        assert was["years_of_service"] == 0, f"ever-inactive should be 0, got {was['years_of_service']}"
        assert was["criteria_met"]["years"] is False

        # Rule 3: joined 2024-02-01 without inactivity → < 3 years.
        assert two["years_of_service"] < 3, f"expected <3 years for Feb-2024 join, got {two['years_of_service']}"
        assert two["criteria_met"]["years"] is False
    finally:
        cleanup()


def test_medallion_bronze_criterion_meets_at_three_years():
    """Fresh user who joined exactly 3 years ago (with no inactivity) should
    have the 'years' criterion satisfied for Bronze."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from datetime import timedelta

    exact_three_years = (datetime.now(timezone.utc).date() - timedelta(days=365 * 3 + 5)).isoformat()
    uid = str(uuid.uuid4())

    async def seed():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.users.insert_one({
            "id": uid,
            "email": f"iter151-{uid[:8]}@test.local",
            "name": "Iter151 Exactly 3y",
            "role": "member",
            "join_date": exact_three_years,
            "status_history": [],
            "chapter_id": None,
        })
        client.close()

    async def teardown():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.users.delete_one({"id": uid})
        client.close()

    asyncio.run(seed())
    try:
        token = _login()
        hdrs = {"Authorization": f"Bearer {token}"}
        j = requests.get(f"{API}/awards/medallion-eligibility", headers=hdrs, timeout=15).json()
        row = next((r for r in j["bronze"] if r["user_id"] == uid), None)
        assert row is not None
        assert row["years_of_service"] >= 3
        assert row["criteria_met"]["years"] is True
    finally:
        asyncio.run(teardown())
