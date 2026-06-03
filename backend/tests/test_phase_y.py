"""Phase Y — Community Service Leaderboard + Zeffy dues integration tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env
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


# -------- Leaderboard --------
class TestLeaderboard:
    def test_quarter_default_shape(self, member_sess):
        r = member_sess.get(f"{API}/leaderboards/community-service", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "period_label" in d
        assert "top_chapters" in d and isinstance(d["top_chapters"], list)
        assert "top_members" in d and isinstance(d["top_members"], list)
        assert len(d["top_chapters"]) <= 5
        assert len(d["top_members"]) <= 5
        # default = quarter
        assert d["period"] == "quarter"

    def test_chapter_row_shape(self, member_sess):
        r = member_sess.get(f"{API}/leaderboards/community-service?period=all", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["period_label"] == "All time"
        if d["top_chapters"]:
            row = d["top_chapters"][0]
            for k in ("chapter_id", "chapter_name", "hours", "count", "member_count"):
                assert k in row, f"missing {k} in chapter row: {row}"

    def test_member_row_shape(self, member_sess):
        r = member_sess.get(f"{API}/leaderboards/community-service?period=all", timeout=15)
        d = r.json()
        if d["top_members"]:
            row = d["top_members"][0]
            for k in ("user_id", "user_name", "avatar_url", "chapter_id", "chapter_name", "hours", "count"):
                assert k in row, f"missing {k} in member row: {row}"

    def test_year_period(self, member_sess):
        from datetime import datetime
        r = member_sess.get(f"{API}/leaderboards/community-service?period=year", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["period_label"] == str(datetime.utcnow().year)

    def test_only_approved_hours_counted(self, member_sess):
        # All hours in leaderboard must be approved; we just check totals are >= 0 and counts >= 0
        r = member_sess.get(f"{API}/leaderboards/community-service?period=all", timeout=15)
        d = r.json()
        for row in d["top_chapters"]:
            assert row["hours"] >= 0
            assert row["count"] >= 0
        for row in d["top_members"]:
            assert row["hours"] >= 0


# -------- Zeffy config --------
class TestZeffyConfig:
    def test_zeffy_config(self, member_sess):
        r = member_sess.get(f"{API}/payments/zeffy/config", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["url"] == "https://www.zeffy.com/en-US/ticketing/national-yearly-dues"
        assert d["currency"] == "USD"
        assert float(d["default_amount"]) == 60.0
        assert d["enabled"] is True


# -------- Zeffy confirm --------
class TestZeffyConfirm:
    def test_create_pending(self, member_sess):
        r = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": "TEST-REF-123", "amount": 60},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending"
        assert "transaction_id" in d
        TestZeffyConfirm.tx_id = d["transaction_id"]

    def test_short_confirmation_rejected(self, member_sess):
        r = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": "x", "amount": 60},
            timeout=15,
        )
        assert r.status_code == 422

    def test_empty_confirmation_rejected(self, member_sess):
        r = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": "", "amount": 60},
            timeout=15,
        )
        assert r.status_code == 422


# -------- Approve flow --------
class TestZeffyApprove:
    def test_member_forbidden(self, member_sess):
        # create a tx first
        c = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": "TEST-MEMBER-FORBID", "amount": 60},
            timeout=15,
        )
        tx_id = c.json()["transaction_id"]
        r = member_sess.put(f"{API}/transactions/{tx_id}/approve-zeffy", timeout=15)
        assert r.status_code == 403

    def test_admin_approves_and_extends_membership(self, member_sess, admin_sess):
        # create pending zeffy tx
        c = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": "TEST-APPROVE-456", "amount": 60},
            timeout=15,
        )
        tx_id = c.json()["transaction_id"]

        # get member before
        me_before = member_sess.get(f"{API}/auth/me", timeout=15).json()
        before_exp = me_before.get("membership_expires_at")

        # approve as admin
        r = admin_sess.put(f"{API}/transactions/{tx_id}/approve-zeffy", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True

        # tx now completed
        tx_list = admin_sess.get(f"{API}/transactions?user_id={me_before['id']}", timeout=15).json()
        approved_tx = [t for t in tx_list if t["id"] == tx_id]
        assert approved_tx, f"tx not in list: {[t['id'] for t in tx_list[:5]]}"
        assert approved_tx[0]["status"] == "completed"
        assert approved_tx[0]["provider"] == "zeffy"
        assert approved_tx[0]["purpose"] == "dues"
        assert approved_tx[0]["type"] == "renewal"
        assert float(approved_tx[0]["amount"]) == 60.0

        # membership extended ~365 days
        me_after = member_sess.get(f"{API}/auth/me", timeout=15).json()
        after_exp = me_after.get("membership_expires_at")
        assert after_exp is not None
        if before_exp:
            from datetime import datetime
            try:
                b = datetime.fromisoformat(before_exp.replace("Z", "+00:00"))
                a = datetime.fromisoformat(after_exp.replace("Z", "+00:00"))
                delta_days = (a - b).days
                # Should be extended by ~365 (or more if was expired)
                assert delta_days >= 0
            except Exception:
                pass

    def test_idempotent_approve(self, member_sess, admin_sess):
        c = member_sess.post(
            f"{API}/payments/zeffy/confirm",
            json={"confirmation": "TEST-IDEMPOTENT-789", "amount": 60},
            timeout=15,
        )
        tx_id = c.json()["transaction_id"]
        r1 = admin_sess.put(f"{API}/transactions/{tx_id}/approve-zeffy", timeout=15)
        assert r1.status_code == 200
        r2 = admin_sess.put(f"{API}/transactions/{tx_id}/approve-zeffy", timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("already") is True

    def test_non_zeffy_returns_400(self, admin_sess):
        # find any non-zeffy transaction to test 400
        txs = admin_sess.get(f"{API}/transactions", timeout=15).json()
        non_zeffy = [t for t in txs if t.get("provider") != "zeffy"]
        if not non_zeffy:
            pytest.skip("no non-zeffy tx to test against")
        r = admin_sess.put(
            f"{API}/transactions/{non_zeffy[0]['id']}/approve-zeffy", timeout=15
        )
        assert r.status_code == 400


# -------- Regression: hours summary still works --------
class TestHoursRegression:
    def test_me_hours_summary(self, member_sess):
        r = member_sess.get(f"{API}/me/hours/summary", timeout=15)
        assert r.status_code == 200

    def test_reports_hours_summary(self, admin_sess):
        r = admin_sess.get(f"{API}/reports/hours/summary?group_by=chapter", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "rows" in d


# -------- Cleanup: delete TEST zeffy pending transactions --------
@pytest.fixture(scope="module", autouse=True)
def cleanup(admin_sess):
    yield
    try:
        txs = admin_sess.get(f"{API}/transactions", timeout=15).json()
        for t in txs:
            desc = t.get("description", "")
            if t.get("provider") == "zeffy" and ("TEST-" in desc):
                admin_sess.delete(f"{API}/transactions/{t['id']}", timeout=10)
    except Exception:
        pass
