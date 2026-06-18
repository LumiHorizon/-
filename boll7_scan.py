#!/usr/bin/env python3
# 描述: 七轨布林线选股扫描——筛出价格处于买入区的标的
"""
七轨布林线扫描 — 筛出当前价格处于买入区的标的
买入区定义：现价 ≤ 四轨（MID - 1×DEV），得分越低越佳
数据源：腾讯K线（历史） + 东方财富实时（现价）
"""
import json, re, time
import numpy as np
import requests

H_QQ = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://finance.qq.com/",
}
H_EM = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

# ── 核心股票池（来自UP主视频提及） ──────────────────────────
STOCKS = {
    # 光模块 / 光互联
    "中际旭创":  "0.300308",
    "新易盛":    "0.300502",
    "天孚通信":  "0.300394",
    "亨通光电":  "1.600487",
    "长飞光纤":  "1.601869",
    "茂莱光学":  "1.603260",
    "沃格光电":  "1.603773",
    "华灿光电":  "0.300323",
    "兆驰股份":  "0.002429",
    # 国产算力 / 半导体
    "海光信息":  "1.688041",
    "澜起科技":  "1.688008",
    "寒武纪":    "1.688256",
    "中国长城":  "0.000066",
    "华丰科技":  "1.688629",
    "博迁新材":  "1.605376",
    # PCB / 材料
    "东山精密":  "0.002384",
    "风华高科":  "0.000636",
    "三环集团":  "0.300408",
    # 液冷 / 散热
    "英维克":    "0.002837",
    "申菱环境":  "0.301018",
    # 燃气轮机 / 能源
    "应流股份":  "0.002369",
    "万泽股份":  "0.002439",
    # 算力租赁 / AIDC
    "润泽科技":  "0.300442",
    # 机器人
    "绿的谐波":  "1.688017",
    "航天电器":  "0.002025",
    # 创新药
    "药明康德":  "1.603259",
    # 储能 / 电力
    "宁德时代":  "0.300750",
    "金风科技":  "0.002202",
    # 商业航天
    "信维通信":  "0.300136",
}


def secid_to_tcode(secid: str) -> str:
    mkt, code = secid.split(".")
    return ("sh" if mkt == "1" else "sz") + code


def fetch_kline(secid, name):
    tcode = secid_to_tcode(secid)
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?_var=k&param={tcode},day,,,100,qfq")
    try:
        r = requests.get(url, headers=H_QQ, timeout=12).text
        idx = r.index("=") + 1
        d = json.loads(r[idx:])
        days = (d["data"][tcode].get("qfqday")
                or d["data"][tcode].get("day", []))
        return days  # [date, open, close, high, low, vol, ...]
    except Exception as e:
        print(f"  [K线失败] {name}: {e}")
        return None


def fetch_realtime_price(secid):
    url = (f"https://push2.eastmoney.com/api/qt/stock/get"
           f"?secid={secid}&fields=f43,f57,f58")
    try:
        d = requests.get(url, headers=H_EM, timeout=8).json().get("data", {})
        v = d.get("f43", 0)
        return v / 100 if v else None
    except Exception:
        return None


def calc_boll7(closes):
    arr = np.array(closes, dtype=float)
    if len(arr) < 25:
        return None
    mids = [arr[i-20:i].mean() for i in range(20, len(arr)+1)]
    stds = [arr[i-20:i].std(ddof=0) for i in range(20, len(arr)+1)]
    devs = [np.mean(stds[max(0, i-5):i]) for i in range(1, len(stds)+1)]
    d, m = devs[-1], mids[-1]
    return {
        "顶轨": m + 3*d,
        "一轨": m + 2*d,
        "二轨": m + d,
        "三轨": m,       # MID
        "四轨": m - d,
        "五轨": m - 2*d,
        "底轨": m - 3*d,
        "MID": m,
        "DEV": d,
    }


def score_position(price, b):
    """返回 (得分, 区间描述)；得分越低越接近底轨"""
    bands = [
        (b["顶轨"], "顶轨以上", 7),
        (b["一轨"], "一~顶轨", 6),
        (b["二轨"], "二~一轨", 5),
        (b["三轨"], "三~二轨", 4),   # 三轨=MID
        (b["四轨"], "四~三轨", 3),
        (b["五轨"], "五~四轨", 2),
        (b["底轨"], "底~五轨", 1),
    ]
    for threshold, label, score in bands:
        if price >= threshold:
            return score, label
    return 0, "底轨以下"


def main():
    results = []
    print(f"共 {len(STOCKS)} 只标的，开始扫描...\n")

    for name, secid in STOCKS.items():
        days = fetch_kline(secid, name)
        if not days:
            continue
        closes = [float(d[2]) for d in days if len(d) > 2]
        b = calc_boll7(closes)
        if not b:
            continue

        # 优先东方财富实时价，失败则用腾讯K线最新收盘
        price = fetch_realtime_price(secid)
        if price is None or price <= 0:
            price = closes[-1]
            price_src = "腾讯收盘"
        else:
            price_src = "EM实时"

        score, zone = score_position(price, b)
        results.append({
            "name": name,
            "secid": secid,
            "price": price,
            "price_src": price_src,
            "score": score,
            "zone": zone,
            "MID": b["MID"],
            "DEV": b["DEV"],
            "四轨": b["四轨"],
            "五轨": b["五轨"],
            "底轨": b["底轨"],
            "顶轨": b["顶轨"],
        })
        time.sleep(0.4)

    # 排序：得分低（买入区）在前
    results.sort(key=lambda x: (x["score"], -x["price"]))

    print("=" * 72)
    print(f"{'标的':<8} {'现价':>8} {'区间':<10} {'得分':>4}  {'四轨':>8} {'三轨(MID)':>10} {'一轨':>8}")
    print("-" * 72)

    buy_zone = []
    watch_zone = []
    for r in results:
        flag = ""
        if r["score"] <= 2:
            flag = " ◀ 强买"
            buy_zone.append(r)
        elif r["score"] == 3:
            flag = " ◀ 买入"
            buy_zone.append(r)
        elif r["score"] == 4:
            flag = " · 观察"
            watch_zone.append(r)

        b = r
        one_rail = b["MID"] + b["DEV"]  # 一轨=MID+2DEV
        print(f"{r['name']:<8} {r['price']:>8.2f} {r['zone']:<10} {r['score']:>4}  "
              f"{b['四轨']:>8.2f} {b['MID']:>10.2f} {one_rail:>8.2f}{flag}")

    print("=" * 72)
    print(f"\n【买入区（得分≤3）】共 {len(buy_zone)} 只：" +
          "、".join(r["name"] for r in buy_zone) if buy_zone else "无")
    print(f"【观察区（得分=4）】共 {len(watch_zone)} 只：" +
          "、".join(r["name"] for r in watch_zone) if watch_zone else "无")


if __name__ == "__main__":
    main()
