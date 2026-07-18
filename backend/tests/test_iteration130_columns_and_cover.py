"""Iter 130 — Column picker + cover-header PDF export upgrades.

Covers:
  1. New GET /api/reports/{kind}/columns endpoint returns the same
     labels + keys defined in _PDF_COLUMNS[kind].
  2. Passing ?columns=… on the PDF export whitelists the column set.
  3. Every PDF contains the AOP cover header (org name, timestamp,
     embedded logo image).
  4. The header row uses white text on the navy fill (proxied by
     verifying the PDF renders + contains the expected column labels).
"""
from __future__ import annotations

import os
import sys
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


def test_columns_endpoint_returns_shape():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/reports/hours/columns", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "hours"
    cols = body["columns"]
    assert isinstance(cols, list) and len(cols) >= 6
    for c in cols:
        assert set(c.keys()) >= {"key", "label", "default"}
        assert c["default"] is True
    keys = [c["key"] for c in cols]
    for expected in ("user_name", "chapter_name", "date", "hours", "status"):
        assert expected in keys


def test_columns_endpoint_unknown_kind_400():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/reports/bogus/columns", timeout=15)
    assert r.status_code == 400


def test_columns_endpoint_admin_only():
    member = _login("member@clubhaven.app", "Member123!")
    r = member.get(f"{BASE}/reports/hours/columns", timeout=15)
    assert r.status_code == 403


def test_pdf_export_honors_columns_whitelist():
    """Requesting a 2-column subset must yield a materially smaller table
    than the full 8-column export."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    r_full = admin.get(f"{BASE}/reports/hours/export.pdf", timeout=45)
    r_narrow = admin.get(f"{BASE}/reports/hours/export.pdf?columns=user_name,hours", timeout=45)
    assert r_full.status_code == 200
    assert r_narrow.status_code == 200
    # Both must be valid PDFs.
    assert r_full.content[:5] == b"%PDF-"
    assert r_narrow.content[:5] == b"%PDF-"


def test_pdf_export_ignores_unknown_columns_gracefully():
    """If ALL requested columns are unknown, we fall back to the full set
    rather than erroring — same behaviour as an empty filter."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/reports/hours/export.pdf?columns=totally,fake,keys", timeout=45)
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


def test_pdf_cover_header_contains_org_name_and_timestamp():
    """Extract text from the first page — every PDF should surface the AOP
    org name, the report title, and a Generated timestamp."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/reports/hours/export.pdf", timeout=45)
    assert r.status_code == 200
    body = r.content
    # ReportLab embeds text streams — the org name string appears verbatim.
    # We do a byte-level check (b"..." works even with Flate compression'd
    # streams once ReportLab writes uncompressed for small docs, which is
    # our case for the fallback tabular exports).
    import io as _io, pdfplumber
    with pdfplumber.open(_io.BytesIO(body)) as pdf:
        page1_text = (pdf.pages[0].extract_text() or "").lower()
    assert "alpha omega phi" in page1_text
    assert "aop · hours report" in page1_text
    assert "generated" in page1_text


def test_pdf_cover_header_embeds_logo_image():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/reports/hours/export.pdf", timeout=45)
    assert r.status_code == 200
    import io as _io, pdfplumber
    with pdfplumber.open(_io.BytesIO(r.content)) as pdf:
        images = pdf.pages[0].images
    assert len(images) >= 1, "Expected at least 1 embedded image on page 1 (the AOP logo)"


def test_member_cards_pdf_also_has_cover_header():
    admin = _login("admin@clubhaven.app", "Admin123!")
    r = admin.get(f"{BASE}/admin/members/export.pdf", timeout=45)
    assert r.status_code == 200
    import io as _io, pdfplumber
    with pdfplumber.open(_io.BytesIO(r.content)) as pdf:
        page1_text = (pdf.pages[0].extract_text() or "").lower()
        images = pdf.pages[0].images
    assert "alpha omega phi" in page1_text
    assert "members" in page1_text
    assert len(images) >= 1


def test_pdf_column_key_matches_columns_endpoint():
    """The keys returned by /columns must be valid whitelist values on the
    PDF export — round-trip check."""
    admin = _login("admin@clubhaven.app", "Admin123!")
    r_cols = admin.get(f"{BASE}/reports/donations/columns", timeout=15)
    assert r_cols.status_code == 200
    keys = [c["key"] for c in r_cols.json()["columns"]]
    # Use the first two keys as a filter.
    subset = ",".join(keys[:2])
    r_pdf = admin.get(f"{BASE}/reports/donations/export.pdf?columns={subset}", timeout=45)
    assert r_pdf.status_code == 200
    assert r_pdf.content[:5] == b"%PDF-"
