# workbuddy.md

> 本文件为使用腾讯 WorkBuddy 开发本项目的对话上下文记录，用于核验 WorkBuddy 专项奖励条件。
> 由 WorkBuddy 会话上下文整理而成。

## 项目

- 名称：麦麦派对真实管家（mcd-party-realbutler）
- 仓库：https://github.com/zhuyifeiRuichuang/mcd-party-realbutler
- 定位：基于麦当劳官方 MCP 的派对/生日会/主题派对/体验营/品鉴会/读书会全链路预约管家，**确认后真下单**
- 开发环境：腾讯 WorkBuddy（Agent 模式）

---

## 一、需求起点

用户提出：在已有的 `mcd-just-enough`（适量点餐，停在付款前）之外，开发一个派对管家 Skill，利用 2026-07 新增的派对类工具（`query-party-city` / `query-party-store` / `query-party-store-date` / `query-party-store-session` + `party-order-create`），**从「规划」走到「真预约下单」**。用户明确指出：现有派对类技能大多只规划不下单，这是实打实的差异化。

## 二、调研过程（WorkBuddy 完成）

1. 读取活动仓库规则文件（`activity_guidelines_raw.md` / `activity_README_raw.md`），确认参赛文件清单与排名规则。
2. 分析工作区内已有的 `mcd-just-enough` 技能，复用其已验证的 Streamable HTTP MCP 客户端范式（`extract_json` / `unwrap` / 说明文字+JSON 混合体解析）。
3. 挖掘工作区 `issues_p*.json`（约 226 个参赛作品）中与派对相关的提交，提炼出**真实派对六级依赖链**与多个项目实测的工程约束：
   - 链路：`mall-points-products → spuId → query-party-city → query-party-store → query-party-store-date → query-party-store-session → party-order-create`
   - **shopId 分流**：派对固定 `shopId=5`，积分商城兑换 `shopId=2`
   - **价格单位陷阱**：场次价格以「分」计，商品以「元」计（实测 11/11 商品恒 ×100）
   - `leftNum > 0` 才可约；`query-party-store-date` 仅约 10 天滚动窗口；`minGroupSize` 成团下限
   - 工具真实命名为 `query-party-store-date` / `query-party-store-session`（非 `query-party-date/session`）
4. 通过 `tools-list` 联调发现当前 `.env` Token 已过期（401），因此采用「真实客户端 + 离线样例回退」双模式设计，确保评委无 Token 也能跑通全流程。

## 三、决策过程

| 决策点 | 选项 | 结论 |
|---|---|---|
| 差异化定位 | A 只规划 / B 规划+真下单 / C 纯展示 | **B**（确认后真下单） |
| 真实下单方式 | A 模型直接调 MCP / B Python 客户端 / C 两者都要 | **C**（模型调 MCP + 客户端双轨） |
| 推荐 | A 纯模型口述 / B 确定性引擎 | **B**（五维打分，可复现可测） |
| 安全门控 | A 软提示 / B 确认锁+载荷复述 | **B** |
| 演示 | A 纯真实 / B 真实+样例回退 | **B** |

## 四、实现过程（WorkBuddy 生成代码）

生成的文件：

1. `SKILL.md`：入口，六级依赖链工作流 + 确认门控 + 硬约束
2. `scripts/mcd_party_client.py`：MCP Streamable HTTP 客户端（ping/tools-list/call + 5 个派对便捷子命令 + mall 选品 + order 确认锁 + demo 模式；带 Session 复用）
3. `scripts/party_recommend.py`：确定性推荐引擎（余位/成团/日期/价格/距离五维打分，淘汰 `leftNum<人数`，输出 2–3 方案）
4. `scripts/build_report.py`：单文件 HTML 报告生成器（内联 CSS/JS，无外部依赖，含确认载荷预览块）
5. `references/mcp-tools.md`：7 个工具清单、入参要点、链路约束
6. `references/workflow.md`：六级链路逐步示例与排错表
7. `examples/sample_party.json`：离线演示样例（spuId/城市/门店/日期/场次，场次价格以分计）
8. `examples/demo_report.html`：样例数据生成的报告
9. `README.md` / `MCP_INTEGRATION.md` / `CONTEST_DECLARATION.md` / `mcp-config.example.json` / `workbuddy.md` / `LICENSE` / `CHANGELOG.md` / `.gitignore`

实现中修正/规避的问题：

- 价格单位不一致（分 vs 元）→ 全链路 `price ÷ 100` 并下单前复核，报告中显式标注换算
- 不可约场次（`leftNum < 人数`）被错误推荐 → 推荐引擎硬性淘汰
- 写操作误触发 → `order` 默认禁用，必须 `--confirm`；对话路径要求复述完整载荷并获明确确认
- 工具字段微调风险 → SKILL.md 明确要求运行时先 `tools/list` 读 `inputSchema`，入参严格取自上级返回

## 五、验证记录

| 步骤 | 方式 | 结果 |
|---|---|---|
| 连通性/工具清单 | `ping` / `tools-list` | 客户端正常；Token 过期(401)后转 demo |
| 离线选品→城市→门店→日期→场次 | `--demo` 五级子命令 | 全通，场次价格正确显示「分」 |
| 推荐引擎 | `party_recommend.py`（上海/10人/预算1500/偏好周日） | 候选 30、可行 25、推荐 3；早场 `leftNum=4<10` 被正确淘汰 |
| 报告 | `build_report.py` | 生成单文件 HTML，含方案卡 + 确认载荷块 |
| 安全锁 | `order`（无/有 `--confirm`） | 无确认仅预览；有 `--confirm` 模拟成功 |

## 六、WorkBuddy 在本项目中的作用

- 完成活动规则与竞品调研，从 `issues_*.json` 提炼真实派对链路与工程约束
- 生成全部代码：MCP 客户端、推荐引擎、报告生成器
- 设计确认门控与安全锁，确保「真下单」有护栏
- 生成参赛所需文档：`README.md`、`MCP_INTEGRATION.md`、`workbuddy.md`、`CONTEST_DECLARATION.md`

## 七、后续待办

- 配置有效 MCP Token 后，用真实数据补一份 `examples/real_*.json` 取数快照
- 在活动仓库提交报名 Issue（正文不超过 1000 字，不带图片）
