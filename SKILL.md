---
name: mcd-party-realbutler
display_name: 麦麦派对真实管家
description: 基于麦当劳 MCP（https://mcp.mcd.cn）的派对/生日会/主题派对/读书会/品鉴会真实预约管家。逐级下钻选品→城市→门店→日期→场次，确定性推荐后，在用户明确确认下调用 party-order-create 完成真实下单（差异化于只规划不下单的派对类技能）。强制价格单位核对（场次价格以「分」计，商品以「元」计）、余位/成团门槛校验、shopId=5 派对分流，并内置 --confirm 安全锁，未经确认绝不发起真实写操作。
version: 1.1.0
---

# 麦麦派对真实管家（mcd-party-realbutler）

## 一句话定位
市面派对类技能大多「只规划、不下单」。本技能走到最后一步：**在用户明确确认后，真调用 `party-order-create` 把派对预约落到麦当劳账户上**——这才是实打实的差异化。

## 适用场景
- 用户想办麦当劳生日派对 / 主题派对 / 亲子读书会 / 品鉴会 / 麦麦体验营，并希望**真正预约成功**（拿到订单）。
- 需要在一个对话框里完成「选品 → 选城市 → 选门店 → 选日期 → 选场次 → 确认 → 下单」全链路。
- 需要确定性推荐（余位、成团门槛、价格、距离、日期）辅助决策。

## 绝不承接
- 普通点餐 / 麦乐送 / 团餐（用 `create-order` 体系，非本技能范围）。
- 在用户未明确确认前发起任何真实下单。

---

## 接入与鉴权（已 live 实测）

- 端点：`https://mcp.mcd.cn`（Streamable HTTP）。
- 鉴权：请求头 `Authorization: Bearer <MCP_TOKEN>`。
- **关键实测坑（官方文档未写）**：会员/账户类工具（如 `mall-points-products`）后端除 Bearer 外，还要求请求头 `authToken`，值**与 MCP Token 相同**。仅带 Bearer 会返回 `403 authToken必填`。本技能客户端每个请求同时发送这两个头。
- Token 获取：登录 https://open.mcd.cn/mcp → 控制台 → 激活 → 复制 MCP Token。
- 限流：每 Token 600 次/分钟（429）。

## 真实链路（六级，工具名以 live 服务端为准）

> 注：官方 README 把日期/场次工具写作 `query-partystore-date`/`query-partystore-session`（无连字符），但 **live 服务端实际工具名为 `query-party-store-date`/`query-party-store-session`（含连字符）**。本技能以 live 服务端为准，并已在 `scripts/mcd_party_client.py` 中验证。

| 步骤 | 工具 | 关键入参 | 产出 |
|---|---|---|---|
| 0 | `mall-points-products` | 无 | 派对商品列表 → `spuId` / `shopId`(=5) / `skuList` |
| 1 | `mall-product-detail` | `spuId` | `skuList[].skuId`、`partyType`(-1 需询问包场/拼团)、`partyPeople`、`partyAge`、`partyRange` |
| 2 | `query-party-city` | `spuId` | 城市列表，每项含 **`code`(整数)**、`name` |
| 3 | `query-party-store` | `code`(城市code)、`spuId` | 门店列表，每项含 `code`(=storeCode)、`name`、`address`、`distance` |
| 4 | `query-party-store-date` | `spuId`、`storeCode` | 可约日期列表，每项含 `date` |
| 5 | `query-party-store-session` | `spuId`、`storeCode`、`dateStr` | 场次列表，每项含 `id`(整数)、`timeStart`、`timeEnd`、`partyMin`、`partyMax`、`price`(**分**)、`leftNum` |
| 6 | `party-order-create` | 见下 | 真实下单，返回 `orderId` / `payH5Url` / `amount` |

### `party-order-create` 真实入参（已按 live schema 校正）
```
partyType  1包场 / 2拼团（商品 partyType=-1 时必须先问用户）
spuId      商品 spuId
skuId      来自 mall-product-detail 的 skuList[].skuId
code       城市 code（来自 query-party-city）
storeCode  门店 code（来自 query-party-store）
dateStr    日期（来自 query-party-store-date 的 date）
id         场次 id（来自 query-party-store-session）
timeStart / timeEnd  场次起止（来自场次）
leftNum    场次余位（来自场次）
count      参与人数
```
> 该工具**没有** `shopId`、`contactName`、`contactPhone`、`sessionId`、`peopleCount`、`date` 等字段；`shopId=5` 仅作为派对类前置校验（来自商品详情），不传入下单。

