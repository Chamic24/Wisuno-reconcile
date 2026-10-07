# Wisuno PSP & CRM 对账系统

把所有 PSP 的出入金、余额、结算通过 API 拉到 PostgreSQL，和 CRM 对账，再给 Ops Hub 前端页面提供数据。

```
PSP API / Webhook ──► connectors/ ──► sync/run_sync.py ──► PostgreSQL ──► api/server.py ──► web/index.html
                      (每家 PSP 一个)   (每 15 分钟，幂等)    (db/schema.sql)   (GET /api/hub)    (Ops Hub 页面)
CRM ─────────────────────────────────────────────────────► crm_txn ──► sync/recon.py（对账，写 recon_break）
```

## 文档

| 文档 | 内容 |
|---|---|
| [docs/01_psp_api_status.md](docs/01_psp_api_status.md) | 29 家 PSP 的 API 状态、测试结果、下一步 |
| [docs/02_psp_api_request.md](docs/02_psp_api_request.md) | 发给 PSP 索取 API 的中英文模板 + 跟踪表 |
| [docs/03_database_selection.md](docs/03_database_selection.md) | 数据库选型（PostgreSQL）及理由 |

## 本地运行

```bash
pip install -r requirements.txt
cp .env.example .env            # 填 DATABASE_URL 和已有的 PSP 密钥
export $(grep -v '^#' .env | xargs)

python -m scripts.smoke_test                 # 先测每家 PSP 能不能连通（只读，不发起支付）
python -m sync.run_sync --init --days 30     # 建表、导入 PSP 清单、拉 30 天数据、对账
uvicorn api.server:app --port 8000           # 打开 http://localhost:8000/
```

前端页面在 `web/index.html`（由上传的原型修改而来）：
- 由 API 服务打开时自动读 `/api/hub`，右上角显示 **Live · API**；
- 单独打开或 API 不通时，自动退回原来的示例数据，显示 **Prototype · sample data**；
- 也可以用 `index.html?api=https://你的API地址` 指定 API。

定时任务：`*/15 * * * * python -m sync.run_sync`

## 测试

```bash
python -m pytest tests                                    # 连接器单元测试（不联网）
TEST_DATABASE_URL=postgresql://…/throwaway python -m pytest tests   # 加上 Postgres 端到端测试（会清空该库）
```

## 新增一家 PSP

1. `data/psp_inventory.csv` 里已有这家 PSP（`code` 列就是连接器代码）。
2. 照 `connectors/paystack.py` 写 `connectors/<code>.py`：实现 `healthcheck`、`list_transactions`、`balances`、`settlements`、`get_transaction`、`parse_webhook` 中 PSP 支持的部分，把字段转换成统一的 `Txn` / `Balance` / `Settlement`。
3. 在 `connectors/__init__.py` 的 `REGISTRY` 里注册，在 `.env.example` 加密钥变量名。
4. 用 `httpx.MockTransport` 照 `tests/fakes.py` 写一个假的 PSP 服务器做单元测试，再用 sandbox 密钥跑 `smoke_test`。
