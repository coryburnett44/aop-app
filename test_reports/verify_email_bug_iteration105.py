"""Focused verification for the email inline-image/attachment deliverability bug.

This script intentionally covers only the reported email flow:
  * legacy /api/files/email/* image URLs are rewritten to /api/email/image/email/*
  * rewritten image URLs are anonymously fetchable by a mailbox image proxy
  * already-public image URLs are not double-rewritten
  * Brevo attachment payload translation emits singular `attachment`
  * preview/test-send/blast wrapper helpers still produce a full HTML document
  * Admin.jsx no longer contains provider-brand "Resend" in the email admin area
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests


ROOT = Path("/app")
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

BASE = os.environ.get("TEST_BACKEND_BASE", "http://localhost:8001/api").rstrip("/")
ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"

# Smallest valid 1x1 transparent PNG.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _login() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    _assert(r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}")
    # The local preview backend sets Secure cookies, which requests will not
    # send back over http://localhost. Use the returned bearer token so the
    # backend-only verification works against both localhost and HTTPS ingress.
    token = r.json().get("access_token")
    _assert(bool(token), "login response did not include access_token")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _path_from_url(url_or_path: str) -> str:
    if url_or_path.startswith("http"):
        m = re.search(r"https?://[^/]+(/api/[^\"'<>\s]+)", url_or_path)
        _assert(bool(m), f"could not extract /api path from {url_or_path}")
        return m.group(1)
    return url_or_path


def main() -> dict:
    results: dict[str, object] = {"base": BASE, "checks": {}}
    admin = _login()

    # 1) Upload a real inline image through the email route, then compose a
    # legacy /api/files/email/* URL that points to the same storage object.
    upload = admin.post(
        f"{BASE}/email/upload-image",
        files={"file": ("iter105.png", io.BytesIO(PNG), "image/png")},
        timeout=30,
    )
    _assert(upload.status_code == 200, f"inline image upload failed: {upload.status_code} {upload.text[:300]}")
    up = upload.json()
    public_path = up["url"]
    _assert(public_path.startswith("/api/email/image/email/"), f"fresh upload did not return scoped public URL: {public_path}")
    storage_path = public_path.split("/api/email/image/", 1)[1]
    legacy_path = f"/api/files/{storage_path}"
    results["checks"]["upload_image"] = {"public_path": public_path, "legacy_path": legacy_path}

    preview = admin.post(
        f"{BASE}/email/preview",
        json={
            "subject": "Iter105 legacy image rewrite",
            "body_html": f'<p>Inline image:</p><img class="legacy" src="{legacy_path}" />',
            "segment": "admins",
        },
        timeout=20,
    )
    _assert(preview.status_code == 200, f"preview failed: {preview.status_code} {preview.text[:300]}")
    html = preview.json()["html"]
    rewritten_path = f"/api/email/image/{storage_path}"
    _assert(rewritten_path in html, f"preview did not preserve email/ prefix in rewrite; expected {rewritten_path}")
    _assert("/api/email/image/email/email/" not in html, "preview double-rewrote image path")
    _assert("/api/files/email/" not in html, "legacy /api/files/email URL remained in preview HTML")
    _assert(html.lstrip().startswith("<!DOCTYPE"), "preview is not wrapped in full HTML5 document")
    _assert("<html" in html and "<head>" in html and "<body" in html, "preview wrapper missing html/head/body")
    _assert("display:none" in html and "font-size:1px" in html, "preview wrapper missing hidden preheader")
    results["checks"]["legacy_preview_rewrite"] = {"expected_path": rewritten_path, "wrapped": True}

    # 2) The rewritten image URL must be fetchable with a brand-new anonymous
    # session, mimicking Gmail/Outlook image proxies that do not send cookies.
    anon = requests.Session()
    fetch = anon.get(f"{BASE.replace('/api', '')}{rewritten_path}", timeout=20)
    _assert(fetch.status_code == 200, f"anonymous public image fetch failed: {fetch.status_code} {fetch.text[:200]}")
    _assert(fetch.content == PNG, f"anonymous public image bytes differed: got {len(fetch.content)} bytes")
    _assert(fetch.headers.get("Content-Type", "").startswith("image/"), f"public image content-type not image/*: {fetch.headers.get('Content-Type')}")
    results["checks"]["anonymous_public_image_fetch"] = {
        "status": fetch.status_code,
        "content_type": fetch.headers.get("Content-Type"),
        "bytes": len(fetch.content),
    }

    # 3) Already-public URLs must stay already-public and not gain a second
    # email/ prefix.
    preview2 = admin.post(
        f"{BASE}/email/preview",
        json={
            "subject": "Iter105 idempotent image rewrite",
            "body_html": f'<p>Already public:</p><img src="{public_path}" />',
            "segment": "admins",
        },
        timeout=20,
    )
    _assert(preview2.status_code == 200, f"public-url preview failed: {preview2.status_code} {preview2.text[:300]}")
    html2 = preview2.json()["html"]
    _assert(public_path in html2, "already-public image URL was not preserved in preview")
    _assert("/api/email/image/email/email/" not in html2, "already-public image URL was double-rewritten")
    results["checks"]["already_public_idempotent"] = True

    # 4) Brevo attachment regression: outgoing translation must use the
    # singular `attachment` key with [{name, content}], not Resend's plural.
    from brevo_sdk import _translate

    encoded = base64.b64encode(b"%PDF iter105 fake").decode("ascii")
    translated = _translate({
        "from": "Alpha Omega Phi <info@aop-app.org>",
        "to": ["member@example.com"],
        "subject": "Attachment regression",
        "html": "<p>See attached.</p>",
        "attachments": [{"filename": "iter105.pdf", "content": encoded, "content_type": "application/pdf"}],
    })
    _assert("attachment" in translated, "Brevo payload missing singular attachment key")
    _assert("attachments" not in translated, "Brevo payload still contains plural attachments key")
    _assert(translated["attachment"] == [{"name": "iter105.pdf", "content": encoded}], f"unexpected attachment payload: {translated.get('attachment')}")
    results["checks"]["brevo_attachment_translation"] = translated["attachment"]

    # Also exercise the real backend attachment path end-to-end: upload a PDF,
    # send a test-only blast to the admin segment, and ensure Brevo accepts it.
    # This proves /email/blast resolves chat_files bytes, base64-encodes them,
    # passes them into send_bulk_email, and receives an accepted provider result.
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog>>\nendobj\ntrailer <<>>\n%%EOF\n"
    att = admin.post(
        f"{BASE}/email/upload-attachment",
        files={"file": ("iter105-attachment.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        timeout=30,
    )
    _assert(att.status_code == 200, f"attachment upload failed: {att.status_code} {att.text[:300]}")
    att_id = att.json()["id"]
    try:
        blast = admin.post(
            f"{BASE}/email/blast",
            json={
                "subject": "Iter105 attachment regression test",
                "body_html": "<p>This is an automated attachment regression verification.</p>",
                "segment": "admins",
                "test_only": True,
                "attachment_ids": [att_id],
            },
            timeout=90,
        )
        _assert(blast.status_code == 200, f"test-only blast with attachment failed: {blast.status_code} {blast.text[:500]}")
        blast_data = blast.json()
        _assert(blast_data.get("sent") == 1 and blast_data.get("failed") == 0, f"test-only blast did not send cleanly: {blast_data}")
        results["checks"]["live_test_only_blast_with_attachment"] = blast_data
    finally:
        admin.delete(f"{BASE}/email/attachments/{att_id}", timeout=10)

    # 5) Direct wrapper regression for blast/test-send helper output.
    from server import _wrap_email_document, _normalize_email_images

    wrapped = _wrap_email_document("<p>Hello</p>", subject="Iter105", preheader="Preview text")
    _assert(wrapped.startswith("<!DOCTYPE"), "_wrap_email_document does not produce HTML5 document")
    _assert(_wrap_email_document(wrapped, subject="Ignored") == wrapped, "_wrap_email_document is not idempotent")
    normalized = _normalize_email_images('<img src="/api/email/image/email/blast/abc/photo.png">')
    _assert(normalized.count("/api/email/image/email/") == 1, "_normalize_email_images double-rewrites already-public URLs")
    results["checks"]["wrapper_and_normalizer_helpers"] = True

    # 6) Provider-brand regression: the Email Blast Admin section should not
    # mention Resend. Generic member-action copy such as "Resend link" is not
    # the provider brand and is reported separately.
    admin_jsx = ROOT / "frontend" / "src" / "pages" / "Admin.jsx"
    text = admin_jsx.read_text()
    email_admin = text[text.index("/* -------- Email Blast Admin"):] if "/* -------- Email Blast Admin" in text else text
    _assert("Resend" not in email_admin, "Email Blast Admin still contains user-facing Resend provider brand")
    member_resend_occurrences = [m.start() for m in re.finditer("Resend", text[: text.index("/* -------- Email Blast Admin")])]
    results["checks"]["provider_brand_email_admin"] = {
        "email_admin_resend_brand_count": 0,
        "non_provider_member_action_resend_count": len(member_resend_occurrences),
    }

    # 7) Re-run the focused backend regression test file the main agent added.
    pytest = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests/test_iteration146_wrapper_and_attachments.py", "-q"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    _assert(pytest.returncode == 0, f"focused pytest failed:\nSTDOUT:\n{pytest.stdout}\nSTDERR:\n{pytest.stderr}")
    results["checks"]["focused_pytest"] = pytest.stdout.strip().splitlines()[-1]

    return results


if __name__ == "__main__":
    try:
        output = main()
        output["ok"] = True
        print(json.dumps(output, indent=2, sort_keys=True))
    except Exception as exc:  # noqa: BLE001 - test script should print deterministic failure evidence
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        raise