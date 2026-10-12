#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦派对真实管家 —— 单文件 HTML 报告生成器（仅标准库，零第三方依赖）。

读取 party_recommend.py 的推荐结果 JSON，生成内联 CSS/JS、无外部依赖的 HTML：
含最优方案卡（城市/门店/日期/场次/总价/人均/余位/成团门槛/风险）、
确认后真下单的载荷预览块（party-order-create 真实入参）、价格单位核对与免责声明。
"""

import argparse
import html
import json
import os
import sys


def esc(x):
    return html.escape(str(x if x is not None else ""))


def risk_badge(risk):
    return '<span class="risk">⚠ %s</span>' % esc(risk)


def build_html(rec):
    product = rec.get("product", {})
    query = rec.get("query", {})
    recs = rec.get("recommendations", [])
    excluded = rec.get("excluded", [])

    product_name = esc(product.get("spuName") or "派对商品")
    spu = esc(product.get("spuId", ""))
    cat = esc(product.get("catName", ""))
    party_type = product.get("partyType")

    q_city = esc(query.get("city", ""))
    q_people = query.get("people", 0)
    q_budget = query.get("budget", 0)

    cards = []
    for r in recs:
        bd = r.get("breakdown", {})
        risks = r.get("risks", [])
        bd_html = " ".join('<span class="tag">%s</span>' % esc("%s:%s" % (k, v)) for k, v in bd.items())
        risk_html = "".join(risk_badge(x) for x in risks) or '<span class="ok">✓ 无显式风险</span>'
        cards.append("""
        <div class="card">
          <div class="rank">方案 #%(rank)d · 评分 %(score)s</div>
          <div class="store">%(city)s · %(store)s</div>
          <div class="meta">%(date)s %(weekday)s ｜ %(start)s–%(end)s ｜ 成团 %(pmin)s–%(pmax)s 人</div>
          <div class="price">总价 ¥%(price)s <span class="per">人均 ¥%(per)s</span></div>
          <div class="kv">门店编码：%(scode)s ｜ 场次ID：%(sid)s ｜ 余位：%(left)s</div>
          <div class="tags">%(bd)s</div>
          <div class="risks">%(risk)s</div>
        </div>
        """ % {
            "rank": r.get("rank", 0),
            "score": esc(r.get("score")),
            "city": esc(r.get("cityName", "")),
            "store": esc(r.get("storeName", "")),
            "date": esc(r.get("date", "")),
            "weekday": esc(r.get("weekday", "")),
            "start": esc(r.get("timeStart", "")),
            "end": esc(r.get("timeEnd", "")),
            "pmin": esc(r.get("partyMin")),
            "pmax": esc(r.get("partyMax")),
            "price": esc(r.get("priceYuan")),
            "per": esc(r.get("perHead")),
            "scode": esc(r.get("storeCode", "")),
            "sid": esc(r.get("sessionId")),
            "left": esc(r.get("leftNum")),
            "bd": bd_html,
            "risk": risk_html,
        })

    # 确认载荷预览（取最优方案，party-order-create 真实入参）
    payload = {}
    if recs:
        top = recs[0]
        sku = (product.get("skuList") or [{}])[0].get("skuId")
        payload = {
            "partyType": party_type if party_type and party_type != -1 else "<1包场/2拼团，需用户确认>",
            "spuId": product.get("spuId"),
            "skuId": sku,
            "code": top.get("cityCode"),
            "storeCode": top.get("storeCode"),
            "dateStr": top.get("date"),
            "id": top.get("sessionId"),
            "timeStart": top.get("timeStart"),
            "timeEnd": top.get("timeEnd"),
            "leftNum": top.get("leftNum"),
            "count": query.get("people"),
        }
    payload_json = esc(json.dumps(payload, ensure_ascii=False, indent=2))

    cards_html = "\n".join(cards) if cards else '<div class="card">未找到可行场次，请放宽人数/预算/日期条件。</div>'

    budget_line = "人均预算 ¥%d" % q_budget if q_budget else "预算不限"
    topprice = "%.2f" % (float(recs[0].get("priceYuan", 0))) if recs else "0.00"
    topprice_fen = "%.0f" % (float(recs[0].get("priceYuan", 0)) * 100) if recs else "0"

    excluded_html = ""
    if excluded:
        items = "".join("<li>%s %s %s %s：%s</li>" % (
            esc(e.get("cityName")), esc(e.get("storeName")), esc(e.get("date")),
            esc(e.get("time")), esc(e.get("reason"))) for e in excluded[:10])
        excluded_html = '<div class="excluded"><b>被排除 %d 个场次（硬门槛未满足）：</b><ul>%s</ul></div>' % (len(excluded), items)

    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>麦麦派对真实管家 · 预约方案</title>
<style>
  :root{--red:#e4002b;--ink:#1d1d1f;--line:#e6e6e6;--bg:#f5f6f8;--card:#fff;}
  *{box-sizing:border-box;}
  body{margin:0;background:var(--bg);color:var(--ink);
       font-family:-apple-system,"PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;}
  .wrap{max-width:820px;margin:0 auto;padding:24px 16px 48px;}
  header{border-bottom:3px solid var(--red);padding-bottom:12px;margin-bottom:18px;}
  h1{font-size:22px;margin:0;color:var(--red);}
  .sub{color:#666;font-size:13px;margin-top:6px;}
  .summary{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 22px;}
  .pill{background:#fff;border:1px solid var(--line);border-radius:999px;
        padding:6px 12px;font-size:13px;}
  .pill b{color:var(--red);}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;
        padding:16px 18px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.04);}
  .rank{font-size:12px;color:#888;font-weight:600;letter-spacing:.5px;}
  .store{font-size:18px;font-weight:700;margin:4px 0;}
  .meta{color:#555;font-size:14px;margin-bottom:8px;}
  .price{font-size:20px;font-weight:800;color:var(--red);}
  .per{font-size:13px;color:#666;font-weight:500;margin-left:8px;}
  .kv{font-size:12px;color:#777;margin:8px 0;font-family:monospace;}
  .tags{margin:6px 0;}
  .tag{display:inline-block;background:#f0f1f3;border-radius:6px;padding:3px 8px;
       font-size:12px;color:#444;margin:2px 4px 2px 0;}
  .risks{margin-top:8px;font-size:13px;}
  .risk{display:inline-block;background:#fff3f3;color:#c0392b;border:1px solid #f3c2c2;
        border-radius:6px;padding:3px 8px;margin:2px 4px 2px 0;font-size:12px;}
  .ok{color:#1e8e3e;font-size:13px;}
  .confirm{background:#0b1f3a;color:#fff;border-radius:14px;padding:16px 18px;margin-top:8px;}
  .confirm h3{margin:0 0 8px;font-size:15px;color:#ffd2d2;}
  .confirm pre{background:#06122a;border-radius:8px;padding:12px;overflow:auto;
       font-size:12px;color:#aef;margin:0;white-space:pre-wrap;}
  .note{background:#fff8e6;border:1px solid #ffe1a6;border-radius:10px;
        padding:12px 14px;font-size:13px;color:#7a5b00;margin:14px 0;}
  .excluded{background:#fdecec;border:1px solid #f3c2c2;border-radius:10px;
        padding:12px 14px;font-size:13px;color:#a33;margin:14px 0;}
  .excluded ul{margin:6px 0 0;padding-left:18px;}
  footer{color:#999;font-size:12px;margin-top:24px;line-height:1.6;border-top:1px solid var(--line);padding-top:12px;}
</style></head>
<body><div class="wrap">
  <header>
    <h1>🎉 麦麦派对真实管家 · 预约方案</h1>
    <div class="sub">商品：%(pname)s（%(cat)s）｜ shopId 固定 5（派对类）</div>
  </header>
  <div class="summary">
    <span class="pill">城市 <b>%(city)s</b></span>
    <span class="pill">人数 <b>%(people)d</b></span>
    <span class="pill"><b>%(budget)s</b></span>
    <span class="pill">spuId <b>%(spu)s</b></span>
  </div>
  %(cards)s
  %(excluded)s
  <div class="note">价格单位已核对：场次价格接口以 <b>分</b> 计，已 ÷100 换算为「元」展示；下单前会再次核对，避免把 ¥%(topprice)s 误读为 ¥%(topprice100)s。</div>
  <div class="confirm">
    <h3>确认后真下单（party-order-create，真实入参）</h3>
    <pre>%(payload)s</pre>
    <div style="font-size:12px;color:#cdd6e6;margin-top:8px;">复述以上完整载荷给用户，收到明确确认后，由管家调用 party-order-create 完成预约；支付在官方渠道进行，管家不触碰支付，也不会在未经确认时调用。</div>
  </div>
  <footer>
    本工具为麦当劳程序员节创意开发大赛参赛作品，非麦当劳官方产品。输出仅供参考；
    派对商品、价格、余位与成团规则以麦当劳官方渠道实时结果为准。未经用户明确确认，不会发起真实下单。
  </footer>
</div></body></html>
""" % {
        "pname": product_name,
        "cat": cat,
        "city": q_city,
        "people": q_people,
        "budget": budget_line,
        "spu": spu,
        "cards": cards_html,
        "excluded": excluded_html,
        "payload": payload_json,
        "topprice": topprice,
        "topprice100": topprice_fen,
    }


def main():
    parser = argparse.ArgumentParser(description="麦麦派对真实管家报告生成器")
    parser.add_argument("--rec", required=True, help="party_recommend.py 输出的推荐 JSON")
    parser.add_argument("--out", default="examples/demo_report.html")
    args = parser.parse_args()

    with open(args.rec, encoding="utf-8") as fh:
        rec = json.load(fh)
    out = build_html(rec)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(out + "\n")
    print("已生成报告：%s" % os.path.abspath(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
