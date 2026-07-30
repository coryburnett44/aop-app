#!/usr/bin/env python3
"""Focused verification for iteration 148 photo album performance fix.

Creates a temporary 190-photo album using one real uploaded image as the
backing object, verifies API pagination/count contracts, verifies persistent
thumbnail storage across a backend restart, and leaves the album in place for
the browser/UI verification step. Run cleanup with --cleanup.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient


ROOT = Path("/app")
STATE_FILE = ROOT / "test_reports" / "iteration148_seed_state.json"
API = os.environ.get("TEST_API_URL", "https://club-express-lite.preview.emergentagent.com/api").rstrip("/")
ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"
ALBUM_NAME = os.environ.get("ITER148_ALBUM_NAME", "QA Iter148 Large Album 190")
SMALL_ALBUM_NAME = os.environ.get("ITER148_SMALL_ALBUM_NAME", "QA Iter148 Small Album 3")

def make_test_jpeg() -> bytes:
    """Generate a small real JPEG so thumbnail tests exercise Pillow successfully."""
    from io import BytesIO
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (96, 96), (10, 36, 99))
    draw = ImageDraw.Draw(img)
    draw.rectangle((10, 10, 86, 86), outline=(200, 16, 46), width=6)
    draw.ellipse((30, 30, 66, 66), fill=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


TEST_JPEG = make_test_jpeg()


def load_db():
    load_dotenv(ROOT / "backend" / ".env")
    mongo_url = os.environ["MONGO_URL"].strip('"')
    db_name = os.environ["DB_NAME"].strip('"')
    client = MongoClient(mongo_url)
    return client, client[db_name]


def login() -> tuple[requests.Session, dict]:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    r.raise_for_status()
    return s, r.json()


def api_get_json(session: requests.Session, path: str, timeout: int = 20):
    r = session.get(f"{API}{path}", timeout=timeout)
    r.raise_for_status()
    return r.json(), r


def create_album(session: requests.Session) -> dict:
    albums, _ = api_get_json(session, "/photos/albums")
    existing = next((a for a in albums if a.get("name") == ALBUM_NAME), None)
    if existing:
        return existing
    r = session.post(f"{API}/photos/albums", json={"name": ALBUM_NAME, "category": "anniversary"}, timeout=20)
    r.raise_for_status()
    return r.json()


def upload_source_photo(session: requests.Session) -> dict:
    files = {"file": ("iter148-source.jpg", TEST_JPEG, "image/jpeg")}
    data = {"title": "QA Iter148 source", "album": ALBUM_NAME}
    r = session.post(f"{API}/photos", files=files, data=data, timeout=60)
    r.raise_for_status()
    return r.json()


def seed_large_album(db, user: dict, source_photo: dict) -> int:
    # Clear any previous interrupted run for this deterministic album name.
    db.photos.delete_many({"album": ALBUM_NAME})
    db.photo_albums.update_one(
        {"name": ALBUM_NAME},
        {"$setOnInsert": {"id": str(uuid.uuid4()), "name": ALBUM_NAME, "is_default": False},
         "$set": {"category": "anniversary", "cover_url": ""}},
        upsert=True,
    )
    now = datetime.now(timezone.utc)
    docs = []
    for i in range(190):
        docs.append({
            "id": str(uuid.uuid4()),
            "title": f"QA Iter148 photo {i + 1:03d}",
            "album": ALBUM_NAME,
            "storage_path": source_photo["storage_path"],
            "original_filename": "iter148-source.jpg",
            "content_type": "image/jpeg",
            "size": source_photo.get("size", len(TEST_JPEG)),
            "uploaded_by": user["id"],
            "uploaded_by_name": user.get("name", "QA Admin"),
            "is_deleted": False,
            "created_at": (now - timedelta(seconds=i)).isoformat(),
            "qa_iteration": 148,
        })
    db.photos.insert_many(docs)
    return len(docs)


def restart_backend_and_wait():
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True, timeout=60)
    deadline = time.time() + 90
    last = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{API}/", timeout=5)
            if r.status_code == 200:
                return
            last = f"HTTP {r.status_code}"
        except Exception as exc:  # noqa: BLE001 - diagnostic only
            last = str(exc)
        time.sleep(2)
    raise RuntimeError(f"backend did not become healthy after restart: {last}")


def verify_contracts(session: requests.Session, source_photo: dict):
    results = []

    total, _ = api_get_json(session, f"/photos/count?album={requests.utils.quote(ALBUM_NAME)}")
    assert total["total"] == 190, total
    results.append({"check": "count endpoint", "ok": True, "observed": total})

    pages = []
    for offset, expected_len in [(0, 60), (60, 60), (120, 60), (180, 10)]:
        data, resp = api_get_json(session, f"/photos?album={requests.utils.quote(ALBUM_NAME)}&limit=60&offset={offset}")
        assert resp.status_code == 200
        assert len(data) == expected_len, (offset, len(data), expected_len)
        pages.append(data)
        results.append({"check": f"page offset {offset}", "ok": True, "len": len(data)})
    ids_by_page = [set(p["id"] for p in page) for page in pages]
    for i, ids in enumerate(ids_by_page):
        for j, other in enumerate(ids_by_page):
            if i < j:
                assert ids.isdisjoint(other), f"overlap between page {i} and {j}"
    assert sum(len(ids) for ids in ids_by_page) == 190
    results.append({"check": "no overlap across adjacent/all pages", "ok": True})

    for path in ["/photos?limit=99999&offset=0", "/photos?limit=5&offset=-3", "/photos?limit=-2&offset=0"]:
        r = session.get(f"{API}{path}", timeout=20)
        assert r.status_code == 200, (path, r.status_code, r.text[:200])
        results.append({"check": f"guard {path}", "ok": True, "status": r.status_code, "len": len(r.json())})

    # Persistent thumbnail proof: use a fresh uploaded storage_path, hit once,
    # wait for async storage write, restart backend (clears RAM cache), hit again.
    thumb_path = f"/photos/thumb/{source_photo['storage_path']}?w=1200"
    r1 = session.get(f"{API}{thumb_path}", timeout=60)
    assert r1.status_code == 200, (r1.status_code, r1.text[:200])
    first_cache = r1.headers.get("x-thumb-cache")
    assert first_cache in {"MISS", "HIT", "STORAGE"}, first_cache
    time.sleep(5)
    restart_backend_and_wait()
    # Cookies/JWT remain valid; create a fresh session if proxy dropped them.
    r2 = session.get(f"{API}{thumb_path}", timeout=60)
    if r2.status_code == 401:
        session, _ = login()
        r2 = session.get(f"{API}{thumb_path}", timeout=60)
    assert r2.status_code == 200, (r2.status_code, r2.text[:200])
    second_cache = r2.headers.get("x-thumb-cache")
    assert second_cache == "STORAGE", f"expected STORAGE after backend restart, got {second_cache!r} (first={first_cache!r})"
    results.append({"check": "thumbnail persisted across backend restart", "ok": True, "first": first_cache, "after_restart": second_cache})

    return results


def cleanup():
    client, db = load_db()
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    album_names = [state.get("album_name", ALBUM_NAME), state.get("small_album_name", SMALL_ALBUM_NAME)]
    deleted_photos = db.photos.delete_many({"album": {"$in": album_names}}).deleted_count
    deleted_albums = db.photo_albums.delete_many({"name": {"$in": album_names}}).deleted_count
    client.close()
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    print(json.dumps({"cleanup": True, "albums": album_names, "deleted_photos": deleted_photos, "deleted_albums": deleted_albums}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.cleanup:
        cleanup()
        return

    client, db = load_db()
    session, user = login()
    album = create_album(session)
    source_photo = upload_source_photo(session)
    inserted = seed_large_album(db, user, source_photo)
    client.close()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "album_name": ALBUM_NAME,
        "album_id": album.get("id"),
        "source_storage_path": source_photo["storage_path"],
        "inserted_photos": inserted,
    }, indent=2))
    results = verify_contracts(session, source_photo)
    print(json.dumps({"ok": True, "album": ALBUM_NAME, "inserted_photos": inserted, "results": results}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - test diagnostic
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        raise