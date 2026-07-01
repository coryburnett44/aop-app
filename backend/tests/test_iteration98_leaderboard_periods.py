"""Iteration 98 — Homepage leaderboards support explicit Q1-Q4 + year period switch.

User request: "On the home page for the top leader boards, allow members to
switch between quarters within the current year, and entire year. Do not
show 'All Time'."

Backend contract this test locks in:
  - GET /api/leaderboards/community-service?period={q1|q2|q3|q4|year}
  - GET /api/leaderboards/top-donors?period={q1|q2|q3|q4|year}
  - Each returns a `period_label` that matches the requested period so the
    homepage subtitle stays honest.
  - Q1 data does NOT leak into Q2 (explicit end_iso bounds every quarter).
"""
import os
from datetime import datetime, timezone

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def _login(email, pwd):
    return requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}).json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@clubhaven.app", "Admin123!")


def _h(t):
    return {"Authorization": f"Bearer {t}"}


CURRENT_YEAR = datetime.now(timezone.utc).year


@pytest.mark.parametrize("endpoint", ["community-service", "top-donors"])
@pytest.mark.parametrize("period,expected_label", [
    ("q1", f"Q1 {CURRENT_YEAR}"),
    ("q2", f"Q2 {CURRENT_YEAR}"),
    ("q3", f"Q3 {CURRENT_YEAR}"),
    ("q4", f"Q4 {CURRENT_YEAR}"),
    ("year", str(CURRENT_YEAR)),
])
def test_named_periods_return_correct_label(admin_token, endpoint, period, expected_label):
    r = requests.get(f"{BASE}/leaderboards/{endpoint}?period={period}", headers=_h(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("period_label") == expected_label
    # top_chapters + top_members must always be lists (possibly empty).
    assert isinstance(body.get("top_chapters"), list)
    assert isinstance(body.get("top_members"), list)


@pytest.mark.parametrize("endpoint", ["community-service", "top-donors"])
def test_q1_does_not_include_data_after_march(admin_token, endpoint):
    """Regression guard: before iter98 each quarter query only had a $gte
    lower bound, so requesting Q1 after March would leak later data. We now
    bound Q1 with both start (Jan 1) AND end (Mar 31 23:59:59). Assert by
    contrast with Q1+Q2+Q3+Q4 vs the year total for community-service
    (which has seeded data)."""
    if endpoint == "top-donors":
        pytest.skip("Top donors has no seeded data — can't cross-verify.")
    quarters = []
    for q in ["q1", "q2", "q3", "q4"]:
        r = requests.get(f"{BASE}/leaderboards/{endpoint}?period={q}", headers=_h(admin_token))
        quarters.append(r.json())
    year = requests.get(f"{BASE}/leaderboards/{endpoint}?period=year", headers=_h(admin_token)).json()
    # Sum of chapter totals per quarter should equal the year total for any
    # given chapter (approx — floating point). Pick "Unassigned" (any that
    # has data across quarters is fine).
    all_chapter_ids = set()
    for q in quarters + [year]:
        for c in q.get("top_chapters", []):
            all_chapter_ids.add(c.get("chapter_id") or c.get("name"))
    for cid in all_chapter_ids:
        q_sum = 0.0
        for q in quarters:
            row = next((c for c in q["top_chapters"] if (c.get("chapter_id") or c.get("name")) == cid), None)
            if row:
                q_sum += float(row.get("hours") or 0)
        year_row = next((c for c in year["top_chapters"] if (c.get("chapter_id") or c.get("name")) == cid), None)
        year_val = float(year_row.get("hours") or 0) if year_row else 0.0
        # Quarterly sums may not perfectly equal year total when quarter
        # top-5 truncation kicks in, so allow either equal-or-lesser.
        assert q_sum <= year_val + 0.01, f"Q sum ({q_sum}) exceeds year ({year_val}) for chapter {cid} — quarter leaked"


def test_all_time_still_works_for_admin_reports(admin_token):
    """The `period=all` query is still supported at the API level — admins
    may need it for private reporting even though the homepage no longer
    exposes it."""
    r = requests.get(f"{BASE}/leaderboards/community-service?period=all", headers=_h(admin_token))
    assert r.status_code == 200
    assert r.json().get("period_label") == "All time"
