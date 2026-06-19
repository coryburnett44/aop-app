"""AOP Gear catalog + page settings + image upload.

Extracted from server.py (Iter 53). Exposes:
  GET    /gear
  GET    /gear/{item_id}
  POST   /gear                  (admin)
  PUT    /gear/{item_id}        (admin)
  DELETE /gear/{item_id}        (admin)
  GET    /gear-page             (public; admin-edited hero/intro)
  PUT    /gear-page             (admin)
  POST   /gear/upload           (admin; image upload to object storage)
"""
from typing import List, Optional
import asyncio
import uuid

from fastapi import Depends, File, HTTPException, UploadFile
from pydantic import BaseModel


class GearColorImage(BaseModel):
    color: str
    image_url: str = ""


class GearItemIn(BaseModel):
    name: str
    name_html: str = ""  # rich-HTML version of the title (admin Quill output); when set, frontend renders this instead of `name`.
    description: str = ""
    price: float = 0.0
    sizes: List[str] = []
    colors: List[str] = []
    color_images: List[GearColorImage] = []
    cover_image: str = ""
    images: List[str] = []
    category: str = "apparel"
    in_stock: bool = True
    sku: str = ""
    is_external_link: bool = False
    external_url: str = ""


class GearItemUpdateIn(BaseModel):
    name: Optional[str] = None
    name_html: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    sizes: Optional[List[str]] = None
    colors: Optional[List[str]] = None
    color_images: Optional[List[GearColorImage]] = None
    cover_image: Optional[str] = None
    images: Optional[List[str]] = None
    category: Optional[str] = None
    in_stock: Optional[bool] = None
    sku: Optional[str] = None
    is_external_link: Optional[bool] = None
    external_url: Optional[str] = None


class GearPageIn(BaseModel):
    hero_image: str = ""
    title: str = ""
    subtitle: str = ""
    intro: str = ""


def gear_out(g: dict) -> dict:
    return {
        "id": g["id"],
        "name": g["name"],
        "name_html": g.get("name_html", ""),
        "description": g.get("description", ""),
        "price": g.get("price", 0.0),
        "sizes": g.get("sizes", []),
        "colors": g.get("colors", []),
        "color_images": g.get("color_images", []),
        "cover_image": g.get("cover_image", ""),
        "images": g.get("images", []),
        "category": g.get("category", "apparel"),
        "in_stock": g.get("in_stock", True),
        "sku": g.get("sku", ""),
        "is_external_link": bool(g.get("is_external_link", False)),
        "external_url": g.get("external_url", ""),
        "created_at": g.get("created_at"),
    }


def register(api, *, db, admin_tab_dep, iso, now_utc, put_object, image_ext, mime_by_ext):
    """Register gear endpoints on the FastAPI `api` router.

    Args:
        api: APIRouter instance (with `/api` prefix already applied).
        db: motor database client.
        admin_tab_dep: dependency factory `admin_tab_dep("gear")`.
        iso, now_utc: time helpers.
        put_object: object-storage upload helper.
        image_ext: set/list of allowed image extensions.
        mime_by_ext: dict mapping extension → MIME type.
    """

    @api.get("/gear")
    async def list_gear(category: Optional[str] = None):
        q = {}
        if category:
            q["category"] = category
        items = await db.gear.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
        return [gear_out(g) for g in items]

    @api.get("/gear/{item_id}")
    async def get_gear(item_id: str):
        g = await db.gear.find_one({"id": item_id}, {"_id": 0})
        if not g:
            raise HTTPException(status_code=404, detail="Gear item not found")
        return gear_out(g)

    @api.post("/gear")
    async def create_gear(body: GearItemIn, _: dict = Depends(admin_tab_dep("gear"))):
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = iso(now_utc())
        await db.gear.insert_one(doc)
        return gear_out(doc)

    @api.put("/gear/{item_id}")
    async def update_gear(item_id: str, body: GearItemUpdateIn, _: dict = Depends(admin_tab_dep("gear"))):
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if updates:
            await db.gear.update_one({"id": item_id}, {"$set": updates})
        g = await db.gear.find_one({"id": item_id}, {"_id": 0})
        if not g:
            raise HTTPException(status_code=404, detail="Gear item not found")
        return gear_out(g)

    @api.delete("/gear/{item_id}")
    async def delete_gear(item_id: str, _: dict = Depends(admin_tab_dep("gear"))):
        await db.gear.delete_one({"id": item_id})
        return {"ok": True}

    @api.get("/gear-page")
    async def get_gear_page():
        doc = await db.app_settings.find_one({"key": "gear_page"}, {"_id": 0})
        if not doc:
            return {"hero_image": "", "title": "", "subtitle": "", "intro": ""}
        return {
            "hero_image": doc.get("hero_image", ""),
            "title": doc.get("title", ""),
            "subtitle": doc.get("subtitle", ""),
            "intro": doc.get("intro", ""),
            "updated_at": doc.get("updated_at"),
        }

    @api.put("/gear-page")
    async def set_gear_page(body: GearPageIn, admin: dict = Depends(admin_tab_dep("gear"))):
        await db.app_settings.update_one(
            {"key": "gear_page"},
            {"$set": {
                "key": "gear_page",
                "hero_image": body.hero_image,
                "title": body.title,
                "subtitle": body.subtitle,
                "intro": body.intro,
                "updated_at": iso(now_utc()),
                "updated_by": admin.get("name", ""),
            }},
            upsert=True,
        )
        return {"ok": True, **body.model_dump()}

    @api.post("/gear/upload")
    async def gear_image_upload(file: UploadFile = File(...), user: dict = Depends(admin_tab_dep("gear"))):
        """Admin uploads an image for a gear item (cover, gallery, or per-color photo)."""
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
        fname = (file.filename or "gear.jpg").replace("/", "_")
        ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
        if ext not in image_ext:
            raise HTTPException(status_code=400, detail="Only images allowed (jpg, png, gif, webp)")
        content_type = file.content_type or mime_by_ext.get(ext, "image/jpeg")
        file_id = str(uuid.uuid4())
        storage_path = f"gear/{file_id}/{fname}"
        await asyncio.to_thread(put_object, storage_path, data, content_type)
        await db.chat_files.insert_one({
            "id": file_id,
            "filename": fname,
            "storage_path": storage_path,
            "content_type": content_type,
            "size": total,
            "kind": "image",
            "uploaded_by": user["id"],
            "is_deleted": False,
            "created_at": iso(now_utc()),
        })
        return {"url": f"/api/files/{storage_path}", "size": total}
