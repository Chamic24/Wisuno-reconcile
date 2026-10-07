# Reconciliation Database: Choice and Cost

Oct 7, 2026 · Simon

## Recommendation

**Use managed PostgreSQL 16 (AWS RDS); the production database costs about US$250–370 a month.** We recommend the AWS Malaysia region (about 15% cheaper than Singapore), on db.m7g.large (2 vCPU, 8 GB), Multi-AZ, with 100 GB of storage.

- On-demand: about **US$315 / month** in Malaysia, US$369 / month in Singapore.
- Once we know we'll keep it, a 1-year reserved instance (no upfront) brings it to about **US$249 / month**.
- A test environment adds about US$69 / month.

Reconciliation needs exact money amounts, no double-counting when the same data is synced again, and matching across tables; PostgreSQL does all three natively. At the estimated volume (about 11 million orders a year), this setup needs no upgrade for 3 years.

## Why PostgreSQL

Reconciliation puts 6 hard requirements on the database; PostgreSQL meets all of them natively, with nothing to patch in our own code.

| Requirement | Why it matters | How PostgreSQL handles it |
| --- | --- | --- |
| Exact money amounts | Floating point leaves 0.01 differences that never reconcile | NUMERIC exact decimals |
| No double-counting on re-sync | Every 15 minutes we re-pull the last 2 days, so the same order is written again and its status moves from pending to success | Unique key + insert-or-update (ON CONFLICT) |
| Transactions | A batch of orders and its sync log must succeed or fail together | Full ACID |
| Cross-table matching | CRM orders match PSP orders by order ID, or by client + amount ±0.5% + 48 hours | SQL JOINs |
| Keep raw PSP payloads | 29 PSPs, all with different fields; audits and later fixes need the original | JSONB, queryable and indexable |
| Audit and access control | Finance data must show who changed what | Row-level security, pgAudit |

The schema is already written and the full sync → reconcile → dashboard flow has been tested end to end on PostgreSQL 16.

## Data volume estimate

About 11 million orders and 22 GB a year, which is small for PostgreSQL. The estimate uses the business volume in the dashboard prototype: a few hundred to just over a thousand orders per PSP per day.

| Item | Estimate |
| --- | --- |
| PSPs | 29 |
| Orders per day (deposits + withdrawals) | ~30,000 |
| Orders per year | ~11 million |
| Storage per year (~2 KB per order incl. raw payload) | ~22 GB |

Even at 5× this volume the setup below is enough; only storage needs adding earlier, at about US$25 / month per extra 100 GB.

## Cost

The recommended setup in the Malaysia region costs about US$315 / month on demand, or about US$249 / month (about US$3,000 a year) on a 1-year reserved instance. Prices come from AWS's official price list (published 2026-10-06), at 730 hours a month, in US dollars, before tax.

| Setup | Use | Malaysia (US$/month) | Singapore (US$/month) |
| --- | --- | --- | --- |
| db.t4g.medium (2 vCPU, 4 GB) Single-AZ, 20 GB | Test environment | 69 | 77 |
| db.t4g.medium (2 vCPU, 4 GB) Multi-AZ, 50 GB | Minimum production | 146 | 162 |
| **db.m7g.large (2 vCPU, 8 GB) Multi-AZ, 100 GB** | **Recommended production** | **315** | **369** |
| Same, 1-year reserved (no upfront) | Once we commit long term | 249 | 291 |

- **Why Multi-AZ**: if one machine fails, a standby takes over automatically, so reconciliation and the screen board keep running. Instance cost is 2× Single-AZ.
- **Why m7g rather than the cheaper t4g**: t4g is burstable; sustained load is billed extra as CPU credits (US$0.075 per vCPU-hour). Syncing every 15 minutes plus reconciliation is steady load, so m7g keeps cost predictable. On a tight budget, start on t4g and upgrade in one click later.
- **Backups**: free up to the database size; beyond that about US$0.09 per GB-month.
- **Not included**: the server running the sync jobs and API, and the fixed egress IP registered with PSPs (not priced here).
- **Why not self-host**: installing PostgreSQL on our own cloud server could roughly halve the machine cost, but backups, failover and patching become our job. Not worth it for finance data.
- Alibaba Cloud's Kuala Lumpur region is also an option; its official prices were not checked this time and can be added if needed.

## Compared with other options

MySQL is the only workable alternative; the others do not suit a reconciliation database.

| Option | Good for | Why not | Cost compared |
| --- | --- | --- | --- |
| **PostgreSQL (recommended)** | Reconciliation database | — | See Cost |
| MySQL 8 | Could also run reconciliation | Weaker at storing raw payloads and conditional aggregation; porting the existing code takes about 1 day | Same AWS price for the same size, no saving |
| MongoDB | Data without a fixed shape | Reconciliation relies on cross-table matching and exact amounts, which a document store pushes into our code and makes error-prone; PostgreSQL already stores raw payloads | Managed plans are usually no cheaper, plus one more system to run |
| ClickHouse | Analytics on billions of rows | Poor at updating existing rows, and order status changes; only fits later as an analytics copy | Extra system and staff time we don't need yet |
| BigQuery / Snowflake | Company-wide data warehouse | Billed per query, so a screen board refreshing every few seconds gets expensive; higher latency | Grows with usage, monthly bill hard to predict |

## Deployment and scaling

Set up these 5 things at launch; add anything else only when the matching situation below appears.

1. **Automatic backups** kept for 35 days, with point-in-time restore on.
2. **Fixed egress IP**: sync jobs reach PSPs from one fixed IP, which we give to PSPs that require whitelisting.
3. **No credentials in the database**: PSP credentials live in AWS Secrets Manager.
4. **Separate accounts**: sync jobs use a write account; the dashboard uses a read-only account.
5. **Run on demand for 1–2 months** to confirm the size, then buy the reserved instance.

| When | Add | Approx. cost |
| --- | --- | --- |
| Orders table passes 50 million rows and daily queries slow down | Partition the orders table by month (no code change) | Free |
| Storage nearly full | More storage | ~US$25 / month per 100 GB |
| Finance wants to write SQL reports directly | A read replica | About the Single-AZ instance price |
| Screen board traffic grows and the API takes over 1 second | Cache results for 1 minute | Free (done in code first) |
| Multi-year historical analysis | Daily copy into ClickHouse / BigQuery | Assess at the time |

## Sources

- [AWS RDS official price list: Singapore, ap-southeast-1](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/ap-southeast-1/index.csv) (published 2026-10-06)
- [AWS RDS official price list: Malaysia, ap-southeast-5](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/ap-southeast-5/index.csv) (published 2026-10-06)
