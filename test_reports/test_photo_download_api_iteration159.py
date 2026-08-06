#!/usr/bin/env python3
"""Focused API regression checks for Iteration 159 photo ZIP download fix."""

import io
import json
import os
import re
import time
import uuid
import zipfile
from pathlib import Path

import requests
from dotenv import dotenv_values
from pymongo import MongoClient


BASE_URL = os.environ.get("TEST_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
PREFERRED_ALBUM = os.environ.get("TEST_PHOTO_ALBUM", "5-Year Anniversary")
ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"
RESULT_PATH = Path("/app/test_reports/photo_download_api_iteration159_results.json")


def safe_filename(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._ -]", "_", s or "")[:120]
    return s or "photo"


def expected_zip_names(photo_docs):
    used = set()
    out = []
    for p in photo_docs:
        ext = (p.get("original_filename") or p["storage_path"]).rsplit(".", 1)[-1].lower()
        base = safe_filename(p.get("title") or p.get("original_filename") or p["id"])
        name = f"{base}.{ext}" if not base.lower().endswith(f".{ext}") else base
        n = name
        i = 2
        while n in used:
            stem = name.rsplit(".", 1)[0]
            n = f"{stem} ({i}).{ext}"
            i += 1
        used.add(n)
        out.append(n)
    return out


def assert_json_detail(resp, status, detail):
    assert resp.status_code == status, f"expected {status}, got {resp.status_code}: {resp.text[:300]}"
    ctype = resp.headers.get("content-type", "")
    assert "application/json" in ctype, f"expected JSON content-type, got {ctype}"
    body = resp.json()
    assert body.get("detail") == detail, f"expected detail {detail!r}, got {body!r}"
    return body


def parse_zip_bytes(resp, expected_count=None):
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text[:300] if resp.content else ''}"
    ctype = resp.headers.get("content-type", "")
    assert "application/zip" in ctype, f"expected application/zip, got {ctype}"
    assert resp.content[:4] == b"PK\x03\x04" or resp.content[:4] == b"PK\x05\x06", "response did not start with ZIP signature"
    with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
        bad = zf.testzip()
        assert bad is None, f"zip corrupt at entry {bad}"
        names = zf.namelist()
    if expected_count is not None:
        assert len(names) == expected_count, f"expected {expected_count} zip entries, got {len(names)}: {names}"
    return names


def check_resilience(session, label, results):
    me = session.get(f"{BASE_URL}/api/auth/me", timeout=30)
    albums = session.get(f"{BASE_URL}/api/photos/albums", timeout=30)
    legacy_me = session.get(f"{BASE_URL}/api/me", timeout=30)
    results["resilience"].append({
        "after": label,
        "auth_me_status": me.status_code,
        "albums_status": albums.status_code,
        "legacy_api_me_status": legacy_me.status_code,
        "auth_me_ok": me.status_code == 200,
        "albums_ok": albums.status_code == 200,
    })
    assert me.status_code == 200, f"/api/auth/me not resilient after {label}: {me.status_code} {me.text[:200]}"
    assert albums.status_code == 200, f"/api/photos/albums not resilient after {label}: {albums.status_code} {albums.text[:200]}"


