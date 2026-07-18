"""Generic admin image upload endpoints.

Provides a single `_upload_image` helper (exposed to the caller via
`register.upload_image` so other extracted modules can reuse it) and thin
wrappers for chapter logos / cause / news / leadership / founders / event
cover / chat-group photos.

Extracted from server.py (iter 128) as part of the ongoing server.py
modularization.
"""
import asyncio
import uuid
from fastapi import Depends, File, HTTPException, UploadFile


def register(api, *, db, get_current_user, admin_tab_dep, put_object, iso, now_utc, image_ext, mime_by_ext):

    async def _upload_image(file: UploadFile, prefix: str, user: dict, max_mb: int = 10) -> dict:
        chunks: list = []
        total = 0
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_mb * 1024 * 1024:
                raise HTTPException(status_code=413, detail=f"Image must be under {max_mb} MB")
            chunks.append(chunk)
        data = b"".join(chunks)
        fname = (file.filename or "image.jpg").replace("/", "_")
        ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
        if ext not in image_ext:
            raise HTTPException(status_code=400, detail="Only images allowed (jpg, png, gif, webp)")
        content_type = file.content_type or mime_by_ext.get(ext, "image/jpeg")
        file_id = str(uuid.uuid4())
        storage_path = f"{prefix}/{file_id}/{fname}"
        await asyncio.to_thread(put_object, storage_path, data, content_type)
        await db.chat_files.insert_one({
            "id": file_id, "filename": fname, "storage_path": storage_path,
            "content_type": content_type, "size": total, "kind": "image",
            "uploaded_by": user["id"], "is_deleted": False, "created_at": iso(now_utc()),
        })
        return {"url": f"/api/files/{storage_path}", "size": total}

    @api.post("/chapters/upload-logo")
    async def chapter_logo_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("chapters"))):
        return await _upload_image(file, "chapter-logos", user)

    @api.post("/causes/upload-image")
    async def cause_image_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("causes"))):
        return await _upload_image(file, "causes", user)

    @api.post("/news/upload-image")
    async def news_image_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("news"))):
        return await _upload_image(file, "news", user)

    @api.post("/leadership/upload-image")
    async def leadership_image_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("pages"))):
        return await _upload_image(file, "leadership", user)

    @api.post("/founders/upload-image")
    async def founders_image_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("pages"))):
        return await _upload_image(file, "founders", user)

    @api.post("/events/upload-cover")
    async def events_cover_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("events"))):
        return await _upload_image(file, "events", user)

    @api.post("/chat/group-photo-upload")
    async def chat_group_photo_upload(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
        """Any logged-in user can upload — they'll only be able to attach the
        resulting URL to a conversation they belong to (enforced by /conversations PUT)."""
        return await _upload_image(file, "chat-groups", user, max_mb=8)

    # Expose the helper so sibling route modules (omega, cms_cards) can reuse it.
    register.upload_image = _upload_image
