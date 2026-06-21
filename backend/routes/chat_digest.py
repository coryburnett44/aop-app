"""Chat email digest service.

Extracted from server.py (Iter 62). Owns the asynchronous queue + background
loop that batches unread chat messages into a single email (and optional SMS)
per recipient per conversation after a debounce window.

Public surface (re-exported through the module):
  - `queue_chat_notifications(conv, message, sender)`     — called by routes/chat.py on every new message
  - `start_chat_digest_loop()`                            — start the background task at FastAPI startup
  - `CHAT_DIGEST_DELAY_SECONDS`                           — debounce window (15 min)

Internal:
  - `_send_chat_digest_email(recipient, conv, notifs)` — Resend transactional send
  - `_send_chat_digest_sms(recipient, conv, notifs)`   — short text via Twilio
  - `_chat_digest_loop()`                              — 60-second tick

Fixes a latent bug from the pre-extraction code: the previous module-level
`_now_iso()` calls would have raised `NameError` because the helper only
existed as a closure inside `routes/chat.py`. The extracted module uses
`iso(now_utc())` directly via the configured helpers.
"""
import asyncio
import os
import uuid
from datetime import timedelta
from typing import Optional


CHAT_DIGEST_DELAY_SECONDS = 15 * 60  # debounce window — 15 minutes per spec.

# Configured by `register(...)` at app startup so the rest of the module can
# stay reference-free (and the unit tests can monkey-patch these).
_db = None
_iso = None
_now_utc = None
_RESEND_API_KEY: Optional[str] = None
_RESEND_FROM: Optional[str] = None
_resend_sdk = None
_send_sms = None
_logger = None
_loop_task: Optional[asyncio.Task] = None


def _html_escape(s: str) -> str:
    import html as _h
    return _h.escape(s or "")


async def queue_chat_notifications(conv: dict, message: dict, sender: dict):
    """Insert one pending notification per recipient (excluding sender).

    A background task wakes every 60s, sends consolidated emails (+ SMS if a
    phone number is on file) for any recipient whose oldest pending
    notification has aged past `CHAT_DIGEST_DELAY_SECONDS`, and marks them
    sent. Read-receipts cancel pending notifications (handled inside
    `routes/chat.py::mark_read`). Recipients who have opted out of BOTH email
    and SMS are skipped at queue time."""
    if _db is None:
        return  # extractor not configured yet — drop the notification silently
    due_at = _iso(_now_utc() + timedelta(seconds=CHAT_DIGEST_DELAY_SECONDS))
    member_ids = [rid for rid in conv.get("member_ids", []) if rid != sender["id"]]
    if not member_ids:
        return
    recipients = await _db.users.find(
        {"id": {"$in": member_ids}},
        {"_id": 0, "id": 1, "chat_email_notifications": 1, "chat_sms_notifications": 1},
    ).to_list(len(member_ids))
    prefs = {r["id"]: r for r in recipients}
    docs = []
    now_iso = _iso(_now_utc())
    for rid in member_ids:
        p = prefs.get(rid, {})
        email_on = p.get("chat_email_notifications", True)
        sms_on = p.get("chat_sms_notifications", True)
        if not email_on and not sms_on:
            continue  # fully opted out
        docs.append({
            "id": str(uuid.uuid4()),
            "recipient_id": rid,
            "conversation_id": conv["id"],
            "message_id": message["id"],
            "sender_id": sender["id"],
            "sender_name": sender.get("name", ""),
            "preview": (message.get("body") or "")[:200],
            "status": "pending",
            "due_at": due_at,
            "created_at": now_iso,
        })
    if docs:
        await _db.chat_notifications.insert_many(docs)