def main():
    env = dotenv_values("/app/backend/.env")
    mongo_url = env.get("MONGO_URL") or "mongodb://localhost:27017"
    db_name = env.get("DB_NAME") or "clubhaven_db"
    client = MongoClient(mongo_url)
    db = client[db_name]
    run_id = uuid.uuid4().hex[:8]
    oversized_album = f"iter159-oversized-{run_id}"

    results = {
        "base_url": BASE_URL,
        "preferred_album": PREFERRED_ALBUM,
        "album_under_test": None,
        "checks": [],
        "resilience": [],
        "oversized_album": oversized_album,
        "passed": False,
    }

    session = requests.Session()
    try:
        # Auth/login sanity.
        login = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
        results["login_status"] = login.status_code
        assert login.status_code == 200, f"login failed: {login.status_code} {login.text[:300]}"
        login_body = login.json()
        if login_body.get("access_token"):
            session.headers.update({"Authorization": f"Bearer {login_body['access_token']}"})
        check_resilience(session, "login", results)

        albums_resp = session.get(f"{BASE_URL}/api/photos/albums", timeout=30)
        assert albums_resp.status_code == 200, f"albums failed: {albums_resp.status_code} {albums_resp.text[:300]}"
        albums = albums_resp.json()
        preferred_album = next((a for a in albums if a.get("name") == PREFERRED_ALBUM), None)
        fallback_album = next((a for a in albums if int(a.get("count") or 0) >= 4), None)
        assert preferred_album or fallback_album, "no real photo album found for happy-path download"
        # The exact production report named 5-Year Anniversary. Preview currently
        # has only two photos there, so exercise whole-album download on that
        # exact album when present, and use any real >=4-photo album for the
        # four-selected-photo path.
        album_for_whole_zip = preferred_album if preferred_album and int(preferred_album.get("count") or 0) > 0 else fallback_album
        album_for_selected_zip = fallback_album if fallback_album else album_for_whole_zip
        ALBUM_NAME = album_for_whole_zip["name"]
        SELECTED_ALBUM_NAME = album_for_selected_zip["name"]
        results["album_under_test"] = ALBUM_NAME
        results["selected_album_under_test"] = SELECTED_ALBUM_NAME
        if preferred_album:
            results["preferred_album_count"] = int(preferred_album.get("count") or 0)
        if SELECTED_ALBUM_NAME != PREFERRED_ALBUM:
            results["selected_album_fallback_reason"] = (
                f"{PREFERRED_ALBUM!r} in preview has fewer than 4 photos; "
                f"used {SELECTED_ALBUM_NAME!r} for the 4-selected-photo assertion."
            )

        photos_resp = session.get(
            f"{BASE_URL}/api/photos",
            params={"album": SELECTED_ALBUM_NAME, "limit": 100, "offset": 0},
            timeout=30,
        )
        assert photos_resp.status_code == 200, f"photos failed: {photos_resp.status_code} {photos_resp.text[:300]}"
        photos = photos_resp.json()
        assert len(photos) >= 4, f"API returned fewer than 4 photos for {SELECTED_ALBUM_NAME}"
        photo_ids = [p["id"] for p in photos[:4]]
        results["selected_photo_ids"] = photo_ids
        results["album_api_count"] = len(photos)

        # DB docs in same sort order as endpoint for exact expected file names.
        docs_album = list(db.photos.find({"album": ALBUM_NAME, "is_deleted": {"$ne": True}}, {"_id": 0}).limit(500))
        expected_album_names = expected_zip_names(docs_album)
        docs_selected = list(db.photos.find({"id": {"$in": photo_ids}, "is_deleted": {"$ne": True}}, {"_id": 0}).limit(500))
        expected_selected_names = expected_zip_names(docs_selected)

        # Happy path: whole album ZIP.
        album_zip = session.post(f"{BASE_URL}/api/photos/download-zip", json={"album": ALBUM_NAME}, timeout=180)
        album_names = parse_zip_bytes(album_zip, expected_count=len(expected_album_names))
        assert sorted(album_names) == sorted(expected_album_names), f"album zip names mismatch: expected {expected_album_names}, got {album_names}"
        results["checks"].append({"name": "whole_album_zip", "status": album_zip.status_code, "entries": album_names})
        check_resilience(session, "whole_album_zip_success", results)

        # Happy path: four selected photos ZIP.
        selected_zip = session.post(f"{BASE_URL}/api/photos/download-zip", json={"photo_ids": photo_ids}, timeout=180)
        selected_names = parse_zip_bytes(selected_zip, expected_count=4)
        assert sorted(selected_names) == sorted(expected_selected_names), f"selected zip names mismatch: expected {expected_selected_names}, got {selected_names}"
        results["checks"].append({"name": "selected_four_zip", "status": selected_zip.status_code, "entries": selected_names})
        check_resilience(session, "selected_four_zip_success", results)

        # Guardrail: empty body -> clean JSON 400.
        empty_resp = session.post(f"{BASE_URL}/api/photos/download-zip", json={}, timeout=30)
        empty_body = assert_json_detail(empty_resp, 400, "Pick photos or pass an album name.")
        results["checks"].append({"name": "empty_body_400", "status": empty_resp.status_code, "body": empty_body})

        # Guardrail: unknown album -> clean JSON 404 and resilience.
        unknown_resp = session.post(
            f"{BASE_URL}/api/photos/download-zip",
            json={"album": f"does-not-exist-{run_id}"},
            timeout=30,
        )
        unknown_body = assert_json_detail(unknown_resp, 404, "No photos to download.")
        results["checks"].append({"name": "unknown_album_404", "status": unknown_resp.status_code, "body": unknown_body})
        check_resilience(session, "unknown_album_404", results)

        # Guardrail: oversized selection/album rejects before storage I/O.
        fake_docs = []
        for i in range(3):
            fake_docs.append({
                "id": f"iter159-fake-{run_id}-{i}",
                "title": f"Oversized fake {i}",
                "album": oversized_album,
                "storage_path": f"clubhaven/photos/fake/{run_id}-{i}.jpg",
                "original_filename": f"oversized-{i}.jpg",
                "content_type": "image/jpeg",
                "size": 200 * 1024 * 1024,
                "size_bytes": 200 * 1024 * 1024,
                "uploaded_by": "iter159-test",
                "uploaded_by_name": "Iter 159 Test",
                "is_deleted": False,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            })
        db.photos.insert_many(fake_docs)
        oversized_resp = session.post(f"{BASE_URL}/api/photos/download-zip", json={"album": oversized_album}, timeout=30)
        assert oversized_resp.status_code == 413, f"expected 413, got {oversized_resp.status_code}: {oversized_resp.text[:300]}"
        assert "application/json" in oversized_resp.headers.get("content-type", ""), "oversized response was not JSON"
        oversized_body = oversized_resp.json()
        assert "Estimated download too large" in oversized_body.get("detail", ""), f"unexpected 413 detail: {oversized_body}"
        results["checks"].append({"name": "oversized_413", "status": oversized_resp.status_code, "body": oversized_body})
        check_resilience(session, "oversized_413", results)

        # Final login endpoint sanity after the affected endpoint has been hammered.
        relogin = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
        results["relogin_status_after_downloads"] = relogin.status_code
        assert relogin.status_code == 200, f"re-login after downloads failed: {relogin.status_code} {relogin.text[:300]}"

        results["passed"] = True
    except Exception as exc:
        results["error"] = str(exc)
        raise
    finally:
        delete_result = db.photos.delete_many({"album": oversized_album})
        results["oversized_cleanup_deleted"] = delete_result.deleted_count
        RESULT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()