---

## 安全与护栏（核心约束）
1. **确认门控**：`party-order-create` 前必须先向用户复述完整下单载荷（spuId/skuId/code/storeCode/dateStr/id/timeStart/timeEnd/leftNum/count），并收到明确确认。
2. **CLI 安全锁**：命令行侧额外要求 `--confirm` 才会真正发起写操作；缺省仅预览载荷。
3. **价格单位核对**：场次 `price` 单位为**分**，商品 `price` 单位为**元**，展示与下单前强制 ÷100 换算并复核，避免把 ¥45 误读到 ¥4500。
4. **硬门槛校验**：`count ≤ leftNum`（余位足够）、`count ≥ partyMin`（成团下限）、`count ≤ partyMax`（单场上限）；任一不满足直接淘汰并提示。
5. **派对分流**：派对固定 `shopId=5`；积分兑换是 `shopId=2`（`mall-create-order`），二者不可混用。
6. **入参取自上级**：所有 id/code/date/余位/成团数严格来自上游返回，绝不自行构造。

---

## 运行方式

### A. 真实联调（需有效 MCP Token）
```bash
export MCD_MCP_TOKEN="你的_TOKEN"
python3 scripts/mcd_party_client.py find-products
python3 scripts/mcd_party_client.py product-detail --spu-id 1830
python3 scripts/mcd_party_client.py party-cities   --spu-id 1830
python3 scripts/mcd_party_client.py party-stores   --spu-id 1830 --city-code 610900
python3 scripts/mcd_party_client.py party-dates    --spu-id 1830 --store-code 1960713
python3 scripts/mcd_party_client.py party-sessions --spu-id 1830 --store-code 1960713 --date 2026-10-12
# 真实下单（务必先确认）—— 下方为示例值，请替换为真实选择
python3 scripts/mcd_party_client.py order \
  --spu-id 1830 --sku-id 2106 --party-type 1 --city-code 610900 \
  --store-code 1960713 --date 2026-10-12 --session-id 36784432 \
  --time-start 10:30 --time-end 12:00 --left-num 12 --count 10 --confirm
```

### B. 离线演示（无需 Token）
所有子命令加 `--demo` 读取 `examples/sample_party.json`，可完整跑通选品→下单预览：
```bash
python3 scripts/mcd_party_client.py --demo find-products --spu-id 1830
python3 scripts/mcd_party_client.py --demo party-cities   --spu-id 1830 --city-code 310000
python3 scripts/mcd_party_client.py --demo party-stores   --spu-id 1830 --city-code 310000
python3 scripts/mcd_party_client.py --demo party-dates    --spu-id 1830 --store-code 310001
python3 scripts/mcd_party_client.py --demo party-sessions --spu-id 1830 --store-code 310001 --date 2026-10-13
# 确定性推荐 + 单文件 HTML 报告
python3 scripts/party_recommend.py --data examples/sample_party.json --city "" --people 10 --budget 200 --prefer-weekday 周六 --out /tmp/rec.json
python3 scripts/build_report.py --rec /tmp/rec.json --out examples/demo_report.html
```

## 配套文件
- `scripts/mcd_party_client.py`：零依赖 Streamable HTTP 客户端（authToken 双头 + 安全锁 + demo）。
- `scripts/party_recommend.py`：确定性推荐引擎（余位/成团/价格/距离/日期打分 + 风险排除）。
- `scripts/build_report.py`：单文件 HTML 报告（内联 CSS/JS，无外部依赖）。
- `references/mcp-tools.md`：各工具入参/出参/约束清单。
- `references/workflow.md`：逐步示例 + 排错表。
- `examples/`：`sample_party.json`（演示数据）、`real_*.json`（live 真实调用快照，作为真实使用证据）、`demo_report.html`。
- `README.md` / `MCP_INTEGRATION.md` / `CONTEST_DECLARATION.md`：参赛必需文档。
