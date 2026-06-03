"""Phase Z — trust_zeffy auto-approve flow.

Covers:
- Admin PUT /api/members/{id} can set trust_zeffy=true/false
- POST /api/payments/zeffy/confirm with trust_zeffy=true:
  - happy path 'ZF-ABC123DEF' -> auto-approved + membership extended
  - pattern variations (ZF-prefix, 10+ raw alphanum, email)
  - bad/too-short patterns still create pending
- Without trust_zeffy, even a valid pattern creates pending
- GET /api/auth/me & GET /api/members/{id} expose trust_zeffy
- Regression: admin approve-zeffy endpoint still works
"""
import os
import re
from datetime import datetime

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass

API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@clubhaven.app", "password": "Admin123!"}
MEMBER = {"email": "member@clubhaven.app", "password": "Member123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_sess():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def member_sess():
    return _login(MEMBER)


@pytest.fixture(scope="module")
def member_id(member_sess):
    me = member_sess.get(f"{API}/auth/me", timeout=15).json()
    return me["id"]


@pytest.fixture(scope="module", autouse=True)
def reset_trust_flag(admin_sess, member_id):
    """Reset trust_zeffy=false after suite."""
    yield
    try:
        admin_sess.put(f"{API}/members/{member_id}", json={"trust_zeffy": False}, timeout=15)
        # Cleanup TEST_ zeffy txs created during tests
        txs = admin_sess.get(f"{API}/transactions", timeout=15).json()
        for t in txs:
            desc = t.get("description", "")
            if t.get("provider") == "zeffy" and "TESTZ" in desc.upper():
                admin_sess.delete(f"{API}/transactions/{t['id']}", timeout=10)
    except Exception:
        pass


# -------- trust_zeffy flag exposure --------
class TestTrustZeffyFlag:
    def test_auth_me_has_trust_zeffy_field(self, member_sess):
        r = member_sess.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "trust_zeffy" in d
        assert isinstance(d["trust_zeffy"], bool)

    def test_admin_get_member_has_trust_zeffy_field(self, admin_sess, member_id):
        r = admin_sess.get(f"{API}/members/{member_id}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "trust_zeffy" in d
        assert isinstance(d["trust_zeffy"], bool)

    def test_admin_can_set_trust_zeffy_true(self, admin_sess, member_id):
        r = admin_sess.put(
            f"{API}/members/{member_id}",
            json={"trust_zeffy": True},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # GET to verify persisted
        g = admin_sess.get(f"{API}/members/{member_id}", timeout=15).json()
        assert g["trust_zeffy"] is True

    def test_admin_can_set_trust_zeffy_false(self, admin_sess, member_id):
        r = admin_sess.put(
            f"{API}/members/{member_id}",
            json={"trust_zeffy": False},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        g = admin_sess.get(f"{API}/members/{member_id}", timeout=15).json()
        assert g["trust_zeffy"] is False


# -------- no-trust path: even valid pattern stays pending --------
class TestNoTrustStillPending:
    def test_valid_pattern_no_trust_is_pending(self, member_sess, admin_sess, member_id):
        # Ensure trust is false
        admin_sess.put(f"{API}/members/{member_id}", json={"trust_zeffy": False}, timeout=15)
        r = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": "ZF-TESTZNOTRUST", "amount": 60},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending"
        assert d.get("auto_approved") in (False, None)
        # Verify DB-side
        txs = admin_sess.get(f"{API}/transactions?user_id={member_id}", timeout=15).json()
        match = [t for t in txs if t.get("id") == d["transaction_id"]]
        assert match
        assert match[0]["status"] == "pending"
        assert match[0].get("zeffy_auto_approved") in (False, None)


# -------- happy-path auto-approve with trust + pattern --------
class TestAutoApproveHappyPath:
    @pytest.fixture(autouse=True)
    def enable_trust(self, admin_sess, member_id):
        admin_sess.put(f"{API}/members/{member_id}", json={"trust_zeffy": True}, timeout=15)
        yield

    def test_zf_prefix_pattern_auto_approves_and_extends(self, member_sess, admin_sess, member_id):
        me_before = member_sess.get(f"{API}/auth/me", timeout=15).json()
        before_exp = me_before.get("membership_expires_at")

        r = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": "ZF-TESTZAUTO1ABCDEF", "amount": 60},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "completed", f"expected completed, got: {d}"
        assert d["auto_approved"] is True

        # Verify DB record
        txs = admin_sess.get(f"{API}/transactions?user_id={member_id}", timeout=15).json()
        match = [t for t in txs if t["id"] == d["transaction_id"]]
        assert match, "tx not found"
        tx = match[0]
        assert tx["status"] == "completed"
        assert tx["provider"] == "zeffy"
        assert tx["purpose"] == "dues"
        assert tx.get("approved_by") == "system:zeffy-trust"
        assert tx.get("zeffy_auto_approved") is True
        assert float(tx["amount"]) == 60.0

        # Membership extended ~365 days
        me_after = member_sess.get(f"{API}/auth/me", timeout=15).json()
        after_exp = me_after.get("membership_expires_at")
        assert after_exp is not None
        try:
            a = datetime.fromisoformat(after_exp.replace("Z", "+00:00"))
            if before_exp:
                b = datetime.fromisoformat(before_exp.replace("Z", "+00:00"))
                delta = (a - b).days
                # Should jump by ~365 (or more, if previous expiry was past)
                assert delta >= 350, f"expected ~365 day extension, got {delta}"
            else:
                # Should be ~365 days in the future
                now = datetime.utcnow().astimezone(a.tzinfo) if a.tzinfo else datetime.utcnow()
                delta = (a - now).days
                assert 360 <= delta <= 370
        except AssertionError:
            raise
        except Exception:
            pass

    @pytest.mark.parametrize(
        "confirmation",
        [
            "ZF-TESTZABCDEF",          # ZF- prefix
            "TESTZABCDEFGH",            # 10+ alphanumeric all uppercase
            "testz.member@example.com", # email format
        ],
    )
    def test_pattern_variations_all_auto_approve(self, member_sess, confirmation):
        r = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": confirmation, "amount": 60},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "completed", f"pattern {confirmation!r} did not auto-approve: {d}"
        assert d["auto_approved"] is True


# -------- bad pattern with trust=true still goes pending --------
class TestBadPatternStillPending:
    @pytest.fixture(autouse=True)
    def enable_trust(self, admin_sess, member_id):
        admin_sess.put(f"{API}/members/{member_id}", json={"trust_zeffy": True}, timeout=15)
        yield

    def test_too_short_confirmation_is_pending(self, member_sess):
        # 'bad' is 3 chars: below 6-char floor in _is_valid_zeffy_receipt
        r = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": "bad", "amount": 60},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending", f"expected pending for short ref, got {d}"
        assert d.get("auto_approved") in (False, None)

    def test_five_char_confirmation_is_pending(self, member_sess):
        # 5 chars, below 6-char minimum
        r = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": "12345", "amount": 60},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending"
        assert d.get("auto_approved") in (False, None)

    def test_no_pattern_match_is_pending(self, member_sess):
        # 7 chars but with spaces and no pattern match
        r = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": "hi there friend", "amount": 60},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending"


# -------- Regression: manual admin approve-zeffy still works --------
class TestApproveZeffyRegression:
    def test_admin_can_still_manually_approve(self, member_sess, admin_sess, member_id):
        # turn trust off so it stays pending
        admin_sess.put(f"{API}/members/{member_id}", json={"trust_zeffy": False}, timeout=15)
        c = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": "TESTZREGRESS-REF", "amount": 60},
            timeout=15,
        )
        assert c.json()["status"] == "pending"
        tx_id = c.json()["transaction_id"]
        r = admin_sess.put(f"{API}/transactions/{tx_id}/approve-zeffy", timeout=15)
        assert r.status_code == 200
        assert r.json()["ok"] is True
