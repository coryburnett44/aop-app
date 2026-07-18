"""Automatic Birthday emails — Iter 133.

Sends a warm HAPPY BIRTHDAY email to every active member on their MM/DD
each year. Uses the existing `send_bulk_email` helper so we get the
List-Unsubscribe headers, CAN-SPAM footer, and org mailing address for
free.

Idempotency: for each (user_id, year, MM/DD) tuple we insert a doc into
`birthday_emails_sent` — the hourly loop is safe to fire multiple times a
day without spamming anyone.

Opt-outs respected:
  • `email_opt_out=True` skips the send entirely.
  • `email_prefs.blasts=False` also skips (birthdays are non-transactional).
  • Deceased members are always skipped.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date as _date
from typing import Optional


# ---------- Module-level injected state ----------
db = None
iso = None
now_utc = None
logger = None
send_bulk_email = None  # coroutine (to_email, subject, html_body, recipient_id, tags) → dict


def register(*, db_ref, iso_fn, now_utc_fn, logger_ref, send_bulk_email_fn):
    """Bind module-level state. Called once from server.py at startup."""
    g = globals()
    g["db"] = db_ref
    g["iso"] = iso_fn
    g["now_utc"] = now_utc_fn
    g["logger"] = logger_ref
    g["send_bulk_email"] = send_bulk_email_fn


# ============================================================
# Helpers
# ============================================================
def _parse_birthday(raw) -> Optional[tuple[int, int]]:
    """Return (month, day) or None. Accepts:
      • ISO strings: "1990-04-15" or "1990-04-15T00:00:00+00:00"
      • MM/DD or MM-DD (year-agnostic)
      • datetime / date objects."""
    if raw is None or raw == "":
        return None
    # Objects with month/day.
    if hasattr(raw, "month") and hasattr(raw, "day"):
        try:
            return int(raw.month), int(raw.day)
        except Exception:
            return None
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    # ISO date/datetime.
    try:
        dt = _date.fromisoformat(s[:10])
        return dt.month, dt.day
    except Exception:
        pass
    # MM/DD or MM-DD.
    for sep in ("/", "-"):
        if sep in s and len(s.split(sep)) >= 2:
            parts = s.split(sep)
            try:
                m = int(parts[0]); d = int(parts[1])
                if 1 <= m <= 12 and 1 <= d <= 31:
                    return m, d
            except Exception:
                pass
    return None


def _first_name(user: dict) -> str:
    fn = (user.get("first_name") or "").strip()
    if fn:
        return fn
    full = (user.get("name") or "").strip()
    if full:
        return full.split()[0]
    return "friend"


ORG_NAME = "Alpha Omega Phi Military Fraternity & Sorority, Inc."


def _render_birthday_email(user: dict) -> tuple[str, str]:
    """Returns (subject, html) — warm, on-brand. Kept as a single card so
    it renders nicely on every email client without CSS support."""
    name = _first_name(user)
    subject = f"Happy Birthday, {name}! 🎉"
    html = f"""
