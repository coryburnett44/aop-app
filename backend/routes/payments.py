"""Payments + transactions routes.

Covers:
  - Manual admin transaction logging.
  - Zeffy dues integration (confirmation-on-return + auto-approve for trusted members).
  - Admin transaction list / delete.
  - Member "my transactions" feed.

PayPal capture routes still live in server.py (they touch many other helpers).

Registered via `register(api, **deps)` from server.py at module-load time.
"""
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from models import TransactionIn


# ---------- Zeffy receipt format detection ----------
# Known Zeffy receipt formats (per Zeffy support docs):
#   - "RCT-XXXX-XXXX"  (canonical Zeffy receipt number, e.g. RCT-0401-5406)
#   - "ZF-XXXXXX"      (Zeffy transaction reference, legacy)
#   - donor confirmation email address
#   - raw alphanumeric transaction id (10+ chars, mixed case, no spaces)
ZEFFY_RECEIPT_PATTERNS = (
    ("rct", re.compile(r"^RCT[-_ ]?\d{3,5}[-_ ]?\d{3,6}$", re.IGNORECASE)),
    ("zf",  re.compile(r"^ZF[-_ ]?[A-Z0-9]{6,}$", re.IGNORECASE)),
    ("email", re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")),
    ("alnum", re.compile(r"^[A-Z0-9]{10,40}$")),
)


def classify_zeffy_receipt(s: str) -> Optional[str]:
    """Return matched format key ('rct'|'zf'|'email'|'alnum') or None."""
    s = (s or "").strip()
    if len(s) < 6 or len(s) > 200:
        return None
    if " " in s and "@" not in s:
        return None
    for key, pat in ZEFFY_RECEIPT_PATTERNS:
        if pat.match(s):
            return key
    return None


def tx_out(t: dict) -> dict:
    return {
        "id": t["id"],
        "user_id": t["user_id"],
        "user_name": t.get("user_name", ""),
        "type": t.get("type", "fee"),
        "amount": t.get("amount", 0.0),
        "currency": t.get("currency", "USD"),
        "description": t.get("description", ""),
        "status": t.get("status", "completed"),
        "recorded_by": t.get("recorded_by"),
        "recorded_by_name": t.get("recorded_by_name", ""),
        "created_at": t.get("created_at"),
        "provider": t.get("provider"),
        "purpose": t.get("purpose"),
        "event_id": t.get("event_id"),
        "event_title": t.get("event_title", ""),
        "rsvp_id": t.get("rsvp_id"),
        "zeffy_confirmation": t.get("zeffy_confirmation"),
        "zeffy_receipt_format": t.get("zeffy_receipt_format"),
        "zeffy_auto_approved": bool(t.get("zeffy_auto_approved")),
        "approved_at": t.get("approved_at"),
        "approved_by": t.get("approved_by"),
        "approved_by_name": t.get("approved_by_name"),
    }


class ZeffyConfirmIn(BaseModel):
    confirmation: str = Field(min_length=2, max_length=200)
    amount: Optional[float] = Field(105.0, ge=1, le=10000)


ZEFFY_DUES_URL = os.environ.get(
    "ZEFFY_DUES_URL",
    "https://www.zeffy.com/en-US/ticketing/national-yearly-dues",
)


def register(api, *, db, get_current_user, require_admin, is_chapter_scoped, chapter_scope_user_ids, iso, now_utc):
    """Wire payments/transactions routes onto the given api router."""

    # ---------- Manual admin transaction logging ----------
    @api.post("/transactions")
    async def admin_create_transaction(body: TransactionIn, admin: dict = Depends(require_admin)):
        user = await db.users.find_one({"id": body.user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="Member not found")
        doc = body.model_dump()
        doc.update({
            "id": str(uuid.uuid4()),
            "user_name": user.get("name", ""),
            "recorded_by": admin["id"],
            "recorded_by_name": admin.get("name", "Admin"),
            "created_at": iso(now_utc()),
        })
        await db.transactions.insert_one(doc)
        return tx_out(doc)

    # ---------- Zeffy dues integration ----------
    @api.get("/payments/zeffy/config")
    async def zeffy_config(user: dict = Depends(get_current_user)):
        """Return the Zeffy dues URL + display config."""
        return {
            "url": ZEFFY_DUES_URL,
            "currency": "USD",
            "default_amount": 105.0,
            "enabled": True,
        }

    @api.get("/payments/zeffy/validate")
    async def zeffy_validate_receipt(value: str, user: dict = Depends(get_current_user)):
        """Live-validate a Zeffy receipt/confirmation string. Returns format
        classification + whether this user would be auto-approved on submit."""
        fmt = classify_zeffy_receipt(value or "")
        label_map = {
            "rct": "Zeffy receipt number (RCT-XXXX-XXXX)",
            "zf": "Zeffy reference (ZF-XXXXXX)",
            "email": "Donor confirmation email",
            "alnum": "Zeffy transaction id",
        }
        return {
            "valid": fmt is not None,
            "format": fmt,
            "label": label_map.get(fmt or "", "Unrecognised — admin will verify manually"),
            "trusted": bool(user.get("trust_zeffy")),
            "will_auto_approve": bool(user.get("trust_zeffy")) and fmt is not None,
        }

    @api.post("/payments/zeffy/confirm")
    async def zeffy_confirm(body: ZeffyConfirmIn, user: dict = Depends(get_current_user)):
        """Member confirms they completed a Zeffy dues payment.

        Default → PENDING transaction (admin must approve).
        If `trust_zeffy=true` on the user AND the confirmation string matches a known
        Zeffy receipt pattern → auto-approve + extend membership 365 days immediately.
        """
        tx_id = str(uuid.uuid4())
        confirmation = (body.confirmation or "").strip()
        receipt_format = classify_zeffy_receipt(confirmation)
        pattern_ok = receipt_format is not None
        auto_approve = bool(user.get("trust_zeffy")) and pattern_ok

        doc = {
            "id": tx_id,
            "user_id": user["id"],
            "user_name": user.get("name", ""),
            "type": "renewal",
            "amount": float(body.amount or 105.0),
            "currency": "USD",
            "description": f"Annual dues via Zeffy (ref: {confirmation})",
            "status": "completed" if auto_approve else "pending",
            "purpose": "dues",
            "provider": "zeffy",
            "zeffy_confirmation": confirmation,
            "zeffy_receipt_format": receipt_format,
            "zeffy_auto_approved": auto_approve,
            "created_at": iso(now_utc()),
        }
        if auto_approve:
            doc["approved_at"] = iso(now_utc())
            doc["approved_by"] = "system:zeffy-trust"
            doc["approved_by_name"] = "Auto-approval (trusted member)"
        await db.transactions.insert_one(doc)

        if auto_approve:
            cur = user.get("membership_expires_at")
            try:
                base = datetime.fromisoformat(cur) if cur else now_utc()
            except Exception:
                base = now_utc()
            if base < now_utc():
                base = now_utc()
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"membership_expires_at": iso(base + timedelta(days=365))}},
            )
            return {
                "transaction_id": tx_id,
                "status": "completed",
                "auto_approved": True,
                "message": "🎉 Auto-approved — your annual dues are paid and your membership is extended 365 days.",
            }

        return {
            "transaction_id": tx_id,
            "status": "pending",
            "auto_approved": False,
            "message": "Submitted for admin verification — your dues will be marked paid once approved.",
        }

    @api.put("/transactions/{tx_id}/approve-zeffy")
    async def admin_approve_zeffy(tx_id: str, admin: dict = Depends(require_admin)):
        """Admin approves a pending Zeffy dues transaction → extends user membership 365 days."""
        tx = await db.transactions.find_one({"id": tx_id})
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")
        if tx.get("provider") != "zeffy":
            raise HTTPException(status_code=400, detail="Not a Zeffy transaction")
        if tx.get("status") == "completed":
            return {"ok": True, "already": True}
        await db.transactions.update_one({"id": tx_id}, {"$set": {
            "status": "completed",
            "approved_at": iso(now_utc()),
            "approved_by": admin["id"],
            "approved_by_name": admin.get("name", "Admin"),
        }})
        if tx.get("purpose") == "dues":
            u = await db.users.find_one({"id": tx["user_id"]})
            if u:
                cur = u.get("membership_expires_at")
                try:
                    base = datetime.fromisoformat(cur) if cur else now_utc()
                except Exception:
                    base = now_utc()
                if base < now_utc():
                    base = now_utc()
                await db.users.update_one(
                    {"id": tx["user_id"]},
                    {"$set": {"membership_expires_at": iso(base + timedelta(days=365))}},
                )
        return {"ok": True}

    # ---------- Transaction list / delete / member feed ----------
    @api.get("/transactions")
    async def admin_list_transactions(user_id: Optional[str] = None, type_filter: Optional[str] = None, admin: dict = Depends(require_admin)):
        query = {}
        if user_id:
            query["user_id"] = user_id
        if type_filter:
            query["type"] = type_filter
        if is_chapter_scoped(admin):
            ids = await chapter_scope_user_ids(admin)
            query["user_id"] = {"$in": ids or []}
        cursor = db.transactions.find(query, {"_id": 0}).sort("created_at", -1).limit(500)
        items = await cursor.to_list(500)
        return [tx_out(t) for t in items]

    @api.delete("/transactions/{tx_id}")
    async def admin_delete_transaction(tx_id: str, _: dict = Depends(require_admin)):
        res = await db.transactions.delete_one({"id": tx_id})
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        return {"ok": True}

    @api.get("/me/transactions")
    async def my_transactions(year: Optional[int] = None, user: dict = Depends(get_current_user)):
        """A member's own transaction history. Optional `year` filter narrows
        to a single calendar year (created_at) for the receipts page picker;
        leave unset for all years."""
        q: dict = {"user_id": user["id"]}
        if year:
            q["created_at"] = {"$gte": f"{year}-01-01T00:00:00", "$lte": f"{year}-12-31T23:59:59"}
        cursor = db.transactions.find(q, {"_id": 0}).sort("created_at", -1).limit(500)
        items = await cursor.to_list(500)
        return [tx_out(t) for t in items]
