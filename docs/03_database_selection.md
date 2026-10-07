# 数据库选型

## 结论

**PostgreSQL 16（托管版），单库起步。** 推荐 AWS RDS for PostgreSQL（新加坡 `ap-southeast-1` 或马来西亚 `ap-southeast-5`），或者阿里云 RDS PostgreSQL（吉隆坡）。
不需要 Redis、Kafka、ClickHouse，等真正遇到下面"什么时候再加"里的情况再加。

表结构已经写好：[`db/schema.sql`](../db/schema.sql)，并在 Postgres 16 上跑通了同步 → 对账 → API 的完整测试。

## 为什么是 PostgreSQL

对账系统对数据库的要求，按重要性排：

| 要求 | 为什么重要 | PostgreSQL |
|---|---|---|
| **金额精确** | 浮点数会出现 0.01 的对不上 | `NUMERIC` 精确小数 ✅ |
| **幂等写入** | 每 15 分钟回拉最近 2 天，同一笔订单会反复写入，状态会从 pending 变 success | `INSERT … ON CONFLICT DO UPDATE` + 唯一约束 (psp, psp订单号) ✅ |
| **事务** | 同步一批订单 + 写同步日志必须一起成功或一起失败 | 完整 ACID ✅ |
| **JOIN 对账** | CRM 订单 ↔ PSP 订单按订单号、或按客户+金额±0.5%+48 小时匹配 | SQL JOIN / LATERAL ✅ |
| **保留原始报文** | 29 家 PSP 字段各不相同；审计和事后修正字段映射都要原始数据 | `JSONB`，可建索引、可查询 ✅ |
| **报表聚合** | 仪表盘按天 × PSP 汇总 | 视图 `psp_daily`，千万行级别秒出 ✅ |
| 审计、权限 | 财务数据要能查谁改了什么 | 行级权限、pgAudit ✅ |

## 数据量估算

按原型里的业务规模（每家 PSP 每天几百到一千多笔，平均单笔 $140–$1,650）：

| 项 | 估算 |
|---|---|
| PSP 数 | 29 |
| 每天订单（入金 + 出金） | ≈ 3 万 |
| 每年订单行 | ≈ 1,100 万 |
| 每行（含原始 JSON 约 2 KB） | ≈ 22 GB / 年 |

这个量对 PostgreSQL 很小：一台 2 vCPU / 8 GB 的托管实例就够，3 年内不需要分库。超过 5,000 万行时，把 `psp_txn` 改成按月分区即可（PostgreSQL 原生分区，应用代码不用改）。

## 和其他选项的比较

| 选项 | 适合 | 不选的原因 |
|---|---|---|
| **MySQL 8** | 也可以用；团队如果只熟悉 MySQL，可以接受 | JSON 支持和 `ON CONFLICT`、`FILTER`、部分索引等对账常用写法比 PG 弱；改动量约 1 天 |
| MongoDB | 字段不固定的原始数据 | 对账核心是多表 JOIN 和精确金额，文档库做这个要在应用层自己拼，易出错。PG 的 JSONB 已覆盖"存原始报文"的需求 |
| ClickHouse | 亿级行的实时分析 | 不支持真正的 UPDATE（订单状态会变），不适合做主库；量大了可以作为 PG 下游的分析库 |
| BigQuery / Snowflake | 数据仓库、跨部门 BI | 按查询计费，仪表盘每 5 秒刷新会很贵；延迟高，不适合做对账主库 |
| TimescaleDB | PG 插件，时序数据 | 可以以后在同一个 PG 上开启，不是另一套数据库 |

## 部署建议

1. **托管实例**：RDS PostgreSQL 16，Multi-AZ，自动备份保留 35 天，开启时间点恢复（PITR）。财务数据不要自建。
2. **固定出口 IP**：很多 PSP（尤其中国区、东南亚）要求 IP 白名单。同步任务放在有 NAT 网关 / 弹性 IP 的子网里，把这个 IP 发给 PSP。
3. **密钥不进数据库**：PSP 密钥放 AWS Secrets Manager / 阿里云 KMS，同步任务启动时读成环境变量（见 `.env.example`）。
4. **账号分离**：同步任务用可写账号；仪表盘 API 用只读账号（只有 `recon_break` 的状态更新需要写权限）。
5. **只读副本**：以后 BI / 财务要直接写 SQL 查询时，加一个只读副本，不影响同步。

## 表结构一览

```
psp ─┬─ psp_txn          每笔 PSP 订单（入金 / 出金），唯一键 (psp_id, psp_txn_id)，raw JSONB 保留原文
     ├─ wallet_balance   余额快照（每次同步一行）→ 视图 wallet_latest
     ├─ wallet_floor     每个钱包的最低运营余额（运营自己设）
     ├─ settlement       结算单
     ├─ sync_run         每次同步的结果 → 前端"Connections"页的最后同步时间 / 状态
     └─ recon_break      对账差异（金额不符 / 汇率差 / PSP 缺单 / CRM 缺单 / CRM 重复）
crm_txn                  CRM 出入金记录
fx_rate                  每日汇率 → 统一折算 USD
视图 psp_daily           每天 × 每家 PSP 的入金 / 出金 / 笔数 / 成功率 / 手续费 / 平均到账时间
```

## 什么时候再加别的

| 现象 | 再加什么 |
|---|---|
| `psp_txn` 超过 5,000 万行，按天查询变慢 | `psp_txn` 按月分区 |
| 大屏 / 仪表盘并发访问多，API 响应 > 1 秒 | `/api/hub` 结果缓存 1 分钟（Redis 或进程内） |
| Webhook 每秒上百条，或同步任务需要多台机器 | 队列（SQS / RabbitMQ）接 Webhook，后台消费写库 |
| 需要做多年历史的大规模分析 | 每天把 PG 数据同步到 ClickHouse / BigQuery |
