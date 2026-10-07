"""End to end against a real Postgres: sync -> recon -> /api/hub -> webhook.

Needs TEST_DATABASE_URL pointing at a throwaway database (it is wiped)."""
import hashlib
import hmac
import json
import os
from datetime import timedelta

import pytest

from connectors.paystack import PaystackConnector
from sync import db
from sync.recon import reconcile
from sync.run_sync import sync_one

from .fakes import NOW, client, paystack_handler

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    c = db.connect(URL)
    c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    c.commit()
    db.init_schema(c)
    c.execute("INSERT INTO fx_rate VALUES (%s, 'NGN', 0.00065)", (NOW.date() - timedelta(days=10),))
    c.commit()
    yield c
    c.close()


def crm(c, cid, client_id, order, amount, minutes, psp="paystack"):
    pid = db.psp_id(c, psp)
    c.execute("""INSERT INTO crm_txn (crm_txn_id, client_id, client_name, psp_id, merchant_order_id, direction,
                   status, amount, currency, usd_amount, created_at)
                 VALUES (%s,%s,'Test',%s,%s,'deposit','approved',%s,'NGN',%s * 0.00065,%s)""",
              (cid, client_id, pid, order, amount, amount, NOW - timedelta(hours=5) + timedelta(minutes=minutes)))


def test_sync_recon_and_hub(conn):
    c = PaystackConnector({"PAYSTACK_SECRET_KEY": "sk_test_good"}, http=client(paystack_handler([])))
    res = sync_one(conn, c, NOW - timedelta(days=2), NOW)
    assert res == {"transactions": "5 rows", "balances": "1 rows", "settlements": "1 rows"}
    # re-sync is idempotent
    sync_one(conn, c, NOW - timedelta(days=2), NOW)
    assert conn.execute("SELECT count(*) FROM psp_txn").fetchone()[0] == 5
    usd = conn.execute("SELECT usd_amount FROM psp_txn WHERE psp_txn_id='1001'").fetchone()[0]
    assert float(usd) == pytest.approx(50000 * 0.00065)

    crm(conn, "C1", "CL-1", "ORD-1", 50000, 0)        # exact match
    crm(conn, "C2", "CL-2", "ORD-2", 20400, 10)       # CRM booked gross, PSP shows less -> Amount mismatch
    crm(conn, "C3", "CL-3", "ORD-404", 7000, 40)      # never reached PSP -> Missing in PSP
    crm(conn, "C4", "CL-1", "ORD-1", 50000, 1)        # second CRM credit for ORD-1 -> Duplicate in CRM
    conn.commit()                                     # PSP 1004 / ORD-9 has no CRM row -> Missing in CRM
    out = reconcile(conn, (NOW - timedelta(days=1)).date(), NOW.date())
    types = sorted(r[0] for r in conn.execute("SELECT type FROM recon_break"))
    assert types == ["Amount mismatch", "Duplicate in CRM", "Missing in CRM", "Missing in PSP"]
    assert out == {"matched": 1, "breaks": 4}
    reconcile(conn, (NOW - timedelta(days=1)).date(), NOW.date())   # no duplicate breaks on re-run
    assert conn.execute("SELECT count(*) FROM recon_break").fetchone()[0] == 4

    # late CRM row for ORD-9 auto-resolves the Missing in CRM break
    crm(conn, "C5", "CL-9", "ORD-9", 30000, 30)
    conn.commit()
    reconcile(conn, (NOW - timedelta(days=1)).date(), NOW.date())
    assert conn.execute("SELECT status FROM recon_break WHERE type='Missing in CRM'").fetchone()[0] == "Resolved"

    conn.execute("""INSERT INTO wallet_floor SELECT id, 'NGN', 10000000 FROM psp WHERE code='paystack'""")
    conn.commit()

    from fastapi.testclient import TestClient
    from api.server import app
    api = TestClient(app)
    h = api.get("/api/hub?days=60").json()
    assert h["source"] == "live" and len(h["dates"]) == 60
    assert [p["id"] for p in h["psps"]] == ["paystack"]
    today = h["daily"][0][-1] if NOW.date().isoformat() == h["dates"][-1] else None
    total = {k: sum(d[k] for d in h["daily"][0]) for k in ("dep", "wd", "cnt", "att")}
    assert total["cnt"] == 3 and total["att"] == 4                       # 3 success + 1 abandoned
    assert total["dep"] == pytest.approx((50000 + 20000 + 30000) * 0.00065)
    assert total["wd"] == pytest.approx(15000 * 0.00065)
    assert h["wallets"] == [{"psp": "paystack", "cur": [["NGN", 9123456.0, 10000000.0]]}]
    assert h["settle"][0]["age"] == 4
    assert h["fx"]["NGN"] == pytest.approx(0.00065) and h["settle"][0]["cur"] == "NGN"
    rec = {k: sum(d[k] for d in h["recon"][0]) for k in ("crmCnt", "pspCnt", "matched")}
    assert rec == {"crmCnt": 5, "pspCnt": 3, "matched": 2}            # C1, C5 clean; C2/C3/C4 have open breaks
    assert {b["type"] for b in h["breaks"] if b["status"] == "Open"} == {"Amount mismatch", "Duplicate in CRM", "Missing in PSP"}
    assert h["conns"][0]["last"] < 5 and h["conns"][0]["rec"] == 5
    assert today is None or isinstance(today["dep"], float)

    bid = next(b["id"] for b in h["breaks"] if b["type"] == "Missing in PSP")
    assert api.post(f"/api/breaks/{bid}/resolve").json() == {"ok": True}
    assert api.post("/api/breaks/BRK-999999/resolve").status_code == 404


def test_webhook_signed_and_rejected(conn, monkeypatch):
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_good")
    from fastapi.testclient import TestClient
    from api.server import app
    api = TestClient(app)
    body = json.dumps({"event": "charge.success", "data": {"id": 42, "reference": "ORD-42", "amount": 990000,
                       "currency": "NGN", "status": "success", "created_at": NOW.isoformat()}}).encode()
    sig = hmac.new(b"sk_test_good", body, hashlib.sha512).hexdigest()
    assert api.post("/webhooks/paystack", content=body, headers={"x-paystack-signature": "bad"}).status_code == 401
    assert api.post("/webhooks/paystack", content=body, headers={"x-paystack-signature": sig}).json() == {"ok": True}
    row = conn.execute("SELECT amount, status FROM psp_txn WHERE psp_txn_id='42'").fetchone()
    assert (float(row[0]), row[1]) == (9900.0, "success")
