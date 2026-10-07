"""PSPs whose docs we have links for but could not read from the dev environment
(docs.pay247.io and apidocs.letknow.com are blocked by the sandbox network policy).

These are deliberately empty: endpoints and signing are NOT guessed. To finish one, open its docs,
fill in the four methods following connectors/paystack.py, and set the capabilities flags.
Fields to look for in the docs:
  - auth / signature (HMAC-SHA256? MD5 sorted-params sign? header names, timestamp, nonce)
  - order query (deposit + payout), ideally a LIST by time range with paging
  - balance query (per currency)
  - settlement / statement / report download
  - callback (webhook) format and how to verify its signature
  - sandbox base URL, production base URL, IP whitelist requirement
"""
from __future__ import annotations

from .base import Connector


class _DocsPending(Connector):
    docs_url = ""

    def healthcheck(self) -> str:
        raise NotImplementedError(f"{self.name}: connector not written yet; read {self.docs_url}")


class Pay247Connector(_DocsPending):
    code = "pay247"
    name = "Pay247"
    docs_url = "https://docs.pay247.io"
    env_vars = ("PAY247_MERCHANT_ID", "PAY247_API_KEY", "PAY247_BASE_URL")


class LetknowConnector(_DocsPending):
    code = "letknow"
    name = "Letknow Pay"
    docs_url = "https://apidocs.letknow.com/"
    env_vars = ("LETKNOW_API_KEY", "LETKNOW_API_SECRET", "LETKNOW_BASE_URL")
