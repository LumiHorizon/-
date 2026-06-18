#!/usr/bin/env python3
# 描述: 抓取 UP 空间全部动态（最全、可翻历史）→ qfps_space.json，并被 feedall 依赖
"""抓取某 UP「空间」里的全部动态（比关注动态 feed 更全，可一直翻历史）。
用法:
  python3 bili_space.py [host_mid] [--pages N] [--full] [--json out.json]
默认 host_mid=1420210197（青枫浦上Q），默认翻到没有 has_more 为止。
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


def major_text(major):
    t = major.get("type")
    if t == "MAJOR_TYPE_ARCHIVE":
        a = major["archive"]
        return f"🎬 {a.get('title','')} ({a.get('bvid','')})"
    if t == "MAJOR_TYPE_ARTICLE":
        return "📄 " + major["article"].get("title", "")
    if t == "MAJOR_TYPE_OPUS":
        op = major["opus"]
        return (op.get("title") or "") + (op.get("summary", {}).get("text", ""))
    if t == "MAJOR_TYPE_DRAW":
        return "🖼[图片动态]"
    return ""


def extract(item):
    m = item.get("modules", {})
    author = m.get("module_author", {})
    dyn = m.get("module_dynamic", {})
    desc = (dyn.get("desc") or {}).get("text", "") if dyn.get("desc") else ""
    major = dyn.get("major") or {}
    body = (desc or major_text(major) or "[无文字内容]").strip()
    dtype = item.get("type", "")
    return {
        "id": item.get("id_str", ""),
        "name": author.get("name", ""),
        "pub_time": author.get("pub_time", ""),
        "pub_ts": author.get("pub_ts", 0),
        "type": dtype,
        "is_forward": dtype == "DYNAMIC_TYPE_FORWARD",
        "major_type": major.get("type", ""),
        "text": body,
    }


def get_page(s, mk, host_mid, offset):
    """取一页，带 -352 风控 + 网络异常退避重试。返回 data 或 None（耗尽重试）。"""
    url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
    backoff = 30
    for attempt in range(8):
        p = {"host_mid": host_mid, "timezone_offset": -480}
        if offset:
            p["offset"] = offset
        try:
            j = s.get(url, params=wbi(p, mk), timeout=20).json()
        except requests.RequestException as e:
            print(f"    网络异常 {type(e).__name__}，{backoff}s 后重试({attempt+1}/8)…", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 240)
            continue
        code = j.get("code")
        if code == 0:
            return j["data"]
        if code == -352:
            print(f"    风控 -352，{backoff}s 后重试({attempt+1}/8)…", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 240)
            continue
        sys.exit(f"接口错误 code={code} msg={j.get('message')}（多半 Cookie 失效）")
    return None


def fetch_space(s, mk, host_mid, max_pages, save_path=None):
    out, offset, page, seen = [], "", 0, set()
    while max_pages == 0 or page < max_pages:
        data = get_page(s, mk, host_mid, offset)
        if data is None:
            print("    多次重试仍失败，已停止。已抓到的会保存。", file=sys.stderr)
            break
        items = data.get("items", [])
        added = 0
        for it in items:
            e = extract(it)
            if e["id"] in seen:
                continue
            seen.add(e["id"]); out.append(e); added += 1
        page += 1
        offset = data.get("offset", "")
        print(f"  第{page}页：+{added} 条，累计 {len(out)}", file=sys.stderr)
        if save_path:  # 每页落盘，崩了不丢
            save_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        if not data.get("has_more") or not offset:
            break
        time.sleep(5.0)
    return out


def main():
    args = sys.argv[1:]
    full = "--full" in args
    if full:
        args.remove("--full")
    out_json = HERE / "qfps_space.json"
    if "--json" in args:
        i = args.index("--json")
        out_json = Path(args[i + 1])
        del args[i:i + 2]
    max_pages = 0
    if "--pages" in args:
        i = args.index("--pages")
        max_pages = int(args[i + 1])
        del args[i:i + 2]
    host_mid = int(args[0]) if args else 1420210197

    s = make_session(load_cookie())
    mk = mixin_key(s)
    print(f"抓取空间动态 host_mid={host_mid} ...", file=sys.stderr)
    items = fetch_space(s, mk, host_mid, max_pages, save_path=out_json)
    out_json.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    orig = sum(1 for x in items if not x["is_forward"])
    fwd = sum(1 for x in items if x["is_forward"])
    print(f"\n共 {len(items)} 条（原创 {orig}，转发 {fwd}）。已存 {out_json.name}")
    if items:
        print(f"时间跨度：{items[-1]['pub_time']}  →  {items[0]['pub_time']}")
    for i, x in enumerate(items, 1):
        tag = "↻转发" if x["is_forward"] else "原创"
        body = x["text"] if full else (x["text"][:80] + ("…" if len(x["text"]) > 80 else ""))
        print(f"{i}. [{x['pub_time']}|{tag}] {body}")


if __name__ == "__main__":
    main()
