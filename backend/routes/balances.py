"""Outstanding-balance routes (10-year-anniversary fees, back dues, etc.).

The platform's primary dues lifecycle (`routes/payments.py`) is a single annual
charge whose payment auto-extends `membership_expires_at`. This module covers a
separate, admin-driven concept: per-member ad-hoc balances (anniversary fees,
back dues, late fees) that pay through a per-member Zeffy URL and do NOT
extend membership.

Storage shape (embedded on `users` for simplicity — small N, batched lookups):

  users.outstanding_zeffy_url: str          # per-member, admin-managed
  users.balance_lines: [
    {
      id:                str (uuid)
      label:             str    # admin-supplied "10-year anniversary fee" etc.
      amount:            float  # > 0
      created_at:        iso
      created_by:        admin id
      created_by_name:   str
      paid_at:           iso | None
      paid_via:          "admin_mark_paid" | "member_receipt" | None
      paid_tx_id:        str | None     # → transactions.id
      paid_by:           admin id | None
      paid_by_name:      str | None
    }, ...
  ]

`outstanding_balance_total` is always computed (never stored) as the sum of
amounts on unpaid lines. We keep paid lines on the user doc as history so
members can see what was settled.

Two confirmation flows (user explicitly asked for both):
  1) Admin marks a line paid directly (one click after reconciling Zeffy).
  2) Member submits a Zeffy receipt + selects which lines they paid → creates
     a PENDING transaction → admin approves it → lines get `paid_at`.

Membership is NEVER extended by these flows (per user requirement #5a).
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field


class _SetZeffyUrlIn(BaseModel):
    url: str = Field(default="", max_length=500)


class _BalanceLineIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=100000)


class _BalanceLineEditIn(BaseModel):
    label: Optional[str] = Field(default=None, max_length=200)
    amount: Optional[float] = Field(default=None, gt=0, le=100000)


class _SubmitReceiptIn(BaseModel):
    confirmation: str = Field(min_length=2, max_length=200)
    line_ids: List[str] = Field(default_factory=list)


def _outstanding_total(lines: list[dict]) -> float:
    return round(
        sum(float(ln.get("amount", 0)) for ln in (lines or []) if not ln.get("paid_at")),
        2,
    )


def _balance_payload(user_doc: dict) -> dict:
    """Shape returned by both admin and member GET endpoints."""
    lines = user_doc.get("balance_lines") or []
    return {
        "user_id": user_doc.get("id"),
        "user_name": user_doc.get("name", ""),
        "zeffy_url": user_doc.get("outstanding_zeffy_url", ""),
        "total": _outstanding_total(lines),
        # Members see all lines (paid history + unpaid current). Frontend
        # buckets them. Admins use the same shape so list components reuse.
        "lines": [
            {
                "id": ln.get("id"),
                "label": ln.get("label", ""),
                "amount": float(ln.get("amount", 0) or 0),
                "created_at": ln.get("created_at"),
                "created_by_name": ln.get("created_by_name", ""),
                "paid_at": ln.get("paid_at"),
                "paid_via": ln.get("paid_via"),
                "paid_tx_id": ln.get("paid_tx_id"),
                "paid_by_name": ln.get("paid_by_name"),
            }
            for ln in lines
        ],
    }


def register(api, *, db, get_current_user, admin_tab_dep, require_admin, iso, now_utc):
    """Wire all balance endpoints onto the given /api router."""

    # ---------- Admin: read ----------
    @api.get("/admin/members/{user_id}/balance")
    async def admin_get_balance(user_id: str, _: dict = Depends(admin_tab_dep("members"))):
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        return _balance_payload(u)

    # ---------- Admin: set Zeffy URL ----------
    @api.put("/admin/members/{user_id}/balance/zeffy-url")
    async def admin_set_zeffy_url(
        user_id: str,
        body: _SetZeffyUrlIn,
        _: dict = Depends(admin_tab_dep("members")),
    ):
        # Empty string clears the URL. When non-empty, require https for safety.
        url = (body.url or "").strip()
        if url and not url.lower().startswith("https://"):
            raise HTTPException(status_code=400, detail="Zeffy URL must start with https://")
        res = await db.users.update_one({"id": user_id}, {"$set": {"outstanding_zeffy_url": url}})
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Member not found")
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        return _balance_payload(u)

    # ---------- Admin: add line ----------
    @api.post("/admin/members/{user_id}/balance/lines")
    async def admin_add_line(
        user_id: str,
        body: _BalanceLineIn,
        admin: dict = Depends(admin_tab_dep("members")),
    ):
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        line = {
            "id": str(uuid.uuid4()),
            "label": body.label.strip(),
            "amount": round(float(body.amount), 2),
            "created_at": iso(now_utc()),
            "created_by": admin["id"],
            "created_by_name": admin.get("name", "Admin"),
            "paid_at": None,
        }
        await db.users.update_one(
            {"id": user_id},
            {"$push": {"balance_lines": line}},
        )
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        return _balance_payload(u)

    # ---------- Admin: edit an unpaid line ----------
    @api.put("/admin/members/{user_id}/balance/lines/{line_id}")
    async def admin_edit_line(
        user_id: str,
        line_id: str,
        body: _BalanceLineEditIn,
        _: dict = Depends(admin_tab_dep("members")),
    ):
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        lines = list(u.get("balance_lines") or [])
        target = next((ln for ln in lines if ln.get("id") == line_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="Line not found")
        if target.get("paid_at"):
            raise HTTPException(status_code=400, detail="Cannot edit a paid line — delete and re-add if needed")
        if body.label is not None:
            target["label"] = body.label.strip()
        if body.amount is not None:
            target["amount"] = round(float(body.amount), 2)
        await db.users.update_one({"id": user_id}, {"$set": {"balance_lines": lines}})
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        return _balance_payload(u)

    # ---------- Admin: delete an unpaid line ----------
    @api.delete("/admin/members/{user_id}/balance/lines/{line_id}")
    async def admin_delete_line(
        user_id: str,
        line_id: str,
        _: dict = Depends(admin_tab_dep("members")),
    ):
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        lines = list(u.get("balance_lines") or [])
        target = next((ln for ln in lines if ln.get("id") == line_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="Line not found")
        if target.get("paid_at"):
            raise HTTPException(status_code=400, detail="Cannot delete a paid line — it is part of payment history")
        lines = [ln for ln in lines if ln.get("id") != line_id]
        await db.users.update_one({"id": user_id}, {"$set": {"balance_lines": lines}})
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        return _balance_payload(u)

    # ---------- Admin: mark a line paid (no Zeffy receipt needed) ----------
    @api.post("/admin/members/{user_id}/balance/lines/{line_id}/mark-paid")
    async def admin_mark_line_paid(
        user_id: str,
        line_id: str,
        admin: dict = Depends(admin_tab_dep("members")),
    ):
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        lines = list(u.get("balance_lines") or [])
        target = next((ln for ln in lines if ln.get("id") == line_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="Line not found")
        if target.get("paid_at"):
            return _balance_payload(u)  # idempotent
        now_iso = iso(now_utc())
        # Create a corresponding transaction record (so the member sees it in
        # their "Transactions" tab and tax letters can include it).
        tx_id = str(uuid.uuid4())
        tx = {
            "id": tx_id,
            "user_id": user_id,
            "user_name": u.get("name", ""),
            "type": "fee",
            "amount": float(target.get("amount", 0)),
            "currency": "USD",
            "description": f"{target.get('label', 'Outstanding balance')} (admin-cleared)",
            "status": "completed",
            "purpose": "balance",
            "provider": "zeffy",
            "balance_line_id": line_id,
            "recorded_by": admin["id"],
            "recorded_by_name": admin.get("name", "Admin"),
            "approved_at": now_iso,
            "approved_by": admin["id"],
            "approved_by_name": admin.get("name", "Admin"),
            "created_at": now_iso,
        }
        await db.transactions.insert_one(tx)
        # Stamp the line as paid in-place.
        target["paid_at"] = now_iso
        target["paid_via"] = "admin_mark_paid"
        target["paid_tx_id"] = tx_id
        target["paid_by"] = admin["id"]
        target["paid_by_name"] = admin.get("name", "Admin")
        await db.users.update_one({"id": user_id}, {"$set": {"balance_lines": lines}})
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        return _balance_payload(u)

    # ---------- Admin: approve a member-submitted Zeffy receipt ----------
    @api.put("/admin/transactions/{tx_id}/approve-balance")
    async def admin_approve_balance_receipt(
        tx_id: str,
        admin: dict = Depends(require_admin),
    ):
        """Approve a pending balance-receipt transaction → mark the associated
        balance line(s) as paid. Does NOT extend membership."""
        tx = await db.transactions.find_one({"id": tx_id})
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")
        if tx.get("purpose") != "balance" or tx.get("provider") != "zeffy":
            raise HTTPException(status_code=400, detail="Not a balance-receipt transaction")
        if tx.get("status") == "completed":
            return {"ok": True, "already": True}
        now_iso = iso(now_utc())
        await db.transactions.update_one({"id": tx_id}, {"$set": {
            "status": "completed",
            "approved_at": now_iso,
            "approved_by": admin["id"],
            "approved_by_name": admin.get("name", "Admin"),
        }})
        # Walk the line_ids stamped on the tx and mark each one paid.
        line_ids = tx.get("balance_line_ids") or []
        if line_ids:
            u = await db.users.find_one({"id": tx["user_id"]}, {"_id": 0})
            if u:
                lines = list(u.get("balance_lines") or [])
                touched = False
                for ln in lines:
                    if ln.get("id") in line_ids and not ln.get("paid_at"):
                        ln["paid_at"] = now_iso
                        ln["paid_via"] = "member_receipt"
                        ln["paid_tx_id"] = tx_id
                        ln["paid_by"] = admin["id"]
                        ln["paid_by_name"] = admin.get("name", "Admin")
                        touched = True
                if touched:
                    await db.users.update_one(
                        {"id": tx["user_id"]},
                        {"$set": {"balance_lines": lines}},
                    )
        return {"ok": True}

    # ---------- Member: read own balance ----------
    @api.get("/me/balance")
    async def my_balance(user: dict = Depends(get_current_user)):
        u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        # Also surface pending balance-receipt submissions awaiting approval.
        pending_txs = await db.transactions.find(
            {"user_id": user["id"], "purpose": "balance", "status": "pending"},
            {"_id": 0},
        ).sort("created_at", -1).to_list(50)
        payload = _balance_payload(u)
        payload["pending_receipts"] = [
            {
                "id": t.get("id"),
                "amount": float(t.get("amount", 0)),
                "confirmation": t.get("zeffy_confirmation", ""),
                "line_ids": t.get("balance_line_ids", []),
                "created_at": t.get("created_at"),
            }
            for t in pending_txs
        ]
        return payload

    # ---------- Member: submit a Zeffy receipt for one or more lines ----------
    @api.post("/me/balance/submit-receipt")
    async def submit_balance_receipt(
        body: _SubmitReceiptIn,
        user: dict = Depends(get_current_user),
    ):
        """Member confirms they paid via Zeffy. Creates a PENDING transaction
        tied to specific unpaid balance line(s); admin must approve to mark
        the lines settled. (We deliberately do NOT auto-approve like the dues
        flow — anniversary balances are easy to misattribute.)"""
        u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Member not found")
        all_lines = u.get("balance_lines") or []
        # Validate every requested line exists AND is unpaid AND not already
        # referenced by another pending submission (to prevent double-counting).
        unpaid_by_id = {ln["id"]: ln for ln in all_lines if not ln.get("paid_at")}
        requested = [lid for lid in (body.line_ids or []) if lid in unpaid_by_id]
        if not requested:
            raise HTTPException(status_code=400, detail="Select at least one unpaid line to confirm.")
        # Block lines already in a pending tx.
        pending_existing = await db.transactions.find(
            {"user_id": user["id"], "purpose": "balance", "status": "pending"},
            {"_id": 0, "balance_line_ids": 1},
        ).to_list(50)
        locked = set()
        for t in pending_existing:
            for lid in t.get("balance_line_ids", []) or []:
                locked.add(lid)
        conflict = [lid for lid in requested if lid in locked]
        if conflict:
            raise HTTPException(status_code=400, detail="One or more of the selected lines already have a pending receipt.")

        amount = round(sum(unpaid_by_id[lid]["amount"] for lid in requested), 2)
        confirmation = (body.confirmation or "").strip()
        tx_id = str(uuid.uuid4())
        tx = {
            "id": tx_id,
            "user_id": user["id"],
            "user_name": u.get("name", ""),
            "type": "fee",
            "amount": amount,
            "currency": "USD",
            "description": f"Outstanding balance payment via Zeffy (ref: {confirmation})",
            "status": "pending",
            "purpose": "balance",
            "provider": "zeffy",
            "zeffy_confirmation": confirmation,
            "balance_line_ids": requested,
            "created_at": iso(now_utc()),
        }
        await db.transactions.insert_one(tx)
        return {
            "transaction_id": tx_id,
            "status": "pending",
            "amount": amount,
            "message": "Receipt submitted — an admin will verify your payment and clear the balance.",
        }
