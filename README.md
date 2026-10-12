# 麦麦派对真实管家 / mcd-party-realbutler

> 麦当劳程序员创意开发大赛参赛作品 · 区别于「只规划不下单」的派对类技能——**在用户明确确认后，真调用 `party-order-create` 完成派对预约下单**。

## 一、这是什么
麦麦派对真实管家是基于[麦当劳官方 MCP](https://mcp.mcd.cn)的派对/生日会/主题派对/亲子读书会/品鉴会/麦麦体验营**真实预约管家**。它把链路真正走到底：选品 → 城市 → 门店 → 日期 → 场次，用确定性推荐引擎辅助决策，经用户确认后**真正发起预约下单**，拿到订单号与支付链接。

**差异化亮点**：市面上派对类技能大多停在「给方案」。本技能在护栏下完成最后一步真实下单，是实打实的差异。

## 二、功能特性
- **六级真实链路**：`mall-points-products` → `mall-product-detail` → `query-party-city` → `query-party-store` → `query-party-store-date` → `query-party-store-session` → `party-order-create`。
- **确定性推荐引擎**：余位、成团门槛、价格、距离、日期临近、星期偏好六维打分；硬门槛（余位/成团下限/单场上限）不满足直接排除并提示。
- **安全护栏**：下单前必须向用户复述完整载荷并取得明确确认；命令行侧额外 `--confirm` 安全锁，缺省仅预览，绝不静默写操作。
- **价格单位核对**：场次价格以**分**计、商品以**元**计，强制 ÷100 换算并二次复核。
- **派对分流**：派对固定 `shopId=5`，与积分兑换(`shopId=2`)隔离，避免错用。
- **零依赖**：客户端仅用 Python 标准库（Streamable HTTP 直连），无需第三方包。

## 三、安装方法
```bash
git clone https://github.com/zhuyifeiRuichuang/mcd-party-realbutler.git
cd mcd-party-realbutler
# 可选：将真实 Token 写入 .env（仅本地，不会提交）
echo 'MCD_MCP_TOKEN=你的_TOKEN' > .env
```
在 WorkBuddy 中导入本技能目录即可使用对话框驱动；也可直接用命令行（`scripts/`）。

## 四、使用示例
### 真实联调（需 Token）
```bash
export MCD_MCP_TOKEN="你的_TOKEN"
python3 scripts/mcd_party_client.py find-products
python3 scripts/mcd_party_client.py product-detail --spu-id 1830
python3 scripts/mcd_party_client.py party-cities   --spu-id 1830
python3 scripts/mcd_party_client.py party-stores   --spu-id 1830 --city-code 610900
python3 scripts/mcd_party_client.py party-dates    --spu-id 1830 --store-code 1960713
python3 scripts/mcd_party_client.py party-sessions --spu-id 1830 --store-code 1960713 --date 2026-10-12
# 真实下单（先确认！）
python3 scripts/mcd_party_client.py order --spu-id 1830 --sku-id 2106 --party-type 1 \
  --city-code 610900 --store-code 1960713 --date 2026-10-12 --session-id 36784432 \
  --time-start 10:30 --time-end 12:00 --left-num 12 --count 10 --confirm
```
### 离线演示（无需 Token）
所有子命令加 `--demo` 读取 `examples/sample_party.json`，可完整跑通选品→下单预览：
```bash
python3 scripts/mcd_party_client.py --demo party-sessions --spu-id 1830 --store-code 310001 --date 2026-10-13
python3 scripts/party_recommend.py --data examples/sample_party.json --city "" --people 10 --budget 200 --prefer-weekday 周六 --out /tmp/rec.json
python3 scripts/build_report.py --rec /tmp/rec.json --out examples/demo_report.html
```

## 五、目标用户
- 想给孩子办麦当劳生日会 / 主题派对的家长。
- 公司团建、亲子活动组织者需要预约主题派对 / 读书会 / 品鉴会。
- 希望在一个对话框里完成「查可约→比选→真下单」的普通消费者。

## 六、目录结构
```
mcd-party-realbutler/
├── SKILL.md                  技能入口与护栏
├── README.md / MCP_INTEGRATION.md / CONTEST_DECLARATION.md
├── scripts/
│   ├── mcd_party_client.py    零依赖 MCP 客户端（authToken 双头 + 安全锁 + demo）
│   ├── party_recommend.py     确定性推荐引擎
│   └── build_report.py        单文件 HTML 报告
├── references/                mcp-tools.md / workflow.md
└── examples/                  sample_party.json / real_*.json(真实快照) / demo_report.html
```

## 七、重要说明
- 本工具为参赛作品，**非麦当劳官方产品**；派对价格、余位、成团规则以官方实时结果为准。
- 下单为真实写操作，务必在用户明确确认后进行；支付在麦当劳官方渠道完成，本工具不触碰支付。
- 真实调用证据见 `examples/real_*.json`（公开商品/门店/场次数据，不含任何敏感信息）。
