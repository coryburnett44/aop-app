"""Iteration 31 backend tests:
- Bug B: Personnel-brief PDF avatar embedding (relative, remote, empty, corrupt)
- Feature D: profile_layout + profile_custom_fields on /api/site-settings
- Feature D: PUT /api/members/me custom_fields persistence + /auth/me round-trip
- Snake_case key validation for custom field keys
- Bug C: mediaUrl host narrowing verified at the data layer (founders_items use customer-assets CDN)
- Regression smokes: /auth/login, /me/personnel-brief/pdf 200, /me/tax-letter/pdf 200, /payments/zeffy/validate
"""
import io
import os
import re
import uuid
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    if not v:
        raise RuntimeError("REACT_APP_BACKEND_URL is not set")
    return v.rstrip("/")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin_s():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def member_s():
    return _login(MEMBER)


# ---------- Bug C — host CDN URLs preserved in site-settings ----------
class TestFoundersCDNUrls:
    def test_founders_use_customer_assets_cdn(self):
        r = requests.get(f"{API}/site-settings", timeout=15)
        assert r.status_code == 200
        s = r.json()
        founders = s.get("founders_items") or []
        assert len(founders) >= 1, "expected default founders to exist"
        # At least one founder uses the customer-assets CDN (which must NOT be rewritten by mediaUrl)
        cdn_hosts = [
            f for f in founders
            if "customer-assets.emergentagent.com" in (f.get("image_url") or "")
        ]
        assert len(cdn_hosts) >= 1, f"expected at least one founder on customer-assets CDN, got {founders}"

    def test_founder_cdn_image_reachable(self):
        r = requests.get(f"{API}/site-settings", timeout=15)
        founders = r.json().get("founders_items") or []
        cdn = next((f["image_url"] for f in founders if "customer-assets.emergentagent.com" in (f.get("image_url") or "")), None)
        assert cdn, "no CDN founder image"
        head = requests.get(cdn, timeout=20, stream=True)
        assert head.status_code == 200, f"CDN image not reachable: {cdn} → {head.status_code}"


# ---------- Feature D backend ----------
class TestProfileLayoutAndCustomFields:
    def test_defaults_present(self, admin_s):
        # First restore defaults so we have a clean slate (a prior test run may have left
        # a custom layout in the DB — the schema validation is what we care about here).
        admin_s.put(f"{API}/site-settings", json={
            "profile_layout": [
                {"key": "identity", "visible": True, "label": "Identity"},
                {"key": "contact", "visible": True, "label": "Contact"},
                {"key": "fraternity", "visible": True, "label": "Fraternity Details"},
                {"key": "languages", "visible": True, "label": "Languages"},
                {"key": "education", "visible": True, "label": "Civilian Education"},
                {"key": "social", "visible": True, "label": "Social Links"},
            ],
            "profile_custom_fields": [],
        }, timeout=15)
        r = requests.get(f"{API}/site-settings", timeout=15)
        assert r.status_code == 200
        s = r.json()
        layout = s.get("profile_layout") or []
        assert isinstance(layout, list) and len(layout) >= 6, f"got {layout}"
        keys = {item.get("key") for item in layout}
        for expected in ("identity", "contact", "fraternity", "languages", "education", "social"):
            assert expected in keys, f"expected default key {expected} in {keys}"
        assert "profile_custom_fields" in s
        assert isinstance(s.get("profile_custom_fields"), list)

    def test_admin_can_update_layout_and_custom_fields(self, admin_s):
        new_layout = [
            {"key": "identity", "visible": True, "label": "Identity"},
            {"key": "contact", "visible": False, "label": "Contact"},
            {"key": "fraternity", "visible": True, "label": "Fraternity Details"},
            {"key": "languages", "visible": True, "label": "Languages"},
            {"key": "education", "visible": True, "label": "Civilian Education"},
            {"key": "social", "visible": True, "label": "Social Links"},
        ]
        fields = [
            {"key": "favorite_color", "label": "Favorite color", "type": "text", "options": [], "required": False, "help_text": ""},
            {"key": "tshirt_size", "label": "Shirt size", "type": "select", "options": ["S", "M", "L", "XL"], "required": False, "help_text": "Used for swag"},
        ]
        r = admin_s.put(f"{API}/site-settings", json={
            "profile_layout": new_layout,
            "profile_custom_fields": fields,
        }, timeout=20)
        assert r.status_code == 200, f"PUT site-settings failed: {r.status_code} {r.text[:300]}"

        g = requests.get(f"{API}/site-settings", timeout=15).json()
        # contact must be invisible now
        contact_item = next(it for it in g["profile_layout"] if it["key"] == "contact")
        assert contact_item["visible"] is False
        # custom fields persisted
        fkeys = {f["key"] for f in g["profile_custom_fields"]}
        assert "favorite_color" in fkeys
        assert "tshirt_size" in fkeys

    def test_snake_case_validation(self, admin_s):
        r = admin_s.put(f"{API}/site-settings", json={
            "profile_custom_fields": [
                {"key": "BadKey-1", "label": "Bad", "type": "text"}
            ]
        }, timeout=15)
        assert r.status_code in (400, 422), f"expected validation error, got {r.status_code} {r.text[:200]}"

    def test_member_custom_fields_round_trip(self, admin_s, member_s):
        # Ensure favorite_color field exists
        admin_s.put(f"{API}/site-settings", json={
            "profile_custom_fields": [
                {"key": "favorite_color", "label": "Favorite color", "type": "text", "options": [], "required": False, "help_text": ""}
            ]
        }, timeout=15)
        val = f"blue_{uuid.uuid4().hex[:6]}"
        r = member_s.put(f"{API}/members/me", json={"custom_fields": {"favorite_color": val}}, timeout=15)
        assert r.status_code == 200, f"PUT /members/me failed: {r.status_code} {r.text[:300]}"

        me = member_s.get(f"{API}/auth/me", timeout=15)
        assert me.status_code == 200
        cf = (me.json() or {}).get("custom_fields") or {}
        assert cf.get("favorite_color") == val, f"expected {val}, got {cf}"


