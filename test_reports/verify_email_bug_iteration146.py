#!/usr/bin/env python3
"""Focused verification for the reported email bug.

Scope:
- Attachments must reach the outgoing Brevo v3 payload as `attachment` (singular).
- Email preview/test-send/blast HTML must be wrapped in the professional document.
- Wrapper must be idempotent.
- Admin email UI must not expose old Resend branding in the email admin flow.

This script intentionally avoids real Brevo sends by monkey-patching only
`brevo_sdk.requests.post` and capturing the JSON body the shim would send.
"""

from __future__ import annotations

import base64
import json as jsonlib
import os
import sys
import traceback
from pathlib import Path

import requests


BACKEND_DIR = Path("/app/backend")
sys.path.insert(0, str(BACKEND_DIR))


API = "http://localhost:8001/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@clubhaven.app")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin123!")


RESULTS: list[dict] = []


def record(name: str, ok: bool, detail: str = ""):
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}: {name} {('- ' + detail) if detail else ''}")


def assert_true(condition, message: str):
    if not condition:
        raise AssertionError(message)


def run_check(name, fn):
    try:
        fn()
        record(name, True)
    except Exception as exc:  # noqa: BLE001 - test script should report all failures
        detail = f"{exc}\n{traceback.format_exc(limit=2)}"
        record(name, False, detail)


def live_login_token() -> str:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    r.raise_for_status()
    token = r.json().get("access_token")
    assert_true(token, "login response did not include access_token")
    return token


def check_live_preview_wrapped():
    token = live_login_token()
    body = {
        "subject": "QA wrapped preview",
        "body_html": '<p>Visible preheader text for QA.</p><img class="x" src="/api/files/email/admin/file/pic.png">',
        "segment": "custom",
        "external_emails": ["qa-preview@example.com"],
    }
    r = requests.post(f"{API}/email/preview", headers={"Authorization": f"Bearer {token}"}, json=body, timeout=10)
    r.raise_for_status()
    html = r.json().get("html", "")
    assert_true(html.startswith("<!DOCTYPE"), "preview html does not start with <!DOCTYPE")
    assert_true("<title>QA wrapped preview</title>" in html, "preview missing subject title")
    assert_true("<!--[if mso]>" in html, "preview missing Outlook conditional comment")
    assert_true("display:none" in html and "font-size:1px" in html, "preview missing hidden preheader")
    assert_true('role="presentation"' in html, "preview missing table presentation container")
    assert_true("Alpha" in html and "Omega" in html and "Phi" in html, "preview missing brand strip")
    assert_true("/api/email/image/" in html, "embedded image URL was not rewritten for public email-image route")
    assert_true('class="x"' not in html, "email image class attribute was not stripped")


class FakeBrevoResponse:
    ok = True
    status_code = 201
    text = "{}"

    def json(self):
        return {"messageId": "<20260728.qa@smtp-relay.mailin.fr>"}


class BrevoPostSpy:
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, url, headers=None, data=None, timeout=None, **kwargs):
        if data is not None:
            payload = jsonlib.loads(data)
        else:
            payload = kwargs.get("json") or {}
        self.calls.append({"url": url, "headers": headers or {}, "payload": payload, "timeout": timeout})
        return FakeBrevoResponse()


def patch_brevo_post():
    import brevo_sdk

    original = brevo_sdk.requests.post
    spy = BrevoPostSpy()
    brevo_sdk.requests.post = spy
    return brevo_sdk, original, spy


def check_test_send_endpoint_captured_html():
    client, brevo_sdk, original_post, spy = make_isolated_email_client()
    try:
        r = client.post(
            "/api/email/test-send",
            json={
                "to_email": "qa-test-send@example.com",
                "subject": "QA test-send wrapper",
                "body_html": "<p>Test-send wrapped body.</p>",
            },
        )
        assert_true(r.status_code == 200, f"test-send failed: {r.status_code} {r.text}")
        response = r.json()
        assert_true(response.get("ok") is True, f"test-send response not ok: {response}")
        assert_true("mailin.fr" in response.get("message_id", ""), f"message_id was not Brevo-shaped: {response}")
        assert_true(spy.calls, "Brevo post spy captured no outgoing request")
        payload = spy.calls[-1]["payload"]
        html = payload.get("htmlContent", "")
        assert_true(html.startswith("<!DOCTYPE"), "outgoing test-send htmlContent does not start with <!DOCTYPE")
        assert_true("<title>QA test-send wrapper</title>" in html, "outgoing test-send htmlContent missing title")
        assert_true("<!--[if mso]>" in html, "outgoing test-send htmlContent missing MSO comment")
        assert_true("display:none" in html and "font-size:1px" in html, "outgoing test-send missing hidden preheader")
        assert_true("Alpha" in html and "Omega" in html and "Phi" in html, "outgoing test-send missing brand strip")
    finally:
        brevo_sdk.requests.post = original_post


