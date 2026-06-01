"""Phase K — Mobile-auth fix + admin membership-expiry + gear redesign tests."""
import io
import os
import pytest
import requests
from pathlib import Path

# Load REACT_APP_BACKEND_URL from frontend/.env (testing must hit the public URL)
def _load_backend_url():
    env_path = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for line in env_path.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found in frontend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or _load_backend_url()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}
MM = {"email": "mm.tx@clubhaven.app", "password": "MemMgr123!"}


def _login(creds):
    """Login and return (access_token, refresh_token, cookies, user_id)."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    return data.get("access_token"), data.get("refresh_token"), s.cookies, data.get("id"), data


@pytest.fixture(scope="module")
def admin_tokens():
    at, rt, _, uid, _ = _login(ADMIN)
    return {"access": at, "refresh": rt, "uid": uid}


@pytest.fixture(scope="module")
def member_tokens():
    at, rt, _, uid, _ = _login(MEMBER)
    return {"access": at, "refresh": rt, "uid": uid}


@pytest.fixture(scope="module")
def mm_tokens():
    at, rt, _, uid, _ = _login(MM)
    return {"access": at, "refresh": rt, "uid": uid}


# ---------- Mobile-auth fix ----------
class TestMobileAuth:
    def test_login_returns_tokens_in_body(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d.get("access_token"), str) and len(d["access_token"]) > 20
        assert isinstance(d.get("refresh_token"), str) and len(d["refresh_token"]) > 20
        # Cookies still set as well
        assert "access_token" in r.cookies or any(c.name == "access_token" for c in r.cookies)

    def test_register_returns_tokens_in_body(self):
        import uuid as _uuid
        email = f"TEST_reg_{_uuid.uuid4().hex[:8]}@clubhaven.app"
        r = requests.post(f"{API}/auth/register", json={
            "email": email, "password": "TestPass123!", "name": "TEST Reg User",
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("access_token"), str) and len(d["access_token"]) > 20
        assert isinstance(d.get("refresh_token"), str) and len(d["refresh_token"]) > 20

    def test_me_with_bearer_only_no_cookie(self, admin_tokens):
        # Fresh session — no cookies at all
        r = requests.get(
            f"{API}/auth/me",
            headers={"Authorization": f"Bearer {admin_tokens['access']}"},
            timeout=30,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == ADMIN["email"]

    def test_put_members_me_with_bearer_only_no_cookie(self, member_tokens):
        # The exact mobile bug — profile save with only Bearer token
        r = requests.put(
            f"{API}/members/me",
            json={"bio": "TEST mobile-auth bio"},
            headers={"Authorization": f"Bearer {member_tokens['access']}"},
            timeout=30,
        )
        assert r.status_code == 200, f"mobile profile save failed: {r.status_code} {r.text}"
        assert r.json()["bio"] == "TEST mobile-auth bio"

    def test_refresh_via_body(self, admin_tokens):
        r = requests.post(
            f"{API}/auth/refresh",
            json={"refresh_token": admin_tokens["refresh"]},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("access_token"), str) and len(d["access_token"]) > 20
        assert isinstance(d.get("refresh_token"), str) and len(d["refresh_token"]) > 20

    def test_refresh_via_bearer_header(self):
        # Get a fresh refresh token first
        _, rt, _, _, _ = _login(MEMBER)
        r = requests.post(
            f"{API}/auth/refresh",
            headers={"Authorization": f"Bearer {rt}"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()

    def test_refresh_via_cookie(self):
        s = requests.Session()
        login_r = s.post(f"{API}/auth/login", json=MEMBER, timeout=30)
        assert login_r.status_code == 200
        # Same session => cookie sent. No body, no header.
        r = s.post(f"{API}/auth/refresh", timeout=30)
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()

    def test_refresh_missing_returns_401(self):
        r = requests.post(f"{API}/auth/refresh", timeout=30)
        assert r.status_code == 401


# ---------- Membership expiry full-admin gating ----------
class TestMembershipExpiryEdit:
    @pytest.fixture(autouse=True)
    def setup(self, admin_tokens, member_tokens):
        self.admin_h = {"Authorization": f"Bearer {admin_tokens['access']}"}
        self.mm_h = None  # set per test
        self.member_id = member_tokens["uid"]
        # Snapshot original expiry to restore later
        r = requests.get(f"{API}/members/{self.member_id}", headers=self.admin_h, timeout=30)
        self.original_expiry = r.json().get("membership_expires_at")
        yield
        # Restore
        requests.put(
            f"{API}/members/{self.member_id}",
            json={"membership_expires_at": self.original_expiry},
            headers=self.admin_h, timeout=30,
        )

    def test_full_admin_can_set_custom_expiry(self):
        custom = "2099-12-31T00:00:00+00:00"
        r = requests.put(
            f"{API}/members/{self.member_id}",
            json={"membership_expires_at": custom},
            headers=self.admin_h, timeout=30,
        )
        assert r.status_code == 200, r.text
        # Verify persisted verbatim (year 2099 should still be there)
        g = requests.get(f"{API}/members/{self.member_id}", headers=self.admin_h, timeout=30).json()
        assert "2099" in (g.get("membership_expires_at") or ""), g

    def test_full_admin_join_date_change_does_not_clobber_explicit_expiry(self):
        custom = "2088-06-15T00:00:00+00:00"
        r = requests.put(
            f"{API}/members/{self.member_id}",
            json={
                "membership_expires_at": custom,
                "join_date": "2020-01-01T00:00:00+00:00",
            },
            headers=self.admin_h, timeout=30,
        )
        assert r.status_code == 200, r.text
        g = requests.get(f"{API}/members/{self.member_id}", headers=self.admin_h, timeout=30).json()
        assert "2088" in (g.get("membership_expires_at") or ""), g

    def test_membership_manager_cannot_change_expiry(self, mm_tokens):
        mm_h = {"Authorization": f"Bearer {mm_tokens['access']}"}
        r = requests.put(
            f"{API}/members/{self.member_id}",
            json={"membership_expires_at": "2099-01-01T00:00:00+00:00"},
            headers=mm_h, timeout=30,
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text}"
        body = r.json()
        # Match server error message
        msg = (body.get("detail") or "").lower()
        assert "full admin" in msg and "expiration" in msg, body


# ---------- Gear page settings (hero/title/subtitle/intro) ----------
class TestGearPage:
    def test_gear_page_public_get(self):
        r = requests.get(f"{API}/gear-page", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("hero_image", "title", "subtitle", "intro"):
            assert k in d

    def test_gear_page_admin_put_then_get(self, admin_tokens):
        h = {"Authorization": f"Bearer {admin_tokens['access']}"}
        payload = {
            "hero_image": "/api/files/test/banner.jpg",
            "title": "TEST Gear Title",
            "subtitle": "TEST Gear Subtitle",
            "intro": "TEST gear intro paragraph.",
        }
        r = requests.put(f"{API}/gear-page", json=payload, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        g = requests.get(f"{API}/gear-page", timeout=30).json()
        assert g["title"] == payload["title"]
        assert g["subtitle"] == payload["subtitle"]
        assert g["intro"] == payload["intro"]
        assert g["hero_image"] == payload["hero_image"]
        # Cleanup: clear back to empty
        requests.put(f"{API}/gear-page", json={"hero_image": "", "title": "", "subtitle": "", "intro": ""}, headers=h, timeout=30)

    def test_gear_page_put_requires_admin(self, member_tokens):
        h = {"Authorization": f"Bearer {member_tokens['access']}"}
        r = requests.put(f"{API}/gear-page", json={"title": "nope"}, headers=h, timeout=30)
        assert r.status_code == 403


# ---------- Gear color_images + CRUD ----------
class TestGearColorImages:
    def test_create_get_update_delete_with_color_images(self, admin_tokens):
        h = {"Authorization": f"Bearer {admin_tokens['access']}"}
        payload = {
            "name": "TEST AOP Tee",
            "description": "test only",
            "price": 25.0,
            "sizes": ["S", "M", "L"],
            "colors": ["red", "navy", "gold"],
            "color_images": [
                {"color": "red", "image_url": "/api/files/test/red.jpg"},
                {"color": "navy", "image_url": "/api/files/test/navy.jpg"},
                {"color": "gold", "image_url": "/api/files/test/gold.jpg"},
            ],
            "cover_image": "/api/files/test/cover.jpg",
            "category": "apparel",
            "in_stock": True,
            "sku": "TEST-TEE-1",
        }
        r = requests.post(f"{API}/gear", json=payload, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        item = r.json()
        gid = item["id"]
        assert len(item["color_images"]) == 3
        assert {c["color"] for c in item["color_images"]} == {"red", "navy", "gold"}

        # GET single
        g = requests.get(f"{API}/gear/{gid}", timeout=30).json()
        assert len(g["color_images"]) == 3

        # GET list
        lst = requests.get(f"{API}/gear", timeout=30).json()
        match = [x for x in lst if x["id"] == gid]
        assert len(match) == 1
        assert len(match[0]["color_images"]) == 3

        # PUT — remove "gold" from both colors and color_images (frontend filters orphans)
        upd = {
            "colors": ["red", "navy"],
            "color_images": [
                {"color": "red", "image_url": "/api/files/test/red2.jpg"},
                {"color": "navy", "image_url": "/api/files/test/navy.jpg"},
            ],
        }
        r2 = requests.put(f"{API}/gear/{gid}", json=upd, headers=h, timeout=30)
        assert r2.status_code == 200, r2.text
        updated = r2.json()
        assert updated["colors"] == ["red", "navy"]
        assert len(updated["color_images"]) == 2
        red_img = next(c for c in updated["color_images"] if c["color"] == "red")
        assert red_img["image_url"] == "/api/files/test/red2.jpg"

        # DELETE
        d = requests.delete(f"{API}/gear/{gid}", headers=h, timeout=30)
        assert d.status_code == 200
        assert requests.get(f"{API}/gear/{gid}", timeout=30).status_code == 404


# ---------- Gear image upload ----------
PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc\xff\xff?\x00\x05"
    b"\xfe\x02\xfe\xa1n#\xc8\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestGearUpload:
    def test_upload_image_admin(self, admin_tokens):
        h = {"Authorization": f"Bearer {admin_tokens['access']}"}
        files = {"file": ("test.png", io.BytesIO(PNG_1PX), "image/png")}
        r = requests.post(f"{API}/gear/upload", headers=h, files=files, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["url"].startswith("/api/files/")
        assert d["size"] > 0

    def test_upload_non_image_rejected(self, admin_tokens):
        h = {"Authorization": f"Bearer {admin_tokens['access']}"}
        files = {"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")}
        r = requests.post(f"{API}/gear/upload", headers=h, files=files, timeout=30)
        assert r.status_code == 400, r.text

    def test_upload_requires_admin(self, member_tokens):
        h = {"Authorization": f"Bearer {member_tokens['access']}"}
        files = {"file": ("test.png", io.BytesIO(PNG_1PX), "image/png")}
        r = requests.post(f"{API}/gear/upload", headers=h, files=files, timeout=30)
        assert r.status_code == 403


# ---------- PayPal order with gear color/size ----------
class TestPayPalGearVariant:
    def test_create_paypal_order_persists_gear_color_size(self, admin_tokens, member_tokens):
        adm_h = {"Authorization": f"Bearer {admin_tokens['access']}"}
        # Create a temp gear item to reference
        payload = {
            "name": "TEST Variant Hoodie",
            "price": 50.0,
            "sizes": ["M", "L"],
            "colors": ["red"],
            "color_images": [{"color": "red", "image_url": "/api/files/test/red.jpg"}],
            "cover_image": "/api/files/test/cover.jpg",
            "category": "apparel",
            "in_stock": True,
        }
        gid = requests.post(f"{API}/gear", json=payload, headers=adm_h, timeout=30).json()["id"]

        mem_h = {"Authorization": f"Bearer {member_tokens['access']}"}
        order_body = {
            "purpose": "gear",
            "amount": 50.0,
            "gear_id": gid,
            "gear_color": "red",
            "gear_size": "M",
            "quantity": 1,
        }
        r = requests.post(f"{API}/payments/paypal/orders", json=order_body, headers=mem_h, timeout=60)
        # PayPal sandbox should accept; if it can't reach PayPal return 502 -> skip
        if r.status_code == 502:
            pytest.skip("PayPal sandbox unreachable")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "order_id" in d and "transaction_id" in d
        tx_id = d["transaction_id"]

        # Verify the persisted transaction has the variant + description
        tx_list = requests.get(f"{API}/admin/transactions", headers=adm_h, timeout=30)
        if tx_list.status_code == 200:
            txs = tx_list.json()
            match = [t for t in (txs if isinstance(txs, list) else txs.get("items", [])) if t.get("id") == tx_id]
            if match:
                tx = match[0]
                assert tx.get("gear_color") == "red"
                assert tx.get("gear_size") == "M"
                assert "(red · M)" in (tx.get("description") or "")

        # Cleanup gear
        requests.delete(f"{API}/gear/{gid}", headers=adm_h, timeout=30)


# ---------- Regression: existing endpoints still healthy ----------
class TestRegression:
    def test_get_members_public(self):
        r = requests.get(f"{API}/members", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_tiers_includes_founder(self):
        r = requests.get(f"{API}/tiers", timeout=30)
        assert r.status_code == 200
        names = [(t.get("name") or "").lower() for t in r.json()]
        assert any("founder" in n for n in names), names

    def test_gear_list_public(self):
        r = requests.get(f"{API}/gear", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
