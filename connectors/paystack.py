"""Paystack (Nigeria). Public docs: https://paystack.com/docs/api/

Reference implementation of a PSP whose API covers everything the dashboard needs:
transaction list, transfers (payouts), balance and settlements. Amounts are in the
currency's subunit (kobo for NGN), so they are divided by 100.
Not yet run against a live merchant key.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from decimal import Decimal
from typing import Iterator

from .base import Balance, Connector, Settlement, Txn, dec, parse_dt

BASE = "https://api.paystack.co"
DEP_STATUS = {"success": "success", "failed": "failed", "abandoned": "failed", "reversed": "refunded"}
WD_STATUS = {"success": "success", "failed": "failed", "reversed": "refunded"}


def sub(v) -> Decimal | None:
    d = dec(v)
    return None if d is None else d / 100


class PaystackConnector(Connector):
    code = "paystack"
    name = "PayStack"
    env_vars = ("PAYSTACK_SECRET_KEY",)
    capabilities = {"list_transactions": True, "get_transaction": True, "balances": True,
                    "settlements": True, "webhook": True, "webhook_signed": True}

    def _get(self, path: str, **params) -> dict:
        r = self.http.get(BASE + path, params=params,
                          headers={"Authorization": f"Bearer {self.creds['PAYSTACK_SECRET_KEY']}"})
        if r.status_code == 401:
            raise PermissionError("Paystack: invalid secret key (401)")
        r.raise_for_status()
        return r.json()

    def _pages(self, path: str, start: datetime, end: datetime) -> Iterator[dict]:
        page = 1
        while True:
            j = self._get(path, perPage=100, page=page, **{"from": start.isoformat(), "to": end.isoformat()})
            yield from j.get("data") or []
            meta = j.get("meta") or {}
            if page >= int(meta.get("pageCount") or 1):
                return
            page += 1

    def healthcheck(self) -> str:
        self._get("/balance")
        return "key ok"

    @staticmethod
    def _deposit(d: dict) -> Txn:
        cust = d.get("customer") or {}
        meta = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
        return Txn(
            psp_txn_id=str(d["id"]), merchant_order_id=d.get("reference"), direction="deposit",
            status=DEP_STATUS.get(d.get("status"), "pending"), amount=sub(d.get("amount")),
            currency=d.get("currency") or "NGN", fee=sub(d.get("fees")),
            created_at=parse_dt(d.get("created_at") or d.get("createdAt")),
            completed_at=parse_dt(d.get("paid_at")),
            client_ref=meta.get("client_id") or cust.get("customer_code"),
            method=d.get("channel"), country="NG", raw=d)

    @staticmethod
    def _withdrawal(d: dict) -> Txn:
        return Txn(
            psp_txn_id="TRF-" + str(d["id"]), merchant_order_id=d.get("reference"), direction="withdrawal",
            status=WD_STATUS.get(d.get("status"), "pending"), amount=sub(d.get("amount")),
            currency=d.get("currency") or "NGN", fee=sub(d.get("fee_charged")),
            created_at=parse_dt(d.get("createdAt") or d.get("created_at")),
            completed_at=parse_dt(d.get("transferred_at")), method="transfer", country="NG", raw=d)

    def list_transactions(self, start: datetime, end: datetime) -> Iterator[Txn]:
        for d in self._pages("/transaction", start, end):
            yield self._deposit(d)
        for d in self._pages("/transfer", start, end):
            yield self._withdrawal(d)

    def get_transaction(self, ref: str) -> Txn:
        return self._deposit(self._get(f"/transaction/verify/{ref}")["data"])

    def balances(self) -> list[Balance]:
        now = datetime.now().astimezone()
        return [Balance(currency=b["currency"], available=sub(b["balance"]), as_of=now, raw=b)
                for b in self._get("/balance").get("data") or []]

    def settlements(self, start: datetime, end: datetime) -> list[Settlement]:
        st = {"success": "paid", "processed": "paid", "failed": "failed"}
        return [Settlement(ref=str(s["id"]), amount=sub(s.get("total_amount") or s.get("effective_amount")),
                           currency=s.get("currency") or "NGN", status=st.get(s.get("status"), "pending"),
                           expected_date=parse_dt(s.get("settlement_date")),
                           settled_at=parse_dt(s.get("settled_at")), raw=s)
                for s in self._pages("/settlement", start, end)]

    def parse_webhook(self, headers: dict, body: bytes) -> Txn:
        sig = {k.lower(): v for k, v in headers.items()}.get("x-paystack-signature", "")
        want = hmac.new(self.creds["PAYSTACK_SECRET_KEY"].encode(), body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(sig, want):
            raise PermissionError("Paystack: bad webhook signature")
        ev = json.loads(body)
        d = ev.get("data") or {}
        return self._withdrawal(d) if str(ev.get("event", "")).startswith("transfer.") else self._deposit(d)
