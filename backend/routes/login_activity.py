"""Login & page-view activity tracking.

Models a `login_activity` collection that records one document per user
session, with append-only `pages_visited` entries. Admins can pull a
chronological / per-user view via `/api/admin/login-activity`.

A "session" is opened on a successful `/auth/login` (handled in
`routes/auth.py` — it calls `record_login_session` from this module after
the password check succeeds) and closed via:
  - `/auth/logout` → `record_logout` stamps `logout_at`.
  - Inactivity → no `logout_at`; the session duration is computed from
    `(last_seen_at - login_at)` instead.

Page views are coarse-grained: the frontend pings
`POST /api/activity/page-view {path}` whenever the user navigates. We
append to `pages_visited` (capped at 100 entries to bound document size)
and bump `last_seen_at` so admins can see real session length.
"""
from typing import List, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field

# Sessions inserted by /auth/login are considered the "current open" session
# for that user as long as last_seen_at is within this window. A page-view
# ping outside the window opens a fresh session (rather than re-attaching
# to a stale one — useful for shared-computer / browser-closed scenarios).
SESSION_IDLE_TIMEOUT_MINUTES = 60 * 8  # 8 hours

PAGE_VIEW_CAP = 100  # max pages stored per session document


def register(api, *, db, get_current_user, require_admin, iso, now_utc, logger):
    # ------------------------------------------------------------------
    # Helpers exported back to auth.py (called from /auth/login & /auth/logout)
    # ------------------------------------------------------------------
    async def record_login_session(user: dict, request: Optional[Request]) -> str:
        """Insert a new session document. Returns its `id`."""
        import uuid
        ip = "unknown"
        ua = ""
        if request is not None:
            xff = request.headers.get("x-forwarded-for", "")
            ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
            ua = request.headers.get("user-agent", "")[:300]
        sid = str(uuid.uuid4())
        now = iso(now_utc())
        await db.login_activity.insert_one({
            "id": sid,
            "user_id": user.get("id"),
            "user_name": user.get("name", ""),
            "user_email": user.get("email", ""),
            "login_at": now,
            "last_seen_at": now,
            "logout_at": None,
            "ip": ip,
            "user_agent": ua,
            "pages_visited": [],
        })
        return sid

    async def record_logout(user_id: str) -> None:
        """Stamp `logout_at` on the user's MOST RECENT open session.

        Mongo's `update_one` doesn't accept a sort, so we find the most
        recent open session by id first and then update that exact row.
        Multiple stale open sessions (e.g. previous test runs / closed
        browser tabs) are left alone — they age out naturally via the
        idle-timeout heuristic in /activity/page-view.
        """
        sess = await db.login_activity.find_one(
            {"user_id": user_id, "logout_at": None},
            {"_id": 0, "id": 1},
            sort=[("login_at", -1)],
        )
        if not sess:
            return
        now = iso(now_utc())
        await db.login_activity.update_one(
            {"id": sess["id"]},
            {"$set": {"logout_at": now, "last_seen_at": now}},
        )

    # ------------------------------------------------------------------
    # Public endpoint: page-view ping from the frontend.
    # ------------------------------------------------------------------
    class PageViewIn(BaseModel):
        path: str = Field(..., max_length=512)

    @api.post("/activity/page-view")
    async def record_page_view(
        body: PageViewIn,
        request: Request,
        user: dict = Depends(get_current_user),
    ):
        from datetime import datetime as _dt, timedelta as _td
        now = now_utc()
        cutoff = now - _td(minutes=SESSION_IDLE_TIMEOUT_MINUTES)
        # Find the user's most recent session, if it's still within the
        # idle window. We use last_seen_at (not login_at) because long
        # sessions with steady activity should accumulate page views.
        sess = await db.login_activity.find_one(
            {"user_id": user.get("id")},
            sort=[("last_seen_at", -1)],
        )
        attach_to_existing = False
        if sess:
            try:
                last_seen = _dt.fromisoformat(sess["last_seen_at"].replace("Z", "+00:00"))
                if last_seen >= cutoff and not sess.get("logout_at"):
                    attach_to_existing = True
            except Exception:
                attach_to_existing = False

        page_entry = {"path": body.path[:512], "at": iso(now)}
        if attach_to_existing:
            # Bump last_seen + push the page view; cap pages_visited so a
            # very chatty client doesn't grow the doc unboundedly. Mongo's
            # $push + $slice keeps only the last PAGE_VIEW_CAP entries.
            await db.login_activity.update_one(
                {"id": sess["id"]},
                {
                    "$set": {"last_seen_at": iso(now)},
                    "$push": {"pages_visited": {"$each": [page_entry], "$slice": -PAGE_VIEW_CAP}},
                },
            )
            return {"ok": True, "session_id": sess["id"]}

        # No active session — start one. This covers: 1) page reload after a
        # long idle, 2) cookies / refresh tokens silently re-authenticated
        # without going through /auth/login. We tag those sessions with
        # `started_via: "page_view"` so admins can tell them apart from
        # explicit logins.
        import uuid
        sid = str(uuid.uuid4())
        xff = request.headers.get("x-forwarded-for", "")
        ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
        await db.login_activity.insert_one({
            "id": sid,
            "user_id": user.get("id"),
            "user_name": user.get("name", ""),
            "user_email": user.get("email", ""),
            "login_at": iso(now),
            "last_seen_at": iso(now),
            "logout_at": None,
            "ip": ip,
            "user_agent": request.headers.get("user-agent", "")[:300],
            "pages_visited": [page_entry],
            "started_via": "page_view",
        })
        return {"ok": True, "session_id": sid}

    # ------------------------------------------------------------------
    # Admin endpoint: list sessions with computed duration.
    # ------------------------------------------------------------------
    @api.get("/admin/login-activity")
    async def list_login_activity(
        user_id: Optional[str] = None,
        limit: int = 200,
        _: dict = Depends(require_admin),
    ):
        from datetime import datetime as _dt
        q: dict = {}
        if user_id:
            q["user_id"] = user_id
        limit = max(1, min(limit, 1000))
        rows = await db.login_activity.find(q, {"_id": 0}).sort("login_at", -1).to_list(limit)
        # Annotate with computed duration_seconds for the UI.
        for r in rows:
            try:
                login_at = _dt.fromisoformat((r.get("login_at") or "").replace("Z", "+00:00"))
                end = r.get("logout_at") or r.get("last_seen_at")
                end_at = _dt.fromisoformat(end.replace("Z", "+00:00")) if end else None
                if end_at:
                    r["duration_seconds"] = int((end_at - login_at).total_seconds())
                else:
                    r["duration_seconds"] = None
                r["pages_count"] = len(r.get("pages_visited") or [])
                # By default omit the full page list from the bulk listing
                # to keep the payload small. The admin UI fetches the full
                # session via /admin/login-activity/{id} when expanded.
                if not user_id:
                    r.pop("pages_visited", None)
            except Exception:
                r["duration_seconds"] = None
                r["pages_count"] = len(r.get("pages_visited") or [])
        return rows

    @api.get("/admin/login-activity/{session_id}")
    async def get_login_activity_detail(session_id: str, _: dict = Depends(require_admin)):
        row = await db.login_activity.find_one({"id": session_id}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        from datetime import datetime as _dt
        try:
            login_at = _dt.fromisoformat((row.get("login_at") or "").replace("Z", "+00:00"))
            end = row.get("logout_at") or row.get("last_seen_at")
            end_at = _dt.fromisoformat(end.replace("Z", "+00:00")) if end else None
            row["duration_seconds"] = int((end_at - login_at).total_seconds()) if end_at else None
        except Exception:
            row["duration_seconds"] = None
        row["pages_count"] = len(row.get("pages_visited") or [])
        return row

    # Stash the helpers on the api object so auth.py can reach them.
    api._record_login_session = record_login_session
    api._record_logout = record_logout

    logger.info("[login-activity] registered POST /activity/page-view + GET /admin/login-activity[/{id}]")
