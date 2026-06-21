"""Chat (1:1 + group conversations + messages + file uploads + WebSocket).

Extracted from server.py (Iter 55). Exposes:

  - GET    /conversations
  - POST   /conversations
  - GET    /conversations/{cid}
  - PUT    /conversations/{cid}
  - POST   /conversations/{cid}/leave
  - DELETE /conversations/{cid}
  - POST   /conversations/{cid}/read
  - GET    /conversations/{cid}/messages
  - POST   /conversations/{cid}/messages
  - DELETE /messages/{mid}
  - POST   /chat/upload
  - WS     /api/ws/chat

Real-time fan-out is delivered through the module-owned `ChatHub` instance
(`chat_hub`). The hub also tracks per-user WebSocket connection sets so
external callers (e.g. the chat email digest cron in server.py) can read
`chat_hub.connections` to decide whether a recipient is online.
"""
import asyncio
import uuid
from datetime import datetime
from typing import List, Literal, Optional

import jwt as _pyjwt
from fastapi import Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel


# ---------- Hub (singleton; created at register-time) ----------
class ChatHub:
    def __init__(self):
        self.connections: dict[str, set[WebSocket]] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.connections.setdefault(user_id, set()).add(ws)

    def disconnect(self, user_id: str, ws: WebSocket):
        if user_id in self.connections:
            self.connections[user_id].discard(ws)
            if not self.connections[user_id]:
                self.connections.pop(user_id, None)

    async def push(self, user_ids: List[str], event: dict):
        dead = []
        for uid in user_ids:
            for ws in list(self.connections.get(uid, set())):
                try:
                    await ws.send_json(event)
                except Exception:
                    dead.append((uid, ws))
        for uid, ws in dead:
            self.disconnect(uid, ws)


chat_hub = ChatHub()


TTL_CHOICES = {"off": 0, "1h": 3600, "24h": 86400, "7d": 604800}


def _ttl_choice_to_seconds(v: Optional[str]) -> int:
    if not v:
        return 0
    return TTL_CHOICES.get(v, 0)


# ---------- Pydantic models ----------
class ConversationCreateIn(BaseModel):
    member_ids: List[str]  # other members (the current user is auto-included)
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    type: Optional[Literal["dm", "group"]] = None
    ttl: Optional[Literal["off", "1h", "24h", "7d"]] = "off"


class ConversationUpdateIn(BaseModel):
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    add_member_ids: Optional[List[str]] = None
    remove_member_ids: Optional[List[str]] = None
    ttl: Optional[Literal["off", "1h", "24h", "7d"]] = None


class MessageIn(BaseModel):
    body: str = ""
    attachments: List[dict] = []
    reply_to: Optional[str] = None
    ttl: Optional[Literal["off", "1h", "24h", "7d"]] = None


CHAT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