<div style="max-width:600px;margin:0 auto;padding:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a1a1a;line-height:1.6;">
  <div style="background:linear-gradient(135deg,#0A2463 0%,#3E5C99 100%);padding:32px 24px;text-align:center;color:#ffffff;border-radius:12px 12px 0 0;">
    <div style="font-size:14px;letter-spacing:2px;text-transform:uppercase;opacity:0.85;margin-bottom:8px;">Alpha Omega Phi</div>
    <div style="font-size:32px;font-weight:800;line-height:1.15;">Happy Birthday,<br/>{name}!</div>
    <div style="font-size:56px;margin-top:8px;">🎂🎉</div>
  </div>
  <div style="background:#ffffff;padding:28px 28px 24px;border:1px solid #e5e7eb;border-top:0;border-radius:0 0 12px 12px;">
    <p style="margin:0 0 14px;font-size:16px;">Dear {name},</p>
    <p style="margin:0 0 14px;font-size:15px;">
      On behalf of every brother and sister of <strong>{ORG_NAME}</strong>,
      we wish you a truly <strong>happy birthday</strong>. Today, the entire
      Alpha Omega Phi family celebrates <em>you</em> — your service, your
      commitment, and the light you bring to our community.
    </p>
    <p style="margin:0 0 14px;font-size:15px;">
      May the year ahead bring you good health, meaningful moments with the
      people you love, and every good thing you deserve. You are seen, you
      are valued, and you are family.
    </p>
    <div style="margin:22px 0;padding:16px 18px;background:#F5F6FA;border-left:4px solid #C8102E;border-radius:6px;">
      <div style="font-size:13px;letter-spacing:1px;text-transform:uppercase;color:#0A2463;font-weight:700;margin-bottom:4px;">From your AOP family</div>
      <div style="font-size:15px;font-style:italic;">"Duty. Honor. Service. Family."</div>
    </div>
    <p style="margin:0 0 6px;font-size:15px;">Cheers to a fantastic year ahead, {name}. Enjoy every second of your day!</p>
    <p style="margin:18px 0 0;font-size:15px;">
      With love and camaraderie,<br/>
      <strong>The Alpha Omega Phi Family</strong>
    </p>
  </div>
</div>
""".strip()
    return subject, html


# ============================================================
# Daily sweep
# ============================================================
async def run_daily_birthday_sweep() -> dict:
    """Send today's birthday emails. Returns a summary dict for logs."""
    if db is None or send_bulk_email is None:
        return {"skipped": "birthday_emails not registered"}
    today = now_utc().date()
    today_key = today.strftime("%m-%d")
    year = today.year

    # We scan the whole user set — it's cheap enough (few thousand rows)
    # and the alternative (a MongoDB $expr on month+day) needs an aggregation
    # against a stored ISO string. Filter down here in Python.
    cursor = db.users.find(
        {"status": {"$ne": "inactive"}},
        {"_id": 0, "password_hash": 0},
    )
    users = await cursor.to_list(10000)

    checked = 0
    sent = 0
    skipped_optout = 0
    skipped_dedupe = 0
    errors = 0
    for u in users:
        md = _parse_birthday(u.get("birthdate") or u.get("birth_date"))
        if not md:
            continue
        month, day = md
        if (month, day) != (today.month, today.day):
            continue
        checked += 1

        # Deceased members: never email.
        if u.get("status_override") == "deceased" or u.get("deceased_at"):
            continue
        # Email opt-out or bulk-emails disabled → skip.
        if u.get("email_opt_out"):
            skipped_optout += 1
            continue
        prefs = u.get("email_prefs") or {}
        if prefs.get("blasts") is False:
            skipped_optout += 1
            continue
        to_email = (u.get("email") or "").strip()
        if not to_email:
            continue

        # Dedupe — one birthday email per member per calendar year.
        dedupe_key = f"{u['id']}:{year}:{today_key}"
        try:
            existing = await db.birthday_emails_sent.find_one({"key": dedupe_key})
        except Exception:
            existing = None
        if existing:
            skipped_dedupe += 1
            continue

        subject, html = _render_birthday_email(u)
        try:
            resp = await send_bulk_email(
                to_email=to_email,
                subject=subject,
                html_body=html,
                recipient_id=u["id"],
                tags=[{"name": "type", "value": "birthday"}],
            )
            if isinstance(resp, dict) and resp.get("skipped"):
                errors += 1
                logger.info(f"[birthday] send skipped for {to_email}: {resp.get('skipped')}")
                continue
            await db.birthday_emails_sent.insert_one({
                "id": str(uuid.uuid4()),
                "key": dedupe_key,
                "user_id": u["id"],
                "email": to_email,
                "sent_at": iso(now_utc()),
                "year": year,
                "mm_dd": today_key,
            })
            sent += 1
        except Exception as e:
            errors += 1
            logger.warning(f"[birthday] send failed for {to_email}: {e}")

    summary = {
        "date": today.isoformat(),
        "matched_today": checked,
        "sent": sent,
        "skipped_optout": skipped_optout,
        "skipped_already_sent": skipped_dedupe,
        "errors": errors,
    }
    if checked:
        logger.info(f"[birthday] daily sweep summary: {summary}")
    return summary


