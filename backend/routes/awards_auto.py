"""Automatic award grants — Iter 120.

Three flavors of auto-grant:

  1. **Alpha Omega Phi Ribbon** — granted the moment a new member joins.
     Called synchronously from every "member created" code path (admin
     create, bulk import, public application approval, self-register).

  2. **Service Ribbon** — granted on a member's actual MM/DD anniversary
     when they hit a milestone year (1, 5, 10, 15…). The "clock" respects
     reactivations: for a member who was inactive then paid dues, the
     anniversary uses `reactivated_at` / `status_history` instead of the
     original join date.

  3. **Community Service Ribbon (annual 100+ hours)** — granted every
     December 31 to every active member with ≥ 100 volunteer hours in
     that calendar year.

Everything is idempotent. Every auto-grant is tagged
`granted_by="system:auto"`, `auto_granted=True`, and
`auto_grant_kind=<one of the 3 kinds>` so the admin dashboard can filter
and label them clearly. Dedupe is per (award, user, key-year/date)
depending on the flavor.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date as _date, datetime, timedelta, timezone
from typing import Optional


# ---------- Module-level injected state ----------
db = None
iso = None
now_utc = None
logger = None


AUTO_GRANT_KIND_JOIN = "alpha_omega_phi_ribbon"
AUTO_GRANT_KIND_SERVICE = "service_ribbon"
AUTO_GRANT_KIND_COMMUNITY = "community_service_ribbon"


def register(*, db_ref, iso_fn, now_utc_fn, logger_ref, send_push_best_effort=None):
    """Bind module-level state. Called once from server.py at startup."""
    g = globals()
    g["db"] = db_ref
    g["iso"] = iso_fn
    g["now_utc"] = now_utc_fn
    g["logger"] = logger_ref
    g["send_push_best_effort"] = send_push_best_effort


# ============================================================
# Shared helpers
# ============================================================
def _parse_iso_date(s: str) -> Optional[_date]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).date()
    except Exception:
        try:
            head = str(s)[:10]
            y, m, d = head.split("-")
            return _date(int(y), int(m), int(d))
        except Exception:
            return None


def _streak_start_date(u: dict) -> Optional[_date]:
    """Effective start-of-active-membership date. Priority:
    reactivated_at → latest 'active' in status_history → join_date → created_at."""
    react = u.get("reactivated_at")
    d = _parse_iso_date(react) if react else None
    if d:
        return d
    history = u.get("status_history") or []
    last_active_at = None
    for h in history:
        if (h.get("status") or "").lower() == "active":
            at = h.get("at") or ""
            if not last_active_at or at > last_active_at:
                last_active_at = at
    if last_active_at:
        d = _parse_iso_date(last_active_at)
        if d:
            return d
    return _parse_iso_date(u.get("join_date") or u.get("created_at") or "")


def _years_complete(start: _date, asof: _date) -> int:
    years = asof.year - start.year
    if (asof.month, asof.day) < (start.month, start.day):
        years -= 1
    return max(0, years)


def _is_service_milestone(years_complete: int) -> bool:
    """Service Ribbon fires at 1yr, then every 5yrs (5, 10, 15, 20…)."""
    if years_complete <= 0:
        return False
    return years_complete == 1 or (years_complete >= 5 and years_complete % 5 == 0)


async def _find_award(name: str) -> Optional[dict]:
    """Case-insensitive lookup so a typo variation still resolves."""
    a = await db.awards.find_one({"name": name}, {"_id": 0})
    if a:
        return a
    # Fallback — regex insensitive match.
    a = await db.awards.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}}, {"_id": 0})
    return a


async def _grant(
    *,
    award: dict,
    user: dict,
    kind: str,
    reason: str,
    granted_at_iso: str,
    dedupe_query: dict,
) -> Optional[dict]:
    """Insert an auto-grant IF the dedupe_query matches nothing. Returns the
    inserted doc, or None if we skipped."""
    if await db.award_grants.find_one(dedupe_query, {"_id": 0, "id": 1}):
        return None
    prior_count = await db.award_grants.count_documents({
        "award_id": award["id"], "user_id": user["id"],
    })
    doc = {
        "id": str(uuid.uuid4()),
        "award_id": award["id"],
        "award_name": award["name"],
        "award_icon": award.get("icon", "ribbon"),
        "award_color": award.get("color", "#F9D466"),
        "user_id": user["id"],
        "user_name": user.get("name", ""),
        "reason": reason,
        "granted_by": "system:auto",
        "granted_by_name": "Automatic grant",
        "granted_at": granted_at_iso,
        "ordinal": prior_count + 1,
        "auto_granted": True,
        "auto_grant_kind": kind,
    }
    await db.award_grants.insert_one(doc)
    logger.info(f"[auto-grant] {award['name']} → {user.get('name','?')} ({user['id']}) — {reason}")
    # Companion OneSignal push — best-effort, non-blocking.
    if globals().get("send_push_best_effort") is not None:
        import os as _os
        _frontend = (_os.environ.get("FRONTEND_URL", "https://aop-app.org") or "").rstrip("/")
        try:
            await globals()["send_push_best_effort"](
                db=db, logger=logger, iso=iso, now_utc=now_utc,
                title=f"🏆 New award: {award['name']}",
                body=(reason or f"You've been recognized with the {award['name']}.")[:180],
                url=f"{_frontend}/awards",
                user_ids=[user["id"]],
                segment="custom",
                trigger="award_auto_granted",
            )
        except Exception as _push_e:
            logger.warning(f"[auto-grant] push failed for {user['id']}: {_push_e}")
    return doc


# ============================================================
# 1) Alpha Omega Phi Ribbon on join
# ============================================================
async def grant_alpha_omega_phi_ribbon_on_join(user: dict) -> Optional[dict]:
    """Grant the Alpha Omega Phi Ribbon to a freshly-created member. Safe to
    call from every member-creation code path — idempotent per user."""
    try:
        award = await _find_award("Alpha Omega Phi Ribbon")
        if not award:
            logger.warning("[auto-grant] Alpha Omega Phi Ribbon award not found — skipping join grant")
            return None
        join_iso = user.get("join_date") or user.get("created_at") or iso(now_utc())
        # Dedupe: only one automatic join-grant per (user, kind).
        return await _grant(
            award=award,
            user=user,
            kind=AUTO_GRANT_KIND_JOIN,
            reason=f"Auto-granted on join date ({(join_iso or '')[:10]})",
            granted_at_iso=join_iso,
            dedupe_query={
                "user_id": user["id"],
                "award_id": award["id"],
                "auto_grant_kind": AUTO_GRANT_KIND_JOIN,
            },
        )
    except Exception as e:
        # Never let auto-grant failures block member creation.
        logger.warning(f"[auto-grant] join-grant failed for {user.get('id')}: {e}")
        return None


# ============================================================
# 2) Service Ribbon daily sweep
# ============================================================
async def _sweep_service_ribbon(today: _date) -> int:
    """For every active member whose start-date MM/DD matches today AND whose
    years_complete lands on a milestone, grant the Service Ribbon.

    Dedupe is per (user, award, anniversary_year) so re-running the sweep on
    the same day is a no-op and reruns on a later year still work for the
    next milestone."""
    award = await _find_award("Service Ribbon")
    if not award:
        logger.warning("[auto-grant] Service Ribbon award not found — skipping sweep")
        return 0
    granted = 0
    cursor = db.users.find(
        {
            "status_override": {"$nin": ["inactive", "deceased"]},
        },
        {
            "_id": 0, "id": 1, "name": 1, "join_date": 1, "created_at": 1,
            "reactivated_at": 1, "status_history": 1, "status_override": 1,
        },
    )
    async for u in cursor:
        start = _streak_start_date(u)
        if not start or start > today:
            continue
        if (start.month, start.day) != (today.month, today.day):
            continue
        years = _years_complete(start, today)
        if not _is_service_milestone(years):
            continue
        try:
            anniversary = start.replace(year=start.year + years)
        except ValueError:
            anniversary = start.replace(year=start.year + years, day=28)
        reason = (
            f"Auto-granted on {years}-year anniversary "
            f"({anniversary.isoformat()}, clock started {start.isoformat()})"
        )
        doc = await _grant(
            award=award,
            user=u,
            kind=AUTO_GRANT_KIND_SERVICE,
            reason=reason,
            granted_at_iso=iso(now_utc()),
            dedupe_query={
                "user_id": u["id"],
                "award_id": award["id"],
                "auto_grant_kind": AUTO_GRANT_KIND_SERVICE,
                "reason": reason,  # unique per (user, anniversary date + start date)
            },
        )
        if doc:
            granted += 1
    return granted


# ============================================================
# 3) Community Service Ribbon (annual 100+ hours) — Dec 31 sweep
# ============================================================
async def _hours_by_user_for_year(year: int) -> dict:
    """Sum approved volunteer hours per user for the given calendar year.
    Uses the same collection convention as routes/awards.py eligibility."""
    day_start_iso = f"{year}-01-01T00:00:00+00:00"
    day_end_iso = f"{year + 1}-01-01T00:00:00+00:00"
    totals: dict = {}
    cursor = db.hours.find(
        {
            "status": "approved",
            "date": {"$gte": day_start_iso[:10], "$lt": day_end_iso[:10]},
        },
        {"_id": 0, "user_id": 1, "hours": 1},
    )
    async for h in cursor:
        uid = h.get("user_id")
        if not uid:
            continue
        try:
            n = float(h.get("hours") or 0)
        except (TypeError, ValueError):
            n = 0.0
        totals[uid] = totals.get(uid, 0.0) + n
    return totals


async def _sweep_community_service_ribbon(today: _date) -> int:
    """On Dec 31 each year, auto-grant every active member with ≥100 volunteer
    hours in that calendar year. No-op on other days."""
    if (today.month, today.day) != (12, 31):
        return 0
    award = await _find_award("Community Service Ribbon")
    if not award:
        logger.warning("[auto-grant] Community Service Ribbon award not found — skipping annual sweep")
        return 0
    year = today.year
    totals = await _hours_by_user_for_year(year)
    if not totals:
        return 0
    granted = 0
    for uid, hrs in totals.items():
        if hrs < 100.0:
            continue
        u = await db.users.find_one(
            {"id": uid, "status_override": {"$nin": ["inactive", "deceased"]}},
            {"_id": 0, "id": 1, "name": 1},
        )
        if not u:
            continue
        reason = f"Auto-granted for {round(hrs, 2)} volunteer hours in {year}"
        doc = await _grant(
            award=award,
            user=u,
            kind=AUTO_GRANT_KIND_COMMUNITY,
            reason=reason,
            granted_at_iso=iso(now_utc()),
            dedupe_query={
                "user_id": uid,
                "award_id": award["id"],
                "auto_grant_kind": AUTO_GRANT_KIND_COMMUNITY,
                "reason": {"$regex": f"in {year}$"},
            },
        )
        if doc:
            granted += 1
    return granted


# ============================================================
# Daily loop entrypoint
# ============================================================
async def run_daily_sweeps() -> dict:
    """Executes all auto-grant sweeps once. Returns a summary dict for logs +
    manual admin trigger endpoint. Safe to call multiple times per day
    (dedupe guarantees idempotency)."""
    today = now_utc().date()
    service_ct = await _sweep_service_ribbon(today)
    community_ct = await _sweep_community_service_ribbon(today)
    summary = {
        "date": today.isoformat(),
        "service_ribbon_granted": service_ct,
        "community_service_ribbon_granted": community_ct,
    }
    if service_ct or community_ct:
        logger.info(f"[auto-grant] daily sweep summary: {summary}")
    return summary


async def auto_grant_daily_loop():
    """Background task — runs the sweeps once per hour. The sweeps themselves
    are cheap and idempotent, so a low-frequency schedule is fine, but we
    run hourly to keep the "on the actual anniversary date" promise as
    tight as possible regardless of the container's UTC boot time."""
    # Small initial delay so we don't collide with the startup seed hooks.
    await asyncio.sleep(30)
    while True:
        try:
            await run_daily_sweeps()
        except Exception as e:
            logger.warning(f"[auto-grant] daily loop error: {e}")
        await asyncio.sleep(3600)  # hourly
