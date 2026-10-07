"""Common interface every PSP connector implements.

A connector only talks to one PSP and returns data in the unified shape below;
it never touches the database. `sync/run_sync.py` does the storing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Iterator

import httpx

# Unified status / direction vocabulary used by the database and the dashboard.
DIRECTIONS = ("deposit", "withdrawal")
STATUSES = ("pending", "success", "failed", "refunded", "chargeback")


@dataclass
class Txn:
    psp_txn_id: str                  # PSP's own id (unique per PSP)
    direction: str                   # deposit | withdrawal
    status: str                      # pending | success | failed | refunded | chargeback
    amount: Decimal                  # gross amount, in `currency`
    currency: str
    created_at: datetime
    merchant_order_id: str | None = None   # our order id, the main key for CRM matching
    fee: Decimal | None = None
    completed_at: datetime | None = None
    client_ref: str | None = None          # CRM client id when the PSP echoes it back
    method: str | None = None              # bank / qr / mpesa / card / usdt-trc20 ...
    country: str | None = None
    raw: dict = field(default_factory=dict)  # untouched PSP payload, kept for audit


@dataclass
class Balance:
    currency: str
    available: Decimal
    as_of: datetime
    pending: Decimal | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class Settlement:
    ref: str
    amount: Decimal
    currency: str
    status: str                      # pending | paid | failed
    expected_date: datetime | None = None
    settled_at: datetime | None = None
    raw: dict = field(default_factory=dict)


class MissingCredentials(Exception):
    def __init__(self, names: list[str]):
        super().__init__("missing env vars: " + ", ".join(names))
        self.names = names


class NotSupported(Exception):
    """The PSP does not expose this through API (we need to ask them for it)."""


class Connector:
    code: str = ""
    name: str = ""
    env_vars: tuple[str, ...] = ()
    # What this PSP's API can give us. False = must request from PSP or use webhook / report file.
    capabilities: dict[str, bool] = {
        "list_transactions": False,
        "get_transaction": False,
        "balances": False,
        "settlements": False,
        "webhook": False,
        "webhook_signed": False,   # True = payload signature is verified in parse_webhook
    }

    def __init__(self, creds: dict[str, str] | None = None, env: str | None = None,
                 http: httpx.Client | None = None):
        self.creds = creds if creds is not None else self.creds_from_env()
        missing = [n for n in self.env_vars if not self.creds.get(n)]
        if missing:
            raise MissingCredentials(missing)
        prefix = self.code.upper()
        self.env = env or os.getenv(f"{prefix}_ENV") or os.getenv("PSP_ENV", "sandbox")
        self.http = http or httpx.Client(timeout=30)

    @classmethod
    def creds_from_env(cls) -> dict[str, str]:
        return {n: os.getenv(n, "") for n in cls.env_vars}

    # --- override in subclasses -------------------------------------------------
    def healthcheck(self) -> str:
        """Authenticate only; return a short human-readable result."""
        raise NotImplementedError

    def list_transactions(self, start: datetime, end: datetime) -> Iterator[Txn]:
        raise NotSupported(f"{self.name}: no transaction list API")

    def get_transaction(self, ref: str) -> Txn:
        raise NotSupported(f"{self.name}: no single-transaction query API")

    def balances(self) -> list[Balance]:
        raise NotSupported(f"{self.name}: no balance API")

    def settlements(self, start: datetime, end: datetime) -> list[Settlement]:
        raise NotSupported(f"{self.name}: no settlement API")

    def parse_webhook(self, headers: dict, body: bytes) -> Txn:
        raise NotSupported(f"{self.name}: webhook not implemented")


def dec(v) -> Decimal | None:
    if v is None or v == "":
        return None
    return Decimal(str(v))


def parse_dt(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v).astimezone()
    s = str(v).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
