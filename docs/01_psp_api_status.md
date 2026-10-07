# PSP API 对接状态

来源：`All_PSP_5.xlsx`（29 家 PSP，去重后）。完整清单见 [`data/psp_inventory.csv`](../data/psp_inventory.csv)。
更新日期：2026-10-07

## 汇总

| 状态 | 数量 | 说明 |
|---|---|---|
| ✅ 已写好连接器，等密钥测试 | 2 | PayStack、Lipad |
| 📄 已有文档链接，连接器待写 | 3 | Pay247、Letknow Pay、Paysnapper（文档站从开发环境访问被拦截，见下文） |
| 🌐 有公开文档，需要商户密钥 | 2 | Kora Pay、Trust Payments |
| ❌ 没有文档，**需要去要 API** | 22 | 见下表 |

## 仪表盘需要每家 PSP 提供的 5 项能力

| # | 能力 | 用在仪表盘哪里 | 优先级 |
|---|---|---|---|
| 1 | **按时间段查询订单列表**（入金 + 出金，分页） | Overview、PSP 表现、对账 | 必须 |
| 2 | **钱包余额查询**（每个币种） | 钱包与结算 | 必须 |
| 3 | **结算 / 对账单**（API 或每日文件） | 待结算、逾期结算 | 必须 |
| 4 | **单笔订单查询**（按我方订单号） | 对账补查、Webhook 二次确认 | 必须 |
| 5 | **回调（Webhook）+ 签名验证方法** | 实时更新、大屏 | 推荐 |

只有单笔查询、没有列表接口的 PSP（如 Lipad），只能靠 Webhook + CRM 订单号逐笔补查，漏单风险高，必须追问列表接口或每日对账文件。

## 已有文档的 PSP

| PSP | 地区 | 1 列表 | 2 余额 | 3 结算 | 4 单笔 | 5 回调 | 下一步 |
|---|---|---|---|---|---|---|---|
| **PayStack** | 尼日利亚 | ✅ `/transaction` `/transfer` | ✅ `/balance` | ✅ `/settlement` | ✅ `/transaction/verify` | ✅ HMAC-SHA512 | 给 `PAYSTACK_SECRET_KEY`（建议先给 test key） |
| **Lipad** | 肯尼亚 / 坦桑 / 乌干达 | ❌ | ❌ | ❌ | ✅ checkout status | ⚠️ 有 callback_url，无签名说明 | 给 consumer key/secret；**向 Lipad 索取 1、2、3 和回调签名** |
| **Pay247** | 东南亚 / 中东 | ? | ? | ? | ? | ? | 文档站被开发环境拦截，需放行或把文档导出给我 |
| **Letknow Pay** | 加密货币 | ? | ? | ? | ? | ? | 同上 |
| **Paysnapper** | 非洲 | ? | ? | ? | ? | ? | 同上；文档有 sandbox 模拟器（Simulator），拿到 sandbox 密钥就能自己造测试订单 |
| Kora Pay | 加纳 / 肯尼亚 / 尼日利亚 / 南非 / 西非 / 中非 | 公开文档 | 公开文档 | 公开文档 | 公开文档 | 公开文档 | 需要 secret key 后写连接器 |
| Trust Payments | 欧洲卡 | Webservices 查询 | – | 对账报表 | ✅ | ✅ | 需要 site reference + webservices 用户 |

Lipad 的接口来自它在 PyPI / npm 上的官方 SDK 源码（`lipad-sdk` 1.0.5），因为 developer.lipad.io 也被拦了。
Sandbox：`https://checkout.api.uat.lipad.io`；生产：`https://checkout.api.lipad.io`。

## 需要去要 API 的 PSP（22 家）

| 地区 | PSP |
|---|---|
| 东南亚 | 5 Pay、OM Pay、Long77Pay (Payme)、Proxpay、Monetix、Acerpay |
| 中国 | Payexchina、uEnjoy、Now Pay、ChipPay、Bipi Pay、Picotop、NEPay、MT Pay、IBit Pay、Ge-link |
| 非洲 | Kuwa |
| 中东 / 南亚 | Tarspay、Unitedpay、Payok、CheezeePay（表里标 pending） |
| 拉美 | Starpago |

直接用 [`02_psp_api_request.md`](02_psp_api_request.md) 里的模板发给这些 PSP。

## 测试结果（2026-10-07）

| 测试 | 结果 |
|---|---|
| PayStack、Lipad 连接器单元测试（模拟 PSP 服务器：鉴权、分页、金额单位、状态映射、Webhook 签名、错误密钥） | ✅ 11/11 通过 |
| 端到端：同步 → Postgres → 对账 → `/api/hub` → 前端页面（真实 Postgres 16 + Chromium） | ✅ 通过，前端无 JS 报错 |
| 用真实密钥连 PSP sandbox | ⏸️ **未执行**：①没有任何 PSP 的商户密钥；②开发环境的网络策略拦截了所有 PSP 域名 |

拿到密钥后在任何能上网的机器上跑：`python -m scripts.smoke_test`，每家 PSP 输出 PASS / FAIL / SKIP / BLOCKED。
