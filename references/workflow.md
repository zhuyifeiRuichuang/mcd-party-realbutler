# 六级依赖链工作流（含示例与排错）

本文件给出麦麦派对真实管家从「选品」到「真下单」的逐步示例。所有真实接口调用都应先确认 `tools-list` 中对应工具的 `inputSchema`，下面的 JSON 为常见形态，**以接口实际返回为准**。

## 真实调用顺序（已 live 验证）
```
mall-points-products        → 取 spuId / shopId=5 / skuList
mall-product-detail(spuId)  → 取 skuId / partyType(-1需问用户)
query-party-city(spuId)     → 取城市 code（整数）
query-party-store(code)      → 取门店 code（=storeCode）
query-party-store-date(spuId,storeCode)     → 取 date
query-party-store-session(spuId,storeCode,dateStr) → 取 id/timeStart/timeEnd/partyMin/partyMax/price(分)/leftNum
party-order-create(...)      → 真实下单（需用户确认 + --confirm）
```

## 逐步示例（真实数据，spuId=1830 亲子读书会）

1. **选品**
   `mall-points-products` → 命中 `catName` 含「生日类派对/主题类派对/读书会…」：
   ```json
   {"spuId":1830,"spuName":"麦当劳亲子读书会","shopId":5,"price":"45","catName":"读书会"}
   ```
2. **详情**
   `mall-product-detail({"spuId":1830})` →
   `skuList:[{"skuId":2106,...}]`，`partyType`:-1（需问用户包场/拼团），`partyPeople":"5-12"`。
3. **城市**
   `query-party-city({"spuId":1830})` → `[{"code":610900,"name":"安康市",...}]`，取 `code`。
4. **门店**
   `query-party-store({"code":610900,"spuId":1830})` → 每项 `code` 即 storeCode。
5. **日期**
   `query-party-store-date({"spuId":1830,"storeCode":"1960713"})` → `[{"date":"2026-10-12",...}]`。
6. **场次**
   `query-party-store-session({"spuId":1830,"storeCode":"1960713","dateStr":"2026-10-12"})` →
   `[{"id":36784432,"timeStart":"10:30","timeEnd":"12:00","partyMin":5,"partyMax":12,"price":4500,"leftNum":12}]`
   ⚠️ `price` 是 **分**（4500 = ¥45）；`id` 是场次主键。
7. **下单（确认后）**
   `party-order-create({partyType:1,spuId:1830,skuId:2106,code:610900,storeCode:"1960713",
   dateStr:"2026-10-12",id:36784432,timeStart:"10:30",timeEnd:"12:00",leftNum:12,count:10})`
   → `{orderId, payH5Url, amount, status}`。

## 确定性推荐（辅助决策）
- 输入逐级收集到的结构化数据（demo / 真实同构，见 `examples/sample_party.json`）。
- `scripts/party_recommend.py` 按 余位裕度 / 成团门槛 / 价格 / 距离 / 日期临近 / 星期偏好 打分，
  并强制硬门槛：`count ≤ leftNum`、`count ≥ partyMin`、`count ≤ partyMax`；不满足直接排除并给原因（余位不足 / 成团人数不足 / 超单场上限）。
- `scripts/build_report.py` 生成单文件 HTML 报告（方案卡 + 真实下单载荷预览 + 价格单位核对 + 免责声明）。

## 排错表
| 现象 | 原因 | 处理 |
|---|---|---|
| `401` | Token 无效/过期/未提供 | 重新申请 MCP Token，检查 `MCD_MCP_TOKEN` |
| `403 authToken必填` | 会员类工具漏传 `authToken` 头 | 本客户端已统一补发；自研客户端须同时发 `Authorization` 与 `authToken` |
| `429` | 超 600 次/分钟 | 降低频率，批量脚本加 sleep |
| 下单报某 id/code 不匹配 | 入参非取自上游返回 | 严格用上级返回的 `id`/`code`/`date`/`storeCode`，勿自行构造 |
| 价格差 100 倍 | 把场次「分」当「元」 | 场次 `price`÷100；商品 `price` 已是元 |
| 下单提示成团/余位不符 | 人数越界 | 校验 `count` 满足 `partyMin ≤ count ≤ min(partyMax, leftNum)` |
| 城市查不到门店 | `query-party-store` 的 `code` 传错（应为城市 code 而非名称） | 用 `query-party-city` 返回的 `code`(整数) |
