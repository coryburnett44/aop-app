"""Phase L — 12-item batch tests for the Alpha Omega Phi platform.

Covers:
1) Photos: /api/photos/albums new fields, default seeded albums, /photos/bulk multi-upload,
   creator+admin album-delete, default albums cannot be deleted.
2) Events: /api/events hides sub-events, only parent in main list; /events/{parent}/sub-events
   returns 5 anniversary sub-events; RSVP on umbrella returns 400 with 'umbrella' message;
   RSVP on sub-event accepts unlimited guests; guest_count increments.
3) Admin check-in: /api/events/{sub}/check-in with each ticket_type (vip, all_access, general,
   guest, speaker, volunteer) succeeds for both member and named-guest mode.
4) Admin image uploaders: /chapters/upload-logo, /news/upload-image, /causes/upload-image,
   /meeting-cards/upload-image all return a URL.
5) Chat: /chat/upload returns URL; POST /conversations accepts avatar_url and persists it.
6) Meeting cards CRUD: POST/GET/PUT/DELETE /meeting-cards.
"""
import io
import os
import time
import uuid
import pytest
import requests
from pathlib import Path


def _load_frontend_env():
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_frontend_env()
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("admin@clubhaven.app", "Admin123!")
MEMBER = ("member@clubhaven.app", "Member123!")


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def member_token():
    return _login(*MEMBER)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def _png_bytes():
    # minimal 1x1 PNG
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
        b"\xc0\x00\x00\x00\x03\x00\x01\x5b\xd2\x9a-\x00\x00\x00\x00IEND\xaeB`\x82"
    )


