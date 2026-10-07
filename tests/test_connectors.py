import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

import pytest

from connectors import REGISTRY, MissingCredentials, NotSupported
from connectors.lipad import LipadConnector, map_status
from connectors.paystack import PaystackConnector

from .fakes import NOW, client, lipad_handler, paystack_handler


def paystack(key="sk_test_good"):
    calls = []
    return PaystackConnector({"PAYSTACK_SECRET_KEY": key}, http=client(paystack_handler(calls))), calls


def test_missing_credentials_lists_env_vars(monkeypatch):
    monkeypatch.delenv("LIPAD_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("LIPAD_CONSUMER_SECRET", raising=False)
    with pytest.raises(MissingCredentials) as e:
        LipadConnector()
    assert e.value.names == ["LIPAD_CONSUMER_KEY", "LIPAD_CONSUMER_SECRET"]


def test_paystack_lists_all_pages_and_transfers():
    c, calls = paystack()
    txns = list(c.list_transactions(NOW - timedelta(days=1), NOW))
    assert [t.psp_txn_id for t in txns] == ["1001", "1002", "1003", "1004", "TRF-77"]
    first = txns[0]
    assert (first.amount, first.fee, first.currency, first.status) == (Decimal(50000), Decimal(850), "NGN", "success")
    assert first.client_ref == "CL-1" and first.merchant_order_id == "ORD-1"
    assert txns[2].status == "failed"                       # abandoned -> failed
    assert txns[4].direction == "withdrawal" and txns[4].amount == Decimal(15000)
    assert [r.url.params["page"] for r in calls if r.url.path == "/transaction"] == ["1", "2"]


def test_paystack_balance_settlement_and_bad_key():
    c, _ = paystack()
    (b,) = c.balances()
    assert (b.currency, b.available) == ("NGN", Decimal("9123456"))
    (s,) = c.settlements(NOW - timedelta(days=30), NOW)
    assert (s.ref, s.amount, s.status) == ("555", Decimal(69000), "pending")
    bad, _ = paystack("sk_test_bad")
    with pytest.raises(PermissionError):
        bad.healthcheck()


def test_paystack_webhook_signature():
    c, _ = paystack()
    body = json.dumps({"event": "charge.success", "data": {"id": 5, "reference": "ORD-5", "amount": 100,
                                                           "currency": "NGN", "status": "success",
                                                           "created_at": "2026-10-01T10:00:00Z"}}).encode()
    sig = hmac.new(b"sk_test_good", body, hashlib.sha512).hexdigest()
    assert c.parse_webhook({"X-Paystack-Signature": sig}, body).merchant_order_id == "ORD-5"
    with pytest.raises(PermissionError):
        c.parse_webhook({"X-Paystack-Signature": "0" * 128}, body)


def test_lipad_status_query_and_mapping():
    calls = []
    c = LipadConnector({"LIPAD_CONSUMER_KEY": "ck", "LIPAD_CONSUMER_SECRET": "cs"}, env="sandbox",
                       http=client(lipad_handler(calls)))
    assert c.healthcheck() == "token ok (sandbox)"
    assert calls[0].url.host == "checkout.api.uat.lipad.io"
    t = c.get_transaction("LP-1")
    assert (t.status, t.amount, t.currency, t.method, t.client_ref) == ("success", Decimal("1500.00"), "KES", "MPESA_KEN", "CL-7")
    with pytest.raises(LookupError):
        c.get_transaction("nope")
    with pytest.raises(NotSupported):
        c.balances()
    assert sum(1 for r in calls if r.url.path.endswith("access-token")) == 1   # token reused


def test_lipad_bad_credentials():
    c = LipadConnector({"LIPAD_CONSUMER_KEY": "ck", "LIPAD_CONSUMER_SECRET": "wrong"}, http=client(lipad_handler([])))
    with pytest.raises(PermissionError):
        c.healthcheck()


@pytest.mark.parametrize("raw,want", [
    ({"overall_payment_status": "PAYMENT_SUCCESSFUL"}, "success"),
    ({"request_status_description": "Request Expired"}, "failed"),
    ({"status": "Awaiting payment"}, "pending"),
    ({}, "pending"),
])
def test_lipad_status_words(raw, want):
    assert map_status(raw) == want


def test_pending_connectors_do_not_pretend():
    c = REGISTRY["pay247"]({"PAY247_MERCHANT_ID": "m", "PAY247_API_KEY": "k", "PAY247_BASE_URL": "u"})
    with pytest.raises(NotImplementedError):
        c.healthcheck()
