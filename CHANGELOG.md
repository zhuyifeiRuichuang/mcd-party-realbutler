# 更新日志

## v1.1.0 (2026-10-12)
- **真实联调修正**：基于 live `tools/list` 与全链路实测，校正此前基于猜测的字段，消除「落后/错误配置」：
  - 修正 `party-order-create` 真实入参（`partyType/spuId/skuId/code/storeCode/dateStr/id/timeStart/timeEnd/leftNum/count`），移除臆测的 `shopId/contactName/contactPhone/sessionId/peopleCount/date`。
  - 修正场次字段：`id`(number) / `price`(**分**) / `partyMin` / `partyMax` / `leftNum`，替代旧 `sessionId/priceFen/minGroupSize`。
  - 修正城市入参为 `code`(整数)、门店主键为 `code`(=storeCode)、日期字段为 `date` / `dateStr`。
  - 新增 `skuId`（`mall-product-detail.skuList`）与 `partyType`（包场/拼团，-1 需询问）下单项。
- **鉴权增强**：客户端每个请求同时发送 `Authorization: Bearer` 与 `authToken` 头，修复会员类工具 `403 authToken必填`。
- **工具名对齐**：以 live 服务端为准（`query-party-store-date`/`query-party-store-session` 含连字符），并标注官方 README 文档中的无连字符拼写错误。
- **推荐引擎/报告/样例数据**全量改用真实字段结构；报告下单载荷预览改用真实 `party-order-create` 入参。
- 新增 `examples/real_*.json` 作为 live 真实调用证据。

## v1.0.0 (2026-10-10)
- 初版：六级下钻链路、确认门控 + `--confirm` 安全锁、确定性推荐引擎、单文件 HTML 报告、离线 `--demo` 模式。