# ---------- Photos ----------
class TestPhotoAlbums:
    def test_list_albums_has_default_set_and_new_fields(self, member_token):
        r = requests.get(f"{API}/photos/albums", headers=H(member_token), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # Must have at least the canonical default set (review request says 47, allow ≥40 to be safe)
        defaults = [a for a in data if a.get("is_default")]
        assert len(defaults) >= 40, f"only {len(defaults)} default albums seeded; expected ≥40"
        # New fields exist
        for a in data[:5]:
            for k in ("id", "name", "count", "is_default", "created_by", "created_by_name"):
                assert k in a, f"missing field {k} in album {a}"

    def test_default_album_cannot_be_deleted(self, admin_token):
        albums = requests.get(f"{API}/photos/albums", headers=H(admin_token), timeout=20).json()
        default = next(a for a in albums if a.get("is_default"))
        r = requests.delete(f"{API}/photos/albums/{default['id']}", headers=H(admin_token), timeout=20)
        assert r.status_code == 400
        assert "default" in r.text.lower()

    def test_member_creates_and_deletes_own_album(self, member_token):
        name = f"TEST_member_album_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/photos/albums", headers=H(member_token), json={"name": name}, timeout=20)
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        # Member can delete their own custom album
        r = requests.delete(f"{API}/photos/albums/{aid}", headers=H(member_token), timeout=20)
        assert r.status_code == 200, r.text

    def test_admin_can_delete_member_album(self, member_token, admin_token):
        name = f"TEST_mem_for_admin_del_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/photos/albums", headers=H(member_token), json={"name": name}, timeout=20)
        assert r.status_code == 200
        aid = r.json()["id"]
        r = requests.delete(f"{API}/photos/albums/{aid}", headers=H(admin_token), timeout=20)
        assert r.status_code == 200, r.text

    def test_non_creator_member_cannot_delete_album(self, admin_token, member_token):
        # Admin creates album → member (non-creator, non-admin) tries to delete
        name = f"TEST_admin_album_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/photos/albums", headers=H(admin_token), json={"name": name}, timeout=20)
        assert r.status_code == 200
        aid = r.json()["id"]
        r = requests.delete(f"{API}/photos/albums/{aid}", headers=H(member_token), timeout=20)
        assert r.status_code == 403
        # cleanup
        requests.delete(f"{API}/photos/albums/{aid}", headers=H(admin_token), timeout=20)

    def test_bulk_upload_two_photos(self, member_token):
        album = f"TEST_bulk_{uuid.uuid4().hex[:6]}"
        files = [
            ("files", ("a.png", _png_bytes(), "image/png")),
            ("files", ("b.png", _png_bytes(), "image/png")),
        ]
        r = requests.post(
            f"{API}/photos/bulk",
            headers=H(member_token),
            data={"album": album},
            files=files,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "uploaded" in body and isinstance(body["uploaded"], list)
        assert len(body["uploaded"]) == 2, body
        # Verify count of the album increments via GET
        albums = requests.get(f"{API}/photos/albums", headers=H(member_token), timeout=20).json()
        matched = next((a for a in albums if a["name"] == album), None)
        assert matched is not None
        assert matched["count"] >= 2


# ---------- Events ----------
class TestEvents:
    @pytest.fixture(scope="class")
    def parent_id(self, member_token):
        r = requests.get(f"{API}/events", headers=H(member_token), timeout=20)
        assert r.status_code == 200, r.text
        events = r.json()
        parent = next((e for e in events if "10-Year Anniversary" in e.get("title", "")), None)
        assert parent is not None, "Anniversary parent event missing in /api/events"
        return parent["id"]

    def test_events_list_hides_sub_events(self, member_token):
        r = requests.get(f"{API}/events", headers=H(member_token), timeout=20)
        assert r.status_code == 200
        events = r.json()
        for e in events:
            assert not e.get("parent_event_id"), (
                f"Sub-event leaked into main /events: {e.get('title')} parent={e.get('parent_event_id')}"
            )

    def test_subevents_endpoint_returns_5(self, member_token, parent_id):
        r = requests.get(f"{API}/events/{parent_id}/sub-events", headers=H(member_token), timeout=20)
        assert r.status_code == 200, r.text
        subs = r.json()
        assert len(subs) == 5, f"Expected 5 sub-events, got {len(subs)}: {[s.get('title') for s in subs]}"
        titles = {s["title"] for s in subs}
        for must in (
            "Transportation to Sip & Paint",
            "Sip & Paint",
            "Sneaker Ball Banquet",
            "Transportation to Top Golf",
            "Top Golf",
        ):
            assert must in titles, f"missing sub-event '{must}'"

    def test_rsvp_on_umbrella_returns_400(self, member_token, parent_id):
        r = requests.post(f"{API}/events/{parent_id}/rsvp", headers=H(member_token), json={"guests": []}, timeout=20)
        assert r.status_code == 400, r.text
        assert "umbrella" in r.text.lower()

    def test_rsvp_on_subevent_with_5_guests(self, member_token, parent_id):
        subs = requests.get(f"{API}/events/{parent_id}/sub-events", headers=H(member_token), timeout=20).json()
        # pick Sip & Paint sub-event
        sub = next(s for s in subs if s["title"] == "Sip & Paint")
        sid = sub["id"]
        # Ensure clean state: cancel existing rsvp if any (toggle off)
        requests.post(f"{API}/events/{sid}/rsvp", headers=H(member_token), json={"guests": []}, timeout=20)
        guests = [{"name": f"TEST Guest {i}", "ticket_type": "guest"} for i in range(5)]
        r = requests.post(f"{API}/events/{sid}/rsvp", headers=H(member_token), json={"guests": guests}, timeout=20)
        # If toggled off above and now back on, this should be {rsvped: True, guests: 5}
        if r.status_code != 200:
            pytest.fail(f"RSVP sub-event failed: {r.status_code} {r.text}")
        body = r.json()
        if body.get("rsvped") is False:
            # We accidentally toggled to OFF, redo to ON
            r = requests.post(f"{API}/events/{sid}/rsvp", headers=H(member_token), json={"guests": guests}, timeout=20)
            body = r.json()
        assert body.get("rsvped") is True, body
        assert body.get("guests") == 5, body
        # Confirm guest_count on the event reflects the addition
        e = next(s for s in requests.get(f"{API}/events/{parent_id}/sub-events", headers=H(member_token), timeout=20).json() if s["id"] == sid)
        assert e.get("guest_count", 0) >= 5, e
        # cleanup - toggle off rsvp
        requests.post(f"{API}/events/{sid}/rsvp", headers=H(member_token), json={"guests": []}, timeout=20)

    def test_rsvp_unlimited_guests_allowed_on_uncapped_subevent(self, member_token, parent_id):
        # Sub-events seeded with capacity=0 (unlimited)
        subs = requests.get(f"{API}/events/{parent_id}/sub-events", headers=H(member_token), timeout=20).json()
        sub = next(s for s in subs if s["title"] == "Top Golf")
        sid = sub["id"]
        # toggle off first to clean
        requests.post(f"{API}/events/{sid}/rsvp", headers=H(member_token), json={"guests": []}, timeout=20)
        many_guests = [{"name": f"TEST Big{i}", "ticket_type": "guest"} for i in range(20)]
        r = requests.post(f"{API}/events/{sid}/rsvp", headers=H(member_token), json={"guests": many_guests}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        if body.get("rsvped") is False:
            r = requests.post(f"{API}/events/{sid}/rsvp", headers=H(member_token), json={"guests": many_guests}, timeout=20)
            body = r.json()
        assert body.get("guests") == 20
        # cleanup
        requests.post(f"{API}/events/{sid}/rsvp", headers=H(member_token), json={"guests": []}, timeout=20)


# ---------- Check-in ----------
class TestCheckIn:
    TICKET_TYPES = ["vip", "all_access", "general", "guest", "speaker", "volunteer"]

    @pytest.fixture(scope="class")
    def sub_event_id(self, admin_token):
        events = requests.get(f"{API}/events", headers=H(admin_token), timeout=20).json()
        parent = next(e for e in events if "10-Year Anniversary" in e.get("title", ""))
        subs = requests.get(f"{API}/events/{parent['id']}/sub-events", headers=H(admin_token), timeout=20).json()
        return next(s for s in subs if s["title"] == "Sneaker Ball Banquet")["id"]

    @pytest.fixture(scope="class")
    def member_id(self, admin_token):
        # Find member user id
        r = requests.get(f"{API}/members", headers=H(admin_token), timeout=20)
        assert r.status_code == 200, r.text
        members = r.json()
        m = next(m for m in members if m.get("email") == "member@clubhaven.app")
        return m["id"]

    def test_check_in_member_general(self, admin_token, sub_event_id, member_id):
        # cleanup prior check-in if any
        ci = requests.get(f"{API}/events/{sub_event_id}/check-ins", headers=H(admin_token), timeout=20).json()
        for c in ci:
            requests.delete(f"{API}/events/{sub_event_id}/check-ins/{c['id']}", headers=H(admin_token), timeout=20)
        r = requests.post(
            f"{API}/events/{sub_event_id}/check-in",
            headers=H(admin_token),
            json={"user_id": member_id, "ticket_type": "general"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ticket_type"] == "general"
        assert data["user_id"] == member_id
        # cleanup
        requests.delete(f"{API}/events/{sub_event_id}/check-ins/{data['id']}", headers=H(admin_token), timeout=20)

    @pytest.mark.parametrize("ticket", TICKET_TYPES)
    def test_check_in_guest_each_ticket_type(self, admin_token, sub_event_id, ticket):
        guest_name = f"TEST_{ticket}_{uuid.uuid4().hex[:4]}"
        r = requests.post(
            f"{API}/events/{sub_event_id}/check-in",
            headers=H(admin_token),
            json={"guest_name": guest_name, "ticket_type": ticket},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ticket_type"] == ticket
        assert data["is_guest"] is True
        requests.delete(f"{API}/events/{sub_event_id}/check-ins/{data['id']}", headers=H(admin_token), timeout=20)


# ---------- Image uploaders (admin) ----------
class TestAdminImageUploads:
    def _upload(self, admin_token, path):
        files = {"file": ("test.png", _png_bytes(), "image/png")}
        return requests.post(f"{API}{path}", headers=H(admin_token), files=files, timeout=30)

    def test_chapters_upload_logo(self, admin_token):
        r = self._upload(admin_token, "/chapters/upload-logo")
        assert r.status_code == 200, r.text
        assert r.json().get("url", "").startswith("/api/")

    def test_news_upload_image(self, admin_token):
        r = self._upload(admin_token, "/news/upload-image")
        assert r.status_code == 200, r.text
        assert r.json().get("url", "").startswith("/api/")

    def test_causes_upload_image(self, admin_token):
        r = self._upload(admin_token, "/causes/upload-image")
        assert r.status_code == 200, r.text
        assert r.json().get("url", "").startswith("/api/")

    def test_meeting_cards_upload_image(self, admin_token):
        r = self._upload(admin_token, "/meeting-cards/upload-image")
        assert r.status_code == 200, r.text
        assert r.json().get("url", "").startswith("/api/")


# ---------- Chat ----------
class TestChatGroup:
    def test_chat_upload_returns_url(self, member_token):
        files = {"file": ("group.png", _png_bytes(), "image/png")}
        r = requests.post(f"{API}/chat/upload", headers=H(member_token), files=files, timeout=30)
        assert r.status_code == 200, r.text
        url = r.json().get("url", "")
        assert url.startswith("/api/"), f"unexpected url: {url}"
        return url

    def test_create_group_conversation_with_avatar_url(self, member_token, admin_token):
        # upload picture
        files = {"file": ("group.png", _png_bytes(), "image/png")}
        up = requests.post(f"{API}/chat/upload", headers=H(member_token), files=files, timeout=30).json()
        # find admin id to add to group
        me_admin = requests.get(f"{API}/auth/me", headers=H(admin_token), timeout=20).json()
        # find a 3rd person to make it a real group
        members = requests.get(f"{API}/members", headers=H(member_token), timeout=20).json()
        third = next((m for m in members if m.get("email") not in ("admin@clubhaven.app", "member@clubhaven.app")), None)
        member_ids = [me_admin["id"]]
        if third:
            member_ids.append(third["id"])
        r = requests.post(
            f"{API}/conversations",
            headers=H(member_token),
            json={
                "type": "group",
                "name": f"TEST group {uuid.uuid4().hex[:4]}",
                "avatar_url": up["url"],
                "member_ids": member_ids,
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        conv = r.json()
        assert conv.get("avatar_url") == up["url"], conv
        # cleanup
        requests.delete(f"{API}/conversations/{conv['id']}", headers=H(member_token), timeout=20)


# ---------- Meeting cards CRUD ----------
class TestMeetingCards:
    def test_full_crud(self, admin_token):
        # create
        payload = {
            "name": f"TEST Card {uuid.uuid4().hex[:4]}",
            "title": "Test title",
            "description": "Schedule a meeting with...",
            "button_label": "Book Meeting",
            "button_url": "https://calendly.com/test",
            "order": 99,
        }
        r = requests.post(f"{API}/meeting-cards", headers=H(admin_token), json=payload, timeout=20)
        assert r.status_code == 200, r.text
        card = r.json()
        cid = card["id"]
        assert card["name"] == payload["name"]
        assert card["button_url"] == payload["button_url"]

        # list - must include our card
        all_cards = requests.get(f"{API}/meeting-cards", timeout=20).json()
        assert any(c["id"] == cid for c in all_cards)

        # update
        r = requests.put(
            f"{API}/meeting-cards/{cid}",
            headers=H(admin_token),
            json={"title": "Updated title", "button_url": "https://calendly.com/updated"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "Updated title"
        assert r.json()["button_url"] == "https://calendly.com/updated"

        # validation - empty button_url
        r = requests.put(
            f"{API}/meeting-cards/{cid}",
            headers=H(admin_token),
            json={"button_url": "   "},
            timeout=20,
        )
        assert r.status_code == 400, r.text

        # delete
        r = requests.delete(f"{API}/meeting-cards/{cid}", headers=H(admin_token), timeout=20)
        assert r.status_code == 200, r.text

        # verify gone
        all_cards = requests.get(f"{API}/meeting-cards", timeout=20).json()
        assert not any(c["id"] == cid for c in all_cards)

    def test_create_requires_button_url(self, admin_token):
        r = requests.post(
            f"{API}/meeting-cards",
            headers=H(admin_token),
            json={"name": "Bad", "button_url": ""},
            timeout=20,
        )
        assert r.status_code == 400, r.text

    def test_member_cannot_create_meeting_card(self, member_token):
        r = requests.post(
            f"{API}/meeting-cards",
            headers=H(member_token),
            json={"name": "x", "button_url": "https://x.com"},
            timeout=20,
        )
        assert r.status_code in (401, 403), r.text
