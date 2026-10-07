"""Pull every connector that has credentials into Postgres, then reconcile.

    python -m sync.run_sync --init             # create tables + seed PSP list
    python -m sync.run_sync                    # sync last 2 days for all PSPs with credentials
    python -m sync.run_sync --psp paystack --days 30

Run it from cron / a scheduler every 15 minutes. Each run is idempotent (upserts), and the
2-day look-back picks up status changes on recent orders (pending -> success, refunds).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from connectors import REGISTRY, MissingCredentials, NotSupported

from . import db
from .recon import reconcile


def run_step(conn, pid: int, kind: str, fn) -> str:
    rid = conn.execute("INSERT INTO sync_run (psp_id, kind) VALUES (%s,%s) RETURNING id", (pid, kind)).fetchone()[0]
    conn.commit()
    try:
        n = fn()
        conn.execute("UPDATE sync_run SET finished_at=now(), ok=true, records=%s WHERE id=%s", (n, rid))
        conn.commit()
        return f"{n} rows"
    except NotSupported as e:
        conn.rollback()
        conn.execute("DELETE FROM sync_run WHERE id=%s", (rid,))
        conn.commit()
        return f"n/a ({e})"
    except Exception as e:  # noqa: BLE001 - logged to sync_run, surfaced on the Connections tab
        conn.rollback()
        conn.execute("UPDATE sync_run SET finished_at=now(), ok=false, error=%s WHERE id=%s",
                     (f"{type(e).__name__}: {e}"[:2000], rid))
        conn.commit()
        return f"ERROR {type(e).__name__}: {e}"


def sync_one(conn, connector, start, end) -> dict:
    pid = db.psp_id(conn, connector.code)
    return {
        "transactions": run_step(conn, pid, "transactions",
                                 lambda: db.upsert_txns(conn, pid, connector.list_transactions(start, end))),
        "balances": run_step(conn, pid, "balances", lambda: db.insert_balances(conn, pid, connector.balances())),
        "settlements": run_step(conn, pid, "settlements",
                                lambda: db.upsert_settlements(conn, pid, connector.settlements(start - timedelta(days=30), end))),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--psp", action="append")
    ap.add_argument("--days", type=int, default=2)
    a = ap.parse_args(argv)
    conn = db.connect()
    if a.init:
        db.init_schema(conn)
        print("schema ready")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=a.days)
    for code in a.psp or REGISTRY:
        try:
            c = REGISTRY[code]()
        except MissingCredentials as e:
            print(f"{code}: skipped, {e}")
            continue
        print(code, sync_one(conn, c, start, end))
    print("recon:", reconcile(conn, start.date(), end.date()))


if __name__ == "__main__":
    main()
