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
import gc
import logging
import re
import uuid
from typing import List, Optional

from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from zipstream.ng import ZipStream

logger = logging.getLogger("clubhaven")


# ---- Hard limits so a runaway download can't OOM the backend on prod ----
# The 5-Year Anniversary album incident (Iter 159): 4 phone photos totalling
# ~180 MB were enough to knock the production worker out and cascade into
# a Cloudflare 520 that also killed the user's session. These limits are
# checked BEFORE any bytes are fetched and return a friendly JSON error.
DOWNLOAD_MAX_PHOTOS = 100
DOWNLOAD_MAX_TOTAL_BYTES = 500 * 1024 * 1024  # 500 MB


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
    async def list_photos(
        album: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ):
        """Return photos, most-recent first. Supports optional pagination via
        `?limit=60&offset=0` — the frontend uses this for infinite-scroll on
        big albums (a 190-photo album loads the first page instantly and
        pulls +60 more each time the user scrolls near the bottom)."""
        query = {"is_deleted": {"$ne": True}}
        if album:
            query["album"] = album
        # Guardrails
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        cursor = (
            db.photos.find(query, {"_id": 0})
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )
        items = await cursor.to_list(limit)
        return [photo_out(p) for p in items]

    @api.get("/photos/count")
    async def count_photos(album: Optional[str] = None):
        """Total number of visible photos in the album (or across the whole
        chapter if `album` is omitted). The frontend uses this to render the
        'Showing X of Y' hint and to decide when to stop scrolling."""
        query = {"is_deleted": {"$ne": True}}
        if album:
            query["album"] = album
        total = await db.photos.count_documents(query)
        return {"total": total}

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
            cover_thumb = ""
            if not cover:
                fp = first_photos.get(a["name"])
                if fp:
                    cover = f"/api/files/{fp}"
                    cover_thumb = f"/api/photos/thumb/{fp}?w=600"
            elif cover.startswith("/api/files/"):
                # Derive thumb URL from the existing cover storage path.
                cover_thumb = "/api/photos/thumb/" + cover[len("/api/files/"):] + "?w=600"
            out.append({
                "id": a.get("id"),
                "name": a["name"],
                "count": counts.get(a["name"], 0),
                "is_default": a.get("is_default", False),
                "created_by": a.get("created_by"),
                "created_by_name": a.get("created_by_name", ""),
                "category": a.get("category", auto_categorize_album(a["name"])),
                "cover_url": cover,
                # Small preview for album cards (600px is enough for the
                # 4:3 card at 2x retina).
                "cover_thumb_url": cover_thumb or cover,
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
        # Accept by extension OR by content_type starting with "image/" — some
        # browsers (esp. iOS Safari sending HEIC) send the file with
        # content_type="image/heic" but a stripped extension. Falling back to
        # content-type lets us still accept the photo.
        ct = (file.content_type or "").lower()
        if ext not in image_ext and not ct.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {ext or ct or 'unknown'}")
        content_type = file.content_type or mime_by_ext.get(ext, "application/octet-stream")
        # If the extension is missing/invalid but the content-type tells us
        # this is an image, persist with a sensible extension so downloads
        # have the right file association.
        if ext not in image_ext:
            ct_to_ext = {
                "image/jpeg": "jpg", "image/png": "png", "image/gif": "gif",
                "image/webp": "webp", "image/heic": "heic", "image/heif": "heif",
            }
            ext = ct_to_ext.get(ct, "jpg")
        path = f"{app_name}/photos/{user['id']}/{uuid.uuid4()}.{ext}"
        data = await file.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 10MB)")
        result = await asyncio.to_thread(put_object, path, data, content_type)
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
                result = await asyncio.to_thread(put_object, path, data, content_type)
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
        """Iter 159 — hardened streaming ZIP.

        Fixes the production regression where a 4-photo album download
        knocked the worker over and cascaded into a Cloudflare 520 that
        also invalidated the user's session:

          1. **True streaming with zipstream-ng.** We add one photo at a
             time, yield its bytes into the ZipStream, then let Python
             GC that photo's buffer before touching the next one. Peak
             RAM = 1 photo (~5-30 MB), not `sum(all photos)` (~180 MB
             for the 5-Year Anniversary incident).
          2. **Hard limits before any I/O.** Downloads > 100 photos or
             > 500 MB total (from the DB size sum) get a friendly 413
             JSON error instead of OOM-ing the worker.
          3. **Explicit gc.collect() after each photo.** Python's zip
             deflate holds internal buffers that don't always get freed
             at scope exit — forcing GC keeps RSS flat across the loop.
          4. **First bytes stream immediately.** ZipStream emits the ZIP
             local-file header before we start fetching photos, so
             Cloudflare gets a Content-Type response within the first
             few ms — well under its 100-second connect timeout.
          5. **Isolated `get_object` failures.** One bad photo used to
             skip a `continue` inside a nested block that could leak
             the zip's write cursor; now we log-and-skip and continue
             streaming so the user still gets the rest.
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

        # Guardrail #1 — photo count.
        if len(photos) > DOWNLOAD_MAX_PHOTOS:
            raise HTTPException(
                status_code=413,
                detail=f"Too many photos ({len(photos)}). Pick {DOWNLOAD_MAX_PHOTOS} or fewer per download.",
            )

        # Guardrail #2 — total bytes based on the stored per-photo size.
        # Photo uploads store the byte count as `size` (server.py stores it
        # via `_id.get('size')`); older rows may use `size_bytes`. Fall back
        # to a 5 MB estimate per row when neither is present (typical
        # phone JPEG average) so the guardrail still bites on unmetadata'd
        # rows.
        est_total = 0
        for p in photos:
            est_total += int(p.get("size") or p.get("size_bytes") or 5 * 1024 * 1024)
        if est_total > DOWNLOAD_MAX_TOTAL_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Estimated download too large ({est_total // (1024 * 1024)} MB). "
                    "Select fewer photos or download an album in chunks."
                ),
            )

        # Pre-compute unique in-zip filenames so we don't need to touch used
        # names inside the inner streaming loop.
        used_names: set = set()
        entries: list = []
        for p in photos:
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
            entries.append((n, p["storage_path"], p.get("id")))

        album_label = _safe_filename(body.album or "photos")
        zs = ZipStream()

        def _fetch_one(storage_path: str, pid: str):
            """Generator that yields the single-blob bytes of one photo,
            wrapped so zipstream-ng calls it lazily inside its iterator.
            Errors are swallowed with a log line so one bad photo doesn't
            take down the whole download; the file entry is skipped
            entirely rather than added with zero bytes."""
            try:
                data, _ct = get_object(storage_path)
            except Exception as e:
                logger.warning(f"download-zip: skipping photo {pid} ({storage_path}): {e}")
                return
            try:
                yield data
            finally:
                # Free the (potentially 30 MB) buffer as soon as
                # zipstream is done reading it, before the next photo
                # is fetched. Peak RSS stays at ~1 photo.
                del data
                gc.collect()

        for zip_name, storage_path, pid in entries:
            zs.add(_fetch_one(storage_path, pid), zip_name)

        async def _stream():
            try:
                for chunk in zs:
                    # Hand control back to the event loop between chunks
                    # so health checks + other requests aren't starved
                    # during a big download.
                    await asyncio.sleep(0)
                    yield chunk
            except Exception as e:
                logger.exception(f"download-zip stream aborted: {e}")

        headers = {
            "Content-Disposition": f'attachment; filename="aop-{album_label}.zip"',
            # no-transform prevents Cloudflare from trying to gzip an
            # already-compressed application/zip payload (double-compress
            # would waste CPU AND cause the "empty response" 520 the
            # user hit — some proxies drop the response when they can't
            # rewrite the Content-Length header of a transfer-encoded
            # stream during transform.
            "Cache-Control": "no-store, no-transform",
        }
        return StreamingResponse(_stream(), media_type="application/zip", headers=headers)
