"""Photo routes — albums + photos + bulk upload + ZIP download.

Extracted from server.py for clarity. The seed (`seed_default_photo_albums`,
`DEFAULT_PHOTO_ALBUMS`, `reconcile_pending_set_password`) and the
`auto_categorize_album` helper still live in server.py because they are needed
at boot before the route registration happens; we just import the helper into
this module via the register() kwargs.

Public surface (paths preserved verbatim):
  GET    /api/photos
  GET    /api/photos/albums
  POST   /api/photos/albums
  PUT    /api/photos/albums/{album_id}
  DELETE /api/photos/albums/{album_id}
  POST   /api/photos
  POST   /api/photos/bulk
  DELETE /api/photos/{photo_id}
  POST   /api/photos/download-zip
"""
import asyncio
import re
import tempfile
import uuid
import zipfile
from typing import List, Optional

from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


def register(
    api,
    *,
    db,
    get_current_user,
    photo_out,
    put_object,
    get_object,
    iso,
    now_utc,
    logger,
    image_ext,
    mime_by_ext,
    app_name,
    photo_album_categories,
    auto_categorize_album,
):
    # ---------- List photos ----------
    @api.get("/photos")
    async def list_photos(album: Optional[str] = None):
        query = {"is_deleted": {"$ne": True}}
        if album:
            query["album"] = album
        cursor = db.photos.find(query, {"_id": 0}).sort("created_at", -1).limit(500)
        items = await cursor.to_list(500)
        return [photo_out(p) for p in items]

    # ---------- Albums ----------
    @api.get("/photos/albums")
    async def list_photo_albums(category: Optional[str] = None):
        """Returns every album the chapter has — canonical + admin-created +
        any albums a member auto-created on upload. Pass `?category=anniversary`
        to filter."""
        q: dict = {}
        if category and category in photo_album_categories:
            q["category"] = category
        albums = await db.photo_albums.find(q, {"_id": 0}).sort([("is_default", -1), ("name", 1)]).to_list(500)
        pipeline = [
            {"$match": {"is_deleted": {"$ne": True}}},
            {"$group": {"_id": "$album", "count": {"$sum": 1}, "first_photo": {"$first": "$storage_path"}}},
        ]
        counts: dict = {}
        first_photos: dict = {}
        async for d in db.photos.aggregate(pipeline):
            key = d["_id"] or "general"
            counts[key] = d["count"]
            first_photos[key] = d.get("first_photo")
        out = []
        for a in albums:
            cover = a.get("cover_url") or ""
            if not cover:
                fp = first_photos.get(a["name"])
                if fp:
                    cover = f"/api/files/{fp}"
            out.append({
                "id": a.get("id"),
                "name": a["name"],
                "count": counts.get(a["name"], 0),
                "is_default": a.get("is_default", False),
                "created_by": a.get("created_by"),
                "created_by_name": a.get("created_by_name", ""),
                "category": a.get("category", auto_categorize_album(a["name"])),
                "cover_url": cover,
            })
        return out

    class AlbumIn(BaseModel):
        name: str
        category: Optional[str] = None
        cover_url: Optional[str] = None

    @api.post("/photos/albums")
    async def create_photo_album(body: AlbumIn, user: dict = Depends(get_current_user)):
        name = (body.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Album name is required.")
        existing = await db.photo_albums.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
        if existing:
            raise HTTPException(status_code=400, detail=f"Album '{existing['name']}' already exists.")
        category = body.category if (body.category in photo_album_categories) else auto_categorize_album(name)
        doc = {
            "id": str(uuid.uuid4()),
            "name": name,
            "is_default": False,
            "created_by": user["id"],
            "created_by_name": user.get("name", ""),
            "category": category,
            "cover_url": (body.cover_url or "").strip(),
            "created_at": iso(now_utc()),
        }
        await db.photo_albums.insert_one(doc)
        return {"id": doc["id"], "name": name, "count": 0, "is_default": False, "created_by_name": user.get("name", ""), "category": category, "cover_url": doc["cover_url"]}

    class AlbumUpdateIn(BaseModel):
        name: Optional[str] = None
        category: Optional[str] = None
        cover_url: Optional[str] = None
        cover_photo_id: Optional[str] = None

    @api.put("/photos/albums/{album_id}")
    async def update_photo_album(album_id: str, body: AlbumUpdateIn, user: dict = Depends(get_current_user)):
        a = await db.photo_albums.find_one({"id": album_id})
        if not a:
            raise HTTPException(status_code=404, detail="Album not found")
        is_admin = user.get("role") == "admin"
        is_creator = a.get("created_by") == user["id"]
        if not (is_admin or is_creator):
            raise HTTPException(status_code=403, detail="Only the album creator or an admin can edit this album.")
        updates: dict = {}
        # ---- Rename ----
        if body.name is not None:
            new_name = body.name.strip()
            if not new_name:
                raise HTTPException(status_code=400, detail="Album name cannot be empty.")
            if new_name != a.get("name"):
                # Case-insensitive uniqueness across all OTHER albums.
                clash = await db.photo_albums.find_one({
                    "id": {"$ne": album_id},
                    "name": {"$regex": f"^{re.escape(new_name)}$", "$options": "i"},
                })
                if clash:
                    raise HTTPException(status_code=400, detail=f"Album '{clash['name']}' already exists.")
                updates["name"] = new_name
                # Cascade rename to every photo whose `album` field references
                # the old name (photos are bucketed by album NAME, not id).
                await db.photos.update_many(
                    {"album": a["name"]},
                    {"$set": {"album": new_name}},
                )
                # If this was a default (canonical-seeded) album, tombstone the
                # OLD canonical name so the boot-time `seed_default_photo_albums`
                # doesn't re-create it. The renamed album also loses its
                # `is_default` badge — it's now a regular admin-managed album.
                if a.get("is_default"):
                    await db.deleted_default_albums.update_one(
                        {"name": a["name"]},
                        {"$setOnInsert": {
                            "name": a["name"],
                            "renamed_to": new_name,
                            "renamed_by": user["id"],
                            "renamed_by_name": user.get("name", ""),
                            "renamed_at": iso(now_utc()),
                        }},
                        upsert=True,
                    )
                    updates["is_default"] = False
        if body.category and body.category in photo_album_categories:
            updates["category"] = body.category
        if body.cover_url is not None:
            updates["cover_url"] = body.cover_url
        if body.cover_photo_id:
            # Look up by the (possibly new) album name.
            current_name = updates.get("name") or a["name"]
            p = await db.photos.find_one({"id": body.cover_photo_id, "album": current_name}, {"_id": 0})
            if p:
                updates["cover_url"] = f"/api/files/{p['storage_path']}"
        if updates:
            await db.photo_albums.update_one({"id": album_id}, {"$set": updates})
        fresh = await db.photo_albums.find_one({"id": album_id}, {"_id": 0})
        return {
            "id": fresh.get("id"),
            "name": fresh.get("name"),
            "category": fresh.get("category", "other"),
            "cover_url": fresh.get("cover_url", ""),
        }

    @api.delete("/photos/albums/{album_id}")
    async def delete_photo_album(album_id: str, user: dict = Depends(get_current_user)):
        """Admins can delete any album (including default/canonical ones).
        Members can only delete custom albums they created. Default albums that
        an admin deletes are tombstoned in `deleted_default_albums` so the
        boot-time seeder does not silently resurrect them. Photos inside the
        album are NOT deleted — their `album` field stays so they remain
        queryable."""
        a = await db.photo_albums.find_one({"id": album_id})
        if not a:
            raise HTTPException(status_code=404, detail="Album not found")
        is_admin = user.get("role") == "admin"
        is_creator = a.get("created_by") == user["id"]
        if not is_admin and a.get("is_default"):
            raise HTTPException(status_code=403, detail="Default albums can only be removed by an admin.")
        if not (is_admin or is_creator):
            raise HTTPException(status_code=403, detail="Only the album creator or an admin may delete this album.")
        if a.get("is_default") and is_admin:
            await db.deleted_default_albums.update_one(
                {"name": a["name"]},
                {"$setOnInsert": {
                    "name": a["name"],
                    "deleted_by": user["id"],
                    "deleted_by_name": user.get("name", ""),
                    "deleted_at": iso(now_utc()),
                }},
                upsert=True,
            )
        await db.photo_albums.delete_one({"id": album_id})
        return {"ok": True}

    # ---------- Photo upload (single + bulk) ----------
    @api.post("/photos")
    async def upload_photo(
        file: UploadFile = File(...),
        title: str = Form(""),
        album: str = Form("general"),
        user: dict = Depends(get_current_user),
    ):
        ext = (file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "bin").lower()
        if ext not in image_ext:
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {ext}")
        content_type = file.content_type or mime_by_ext.get(ext, "application/octet-stream")
        path = f"{app_name}/photos/{user['id']}/{uuid.uuid4()}.{ext}"
        data = await file.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 10MB)")
        result = put_object(path, data, content_type)
        album_name = (album or "general").strip() or "general"
        await db.photo_albums.update_one(
            {"name": album_name},
            {"$setOnInsert": {
                "id": str(uuid.uuid4()),
                "name": album_name,
                "is_default": False,
                "created_by": user["id"],
                "created_by_name": user.get("name", ""),
                "created_at": iso(now_utc()),
            }},
            upsert=True,
        )
        doc = {
            "id": str(uuid.uuid4()),
            "title": title,
            "album": album_name,
            "storage_path": result["path"],
            "original_filename": file.filename,
            "content_type": content_type,
            "size": result.get("size", len(data)),
            "uploaded_by": user["id"],
            "uploaded_by_name": user.get("name", ""),
            "is_deleted": False,
            "created_at": iso(now_utc()),
        }
        await db.photos.insert_one(doc)
        return photo_out(doc)

    @api.post("/photos/bulk")
    async def upload_photos_bulk(
        files: List[UploadFile] = File(...),
        album: str = Form("general"),
        user: dict = Depends(get_current_user),
    ):
        """Upload many photos at once into a single album. Returns
        {uploaded: [...photo_out], failed: [{name, error}]}. Caps total batch
        at 50 files / 100 MB."""
        if len(files) > 50:
            raise HTTPException(status_code=400, detail="Upload up to 50 photos per batch.")
        album_name = (album or "general").strip() or "general"
        await db.photo_albums.update_one(
            {"name": album_name},
            {"$setOnInsert": {
                "id": str(uuid.uuid4()), "name": album_name, "is_default": False,
                "created_by": user["id"], "created_by_name": user.get("name", ""),
                "created_at": iso(now_utc()),
            }},
            upsert=True,
        )
        uploaded, failed = [], []
        total_bytes = 0
        for f in files:
            try:
                data = await f.read()
                if len(data) > 10 * 1024 * 1024:
                    failed.append({"name": f.filename, "error": "Over 10MB"}); continue
                total_bytes += len(data)
                if total_bytes > 100 * 1024 * 1024:
                    failed.append({"name": f.filename, "error": "Batch exceeded 100MB"}); continue
                ext = (f.filename.rsplit(".", 1)[-1] if f.filename and "." in f.filename else "bin").lower()
                if ext not in image_ext:
                    failed.append({"name": f.filename, "error": "Not an image"}); continue
                content_type = f.content_type or mime_by_ext.get(ext, "image/jpeg")
                path = f"{app_name}/photos/{user['id']}/{uuid.uuid4()}.{ext}"
                result = put_object(path, data, content_type)
                doc = {
                    "id": str(uuid.uuid4()),
                    "title": "",
                    "album": album_name,
                    "storage_path": result["path"],
                    "original_filename": f.filename,
                    "content_type": content_type,
                    "size": result.get("size", len(data)),
                    "uploaded_by": user["id"],
                    "uploaded_by_name": user.get("name", ""),
                    "is_deleted": False,
                    "created_at": iso(now_utc()),
                }
                await db.photos.insert_one(doc)
                uploaded.append(photo_out(doc))
            except Exception as e:
                failed.append({"name": getattr(f, "filename", "unknown"), "error": str(e)})
        return {"uploaded": uploaded, "failed": failed}

    @api.delete("/photos/{photo_id}")
    async def delete_photo(photo_id: str, user: dict = Depends(get_current_user)):
        p = await db.photos.find_one({"id": photo_id})
        if not p:
            raise HTTPException(status_code=404, detail="Not found")
        if p.get("uploaded_by") != user["id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not allowed")
        await db.photos.update_one({"id": photo_id}, {"$set": {"is_deleted": True}})
        return {"ok": True}

    # ---------- Photo bulk download (zip) ----------
    class PhotoDownloadIn(BaseModel):
        photo_ids: List[str] = Field(default_factory=list, max_length=500)
        album: Optional[str] = None  # if set, downloads the entire album

    def _safe_filename(s: str) -> str:
        s = re.sub(r"[^a-zA-Z0-9._ -]", "_", s or "")[:120]
        return s or "photo"

    @api.post("/photos/download-zip")
    async def download_photos_zip(body: PhotoDownloadIn, user: dict = Depends(get_current_user)):
        """Build a ZIP of one or more photos (or an entire album) and stream
        it back.

        Why a SpooledTemporaryFile + chunked StreamingResponse:
          - Building the entire zip in a BytesIO blocked the event loop and
            held the whole archive in RAM. Large albums (hundreds of MB) would
            either OOM the worker or hit Cloudflare's 100-second proxy timeout
            because no bytes were sent until the zip was fully built.
          - A SpooledTemporaryFile keeps small archives in memory but spills
            to disk past 50 MB, so RAM stays bounded.
          - We yield 64 KB chunks via an async generator so bytes start
            flowing back through Cloudflare immediately and the user sees a
            real download progress bar instead of a hung browser.
        """
        q: dict = {"is_deleted": {"$ne": True}}
        if body.album:
            q["album"] = body.album
        elif body.photo_ids:
            q["id"] = {"$in": body.photo_ids}
        else:
            raise HTTPException(status_code=400, detail="Pick photos or pass an album name.")
        photos = await db.photos.find(q, {"_id": 0}).to_list(500)
        if not photos:
            raise HTTPException(status_code=404, detail="No photos to download.")

        spool = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024, mode="w+b")
        used_names: set = set()

        def _build_zip():
            with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                for p in photos:
                    try:
                        data, _ct = get_object(p["storage_path"])
                    except Exception as e:
                        logger.warning(f"Skipping photo {p.get('id')} in zip: {e}")
                        continue
                    ext = (p.get("original_filename") or p["storage_path"]).rsplit(".", 1)[-1].lower()
                    base = _safe_filename(p.get("title") or p.get("original_filename") or p["id"])
                    name = f"{base}.{ext}" if not base.lower().endswith(f".{ext}") else base
                    n = name
                    i = 2
                    while n in used_names:
                        stem = name.rsplit(".", 1)[0]
                        n = f"{stem} ({i}).{ext}"
                        i += 1
                    used_names.add(n)
                    zf.writestr(n, data)
            spool.seek(0)

        # Build the archive off the event loop so the server can keep
        # responding to other requests while a big album is zipping.
        await asyncio.to_thread(_build_zip)

        async def _iter_chunks(chunk_size: int = 64 * 1024):
            try:
                while True:
                    chunk = await asyncio.to_thread(spool.read, chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                spool.close()

        album_label = _safe_filename(body.album or "photos")
        headers = {"Content-Disposition": f'attachment; filename="aop-{album_label}.zip"'}
        return StreamingResponse(_iter_chunks(), media_type="application/zip", headers=headers)
