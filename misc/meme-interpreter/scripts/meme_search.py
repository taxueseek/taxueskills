#!/usr/bin/env python3
"""meme_search.py — 梗解读定向检索 CLI

内置六个免认证数据源的直接查询，带缓存。
萌娘百科 API 已关闭、微信指数无公开接口，这两个不在此脚本内，用 web_search 定向查询。

用法:
  python3 meme_search.py geng <query>    # itotii 梗百科（中文流行语释义）
  python3 meme_search.py ud <term>       # Urban Dictionary（英文俚语）
  python3 meme_search.py kym <query>     # Know Your Meme（英文 meme 溯源）
  python3 meme_search.py zh <query>      # 百度百科（结构化卡片）
  python3 meme_search.py wiki <query>    # 中文维基百科（权威词条）
  python3 meme_search.py hot             # 热榜聚合（B站 + 百度 + 头条）
  python3 meme_search.py all <query>     # 自动路由聚合：中文词查 geng+zh+wiki，英文词查 ud+kym
  python3 meme_search.py cache-clear     # 清空缓存

缓存: ~/.cache/meme_search/。词条查询 TTL 6 小时，热榜 TTL 10 分钟。
失败与限流结果不写缓存，避免把瞬时错误冻成 6 小时空结果。
"""

import argparse
import hashlib
import html as html_mod
import json
import os
from pathlib import Path
import socket
import ipaddress
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

