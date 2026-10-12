#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦派对真实管家 —— 确定性推荐引擎（仅标准库，零第三方依赖）。

输入：派对链路逐级收集到的结构化数据（demo 与真实模式同构）：
    {
      "product": {"spuId","spuName","shopId":5,"price"(元),"catName",
                  "partyType"(-1/1/2),"partyPeople","partyAge","partyRange","skuList":[{"skuId","price"}]},
      "cities":  [{"code"(整数),"name","latitude","longitude"}],
      "stores":  {"<cityCode>": [{"code"(=storeCode),"name","address","latitude","longitude","distance"}]},
      "dates":   {"<storeCode>": [{"date","storeCode"}]},
      "sessions":{""<storeCode>|<date>": [{"id"(整数),"timeStart","timeEnd",
                  "partyMin","partyMax","price"(分),"leftNum"}]}
    }

硬门槛（任一不满足即淘汰，并记入 risks_summary）：
    - 人数 <= leftNum（余位足够）
    - 人数 >= partyMin（成团下限）
    - 人数 <= partyMax（单场上限）

软风险（可行方案仍提示）：
    - 余位告急：leftNum - 人数 <= 2
    - 超人均预算：人均 > --budget
    - 成团下限偏高：partyMin 较大（如 > 8）提示凑人难度

