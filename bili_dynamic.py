#!/usr/bin/env python3
"""读取 B 站「我的关注动态」。需要在 cookie.txt 里放你自己的登录 Cookie。"""
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

# WBI 混淆表（B 站固定）
MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def load_cookie() -> str:
    if not COOKIE_FILE.exists():
        sys.exit(f"找不到 {COOKIE_FILE}\n请把浏览器里 B 站的 Cookie 整段粘进这个文件。")
    ck = COOKIE_FILE.read_text(encoding="utf-8").strip()
    if "SESSDATA" not in ck:
        sys.exit("cookie.txt 里没有 SESSDATA，说明不是登录态的 Cookie，拿不到动态。")
    return ck


def make_session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Referer": "https://t.bilibili.com/",
        "Origin": "https://t.bilibili.com",
        "Cookie": cookie,
    })
    return s


def get_mixin_key(s: requests.Session) -> str:
    r = s.get("https://api.bilibili.com/x/web-interface/nav", timeout=10)
    data = r.json()["data"]["wbi_img"]
    img = data["img_url"].rsplit("/", 1)[-1].split(".")[0]
    sub = data["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    raw = img + sub
    return "".join(raw[i] for i in MIXIN_TAB)[:32]


def wbi_sign(params: dict, mixin_key: str) -> dict:
    params = dict(params)
    params["wts"] = int(time.time())
    query = urllib.parse.urlencode(sorted(params.items()))
    params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return params


def fetch_feed(s: requests.Session, mixin_key: str, offset: str = "") -> dict:
    url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all"
    params = {"type": "all", "page": 1}
    if offset:
        params["offset"] = offset
    params = wbi_sign(params, mixin_key)
    r = s.get(url, params=params, timeout=10)
    j = r.json()
    if j.get("code") != 0:
        sys.exit(f"接口返回错误 code={j.get('code')} msg={j.get('message')}\n"
                 f"多半是 Cookie 失效，重新复制一份新的到 cookie.txt。")
    return j["data"]


def summarize(item: dict, full: bool = False) -> str:
    m = item.get("modules", {})
    author = m.get("module_author", {})
    name = author.get("name", "?")
    pub = author.get("pub_time", "")
    dyn = m.get("module_dynamic", {})
    # 正文
    desc = ""
    if dyn.get("desc"):
        desc = dyn["desc"].get("text", "")
    major = dyn.get("major") or {}
    title = ""
    if major.get("type") == "MAJOR_TYPE_ARCHIVE":
        title = "🎬 " + major["archive"].get("title", "")
    elif major.get("type") == "MAJOR_TYPE_ARTICLE":
        title = "📄 " + major["article"].get("title", "")
    elif major.get("type") == "MAJOR_TYPE_OPUS":
        op = major["opus"]
        title = (op.get("title") or "") + (op.get("summary", {}).get("text", ""))
    body = (desc or title or "[无文字内容]").strip().replace("\n", " ")
    if not full and len(body) > 100:
        body = body[:100] + "…"
    did = item.get("id_str", "")
    return f"【{name}】{pub}\n  {body}\n  https://t.bilibili.com/{did}"


def author_name(item: dict) -> str:
    return item.get("modules", {}).get("module_author", {}).get("name", "")


def main():
    # 用法: bili_dynamic.py [页数] [--up UP名]
    args = sys.argv[1:]
    full = False
    if "--full" in args:
        full = True
        args.remove("--full")
    up_filter = None
    if "--up" in args:
        i = args.index("--up")
        up_filter = args[i + 1]
        del args[i:i + 2]
    pages = int(args[0]) if args else (8 if up_filter else 1)

    s = make_session(load_cookie())
    mixin_key = get_mixin_key(s)
    offset = ""
    n = 0
    for _ in range(pages):
        data = fetch_feed(s, mixin_key, offset)
        for it in data.get("items", []):
            if up_filter and up_filter not in author_name(it):
                continue
            n += 1
            print(f"{n}. {summarize(it, full)}\n")
        offset = data.get("offset", "")
        if not data.get("has_more"):
            break
    tip = f"（仅 {up_filter}）" if up_filter else ""
    print(f"共 {n} 条动态。{tip}")


if __name__ == "__main__":
    main()