async def _send_chat_digest_email(recipient: dict, conv: dict, notifs: list) -> bool:
    """One consolidated email per recipient + conversation. Returns True on success."""
    if not _RESEND_API_KEY:
        return False
    to_email = (recipient.get("email") or "").strip()
    if not to_email:
        return False
    name = recipient.get("name") or recipient.get("first_name") or "there"
    conv_name = conv.get("name") or "your chat"
    count = len(notifs)
    senders = list({n.get("sender_name", "") for n in notifs if n.get("sender_name")})
    senders_label = ", ".join(senders[:3]) + (f" +{len(senders) - 3} others" if len(senders) > 3 else "")
    items_html = "".join(
        f"<li><strong>{_html_escape(n.get('sender_name', ''))}</strong>: {_html_escape(n.get('preview', ''))}</li>"
        for n in notifs[:10]
    )
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    body_html = f"""
    <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#222">
      <h2 style="color:#C8102E;margin:0 0 12px">You have {count} unread message{'s' if count != 1 else ''}</h2>
      <p>Hi {_html_escape(name)}, you received new messages in <strong>{_html_escape(conv_name)}</strong> from {_html_escape(senders_label) or 'Alpha Omega Phi'}.</p>
      <ul style="background:#f7f5f0;border-radius:12px;padding:16px 16px 16px 32px">{items_html}</ul>
      <p style="margin-top:24px"><a href="{frontend}/chat" style="background:#C8102E;color:#fff;padding:10px 20px;border-radius:999px;text-decoration:none;font-weight:600">Open chat</a></p>
      <p style="font-size:11px;color:#888;margin-top:24px">You receive this email because you didn't open your chat within {CHAT_DIGEST_DELAY_SECONDS // 60} minutes of receiving a message.</p>
    </div>
    """
    try:
        params = {
            "from": _RESEND_FROM,
            "to": [to_email],
            "subject": f"{count} new message{'s' if count != 1 else ''} from Alpha Omega Phi chat",
            "html": body_html,
            "tags": [{"name": "type", "value": "chat_digest"}],
        }
        await asyncio.to_thread(_resend_sdk.Emails.send, params)
        return True
    except Exception as e:
        _logger.warning(f"Chat digest email failed for {to_email}: {e}")
        return False


async def _send_chat_digest_sms(recipient: dict, conv: dict, notifs: list) -> bool:
    """Per spec: short text. Recipient has phone + sms_on already checked."""
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    body = f"You have a new message in Alpha Omega Phi chat. Open the portal to read it: {frontend.rstrip('/')}/chat"
    return await _send_sms(recipient["phone"], body)


async def _chat_digest_loop():
    """Background loop: every 60s, batch pending notifications older than
    `due_at` by (recipient, conversation), send one consolidated email + SMS
    per bundle, mark them sent."""
    while True:
        try:
            now_iso_s = _iso(_now_utc())
            cursor = _db.chat_notifications.find(
                {"status": "pending", "due_at": {"$lte": now_iso_s}},
                {"_id": 0},
            ).limit(500)
            items = await cursor.to_list(500)
            groups: dict = {}
            for n in items:
                key = (n["recipient_id"], n["conversation_id"])
                groups.setdefault(key, []).append(n)
            for (rid, cid), notifs in groups.items():
                recipient = await _db.users.find_one({"id": rid}, {"_id": 0, "password_hash": 0})
                conv = await _db.conversations.find_one({"id": cid}, {"_id": 0})
                if not recipient or not conv:
                    await _db.chat_notifications.update_many(
                        {"id": {"$in": [n["id"] for n in notifs]}},
                        {"$set": {"status": "skipped", "sent_at": _iso(_now_utc())}},
                    )
                    continue
                email_on = recipient.get("chat_email_notifications", True)
                sms_on = recipient.get("chat_sms_notifications", True)
                email_sent = False
                sms_sent = False
                if email_on:
                    email_sent = await _send_chat_digest_email(recipient, conv, notifs)
                if sms_on and recipient.get("phone"):
                    sms_sent = await _send_chat_digest_sms(recipient, conv, notifs)
                attempted_any = email_on or (sms_on and recipient.get("phone"))
                if not attempted_any:
                    final = "skipped"
                elif email_sent or sms_sent:
                    final = "sent"
                else:
                    final = "failed"
                await _db.chat_notifications.update_many(
                    {"id": {"$in": [n["id"] for n in notifs]}},
                    {"$set": {"status": final, "sent_at": _iso(_now_utc()), "email_sent": email_sent, "sms_sent": sms_sent}},
                )
        except Exception as e:
            if _logger:
                _logger.error(f"chat digest loop iteration error: {e}")
        await asyncio.sleep(60)


def register(*, db, iso, now_utc, resend_api_key, resend_from, resend_sdk, send_sms, logger):
    """Bind dependencies. Call this exactly once at app startup BEFORE
    spinning up the background loop (and BEFORE wiring `routes/chat.py`,
    which needs `queue_chat_notifications`)."""
    global _db, _iso, _now_utc, _RESEND_API_KEY, _RESEND_FROM, _resend_sdk, _send_sms, _logger
    _db = db
    _iso = iso
    _now_utc = now_utc
    _RESEND_API_KEY = resend_api_key
    _RESEND_FROM = resend_from
    _resend_sdk = resend_sdk
    _send_sms = send_sms
    _logger = logger


def start_chat_digest_loop() -> asyncio.Task:
    """Spawn the background loop on the current event loop. Idempotent — if
    a task is already running, returns it instead of starting a second one."""
    global _loop_task
    if _loop_task is None or _loop_task.done():
        _loop_task = asyncio.create_task(_chat_digest_loop())
    return _loop_task