def check_blast_attachment_endpoint_payload_shape():
    """Register the real email router against a fake DB/storage layer, then call
    POST /api/email/blast with attachment_ids. The send path uses the real
    server.send_bulk_email + real Brevo shim with requests.post monkey-patched,
    so the captured payload is the actual Brevo v3 JSON body.
    """
    client, brevo_sdk, original_post, spy = make_isolated_email_client()
    try:
        r = client.post(
            "/api/email/blast",
            json={
                "subject": "QA blast attachment",
                "body_html": "<p>Blast body with attachment.</p>",
                "segment": "custom",
                "external_emails": ["qa-blast-recipient@example.com"],
                "attachment_ids": ["att-qa-1"],
            },
        )
        assert_true(r.status_code == 200, f"blast endpoint failed: {r.status_code} {r.text}")
        assert_true(r.json().get("sent") == 1 and r.json().get("failed") == 0, f"unexpected blast result: {r.json()}")
        assert_true(spy.calls, "Brevo post spy captured no blast outgoing request")
        payload = spy.calls[-1]["payload"]
        assert_true("attachment" in payload, f"Brevo payload missing singular attachment key: {payload.keys()}")
        assert_true("attachments" not in payload, "Brevo payload still contains plural attachments key")
        att = payload["attachment"][0]
        assert_true(att.get("name") == "qa-attachment.txt", f"unexpected attachment name: {att}")
        assert_true(base64.b64decode(att.get("content", "")) == b"attached QA bytes", "attachment content did not round-trip from base64")
        html = payload.get("htmlContent", "")
        assert_true(html.startswith("<!DOCTYPE"), "blast htmlContent was not wrapped")
    finally:
        brevo_sdk.requests.post = original_post


class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def limit(self, _n):
        return self

    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, _n):
        return list(self.docs)


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.inserted = []

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            if query.get("id") and doc.get("id") != query.get("id"):
                continue
            if query.get("kind") and doc.get("kind") != query.get("kind"):
                continue
            if query.get("email") and doc.get("email") != query.get("email"):
                continue
            if doc.get("is_deleted") is True:
                continue
            return dict(doc)
        return None

    def find(self, *_args, **_kwargs):
        return FakeCursor([])

    async def insert_one(self, doc):
        self.inserted.append(dict(doc))
        return type("InsertResult", (), {"inserted_id": "fake"})()

    async def count_documents(self, *_args, **_kwargs):
        return 0


class FakeDB:
    def __init__(self):
        self.chat_files = FakeCollection([
            {
                "id": "att-qa-1",
                "kind": "attachment",
                "filename": "qa-attachment.txt",
                "storage_path": "fake/path/qa-attachment.txt",
                "content_type": "text/plain",
                "size": 17,
                "is_deleted": False,
            }
        ])
        self.users = FakeCollection([
            {"id": "admin-qa", "email": "admin@clubhaven.app", "name": "QA Admin", "role": "admin"}
        ])
        self.email_blasts = FakeCollection([])
        self.email_templates = FakeCollection([])
        self.email_drafts = FakeCollection([])
        self.password_setup_attempts = FakeCollection([])
        self.email_signatures = FakeCollection([])


