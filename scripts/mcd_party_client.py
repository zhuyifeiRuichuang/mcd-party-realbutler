#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦派对真实管家 —— 麦当劳 MCP Streamable HTTP 客户端（仅标准库，零第三方依赖）。

对 https://mcp.mcd.cn 做 JSON-RPC 直连：
    initialize -> tools/list -> tools/call

派对预约真实链路（基于 live tools/list 实测 schema）：
    find-products      mall-points-products         选品 -> spuId / shopId(=5) / skuList
    product-detail     mall-product-detail          取 skuId、partyType(-1需询问包场/拼团)
    party-cities       query-party-city             城市 -> code(整数)
    party-stores       query-party-store            门店 -> code(=storeCode)
    party-dates        query-party-store-date       日期 -> date
    party-sessions     query-party-store-session    场次 -> id/timeStart/timeEnd/partyMin/partyMax/price(分)/leftNum
    now-time           now-time-info                当前时间（用于锚定预约窗口）
    order              party-order-create           真下单（必须 --confirm）

关键实测约束（已在 live 环境验证）：
    1. 会员/账户类工具后端除 Authorization: Bearer 外，额外要求 authToken 请求头（值与 Token 相同）；
       仅带 Bearer 会返回 403 authToken必填。本客户端每个请求都同时发送两个头。
    2. party-order-create 入参为 partyType/spuId/skuId/code/storeCode/dateStr/id/timeStart/
       timeEnd/leftNum/count；无 shopId、无联系人字段。shopId=5 仅作为派对类前置校验（来自商品详情）。
    3. 场次 price 单位为「分」，商品 price 单位为「元」，展示需 /100。
    4. 下单是真实写操作，必须显式 --confirm，且官方工具约束要求下单前获得用户明确确认。

安全设计：
    - order 默认禁用，必须显式 --confirm 才执行真实写操作
    - --demo 模式读取 examples/sample_party.json，无需 Token 即可跑通全流程

