"""OneSignal web-push integration.

Sends push notifications via OneSignal's REST API and exposes admin-facing
endpoints for composing / auditing / triggering broadcast pushes. Frontend
subscribes users through the OneSignal Web SDK; we identify each session via
`external_id = <mongo user.id>` so backend calls target the correct people.

Environment:
  ONESIGNAL_APP_ID       — public app id (safe to use in error responses)
  ONESIGNAL_REST_API_KEY — SECRET rest key, never leaves the backend
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Literal, Optional

import requests
from fastapi import Depends, HTTPException
from pydantic import BaseModel


ONESIGNAL_API_URL = "https://api.onesignal.com/notifications?c=push"
ONESIGNAL_REQUEST_TIMEOUT = 20


def _env() -> tuple[str, str]:
    app_id = os.environ.get("ONESIGNAL_APP_ID", "").strip()
    rest = os.environ.get("ONESIGNAL_REST_API_KEY", "").strip()
    return app_id, rest


def is_configured() -> bool:
    a, r = _env()
    return bool(a and r)


class SubscriptionIn(BaseModel):
    subscription_id: str = ""
    opted_in: bool = True


class PushComposeIn(BaseModel):
    """Admin → Push composer payload."""
    title: str
    body: str
    url: Optional[str] = None
    icon_url: Optional[str] = None
    # Audience: exactly one of these should be non-empty. If several are set,
    # `user_ids` wins → then chapters/tiers/segments → then "everyone".
    segment: Literal["all", "active", "admins", "chapter", "tier", "custom"] = "active"
    chapter_id: Optional[str] = None
    tier_id: Optional[str] = None
    user_ids: list[str] = []
    test_only: bool = False


def _build_target_payload(
    *,
    app_id: str,
    body: PushComposeIn,
    resolved_user_ids: list[str],
) -> dict:
    """Assemble the OneSignal REST-API request body for the given audience."""
    data: dict[str, Any] = {
        "app_id": app_id,
        "target_channel": "push",
        "headings": {"en": body.title},
        "contents": {"en": body.body},
        "idempotency_key": str(uuid.uuid4()),
    }
    if body.url:
        data["url"] = body.url
    if body.icon_url:
        data["chrome_web_icon"] = body.icon_url
        data["chrome_web_image"] = body.icon_url
        data["firefox_icon"] = body.icon_url
    # OneSignal caps `include_aliases.external_id` at 20,000 entries per
    # request — plenty for a fraternity roster. If we ever exceed it we'd
    # need to chunk.
    if resolved_user_ids:
        data["include_aliases"] = {"external_id": resolved_user_ids[:20000]}
    else:
        # "everybody who ever subscribed" is a built-in OneSignal segment.
        data["included_segments"] = ["Subscribed Users"]
    return data


async def _post_to_onesignal(payload: dict) -> dict:
    """Fire the REST call from a worker thread so we don't block the event
    loop. Returns the parsed JSON or raises HTTPException with the OneSignal
    error surface preserved."""
    _, rest = _env()

    def _do() -> tuple[int, dict]:
        r = requests.post(
            ONESIGNAL_API_URL,
            json=payload,
            headers={
                "Authorization": f"Key {rest}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=ONESIGNAL_REQUEST_TIMEOUT,
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:400]}

    status, body = await asyncio.to_thread(_do)
    if status >= 400:
        raise HTTPException(status_code=502, detail={"onesignal_status": status, "error": body})
    return body


def register(api, *, db, admin_tab_dep, get_current_user, iso, now_utc, logger):
    async def _resolve_recipients(body: PushComposeIn, admin: dict) -> list[str]:
        """Return the list of mongo user_ids that should receive the push.
        Empty list means "broadcast to Subscribed Users segment"."""
        if body.test_only:
            return [admin["id"]]
        if body.segment == "custom":
            return [uid for uid in (body.user_ids or []) if uid]
        # Everyone-who-opted-in flows: rely on OneSignal's Subscribed Users
        # segment so we don't need to build a giant alias list.
        if body.segment == "all":
            return []
        q: dict = {"status_override": {"$ne": "deceased"}}
        if body.segment == "active":
            pass  # active is exactly the "not deceased" filter above
        elif body.segment == "admins":
            q["role"] = "admin"
        elif body.segment == "chapter" and body.chapter_id:
            q["chapter_id"] = body.chapter_id
        elif body.segment == "tier" and body.tier_id:
            q["tier_id"] = body.tier_id
        cursor = db.users.find(q, {"_id": 0, "id": 1}).limit(20000)
        return [u["id"] async for u in cursor]

    # ============================================================
    # Public config for the Web SDK (safe to expose the App ID).
    # ============================================================
    @api.get("/push/config")
    async def push_config():
        app_id, _rest = _env()
        return {
            "enabled": bool(app_id),
            "app_id": app_id,
            "safari_web_id": os.environ.get("ONESIGNAL_SAFARI_WEB_ID", ""),
        }

    # ============================================================
    # Called by the frontend right after `OneSignal.login()` so we can
    # remember which members have granted push permission — used by the
    # admin composer's "audience preview" and by future channel-hygiene
    # crons.
    # ============================================================
    @api.post("/push/subscription")
    async def upsert_push_subscription(body: SubscriptionIn, user: dict = Depends(get_current_user)):
        await db.push_subscriptions.update_one(
            {"user_id": user["id"]},
            {"$set": {
                "user_id": user["id"],
                "subscription_id": body.subscription_id or "",
                "opted_in": bool(body.opted_in),
                "updated_at": iso(now_utc()),
            }, "$setOnInsert": {"created_at": iso(now_utc())}},
            upsert=True,
        )
        return {"ok": True}

    @api.get("/push/me")
    async def get_my_push_status(user: dict = Depends(get_current_user)):
        row = await db.push_subscriptions.find_one({"user_id": user["id"]}, {"_id": 0})
        return row or {"user_id": user["id"], "opted_in": False, "subscription_id": ""}

    # ============================================================
    # Admin composer + history
    # ============================================================
    @api.post("/admin/push/send")
    async def send_push(body: PushComposeIn, admin: dict = Depends(admin_tab_dep("email"))):
        """Admin-triggered ad-hoc push. Gated by the `email` admin tab so any
        admin who can send email blasts can also send pushes — same audience."""
        if not is_configured():
            raise HTTPException(status_code=503, detail="OneSignal not configured (ONESIGNAL_APP_ID / REST key)")
        app_id, _rest = _env()
        recipients = await _resolve_recipients(body, admin)
        payload = _build_target_payload(app_id=app_id, body=body, resolved_user_ids=recipients)
        result = await _post_to_onesignal(payload)
        log = {
            "id": str(uuid.uuid4()),
            "title": body.title,
            "body": body.body,
            "url": body.url or "",
            "icon_url": body.icon_url or "",
            "segment": body.segment,
            "chapter_id": body.chapter_id or "",
            "tier_id": body.tier_id or "",
            "user_ids": recipients if body.segment == "custom" else [],
            "target_count": len(recipients) if recipients else None,  # None = broadcast segment
            "test_only": bool(body.test_only),
            "sent_by": admin["id"],
            "sent_by_name": admin.get("name", "Admin"),
            "sent_at": iso(now_utc()),
            "onesignal_id": (result or {}).get("id", ""),
            "onesignal_recipients": (result or {}).get("recipients", 0),
        }
        await db.push_notifications.insert_one(log)
        log.pop("_id", None)
        if logger:
            logger.info(f"[push] admin={admin.get('email')} sent '{body.title}' → recipients={log['onesignal_recipients']}")
        return {
            "ok": True,
            "onesignal_id": log["onesignal_id"],
            "recipients": log["onesignal_recipients"],
            "target_count": log["target_count"],
        }

    @api.get("/admin/push/history")
    async def list_push_history(_: dict = Depends(admin_tab_dep("email"))):
        items = await db.push_notifications.find({}, {"_id": 0}).sort("sent_at", -1).limit(100).to_list(100)
        return items


# ============================================================
# Helpers used by other modules (news / events / email) to send a push
# alongside their own primary channel. All calls are best-effort — if
# OneSignal isn't configured or the send fails we log & swallow so we
# never break the caller's flow.
# ============================================================
async def send_push_best_effort(
    *,
    db,
    logger,
    iso,
    now_utc,
    title: str,
    body: str,
    url: str = "",
    icon_url: str = "",
    user_ids: Optional[list[str]] = None,
    segment: str = "active",
    chapter_id: str = "",
    tier_id: str = "",
    trigger: str = "manual",
) -> dict:
    """Fire a push targeting the given audience. `user_ids` beats `segment`.
    Never raises — errors are logged and returned as `{ok: false, error}`."""
    if not is_configured():
        return {"ok": False, "skipped": "onesignal_not_configured"}
    app_id, _rest = _env()
    try:
        payload_obj = PushComposeIn(
            title=title,
            body=body,
            url=url or None,
            icon_url=icon_url or None,
            segment=segment if segment in {"all", "active", "admins", "chapter", "tier", "custom"} else "active",  # type: ignore[arg-type]
            chapter_id=chapter_id or None,
            tier_id=tier_id or None,
            user_ids=user_ids or [],
        )
        resolved = user_ids or []
        # For segment-based sends we skip the alias list and let OneSignal's
        # Subscribed Users segment handle it — matches the admin composer's
        # broadcast path.
        if not resolved and segment == "all":
            resolved = []
        elif not resolved and segment in {"active", "admins", "chapter", "tier"}:
            # Resolve segment against Mongo so we can target our internal
            # audience even if the member hasn't tagged themselves yet.
            q: dict = {"status_override": {"$ne": "deceased"}}
            if segment == "admins":
                q["role"] = "admin"
            elif segment == "chapter" and chapter_id:
                q["chapter_id"] = chapter_id
            elif segment == "tier" and tier_id:
                q["tier_id"] = tier_id
            resolved = [u["id"] async for u in db.users.find(q, {"_id": 0, "id": 1}).limit(20000)]
        req = _build_target_payload(app_id=app_id, body=payload_obj, resolved_user_ids=resolved)
        result = await _post_to_onesignal(req)
        try:
            await db.push_notifications.insert_one({
                "id": str(uuid.uuid4()),
                "title": title,
                "body": body,
                "url": url,
                "icon_url": icon_url,
                "segment": segment,
                "chapter_id": chapter_id,
                "tier_id": tier_id,
                "user_ids": user_ids or [],
                "target_count": len(resolved) if resolved else None,
                "test_only": False,
                "sent_by": "system",
                "sent_by_name": trigger,
                "sent_at": iso(now_utc()),
                "onesignal_id": (result or {}).get("id", ""),
                "onesignal_recipients": (result or {}).get("recipients", 0),
                "kind": trigger,
            })
        except Exception:
            pass
        return {"ok": True, "onesignal_id": (result or {}).get("id"), "recipients": (result or {}).get("recipients")}
    except HTTPException as he:
        if logger:
            logger.error(f"[push:{trigger}] send failed: {he.detail}")
        return {"ok": False, "error": str(he.detail)[:500]}
    except Exception as e:
        if logger:
            logger.error(f"[push:{trigger}] unexpected error: {e}")
        return {"ok": False, "error": str(e)[:500]}
