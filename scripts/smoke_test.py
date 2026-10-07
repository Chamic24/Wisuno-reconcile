"""Connectivity test for every connector that has credentials set.

    python -m scripts.smoke_test            # all connectors
    python -m scripts.smoke_test lipad      # one connector
    python -m scripts.smoke_test lipad --order ORDER123   # also query one order

Result per check: PASS / FAIL / SKIP (no credentials or not supported) / BLOCKED (network).
Writes reports/smoke_<timestamp>.md. Read-only: never creates payments or payouts.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from connectors import REGISTRY, MissingCredentials, NotSupported


def run_check(fn):
    try:
        return "PASS", fn()
    except NotSupported as e:
        return "SKIP", f"not in API: {e}"
    except NotImplementedError as e:
        return "SKIP", str(e)
    except (httpx.ConnectError, httpx.ProxyError, httpx.ConnectTimeout) as e:
        return "BLOCKED", f"network: {e}"
    except Exception as e:  # noqa: BLE001 - report everything
        return "FAIL", f"{type(e).__name__}: {e}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="*")
    ap.add_argument("--order", help="merchant order id to look up with get_transaction")
    ap.add_argument("--days", type=int, default=1)
    a = ap.parse_args(argv)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=a.days)
    rows = []
    for code in a.codes or REGISTRY:
        cls = REGISTRY[code]
        try:
            c = cls()
        except MissingCredentials as e:
            rows.append((cls.name, "credentials", "SKIP", "set " + ", ".join(e.names)))
            continue
        rows.append((c.name, "auth", *run_check(c.healthcheck)))
        if rows[-1][2] != "PASS":
            continue
        rows.append((c.name, "balances", *run_check(lambda: "; ".join(
            f"{b.currency} {b.available}" for b in c.balances()) or "no wallets")))
        rows.append((c.name, f"transactions {a.days}d", *run_check(lambda: f"{sum(1 for _ in c.list_transactions(start, end))} rows")))
        rows.append((c.name, "settlements", *run_check(lambda: f"{len(c.settlements(start - timedelta(days=30), end))} rows")))
        if a.order:
            rows.append((c.name, f"order {a.order}", *run_check(lambda: (lambda t: f"{t.status} {t.amount} {t.currency}")(c.get_transaction(a.order)))))
    out = ["| PSP | Check | Result | Detail |", "|---|---|---|---|"]
    out += [f"| {r[0]} | {r[1]} | {r[2]} | {str(r[3]).replace('|', '/')[:200]} |" for r in rows]
    text = "\n".join(out)
    print(text)
    Path("reports").mkdir(exist_ok=True)
    Path(f"reports/smoke_{end:%Y%m%d_%H%M%S}.md").write_text(text + "\n")
    return 1 if any(r[2] == "FAIL" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
