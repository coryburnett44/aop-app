"""Admin member CRUD + bulk import — extracted from server.py.

Endpoints (paths preserved verbatim):
  POST   /api/admin/members                                     create
  POST   /api/admin/members/bulk-import                         CSV bulk import
  GET    /api/admin/members/bulk-import/template                CSV template download
  POST   /api/admin/members/{user_id}/resend-set-password       single resend
  POST   /api/admin/members/bulk-resend-set-password            bulk resend
  PUT    /api/members/{user_id}                                 update
  DELETE /api/members/{user_id}                                 hard-delete + cascade
  PUT    /api/members/{user_id}/role                            role change (full admin only)
  PUT    /api/members/{user_id}/chapter                         chapter assignment
  PUT    /api/members/{user_id}/tier                            tier assignment (full admin only)

Follows the same `register(api, **deps)` pattern used by `routes/automated_emails.py`
so server.py just imports + calls register() at the bottom.
"""
import csv as _csv
import io as _io
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from dateutil import parser as _date_parser
from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response as FastResponse

from models import (
    AdminCreateMemberIn,
    AdminUpdateMemberIn,
    AssignChapterIn,
    AssignTierIn,
    RoleUpdateIn,
)


# ---------- CSV bulk-import helpers ----------
_BULK_COLUMN_ALIASES = {
    "email": ["email", "e-mail", "email address"],
    "title": ["title", "salutation", "honorific"],
    "first_name": ["first name", "firstname", "first", "given name"],
    "middle_name": ["middle name", "middlename", "middle"],
    "last_name": ["last name", "lastname", "last", "surname", "family name"],
    "phone": ["phone", "telephone", "mobile", "cell", "phone number"],
    "address": ["address", "street", "address line 1", "street address"],
    "city": ["city", "town"],
    "state": ["state", "province", "region"],
    "zip_code": ["zip", "zip code", "zipcode", "postal code", "postcode"],
    "country": ["country"],
    "birthdate": ["birthdate", "birth date", "date of birth", "dob"],
    "branch_of_service": ["branch of service", "military branch", "branch", "service branch"],
    "renewal_date": ["renewal date", "renewal", "expires", "expiration", "membership expires", "renew on"],
    "join_date": ["join date", "joined", "member since", "join", "membership start"],
    "line_name": ["line name", "line"],
    "intake_line": ["intake line"],
    "intake_completed_at": ["intake completed at", "intake date", "intake completed", "crossed"],
    "username": ["username", "user name", "screen name"],
    "chapter": ["chapter", "chapter name"],
}

_TITLE_VALID = {"Mr.", "Mrs.", "Ms.", "Miss", "Dr.", "Prof.", "Rev.", "Hon.", "Mx."}


def _normalize_header(h: str) -> str:
    return (h or "").strip().lower().replace("_", " ")


