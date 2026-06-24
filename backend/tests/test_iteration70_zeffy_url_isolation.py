"""Iteration 70 — Verify PUT /api/members/{id} cannot mutate outstanding_zeffy_url.

This is the security boundary that originally caused the admin UX bug
(admin pasted URL into the URL field then clicked the dialog's bottom
'Save changes' — the URL was silently dropped because that endpoint
intentionally ignores `outstanding_zeffy_url`). Verify the boundary still
holds after the auto-save-on-blur UI fix.
"""
import os
import pytest
import httpx

API_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not API_BASE:
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)

API = f"{API_BASE.rstrip('/')}/api"
ADMIN = ("admin@clubhaven.app", "Admin123!")
MAYA_EMAIL = "maya.patel@clubhaven.app"


@pytest.fixture
def admin_client():
    c = httpx.Client(timeout=15.0, follow_redirects=True)
    r = c.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
    assert r.status_code == 200, r.text
    yield c
    c.close()


@pytest.fixture
def maya_id(admin_client):
    rows = admin_client.get(f"{API}/members").json()
    return next(m["id"] for m in rows if m["email"] == MAYA_EMAIL)


def test_put_members_does_not_touch_zeffy_url(admin_client, maya_id):
    # 1. Set a Zeffy URL via the dedicated endpoint.
    saved_url = "https://www.zeffy.com/en-US/ticketing/iter70-boundary"
    r = admin_client.put(
        f"{API}/admin/members/{maya_id}/balance/zeffy-url",
        json={"url": saved_url},
    )
    assert r.status_code == 200
    assert r.json()["zeffy_url"] == saved_url

    # 2. Read the current member record to build a faithful PUT payload.
    member = admin_client.get(f"{API}/members/{maya_id}").json()

    # 3. Build a PUT body that mimics what the admin dialog sends, plus a
    #    malicious extra field attempting to overwrite outstanding_zeffy_url
    #    AND a different value to test the boundary holds.
    put_body = {
        "name": member.get("name"),
        "email": member.get("email"),
        "role": member.get("role"),
        "chapter_id": member.get("chapter_id"),
        "membership_expires_at": member.get("membership_expires_at"),
        "member_status": member.get("member_status") or "active",
        # Attempt to inject — must be silently ignored by server.
        "outstanding_zeffy_url": "https://evil.example.com/hijack",
    }
    r2 = admin_client.put(f"{API}/members/{maya_id}", json=put_body)
    assert r2.status_code in (200, 204), r2.text

    # 4. Re-read the balance and confirm the URL is unchanged.
    bal = admin_client.get(f"{API}/admin/members/{maya_id}/balance").json()
    assert bal["zeffy_url"] == saved_url, (
        f"SECURITY: PUT /members/{{id}} mutated outstanding_zeffy_url! "
        f"Expected {saved_url!r}, got {bal['zeffy_url']!r}"
    )

    # Cleanup: clear URL
    admin_client.put(
        f"{API}/admin/members/{maya_id}/balance/zeffy-url", json={"url": ""}
    )
