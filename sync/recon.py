"""CRM vs PSP matching. Writes recon_break rows; re-running is safe.

Rule (same as the dashboard footnote):
  1. match on merchant_order_id (the order id we sent to the PSP) - exact;
  2. otherwise same PSP + same client + USD amount within 0.5% + within 48 hours.
Matched pairs that differ: same currency and amount differs -> "Amount mismatch" (usually fee
booked net vs gross); otherwise USD differs by > 0.5% -> "FX difference".
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

TOL = Decimal("0.005")

PAIRS = """
WITH crm AS (
  SELECT * FROM crm_txn WHERE direction='deposit' AND created_at >= %(s)s AND created_at < %(e)s
), psp AS (
  SELECT * FROM psp_txn WHERE direction='deposit' AND status='success'
    AND created_at >= %(s)s - interval '2 days' AND created_at < %(e)s + interval '2 days'
)
SELECT c.id, p.id, c.psp_id, (c.created_at AT TIME ZONE 'UTC')::date, c.usd_amount, p.usd_amount,
       c.currency = p.currency AND c.amount <> p.amount AS amt_diff
FROM crm c
JOIN LATERAL (
  SELECT p.* FROM psp p
  WHERE p.merchant_order_id = c.merchant_order_id
     OR (c.merchant_order_id IS NULL AND p.psp_id = c.psp_id AND p.client_ref = c.client_id
         AND abs(p.usd_amount - c.usd_amount) <= %(tol)s * c.usd_amount
         AND abs(extract(epoch FROM p.created_at - c.created_at)) <= 172800)
  ORDER BY (p.merchant_order_id = c.merchant_order_id) DESC NULLS LAST,
           abs(extract(epoch FROM p.created_at - c.created_at))
  LIMIT 1) p ON true
"""


def _brk(conn, day, pid, typ, cid, tid, cu, pu):
    conn.execute("""INSERT INTO recon_break (day, psp_id, type, crm_txn_id, psp_txn_id, crm_usd, psp_usd)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                 (day, pid, typ, cid, tid, cu, pu))


def reconcile(conn, start: date, end: date) -> dict:
    p = {"s": start, "e": end + timedelta(days=1), "tol": TOL}
    pairs = conn.execute(PAIRS, p).fetchall()
    out = {"matched": 0, "breaks": 0}
    seen: dict[int, int] = {}
    for cid, tid, pid, day, cu, pu, amt_diff in pairs:
        if tid in seen:
            _brk(conn, day, pid, "Duplicate in CRM", cid, tid, cu, pu); out["breaks"] += 1
            continue
        seen[tid] = cid
        if amt_diff:
            _brk(conn, day, pid, "Amount mismatch", cid, tid, cu, pu); out["breaks"] += 1
        elif cu is not None and pu is not None and abs(cu - pu) > TOL * cu:
            _brk(conn, day, pid, "FX difference", cid, tid, cu, pu); out["breaks"] += 1
        else:
            out["matched"] += 1
    matched_crm = {c for c, *_ in pairs}
    for cid, pid, day, cu in conn.execute(
            """SELECT id, psp_id, (created_at AT TIME ZONE 'UTC')::date, usd_amount FROM crm_txn
               WHERE direction='deposit' AND psp_id IS NOT NULL AND created_at >= %(s)s AND created_at < %(e)s""", p):
        if cid not in matched_crm:
            _brk(conn, day, pid, "Missing in PSP", cid, None, cu, None); out["breaks"] += 1
    for tid, pid, day, pu in conn.execute(
            """SELECT id, psp_id, (created_at AT TIME ZONE 'UTC')::date, usd_amount FROM psp_txn
               WHERE direction='deposit' AND status='success' AND created_at >= %(s)s AND created_at < %(e)s""", p):
        if tid not in seen:
            _brk(conn, day, pid, "Missing in CRM", None, tid, None, pu); out["breaks"] += 1
    # A record that arrived late (PSP sync lag, CRM callback retry) closes its earlier "missing" break.
    conn.execute("""UPDATE recon_break SET status='Resolved', resolved_by='auto', resolved_at=now(),
                       note='matched on a later sync'
                    WHERE status <> 'Resolved' AND ((type='Missing in PSP' AND crm_txn_id = ANY(%s))
                                                 OR (type='Missing in CRM' AND psp_txn_id = ANY(%s)))""",
                 (list(matched_crm), list(seen)))
    conn.commit()
    return out
