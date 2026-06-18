#!/usr/bin/env python3
"""抓取某 UP 在关注动态里的视频，并尝试下载字幕（转录文本）。
用法: python3 bili_videos.py --up 青枫浦上Q [页数] [--list]
  --list 只列出视频清单(bvid/标题)，不抓字幕。
"""
import sys
import time
import json
import hashlib
import urllib.parse
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
COOKIE_FILE = HERE / "cookie.txt"
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
    s.headers.update({"User-Agent": UA, "Referer": "https://t.bilibili.com/",
                      "Origin": "https://t.bilibili.com", "Cookie": ck})
    return s


def mixin_key(s):
    d = s.get("https://api.bilibili.com/x/web-interface/nav", timeout=10).json()["data"]["wbi_img"]
    raw = d["img_url"].rsplit("/",1)[-1].split(".")[0] + d["sub_url"].rsplit("/",1)[-1].split(".")[0]
    return "".join(raw[i] for i in MIXIN_TAB)[:32]


def wbi(params, mk):
    params = dict(params); params["wts"] = int(time.time())
    q = urllib.parse.urlencode(sorted(params.items()))
    params["w_rid"] = hashlib.md5((q+mk).encode()).hexdigest()
    return params


def collect_videos(s, mk, up, pages):
    url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all"
    vids, offset = [], ""
    for _ in range(pages):
        p = {"type":"all","page":1}
        if offset: p["offset"] = offset
        data = s.get(url, params=wbi(p, mk), timeout=10).json()["data"]
        for it in data.get("items", []):
            m = it.get("modules", {})
            if m.get("module_author", {}).get("name","") != up:
                continue
            major = (m.get("module_dynamic", {}) or {}).get("major") or {}
            if major.get("type") == "MAJOR_TYPE_ARCHIVE":
                a = major["archive"]
                vids.append({"bvid": a.get("bvid"), "title": a.get("title",""),
                             "time": m["module_author"].get("pub_time","")})
        offset = data.get("offset","");
        if not data.get("has_more"): break
    return vids


def get_subtitle(s, bvid):
    """返回 (cid, 字幕文本 or None, 原因)。"""
    v = s.get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", timeout=10).json()
    if v.get("code") != 0:
        return None, None, f"view错误 {v.get('message')}"
    cid = v["data"]["cid"]; aid = v["data"]["aid"]
    pv = s.get("https://api.bilibili.com/x/player/v2",
               params={"aid": aid, "cid": cid, "bvid": bvid}, timeout=10).json()
    if pv.get("code") != 0:
        return cid, None, f"player错误 {pv.get('message')}"
    subs = pv.get("data", {}).get("subtitle", {}).get("subtitles", [])
    if not subs:
        return cid, None, "无字幕"
    cands = [x for x in subs if x.get("subtitle_url")]
    if not cands:
        return cid, None, f"有{len(subs)}条字幕但url为空(可能需鉴权)"
    # 优先中文(lan 以 zh / ai-zh 开头)，没有中文再用其他语言
    zh = [x for x in cands if x.get("lan", "").startswith(("zh", "ai-zh"))]
    pool = zh or cands
    best_text, best_lan = "", "?"
    for x in pool:
        u = x["subtitle_url"]
        if u.startswith("//"): u = "https:" + u
        body = s.get(u, timeout=10).json().get("body", [])
        t = "".join(seg.get("content","") for seg in body)
        if len(t) > len(best_text):
            best_text, best_lan = t, x.get("lan_doc", "?")
    return cid, best_text, f"字幕语言={best_lan}"


def main():
    args = sys.argv[1:]
    list_only = "--list" in args
    if list_only: args.remove("--list")
    up = "青枫浦上Q"
    if "--up" in args:
        i = args.index("--up"); up = args[i+1]; del args[i:i+2]
    pages = int(args[0]) if args else 25

    s = make_session(load_cookie()); mk = mixin_key(s)
    vids = collect_videos(s, mk, up, pages)
    print(f"找到 {len(vids)} 个视频\n")
    out = []
    for i, v in enumerate(vids, 1):
        line = f"{i}. [{v['time']}] {v['title']}  ({v['bvid']})"
        print(line)
        if list_only:
            continue
        best, why = "", ""
        for attempt in range(3):
            cid, text, w = get_subtitle(s, v["bvid"])
            if text and len(text) > len(best):
                best, why = text, w
            if best and len(best) > 1000:
                break
            time.sleep(1.0)
        why = why or w
        print(f"   字幕: {why}; 长度={len(best)}")
        out.append({**v, "subtitle": best or None, "why": why})
        time.sleep(0.8)
    if not list_only:
        (HERE / "qfps_videos.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        got = sum(1 for o in out if o["subtitle"])
        print(f"\n有字幕 {got}/{len(out)} 个，已存 qfps_videos.json")


if __name__ == "__main__":
    main()
