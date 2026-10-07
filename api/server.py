"""HTTP API the Ops Hub page reads.

    uvicorn api.server:app --port 8000
    open http://localhost:8000/        (serves web/index.html, which calls /api/hub)

GET  /api/hub?days=366        everything the dashboard renders, already in the shapes it uses
POST /api/breaks/{id}/resolve mark a reconciliation break resolved
POST /webhooks/{psp_code}     PSP callbacks (verified by the connector, then upserted)
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from connectors import REGISTRY, NotSupported
from sync import db

app = FastAPI(title="Wisuno PSP & CRM Ops Hub API")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["GET", "POST"], allow_headers=["*"])
WEB = Path(__file__).resolve().parent.parent / "web" / "index.html"


@contextmanager
def conn():
    c = db.connect()
    try:
        yield c
    finally:
        c.close()


def f(v) -> float:
    return float(v) if v is not None else 0.0


@app.get("/")
def index():
    return FileResponse(WEB)


@app.get("/api/hub")
def hub(days: int = 366):
    days = max(30, min(days, 1100))
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    dates = [start + timedelta(days=i) for i in range(days)]
    with conn() as c:
        psps = c.execute("""
            SELECT p.id, p.code, p.name, coalesce(p.category,''), p.conn_method, p.sync_freq,
                   p.dep_fee_rate, p.wd_fee_rate
            FROM psp p
            WHERE p.active AND (EXISTS (SELECT 1 FROM psp_txn t WHERE t.psp_id=p.id AND t.created_at >= %s)
                             OR EXISTS (SELECT 1 FROM wallet_balance w WHERE w.psp_id=p.id))
            ORDER BY p.name""", (start,)).fetchall()
        ids = [p[0] for p in psps]
        series = {pid: [None] * days for pid in ids}
        for pid, day, dep, wd, cnt, att, fees, wfees, proc in c.execute(
                "SELECT * FROM psp_daily WHERE day >= %s AND psp_id = ANY(%s)", (start, ids)):
            series[pid][(day - start).days] = {"dep": f(dep), "wd": f(wd), "cnt": cnt, "att": att,
                                               "fees": f(fees), "wfees": f(wfees), "proc": f(proc)}
        zero = {"dep": 0, "wd": 0, "cnt": 0, "att": 0, "fees": 0, "wfees": 0, "proc": 0}
        out_psps = []
        for pid, code, name, cat, method, freq, dfee, wfee in psps:
            s = [r or dict(zero) for r in series[pid]]
            series[pid] = s
            last30 = s[-30:]
            dep30, cnt30 = sum(r["dep"] for r in last30), sum(r["cnt"] for r in last30)
            out_psps.append({"id": code, "name": name, "type": cat, "method": method, "freq": freq,
                             "fee": f(dfee) or (sum(r["fees"] for r in last30) / dep30 if dep30 else 0),
                             "wfee": f(wfee), "base": dep30 / 30, "ticket": dep30 / cnt30 if cnt30 else 0})
        code_of = {p[0]: p[1] for p in psps}

        fx = {cur: f(rate) for cur, rate in c.execute(
            "SELECT DISTINCT ON (currency) currency, usd_rate FROM fx_rate ORDER BY currency, day DESC")}

        wallets: dict[str, list] = {}
        for pid, cur, avail, floor in c.execute("""
                SELECT w.psp_id, w.currency, w.available, coalesce(fl.min_balance, 0)
                FROM wallet_latest w LEFT JOIN wallet_floor fl USING (psp_id, currency)
                WHERE w.psp_id = ANY(%s) ORDER BY 1, 2""", (ids,)):
            wallets.setdefault(code_of[pid], []).append([cur, f(avail), f(floor)])

        settle = [{"psp": code_of[pid], "ref": ref, "amt": f(amt), "cur": cur, "exp": exp.isoformat(),
                   "age": max(0, (today - exp).days)}
                  for pid, ref, amt, cur, exp in c.execute("""
                SELECT psp_id, ref, amount, currency, expected_date FROM settlement
                WHERE status='pending' AND expected_date IS NOT NULL AND psp_id = ANY(%s)""", (ids,))]

        breaks = []
        for bid, day, pid, typ, cu, pu, st, client, cname, ptx in c.execute("""
                SELECT b.id, b.day, b.psp_id, b.type, b.crm_usd, b.psp_usd, b.status,
                       ct.client_id, ct.client_name, coalesce(pt.psp_txn_id, ct.merchant_order_id)
                FROM recon_break b LEFT JOIN crm_txn ct ON ct.id=b.crm_txn_id LEFT JOIN psp_txn pt ON pt.id=b.psp_txn_id
                WHERE b.day >= %s AND b.psp_id = ANY(%s)""", (start, ids)):
            breaks.append({"id": f"BRK-{bid}", "di": (day - start).days, "psp": code_of[pid], "type": typ,
                           "ago": (today - day).days, "date": day.isoformat(), "client": client or "—",
                           "cname": cname or "—", "crm": None if cu is None else f(cu),
                           "pspAmt": None if pu is None else f(pu), "txn": ptx or "—", "status": st})
        breaks.sort(key=lambda b: b["ago"])

        # Daily reconciliation report: real CRM vs PSP counts per PSP per day.
        recon = {pid: [{"crmCnt": 0, "crmAmt": 0.0, "pspCnt": r["cnt"], "pspAmt": r["dep"], "matched": 0}
                       for r in series[pid]] for pid in ids}
        for pid, day, n, amt, broken in c.execute("""
                SELECT ct.psp_id, (ct.created_at AT TIME ZONE 'UTC')::date, count(*), coalesce(sum(ct.usd_amount),0),
                       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM recon_break b
                                                      WHERE b.crm_txn_id=ct.id AND b.status <> 'Resolved'))
                FROM crm_txn ct
                WHERE ct.direction='deposit' AND ct.created_at >= %s AND ct.psp_id = ANY(%s) GROUP BY 1, 2""",
                (start, ids)):
            if 0 <= (day - start).days < days:
                recon[pid][(day - start).days].update(crmCnt=n, crmAmt=f(amt), matched=n - broken)

        now = datetime.now(timezone.utc)
        conns = []
        for pid, code, name, cat, method, freq, *_ in psps:
            last, rec = c.execute("""
                SELECT (SELECT max(finished_at) FROM sync_run WHERE psp_id=%s AND ok),
                       (SELECT count(*) FROM psp_txn WHERE psp_id=%s AND updated_at > now() - interval '24 hours')""",
                                  (pid, pid)).fetchone()
            conns.append({"name": name, "cat": "PSP · " + (cat or "—"), "method": method, "freq": freq,
                          "last": (now - last).total_seconds() / 60 if last else 1e6, "rec": rec, "pspId": code})

    return {"source": "live", "generated_at": now.isoformat(), "dates": [d.isoformat() for d in dates],
            "psps": out_psps, "daily": [series[p[0]] for p in psps], "fx": fx,
            "wallets": [{"psp": k, "cur": v} for k, v in wallets.items()],
            "settle": settle, "breaks": breaks, "conns": conns,
            "recon": [recon[p[0]] for p in psps]}


@app.post("/api/breaks/{bid}/resolve")
def resolve_break(bid: str, request: Request):
    n = int(bid.removeprefix("BRK-"))
    with conn() as c:
        r = c.execute("""UPDATE recon_break SET status='Resolved', resolved_at=now(), resolved_by=%s
                         WHERE id=%s RETURNING id""", (request.headers.get("x-user", "dashboard"), n)).fetchone()
        c.commit()
    if not r:
        raise HTTPException(404, "break not found")
    return {"ok": True}


@app.post("/webhooks/{code}")
async def webhook(code: str, request: Request):
    cls = REGISTRY.get(code)
    if not cls:
        raise HTTPException(404, "unknown PSP")
    connector = cls()
    body = await request.body()
    try:
        txn = connector.parse_webhook(dict(request.headers), body)
    except NotSupported:
        raise HTTPException(404, "webhook not supported for this PSP")
    except PermissionError as e:
        raise HTTPException(401, str(e))
    if not connector.capabilities.get("webhook_signed"):
        # No documented signature: trust only what the status API confirms.
        try:
            txn = connector.get_transaction(txn.merchant_order_id or txn.psp_txn_id)
        except NotSupported:
            pass
    with conn() as c:
        pid = db.psp_id(c, code)
        db.upsert_txns(c, pid, [txn])
        c.execute("INSERT INTO sync_run (psp_id, kind, finished_at, ok, records) VALUES (%s,'webhook',now(),true,1)", (pid,))
        c.commit()
    return {"ok": True}
