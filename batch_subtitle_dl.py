#!/usr/bin/env python3
# 描述: 按月批量下载视频字幕
"""
批量下载字幕：从 qfps_video_catalog.json 取指定月份的视频，
把字幕存到 subtitles/{date}_{bvid}_{safe_title}.txt
"""
import sys, time, json, hashlib, urllib.parse, re
from pathlib import Path
import requests

HERE = Path(__file__).resolve().parent
COOKIE_FILE = HERE / "cookie.txt"
CATALOG_FILE = HERE / "qfps_video_catalog.json"
OUT_DIR = HERE / "subtitles"
OUT_DIR.mkdir(exist_ok=True)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MIXIN_TAB = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,
             29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,
             4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]


def load_cookie():
    ck = COOKIE_FILE.read_text(encoding="utf-8").strip()
    if "SESSDATA" not in ck:
        sys.exit("cookie.txt 缺少 SESSDATA")
    return ck


def make_session(ck):
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Referer": "https://space.bilibili.com/",
        "Origin": "https://space.bilibili.com",
        "Cookie": ck,
    })
    return s


def mixin_key(s):
    d = s.get("https://api.bilibili.com/x/web-interface/nav", timeout=10).json()["data"]["wbi_img"]
    raw = d["img_url"].rsplit("/", 1)[-1].split(".")[0] + d["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    return "".join(raw[i] for i in MIXIN_TAB)[:32]


def wbi(params, mk):
    params = dict(params)
    params["wts"] = int(time.time())
    q = urllib.parse.urlencode(sorted(params.items()))
    params["w_rid"] = hashlib.md5((q + mk).encode()).hexdigest()
    return params


def safe_name(title):
    return re.sub(r'[\\/:*?"<>|\r\n]', '_', title)[:60]


def get_subtitle_text(s, mk, bvid):
    """返回字幕纯文本（每行一句），无字幕返回 None"""
    info = s.get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", timeout=10).json()
    if info.get("code") != 0:
        return None, f"view错误: {info.get('message')}"
    cid = info["data"]["cid"]

    sub_data = s.get("https://api.bilibili.com/x/player/wbi/v2",
                     params=wbi({"bvid": bvid, "cid": cid}, mk), timeout=10).json()
    subs = sub_data.get("data", {}).get("subtitle", {}).get("subtitles", [])
    if not subs:
        # fallback: try x/player/v2
        aid = info["data"]["aid"]
        pv = s.get("https://api.bilibili.com/x/player/v2",
                   params={"aid": aid, "cid": cid, "bvid": bvid}, timeout=10).json()
        subs = pv.get("data", {}).get("subtitle", {}).get("subtitles", [])
    if not subs:
        return None, "无字幕"

    cands = [x for x in subs if x.get("subtitle_url")]
    if not cands:
        return None, "字幕url为空"
    zh = [x for x in cands if x.get("lan", "").startswith(("zh", "ai-zh"))]
    pool = zh or cands

    best_text, best_len = "", 0
    for x in pool:
        u = x["subtitle_url"]
        if u.startswith("//"): u = "https:" + u
        try:
            body = requests.get(u, timeout=15).json().get("body", [])
            t = "\n".join(item["content"] for item in body)
            if len(t) > best_len:
                best_text, best_len = t, len(t)
        except Exception:
            continue
    if not best_text:
        return None, "字幕内容为空"
    return best_text, f"OK ({best_len}字)"


def main():
    from datetime import datetime
    from collections import defaultdict

    # parse target months from args, e.g. "2025-09 2025-10"
    target_months = set(sys.argv[1:]) if len(sys.argv) > 1 else set()

    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    # group by month
    by_month = defaultdict(list)
    for v in catalog:
        ts = v.get("pub_ts", 0)
        if not ts:
            continue
        dt = datetime.fromtimestamp(ts)
        key = dt.strftime("%Y-%m")
        by_month[key].append({
            "bvid": v["bvid"],
            "title": v["title"],
            "date": dt.strftime("%Y-%m-%d"),
        })

    if target_months:
        months = sorted(m for m in by_month if m in target_months)
    else:
        months = sorted(by_month.keys())

    s = make_session(load_cookie())
    mk = mixin_key(s)
    print(f"WBI key 获取成功")

    total_ok = total_skip = total_fail = 0

    for month in months:
        videos = by_month[month]
        print(f"\n=== {month} ({len(videos)} 个视频) ===")
        for v in videos:
            bvid, title, date = v["bvid"], v["title"], v["date"]
            fname = OUT_DIR / f"{date}_{bvid}_{safe_name(title)}.txt"
            if fname.exists():
                print(f"  [跳过] {date} {title}")
                total_skip += 1
                continue
            print(f"  [下载] {date} {title} ... ", end="", flush=True)
            try:
                text, reason = get_subtitle_text(s, mk, bvid)
                if text:
                    fname.write_text(text, encoding="utf-8")
                    print(f"{reason}")
                    total_ok += 1
                else:
                    print(f"无字幕: {reason}")
                    total_fail += 1
            except Exception as e:
                print(f"异常: {e}")
                total_fail += 1
            time.sleep(1.2)

    print(f"\n完成: 成功={total_ok} 跳过={total_skip} 失败={total_fail}")


if __name__ == "__main__":
    main()
