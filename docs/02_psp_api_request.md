# 向 PSP 索取 API：发送模板

把下面的英文版直接发给 PSP 的对接经理（中国区 PSP 用中文版）。收到回复后，在
[`data/psp_inventory.csv`](../data/psp_inventory.csv) 里把 `api_status` 改成 `docs_received`，填上 `docs_url`。

---

## English

**Subject: API access request for reporting & reconciliation – Wisuno**

Hi {name},

We are building an internal reconciliation dashboard and want to pull our data from {PSP} by API instead of
downloading reports. Could you send us the following? Read-only access is enough; we will not create payments
through these credentials.

1. **API documentation** (link or PDF), including the signature / authentication method and a signing example.
2. **Sandbox** base URL + test credentials, and **production** base URL.
3. Endpoints for:
   - **Transaction list by time range** for both deposits (pay-in) and withdrawals (payout), with paging.
     Please confirm the maximum time range and page size, and which timestamp it filters on (created / updated).
   - **Single order query** by our merchant order ID.
   - **Account / wallet balance** per currency (available and pending / frozen).
   - **Settlement report** (API or daily file via SFTP / email): settlement ID, amount, currency, fees, status,
     settlement date, and which transactions it covers.
4. **Callback (webhook)**: payload format, status values, retry policy, and how to verify the signature.
5. **Status values** and their meaning (pending / success / failed / refunded / chargeback), and whether a
   status can change after "success".
6. **Fee fields**: is the amount in the transaction list gross or net of fees? Is the fee returned per transaction?
7. **IP whitelist**: do we need to register our server IPs? Our egress IPs: {IPs}.
8. **Rate limits** and the timezone used in timestamps.

Thank you,
{your name}, Wisuno Finance & Operations

---

## 中文

**主题：Wisuno 申请对账 / 报表 API 权限**

{称呼} 您好，

我们正在搭建内部对账系统，希望通过 API 直接拉取我们在 {PSP} 的数据，替代手工下载报表。麻烦提供以下内容（只需只读权限，不会用这套密钥发起支付）：

1. **API 文档**（链接或 PDF），包括签名 / 鉴权方式和签名示例代码。
2. **测试环境**地址 + 测试账号密钥，**生产环境**地址。
3. 以下接口：
   - **按时间段查询订单列表**：代收（入金）和代付（出金）都要，支持分页。请说明最大时间跨度、每页条数、按创建时间还是更新时间筛选。
   - **单笔订单查询**（按我方商户订单号）。
   - **余额查询**（每个币种的可用余额、冻结 / 在途余额）。
   - **结算单 / 对账单**（API 或每日文件，SFTP / 邮件均可）：结算单号、金额、币种、手续费、状态、结算日期、包含哪些订单。
4. **回调通知**：报文格式、状态值、重试机制、**验签方法**。
5. **订单状态**列表及含义（处理中 / 成功 / 失败 / 退款 / 拒付），成功后状态是否还会变化。
6. **手续费**：订单列表里的金额是含手续费还是扣除后的？每笔订单是否返回手续费？
7. **IP 白名单**：是否需要报备服务器 IP？我们的出口 IP：{IPs}。
8. **频率限制**，以及时间字段使用的时区。

谢谢！
{姓名}，Wisuno 财务运营部

---

## 发送跟踪

| PSP | 联系人 | 发送日期 | 收到文档 | 收到 sandbox 密钥 | 备注 |
|---|---|---|---|---|---|
| Lipad（追问列表 / 余额 / 结算 / 回调签名） | | | ✅ | | 只有单笔查询 |
| 5 Pay | | | | | |
| OM Pay | | | | | |
| Long77Pay (Payme) | | | | | |
| Proxpay | | | | | |
| Monetix | | | | | |
| Acerpay | | | | | |
| Payexchina | | | | | |
| uEnjoy | | | | | |
| Now Pay | | | | | |
| ChipPay | | | | | |
| Bipi Pay | | | | | |
| Picotop | | | | | |
| NEPay | | | | | |
| MT Pay | | | | | |
| IBit Pay | | | | | |
| Ge-link | | | | | |
| Kuwa | | | | | |
| Paysnapper | | | | | |
| Tarspay | | | | | |
| Unitedpay | | | | | |
| Payok | | | | | |
| CheezeePay | | | | | |
| Starpago | | | | | |
