#!/usr/bin/env python3
"""Seed a temporary 3-photo album for the iteration 148 small-album UI edge case."""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path("/app")
STATE_FILE = ROOT / "test_reports" / "iteration148_seed_state.json"
SMALL_ALBUM_NAME = "QA Iter148 Small Album 3"


def main():
    if not STATE_FILE.exists():
        raise SystemExit("Run bug_verification_iteration148_api.py first so a real source_storage_path exists.")
    state = json.loads(STATE_FILE.read_text())
    source_path = state["source_storage_path"]
    load_dotenv(ROOT / "backend" / ".env")
    client = MongoClient(os.environ["MONGO_URL"].strip('"'))
    db = client[os.environ["DB_NAME"].strip('"')]
    user = db.users.find_one({"email": "admin@clubhaven.app"}, {"_id": 0}) or {}
    db.photos.delete_many({"album": SMALL_ALBUM_NAME})
    album_id = str(uuid.uuid4())
    db.photo_albums.delete_many({"name": SMALL_ALBUM_NAME})
    db.photo_albums.insert_one({
        "id": album_id,
        "name": SMALL_ALBUM_NAME,
        "is_default": False,
        "created_by": user.get("id"),
        "created_by_name": user.get("name", "QA Admin"),
        "category": "anniversary",
        "cover_url": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    now = datetime.now(timezone.utc)
    docs = []
    for i in range(3):
        docs.append({
            "id": str(uuid.uuid4()),
            "title": f"QA Iter148 small photo {i + 1}",
            "album": SMALL_ALBUM_NAME,
            "storage_path": source_path,
            "original_filename": "iter148-source.jpg",
            "content_type": "image/jpeg",
            "size": 633,
            "uploaded_by": user.get("id"),
            "uploaded_by_name": user.get("name", "QA Admin"),
            "is_deleted": False,
            "created_at": (now - timedelta(seconds=i)).isoformat(),
            "qa_iteration": 148,
        })
    db.photos.insert_many(docs)
    client.close()
    state["small_album_name"] = SMALL_ALBUM_NAME
    state["small_album_id"] = album_id
    state["small_inserted_photos"] = 3
    STATE_FILE.write_text(json.dumps(state, indent=2))
    print(json.dumps({"ok": True, "small_album_name": SMALL_ALBUM_NAME, "small_album_id": album_id, "photos": 3}, indent=2))


if __name__ == "__main__":
    main()