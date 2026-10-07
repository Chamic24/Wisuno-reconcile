"""Database helpers: schema setup, PSP seeding, idempotent upserts."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from connectors import Balance, Settlement, Txn

ROOT = Path(__file__).resolve().parent.parent


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or os.environ["DATABASE_URL"], autocommit=False)


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute((ROOT / "db" / "schema.sql").read_text())
    with open(ROOT / "data" / "psp_inventory.csv", newline="") as f:
        for r in csv.DictReader(f):
            conn.execute(
                """INSERT INTO psp (code, name, region, category, api_status)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, region=EXCLUDED.region,
                     category=EXCLUDED.category""",
                (r["code"], r["name"], r["region"], r["category"] or None, r["api_status"]))
    for cur in ("USD", "USDT"):
        conn.execute("INSERT INTO fx_rate VALUES (DATE '2000-01-01', %s, 1) ON CONFLICT DO NOTHING", (cur,))
    conn.commit()


def psp_id(conn: psycopg.Connection, code: str) -> int:
    row = conn.execute("SELECT id FROM psp WHERE code=%s", (code,)).fetchone()
    if not row:
        raise KeyError(f"PSP {code!r} not in psp table (add it to data/psp_inventory.csv)")
    return row[0]


def _raw(d: dict) -> Jsonb:
    return Jsonb(json.loads(json.dumps(d, default=str)))


USD_SQL = """(SELECT %(v)s * usd_rate FROM fx_rate
              WHERE currency=%(cur)s AND day <= %(ts)s::date ORDER BY day DESC LIMIT 1)"""


def upsert_txns(conn: psycopg.Connection, pid: int, txns) -> int:
    n = 0
    for t in txns:
        t: Txn
        p = dict(pid=pid, id=t.psp_txn_id, order=t.merchant_order_id, dir=t.direction, st=t.status,
                 amt=t.amount, cur=t.currency.upper(), fee=t.fee, client=t.client_ref, method=t.method,
                 country=(t.country or None) and t.country[:2].upper(), ts=t.created_at, done=t.completed_at,
                 raw=_raw(t.raw))
        conn.execute(f"""
            INSERT INTO psp_txn (psp_id, psp_txn_id, merchant_order_id, direction, status, amount, currency,
                                 fee, usd_amount, usd_fee, client_ref, method, country, created_at, completed_at, raw)
            VALUES (%(pid)s, %(id)s, %(order)s, %(dir)s, %(st)s, %(amt)s, %(cur)s, %(fee)s,
                    {USD_SQL % dict(v='%(amt)s', cur='%(cur)s', ts='%(ts)s')},
                    {USD_SQL % dict(v='%(fee)s', cur='%(cur)s', ts='%(ts)s')},
                    %(client)s, %(method)s, %(country)s, %(ts)s, %(done)s, %(raw)s)
            ON CONFLICT (psp_id, psp_txn_id) DO UPDATE SET
                status=EXCLUDED.status, fee=coalesce(EXCLUDED.fee, psp_txn.fee),
                usd_fee=coalesce(EXCLUDED.usd_fee, psp_txn.usd_fee),
                completed_at=coalesce(EXCLUDED.completed_at, psp_txn.completed_at),
                merchant_order_id=coalesce(EXCLUDED.merchant_order_id, psp_txn.merchant_order_id),
                client_ref=coalesce(EXCLUDED.client_ref, psp_txn.client_ref),
                raw=EXCLUDED.raw, updated_at=now()""", p)
        n += 1
    return n


def insert_balances(conn: psycopg.Connection, pid: int, bals: list[Balance]) -> int:
    for b in bals:
        conn.execute("""INSERT INTO wallet_balance (psp_id, currency, available, pending, as_of, raw)
                        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                     (pid, b.currency.upper(), b.available, b.pending, b.as_of, _raw(b.raw)))
    return len(bals)


def upsert_settlements(conn: psycopg.Connection, pid: int, rows: list[Settlement]) -> int:
    for s in rows:
        conn.execute("""INSERT INTO settlement (psp_id, ref, amount, currency, status, expected_date, settled_at, raw)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (psp_id, ref) DO UPDATE SET status=EXCLUDED.status,
                          settled_at=EXCLUDED.settled_at, raw=EXCLUDED.raw""",
                     (pid, s.ref, s.amount, s.currency.upper(), s.status,
                      s.expected_date.date() if s.expected_date else None, s.settled_at, _raw(s.raw)))
    return len(rows)
