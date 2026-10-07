# PSP API Onboarding Checklist

Oct 7, 2026 · Simon

## Overview

We want to pull deposits, withdrawals, balances and settlements from all 29 PSPs into the reconciliation system by API, instead of downloading reports by hand. Each PSP needs to provide the 8 items in the next section; without the first 4 we cannot connect at all.

- **Who asks**: the colleague who owns the relationship with that PSP (the "Owner" column below).
- **Once received**: send the docs and credentials to the tech team. Never paste credentials in group chats or email bodies; use a password manager or an encrypted file.
- **Read-only access is enough**: we only query data and never create payments with these credentials, so PSPs usually approve faster.

## The 8 items to request from each PSP

| # | Item | Required? | What we use it for |
| --- | --- | --- | --- |
| 1 | **API documentation** (link or PDF), including the signature / authentication method and a signing example. If the online docs have a Download button, also download the OpenAPI file (.json / .yaml) | Required | Writing the integration |
| 2 | **Sandbox** base URL + test credentials; **production** base URL | Required | Test end to end in sandbox before going live |
| 3 | **Transaction list by time range** endpoint: both deposits (pay-in) and withdrawals (payout), with paging; ask for the maximum time range and page size | Required | Dashboard amounts, counts, success rate; reconciliation |
| 4 | **Balance** endpoint (available and frozen balance per currency) | Required | Wallet balances, low-balance alerts |
| 5 | **Settlement / statement reports**: API or daily file (SFTP / email), with settlement ID, amount, fees and settlement date | Important | Pending and overdue settlements |
| 6 | **Callback (webhook) format + how to verify its signature** | Important | Real-time updates, ops screen board |
| 7 | **Status values** and their meaning; whether amounts are gross or net of fees | Important | Stops fees showing up as reconciliation breaks |
| 8 | **IP whitelist** requirements, rate limits, and the timezone of timestamps | Important | Registering our server IPs at deployment |

If a PSP only offers a single-order lookup and no transaction list (e.g. Lipad), keep pushing for item 3 or a daily statement file; otherwise orders will be missed.

## To-do by PSP

Of the 29 PSPs, the first 7 already have docs (received or public) but all still need **test credentials**; the other 22 must start from item 1. Owners: please fill in the "Progress" column (Not sent / Sent, awaiting reply / Docs received / Credentials received / Connected).

| PSP | Region | What to request | Owner | Progress |
| --- | --- | --- | --- | --- |
| Lipad | Kenya / Tanzania / Uganda | Test credentials; **push for items 3, 4, 5 and webhook signature** (current API only looks up single orders) |  | Docs received |
| Pay247 | Southeast Asia / Middle East | Test credentials; docs exported as PDF or OpenAPI file |  | Docs received |
| Letknow Pay | Crypto | Test credentials; docs exported as PDF or OpenAPI file |  | Docs received |
| Paysnapper | Africa | Test credentials (docs include a simulator for creating test orders); docs exported as OpenAPI file |  | Docs received |
| PayStack | Nigeria | Test secret key; integration already written |  | Docs received |
| Kora Pay | Multiple African countries | Test credentials (public docs available) |  | Docs received |
| Trust Payments | European cards | Site reference + Webservices user |  | Docs received |
| 5 Pay | Southeast Asia | All 8 items |  |  |
| OM Pay | Southeast Asia / Crypto | All 8 items |  |  |
| Long77Pay (Payme) | Southeast Asia | All 8 items |  |  |
| Proxpay | Southeast Asia | All 8 items |  |  |
| Monetix | Southeast Asia / Middle East | All 8 items |  |  |
| Acerpay | Southeast Asia / Middle East / Latin America | All 8 items |  |  |
| Payexchina | China | All 8 items |  |  |
| uEnjoy | China | All 8 items |  |  |
| Now Pay | China | All 8 items |  |  |
| ChipPay | China / Crypto | All 8 items |  |  |
| Bipi Pay | China | All 8 items |  |  |
| Picotop | China | All 8 items |  |  |
| NEPay | China | All 8 items |  |  |
| MT Pay | China | All 8 items |  |  |
| IBit Pay | China | All 8 items |  |  |
| Ge-link | China | All 8 items |  |  |
| Kuwa | Africa | All 8 items |  |  |
| Tarspay | Middle East / Latin America | All 8 items |  |  |
| Unitedpay | Egypt | All 8 items |  |  |
| Payok | Middle East / Latin America | All 8 items |  |  |
| CheezeePay | India | All 8 items (marked pending in the sheet; confirm first whether we still work with them) |  |  |
| Starpago | Latin America | All 8 items |  |  |

## Email templates

Replace the {braces} and send. Use the Chinese version for PSPs in China and the English version for the rest. Our egress IPs can be added later, once the servers are set up.

### English

```
Subject: API access request for reporting & reconciliation – Wisuno

Hi {name},

We are building an internal reconciliation system and want to pull our data
from {PSP} by API. Read-only access is enough; we will not create payments
with these credentials. Could you send us:

1. API documentation (link or PDF), including the signature method and a
   signing example.
2. Sandbox base URL + test credentials, and the production base URL.
3. A transaction list endpoint by time range, for both deposits and payouts,
   with paging (max range and page size).
4. A balance endpoint per currency (available and frozen).
5. Settlement reports (API or daily file).
6. Webhook payload format and how to verify its signature.
7. Status values and their meaning; whether amounts are gross or net of fees.
8. IP whitelist requirements, rate limits, and the timezone of timestamps.

Thank you,
{your name}, Wisuno Finance & Operations
```

### Chinese (for PSPs in China)

```
主题：Wisuno 申请对账 / 报表 API 权限

{称呼} 您好，

我们正在搭建内部对账系统，希望通过 API 直接拉取我们在 {PSP} 的数据。
只需只读权限，不会用这套密钥发起支付。麻烦提供：

1. API 文档（链接或 PDF），含签名方式和签名示例代码。
2. 测试环境地址 + 测试密钥，生产环境地址。
3. 按时间段查询订单列表的接口（代收、代付都要，支持分页），及最大时间跨度、每页条数。
4. 余额查询接口（每个币种的可用、冻结余额）。
5. 结算单 / 对账单（API 或每日文件）。
6. 回调通知的报文格式和验签方法。
7. 订单状态列表及含义；订单金额是含手续费还是扣除后的。
8. 是否需要 IP 白名单、频率限制、时间字段的时区。

谢谢！
{姓名}，Wisuno 财务运营部
```
