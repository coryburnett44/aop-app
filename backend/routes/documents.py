"""Document & document-folder routes.

Extracted from server.py to continue the modularization roll-out. The file
proxy `/api/files/{storage_path}` stays in server.py because it spans photos,
documents AND chat files.

Endpoints:
  GET    /api/documents                  — list (filter by category / folder)
  GET    /api/document-folders           — list folders + live doc counts
  POST   /api/document-folders           — admin create (max 2 levels)
  PUT    /api/document-folders/{id}      — admin rename
  DELETE /api/document-folders/{id}      — admin delete (orphans contents)
  POST   /api/documents                  — admin single-file upload
  POST   /api/documents/bulk             — admin multi-file upload (≤50)
  DELETE /api/documents/{id}             — uploader or admin soft-delete
"""
import uuid
from typing import List, Optional

from fastapi import Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field


def register(
    api,
    *,
    db,
    get_current_user,
    admin_tab_dep,
    put_object,
    iso,
    now_utc,
    logger,
    doc_ext,
    image_ext,
    mime_by_ext,
    app_name,
):
    def document_out(d: dict) -> dict:
        return {
            "id": d["id"],
            "title": d.get("title", d.get("original_filename", "")),
            "category": d.get("category", "general"),
            "description": d.get("description", ""),
            "storage_path": d["storage_path"],
            "url": f"/api/files/{d['storage_path']}",
            "original_filename": d.get("original_filename", ""),
            "content_type": d.get("content_type", ""),
            "size": d.get("size", 0),
            "uploaded_by": d.get("uploaded_by"),
            "uploaded_by_name": d.get("uploaded_by_name", ""),
            "folder_id": d.get("folder_id"),
            "created_at": d.get("created_at"),
        }

    @api.get("/documents")
    async def list_documents(category: Optional[str] = None, folder_id: Optional[str] = None):
        query: dict = {"is_deleted": {"$ne": True}}
        if category:
            query["category"] = category
        if folder_id == "root":
            query["folder_id"] = {"$in": [None, ""]}
        elif folder_id:
            query["folder_id"] = folder_id
        cursor = db.documents.find(query, {"_id": 0}).sort("created_at", -1).limit(500)
        items = await cursor.to_list(500)
        return [document_out(d) for d in items]

    # ---------- Document Folders (2 levels deep) ----------
    class DocumentFolderIn(BaseModel):
        name: str = Field(min_length=1, max_length=120)
        parent_id: Optional[str] = None

    @api.get("/document-folders")
    async def list_document_folders():
        """Return all folders. Frontend builds the 2-level tree from parent_id."""
        folders = await db.document_folders.find({"is_deleted": {"$ne": True}}, {"_id": 0}).sort("name", 1).to_list(500)
        counts: dict = {}
        pipeline = [
            {"$match": {"is_deleted": {"$ne": True}, "folder_id": {"$ne": None}}},
            {"$group": {"_id": "$folder_id", "count": {"$sum": 1}}},
        ]
        async for d in db.documents.aggregate(pipeline):
            counts[d["_id"]] = d["count"]
        return [
            {
                "id": f["id"],
                "name": f["name"],
                "parent_id": f.get("parent_id"),
                "created_by_name": f.get("created_by_name", ""),
                "doc_count": counts.get(f["id"], 0),
                "created_at": f.get("created_at"),
            }
            for f in folders
        ]

    @api.post("/document-folders")
    async def create_document_folder(body: DocumentFolderIn, admin: dict = Depends(admin_tab_dep("documents"))):
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Folder name is required.")
        parent_id = body.parent_id or None
        if parent_id:
            parent = await db.document_folders.find_one({"id": parent_id, "is_deleted": {"$ne": True}})
            if not parent:
                raise HTTPException(status_code=404, detail="Parent folder not found")
            if parent.get("parent_id"):
                raise HTTPException(status_code=400, detail="Subfolders cannot have their own subfolders (max 2 levels).")
        doc = {
            "id": str(uuid.uuid4()),
            "name": name,
            "parent_id": parent_id,
            "created_by": admin["id"],
            "created_by_name": admin.get("name", ""),
            "is_deleted": False,
            "created_at": iso(now_utc()),
        }
        await db.document_folders.insert_one(doc)
        return {"id": doc["id"], "name": name, "parent_id": parent_id, "doc_count": 0, "created_by_name": doc["created_by_name"], "created_at": doc["created_at"]}

    @api.put("/document-folders/{folder_id}")
    async def rename_document_folder(folder_id: str, body: DocumentFolderIn, admin: dict = Depends(admin_tab_dep("documents"))):
        f = await db.document_folders.find_one({"id": folder_id, "is_deleted": {"$ne": True}})
        if not f:
            raise HTTPException(status_code=404, detail="Folder not found")
        await db.document_folders.update_one({"id": folder_id}, {"$set": {"name": body.name.strip()}})
        return {"ok": True}

    @api.delete("/document-folders/{folder_id}")
    async def delete_document_folder(folder_id: str, admin: dict = Depends(admin_tab_dep("documents"))):
        """Delete a folder. Any subfolders become root-level, any documents become uncategorized."""
        f = await db.document_folders.find_one({"id": folder_id, "is_deleted": {"$ne": True}})
        if not f:
            raise HTTPException(status_code=404, detail="Folder not found")
        await db.document_folders.update_one({"id": folder_id}, {"$set": {"is_deleted": True}})
        await db.document_folders.update_many({"parent_id": folder_id}, {"$set": {"parent_id": None}})
        await db.documents.update_many({"folder_id": folder_id}, {"$set": {"folder_id": None}})
        return {"ok": True}

    @api.post("/documents/bulk")
    async def upload_documents_bulk(
        files: List[UploadFile] = File(...),
        category: str = Form("general"),
        folder_id: str = Form(""),
        user: dict = Depends(admin_tab_dep("documents")),
    ):
        """Multi-file upload (admin-only — restricted to documents-tab admins).
        Returns the doc rows that succeeded + the names that failed."""
        if len(files) == 0:
            raise HTTPException(status_code=400, detail="Pick at least one file.")
        if len(files) > 50:
            raise HTTPException(status_code=400, detail="Max 50 files per batch.")
        folder = None
        if folder_id:
            folder = await db.document_folders.find_one({"id": folder_id, "is_deleted": {"$ne": True}})
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")
        uploaded: list = []
        failed: list = []
        for f in files:
            try:
                ext = (f.filename.rsplit(".", 1)[-1] if f.filename and "." in f.filename else "bin").lower()
                if ext not in doc_ext and ext not in image_ext:
                    failed.append({"filename": f.filename, "reason": f"Unsupported type .{ext}"}); continue
                content_type = f.content_type or mime_by_ext.get(ext, "application/octet-stream")
                data = await f.read()
                if len(data) > 25 * 1024 * 1024:
                    failed.append({"filename": f.filename, "reason": "File over 25MB"}); continue
                path = f"{app_name}/documents/{user['id']}/{uuid.uuid4()}.{ext}"
                result = put_object(path, data, content_type)
                doc = {
                    "id": str(uuid.uuid4()),
                    "title": f.filename,
                    "category": category or "general",
                    "description": "",
                    "folder_id": folder_id or None,
                    "storage_path": result["path"],
                    "original_filename": f.filename,
                    "content_type": content_type,
                    "size": result.get("size", len(data)),
                    "uploaded_by": user["id"],
                    "uploaded_by_name": user.get("name", ""),
                    "is_deleted": False,
                    "created_at": iso(now_utc()),
                }
                await db.documents.insert_one(doc)
                uploaded.append(document_out(doc))
            except Exception as ex:
                logger.warning(f"Doc upload failed for {f.filename}: {ex}")
                failed.append({"filename": f.filename, "reason": str(ex)})
        return {"uploaded": uploaded, "failed": failed}

    @api.post("/documents")
    async def upload_document(
        file: UploadFile = File(...),
        title: str = Form(""),
        category: str = Form("general"),
        description: str = Form(""),
        folder_id: str = Form(""),
        user: dict = Depends(admin_tab_dep("documents")),
    ):
        """Single-file upload (admin-only — restricted to documents-tab admins).
        Members can VIEW the Docs & Forms page but cannot upload (Iter 36 policy)."""
        ext = (file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "bin").lower()
        if ext not in doc_ext and ext not in image_ext:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
        content_type = file.content_type or mime_by_ext.get(ext, "application/octet-stream")
        path = f"{app_name}/documents/{user['id']}/{uuid.uuid4()}.{ext}"
        data = await file.read()
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 25MB)")
        result = put_object(path, data, content_type)
        doc = {
            "id": str(uuid.uuid4()),
            "title": title or file.filename,
            "category": category or "general",
            "description": description,
            "folder_id": folder_id or None,
            "storage_path": result["path"],
            "original_filename": file.filename,
            "content_type": content_type,
            "size": result.get("size", len(data)),
            "uploaded_by": user["id"],
            "uploaded_by_name": user.get("name", ""),
            "is_deleted": False,
            "created_at": iso(now_utc()),
        }
        await db.documents.insert_one(doc)
        return document_out(doc)

    @api.delete("/documents/{doc_id}")
    async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
        d = await db.documents.find_one({"id": doc_id})
        if not d:
            raise HTTPException(status_code=404, detail="Not found")
        if d.get("uploaded_by") != user["id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not allowed")
        await db.documents.update_one({"id": doc_id}, {"$set": {"is_deleted": True}})
        return {"ok": True}

    # Expose document_out so other server.py code paths (e.g. legacy callers)
    # can still build response shapes consistently if needed.
    register.document_out = document_out
