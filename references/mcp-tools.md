# 麦当劳 MCP 派对相关工具清单（基于 live `tools/list` 实测，2026-10-12）

> 端点 `https://mcp.mcd.cn`，Streamable HTTP；鉴权头 `Authorization: Bearer <TOKEN>`，
> 且会员/账户类工具需额外 `authToken` 头（值同 Token）。字段名、类型均来自服务端返回。
> 全量 35 个工具；本技能真实使用 **7 个**（5 个派对 + 2 个商城选品）。

## 链路工具

### 0. `mall-points-products`（选品）
- 入参：无（可选 `catRuleIds`）
- 出参 `data`：数组，每项
  - `spuId`(int) · `spuName`(str) · `shopId`(**派对固定 5，兑换为 2**) · `price`(**元，字符串**) · `catName`(生日类派对/主题类派对/读书会/品鉴会/麦麦体验营) · `status` · `point` · `spuImage` · `selling`
- 用途：筛选派对类商品，取 `spuId` 进入下一步。

### 1. `mall-product-detail`（商品详情）
- 入参：`spuId`(int, 必填)
- 出参 `data`：
  - `spuId` · `spuName` · `shopId`(5) · `price`(元) · `catName`
  - **`skuList`**：`[{skuId, extTradePrice, points, price}]` —— 下单必须 `skuId`
  - **`partyType`**：`-1` 需询问用户包场(1)/拼团(2)；`1` 仅包场；`2` 仅拼团
  - `partyPeople`(如 "5-12") · `partyAge` · `partyRange`(提前预订天数) · `spuLimit` · `note`(活动须知 HTML)

### 2. `query-party-city`（城市）
- 入参：`spuId`(int, 必填)
- 出参 `data`：数组，每项 `code`(**int，城市编码**) · `name` · `latitude` · `longitude` · `initial` · `sortNo`

### 3. `query-party-store`（门店）
- 入参：`code`(**城市 code，int/str**) · `spuId`(int) · 可选 `latitude`/`longitude`
- 出参 `data`：数组，每项 `code`(**即 storeCode**) · `name` · `address` · `cityCode` · `cityName` · `latitude` · `longitude` · `distance` · `distanceText` · `businessStatus` · `onlineBusinessStatus`

### 4. `query-party-store-date`（可约日期）
- 入参：`spuId`(int) · `storeCode`(str, 必填)
- 出参 `data`：数组，每项 `date`("yyyy-MM-dd") · `storeCode`
- 备注：约 10 天滚动窗口（以 `now-time-info` 锚定“今天”）。

### 5. `query-party-store-session`（场次）
- 入参：`spuId`(int) · `storeCode`(str) · `dateStr`(**str，取自上一步 date**)
- 出参 `data`：数组，每项
  - `id`(**int，场次 id**) · `timeStart`(str "HH:mm") · `timeEnd`(str)
  - **`partyMin`**(int 成团下限) · **`partyMax`**(int 单场上限)
  - **`price`**(**int，单位：分** ⚠️) · `leftNum`(int 余位)
  - （另有 `cookEmpNo`/`opEmpNo`/`rgmEmpNo` 内部字段，下单无需）

### 6. `party-order-create`（下单 · 真实写操作）
- 入参（按 live schema，仅列必填/关键）：
  - `partyType`(int, **必填**：1 包场 / 2 拼团)
  - `spuId`(number) · `skuId`(number) · `code`(城市 code) · `storeCode`(str)
  - `dateStr`(str) · `id`(场次 id, number) · `timeStart`(str) · `timeEnd`(str)
  - `leftNum`(int) · `count`(参与人数, int)
- **无** `shopId` / `contactName` / `contactPhone` / `sessionId` / `peopleCount` / `date`
- 出参 `data`：`orderId` · `status` · `amount`(现金金额) · `payH5Url`(支付链接) · `point` · `goods[]` · `orderStatus`
- 官方约束：每一步须等待用户明确选择，下单前须确认信息。

## 辅助工具（本技能未强制使用，可用于增强）
- `now-time-info`：无入参，返回服务器当前时间（`date`/`formatted`/`dayOfWeek`），用于锚定可约窗口。
- `mall-product-detail` 已覆盖派对所需信息；`mall-create-order`(shopId=2) 与本技能无关（积分兑换）。

## 错误码
- `401`：Token 无效 / 过期 / 未提供。
- `429`：超过 600 次/分钟限流。
- `403 authToken必填`：会员类工具漏传 `authToken` 头（本客户端已统一补发）。