Token 读取优先级：--token > 环境变量 MCD_MCP_TOKEN > .env 文件。
Token 只用于请求头，不会写入任何输出文件。
"""

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"
TIMEOUT = 40
PARTY_SHOP_ID = 5  # 派对类固定 shopId；积分兑换是 2，二者分流（仅作前置校验）

DEMO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "examples", "sample_party.json")


class McpError(RuntimeError):
    pass


# ------------------------------------------------------ Token

def load_token(cli_token: str = "") -> str:
    if cli_token:
        return cli_token
    env = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if env:
        return env
    roots = (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), os.getcwd())
    for base in roots:
        env_path = os.path.join(base, ".env")
        if os.path.isfile(env_path):
            with open(env_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("MCD_MCP_TOKEN="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ------------------------------------------------------ 协议（带 session 复用）

_SESSION_ID = None


def rpc(method: str, params: dict, token: str, url: str) -> dict:
    global _SESSION_ID
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer " + token,
        # 实测必需：会员/账户类工具（mall-points-products 等）后端额外要求 authToken 头，
        # 值与 MCP Bearer Token 相同；仅 Authorization 会导致 403 authToken必填。
        "authToken": token,
        "User-Agent": "mcd-party-realbutler/1.1.0",
    }
    if _SESSION_ID:
        headers["Mcp-Session-Id"] = _SESSION_ID
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        if exc.code == 401:
            raise McpError("401 Token 无效、已过期或未提供，请检查 MCD_MCP_TOKEN。")
        if exc.code == 429:
            raise McpError("429 触发限流（600 次/分钟），请降低调用频率。")
        raise McpError("HTTP %s：%s" % (exc.code, detail[:400]))
    except urllib.error.URLError as exc:
        raise McpError("网络错误：%r（若需代理请检查系统代理设置）" % (exc,))

    sid = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
    if sid:
        _SESSION_ID = sid

    raw = raw.strip()
    if not raw:
        return {}
    if raw.startswith("event:") or "\ndata:" in raw or raw.startswith("data:"):
        data_lines = [ln[5:].strip() for ln in raw.splitlines() if ln.startswith("data:")]
        raw = "\n".join(data_lines)
    try:
        msg = json.loads(raw)
    except ValueError:
        raise McpError("响应不是合法 JSON：%s" % raw[:300])
    if "error" in msg:
        err = msg["error"]
        raise McpError("MCP 错误 %s：%s" % (err.get("code"), err.get("message")))
    return msg.get("result", {})


def initialize(token: str, url: str) -> dict:
    return rpc("initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "mcd-party-realbutler", "version": "1.1.0"},
    }, token, url)


def tools_list(token: str, url: str) -> list:
    return rpc("tools/list", {}, token, url).get("tools", [])


def call_tool(name: str, arguments: dict, token: str, url: str) -> dict:
    return rpc("tools/call", {"name": name, "arguments": arguments or {}}, token, url)


# ------------------------------------------------------ 响应解析

def extract_json(text):
    if isinstance(text, (dict, list)):
        return text
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    starts = [i for i in (stripped.find('{"'), stripped.find("[{")) if i >= 0]
    if not starts:
        return None
    start = min(starts)
    open_ch = stripped[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for idx in range(start, len(stripped)):
        ch = stripped[idx]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(stripped[start:idx + 1])
                except ValueError:
                    break
    return None


def unwrap(result: dict):
    content = result.get("content") or []
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    joined = "\n".join(texts).strip()
    parsed = extract_json(joined)
    if parsed is None:
        return joined
    if isinstance(parsed, dict) and "data" in parsed and "success" in parsed:
        if not parsed.get("success"):
            raise McpError("接口返回失败：%s / %s" % (parsed.get("code"), parsed.get("message")))
        data = parsed.get("data")
        inner = extract_json(data) if isinstance(data, str) else data
        return inner if inner is not None else data
    return parsed


# ------------------------------------------------------ 输出

def dump(payload, out_path):
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("已写入：%s" % os.path.abspath(out_path))
    else:
        print(text)


# ------------------------------------------------------ Demo 数据

def load_demo():
    with open(DEMO_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def demo_cities(d):
    return d.get("cities", [])


def demo_stores(d, city_code):
    return d.get("stores", {}).get(str(city_code), [])


def demo_dates(d, store_code):
    return d.get("dates", {}).get(str(store_code), [])


def demo_sessions(d, store_code, date):
    return d.get("sessions", {}).get("%s|%s" % (store_code, date), [])


# ------------------------------------------------------ 子命令

def _need_spu(args):
    if not args.spu_id:
        raise McpError("缺少 --spu-id（先由 find-products 取得）。")
    return args.spu_id


def cmd_find_products(args, token, url):
    if args.demo:
        p = load_demo().get("product", {})
        print("【DEMO】派对商品：%s (spuId=%s, shopId=%s)" % (
            p.get("spuName"), p.get("spuId"), p.get("shopId")))
        dump({"demo": True, "product": p}, args.out)
        return 0
    data = unwrap(call_tool("mall-points-products", {}, token, url))
    products = data if isinstance(data, list) else []
    party = [x for x in products if x.get("catName") in (
        "生日类派对", "主题类派对", "读书会", "品鉴会", "麦麦体验营")]
    dump({"source_tool": "mall-points-products", "total": len(products),
          "party_count": len(party), "party_sample": party[:10]}, args.out)
    print("商品总数：%d，派对类：%d（请筛选派对类并取 spuId）" % (len(products), len(party)))
    return 0


def cmd_product_detail(args, token, url):
    spu = _need_spu(args)
    if args.demo:
        p = load_demo().get("product", {})
        print("【DEMO】%s: shopId=%s, partyType=%s, skuId=%s" % (
            p.get("spuName"), p.get("shopId"), p.get("partyType"),
            p.get("skuList", [{}])[0].get("skuId") if p.get("skuList") else None))
        dump({"demo": True, "detail": p}, args.out)
        return 0
    data = unwrap(call_tool("mall-product-detail", {"spuId": spu}, token, url))
    skus = data.get("skuList") or []
    print("spuId=%s shopId=%s partyType=%s partyPeople=%s partyAge=%s" % (
        data.get("spuId"), data.get("shopId"), data.get("partyType"),
        data.get("partyPeople"), data.get("partyAge")))
    print("skuList: %s" % json.dumps(skus, ensure_ascii=False))
    dump({"source_tool": "mall-product-detail", "spuId": spu, "detail": data}, args.out)
    return 0


def cmd_party_cities(args, token, url):
    spu = _need_spu(args)
    if args.demo:
        cities = demo_cities(load_demo())
        print("【DEMO】%s 支持城市：%s" % (spu, "、".join(str(c.get("code")) + c.get("name") for c in cities)))
        dump({"demo": True, "spuId": spu, "cities": cities}, args.out)
        return 0
    data = unwrap(call_tool("query-party-city", {"spuId": spu}, token, url))
    cities = data if isinstance(data, list) else []
    dump({"source_tool": "query-party-city", "spuId": spu, "cities": cities}, args.out)
    print("城市数量：%d（取目标城市的 code 传入 party-stores --city-code）" % len(cities))
    return 0


def cmd_party_stores(args, token, url):
    spu = _need_spu(args)
    if not args.city_code:
        raise McpError("party-stores 需要 --city-code（来自 query-party-city 的 code，整数）。")
    if args.demo:
        stores = demo_stores(load_demo(), args.city_code)
        print("【DEMO】城市 %s 可办派对门店：%d 家" % (args.city_code, len(stores)))
        for s in stores:
            print("  %s | %s | 距%.1fkm" % (s.get("code"), s.get("name"), s.get("distance", 0)))
        dump({"demo": True, "spuId": spu, "cityCode": args.city_code, "stores": stores}, args.out)
        return 0
    params = {"code": args.city_code, "spuId": spu}
    data = unwrap(call_tool("query-party-store", params, token, url))
    stores = data if isinstance(data, list) else []
    dump({"source_tool": "query-party-store", "params": params, "stores": stores}, args.out)
    print("门店数量：%d（取目标门店的 code 作为 --store-code）" % len(stores))
    return 0


def cmd_party_dates(args, token, url):
    spu = _need_spu(args)
    if not args.store_code:
        raise McpError("party-dates 需要 --store-code（来自 query-party-store 的 code）。")
    if args.demo:
        dates = demo_dates(load_demo(), args.store_code)
        print("【DEMO】门店 %s 可约日期：%s" % (args.store_code, "、".join(x.get("date") for x in dates)))
        dump({"demo": True, "spuId": spu, "storeCode": args.store_code, "dates": dates}, args.out)
        return 0
    params = {"spuId": spu, "storeCode": args.store_code}
    data = unwrap(call_tool("query-party-store-date", params, token, url))
    dates = data if isinstance(data, list) else []
    dump({"source_tool": "query-party-store-date", "params": params, "dates": dates}, args.out)
    print("可约日期：%d（取 date 作为 --date）" % len(dates))
    return 0


def cmd_party_sessions(args, token, url):
    spu = _need_spu(args)
    if not (args.store_code and args.date):
        raise McpError("party-sessions 需要 --store-code 与 --date。")
    if args.demo:
        sessions = demo_sessions(load_demo(), args.store_code, args.date)
        print("【DEMO】%s %s 场次：%d（price 单位：分）" % (args.store_code, args.date, len(sessions)))
        for s in sessions:
            print("  id=%s | %s-%s | ¥%.2f | 余位%d | 成团%s-%s人" % (
                s.get("id"), s.get("timeStart"), s.get("timeEnd"),
                s.get("price", 0) / 100.0, s.get("leftNum"),
                s.get("partyMin"), s.get("partyMax")))
        dump({"demo": True, "spuId": spu, "storeCode": args.store_code,
              "date": args.date, "sessions": sessions}, args.out)
        return 0
    params = {"spuId": spu, "storeCode": args.store_code, "dateStr": args.date}
    data = unwrap(call_tool("query-party-store-session", params, token, url))
    sessions = data if isinstance(data, list) else []
    dump({"source_tool": "query-party-store-session", "params": params, "sessions": sessions}, args.out)
    print("场次数量：%d（price 单位：分；取 id 作为 --session-id）" % len(sessions))
    return 0


def cmd_now_time(args, token, url):
    data = unwrap(call_tool("now-time-info", {}, token, url))
    dump({"source_tool": "now-time-info", "now": data}, args.out)
    print("当前服务器时间：%s（用其锚定派对可约窗口）" % data.get("formatted") if isinstance(data, dict) else data)
    return 0


def cmd_order(args, token, url):
    spu = _need_spu(args)
    required = ["sku_id", "party_type", "city_code", "store_code", "date",
                "session_id", "time_start", "time_end", "left_num", "count"]
    missing = [r for r in required if getattr(args, r) in (None, "")]
    if missing and not args.demo:
        raise McpError("order 缺少参数：%s" % ", ".join("--" + r.replace("_", "-") for r in missing))

    # 价格换算核对（场次 price 为分）
    price_fen = args.price_fen or 0
    params = {
        "partyType": args.party_type,
        "spuId": spu,
        "skuId": args.sku_id,
        "code": args.city_code,
        "storeCode": args.store_code,
        "dateStr": args.date,
        "id": args.session_id,
        "timeStart": args.time_start,
        "timeEnd": args.time_end,
        "leftNum": args.left_num,
        "count": args.count,
    }
    if args.shop_id:
        params["shopId"] = args.shop_id  # 冗余传参无副作用；派对固定 5

    # 校验：成团下限 / 上限 / 余位
    warns = []
    if args.left_num is not None and args.count is not None and args.count > args.left_num:
        warns.append("人数(%d)超过余位(%d)，无法预约" % (args.count, args.left_num))
    if args.party_min is not None and args.count is not None and args.count < args.party_min:
        warns.append("人数(%d)低于成团下限(%d)，拼团/包场可能不成立" % (args.count, args.party_min))
    if args.party_max is not None and args.count is not None and args.count > args.party_max:
        warns.append("人数(%d)超过单场上限(%d)" % (args.count, args.party_max))

    print("下单载荷预览（price 单位已核对为元）：")
    print(json.dumps(params, ensure_ascii=False, indent=2))
    for w in warns:
        print("⚠️ %s" % w)

    if args.demo:
        if not args.confirm:
            print("[DEMO] 未传 --confirm，仅预览，不执行模拟下单。")
            return 0
        print("[DEMO] 模拟下单成功（非真实）：orderNo=DEMO%s" % (
            dt.datetime.now().strftime("%Y%m%d%H%M%S")))
        return 0

    if warns:
        print("⚠️ 存在约束冲突，仍可在用户明确确认后下单；请确认无误。")
    if not args.confirm:
        print("⚠️ 安全锁：真实写操作 party-order-create 已拦截。确认无误后加 --confirm 再执行。")
        return 0
    data = unwrap(call_tool("party-order-create", params, token, url))
    dump({"source_tool": "party-order-create", "params": params, "result": data}, args.out)
    print("下单完成，请在官方渠道完成支付。订单信息见上方 result。")
    return 0


# ------------------------------------------------------ 主入口

def main() -> int:
    parser = argparse.ArgumentParser(description="麦麦派对真实管家 MCP 客户端")
    parser.add_argument("action", nargs="?", default="", choices=[
        "ping", "tools-list", "now-time", "call", "find-products", "product-detail",
        "party-cities", "party-stores", "party-dates", "party-sessions", "order", ""])
    parser.add_argument("tool_or_args", nargs="?", default="")
    parser.add_argument("arguments", nargs="?", default="{}")
    parser.add_argument("--token", default="")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default="")
    parser.add_argument("--demo", action="store_true", help="离线演示模式（读 sample_party.json）")
    # 派对参数
    parser.add_argument("--spu-id", type=int, default=0)
    parser.add_argument("--sku-id", type=int, default=0)
    parser.add_argument("--shop-id", type=int, default=0)
    parser.add_argument("--party-type", type=int, default=0, help="1包场 2拼团；商品 partyType=-1 时必须显式传入")
    parser.add_argument("--city-code", type=int, default=0, help="城市 code（来自 query-party-city）")
    parser.add_argument("--store-code", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--session-id", type=int, default=0)
    parser.add_argument("--time-start", default="")
    parser.add_argument("--time-end", default="")
    parser.add_argument("--left-num", type=int, default=None)
    parser.add_argument("--party-min", type=int, default=None)
    parser.add_argument("--party-max", type=int, default=None)
    parser.add_argument("--price-fen", type=int, default=0)
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--remark", default="")
    parser.add_argument("--confirm", action="store_true", help="解锁真实写操作（party-order-create）")
    args = parser.parse_args()

    if args.action == "" and not args.demo:
        parser.print_help()
        return 0

    if args.demo:
        token = ""
    else:
        token = load_token(args.token)
        if not token:
            print("缺少 MCP Token：使用 --token、设置环境变量 MCD_MCP_TOKEN，或写入 .env。", file=sys.stderr)
            return 2

    try:
        if args.action == "ping":
            print(json.dumps(initialize(token, args.url), ensure_ascii=False))
            return 0
        if args.action == "tools-list":
            tools = tools_list(token, args.url)
            print("工具数量：%d" % len(tools))
            for t in tools:
                print("- %s | %s" % (t.get("name"), (t.get("description") or "").split("\n")[0][:70]))
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    json.dump(tools, fh, ensure_ascii=False, indent=2)
                print("已写入：%s" % os.path.abspath(args.out))
            return 0
        if args.action == "now-time":
            return cmd_now_time(args, token, args.url)
        if args.action == "call":
            try:
                params = json.loads(args.arguments or "{}")
            except ValueError as exc:
                print("参数不是合法 JSON：%r" % (exc,), file=sys.stderr)
                return 2
            result = unwrap(call_tool(args.tool_or_args, params, token, args.url))
            dump(result, args.out)
            return 0
        if args.action == "find-products":
            return cmd_find_products(args, token, args.url)
        if args.action == "product-detail":
            return cmd_product_detail(args, token, args.url)
        if args.action == "party-cities":
            return cmd_party_cities(args, token, args.url)
        if args.action == "party-stores":
            return cmd_party_stores(args, token, args.url)
        if args.action == "party-dates":
            return cmd_party_dates(args, token, args.url)
        if args.action == "party-sessions":
            return cmd_party_sessions(args, token, args.url)
        if args.action == "order":
            return cmd_order(args, token, args.url)
    except McpError as exc:
        print("MCP 调用失败：%s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