async def birthday_email_loop():
    """Background task — runs the birthday sweep once per hour. Cheap and
    idempotent (dedupe key ensures we send at most one email per member per
    year), so hourly cadence just tightens the "sent on their actual
    birthday" promise regardless of container boot time."""
    # Small initial delay so we don't collide with startup seed hooks.
    await asyncio.sleep(45)
    while True:
        try:
            await run_daily_birthday_sweep()
        except Exception as e:
            logger.warning(f"[birthday] loop error: {e}")
        await asyncio.sleep(3600)  # hourly


def register_routes(api, admin_tab_dep):
    """Mount the admin trigger + upcoming-birthdays endpoints. Called from
    server.py at startup after the module-level `register(...)` binding."""
    from fastapi import Depends, HTTPException

    @api.post("/admin/birthday-emails/sweep")
    async def trigger_birthday_sweep(_: dict = Depends(admin_tab_dep("email"))):
        """Manually run the birthday email sweep. Idempotent — a member who
        already got today's email won't get another. Handy for verifying
        the flow works after a Brevo key rotation."""
        if db is None or send_bulk_email is None:
            raise HTTPException(status_code=500, detail="Birthday module not initialized")
        return await run_daily_birthday_sweep()

    @api.get("/admin/birthday-emails/upcoming")
    async def upcoming_birthdays(days: int = 30, _: dict = Depends(admin_tab_dep("members"))):
        """List members with birthdays in the next N days so admins can
        preview who's on deck. Deceased members and members with no
        birthdate on file are excluded."""
        days = max(1, min(int(days or 30), 365))
        today = now_utc().date()
        cursor = db.users.find(
            {
                "status_override": {"$ne": "deceased"},
                "$or": [
                    {"birthdate": {"$nin": [None, ""]}},
                    {"birth_date": {"$nin": [None, ""]}},
                ],
            },
            {"_id": 0, "id": 1, "name": 1, "first_name": 1, "email": 1,
             "birthdate": 1, "birth_date": 1, "email_opt_out": 1, "email_prefs": 1,
             "status": 1},
        )
        users = await cursor.to_list(10000)
        upcoming = []
        for u in users:
            md = _parse_birthday(u.get("birthdate") or u.get("birth_date"))
            if not md:
                continue
            month, day = md
            # Compute the next occurrence.
            year = today.year
            try:
                nxt = _date(year, month, day)
            except ValueError:
                # Feb 29 on a non-leap year — bump forward a year.
                nxt = _date(year + 1, month, day) if month == 2 and day == 29 else None
            if nxt is None:
                continue
            if nxt < today:
                try:
                    nxt = _date(year + 1, month, day)
                except ValueError:
                    continue
            days_out = (nxt - today).days
            if days_out > days:
                continue
            already = False
            try:
                already = bool(
                    await db.birthday_emails_sent.find_one({
                        "user_id": u["id"], "year": nxt.year, "mm_dd": nxt.strftime("%m-%d"),
                    })
                )
            except Exception:
                already = False
            prefs = u.get("email_prefs") or {}
            upcoming.append({
                "user_id": u["id"],
                "name": u.get("name") or u.get("first_name") or "",
                "email": u.get("email") or "",
                "birthday": nxt.isoformat(),
                "days_until": days_out,
                "will_send": (not u.get("email_opt_out")) and (prefs.get("blasts") is not False) and bool(u.get("email")),
                "already_sent_this_year": already,
                "email_opt_out": bool(u.get("email_opt_out")),
            })
        upcoming.sort(key=lambda x: (x["days_until"], (x["name"] or "").lower()))
        return {"today": today.isoformat(), "window_days": days, "count": len(upcoming), "upcoming": upcoming}