def _map_row(row: dict) -> dict:
    out: dict = {}
    norm = {_normalize_header(k): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
    for canonical, aliases in _BULK_COLUMN_ALIASES.items():
        for a in aliases:
            if a in norm and norm[a]:
                out[canonical] = norm[a]
                break
    return out


def _parse_date(s: str):
    if not s:
        return None
    try:
        dt = _date_parser.parse(str(s))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _normalize_title(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip().rstrip(".")
    candidates = {t.rstrip("."): t for t in _TITLE_VALID}
    return candidates.get(s, candidates.get(s.title(), ""))


def register(
    api,
    *,
    db,
    iso,
    now_utc,
    logger,
    admin_tab_dep,
    admin_role_of,
    hash_password,
    public_user,
    all_admin_tabs,
    send_welcome_email,
    send_set_password_email,
    resend_api_key_getter,
):
    """Wire all member-admin endpoints. `resend_api_key_getter` is a callable
    (so the test/runtime can swap the key at run-time without re-registering)."""

    @api.post("/admin/members")
    async def admin_create_member(body: AdminCreateMemberIn, _: dict = Depends(admin_tab_dep("members"))):
        email = body.email.lower()
        if await db.users.find_one({"email": email}):
            raise HTTPException(status_code=400, detail="Email already registered")
        if body.username and await db.users.find_one({"username": body.username}):
            raise HTTPException(status_code=400, detail="Username already taken")
        uid = str(uuid.uuid4())
        created = now_utc()
        composed_name = body.name or " ".join(
            p for p in [body.first_name, body.middle_name, body.last_name] if p
        ).strip() or email.split("@")[0]
        join_dt = body.join_date or created
        if isinstance(join_dt, datetime):
            join_iso = iso(join_dt)
            exp_iso = iso(join_dt + timedelta(days=365))
        else:
            join_iso = iso(created)
            exp_iso = iso(created + timedelta(days=365))
        doc = {
            "id": uid,
            "email": email,
            "username": body.username,
            "password_hash": hash_password(body.password),
            "name": composed_name,
            "title": body.title or "",
            "first_name": body.first_name,
            "middle_name": body.middle_name,
            "last_name": body.last_name,
            "line_name": body.line_name,
            "intake_line": body.intake_line,
            "intake_completed_at": body.intake_completed_at,
            "phone": body.phone,
            "address": body.address,
            "state": body.state,
            "zip_code": body.zip_code,
            "country": body.country,
            "birthdate": body.birthdate,
            "branch_of_service": body.branch_of_service,
            "role": body.role,
            "bio": "",
            "city": body.city,
            "interests": [],
            "avatar_url": "",
            "membership_tier": "standard",
            "tier_id": body.tier_id,
            "chapter_id": body.chapter_id,
            "status_override": body.member_status,
            "admin_role": (body.admin_role or "full") if body.role == "admin" else None,
            "allowed_tabs": [t for t in (body.allowed_tabs or []) if t in all_admin_tabs] if body.role == "admin" else [],
            "join_date": join_iso,
            "membership_expires_at": exp_iso,
            "email_verified": True,
            "created_at": iso(created),
        }
        if body.tier_id:
            tier = await db.tiers.find_one({"id": body.tier_id}, {"_id": 0})
            if tier:
                doc["membership_tier"] = tier.get("name", "standard")
                doc["is_lifetime_member"] = bool(tier.get("is_lifetime"))
                if tier.get("is_lifetime"):
                    doc["membership_expires_at"] = None
        await db.users.insert_one(doc)
        # Iter 120: auto-grant Alpha Omega Phi Ribbon on join.
        try:
            from routes import awards_auto as _aa  # local import to avoid cycles
            await _aa.grant_alpha_omega_phi_ribbon_on_join(doc)
        except Exception as _e:
            logger.warning(f"[auto-grant] on admin create failed for {email}: {_e}")
        try:
            await send_welcome_email(email, composed_name, body.password)
        except Exception as e:
            logger.warning(f"welcome email failed for {email}: {e}")
        return public_user(doc)

    @api.post("/admin/members/bulk-import")
    async def admin_bulk_import_members(
        file: UploadFile = File(...),
        default_chapter_id: str = Form(None),
        dry_run: bool = Form(False),
        send_set_password_emails: bool = Form(True),
        admin: dict = Depends(admin_tab_dep("members")),
    ):
        """Bulk-import members from a CSV (e.g. exported from ClubExpress)."""
        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Please upload a .csv file")
        raw = await file.read()
        if len(raw) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="CSV too large (max 5 MB)")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")

        reader = _csv.DictReader(_io.StringIO(text))
        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV has no header row")

        chapters_list = await db.chapters.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
        chapters_by_name = {(c.get("name") or "").lower().strip(): c["id"] for c in chapters_list}

        results = {"created": [], "skipped": [], "errors": [], "total": 0}
        now = now_utc()
        resend_api_key = resend_api_key_getter()

        for idx, raw_row in enumerate(reader, start=2):
            results["total"] += 1
            row = _map_row(raw_row)
            email = (row.get("email") or "").lower().strip()
            if not email or "@" not in email:
                results["errors"].append({"row": idx, "email": email, "reason": "missing or invalid email"})
                continue
            if await db.users.find_one({"email": email}):
                results["skipped"].append({"row": idx, "email": email, "reason": "email already exists"})
                continue

            first = row.get("first_name", "")
            last = row.get("last_name", "")
            middle = row.get("middle_name", "")
            title = _normalize_title(row.get("title", ""))
            composed_name = " ".join(p for p in [first, middle, last] if p).strip() or email.split("@")[0]

            chapter_id = default_chapter_id
            ch_raw = (row.get("chapter") or "").lower().strip()
            if ch_raw and ch_raw in chapters_by_name:
                chapter_id = chapters_by_name[ch_raw]

            renewal_dt = _parse_date(row.get("renewal_date", ""))
            join_dt = _parse_date(row.get("join_date", "")) or now
            expires_dt = (renewal_dt + timedelta(days=365)) if renewal_dt else (now + timedelta(days=365))
            birth_dt = _parse_date(row.get("birthdate", ""))

            if dry_run:
                results["created"].append({
                    "row": idx,
                    "email": email,
                    "name": composed_name,
                    "membership_expires_at": iso(expires_dt),
                    "chapter_id": chapter_id,
                })
                continue

            temp_password = secrets.token_urlsafe(18)
            uid = str(uuid.uuid4())
            doc = {
                "id": uid,
                "email": email,
                "username": row.get("username", ""),
                "password_hash": hash_password(temp_password),
                "name": composed_name,
                "title": title,
                "first_name": first,
                "middle_name": middle,
                "last_name": last,
                "line_name": row.get("line_name", ""),
                "intake_line": row.get("intake_line", ""),
                "intake_completed_at": row.get("intake_completed_at", ""),
                "phone": row.get("phone", ""),
                "address": row.get("address", ""),
                "city": row.get("city", ""),
                "state": row.get("state", ""),
                "zip_code": row.get("zip_code", ""),
                "country": row.get("country", ""),
                "birthdate": iso(birth_dt) if birth_dt else "",
                "branch_of_service": row.get("branch_of_service", ""),
                "role": "member",
                "bio": "",
                "interests": [],
                "avatar_url": "",
                "membership_tier": "standard",
                "chapter_id": chapter_id,
                "join_date": iso(join_dt),
                "membership_expires_at": iso(expires_dt),
                "email_verified": True,
                "pending_set_password": True,
                "imported_from": "clubexpress_csv",
                "imported_at": iso(now),
                "created_at": iso(now),
            }
            try:
                await db.users.insert_one(doc)
                # Iter 120: auto-grant Alpha Omega Phi Ribbon on join for
                # bulk-imported members too — they're joining today.
                try:
                    from routes import awards_auto as _aa
                    await _aa.grant_alpha_omega_phi_ribbon_on_join(doc)
                except Exception:
                    pass
                row_result = {
                    "row": idx,
                    "email": email,
                    "name": composed_name,
                    "membership_expires_at": iso(expires_dt),
                }
                if send_set_password_emails and resend_api_key:
                    try:
                        token = secrets.token_urlsafe(32)
                        expires_at = now + timedelta(days=7)
                        await db.password_set_tokens.insert_one({
                            "token": token,
                            "user_id": uid,
                            "expires_at": iso(expires_at),
                            "expires_at_dt": expires_at,
                            "used": False,
                            "created_at": iso(now),
                        })
                        sent = await send_set_password_email(email, composed_name, token)
                        row_result["set_password_email_sent"] = bool(sent)
                    except Exception as ex_email:
                        row_result["set_password_email_sent"] = False
                        logger.warning(f"[bulk-import] set-password email failed for {email}: {ex_email}")
                else:
                    row_result["set_password_email_sent"] = False
                results["created"].append(row_result)
            except Exception as ex:
                results["errors"].append({"row": idx, "email": email, "reason": f"insert failed: {ex}"})

        results["created_count"] = len(results["created"])
        results["skipped_count"] = len(results["skipped"])
        results["error_count"] = len(results["errors"])
        results["dry_run"] = bool(dry_run)
        results["emails_sent_count"] = sum(1 for r in results["created"] if r.get("set_password_email_sent"))
        logger.info(
            f"[bulk-import] admin={admin.get('email')} created={results['created_count']} "
            f"skipped={results['skipped_count']} errors={results['error_count']} "
            f"emails={results['emails_sent_count']} dry_run={dry_run}"
        )
        return results

    @api.get("/admin/members/bulk-import/template")
    async def admin_bulk_import_template(_: dict = Depends(admin_tab_dep("members"))):
        headers = [
            "Email", "Title", "First Name", "Middle Name", "Last Name", "Username",
            "Phone", "Address", "City", "State", "Zip Code", "Country",
            "Birthdate", "Branch of Service",
            "Renewal Date", "Join Date",
            "Line Name", "Intake Line", "Intake Completed At",
            "Chapter",
        ]
        example = [
            "jane.doe@example.com", "Ms.", "Jane", "", "Doe", "janed",
            "555-123-4567", "123 Main St", "Houston", "TX", "77001", "USA",
            "1985-04-12", "Army",
            "2026-01-15", "2020-01-15",
            "Theta-3", "Spring 2020", "2020-06-01",
            "Texas",
        ]
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(headers)
        w.writerow(example)
        return FastResponse(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=aop-bulk-import-template.csv"},
        )

    @api.post("/admin/members/{user_id}/resend-set-password")
    async def admin_resend_set_password(user_id: str, admin: dict = Depends(admin_tab_dep("members"))):
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="Member not found")
        if not user.get("email"):
            raise HTTPException(status_code=400, detail="Member has no email on file")
        if not resend_api_key_getter():
            raise HTTPException(status_code=503, detail="Email service not configured on the server (RESEND_API_KEY missing).")
        now = now_utc()
        token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(days=7)
        await db.password_set_tokens.update_many(
            {"user_id": user_id, "used": False},
            {"$set": {"used": True, "used_at": iso(now), "invalidated_by": "resend"}},
        )
        await db.password_set_tokens.insert_one({
            "token": token,
            "user_id": user_id,
            "expires_at": iso(expires_at),
            "expires_at_dt": expires_at,
            "used": False,
            "created_at": iso(now),
        })
        await db.users.update_one({"id": user_id}, {"$set": {"pending_set_password": True}})
        name = user.get("name") or user.get("first_name") or user.get("email")
        sent = await send_set_password_email(user["email"], name, token)
        logger.info(f"[resend-set-password] admin={admin.get('email')} user={user.get('email')} sent={sent}")
        await db.password_setup_attempts.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "user_name": user.get("name", ""),
            "email": user["email"],
            "ok": bool(sent),
            "reason": "" if sent else "Resend API rejected or no API key configured",
            "mode": "single",
            "admin_id": admin.get("id"),
            "admin_name": admin.get("name", ""),
            "attempted_at": iso(now),
            "attempted_at_dt": now,
        })
        return {"ok": True, "sent": bool(sent), "email": user["email"]}

    @api.post("/admin/members/bulk-resend-set-password")
    async def admin_bulk_resend_set_password(admin: dict = Depends(admin_tab_dep("members"))):
        if not resend_api_key_getter():
            raise HTTPException(status_code=503, detail="Email service not configured on the server (RESEND_API_KEY missing).")
        cursor = db.users.find({"pending_set_password": True}, {"_id": 0})
        pending = await cursor.to_list(500)
        now = now_utc()
        summary = {"ok": True, "total": len(pending), "sent": 0, "failed": 0, "skipped_no_email": 0, "members": []}
        attempt_logs: list[dict] = []
        for user in pending:
            email = (user.get("email") or "").strip()
            uid = user.get("id")
            if not email:
                summary["skipped_no_email"] += 1
                summary["members"].append({"id": uid, "name": user.get("name", ""), "email": "", "sent": False, "skipped": True})
                attempt_logs.append({
                    "id": str(uuid.uuid4()),
                    "user_id": uid,
                    "user_name": user.get("name", ""),
                    "email": "",
                    "ok": False,
                    "reason": "Member has no email address on file",
                    "mode": "bulk",
                    "admin_id": admin.get("id"),
                    "admin_name": admin.get("name", ""),
                    "attempted_at": iso(now),
                    "attempted_at_dt": now,
                })
                continue
            token = secrets.token_urlsafe(32)
            expires_at = now + timedelta(days=7)
            try:
                await db.password_set_tokens.update_many(
                    {"user_id": uid, "used": False},
                    {"$set": {"used": True, "used_at": iso(now), "invalidated_by": "bulk-resend"}},
                )
                await db.password_set_tokens.insert_one({
                    "token": token,
                    "user_id": uid,
                    "expires_at": iso(expires_at),
                    "expires_at_dt": expires_at,
                    "used": False,
                    "created_at": iso(now),
                })
                name = user.get("name") or user.get("first_name") or email
                sent = await send_set_password_email(email, name, token)
                if sent:
                    summary["sent"] += 1
                else:
                    summary["failed"] += 1
                summary["members"].append({"id": uid, "name": user.get("name", ""), "email": email, "sent": bool(sent)})
                attempt_logs.append({
                    "id": str(uuid.uuid4()),
                    "user_id": uid,
                    "user_name": user.get("name", ""),
                    "email": email,
                    "ok": bool(sent),
                    "reason": "" if sent else "Resend API rejected or no API key configured",
                    "mode": "bulk",
                    "admin_id": admin.get("id"),
                    "admin_name": admin.get("name", ""),
                    "attempted_at": iso(now),
                    "attempted_at_dt": now,
                })
            except Exception as ex:
                summary["failed"] += 1
                summary["members"].append({"id": uid, "name": user.get("name", ""), "email": email, "sent": False, "error": str(ex)})
                attempt_logs.append({
                    "id": str(uuid.uuid4()),
                    "user_id": uid,
                    "user_name": user.get("name", ""),
                    "email": email,
                    "ok": False,
                    "reason": str(ex)[:300],
                    "mode": "bulk",
                    "admin_id": admin.get("id"),
                    "admin_name": admin.get("name", ""),
                    "attempted_at": iso(now),
                    "attempted_at_dt": now,
                })
                logger.warning(f"[bulk-resend-setpw] failed for {email}: {ex}")
        if attempt_logs:
            await db.password_setup_attempts.insert_many(attempt_logs)
        logger.info(
            f"[bulk-resend-setpw] admin={admin.get('email')} total={summary['total']} "
            f"sent={summary['sent']} failed={summary['failed']} skipped_no_email={summary['skipped_no_email']}"
        )
        return summary

    @api.put("/members/{user_id}")
    async def admin_update_member(user_id: str, body: AdminUpdateMemberIn, admin: dict = Depends(admin_tab_dep("members"))):
        existing = await db.users.find_one({"id": user_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Member not found")
        expires_changing = body.membership_expires_at is not None and (
            iso(body.membership_expires_at) != (existing.get("membership_expires_at") or "")
        )
        tabs_changing = body.allowed_tabs is not None and (
            list(body.allowed_tabs) != list(existing.get("allowed_tabs") or [])
        )
        if (
            (body.role is not None and body.role != existing.get("role"))
            or (body.admin_role is not None and body.admin_role != existing.get("admin_role"))
            or (body.tier_id is not None and body.tier_id != existing.get("tier_id"))
            or expires_changing
            or tabs_changing
        ):
            if admin_role_of(admin) != "full":
                raise HTTPException(status_code=403, detail="Only full Admins may change roles, tiers, custom tab permissions, or the membership expiration date.")
        if body.allowed_tabs is not None:
            body.allowed_tabs = sorted({t for t in body.allowed_tabs if t in all_admin_tabs})
        updates = {k: v for k, v in body.model_dump().items() if v is not None and k not in ("new_password", "member_status")}
        if body.role == "member" and existing.get("role") == "admin":
            updates["admin_role"] = None
            updates["allowed_tabs"] = []
        if body.member_status is not None:
            updates["status_override"] = body.member_status
            if body.member_status == "deceased" and not (body.deceased_at or existing.get("deceased_at")):
                updates["deceased_at"] = iso(now_utc())
            if body.member_status != "deceased" and existing.get("deceased_at") and not body.deceased_at:
                updates["deceased_at"] = None
            # Iter 111: Append to the member's status_history so we can compute
            # continuous-active streaks for Service Ribbon eligibility.
            if body.member_status != existing.get("status_override"):
                history = list(existing.get("status_history") or [])
                history.append({
                    "status": body.member_status,
                    "at": iso(now_utc()),
                    "by": admin.get("id"),
                    "by_name": admin.get("name", "Admin"),
                })
                updates["status_history"] = history
        if "username" in updates and updates["username"]:
            clash = await db.users.find_one({"username": updates["username"], "id": {"$ne": user_id}})
            if clash:
                raise HTTPException(status_code=400, detail="Username already taken")
        if "email" in updates and updates["email"]:
            updates["email"] = updates["email"].lower()
            clash = await db.users.find_one({"email": updates["email"], "id": {"$ne": user_id}})
            if clash:
                raise HTTPException(status_code=400, detail="Email already registered")
        if any(k in updates for k in ("first_name", "middle_name", "last_name")) and "name" not in updates:
            parts = [
                updates.get("first_name", existing.get("first_name", "")),
                updates.get("middle_name", existing.get("middle_name", "")),
                updates.get("last_name", existing.get("last_name", "")),
            ]
            composed = " ".join(p for p in parts if p).strip()
            if composed:
                updates["name"] = composed
        if "tier_id" in updates and updates["tier_id"]:
            tier = await db.tiers.find_one({"id": updates["tier_id"]}, {"_id": 0})
            if tier:
                updates["membership_tier"] = tier.get("name", "standard")
                updates["is_lifetime_member"] = bool(tier.get("is_lifetime"))
                if tier.get("is_lifetime"):
                    updates["membership_expires_at"] = None
        if "membership_expires_at" in updates and isinstance(updates["membership_expires_at"], datetime):
            updates["membership_expires_at"] = iso(updates["membership_expires_at"])
        if "join_date" in updates and isinstance(updates["join_date"], datetime):
            jd = updates["join_date"]
            updates["join_date"] = iso(jd)
            if "membership_expires_at" not in updates:
                updates["membership_expires_at"] = iso(jd + timedelta(days=365))
        if body.new_password:
            updates["password_hash"] = hash_password(body.new_password)
            updates["pending_set_password"] = False
        if updates:
            await db.users.update_one({"id": user_id}, {"$set": updates})
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        return public_user(u)

    @api.delete("/members/{user_id}")
    async def admin_delete_member(user_id: str, admin: dict = Depends(admin_tab_dep("members"))):
        """Hard-delete personal data; soft-delete chat messages so other group
        members still see context (sender shown as 'Deleted Member'); KEEP PayPal
        transactions for accounting but anonymize the linked user_name."""
        if user_id == admin["id"]:
            raise HTTPException(status_code=400, detail="Cannot delete yourself")
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "name": 1, "email": 1})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        deleted_name = "Deleted Member"
        await db.users.delete_one({"id": user_id})
        await db.rsvps.delete_many({"user_id": user_id})
        await db.checkins.delete_many({"user_id": user_id})
        await db.volunteer_hours.delete_many({"user_id": user_id})
        await db.award_grants.delete_many({"user_id": user_id})
        await db.applications.delete_many({"email": (u.get("email") or "").lower()})
        await db.password_set_tokens.delete_many({"user_id": user_id})
        await db.password_reset_tokens.delete_many({"user_id": user_id})
        await db.photos.delete_many({"uploaded_by": user_id})
        await db.documents.delete_many({"uploaded_by": user_id})
        await db.photo_albums.delete_many({"created_by": user_id, "is_default": {"$ne": True}})
        await db.omega_tributes.delete_many({"user_id": user_id})
        await db.chat_notifications.delete_many({"recipient_id": user_id})
        await db.chat_messages.update_many(
            {"sender_id": user_id},
            {"$set": {"sender_name": deleted_name, "sender_avatar": "", "body": "(message removed — member deleted)", "attachments": [], "deleted_at": iso(now_utc())}},
        )
        await db.conversations.update_many({"member_ids": user_id}, {"$pull": {"member_ids": user_id}})
        await db.transactions.update_many({"user_id": user_id}, {"$set": {"user_name": deleted_name, "anonymized": True}})
        return {"ok": True, "deleted_user_id": user_id}

    @api.put("/members/{user_id}/role")
    async def update_member_role(user_id: str, body: RoleUpdateIn, admin: dict = Depends(admin_tab_dep("members"))):
        if admin_role_of(admin) != "full":
            raise HTTPException(status_code=403, detail="Only full Admins may change member roles")
        await db.users.update_one({"id": user_id}, {"$set": {"role": body.role}})
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        return public_user(u)

    @api.put("/members/{user_id}/chapter")
    async def assign_chapter(user_id: str, body: AssignChapterIn, _: dict = Depends(admin_tab_dep("members"))):
        update = {"chapter_id": body.chapter_id} if body.chapter_id else {"chapter_id": None}
        await db.users.update_one({"id": user_id}, {"$set": update})
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        return public_user(u)

    @api.put("/members/{user_id}/tier")
    async def assign_tier(user_id: str, body: AssignTierIn, admin: dict = Depends(admin_tab_dep("members"))):
        if admin_role_of(admin) != "full":
            raise HTTPException(status_code=403, detail="Only full Admins may change member tiers")
        updates: dict = {"tier_id": body.tier_id}
        is_lifetime = False
        if body.tier_id:
            tier = await db.tiers.find_one({"id": body.tier_id}, {"_id": 0})
            if tier:
                updates["membership_tier"] = tier.get("name", "standard")
                is_lifetime = bool(tier.get("is_lifetime"))
        updates["is_lifetime_member"] = is_lifetime
        if is_lifetime:
            updates["membership_expires_at"] = None
        else:
            u_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
            if u_doc and (u_doc.get("is_lifetime_member") or not u_doc.get("membership_expires_at")):
                base = now_utc()
                join_iso = u_doc.get("join_date")
                try:
                    if join_iso:
                        base = max(base, datetime.fromisoformat(join_iso))
                except Exception:
                    pass
                updates["membership_expires_at"] = iso(base + timedelta(days=365))
            if body.extend_days:
                u = await db.users.find_one({"id": user_id})
                if u:
                    cur = updates.get("membership_expires_at") or u.get("membership_expires_at")
                    try:
                        base = datetime.fromisoformat(cur) if cur else now_utc()
                    except Exception:
                        base = now_utc()
                    if base < now_utc():
                        base = now_utc()
                    updates["membership_expires_at"] = iso(base + timedelta(days=body.extend_days))
        await db.users.update_one({"id": user_id}, {"$set": updates})
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        return public_user(u)
