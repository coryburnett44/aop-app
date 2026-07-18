"""AOP Form Links (picture cards) + Schedule-a-Meeting cards.

Endpoints:
  - /form-links (GET, POST), /form-links/{id} (PUT, DELETE), /form-links/upload (POST)
  - /meeting-cards (GET, POST), /meeting-cards/{id} (PUT, DELETE), /meeting-cards/upload-image (POST)

Extracted from server.py (iter 128) as part of the ongoing server.py
modularization.
"""
import asyncio
import uuid
from typing import Optional

from fastapi import Depends, File, HTTPException, UploadFile
from pydantic import BaseModel


class FormLinkIn(BaseModel):
    title: str
    description: str = ""
    url: str
    image_url: str = ""
    order: int = 0


class FormLinkUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    order: Optional[int] = None


class MeetingCardIn(BaseModel):
    name: str
    title: str = ""
    description: str = ""
    image_url: str = ""
    button_label: str = "Book Meeting"
    button_url: str
    order: int = 0


class MeetingCardUpdateIn(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    button_label: Optional[str] = None
    button_url: Optional[str] = None
    order: Optional[int] = None


def _form_link_out(d: dict) -> dict:
    return {
        "id": d["id"],
        "title": d.get("title", ""),
        "description": d.get("description", ""),
        "url": d.get("url", ""),
        "image_url": d.get("image_url", ""),
        "order": d.get("order", 0),
        "created_at": d.get("created_at"),
        "created_by_name": d.get("created_by_name", ""),
    }


def _meeting_out(d: dict) -> dict:
    return {
        "id": d["id"],
        "name": d.get("name", ""),
        "title": d.get("title", ""),
        "description": d.get("description", ""),
        "image_url": d.get("image_url", ""),
        "button_label": d.get("button_label", "Book Meeting"),
        "button_url": d.get("button_url", ""),
        "order": d.get("order", 0),
        "created_at": d.get("created_at"),
    }


def register(api, *, db, admin_tab_dep, put_object, iso, now_utc, image_ext, mime_by_ext):

    # ---------- Form Links ----------
    @api.get("/form-links")
    async def list_form_links():
        rows = await db.form_links.find({}, {"_id": 0}).sort([("order", 1), ("created_at", 1)]).to_list(200)
        return [_form_link_out(r) for r in rows]

    @api.post("/form-links")
    async def create_form_link(body: FormLinkIn, admin: dict = Depends(admin_tab_dep("members"))):
        if not body.title.strip() or not body.url.strip():
            raise HTTPException(status_code=400, detail="Title and URL are required.")
        doc = {
            "id": str(uuid.uuid4()),
            "title": body.title.strip(),
            "description": body.description.strip(),
            "url": body.url.strip(),
            "image_url": body.image_url.strip(),
            "order": body.order,
            "created_by": admin["id"],
            "created_by_name": admin.get("name", ""),
            "created_at": iso(now_utc()),
            "updated_at": iso(now_utc()),
        }
        await db.form_links.insert_one(doc)
        return _form_link_out(doc)

    @api.put("/form-links/{link_id}")
    async def update_form_link(link_id: str, body: FormLinkUpdateIn, _: dict = Depends(admin_tab_dep("members"))):
        existing = await db.form_links.find_one({"id": link_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Form link not found")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "title" in updates and not str(updates["title"]).strip():
            raise HTTPException(status_code=400, detail="Title cannot be blank.")
        if "url" in updates and not str(updates["url"]).strip():
            raise HTTPException(status_code=400, detail="URL cannot be blank.")
        updates["updated_at"] = iso(now_utc())
        await db.form_links.update_one({"id": link_id}, {"$set": updates})
        out = await db.form_links.find_one({"id": link_id}, {"_id": 0})
        return _form_link_out(out)

    @api.delete("/form-links/{link_id}")
    async def delete_form_link(link_id: str, _: dict = Depends(admin_tab_dep("members"))):
        existing = await db.form_links.find_one({"id": link_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Form link not found")
        await db.form_links.delete_one({"id": link_id})
        return {"ok": True}

    @api.post("/form-links/upload")
    async def upload_form_link_image(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("members"))):
        """Admin uploads a picture for a form-link card. Returns {url}."""
        chunks: list = []
        total = 0
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 10 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="Image must be under 10 MB")
            chunks.append(chunk)
        data = b"".join(chunks)
        fname = (file.filename or "link.jpg").replace("/", "_")
        ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
        if ext not in image_ext:
            raise HTTPException(status_code=400, detail="Only images allowed (jpg, png, gif, webp)")
        content_type = file.content_type or mime_by_ext.get(ext, "image/jpeg")
        file_id = str(uuid.uuid4())
        storage_path = f"form-links/{file_id}/{fname}"
        await asyncio.to_thread(put_object, storage_path, data, content_type)
        rec = {
            "id": file_id,
            "filename": fname,
            "storage_path": storage_path,
            "content_type": content_type,
            "size": total,
            "kind": "image",
            "uploaded_by": user["id"],
            "is_deleted": False,
            "created_at": iso(now_utc()),
        }
        await db.chat_files.insert_one(rec)
        return {"url": f"/api/files/{storage_path}", "size": total}

    # ---------- Meeting Cards ----------
    @api.get("/meeting-cards")
    async def list_meeting_cards():
        rows = await db.meeting_cards.find({}, {"_id": 0}).sort([("order", 1), ("created_at", 1)]).to_list(200)
        return [_meeting_out(r) for r in rows]

    @api.post("/meeting-cards")
    async def create_meeting_card(body: MeetingCardIn, admin: dict = Depends(admin_tab_dep("members"))):
        if not body.name.strip() or not body.button_url.strip():
            raise HTTPException(status_code=400, detail="Name and Book Meeting URL are required.")
        doc = {
            "id": str(uuid.uuid4()),
            "name": body.name.strip(),
            "title": body.title.strip(),
            "description": body.description.strip(),
            "image_url": body.image_url.strip(),
            "button_label": (body.button_label or "Book Meeting").strip(),
            "button_url": body.button_url.strip(),
            "order": body.order,
            "created_by_name": admin.get("name", ""),
            "created_at": iso(now_utc()),
            "updated_at": iso(now_utc()),
        }
        await db.meeting_cards.insert_one(doc)
        return _meeting_out(doc)

    @api.put("/meeting-cards/{card_id}")
    async def update_meeting_card(card_id: str, body: MeetingCardUpdateIn, _: dict = Depends(admin_tab_dep("members"))):
        existing = await db.meeting_cards.find_one({"id": card_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Meeting card not found")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "name" in updates and not str(updates["name"]).strip():
            raise HTTPException(status_code=400, detail="Name cannot be blank.")
        if "button_url" in updates and not str(updates["button_url"]).strip():
            raise HTTPException(status_code=400, detail="Book Meeting URL cannot be blank.")
        updates["updated_at"] = iso(now_utc())
        await db.meeting_cards.update_one({"id": card_id}, {"$set": updates})
        out = await db.meeting_cards.find_one({"id": card_id}, {"_id": 0})
        return _meeting_out(out)

    @api.delete("/meeting-cards/{card_id}")
    async def delete_meeting_card(card_id: str, _: dict = Depends(admin_tab_dep("members"))):
        existing = await db.meeting_cards.find_one({"id": card_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Meeting card not found")
        await db.meeting_cards.delete_one({"id": card_id})
        return {"ok": True}

    @api.post("/meeting-cards/upload-image")
    async def meeting_card_image_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("members"))):
        """Admin uploads a picture for a meeting card. Returns {url}."""
        chunks: list = []
        total = 0
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 10 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="Image must be under 10 MB")
            chunks.append(chunk)
        data = b"".join(chunks)
        fname = (file.filename or "meeting.jpg").replace("/", "_")
        ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
        if ext not in image_ext:
            raise HTTPException(status_code=400, detail="Only images allowed (jpg, png, gif, webp)")
        content_type = file.content_type or mime_by_ext.get(ext, "image/jpeg")
        file_id = str(uuid.uuid4())
        storage_path = f"meeting-cards/{file_id}/{fname}"
        await asyncio.to_thread(put_object, storage_path, data, content_type)
        rec = {
            "id": file_id,
            "filename": fname,
            "storage_path": storage_path,
            "content_type": content_type,
            "size": total,
            "kind": "image",
            "uploaded_by": user["id"],
            "is_deleted": False,
            "created_at": iso(now_utc()),
        }
        await db.chat_files.insert_one(rec)
        return {"url": f"/api/files/{storage_path}", "size": total}
