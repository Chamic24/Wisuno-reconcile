"""Lipad (Kenya / Tanzania / Uganda mobile money).

Endpoints come from Lipad's official SDKs (PyPI `lipad-sdk` 1.0.5, npm `lipad-sdk` 1.0.5 /
`lpd-sdk` 0.0.1), because developer.lipad.io was not reachable from the dev environment.

What Lipad's public API covers:
  - access token                      POST {checkout}/api/v1/api-auth/access-token
  - checkout status by our order id   GET  {checkout}/api/v1/checkout/request/status?merchant_transaction_id=
  - direct-charge token               POST {charge}/auth
  - direct-charge status by charge id GET  {charge}/transaction/{id}/status
What it does NOT cover (ask Lipad): transaction list by date, wallet balance, settlement report,
payout status. Until then Lipad data comes in through the callback_url webhook, and the status
query is used to re-check orders the CRM knows about.

Response field names below are best-effort and must be checked against a real sandbox response;
every raw payload is stored so the mapping can be fixed without losing data.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .base import Connector, Txn, dec, parse_dt

CHECKOUT = {"production": "https://checkout.api.lipad.io", "sandbox": "https://checkout.api.uat.lipad.io"}
CHARGE = {"production": "https://charge.lipad.io/v1", "sandbox": "https://dev.charge.lipad.io/v1"}
CHARGE_AUTH = {"production": "https://charge.lipad.io/v1/auth", "sandbox": "https://dev.lipad.io/v1/auth"}

SUCCESS_WORDS = ("success", "paid", "complete", "settled")
FAIL_WORDS = ("fail", "reject", "cancel", "expire", "declin", "unpaid")


def map_status(raw: dict) -> str:
    for k in ("overall_payment_status", "request_status_description", "status_description",
              "payment_status", "status"):
        v = raw.get(k)
        if isinstance(v, str) and v:
            s = v.lower()
            if any(w in s for w in SUCCESS_WORDS):
                return "success"
            if any(w in s for w in FAIL_WORDS):
                return "failed"
            return "pending"
    return "pending"


def first(raw: dict, *keys):
    for k in keys:
        if raw.get(k) not in (None, ""):
            return raw[k]
    return None


def to_txn(raw: dict) -> Txn:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    payments = data.get("payments") or []
    pay = payments[0] if payments and isinstance(payments[0], dict) else {}
    return Txn(
        psp_txn_id=str(first(data, "checkout_request_id", "charge_request_id", "transaction_id", "id",
                             "merchant_transaction_id")),
        merchant_order_id=first(data, "merchant_transaction_id", "external_reference"),
        direction="deposit",
        status=map_status(data),
        amount=dec(first(data, "request_amount", "amount", "amount_paid")) or dec(0),
        currency=str(first(data, "currency_code", "currency") or ""),
        fee=dec(first(data, "transaction_charge", "charge", "fee")),
        created_at=parse_dt(first(data, "created_at", "request_date", "date")) or datetime.now(timezone.utc),
        completed_at=parse_dt(first(pay, "payment_date", "created_at")),
        client_ref=first(data, "account_number"),
        method=first(pay, "payment_option_code", "payment_method_code") or first(data, "payment_method_code"),
        country=first(data, "country_code"),
        raw=raw,
    )


class LipadConnector(Connector):
    code = "lipad"
    name = "Lipad"
    env_vars = ("LIPAD_CONSUMER_KEY", "LIPAD_CONSUMER_SECRET")
    capabilities = {"list_transactions": False, "get_transaction": True, "balances": False,
                    "settlements": False, "webhook": True, "webhook_signed": False}

    _token: str | None = None

    def _checkout_token(self) -> str:
        if not self._token:
            r = self.http.post(CHECKOUT[self.env] + "/api/v1/api-auth/access-token", data={
                "consumerKey": self.creds["LIPAD_CONSUMER_KEY"],
                "consumerSecret": self.creds["LIPAD_CONSUMER_SECRET"],
            })
            if r.status_code == 401:
                raise PermissionError("Lipad: invalid credentials (401)")
            r.raise_for_status()
            tok = r.json().get("access_token")
            if not tok:
                raise RuntimeError(f"Lipad: no access_token in response: {r.text[:200]}")
            self._token = tok
        return self._token

    def healthcheck(self) -> str:
        self._checkout_token()
        return f"token ok ({self.env})"

    def get_transaction(self, ref: str) -> Txn:
        r = self.http.get(CHECKOUT[self.env] + "/api/v1/checkout/request/status",
                          params={"merchant_transaction_id": ref},
                          headers={"Authorization": f"Bearer {self._checkout_token()}"})
        if r.status_code == 404:
            raise LookupError(f"Lipad: merchant_transaction_id {ref!r} not found")
        r.raise_for_status()
        return to_txn(r.json())

    def parse_webhook(self, headers: dict, body: bytes) -> Txn:
        # Lipad posts the checkout result to callback_url. No signature scheme is documented in the
        # SDK, so the webhook handler re-queries the status API before trusting the payload.
        return to_txn(json.loads(body))
