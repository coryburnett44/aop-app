"""Iteration 38 backend tests:
- Gear external-link fields (name_html, is_external_link, external_url) on POST/GET/PUT
- Sub-event creation on a non-anniversary parent event
- /api/email/upload-image returns a usable URL
"""
import io
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@clubhaven.app", "password": "Admin123!"})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def member_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "member@clubhaven.app", "password": "Member123!"})
    assert r.status_code == 200, f"member login failed: {r.status_code} {r.text}"
    return s


# ---------- F2a: Gear external-link backend fields ----------
class TestGearExternalLink:
    def test_create_external_link_gear(self, admin_session):
        payload = {
            "name": "TEST_External Gear",
            "name_html": "<strong>Visit Partner Store</strong>",
            "is_external_link": True,
            "external_url": "https://example.com/store",
            "category": "apparel",
        }
        r = admin_session.post(f"{API}/gear", json=payload)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data["is_external_link"] is True
        assert data["external_url"] == "https://example.com/store"
        assert data["name_html"] == "<strong>Visit Partner Store</strong>"
        assert "id" in data
        gid = data["id"]

        # GET to verify persistence
        rg = admin_session.get(f"{API}/gear/{gid}")
        assert rg.status_code == 200
        g = rg.json()
        assert g["is_external_link"] is True
        assert g["external_url"] == "https://example.com/store"
        assert g["name_html"] == "<strong>Visit Partner Store</strong>"

        # Listed in /gear
        rl = admin_session.get(f"{API}/gear")
        assert rl.status_code == 200
        ids = [i["id"] for i in rl.json()]
        assert gid in ids

        # PUT toggle off external mode
        ru = admin_session.put(f"{API}/gear/{gid}", json={"is_external_link": False, "price": 25.50})
        assert ru.status_code == 200
        u = ru.json()
        assert u["is_external_link"] is False
        assert u["price"] == 25.50

        # Cleanup
        admin_session.delete(f"{API}/gear/{gid}")

    def test_regular_gear_defaults(self, admin_session):
        payload = {"name": "TEST_Regular Gear", "price": 10.0, "category": "apparel"}
        r = admin_session.post(f"{API}/gear", json=payload)
        assert r.status_code in (200, 201)
        d = r.json()
        assert d["is_external_link"] is False
        assert d["external_url"] == ""
        assert d["name_html"] == ""
        admin_session.delete(f"{API}/gear/{d['id']}")


# ---------- F3: Sub-events on any parent event ----------
class TestSubEventsAnyParent:
    def test_create_sub_event_under_arbitrary_parent(self, admin_session):
        # Find a non-sub-event to use as parent
        r = admin_session.get(f"{API}/events")
        assert r.status_code == 200
        events = r.json()
        # Filter to events with no parent_event_id (top-level)
        parents = [e for e in events if not e.get("parent_event_id")]
        assert parents, "No top-level parent events found"
        parent = parents[0]
        parent_id = parent["id"]

        # Create sub-event
        payload = {
            "title": "TEST_Sub Event Iter38",
            "category": "social",
            "start_at": "2026-06-01T18:00:00Z",
            "end_at": "2026-06-01T20:00:00Z",
            "location": "Test venue",
            "parent_event_id": parent_id,
            "allow_ticket_types": False,
        }
        rc = admin_session.post(f"{API}/events", json=payload)
        assert rc.status_code in (200, 201), rc.text
        sub = rc.json()
        assert sub.get("parent_event_id") == parent_id
        sub_id = sub["id"]

        # Verify it appears in parent's sub-events listing
        rl = admin_session.get(f"{API}/events/{parent_id}/sub-events")
        assert rl.status_code == 200
        subs = rl.json()
        sub_match = [e for e in subs if e["id"] == sub_id]
        assert sub_match, "Created sub-event not in parent's /sub-events list"
        assert sub_match[0].get("parent_event_id") == parent_id

        # Also verify it appears in /events when include_sub_events=true
        rl2 = admin_session.get(f"{API}/events?include_sub_events=true")
        assert rl2.status_code == 200
        assert any(e["id"] == sub_id for e in rl2.json())

        # Cleanup
        admin_session.delete(f"{API}/events/{sub_id}")

    def test_member_cannot_create_event(self, member_session):
        payload = {"title": "TEST_Member Event", "category": "social", "start_at": "2026-06-01T18:00:00Z"}
        r = member_session.post(f"{API}/events", json=payload)
        assert r.status_code in (401, 403)


# ---------- F4: /api/email/upload-image ----------
class TestUploadImageEndpoint:
    def test_admin_upload_image(self, admin_session):
        # 1x1 transparent PNG
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
            b"\xc0\x00\x00\x00\x03\x00\x01\\\xcd\xff i\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        files = {"file": ("test.png", io.BytesIO(png), "image/png")}
        r = admin_session.post(f"{API}/email/upload-image", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        # Expect either {"url": ".."} or {"image_url": ".."}
        url = body.get("url") or body.get("image_url") or body.get("path")
        assert url, f"No url field in response: {body}"
        assert "/api/files/" in url or url.startswith("http"), f"unexpected url: {url}"
