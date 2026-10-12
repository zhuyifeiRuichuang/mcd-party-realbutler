# MCP 集成说明

## 一、使用的 MCP Server
- **Server**：麦当劳中国官方 MCP，端点 `https://mcp.mcd.cn`，传输协议 Streamable HTTP。
- **鉴权**：请求头 `Authorization: Bearer <MCP_TOKEN>`；**会员/账户类工具额外要求 `authToken` 头（值同 Token）**——此为 live 实测结论，官方文档未明示，缺失会返回 `403 authToken必填`。

## 二、实际使用的 Tool（共 35 个工具中真实使用 7 个）
| Tool | 用途 | 关键入参 | 关键出参 |
|---|---|---|---|
| `mall-points-products` | 派对商品选品 | 无 | `spuId`、`shopId`(=5)、`price`(元)、`catName` |
| `mall-product-detail` | 商品详情 | `spuId` | `skuList[].skuId`、`partyType`(-1需问)、`partyPeople` |
| `query-party-city` | 活动城市 | `spuId` | `code`(整数)、`name` |
| `query-party-store` | 城市下门店 | `code`(城市code)、`spuId` | `code`(=storeCode)、`name`、`distance` |
| `query-party-store-date` | 门店可约日期 | `spuId`、`storeCode` | `date` |
| `query-party-store-session` | 日期下场次 | `spuId`、`storeCode`、`dateStr` | `id`、`timeStart/End`、`partyMin/Max`、`price`(**分**)、`leftNum` |
| `party-order-create` | **真实下单** | `partyType,spuId,skuId,code,storeCode,dateStr,id,timeStart,timeEnd,leftNum,count` | `orderId`、`payH5Url`、`amount` |

> 工具名以 live 服务端为准：`query-party-store-date` / `query-party-store-session`（含连字符）；官方 README 文档中误写作无连字符形式，已以服务端实测为准。

## 三、调用流程（业务价值）
1. `mall-points-products` 选出派对类商品 → 拿到 `spuId` / `shopId=5` / `skuList`。
2. `mall-product-detail` 取 `skuId` 与 `partyType`（包场/拼团），为下单备料。
3. `query-party-city` → `query-party-store` → `query-party-store-date` → `query-party-store-session` 逐级下钻，收集用户可选的真实可约场次。
4. `party_recommend.py` 对候选场次做余位/成团门槛/价格/距离/日期六维打分，淘汰不满足硬门槛（余位不足、成团人数不足、超单场上限）的场次，输出 Top 方案与风险。
5. 向用户复述完整下单载荷并**取得明确确认**后，调用 `party-order-create` 完成真实预约（CLI 侧还需 `--confirm`），返回订单号与支付链接。

**业务价值**：把零散的 7 个 MCP 工具编排成一条「查得到→比得清→约得成」的闭环，把派对预约从「查完还要自己手动下单」升级为「确认即真下单」，且通过价格单位核对、余位/成团校验、派对 shopId 分流、确认门控等护栏，降低误操作与资损风险。

## 四、真实调用证据
- `examples/real_products.json`：`mall-points-products` 真实返回（派对类商品样本 + 分类清单）。
- `examples/real_detail.json`：`mall-product-detail` 真实返回（含 `skuList`/`partyType`/`partyPeople`）。
- `examples/real_cities.json`：`query-party-city` 真实返回（城市 `code` 列表）。
- `examples/real_store_dates_sessions.json`：`query-party-store` / `query-party-store-date` / `query-party-store-session` 真实返回。
- 以上均为公开商品/门店/场次数据，不含任何用户隐私或敏感信息。

## 五、兼容性 / 版本
- 传输协议对齐官方最新文档（Streamable HTTP，MCP 协议版本 `2025-06-18`）。
- 仅依赖 Python 3 标准库，无第三方包，跨平台零安装即可运行。
- 已按 live `tools/list`（2026-10-12）校正全部工具名与入参，避免沿用官方 README 中过时的无连字符工具名与臆测字段。
