"""Iteration 146 — Professional email wrapper + Brevo attachment translation.

Two bugs from the user report:
  1. "The attachments are not attached in the emails." → the Brevo shim's
     `_translate()` completely dropped the `attachments` parameter. Brevo
     v3 wants `"attachment": [{"name","content"}]` (singular).
  2. "The email still goes to junk mail." → the outgoing HTML was a bare
     fragment with no DOCTYPE, no <html>/<head>, no charset, no preheader.
     Now we wrap every outbound email in a bulletproof HTML document with
     Outlook-friendly table structure, brand strip, and hidden preheader.

Regression scope (offline, no network):
  - `brevo_sdk._translate` converts resend-style attachments → Brevo shape.
  - Base64 encoding is applied when raw bytes are supplied.
  - Attachments with a URL and a name pass through as remote attachments.
  - `_wrap_email_document` renders a full HTML5 document with all the
    key deliverability signals (doctype, html, head, meta charset, preheader,
    Outlook conditional comment, table container, brand strip).
  - `_wrap_email_document` is idempotent — already-wrapped HTML is returned
    unchanged so we never double-wrap.
  - `_extract_preheader` strips HTML and caps at ~120 chars.
"""

import os
import sys
import base64

# Make imports work when pytest is run from /app/backend
sys.path.insert(0, "/app/backend")


def test_brevo_translate_attachments_from_resend_shape():
    from brevo_sdk import _translate

    payload = {
        "from": "Alpha Omega Phi <info@aop-app.org>",
        "to": ["m@example.com"],
        "subject": "Hi",
        "html": "<p>hi</p>",
        "attachments": [
            {
                "filename": "roster.pdf",
                "content": base64.b64encode(b"%PDF-1.4 fake").decode("ascii"),
                "content_type": "application/pdf",
            },
            {
                "filename": "sheet.xlsx",
                "content": base64.b64encode(b"PK\x03\x04").decode("ascii"),
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
        ],
    }
    out = _translate(payload)
    assert "attachment" in out, "Brevo expects singular 'attachment' key"
    assert "attachments" not in out
    assert len(out["attachment"]) == 2
    assert out["attachment"][0]["name"] == "roster.pdf"
    assert isinstance(out["attachment"][0]["content"], str)
    assert out["attachment"][1]["name"] == "sheet.xlsx"


def test_brevo_translate_attachments_auto_base64_bytes():
    """Raw bytes payload should be auto-base64-encoded."""
    from brevo_sdk import _translate

    payload = {
        "from": "info@aop-app.org",
        "to": ["m@example.com"],
        "subject": "Hi",
        "html": "<p>hi</p>",
        "attachments": [{"filename": "x.bin", "content": b"\x00\x01\x02\x03raw-bytes"}],
    }
    out = _translate(payload)
    assert out["attachment"][0]["name"] == "x.bin"
    # Should be a base64 string — decode round-trip
    decoded = base64.b64decode(out["attachment"][0]["content"])
    assert decoded == b"\x00\x01\x02\x03raw-bytes"


def test_brevo_translate_attachment_url_passthrough():
    from brevo_sdk import _translate

    payload = {
        "from": "info@aop-app.org",
        "to": ["m@example.com"],
        "subject": "Hi",
        "html": "<p>hi</p>",
        "attachments": [{"url": "https://cdn.example.com/big.pdf", "filename": "big.pdf"}],
    }
    out = _translate(payload)
    assert out["attachment"] == [{"url": "https://cdn.example.com/big.pdf", "name": "big.pdf"}]


def test_wrap_email_document_full_structure():
    """The wrapper must add every signal that helps land in inbox."""
    from server import _wrap_email_document

    html = _wrap_email_document("<p>Hello member!</p>", subject="Weekly update", preheader="Community + volunteering")
    assert html.startswith("<!DOCTYPE"), "Must start with an HTML5 doctype"
    assert '<html xmlns="http://www.w3.org/1999/xhtml" lang="en"' in html
    assert '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8"' in html
    assert '<meta name="viewport"' in html
    assert "<title>Weekly update</title>" in html
    # Outlook conditional comment for MSO font fallback
    assert "<!--[if mso]>" in html
    # Hidden preheader block for inbox preview
    assert "Community + volunteering" in html
    assert 'display:none' in html and 'font-size:1px' in html
    # Table-based bulletproof container
    assert "<table" in html and 'role="presentation"' in html
    # Original body is preserved
    assert "<p>Hello member!</p>" in html
    # Brand strip renders "Alpha Omega Phi"
    assert "Alpha" in html and "Omega" in html and "Phi" in html
    assert "Military Fraternity" in html


def test_wrap_email_document_is_idempotent():
    """If we accidentally call the wrapper twice we must NOT double-wrap."""
    from server import _wrap_email_document

    once = _wrap_email_document("<p>Hi</p>", subject="Once", preheader="")
    twice = _wrap_email_document(once, subject="Twice-should-be-ignored", preheader="ignored")
    assert once == twice, "Second wrap should be a no-op"
    # And it should still say the ORIGINAL subject, not the second one
    assert "<title>Once</title>" in twice


def test_extract_preheader_strips_html_and_caps():
    from server import _extract_preheader

    long_html = "<h1>Big Title</h1><p>" + ("word " * 200) + "</p>"
    ph = _extract_preheader(long_html)
    assert "<" not in ph and ">" not in ph
    assert len(ph) <= 120

    # Empty is safe
    assert _extract_preheader("") == ""
    assert _extract_preheader(None) == ""


def test_wrap_email_document_escapes_subject():
    """Prevent HTML injection through the subject."""
    from server import _wrap_email_document

    html = _wrap_email_document(
        "<p>Body</p>",
        subject='"><script>alert(1)</script>',
        preheader="",
    )
    # The raw script tag must not appear inside <title>
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_normalize_preserves_email_prefix_in_legacy_urls():
    """Regression: legacy `/api/files/email/{path}` URLs must be rewritten
    to `/api/email/image/email/{path}` — the `email/` prefix is required by
    the public image endpoint which is scoped to `email/*` storage paths.
    Previously the code dropped the prefix, causing 404s in delivered mail.
    """
    from server import _normalize_email_images

    html = '<p><img src="/api/files/email/blast/abc/photo.png" alt=""></p>'
    out = _normalize_email_images(html)
    # New public URL — must retain the email/ prefix
    assert "/api/email/image/email/blast/abc/photo.png" in out
    # Must NOT have dropped the prefix
    assert "/api/email/image/blast/abc/photo.png" not in out
    # And must not have the old files/email path anymore
    assert "/api/files/email/" not in out


def test_normalize_idempotent_on_already_public_url():
    """Already-public `/api/email/image/email/...` URLs must NOT be
    double-rewritten to `/api/email/image/email/email/...`."""
    from server import _normalize_email_images

    html = '<img src="/api/email/image/email/blast/abc/photo.png" alt="">'
    out = _normalize_email_images(html)
    assert out.count("/api/email/image/email/") == 1
    assert "/api/email/image/email/email/" not in out
