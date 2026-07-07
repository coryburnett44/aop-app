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
    promote_ids: Optional[List[str]] = None
    demote_ids: Optional[List[str]] = None
    member_add_policy: Optional[Literal["admins_only", "anyone"]] = None
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
    send_bulk_email,
    send_sms,
    frontend_url,
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
            "admin_ids": c.get("admin_ids", []),
            "member_add_policy": c.get("member_add_policy", "admins_only"),
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
            "kind": m.get("kind") or "text",
            "meeting": m.get("meeting"),
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
            "admin_ids": [],  # creator is implicitly an admin; extras go here
            "member_add_policy": "admins_only",
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

        # Role of the requester within this conversation. Site-admins are
        # granted creator-level power everywhere so they can moderate any chat.
        creator_id = c.get("created_by")
        admin_ids = list(c.get("admin_ids", []) or [])
        is_creator = user["id"] == creator_id or user.get("role") == "admin"
        is_group_admin = is_creator or user["id"] in admin_ids
        policy = c.get("member_add_policy", "admins_only")
        is_dm = c.get("type") == "dm"
        can_add_members = is_dm or is_group_admin or (policy == "anyone")

        sets: dict = {}
        if body.name is not None:
            sets["name"] = body.name
        if body.avatar_url is not None:
            sets["avatar_url"] = body.avatar_url
        if body.ttl is not None:
            sets["ttl"] = body.ttl
        if body.member_add_policy is not None:
            if is_dm:
                raise HTTPException(status_code=400, detail="Policy applies to group chats only")
            if not is_creator:
                raise HTTPException(status_code=403, detail="Only the creator can change who may add members")
            sets["member_add_policy"] = body.member_add_policy

        # ---- Membership changes ----
        current_members = set(c.get("member_ids", []))
        new_members = set(current_members)
        member_ids_dirty = False
        if body.add_member_ids:
            if not can_add_members:
                raise HTTPException(status_code=403, detail="Only group admins can add members to this chat")
            before = set(new_members)
            new_members.update(body.add_member_ids)
            if new_members != before:
                member_ids_dirty = True
        if body.remove_member_ids:
            if is_dm:
                raise HTTPException(status_code=400, detail="Can't remove members from a DM — leave the chat instead")
            if not is_group_admin:
                raise HTTPException(status_code=403, detail="Only the creator or group admins can remove members")
            if creator_id in body.remove_member_ids:
                raise HTTPException(status_code=400, detail="The group creator can't be removed — they must delete the group instead")
            before = set(new_members)
            for rid in body.remove_member_ids:
                new_members.discard(rid)
                # If the removed member was a group-admin, also drop from admin_ids.
                if rid in admin_ids:
                    admin_ids.remove(rid)
            if new_members != before:
                member_ids_dirty = True
        # The editor can never accidentally remove themselves via this endpoint.
        new_members.add(user["id"])
        if member_ids_dirty:
            sets["member_ids"] = list(new_members)
            # DM → group auto-promotion when a 3rd participant joins.
            if is_dm and len(new_members) > 2:
                sets["type"] = "group"
                # First person to add is treated as the (still) creator — no
                # extra bootstrap; other DM parties stay regular members.

        # ---- Promote / demote (creator-only) ----
        admin_ids_dirty = False
        if body.promote_ids or body.demote_ids:
            if is_dm:
                raise HTTPException(status_code=400, detail="Only group chats have group admins")
            if not is_creator:
                raise HTTPException(status_code=403, detail="Only the creator can change group admins")
            final_members = new_members if member_ids_dirty else current_members
            if body.promote_ids:
                for pid in body.promote_ids:
                    if pid == creator_id:
                        continue  # already implicit admin
                    if pid not in final_members:
                        raise HTTPException(status_code=400, detail="Can't promote a non-member — add them first")
                    if pid not in admin_ids:
                        admin_ids.append(pid)
                        admin_ids_dirty = True
            if body.demote_ids:
                for did in body.demote_ids:
                    if did == creator_id:
                        raise HTTPException(status_code=400, detail="The creator can't be demoted")
                    if did in admin_ids:
                        admin_ids.remove(did)
                        admin_ids_dirty = True

        # Removed members who happened to be admins were already popped above.
        if admin_ids_dirty or (member_ids_dirty and set(admin_ids) != set(c.get("admin_ids", []) or [])):
            sets["admin_ids"] = admin_ids

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
        # Drop leaver from admin_ids if they had that role.
        sets = {"member_ids": new_members}
        current_admins = list(c.get("admin_ids", []) or [])
        if user["id"] in current_admins:
            current_admins.remove(user["id"])
            sets["admin_ids"] = current_admins
        await db.conversations.update_one({"id": cid}, {"$set": sets})
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

    # ---------- Video meetings (Jitsi Meet — free, no key required) ----------
    # A participant is considered "active" if their `last_seen_at` heartbeat
    # is within this window. Chosen to be 2× the client's 15s polling cadence.
    MEETING_ACTIVE_WINDOW_SECONDS = 30
    # A meeting is "over" once someone has joined AND no participants are
    # currently active. Cards use this flag to stop their 15s poller.

    def _meeting_over(any_ever_joined: bool, active_count: int) -> bool:
        return any_ever_joined and active_count == 0

    @api.post("/conversations/{cid}/video-meeting")
    async def start_video_meeting(cid: str, user: dict = Depends(get_current_user)):
        """Generate a fresh Jitsi room URL and post it as a system-flavored
        message so every member sees an in-thread 'Join meeting' card.
        Anyone in the conversation may start a meeting — rooms are ephemeral
        and only live on jitsi's server for as long as someone is present."""
        c = await db.conversations.find_one({"id": cid, "member_ids": user["id"]})
        if not c:
            raise HTTPException(status_code=404, detail="Conversation not found")
        # Use a URL-safe slug so the room name is stable per-conversation +
        # per-launch but still hard to guess (16 bytes of entropy).
        slug = ''.join(ch for ch in (c.get("name") or "aop-chat").lower() if ch.isalnum())[:20] or "aop-chat"
        room = f"aop-{slug}-{uuid.uuid4().hex[:12]}"
        meeting_url = f"https://meet.jit.si/{room}"
        now_iso = _now_iso()
        doc = {
            "id": str(uuid.uuid4()),
            "conversation_id": cid,
            "sender_id": user["id"],
            "sender_name": user.get("name", ""),
            "sender_avatar": user.get("avatar_url", ""),
            "body": "",
            "attachments": [],
            "reply_to": None,
            "ttl_seconds": 0,  # meeting cards never disappear
            "first_read_at": None,
            "created_at": now_iso,
            "edited_at": None,
            "deleted_at": None,
            "kind": "video_meeting",
            "meeting": {
                "url": meeting_url,
                "room": room,
                "started_by": user["id"],
                "started_by_name": user.get("name", ""),
                "started_at": now_iso,
            },
        }
        await db.messages.insert_one(doc)
        preview = f"📹 {user.get('name', 'Someone')} started a video meeting"
        await db.conversations.update_one(
            {"id": cid},
            {"$set": {"last_message_at": now_iso, "last_message_preview": preview[:140], f"read_state.{user['id']}": now_iso}},
        )
        payload = message_out(doc, user["id"])
        member_ids = c.get("member_ids", []) or []
        await chat_hub.push(member_ids, {"type": "message:new", "message": payload})

        # Immediate video-meeting fan-out: bypasses the 15-min digest debounce
        # so members are notified the moment the meeting starts. Sends a
        # dedicated `meeting:notify` WebSocket event and a transactional email
        # (both — the app handles anti-spam by only firing per meeting start).
        conv_name = c.get("name") or await _pretty_conv_name_for(c, user["id"])
        starter_name = user.get("name", "Someone")
        notify_payload = {
            "type": "meeting:notify",
            "conversation_id": cid,
            "conversation_name": conv_name,
            "message_id": doc["id"],
            "started_by_name": starter_name,
            "started_by_id": user["id"],
            "meeting_url": meeting_url,
        }
        # Push to everyone except the starter so they don't ping themselves.
        recipients_push = [uid for uid in member_ids if uid != user["id"]]
        try:
            await chat_hub.push(recipients_push, notify_payload)
        except Exception as e:
            logger.warning(f"meeting:notify push failed: {e}")

        # Transactional email — sent one at a time so each recipient gets a
        # per-recipient unsubscribe header (compliant + also personalizable).
        try:
            recipients = [u async for u in db.users.find(
                {
                    "id": {"$in": recipients_push},
                    "email": {"$exists": True, "$ne": ""},
                    "email_opt_out": {"$ne": True},
                },
                {"_id": 0, "id": 1, "email": 1, "name": 1, "email_prefs": 1},
            )]
            fe = frontend_url or ""
            chat_link = f"{fe}/chat/{cid}" if fe else meeting_url
            for r in recipients:
                # Respect chat_notifications opt-out if the user has toggled it.
                if (r.get("email_prefs") or {}).get("chat_notifications") is False:
                    continue
                await _send_video_meeting_email(
                    to_email=r["email"],
                    to_name=r.get("name", ""),
                    recipient_id=r["id"],
                    starter_name=starter_name,
                    conv_name=conv_name,
                    meeting_url=meeting_url,
                    chat_url=chat_link,
                )
        except Exception as e:
            logger.warning(f"video meeting email fan-out failed: {e}")

        # SMS fan-out (Brevo). Each recipient with a phone number AND the
        # `chat_sms_notifications` preference not explicitly disabled gets a
        # one-line text linking to the meeting. Best-effort — failures per
        # recipient are logged, the endpoint always returns success.
        try:
            sms_recipients = [u async for u in db.users.find(
                {
                    "id": {"$in": recipients_push},
                    "phone": {"$exists": True, "$ne": ""},
                },
                {"_id": 0, "id": 1, "name": 1, "phone": 1, "chat_sms_notifications": 1},
            )]
            sms_body = (
                f"📹 {starter_name} started a video meeting in "
                f"\"{conv_name}\". Join: {meeting_url}"
            )[:1500]
            for r in sms_recipients:
                if r.get("chat_sms_notifications") is False:
                    continue
                ok = await send_sms(r["phone"], sms_body)
                if not ok:
                    logger.info(f"video-meeting SMS skipped for {r.get('name','?')} ({r.get('phone','?')}) — provider unavailable or invalid number")
        except Exception as e:
            logger.warning(f"video meeting SMS fan-out failed: {e}")

        return payload

    async def _pretty_conv_name_for(c: dict, viewer_id: str) -> str:
        # For DMs, show the other participant's name; for groups use the
        # explicit name (fallback to "Video meeting").
        if c.get("name"):
            return c["name"]
        if c.get("type") == "dm":
            other_ids = [uid for uid in (c.get("member_ids") or []) if uid != viewer_id]
            if other_ids:
                brief = await _user_brief(other_ids[0])
                return f"chat with {brief.get('name', 'a member')}"
        return "your chat"

    async def _send_video_meeting_email(*, to_email: str, to_name: str, recipient_id: str,
                                        starter_name: str, conv_name: str, meeting_url: str, chat_url: str) -> None:
        """Compose + send the transactional invite. Uses the same
        `send_bulk_email` helper the rest of the app relies on so the AOP
        branding, unsubscribe footer, and CAN-SPAM headers stay consistent."""
        first_name = (to_name or "").split(" ")[0] or "there"
        subject = f"📹 {starter_name} started a video meeting in {conv_name}"
        button_html = (
            f'<div style="text-align:center;margin:24px 0">'
            f'<a href="{meeting_url}" target="_blank" rel="noopener" '
            f'style="display:inline-block;background:#C8102E;color:#ffffff;text-decoration:none;'
            f'font-weight:700;padding:14px 32px;border-radius:999px;font-size:15px;line-height:1;'
            f'font-family:Inter,Helvetica,Arial,sans-serif">Join meeting</a></div>'
        )
        html_body = (
            f'<p>Hi {first_name},</p>'
            f'<p><strong>{starter_name}</strong> just started a video meeting in <strong>{conv_name}</strong>. '
            f'Tap the button below to join instantly — no downloads, works on any browser.</p>'
            f'{button_html}'
            f'<p style="font-size:13px;color:#64748b">Or paste this link into your browser: '
            f'<a href="{meeting_url}" style="color:#0A2463">{meeting_url}</a></p>'
            f'<hr style="border:none;border-top:1px solid #e2e8f0;margin:24px auto;max-width:80%">'
            f'<p style="font-size:12px;color:#94a3b8;text-align:center">Missed it? '
            f'<a href="{chat_url}" style="color:#0A2463">Open the chat</a> to see who else joined.</p>'
        )
        try:
            await send_bulk_email(
                to_email=to_email,
                subject=subject,
                html_body=html_body,
                recipient_id=recipient_id,
                tags=[
                    {"name": "type", "value": "chat_video_meeting"},
                ],
            )
        except Exception as e:
            logger.warning(f"video meeting email to {to_email} failed: {e}")

    async def _meeting_participants_summary(meeting_id: str) -> dict:
        """Compute {active, count, is_over} for a meeting. Active window is
        {MEETING_ACTIVE_WINDOW_SECONDS}s (2× the client's 15s poll)."""
        from datetime import timedelta
        now = now_utc()
        cutoff = iso(now - timedelta(seconds=MEETING_ACTIVE_WINDOW_SECONDS))
        active_cursor = db.meeting_participants.find(
            {
                "meeting_id": meeting_id,
                "left_at": None,
                "last_seen_at": {"$gte": cutoff},
            },
            {"_id": 0, "user_id": 1, "user_name": 1, "avatar_url": 1, "last_seen_at": 1, "joined_at": 1},
        ).sort("joined_at", 1)
        active = [p async for p in active_cursor]
        any_ever = await db.meeting_participants.count_documents({"meeting_id": meeting_id}) > 0
        return {
            "meeting_id": meeting_id,
            "active": active,
            "count": len(active),
            "is_over": _meeting_over(any_ever, len(active)),
            "any_ever_joined": any_ever,
        }

    async def _ensure_can_view_meeting(mid: str, user: dict) -> tuple[dict, dict]:
        m = await db.messages.find_one({"id": mid, "kind": "video_meeting"}, {"_id": 0})
        if not m:
            raise HTTPException(status_code=404, detail="Meeting message not found")
        c = await db.conversations.find_one({"id": m["conversation_id"], "member_ids": user["id"]})
        if not c:
            raise HTTPException(status_code=404, detail="Meeting message not found")
        return m, c

    @api.post("/meetings/{mid}/heartbeat")
    async def meeting_heartbeat(mid: str, left: bool = False, user: dict = Depends(get_current_user)):
        """Called by the client every 15s while the meeting modal is open,
        and once with `left=true` when the user closes/leaves."""
        m, _c = await _ensure_can_view_meeting(mid, user)
        now = _now_iso()
        set_doc = {
            "meeting_id": mid,
            "conversation_id": m["conversation_id"],
            "user_id": user["id"],
            "user_name": user.get("name", ""),
            "avatar_url": user.get("avatar_url", ""),
            "last_seen_at": now,
            "left_at": now if left else None,
        }
        # Upsert: `joined_at` set only on first insert; subsequent heartbeats
        # only refresh last_seen_at / left_at.
        await db.meeting_participants.update_one(
            {"meeting_id": mid, "user_id": user["id"]},
            {"$set": set_doc, "$setOnInsert": {"id": str(uuid.uuid4()), "joined_at": now}},
            upsert=True,
        )
        summary = await _meeting_participants_summary(mid)
        # Broadcast so other members' cards update near-instantly (in addition
        # to their own 15s poll) — cheap because it only fires on join/leave.
        try:
            await chat_hub.push(
                (await db.conversations.find_one({"id": m["conversation_id"]}, {"_id": 0, "member_ids": 1})).get("member_ids", []),
                {"type": "meeting:update", "conversation_id": m["conversation_id"], "summary": summary},
            )
        except Exception as e:
            logger.warning(f"meeting:update push failed: {e}")
        return summary

    @api.get("/meetings/{mid}/participants")
    async def meeting_participants(mid: str, user: dict = Depends(get_current_user)):
        await _ensure_can_view_meeting(mid, user)
        return await _meeting_participants_summary(mid)

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