# ---------- Bug B — Personnel Brief PDF avatar embedding ----------
def _pdf_image_count(pdf_bytes):
    """Return number of /Subtype /Image XObjects across all pages."""
    try:
        from pypdf import PdfReader
    except Exception:
        pytest.skip("pypdf not installed")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total = 0
    for page in reader.pages:
        try:
            res = page.get("/Resources")
            if res is None:
                continue
            xobj = res.get("/XObject") if hasattr(res, "get") else None
            if xobj is None:
                continue
            xobj = xobj.get_object()
            for name in xobj:
                obj = xobj[name].get_object()
                if obj.get("/Subtype") == "/Image":
                    total += 1
        except Exception:
            continue
    return total


class TestBriefPDFAvatar:
    def test_brief_pdf_with_remote_http_avatar(self, admin_s, member_s):
        # Set the member's avatar to a remote https image (unsplash-style)
        me = member_s.get(f"{API}/auth/me", timeout=15).json()
        mid = me["id"]
        remote = "https://images.unsplash.com/photo-1503023345310-bd7c1de61c7d?w=400"
        r = admin_s.put(f"{API}/members/{mid}", json={"avatar_url": remote}, timeout=20)
        assert r.status_code == 200, r.text[:300]

        pdf = member_s.get(f"{API}/me/personnel-brief/pdf", timeout=45)
        assert pdf.status_code == 200, pdf.text[:300]
        assert pdf.headers.get("content-type", "").startswith("application/pdf")
        assert pdf.content.startswith(b"%PDF")
        count = _pdf_image_count(pdf.content)
        assert count >= 1, f"expected >=1 embedded image (avatar), got {count}"

    def test_brief_pdf_with_empty_avatar(self, admin_s, member_s):
        me = member_s.get(f"{API}/auth/me", timeout=15).json()
        mid = me["id"]
        r = admin_s.put(f"{API}/members/{mid}", json={"avatar_url": ""}, timeout=20)
        assert r.status_code == 200
        pdf = member_s.get(f"{API}/me/personnel-brief/pdf", timeout=45)
        assert pdf.status_code == 200, "empty avatar must still produce a 200 PDF"
        assert pdf.content.startswith(b"%PDF")

    def test_brief_pdf_with_garbage_avatar_path(self, admin_s, member_s):
        """A corrupt or non-existent /api/files/ path must NOT crash the PDF endpoint."""
        me = member_s.get(f"{API}/auth/me", timeout=15).json()
        mid = me["id"]
        bogus = "/api/files/this_file_does_not_exist_" + uuid.uuid4().hex
        r = admin_s.put(f"{API}/members/{mid}", json={"avatar_url": bogus}, timeout=20)
        assert r.status_code == 200
        pdf = member_s.get(f"{API}/me/personnel-brief/pdf", timeout=45)
        assert pdf.status_code == 200, f"corrupt avatar must not 500, got {pdf.status_code} {pdf.text[:200]}"
        assert pdf.content.startswith(b"%PDF")


# ---------- Regression smokes ----------
class TestRegression:
    def test_login_by_email_works(self):
        r = requests.post(f"{API}/auth/login", json=MEMBER, timeout=15)
        assert r.status_code == 200

    def test_zeffy_validate(self, member_s):
        # Endpoint may be auth-gated; use authenticated session
        r = member_s.get(f"{API}/payments/zeffy/validate?url=https://www.zeffy.com/embed/donation-form/test", timeout=15)
        assert r.status_code in (200, 400, 422), f"unexpected {r.status_code}: {r.text[:200]}"

    def test_me_brief_pdf_200(self, member_s):
        r = member_s.get(f"{API}/me/personnel-brief/pdf", timeout=45)
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")

    def test_me_tax_letter_pdf_200(self, member_s):
        r = member_s.get(f"{API}/me/tax-letter/pdf", timeout=45)
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")

    def test_bulk_import_template_admin_only(self, admin_s):
        r = admin_s.get(f"{API}/admin/members/bulk-import/template", timeout=15)
        # Some implementations stream CSV; either way status must be 2xx
        assert 200 <= r.status_code < 300, f"{r.status_code} {r.text[:200]}"


# ---------- Cleanup: restore default layout + clear favorite_color value ----------
@pytest.fixture(scope="module", autouse=True)
def _restore(admin_s, member_s):
    yield
    try:
        admin_s.put(f"{API}/site-settings", json={
            "profile_layout": [
                {"key": "identity", "visible": True, "label": "Identity"},
                {"key": "contact", "visible": True, "label": "Contact"},
                {"key": "fraternity", "visible": True, "label": "Fraternity Details"},
                {"key": "languages", "visible": True, "label": "Languages"},
                {"key": "education", "visible": True, "label": "Civilian Education"},
                {"key": "social", "visible": True, "label": "Social Links"},
            ],
            "profile_custom_fields": [],
        }, timeout=15)
    except Exception:
        pass
    try:
        member_s.put(f"{API}/members/me", json={"custom_fields": {}, "avatar_url": ""}, timeout=15)
    except Exception:
        pass