打分维度：余位裕度 / 价格(低优) / 距离(近优) / 日期临近(近优) / 成团门槛(低优) / 星期偏好
输出：最优方案列表 + 风险与排除汇总，写入 --out JSON。
"""

import argparse
import datetime as dt
import json
import os
import sys


def load_data(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def weekday_cn(date_str):
    try:
        d = dt.date.fromisoformat(date_str)
        return WEEKDAYS[d.weekday()]
    except Exception:
        return ""


def evaluate(store, date_item, session, product, people, budget,
             prefer_weekday, anchor):
    risks = []
    breakdown = {}

    price_fen = float(session.get("price") or 0)      # 场次价格单位：分
    price_yuan = price_fen / 100.0
    per_head = price_yuan / people if people > 0 else 0.0
    party_min = int(session.get("partyMin") or product.get("partyMin") or 0)
    party_max = int(session.get("partyMax") or product.get("partyMax") or 0)
    left_num = int(session.get("leftNum") or 0)

    # ---- 硬门槛 ----
    if people > left_num:
        return None, "余位不足：仅剩 %d 个名额，当前 %d 人" % (left_num, people)
    if party_min and people < party_min:
        return None, "成团人数不足：本场下限 %d 人，当前 %d 人" % (party_min, people)
    if party_max and people > party_max:
        return None, "超单场上限：本场上限 %d 人，当前 %d 人" % (party_max, people)

    score = 100.0

    # 1. 余位裕度（越宽裕越好）
    slack = left_num - people
    if slack <= 2:
        score -= 12
        risks.append("余位告急：仅剩 %d 个名额（含本场）" % left_num)
        breakdown["余位"] = "告急-%d" % left_num
    elif slack <= 6:
        breakdown["余位"] = "适中-%d" % left_num
    else:
        score += 4
        breakdown["余位"] = "宽松-%d" % left_num

    # 2. 成团门槛（越低越易成团）
    if party_min:
        if party_min >= 8:
            score -= 6
            risks.append("成团下限偏高：本场需 %d 人成团，凑人难度较大" % party_min)
        breakdown["成团门槛"] = "下限%d人" % party_min
    else:
        breakdown["成团门槛"] = "无下限"

    # 3. 价格（越低越好）
    score += max(-10.0, 8.0 - price_yuan / 10.0)
    breakdown["总价"] = "¥%.0f" % price_yuan

    # 4. 距离（越近越好）
    dist = store.get("distance")
    if dist is not None:
        score += max(0.0, 10.0 - float(dist))
        breakdown["距离"] = "%.1fkm" % float(dist)
    else:
        breakdown["距离"] = "未知"

    # 5. 日期临近（越近越好）+ 星期偏好
    date_str = date_item.get("date", "")
    wd = weekday_cn(date_str)
    proximity = 0.0
    if anchor:
        try:
            delta = (dt.date.fromisoformat(date_str) - anchor).days
            if delta >= 0:
                proximity = max(0.0, 10.0 - delta * 1.5)
                score += proximity
        except Exception:
            pass
    if prefer_weekday and wd == prefer_weekday:
        score += 8
        breakdown["日期"] = "命中星期"
    else:
        breakdown["日期"] = wd or "未知"

    # 6. 预算（人均）
    if budget and budget > 0:
        if per_head <= budget:
            score += 6
            breakdown["预算"] = "人均¥%.0f≤¥%d" % (per_head, budget)
        else:
            score -= 18
            risks.append("超人均预算：人均¥%.0f > ¥%d" % (per_head, budget))
            breakdown["预算"] = "超支"
    else:
        breakdown["预算"] = "未限"

    return {
        "score": round(score, 1),
        "priceYuan": round(price_yuan, 2),
        "perHead": round(per_head, 2),
        "breakdown": breakdown,
        "risks": risks,
    }, None


def recommend(data, city, people, budget, prefer_weekday, anchor, top_n=3):
    product = data.get("product", {})
    cities = data.get("cities", [])
    stores_map = data.get("stores", {})
    dates_map = data.get("dates", {})
    sessions_map = data.get("sessions", {})

    targets = cities if not city else [c for c in cities if str(c.get("code")) == str(city) or c.get("name") == city]

    candidates = []
    excluded = []
    total = 0
    for c in targets:
        ccode = str(c.get("code"))
        for store in stores_map.get(ccode, []):
            sc = store.get("code")
            for date_item in dates_map.get(str(sc), []):
                key = "%s|%s" % (sc, date_item.get("date"))
                for session in sessions_map.get(key, []):
                    total += 1
                    res, reason = evaluate(store, date_item, session, product, people,
                                           budget, prefer_weekday, anchor)
                    if res is None:
                        excluded.append({
                            "cityName": c.get("name"), "storeName": store.get("name"),
                            "date": date_item.get("date"), "time": "%s-%s" % (
                                session.get("timeStart"), session.get("timeEnd")),
                            "reason": reason,
                        })
                        continue
                    candidates.append({
                        "cityCode": ccode, "cityName": c.get("name"),
                        "storeCode": sc, "storeName": store.get("name"),
                        "distance": store.get("distance"),
                        "date": date_item.get("date"),
                        "weekday": weekday_cn(date_item.get("date", "")),
                        "sessionId": session.get("id"),
                        "timeStart": session.get("timeStart"),
                        "timeEnd": session.get("timeEnd"),
                        "priceYuan": res["priceYuan"],
                        "perHead": res["perHead"],
                        "leftNum": session.get("leftNum"),
                        "partyMin": session.get("partyMin"),
                        "partyMax": session.get("partyMax"),
                        "score": res["score"],
                        "breakdown": res["breakdown"],
                        "risks": res["risks"],
                    })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    recs = candidates[:top_n]
    for i, r in enumerate(recs, 1):
        r["rank"] = i
    return {
        "query": {
            "city": city or "全部", "people": people, "budget": budget,
            "prefer_weekday": prefer_weekday, "anchor": anchor.isoformat() if anchor else "",
        },
        "product": product,
        "recommendations": recs,
        "excluded": excluded,
        "total_candidates": total,
        "feasible_candidates": len(candidates),
    }


def main():
    parser = argparse.ArgumentParser(description="麦麦派对真实管家推荐引擎")
    parser.add_argument("--data", required=True, help="收集到的链路数据 JSON（demo 或真实同构）")
    parser.add_argument("--city", default="", help="城市 code 或名称；留空评估全部城市")
    parser.add_argument("--people", type=int, required=True)
    parser.add_argument("--budget", type=int, default=0, help="人均预算上限，0 表示不限")
    parser.add_argument("--prefer-weekday", default="", help="期望星期，如 周六")
    parser.add_argument("--anchor", default="", help="锚定日期(yyyy-MM-dd)，用于日期临近打分；留空用今天")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    if args.anchor:
        try:
            anchor = dt.date.fromisoformat(args.anchor)
        except Exception:
            anchor = dt.date.today()
    else:
        anchor = dt.date.today()

    data = load_data(args.data)
    result = recommend(data, args.city, args.people, args.budget,
                       args.prefer_weekday, anchor, args.top)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print("已写入：%s" % os.path.abspath(args.out))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    print("候选场次 %d，可行 %d，推荐 %d，排除 %d。" % (
        result["total_candidates"], result["feasible_candidates"],
        len(result["recommendations"]), len(result["excluded"])))
    for r in result["recommendations"]:
        print("#%d %s %s | %s %s | %s-%s | ¥%.2f(人均¥%.2f) | 余位%d | 分%.1f" % (
            r["rank"], r["cityName"], r["storeName"], r["date"], r["weekday"],
            r["timeStart"], r["timeEnd"], r["priceYuan"], r["perHead"],
            r["leftNum"], r["score"]))
        for risk in r["risks"]:
            print("   ⚠ %s" % risk)
    for ex in result["excluded"][:8]:
        print("   排除 %s %s %s %s：%s" % (
            ex["cityName"], ex["storeName"], ex["date"], ex["time"], ex["reason"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