def make_isolated_email_client():
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    import brevo_sdk
    import server
    from routes import email as email_routes

    admin = {"id": "admin-qa", "email": "admin@clubhaven.app", "name": "QA Admin", "role": "admin"}

    def admin_tab_dep(_tab):
        async def dep():
            return admin
        return dep

    async def get_current_user():
        return admin

    def fake_get_object(storage_path):
        assert_true(storage_path == "fake/path/qa-attachment.txt", f"unexpected storage path {storage_path}")
        return b"attached QA bytes", "text/plain"

    app = FastAPI()
    api = APIRouter(prefix="/api")
    fake_db = FakeDB()
    spy = BrevoPostSpy()
    original_post = brevo_sdk.requests.post
    brevo_sdk.requests.post = spy
    brevo_sdk.Brevo.api_key = "test-key"
    server.RESEND_API_KEY = "test-key"

    email_routes.register(
        api,
        db=fake_db,
        iso=server.iso,
        now_utc=server.now_utc,
        logger=server.logger,
        admin_tab_dep=admin_tab_dep,
        get_current_user=get_current_user,
        resend_sdk=brevo_sdk,
        resend_api_key="test-key",
        resend_from="Alpha Omega Phi <info@aop-app.org>",
        resend_reply_to="info@aop-app.org",
        org_mailing_address="Alpha Omega Phi Military Fraternity & Sorority, Inc.",
        send_bulk_email=server.send_bulk_email,
        normalize_email_images=server._normalize_email_images,
        verify_unsubscribe_token=lambda _token: None,
        put_object=lambda *_args, **_kwargs: {},
        image_extensions=server.IMAGE_EXT,
        mime_by_ext=server.MIME_BY_EXT,
        get_object=fake_get_object,
        wrap_email_document=server._wrap_email_document,
        extract_preheader=server._extract_preheader,
    )
    app.include_router(api)
    return TestClient(app), brevo_sdk, original_post, spy


def check_translate_edges_and_idempotent_wrapper():
    import brevo_sdk
    import server

    out = brevo_sdk._translate({
        "from": "info@aop-app.org",
        "to": ["member@example.com"],
        "subject": "Attachments",
        "html": "<p>Hi</p>",
        "attachments": [
            {"filename": "raw.bin", "content": b"raw-bytes"},
            {"filename": "remote.pdf", "url": "https://cdn.example.com/remote.pdf"},
        ],
    })
    assert_true("attachment" in out and "attachments" not in out, "_translate did not map attachments to singular attachment")
    assert_true(base64.b64decode(out["attachment"][0]["content"]) == b"raw-bytes", "raw bytes were not base64 encoded")
    assert_true(out["attachment"][1] == {"url": "https://cdn.example.com/remote.pdf", "name": "remote.pdf"}, "URL attachment passthrough failed")

    once = server._wrap_email_document("<p>Hi</p>", subject="Once", preheader="Hi")
    twice = server._wrap_email_document(once, subject="Twice", preheader="Nope")
    assert_true(once == twice, "_wrap_email_document is not idempotent")
    assert_true(once.startswith("<!DOCTYPE") and "<!--[if mso]>" in once, "wrapped document missing core structure")


def check_admin_email_flow_resend_branding():
    src = Path("/app/frontend/src/pages/Admin.jsx").read_text()
    marker = "/* -------- Email Blast Admin (Brevo) -------- */"
    email_section = src[src.index(marker):] if marker in src else src
    offending = []
    for i, line in enumerate(email_section.splitlines(), start=1):
        if "Resend" in line:
            offending.append(line.strip())
    assert_true(not offending, "Resend brand text remains in Email Blast Admin section: " + " | ".join(offending[:5]))


if __name__ == "__main__":
    run_check("live /api/email/preview returns fully wrapped professional HTML", check_live_preview_wrapped)
    run_check("/api/email/test-send outgoing Brevo payload contains wrapped htmlContent", check_test_send_endpoint_captured_html)
    run_check("/api/email/blast with attachment_ids sends Brevo attachment payload", check_blast_attachment_endpoint_payload_shape)
    run_check("Brevo _translate attachment edges and wrapper idempotency", check_translate_edges_and_idempotent_wrapper)
    run_check("Admin email flow has no user-facing Resend brand text", check_admin_email_flow_resend_branding)

    passed = sum(1 for r in RESULTS if r["ok"])
    print(jsonlib.dumps({"passed": passed, "total": len(RESULTS), "results": RESULTS}, indent=2))
    raise SystemExit(0 if passed == len(RESULTS) else 1)