CACHE_DIR = os.path.expanduser("~/.cache/meme_search")
TTL = 6 * 3600          # 词条查询缓存
HOT_TTL = 10 * 60       # 热榜缓存
TIMEOUT = 12
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def cache_get(key, ttl=TTL):
    if not re.fullmatch(r"[a-z_0-9]+", key):
        return None
    path = os.path.join(CACHE_DIR, key + ".json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if time.time() - data.get("ts", 0) < ttl:
            return data.get("payload")
    except Exception:
        pass
    return None


def cache_set(key, payload):
    if not re.fullmatch(r"[a-z_0-9]+", key):
        raise ValueError(f"非法缓存 key: {key}")
    os.makedirs(CACHE_DIR, exist_ok=True)
    Path(CACHE_DIR, key + ".json").write_text(
        json.dumps({"ts": time.time(), "payload": payload}, ensure_ascii=False))


_ALLOWED_HOSTS = {"geng.itotii.com", "baike.baidu.com", "zh.wikipedia.org", "api.urbandictionary.com", "knowyourmeme.com"}


def _validate_url(url):
    """仅允许 http/https 到白名单站点；拒绝其他协议、主机与受限制地址。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or (parsed.hostname or "") not in _ALLOWED_HOSTS:
        raise ValueError(f"不允许的请求目标: {url}")
    ip_obj = ipaddress.ip_address(socket.getaddrinfo(parsed.hostname, None)[0][4][0])
    if not ip_obj.is_global or ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_link_local:
        raise ValueError(f"解析到受限制地址: {ip_obj}")


def http_get(url, timeout=TIMEOUT, headers=None):
    _validate_url(url)
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def http_get_retry(url, retries=3, timeout=TIMEOUT, headers=None, retry_on=(429, 503)):
    """带退避重试的 GET。遇限流状态码时等待后重试。"""
    last_err = None
    for attempt in range(retries):
        try:
            return http_get(url, timeout=timeout, headers=headers)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in retry_on and attempt < retries - 1:
                time.sleep(0.6 * (attempt + 1))
                continue
            raise
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(0.4 * (attempt + 1))
                continue
            raise
    raise last_err


def is_error_item(item):
    return isinstance(item, dict) and "error" in item


def cached_call(source, query, fn, ttl=TTL, display=None):
    """调用 fn，结果写缓存。异常返回带展示名 source 的 error dict，且不缓存。

    source: 缓存 key 前缀（英文短名，稳定）
    display: 输出区展示名，须与结果 item 的 source 字段一致
    """
    label = display or source
    key = source + "_" + hashlib.md5(query.encode()).hexdigest()[:16]
    hit = cache_get(key, ttl)
    if hit is not None:
        return hit
    try:
        payload = fn()
    except Exception as e:
        return {"source": label, "error": f"{label} 查询失败: {e}"}
    # 空列表正常（词条不存在），可缓存；error 不走缓存
    cache_set(key, payload)
    return payload


def as_flat_list(results):
    """把单源 list / error dict / 多源嵌套结果统一成 list[dict]。"""
    if results is None:
        return []
    if isinstance(results, dict):
        return [results]
    flat = []
    for r in results:
        if isinstance(r, list):
            flat.extend(r)
        elif isinstance(r, dict):
            flat.append(r)
    return flat


def strip_tags(s):
    text = html_mod.unescape(re.sub(r"<[^>]+>", "", s or ""))
    return re.sub(r"\s+", " ", text).strip()


# ---------- itotii 梗百科（WordPress REST API，免认证） ----------

def search_geng(query, limit=5):
    url = (
        "https://geng.itotii.com/wp-json/wp/v2/posts?search="
        + urllib.parse.quote(query)
        + f"&per_page={limit}"
    )

    def run():
        data = json.loads(http_get(url))
        out = []
        for p in data:
            out.append({
                "source": "itotii 梗百科",
                "title": strip_tags(p.get("title", {}).get("rendered", "")),
                "date": p.get("date", "") or "",
                "summary": strip_tags(p.get("content", {}).get("rendered", ""))[:200],
                "url": p.get("link", ""),
            })
        return out

    return cached_call("geng", query, run, display="itotii 梗百科")


# ---------- 百度百科（BaikeLemmaCardApi 开放接口，免认证） ----------
# 该接口有间歇限流（errno:2），需重试；限流不得缓存为空列表。

def search_baike(query, retries=4):
    url = (
        "https://baike.baidu.com/api/openapi/BaikeLemmaCardApi"
        f"?scope=103&format=json&appid=379020&bk_key={urllib.parse.quote(query)}"
    )

    def run():
        last_errno = None
        for attempt in range(retries):
            data = json.loads(http_get(url))
            if not data:
                return []
            # 限流 / 临时错误：重试，不要当成「无词条」
            if "errno" in data and "title" not in data:
                last_errno = data.get("errno")
                time.sleep(0.35 * (attempt + 1))
                continue
            if "title" not in data:
                return []
            parts = []
            for c in data.get("card", []) or []:
                name = c.get("name", "")
                vals = c.get("value", [])
                vals = vals if isinstance(vals, list) else [vals]
                text = "、".join(strip_tags(str(v)) for v in vals if v)
                if text:
                    parts.append(f"{name}: {text}" if name else text)
            # card 为空时仍返回 title + desc，总比空结果有用
            summary = "；".join(parts)[:400]
            if not summary and data.get("desc"):
                summary = strip_tags(str(data.get("desc", "")))
            if not summary and data.get("abstract"):
                summary = strip_tags(str(data.get("abstract", "")))[:400]
            return [{
                "source": "百度百科",
                "title": data.get("title", ""),
                "desc": data.get("desc", ""),
                "summary": summary,
                "url": "https://baike.baidu.com/item/" + urllib.parse.quote(data.get("title", "")),
            }]
        raise RuntimeError(f"接口限流或暂时不可用 (errno={last_errno})")

    return cached_call("baike", query, run, display="百度百科")


# ---------- 中文维基百科（MediaWiki API，免认证） ----------

def search_wiki(query, limit=5):
    url = (
        "https://zh.wikipedia.org/w/api.php?action=query&list=search"
        f"&srsearch={urllib.parse.quote(query)}&srlimit={limit}&format=json"
        "&origin=*"
    )
    # MediaWiki 要求可识别 UA，裸 Chrome 串容易 429
    wiki_headers = {
        "User-Agent": "meme-interpreter/1.1 (skill CLI; educational; contact: local)",
        "Accept": "application/json",
    }

    def run():
        data = json.loads(http_get_retry(url, retries=4, headers=wiki_headers))
        out = []
        for s in data.get("query", {}).get("search", []):
            title = s.get("title", "")
            snippet = strip_tags(s.get("snippet", ""))[:150]
            out.append({
                "source": "中文维基百科",
                "title": title,
                "snippet": snippet,
                "url": "https://zh.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
            })
        return out

    return cached_call("wiki", query, run, display="中文维基百科")


# ---------- Urban Dictionary（官方 API，免认证） ----------

def search_ud(term, limit=3):
    url = "https://api.urbandictionary.com/v0/define?term=" + urllib.parse.quote(term)

    def run():
        data = json.loads(http_get(url))
        out = []
        for d in data.get("list", [])[:limit]:
            out.append({
                "source": "Urban Dictionary",
                "word": d.get("word", ""),
                "definition": d.get("definition", "").replace("\r\n", " ")[:300],
                "example": d.get("example", "").replace("\r\n", " ")[:200],
                "date": d.get("written_on", "") or "",
                "url": d.get("permalink", ""),
            })
        return out

    return cached_call("ud", term, run, display="Urban Dictionary")


# ---------- Know Your Meme（HTML 解析，带 UA 即可） ----------

def search_kym(query, limit=5):
    url = "https://knowyourmeme.com/search?q=" + urllib.parse.quote(query)

    def run():
        page = http_get(url)
        out = []
        for m in re.finditer(r'<a class="item"[^>]*>', page):
            href = re.search(r'href="([^"]+)"', m.group(0))
            alt = re.search(r'alt="([^"]*)"', m.group(0))
            author = re.search(r'data-author="([^"]*)"', m.group(0))
            if not href:
                continue
            path = href.group(1)
            if path.startswith("/sensitive/"):
                continue  # 受限内容，跳过
            out.append({
                "source": "Know Your Meme",
                "title": html_mod.unescape(alt.group(1) if alt else path.rsplit("/", 1)[-1]).strip(),
                "author": author.group(1) if author else "",
                "url": "https://knowyourmeme.com" + path,
            })
            if len(out) >= limit:
                break
        return out

    return cached_call("kym", query, run, display="Know Your Meme")


# ---------- 热榜聚合（B站 + 百度 + 头条，均免认证） ----------

def fetch_hot_bilibili(limit=10):
    def run():
        data = json.loads(http_get(
            "https://api.bilibili.com/x/web-interface/search/square?limit=20"
        ))
        items = data.get("data", {}).get("trending", {}).get("list", [])
        return [{
            "source": "B站热搜",
            "keyword": i.get("keyword", ""),
            "url": "https://search.bilibili.com/all?keyword=" + urllib.parse.quote(i.get("keyword", "")),
        } for i in items[:limit] if i.get("keyword")]

    return cached_call("hot_bili", "hot", run, ttl=HOT_TTL, display="B站热搜")


def fetch_hot_baidu(limit=10):
    def run():
        page = http_get("https://top.baidu.com/board?tab=realtime")
        words = re.findall(r'word":"([^"]+)"', page)
        seen, out = set(), []
        for w in words:
            if w not in seen:
                seen.add(w)
                out.append({
                    "source": "百度热搜",
                    "keyword": w,
                    "url": "https://www.baidu.com/s?wd=" + urllib.parse.quote(w),
                })
            if len(out) >= limit:
                break
        return out

    return cached_call("hot_baidu", "hot", run, ttl=HOT_TTL, display="百度热搜")


def fetch_hot_toutiao(limit=10):
    def run():
        data = json.loads(http_get(
            "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
        ))
        items = data.get("data", [])
        return [{
            "source": "今日头条热榜",
            "keyword": i.get("Title", ""),
            "url": i.get("Url", ""),
        } for i in items[:limit] if i.get("Title")]

    return cached_call("hot_tt", "hot", run, ttl=HOT_TTL, display="今日头条热榜")


# ---------- 输出 ----------

def fmt_geng(r):
    date = (r.get("date") or "")[:10] or "未知日期"
    return f"- [{date}] {r.get('title', '')} — {r.get('summary', '')} | {r.get('url', '')}"


def fmt_baike(r):
    d = f"（{r['desc']}）" if r.get("desc") else ""
    summary = r.get("summary") or "（无卡片详情）"
    return f"- {r.get('title', '')}{d}: {summary} | {r.get('url', '')}"


def fmt_wiki(r):
    return f"- {r.get('title', '')} — {r.get('snippet', '')} | {r.get('url', '')}"


def fmt_ud(r):
    date = (r.get("date") or "")[:10] or "未知日期"
    ex = f"  例: {r['example']}" if r.get("example") else ""
    return f"- [{date}] {r.get('word', '')}: {r.get('definition', '')}\n{ex}\n  {r.get('url', '')}"


def fmt_kym(r):
    author = f" ({r['author']})" if r.get("author") else ""
    return f"- {r.get('title', '')}{author} | {r.get('url', '')}"


def render(results, query):
    results = as_flat_list(results)
    lines = [f"## {query}\n"]
    order = [
        ("itotii 梗百科", fmt_geng),
        ("百度百科", fmt_baike),
        ("中文维基百科", fmt_wiki),
        ("Urban Dictionary", fmt_ud),
        ("Know Your Meme", fmt_kym),
    ]
    shown = False
    for src, fmt in order:
        items = [r for r in results if r.get("source") == src and not is_error_item(r)]
        errs = [r for r in results if r.get("source") == src and is_error_item(r)]
        if items:
            lines.append(f"### {src}")
            lines.extend(fmt(r) for r in items)
            lines.append("")
            shown = True
        elif errs:
            lines.append(f"### {src}")
            lines.append(f"- {errs[0]['error']}")
            lines.append("")
            shown = True
    if not shown:
        for r in results:
            if is_error_item(r):
                lines.append(f"- {r['error']}")
                shown = True
        if not shown:
            lines.append("（未查到结果）\n")
    return "\n".join(lines).rstrip() + "\n"


def render_hot(groups):
    groups = as_flat_list(groups)
    lines = ["## 热榜速览\n"]
    order = ["B站热搜", "百度热搜", "今日头条热榜"]
    for src in order:
        items = [r for r in groups if r.get("source") == src and not is_error_item(r)]
        errs = [r for r in groups if r.get("source") == src and is_error_item(r)]
        if items:
            lines.append(f"### {src}")
            for i, r in enumerate(items, 1):
                lines.append(f"{i}. {r.get('keyword', '')}")
            lines.append("")
        elif errs:
            lines.append(f"### {src}")
            lines.append(f"- {errs[0]['error']}")
            lines.append("")
        else:
            lines.append(f"### {src}")
            lines.append("- （暂无数据）")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def is_cjk(t):
    if not t:
        return False
    return sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff") >= len(t) * 0.3


def main():
    ap = argparse.ArgumentParser(description="梗解读定向检索")
    ap.add_argument("cmd", choices=["geng", "ud", "kym", "zh", "wiki", "hot", "all", "cache-clear"])
    ap.add_argument("query", nargs="?", default="")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    if args.cmd == "cache-clear":
        if os.path.isdir(CACHE_DIR):
            for f in os.listdir(CACHE_DIR):
                os.remove(os.path.join(CACHE_DIR, f))
            print("缓存已清空")
        else:
            print("无缓存")
        return

    if args.cmd == "hot":
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = [
                ex.submit(fetch_hot_bilibili),
                ex.submit(fetch_hot_baidu),
                ex.submit(fetch_hot_toutiao),
            ]
            groups = [f.result() for f in futs]
        print(render_hot(groups))
        return

    if not args.query:
        print("缺少查询词", file=sys.stderr)
        sys.exit(1)

    q = args.query.strip()
    if args.cmd == "all":
        with ThreadPoolExecutor(max_workers=3) as ex:
            if is_cjk(q):
                # 中文词查 itotii + 百度百科 + 中文维基
                futs = [
                    ex.submit(search_geng, q, args.limit),
                    ex.submit(search_baike, q),
                    ex.submit(search_wiki, q, args.limit),
                ]
            else:
                # 英文词查 Urban Dictionary + Know Your Meme
                futs = [
                    ex.submit(search_ud, q, 3),
                    ex.submit(search_kym, q, args.limit),
                ]
            results = [f.result() for f in futs]
        print(render(results, q))
    elif args.cmd == "geng":
        print(render(search_geng(q, args.limit), q))
    elif args.cmd == "zh":
        print(render(search_baike(q), q))
    elif args.cmd == "wiki":
        print(render(search_wiki(q, args.limit), q))
    elif args.cmd == "ud":
        print(render(search_ud(q, 3), q))
    elif args.cmd == "kym":
        print(render(search_kym(q, args.limit), q))


if __name__ == "__main__":
    main()