def register(
    api,
    app,
    *,
    db,
    iso,
    now_utc,
    get_current_user,
    jwt_secret,
    JWT_ALGORITHM,
    queue_chat_notifications,
    put_object,
    image_ext,
    mime_by_ext,
    logger,
):
    """Wire chat REST + WebSocket endpoints onto the supplied `api` router /
    `app` FastAPI instance. WebSocket lives on `app` (not the prefixed router)
    so the full path `/api/ws/chat` is preserved verbatim.
    """

    def _now_iso():
        return iso(now_utc())

    async def _user_brief(user_id: str) -> dict:
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not u:
            return {"id": user_id, "name": "Unknown", "avatar_url": ""}
        return {"id": u["id"], "name": u.get("name", ""), "avatar_url": u.get("avatar_url", ""), "email": u.get("email", "")}

    async def conversation_out(c: dict, viewer_id: str) -> dict:
        member_briefs = []
        for mid in c.get("member_ids", []):
            member_briefs.append(await _user_brief(mid))
        title = c.get("name")
        avatar = c.get("avatar_url", "")
        if not title:
            if c.get("type") == "dm":
                other = next((m for m in member_briefs if m["id"] != viewer_id), member_briefs[0] if member_briefs else None)
                title = other["name"] if other else "Direct message"
                avatar = avatar or (other.get("avatar_url", "") if other else "")
            else:
                names = [m["name"].split(" ")[0] for m in member_briefs if m["id"] != viewer_id]
                title = ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
        return {
            "id": c["id"],
            "type": c.get("type", "group"),
            "name": title,
            "raw_name": c.get("name"),
            "avatar_url": avatar,
            "members": member_briefs,
            "member_ids": c.get("member_ids", []),
            "created_by": c.get("created_by"),
            "created_at": c.get("created_at"),
            "last_message_at": c.get("last_message_at"),
            "last_message_preview": c.get("last_message_preview", ""),
            "last_read_at": c.get("read_state", {}).get(viewer_id),
            "ttl": c.get("ttl", "off"),
        }

    def _is_message_expired(m: dict, viewer_id: str) -> bool:
        """A disappearing message expires {ttl_seconds} after the first time
        any recipient (other than the sender) read it."""
        ttl = int(m.get("ttl_seconds") or 0)
        if ttl <= 0:
            return False
        first_seen = m.get("first_read_at")
        if not first_seen:
            return False
        try:
            seen_at = datetime.fromisoformat(first_seen)
        except Exception:
            return False
        return (now_utc() - seen_at).total_seconds() >= ttl

    def message_out(m: dict, viewer_id: str = "") -> dict:
        return {
            "id": m["id"],
            "conversation_id": m["conversation_id"],
            "sender_id": m["sender_id"],
            "sender_name": m.get("sender_name", ""),
            "sender_avatar": m.get("sender_avatar", ""),
            "body": m.get("body", ""),
            "attachments": m.get("attachments", []),
            "reply_to": m.get("reply_to"),
            "created_at": m.get("created_at"),
            "edited_at": m.get("edited_at"),
            "deleted_at": m.get("deleted_at"),
            "ttl_seconds": int(m.get("ttl_seconds") or 0),
            "first_read_at": m.get("first_read_at"),
            "expires_at": m.get("expires_at"),
        }

    # ---------- Conversations ----------
    @api.get("/conversations")
    async def list_conversations(user: dict = Depends(get_current_user)):
        cursor = db.conversations.find(
            {"member_ids": user["id"]},
            {"_id": 0},
        ).sort([("last_message_at", -1), ("created_at", -1)])
        items = await cursor.to_list(500)
        return [await conversation_out(c, user["id"]) for c in items]

    @api.post("/conversations")
    async def create_conversation(body: ConversationCreateIn, user: dict = Depends(get_current_user)):
        members = list({user["id"], *body.member_ids})
        if len(members) < 2:
            raise HTTPException(status_code=400, detail="Pick at least one other member")
        valid = await db.users.count_documents({"id": {"$in": members}})
        if valid != len(members):
            raise HTTPException(status_code=400, detail="Some members not found")
        ctype = body.type or ("dm" if len(members) == 2 else "group")
        if ctype == "dm" and len(members) == 2:
            existing = await db.conversations.find_one({"type": "dm", "member_ids": {"$all": members, "$size": 2}})
            if existing:
                return await conversation_out(existing, user["id"])
        doc = {
            "id": str(uuid.uuid4()),
            "type": ctype,
            "name": body.name,
            "avatar_url": body.avatar_url or "",
            "member_ids": members,
            "created_by": user["id"],
            "ttl": body.ttl or "off",
            "created_at": _now_iso(),
            "last_message_at": _now_iso(),
            "last_message_preview": "",
            "read_state": {user["id"]: _now_iso()},
        }
        await db.conversations.insert_one(doc)
        await chat_hub.push(members, {"type": "conversation:created", "conversation": await conversation_out(doc, user["id"])})
        return await conversation_out(doc, user["id"])

    @api.get("/conversations/{cid}")
    async def get_conversation(cid: str, user: dict = Depends(get_current_user)):
        c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return await conversation_out(c, user["id"])

    @api.put("/conversations/{cid}")
    async def update_conversation(cid: str, body: ConversationUpdateIn, user: dict = Depends(get_current_user)):
        c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
        if not c:
            raise HTTPException(status_code=404, detail="Conversation not found")
        sets: dict = {}
        if body.name is not None:
            sets["name"] = body.name
        if body.avatar_url is not None:
            sets["avatar_url"] = body.avatar_url
        if body.ttl is not None:
            sets["ttl"] = body.ttl
        # Member changes only allowed in group chats.
        if c.get("type") == "group":
            members = set(c.get("member_ids", []))
            if body.add_member_ids:
                members.update(body.add_member_ids)
            if body.remove_member_ids:
                for rid in body.remove_member_ids:
                    members.discard(rid)
            members.add(user["id"])  # editor can't accidentally remove themselves
            if members != set(c.get("member_ids", [])):
                sets["member_ids"] = list(members)
        if sets:
            await db.conversations.update_one({"id": cid}, {"$set": sets})
        c2 = await db.conversations.find_one({"id": cid}, {"_id": 0})
        payload = await conversation_out(c2, user["id"])
        await chat_hub.push(c2.get("member_ids", []), {"type": "conversation:updated", "conversation": payload})
        return payload

    @api.post("/conversations/{cid}/leave")
    async def leave_conversation(cid: str, user: dict = Depends(get_current_user)):
        c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
        if not c:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if c.get("type") == "dm":
            raise HTTPException(status_code=400, detail="DMs can't be left — use delete")
        new_members = [m for m in c.get("member_ids", []) if m != user["id"]]
        if not new_members:
            await db.conversations.delete_one({"id": cid})
            await db.messages.delete_many({"conversation_id": cid})
            return {"ok": True, "deleted": True}
        await db.conversations.update_one({"id": cid}, {"$set": {"member_ids": new_members}})
        await chat_hub.push(c.get("member_ids", []), {"type": "conversation:member_left", "conversation_id": cid, "user_id": user["id"]})
        return {"ok": True}

    @api.delete("/conversations/{cid}")
    async def delete_conversation(cid: str, user: dict = Depends(get_current_user)):
        c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
        if not c:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if c.get("created_by") != user["id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only the creator or an admin can delete this conversation")
        await db.conversations.delete_one({"id": cid})
        await db.messages.delete_many({"conversation_id": cid})
        await chat_hub.push(c.get("member_ids", []), {"type": "conversation:deleted", "conversation_id": cid})
        return {"ok": True}

    @api.post("/conversations/{cid}/read")
    async def mark_read(cid: str, user: dict = Depends(get_current_user)):
        c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
        if not c:
            raise HTTPException(status_code=404, detail="Conversation not found")
        now_iso = _now_iso()
        await db.conversations.update_one({"id": cid}, {"$set": {f"read_state.{user['id']}": now_iso}})
        # Stamp first_read_at on disappearing messages this viewer hasn't seen.
        await db.messages.update_many(
            {
                "conversation_id": cid,
                "ttl_seconds": {"$gt": 0},
                "first_read_at": None,
                "sender_id": {"$ne": user["id"]},
            },
            {"$set": {"first_read_at": now_iso}},
        )
        # Cancel any pending email digest notifications for this user+conversation.
        await db.chat_notifications.update_many(
            {"recipient_id": user["id"], "conversation_id": cid, "status": "pending"},
            {"$set": {"status": "cancelled", "cancelled_at": now_iso}},
        )
        return {"ok": True}

    # ---------- Messages ----------
    @api.get("/conversations/{cid}/messages")
    async def list_messages(
        cid: str,
        before: Optional[str] = None,
        limit: int = 50,
        user: dict = Depends(get_current_user),
    ):
        c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
        if not c:
            raise HTTPException(status_code=404, detail="Conversation not found")
        q: dict = {"conversation_id": cid, "deleted_at": None}
        if before:
            q["created_at"] = {"$lt": before}
        items = await db.messages.find(q, {"_id": 0}).sort("created_at", -1).limit(min(limit, 100)).to_list(100)
        items.reverse()
        keep = []
        expired_ids = []
        for m in items:
            if _is_message_expired(m, user["id"]):
                expired_ids.append(m["id"])
            else:
                keep.append(m)
        if expired_ids:
            asyncio.create_task(db.messages.update_many(
                {"id": {"$in": expired_ids}},
                {"$set": {"deleted_at": _now_iso(), "body": "", "attachments": []}},
            ))
        return [message_out(m, user["id"]) for m in keep]

    @api.post("/conversations/{cid}/messages")
    async def send_message(cid: str, body: MessageIn, user: dict = Depends(get_current_user)):
        c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
        if not c:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if not body.body.strip() and not body.attachments:
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        effective_ttl_choice = body.ttl if body.ttl is not None else c.get("ttl", "off")
        ttl_seconds = _ttl_choice_to_seconds(effective_ttl_choice)
        doc = {
            "id": str(uuid.uuid4()),
            "conversation_id": cid,
            "sender_id": user["id"],
            "sender_name": user.get("name", ""),
            "sender_avatar": user.get("avatar_url", ""),
            "body": body.body,
            "attachments": body.attachments,
            "reply_to": body.reply_to,
            "ttl_seconds": ttl_seconds,
            "first_read_at": None,
            "created_at": _now_iso(),
            "edited_at": None,
            "deleted_at": None,
        }
        await db.messages.insert_one(doc)
        preview = body.body if body.body else (f"📎 {body.attachments[0].get('filename', 'Attachment')}" if body.attachments else "")
        await db.conversations.update_one(
            {"id": cid},
            {"$set": {"last_message_at": doc["created_at"], "last_message_preview": preview[:140], f"read_state.{user['id']}": doc["created_at"]}},
        )
        payload = message_out(doc, user["id"])
        await chat_hub.push(c.get("member_ids", []), {"type": "message:new", "message": payload})
        try:
            await queue_chat_notifications(c, doc, user)
        except Exception as e:
            logger.warning(f"queue_chat_notifications failed: {e}")
        return payload

    @api.delete("/messages/{mid}")
    async def delete_message(mid: str, user: dict = Depends(get_current_user)):
        m = await db.messages.find_one({"id": mid})
        if not m:
            raise HTTPException(status_code=404, detail="Message not found")
        if m["sender_id"] != user["id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not allowed")
        await db.messages.update_one({"id": mid}, {"$set": {"deleted_at": _now_iso(), "body": "", "attachments": []}})
        c = await db.conversations.find_one({"id": m["conversation_id"]})
        if c:
            await chat_hub.push(c.get("member_ids", []), {"type": "message:deleted", "message_id": mid, "conversation_id": m["conversation_id"]})
        return {"ok": True}

    # ---------- File uploads ----------
    @api.post("/chat/upload")
    async def chat_upload(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
        chunks = []
        total = 0
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > CHAT_MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail=f"File exceeds {CHAT_MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
            chunks.append(chunk)
        data = b"".join(chunks)
        fname = (file.filename or "file").replace("/", "_")
        ext = (fname.rsplit(".", 1)[-1] if "." in fname else "").lower()
        content_type = file.content_type or mime_by_ext.get(ext, "application/octet-stream")
        file_id = str(uuid.uuid4())
        storage_path = f"chat/{user['id']}/{file_id}/{fname}"
        await asyncio.to_thread(put_object, storage_path, data, content_type)
        kind = (
            "image" if ext in image_ext
            else "video" if ext in {"mp4", "mov", "webm", "avi"}
            else "audio" if ext in {"mp3", "wav", "ogg", "m4a"}
            else "file"
        )
        rec = {
            "id": file_id,
            "filename": fname,
            "storage_path": storage_path,
            "content_type": content_type,
            "size": total,
            "kind": kind,
            "uploaded_by": user["id"],
            "is_deleted": False,
            "created_at": _now_iso(),
        }
        await db.chat_files.insert_one(rec)
        return {
            "id": file_id,
            "filename": fname,
            "url": f"/api/files/{storage_path}",
            "size": total,
            "content_type": content_type,
            "kind": kind,
        }

    # ---------- WebSocket ----------
    def _decode_jwt(token: str) -> Optional[dict]:
        try:
            return _pyjwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
        except Exception:
            return None

    @app.websocket("/api/ws/chat")
    async def chat_ws(ws: WebSocket):
        token = ws.cookies.get("access_token")
        payload = _decode_jwt(token) if token else None
        if not payload or not payload.get("sub"):
            await ws.close(code=4401)
            return
        user_id = payload["sub"]
        u = await db.users.find_one({"id": user_id})
        if not u:
            await ws.close(code=4401)
            return
        await chat_hub.connect(user_id, ws)
        try:
            await ws.send_json({"type": "connected", "user_id": user_id})
            while True:
                msg = await ws.receive_json()
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong"})
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning(f"WS error for {user_id}: {e}")
        finally:
            chat_hub.disconnect(user_id, ws)

    # Re-export key helpers so server.py's chat-email-digest service (which
    # still lives in server.py) can keep importing them via the chat module.
    register.conversation_out = conversation_out
    register.message_out = message_out
    register.user_brief = _user_brief
