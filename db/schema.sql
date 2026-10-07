-- PSP & CRM reconciliation store. PostgreSQL 15+.
-- Money is NUMERIC (never float). All timestamps are timestamptz, stored in UTC.
-- Layers: raw PSP payload (raw jsonb) -> unified rows (psp_txn) -> daily view the dashboard reads.

CREATE TABLE IF NOT EXISTS psp (
    id              smallserial PRIMARY KEY,
    code            text UNIQUE NOT NULL,          -- matches connectors.REGISTRY key
    name            text NOT NULL,
    region          text,
    category        text,                          -- E-wallet / Bank transfer / Crypto · USDT ...
    conn_method     text NOT NULL DEFAULT 'API',   -- API | Webhook | SFTP | CSV upload
    sync_freq       text NOT NULL DEFAULT 'Every 15 min',
    api_status      text NOT NULL DEFAULT 'docs_needed', -- docs_needed | docs_received | creds_needed | sandbox_ok | live
    dep_fee_rate    numeric(8,5),                  -- contract rate, used to explain amount mismatches
    wd_fee_rate     numeric(8,5),
    active          boolean NOT NULL DEFAULT true
);

-- One row per PSP transaction (deposit or withdrawal), upserted on every sync.
CREATE TABLE IF NOT EXISTS psp_txn (
    id                bigserial PRIMARY KEY,
    psp_id            smallint NOT NULL REFERENCES psp(id),
    psp_txn_id        text NOT NULL,
    merchant_order_id text,
    direction         text NOT NULL CHECK (direction IN ('deposit','withdrawal')),
    status            text NOT NULL CHECK (status IN ('pending','success','failed','refunded','chargeback')),
    amount            numeric(24,8) NOT NULL,
    currency          text NOT NULL,
    fee               numeric(24,8),
    usd_amount        numeric(20,4),               -- filled from fx_rate at created_at date
    usd_fee           numeric(20,4),
    client_ref        text,
    method            text,
    country           char(2),
    created_at        timestamptz NOT NULL,
    completed_at      timestamptz,
    raw               jsonb NOT NULL DEFAULT '{}',
    first_seen_at     timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (psp_id, psp_txn_id)
);
CREATE INDEX IF NOT EXISTS psp_txn_created ON psp_txn (created_at, psp_id);
CREATE INDEX IF NOT EXISTS psp_txn_order   ON psp_txn (merchant_order_id);
CREATE INDEX IF NOT EXISTS psp_txn_client  ON psp_txn (client_ref, created_at);

-- Balance snapshots: one row per PSP/currency per sync. Latest row = current balance.
CREATE TABLE IF NOT EXISTS wallet_balance (
    psp_id     smallint NOT NULL REFERENCES psp(id),
    currency   text NOT NULL,
    available  numeric(24,8) NOT NULL,
    pending    numeric(24,8),
    as_of      timestamptz NOT NULL,
    raw        jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (psp_id, currency, as_of)
);
CREATE TABLE IF NOT EXISTS wallet_floor (          -- minimum operating balance (ops sets this)
    psp_id      smallint NOT NULL REFERENCES psp(id),
    currency    text NOT NULL,
    min_balance numeric(24,8) NOT NULL,
    PRIMARY KEY (psp_id, currency)
);

CREATE TABLE IF NOT EXISTS settlement (
    psp_id        smallint NOT NULL REFERENCES psp(id),
    ref           text NOT NULL,
    amount        numeric(24,8) NOT NULL,
    currency      text NOT NULL,
    status        text NOT NULL,                  -- pending | paid | failed
    expected_date date,
    settled_at    timestamptz,
    raw           jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (psp_id, ref)
);

CREATE TABLE IF NOT EXISTS fx_rate (               -- 1 unit of currency = usd_rate USD
    day      date NOT NULL,
    currency text NOT NULL,
    usd_rate numeric(20,10) NOT NULL,
    PRIMARY KEY (day, currency)
);

-- CRM side, loaded by the CRM connector (API or read replica).
CREATE TABLE IF NOT EXISTS crm_txn (
    id                bigserial PRIMARY KEY,
    crm_txn_id        text UNIQUE NOT NULL,
    client_id         text NOT NULL,
    client_name       text,
    psp_id            smallint REFERENCES psp(id),
    merchant_order_id text,                       -- the order id we sent to the PSP
    direction         text NOT NULL CHECK (direction IN ('deposit','withdrawal')),
    status            text NOT NULL,
    amount            numeric(24,8) NOT NULL,
    currency          text NOT NULL,
    usd_amount        numeric(20,4),
    created_at        timestamptz NOT NULL,
    raw               jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS crm_txn_order ON crm_txn (merchant_order_id);

CREATE TABLE IF NOT EXISTS recon_break (
    id          bigserial PRIMARY KEY,
    day         date NOT NULL,
    psp_id      smallint NOT NULL REFERENCES psp(id),
    type        text NOT NULL,     -- Amount mismatch | FX difference | Missing in PSP | Missing in CRM | Duplicate in CRM
    crm_txn_id  bigint REFERENCES crm_txn(id),
    psp_txn_id  bigint REFERENCES psp_txn(id),
    crm_usd     numeric(20,4),
    psp_usd     numeric(20,4),
    status      text NOT NULL DEFAULT 'Open',     -- Open | Investigating | Resolved
    note        text,
    resolved_by text,
    resolved_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (type, crm_txn_id, psp_txn_id)
);

-- Every connector run. Feeds the "Connections" tab (last sync, records, status).
CREATE TABLE IF NOT EXISTS sync_run (
    id          bigserial PRIMARY KEY,
    psp_id      smallint REFERENCES psp(id),
    kind        text NOT NULL,                    -- transactions | balances | settlements | webhook
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    ok          boolean,
    records     integer NOT NULL DEFAULT 0,
    error       text
);
CREATE INDEX IF NOT EXISTS sync_run_recent ON sync_run (psp_id, started_at DESC);

-- What the dashboard's per-PSP daily series is built from.
-- Success rate = successful deposits / all deposit attempts (pending excluded).
CREATE OR REPLACE VIEW psp_daily AS
SELECT psp_id,
       (created_at AT TIME ZONE 'UTC')::date                                                    AS day,
       coalesce(sum(usd_amount) FILTER (WHERE direction='deposit'    AND status='success'),0)   AS dep,
       coalesce(sum(usd_amount) FILTER (WHERE direction='withdrawal' AND status='success'),0)   AS wd,
       count(*)                 FILTER (WHERE direction='deposit'    AND status='success')      AS cnt,
       count(*)                 FILTER (WHERE direction='deposit'    AND status<>'pending')     AS att,
       coalesce(sum(usd_fee)    FILTER (WHERE direction='deposit'    AND status='success'),0)   AS fees,
       coalesce(sum(usd_fee)    FILTER (WHERE direction='withdrawal' AND status='success'),0)   AS wfees,
       avg(extract(epoch FROM completed_at - created_at)/60)
                                FILTER (WHERE direction='deposit' AND status='success')         AS proc_min
FROM psp_txn
GROUP BY 1, 2;

CREATE OR REPLACE VIEW wallet_latest AS
SELECT DISTINCT ON (psp_id, currency) psp_id, currency, available, pending, as_of
FROM wallet_balance ORDER BY psp_id, currency, as_of DESC;
