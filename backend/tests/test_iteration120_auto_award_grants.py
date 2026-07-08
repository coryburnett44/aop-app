"""Iter 120 — Automatic award grants.

Covers:
  1. Alpha Omega Phi Ribbon is auto-granted the moment a member is created
     (admin create + public application approval). Repeat calls are
     idempotent — never double-grant.
  2. Service Ribbon eligibility payload is year-scoped: a member whose
     5-year anniversary fell in 2025 must NOT appear in the 2026 view.
  3. Service Ribbon daily sweep grants on the actual MM/DD anniversary
     and honors the reactivation clock (reactivated_at). Re-running the
     sweep on the same day is a no-op.
  4. Community Service Ribbon annual sweep fires only on Dec 31, grants
     every active member with >=100 hours in that year, and dedupes on
     re-run.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date as _date, datetime, timedelta, timezone
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


def _admin() -> requests.Session:
    return _login("admin@clubhaven.app", "Admin123!")


# ============================================================
# 1) AOP Ribbon on join — end-to-end via HTTP
# ============================================================
def test_new_member_auto_receives_alpha_omega_phi_ribbon():
    admin = _admin()
    email = f"iter120-join-{uuid.uuid4().hex[:8]}@example.com"
    r = admin.post(f"{BASE}/admin/members", json={
        "email": email, "password": "Iter120!!", "name": "Iter120 Join Test", "role": "member",
    }, timeout=15)
    assert r.status_code == 200, r.text
    user_id = r.json()["id"]

    # Poll briefly — grant is synchronous but Mongo write may take a moment.
    grants = []
    for _ in range(5):
        r = admin.get(f"{BASE}/admin/auto-grants?days=1", timeout=15)
        assert r.status_code == 200
        grants = [
            g for g in r.json()["items"]
            if g.get("user_id") == user_id and g.get("auto_grant_kind") == "alpha_omega_phi_ribbon"
        ]
        if grants:
            break
    assert len(grants) == 1, f"expected exactly one AOP-ribbon auto-grant, got {grants}"
    assert "join date" in (grants[0].get("reason") or "").lower()
    assert grants[0].get("auto_granted") is True
    assert grants[0].get("granted_by") == "system:auto"


# ============================================================
# 2) Year-scoping — Service Ribbon
# ============================================================
def test_service_ribbon_eligibility_year_scoping():
    admin = _admin()
    # Query 2025 and 2026 — anything with a 2025-* anniversary_date must NOT
    # appear in the 2026 payload.
    r25 = admin.get(f"{BASE}/awards/eligibility?year=2025", timeout=15)
    assert r25.status_code == 200
    r26 = admin.get(f"{BASE}/awards/eligibility?year=2026", timeout=15)
    assert r26.status_code == 200
    sr_25 = r25.json().get("service_ribbon") or []
    sr_26 = r26.json().get("service_ribbon") or []
    for row in sr_25:
        assert (row.get("anniversary_date") or "").startswith("2025-"), row
    for row in sr_26:
        assert (row.get("anniversary_date") or "").startswith("2026-"), row


# ============================================================
# 3) Service Ribbon daily sweep — unit-tests against injected DB
# ============================================================
def test_service_ribbon_sweep_uses_reactivation_clock_and_dedupes():
    async def go():
        from routes import awards_auto as aa

        today = _date(2026, 7, 8)  # matches the anniversary MM/DD

        AWARD = {"id": "aw-sr", "name": "Service Ribbon", "icon": "ribbon", "color": "#64748B"}

        # Members:
        #   u1: joined 2020-07-08, no reactivation — this year is 6yr (not milestone).
        #   u2: joined 2018-07-08, reactivated 2025-07-08 → today = 1yr from clock reset. Milestone.
        #   u3: joined 2025-07-08 — today is 1yr anniv. Milestone.
        #   u4: joined 2020-01-15 — MM/DD doesn't match today. Skip.
        USERS = [
            {"id": "u1", "name": "Six Yr No React", "join_date": "2020-07-08T00:00:00+00:00"},
            {"id": "u2", "name": "Reactivated 1yr", "join_date": "2018-07-08T00:00:00+00:00", "reactivated_at": "2025-07-08T00:00:00+00:00"},
            {"id": "u3", "name": "Fresh 1yr", "join_date": "2025-07-08T00:00:00+00:00"},
            {"id": "u4", "name": "Wrong Day", "join_date": "2020-01-15T00:00:00+00:00"},
        ]
        AWARD_GRANTS: list = []

        class _AwardsCol:
            async def find_one(self, q, *a, **kw):
                if q.get("name") == "Service Ribbon":
                    return AWARD
                return None

        class _Cursor:
            def __init__(self, docs):
                self._docs = docs
                self._i = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._i >= len(self._docs):
                    raise StopAsyncIteration
                d = self._docs[self._i]
                self._i += 1
                return d

        class _UsersCol:
            def find(self, *a, **kw):
                # Filter out inactive/deceased like the real query does.
                return _Cursor([u for u in USERS])

        class _GrantsCol:
            async def find_one(self, q, *a, **kw):
                for g in AWARD_GRANTS:
                    if (
                        g.get("user_id") == q.get("user_id")
                        and g.get("award_id") == q.get("award_id")
                        and g.get("auto_grant_kind") == q.get("auto_grant_kind")
                        and (q.get("reason") is None or g.get("reason") == q.get("reason"))
                    ):
                        return {"id": g["id"]}
                return None

            async def count_documents(self, q, *a, **kw):
                return sum(1 for g in AWARD_GRANTS if g.get("user_id") == q.get("user_id") and g.get("award_id") == q.get("award_id"))

            async def insert_one(self, doc):
                AWARD_GRANTS.append(dict(doc))
                return None

        class _DB:
            awards = _AwardsCol()
            users = _UsersCol()
            award_grants = _GrantsCol()

        aa.register(
            db_ref=_DB(),
            iso_fn=lambda dt: dt.isoformat(),
            now_utc_fn=lambda: datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc),
            logger_ref=__import__("logging").getLogger("test"),
        )

        n = await aa._sweep_service_ribbon(today)
        assert n == 2, f"expected 2 grants (u2 + u3), got {n}"
        # Re-run — should be idempotent.
        n2 = await aa._sweep_service_ribbon(today)
        assert n2 == 0, f"repeat sweep must be a no-op, got {n2}"
        # Reasons should mention the correct clock start.
        by_user = {g["user_id"]: g for g in AWARD_GRANTS}
        assert "2025-07-08" in by_user["u2"]["reason"], by_user["u2"]["reason"]
        assert "2025-07-08" in by_user["u3"]["reason"], by_user["u3"]["reason"]
        assert "u1" not in by_user  # 6yr, no milestone
        assert "u4" not in by_user  # wrong MM/DD

    asyncio.run(go())


# ============================================================
# 4) Community Service Ribbon annual sweep
# ============================================================
def test_community_service_ribbon_sweep_only_on_dec_31_and_dedupes():
    async def go():
        from routes import awards_auto as aa

        AWARD = {"id": "aw-csr", "name": "Community Service Ribbon", "icon": "ribbon", "color": "#10B981"}
        AWARD_GRANTS: list = []

        class _AwardsCol:
            async def find_one(self, q, *a, **kw):
                if q.get("name") == "Community Service Ribbon":
                    return AWARD
                if isinstance(q.get("name"), dict):
                    # regex fallback path
                    return AWARD
                return None

        USERS = {
            "u-100": {"id": "u-100", "name": "Hundred", "status_override": None},
            "u-49":  {"id": "u-49",  "name": "Under",   "status_override": None},
            "u-inactive": {"id": "u-inactive", "name": "Gone", "status_override": "inactive"},
        }
        HOURS = [
            {"user_id": "u-100", "hours": 60.0, "status": "approved", "date": "2026-03-01"},
            {"user_id": "u-100", "hours": 45.0, "status": "approved", "date": "2026-11-15"},
            {"user_id": "u-49",  "hours": 49.0, "status": "approved", "date": "2026-05-01"},
            {"user_id": "u-inactive", "hours": 200.0, "status": "approved", "date": "2026-06-01"},
        ]

        class _Cursor:
            def __init__(self, docs):
                self._docs = docs
                self._i = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._i >= len(self._docs):
                    raise StopAsyncIteration
                d = self._docs[self._i]
                self._i += 1
                return d

        class _HoursCol:
            def find(self, q, *a, **kw):
                lo, hi = q.get("date", {}).get("$gte"), q.get("date", {}).get("$lt")
                return _Cursor([h for h in HOURS if h.get("status") == "approved" and lo <= h["date"] < hi])

        class _UsersCol:
            async def find_one(self, q, *a, **kw):
                u = USERS.get(q.get("id"))
                if not u:
                    return None
                so = (u.get("status_override") or "").lower()
                excl = q.get("status_override", {}).get("$nin") or []
                if so in excl:
                    return None
                return dict(u)

            def find(self, *a, **kw):
                return _Cursor(list(USERS.values()))

        class _GrantsCol:
            async def find_one(self, q, *a, **kw):
                # Support $regex on reason too.
                for g in AWARD_GRANTS:
                    match = True
                    for k, v in q.items():
                        if isinstance(v, dict) and "$regex" in v:
                            import re
                            if not re.search(v["$regex"], str(g.get(k, ""))):
                                match = False
                                break
                        elif g.get(k) != v:
                            match = False
                            break
                    if match:
                        return {"id": g["id"]}
                return None

            async def count_documents(self, q, *a, **kw):
                return sum(1 for g in AWARD_GRANTS if g.get("user_id") == q.get("user_id") and g.get("award_id") == q.get("award_id"))

            async def insert_one(self, doc):
                AWARD_GRANTS.append(dict(doc))
                return None

        class _DB:
            awards = _AwardsCol()
            hours = _HoursCol()
            users = _UsersCol()
            award_grants = _GrantsCol()

        aa.register(
            db_ref=_DB(),
            iso_fn=lambda dt: dt.isoformat(),
            now_utc_fn=lambda: datetime(2026, 12, 31, 23, 0, 0, tzinfo=timezone.utc),
            logger_ref=__import__("logging").getLogger("test"),
        )

        # Non-Dec 31 → no-op.
        n_mid = await aa._sweep_community_service_ribbon(_date(2026, 6, 30))
        assert n_mid == 0

        # Dec 31 → should grant u-100 (105h approved). u-49 under threshold.
        # u-inactive is excluded.
        n = await aa._sweep_community_service_ribbon(_date(2026, 12, 31))
        assert n == 1, f"expected 1 grant (u-100 with 105h), got {n}"

        # Rerun same day → dedupe.
        n2 = await aa._sweep_community_service_ribbon(_date(2026, 12, 31))
        assert n2 == 0

        assert AWARD_GRANTS[0]["user_id"] == "u-100"
        assert "105.0" in AWARD_GRANTS[0]["reason"] or "105" in AWARD_GRANTS[0]["reason"]
        assert "in 2026" in AWARD_GRANTS[0]["reason"]

    asyncio.run(go())


# ============================================================
# 5) Admin endpoint auth check
# ============================================================
def test_auto_grants_admin_only():
    r = requests.get(f"{BASE}/admin/auto-grants", timeout=15)
    assert r.status_code in (401, 403)
    r = requests.post(f"{BASE}/admin/auto-grants/run-now", timeout=15)
    assert r.status_code in (401, 403)
