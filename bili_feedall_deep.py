#!/usr/bin/env python3
"""深翻「关注动态」feed/all,过滤指定UP,抓全文,看能往前翻到多早。
付费长文因已订阅会在此接口解锁(与空间接口不同)。
用法: python3 bili_feedall_deep.py [UP名] [--pages N]
"""
import sys
import time
import json
import importlib.util
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bs", HERE / "bili_space.py")
bs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bs)

FEED = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all"


def get_page(s, mk, offset):
    backoff = 30
    for attempt in range(8):
        p = {"type": "all", "page": 1}
        if offset:
            p["offset"] = offset
        try:
            j = s.get(FEED, params=bs.wbi(p, mk), timeout=20).json()
        except requests.RequestException as e:
            print(f"    网络异常 {type(e).__name__},{backoff}s 后重试({attempt+1}/8)…", file=sys.stderr)
            time.sleep(backoff); backoff = min(backoff*2, 240); continue
        code = j.get("code")
        if code == 0:
            return j["data"]
        if code == -352:
            print(f"    风控 -352,{backoff}s 后重试({attempt+1}/8)…", file=sys.stderr)
            time.sleep(backoff); backoff = min(backoff*2, 240); continue
        sys.exit(f"接口错误 code={code} msg={j.get('message')}")
    return None


def main():
    args = sys.argv[1:]
    max_pages = 60
    if "--pages" in args:
        i = args.index("--pages"); max_pages = int(args[i+1]); del args[i:i+2]
    resume = "--resume" in args
    if resume:
        args.remove("--resume")
    up = args[0] if args else "青枫浦上Q"

    s = bs.make_session(bs.load_cookie()); mk = bs.mixin_key(s)
    out, offset, page, seen = [], "", 0, set()
    out_json = HERE / "qfps_all_deep.json"
    off_file = HERE / "qfps_all_deep.offset"
    if resume and out_json.exists():
        out = json.loads(out_json.read_text(encoding="utf-8"))
        seen = {x["id"] for x in out}
        if off_file.exists():
            offset = off_file.read_text(encoding="utf-8").strip()
        print(f"续传:已有 {len(out)} 条,从 offset={offset[:20]}… 继续", file=sys.stderr)
    print(f"深翻 feed/all 过滤 [{up}] ...", file=sys.stderr)
    while page < max_pages:
        data = get_page(s, mk, offset)
        if data is None:
            print("    多次重试仍失败,停止。", file=sys.stderr); break
        items = data.get("items", [])
        added = 0
        for it in items:
            e = bs.extract(it)
            if e["name"] != up or e["id"] in seen:
                continue
            # 判断是否解锁:文本不是空占位且不是BLOCKED
            e["unlocked"] = e["text"] not in ("[无文字内容]", "") and "MAJOR_TYPE_BLOCKED" not in e.get("major_type", "")
            seen.add(e["id"]); out.append(e); added += 1
        page += 1
        offset = data.get("offset", "")
        earliest = out[-1]["pub_time"] if out else "-"
        print(f"  第{page}页:本UP+{added},累计{len(out)},最早 {earliest}", file=sys.stderr)
        out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        off_file.write_text(offset, encoding="utf-8")
        if not data.get("has_more") or not offset:
            print("    feed 已到底 has_more=False。", file=sys.stderr); break
        time.sleep(4.0)

    print(f"\n共 {len(out)} 条本UP动态。", file=sys.stderr)
    if out:
        print(f"时间跨度:{out[-1]['pub_time']} -> {out[0]['pub_time']}", file=sys.stderr)
        unlocked = sum(1 for x in out if x.get("unlocked"))
        print(f"解锁全文:{unlocked}/{len(out)}", file=sys.stderr)


if __name__ == "__main__":
    main()
