#!/usr/bin/env python3
"""Focused Iter 160 backend verification for photo downscale/WebP ingest.

Creates realistic JPEG uploads, exercises the protected upload/backfill/zip
endpoints through the preview API, and writes structured evidence for the
testing report. This is test-only code; it does not modify product files.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv
from PIL import Image
from pymongo import MongoClient


ROOT = Path("/app")
REPORT_DIR = ROOT / "test_reports"
ARTIFACT_DIR = ROOT / "test_reports" / "artifacts_iter160"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / "frontend" / ".env")
load_dotenv(ROOT / "backend" / ".env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://club-express-lite.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
ADMIN_EMAIL = "admin@clubhaven.app"
ADMIN_PASSWORD = "Admin123!"
MEMBER_EMAIL = "member@clubhaven.app"
MEMBER_PASSWORD = "Member123!"
APP_NAME = "clubhaven"
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"

RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
TEST_ALBUM = f"Iter160 QA WebP {RUN_ID}"
LEGACY_ALBUM = f"Iter160 QA Legacy {RUN_ID}"

results: dict = {
    "base_url": BASE,
    "run_id": RUN_ID,
    "test_album": TEST_ALBUM,
    "legacy_album": LEGACY_ALBUM,
    "checks": [],
    "created_photo_ids": [],
    "created_storage_paths": [],
}


def record(name: str, ok: bool, **details):
    item = {"name": name, "ok": bool(ok), **details}
    results["checks"].append(item)
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {json.dumps(details, default=str)[:1000]}")
    return ok


def fail(name: str, exc: Exception | str):
    return record(name, False, error=str(exc))


def save_results():
    out = REPORT_DIR / "iter160_downscale_api_results.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"Wrote {out}")


def make_realistic_jpeg(path: Path, seed: int, target_min=3 * 1024 * 1024, target_max=5 * 1024 * 1024) -> int:
    """Create a photo-like JPEG in the requested 3-5 MB range."""
    rng = np.random.default_rng(seed)
    candidates = [(3600, 2400), (4000, 2667), (4500, 3000), (5000, 3333)]
    best_under = None
    best_any = None
    for width, height in candidates:
        x = np.linspace(0, 1, width, dtype=np.float32)
        y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
        arr = np.empty((height, width, 3), dtype=np.float32)
        # Sky/grass/warm-light style gradients with mild sensor noise: large
        # enough JPEGs but still photo-realistic enough to downscale well.
        arr[..., 0] = 80 + 115 * x + 25 * np.sin(8 * y + seed)
        arr[..., 1] = 95 + 80 * y + 35 * np.sin(5 * x + seed / 3)
        arr[..., 2] = 135 + 55 * (1 - y) + 20 * np.cos(6 * x)
        noise = rng.normal(0, 15, size=(height, width, 3)).astype(np.float32)
        arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr, "RGB")
        for quality in range(96, 72, -2):
            img.save(path, format="JPEG", quality=quality, optimize=True, progressive=True)
            size = path.stat().st_size
            best_any = size
            if size <= target_max:
                best_under = size
            if target_min <= size <= target_max:
                return size
    if best_under and best_under >= target_min:
        return best_under
    raise RuntimeError(f"Could not generate JPEG in 3-5MB range; last={best_any}, best_under={best_under}")


def login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    data = r.json()
    token = data.get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    record(f"login {email}", True, status=r.status_code, role=data.get("role"), user_id=data.get("id"))
    return s


def health(session: requests.Session, label: str) -> bool:
    try:
        me = session.get(f"{API}/auth/me", timeout=20)
        albums = session.get(f"{API}/photos/albums", timeout=20)
        ok = me.status_code == 200 and albums.status_code == 200
        return record(f"post-op health after {label}", ok, auth_me_status=me.status_code, albums_status=albums.status_code)
    except Exception as e:
        return fail(f"post-op health after {label}", e)


def assert_downscaled_photo(session: requests.Session, payload: dict, original_size: int, label: str) -> bool:
    checks = {
        "downscaled": payload.get("downscaled") is True,
        "content_type": payload.get("content_type") == "image/webp",
        "storage_path_webp": str(payload.get("storage_path", "")).endswith(".webp"),
        "original_size_matches": payload.get("original_size") == original_size,
        "size_reduced_80pct": isinstance(payload.get("size"), int) and payload.get("size") < original_size * 0.20,
    }
    fetched = None
    try:
        fr = session.get(f"{BASE}{payload['url']}", timeout=60)
        fetched = {"status": fr.status_code, "content_type": fr.headers.get("Content-Type"), "bytes": len(fr.content)}
        img = Image.open(io.BytesIO(fr.content))
        fetched["format"] = img.format
        fetched["width"] = img.width
        checks["served_file_webp"] = fr.status_code == 200 and img.format == "WEBP" and "image/webp" in (fr.headers.get("Content-Type") or "")
        checks["served_width_lte_1200"] = img.width <= 1200
    except Exception as e:
        fetched = {"error": str(e)}
        checks["served_file_webp"] = False
        checks["served_width_lte_1200"] = False
    ok = all(checks.values())
    record(label, ok, photo_id=payload.get("id"), storage_path=payload.get("storage_path"), original_size=original_size, returned_size=payload.get("size"), reduction_pct=round((1 - (payload.get("size", original_size) / original_size)) * 100, 2), checks=checks, fetched=fetched)
    if payload.get("id"):
        results["created_photo_ids"].append(payload["id"])
    if payload.get("storage_path"):
        results["created_storage_paths"].append(payload["storage_path"])
    return ok


def upload_single(session: requests.Session, jpeg_path: Path) -> dict | None:
    try:
        original_size = jpeg_path.stat().st_size
        with jpeg_path.open("rb") as f:
            r = session.post(
                f"{API}/photos",
                data={"title": f"Iter160 single {RUN_ID}", "album": TEST_ALBUM},
                files={"file": (jpeg_path.name, f, "image/jpeg")},
                timeout=120,
            )
        ok_status = record("single upload status", r.status_code == 200, status=r.status_code, text=r.text[:300])
        if not ok_status:
            return None
        payload = r.json()
        assert_downscaled_photo(session, payload, original_size, "single upload returns downscaled WebP metadata and serves small WebP")
        return payload
    except Exception as e:
        fail("single upload exception", e)
        return None


def upload_bulk(session: requests.Session, jpeg_paths: list[Path]) -> list[dict]:
    try:
        handles = [p.open("rb") for p in jpeg_paths]
        try:
            files = [("files", (p.name, h, "image/jpeg")) for p, h in zip(jpeg_paths, handles)]
            r = session.post(f"{API}/photos/bulk", data={"album": TEST_ALBUM}, files=files, timeout=180)
        finally:
            for h in handles:
                h.close()
        ok_status = record("bulk upload status", r.status_code == 200, status=r.status_code, text=r.text[:500])
        if not ok_status:
            return []
        payload = r.json()
        uploaded = payload.get("uploaded") or []
        failed = payload.get("failed") or []
        row_ok = len(uploaded) == len(jpeg_paths) and not failed
        record("bulk upload row count", row_ok, uploaded_count=len(uploaded), failed=failed)
        by_name_size = {p.name: p.stat().st_size for p in jpeg_paths}
        for row in uploaded:
            original = by_name_size.get(row.get("original_filename"), row.get("original_size") or 0)
            assert_downscaled_photo(session, row, original, f"bulk row {row.get('original_filename')} downscaled WebP")
        return uploaded
    except Exception as e:
        fail("bulk upload exception", e)
        return []


def storage_put(path: str, data: bytes, content_type: str) -> dict:
    init = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ.get("EMERGENT_LLM_KEY")}, timeout=30)
    init.raise_for_status()
    key = init.json().get("storage_key")
    if not key:
        raise RuntimeError("No storage_key from object storage init")
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def seed_legacy_photo(admin_user_id: str, jpeg_path: Path) -> dict:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = MongoClient(mongo_url)
    db = client[db_name]
    raw = jpeg_path.read_bytes()
    storage_path = f"{APP_NAME}/photos/{admin_user_id}/{uuid.uuid4()}.jpg"
    put = storage_put(storage_path, raw, "image/jpeg")
    now = datetime.now(timezone.utc).isoformat()
    db.photo_albums.update_one(
        {"name": LEGACY_ALBUM},
        {"$setOnInsert": {"id": str(uuid.uuid4()), "name": LEGACY_ALBUM, "is_default": False, "created_by": admin_user_id, "created_by_name": "QA", "category": "other", "cover_url": "", "created_at": now}},
        upsert=True,
    )
    doc = {
        "id": str(uuid.uuid4()),
        "title": f"Iter160 legacy backfill {RUN_ID}",
        "album": LEGACY_ALBUM,
        "storage_path": put.get("path", storage_path),
        "original_filename": jpeg_path.name,
        "content_type": "image/jpeg",
        "size": len(raw),
        "original_size": len(raw),
        "downscaled": False,
        "uploaded_by": admin_user_id,
        "uploaded_by_name": "QA Admin",
        "is_deleted": False,
        "created_at": now,
    }
    db.photos.insert_one(doc)
    results["seeded_legacy_photo"] = {k: v for k, v in doc.items() if k != "_id"}
    results["created_photo_ids"].append(doc["id"])
    results["created_storage_paths"].append(doc["storage_path"])
    record("seed legacy large JPEG in storage/db", True, photo_id=doc["id"], storage_path=doc["storage_path"], size=doc["size"], album=LEGACY_ALBUM)
    return doc


def test_backfill(admin: requests.Session, member: requests.Session, legacy_doc: dict):
    unauth = requests.Session().post(f"{API}/photos/backfill-downscale?limit=5", timeout=30)
    record("backfill unauthenticated is 401", unauth.status_code == 401, status=unauth.status_code, text=unauth.text[:200])
    health(admin, "backfill unauthenticated 401")

    forbidden = member.post(f"{API}/photos/backfill-downscale?limit=5", timeout=30)
    record("backfill non-admin is 403", forbidden.status_code == 403, status=forbidden.status_code, text=forbidden.text[:200])
    health(admin, "backfill non-admin 403")

    r = admin.post(f"{API}/photos/backfill-downscale?limit=5&album={requests.utils.quote(LEGACY_ALBUM)}", timeout=180)
    ok_status = record("backfill admin status", r.status_code == 200, status=r.status_code, text=r.text[:500])
    if not ok_status:
        return
    payload = r.json()
    expected_keys = {"processed", "skipped", "batch_size", "saved_bytes", "saved_mb", "has_more", "remaining"}
    ok_payload = expected_keys.issubset(payload.keys()) and payload.get("processed", 0) > 0 and payload.get("saved_bytes", 0) > 0
    record("backfill admin payload processed legacy and is well formed", ok_payload, payload=payload, expected_keys=sorted(expected_keys))

    # Verify the legacy DB row now points to a WebP and serves <=1200px.
    photos = admin.get(f"{API}/photos?album={requests.utils.quote(LEGACY_ALBUM)}&limit=10", timeout=30)
    if photos.status_code == 200 and photos.json():
        row = next((p for p in photos.json() if p.get("id") == legacy_doc["id"]), photos.json()[0])
        checks = {
            "downscaled": row.get("downscaled") is True,
            "content_type": row.get("content_type") == "image/webp",
            "storage_path_webp": str(row.get("storage_path", "")).endswith(".webp"),
            "size_reduced": (row.get("size") or legacy_doc["size"]) < legacy_doc["size"],
        }
        record("backfilled row metadata converted to WebP", all(checks.values()), row=row, checks=checks)
    else:
        record("backfilled row metadata converted to WebP", False, status=photos.status_code, text=photos.text[:300])
    health(admin, "admin backfill")


def test_album_zip(admin: requests.Session):
    album = "Commitment Ceremony 2026"
    try:
        photo_list = admin.get(f"{API}/photos?album={requests.utils.quote(album)}&limit=500", timeout=30)
        est_total = None
        count = None
        if photo_list.status_code == 200:
            rows = photo_list.json()
            count = len(rows)
            est_total = sum(int(p.get("size") or 0) for p in rows)
        r = admin.post(f"{API}/photos/download-zip", json={"album": album}, timeout=240)
        details = {"status": r.status_code, "content_type": r.headers.get("Content-Type"), "bytes": len(r.content), "album_photo_count": count, "album_est_total_bytes": est_total}
        if r.status_code == 200:
            bio = io.BytesIO(r.content)
            is_zip = zipfile.is_zipfile(bio)
            names = []
            if is_zip:
                with zipfile.ZipFile(bio) as zf:
                    names = zf.namelist()
            details.update({"is_zip": is_zip, "zip_entries": len(names), "first_entries": names[:5], "pct_of_500mb_guardrail": round((len(r.content) / (500 * 1024 * 1024)) * 100, 4)})
            ok = is_zip and len(names) > 0 and len(r.content) < 50 * 1024 * 1024
        else:
            details["text"] = r.text[:500]
            ok = False
        record("whole-album download zip works and is far below guardrail", ok, **details)
    except Exception as e:
        fail("whole-album download zip exception", e)
    health(admin, "whole-album download zip")


def main() -> int:
    try:
        jpgs = []
        for i in range(4):
            p = ARTIFACT_DIR / f"iter160_source_{RUN_ID}_{i}.jpg"
            size = make_realistic_jpeg(p, seed=1600 + i)
            jpgs.append(p)
            record("generated 3-5MB source JPEG", 3 * 1024 * 1024 <= size <= 5 * 1024 * 1024, path=str(p), size=size)

        admin = login(ADMIN_EMAIL, ADMIN_PASSWORD)
        admin_me = admin.get(f"{API}/auth/me", timeout=20).json()
        member = login(MEMBER_EMAIL, MEMBER_PASSWORD)

        upload_single(admin, jpgs[0])
        health(admin, "single upload")

        upload_bulk(admin, jpgs[1:4])
        health(admin, "bulk upload")

        legacy = seed_legacy_photo(admin_me["id"], jpgs[0])
        test_backfill(admin, member, legacy)

        test_album_zip(admin)

    except Exception as e:
        fail("test harness fatal", e)
    finally:
        save_results()

    failed = [c for c in results["checks"] if not c.get("ok")]
    print(f"Total checks={len(results['checks'])}; failures={len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())