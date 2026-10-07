"""Fake PSP HTTP servers built on httpx.MockTransport (no network)."""
import json
from datetime import datetime, timedelta, timezone

import httpx

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def paystack_handler(calls: list):
    t0 = NOW - timedelta(hours=5)
    txns = [  # amounts in kobo
        {"id": 1001, "reference": "ORD-1", "amount": 5_000_000, "currency": "NGN", "status": "success",
         "fees": 85_000, "created_at": iso(t0), "paid_at": iso(t0 + timedelta(minutes=2)), "channel": "card",
         "metadata": {"client_id": "CL-1"}, "customer": {"customer_code": "CUS_x"}},
        {"id": 1002, "reference": "ORD-2", "amount": 2_000_000, "currency": "NGN", "status": "success",
         "fees": 40_000, "created_at": iso(t0 + timedelta(minutes=10)), "paid_at": iso(t0 + timedelta(minutes=13)),
         "channel": "bank", "metadata": {"client_id": "CL-2"}},
        {"id": 1003, "reference": "ORD-3", "amount": 1_000_000, "currency": "NGN", "status": "abandoned",
         "fees": None, "created_at": iso(t0 + timedelta(minutes=20)), "paid_at": None, "channel": "card"},
        {"id": 1004, "reference": "ORD-9", "amount": 3_000_000, "currency": "NGN", "status": "success",
         "fees": 60_000, "created_at": iso(t0 + timedelta(minutes=30)), "paid_at": iso(t0 + timedelta(minutes=31)),
         "channel": "card"},
    ]

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.headers.get("authorization") != "Bearer sk_test_good":
            return httpx.Response(401, json={"status": False, "message": "Invalid key"})
        page = int(req.url.params.get("page", 1))
        if req.url.path == "/transaction":
            return httpx.Response(200, json={"status": True, "data": txns[(page - 1) * 2: page * 2],
                                             "meta": {"page": page, "pageCount": 2}})
        if req.url.path == "/transfer":
            return httpx.Response(200, json={"status": True, "data": [
                {"id": 77, "reference": "WD-1", "amount": 1_500_000, "currency": "NGN", "status": "success",
                 "createdAt": iso(t0 + timedelta(hours=1)), "fee_charged": 5000}], "meta": {"pageCount": 1}})
        if req.url.path == "/balance":
            return httpx.Response(200, json={"status": True, "data": [{"currency": "NGN", "balance": 912_345_600}]})
        if req.url.path == "/settlement":
            return httpx.Response(200, json={"status": True, "data": [
                {"id": 555, "total_amount": 6_900_000, "status": "pending", "currency": "NGN",
                 "settlement_date": iso(NOW - timedelta(days=4))}], "meta": {"pageCount": 1}})
        if req.url.path.startswith("/transaction/verify/"):
            ref = req.url.path.rsplit("/", 1)[1]
            hit = [t for t in txns if t["reference"] == ref]
            return httpx.Response(200 if hit else 404, json={"status": bool(hit), "data": hit[0] if hit else None})
        return httpx.Response(404)
    return handler


def lipad_handler(calls: list):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.url.path == "/api/v1/api-auth/access-token":
            body = dict(httpx.QueryParams(req.content.decode()))
            if body.get("consumerKey") == "ck" and body.get("consumerSecret") == "cs":
                return httpx.Response(200, json={"access_token": "tok123", "expires_in": 3600})
            return httpx.Response(401, json={"message": "Invalid Credentials"})
        if req.url.path == "/api/v1/checkout/request/status":
            assert req.headers["authorization"] == "Bearer tok123"
            mid = req.url.params["merchant_transaction_id"]
            if mid != "LP-1":
                return httpx.Response(404, json={})
            return httpx.Response(200, json={
                "merchant_transaction_id": "LP-1", "checkout_request_id": 98765,
                "overall_payment_status": "PAYMENT_SUCCESSFUL", "request_amount": "1500.00",
                "currency_code": "KES", "country_code": "KE", "account_number": "CL-7",
                "created_at": iso(NOW - timedelta(hours=1)),
                "payments": [{"payment_option_code": "MPESA_KEN", "payment_date": iso(NOW)}]})
        return httpx.Response(404)
    return handler


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


__all__ = ["paystack_handler", "lipad_handler", "client", "NOW", "json"]
