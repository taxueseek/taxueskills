#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
腾讯校招官网岗位 JD 抓取与简历匹配引擎。

直接调用 join.qq.com 公开接口，无需鉴权，仅依赖标准库。
普通岗位详情使用 desc/request 字段；青云计划课题类岗位详情使用 topicDetail/topicRequirement 字段。

用法：
    python3 scripts/fetch_recruit_jds.py search --keyword 后台 --page-size 10
    python3 scripts/fetch_recruit_jds.py detail 1200791473415778304
    python3 scripts/fetch_recruit_jds.py match "Python 后台 分布式 MySQL Redis 深圳"
    python3 scripts/fetch_recruit_jds.py dicts

输出纪律：默认紧凑 JSON，且岗位/匹配列表默认只渲染前 30 条（--limit N 调整，
--full 放开）。全量抓取类命令请显式加 --full，否则上千条岗位会一次性灌进上下文。
"""

import argparse
import concurrent.futures
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import socket
import ipaddress
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


def configure_output_encoding() -> None:
    """Avoid UnicodeEncodeError on Windows terminals with legacy encodings."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


configure_output_encoding()

BASE = "https://join.qq.com/api/v1"
POST_PAGE = "https://join.qq.com/post.html"
DETAIL_PAGE = "https://join.qq.com/post_detail.html?postid={post_id}"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_PROJECT_IDS = [1, 2, 12, 14, 20, 21, 5, 15]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": POST_PAGE,
    "Origin": "https://join.qq.com",
    "Accept": "application/json, text/plain, */*",
}

TECH_TERMS = [
    "Python", "Java", "Go", "Golang", "C++", "C/C++", "JavaScript", "TypeScript", "React", "Vue",
    "后台", "后端", "服务端", "前端", "客户端", "测试", "运维", "安全", "数据", "算法", "机器学习", "深度学习",
    "NLP", "自然语言", "多模态", "计算机视觉", "CV", "推荐", "搜索", "大模型", "LLM", "AIGC",
    "分布式", "高并发", "微服务", "数据库", "MySQL", "Redis", "NoSQL", "Kubernetes", "Docker", "Linux",
    "产品", "运营", "市场", "设计", "交互", "视觉", "游戏", "策划", "财务", "HR", "法务",
]
CITY_TERMS = ["深圳", "深圳总部", "北京", "上海", "广州", "成都", "武汉", "杭州", "合肥", "香港", "远程"]
PROJECT_KEYWORDS = {
    "实习": [2, 12, 20],
    "应届": [1, 14, 21],
    "校招": [1, 14, 21],
    "青云": [14, 20],
    "提前批": [21],
}


def _timestamp() -> int:
    return int(time.time() * 1000)


def _json_dumps(data: Any, pretty: bool = True) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2 if pretty else None)

def _validate_url(url: str) -> None:
    """仅允许 https 到 join.qq.com；拒绝其他协议、主机与受限制地址。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "join.qq.com":
        raise ValueError(f"不允许的请求目标: {url}")
    ip_obj = ipaddress.ip_address(socket.getaddrinfo(parsed.hostname, None)[0][4][0])
    if not ip_obj.is_global or ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_link_local:
        raise ValueError(f"解析到受限制地址: {ip_obj}")


_REQUEST_CACHE: Dict[Tuple[str, str, str], Tuple[float, Dict[str, Any]]] = {}
_SESSION_TS: Optional[float] = None


def _bump_timestamp() -> int:
    """会话内共用时间戳，提升请求可缓存性；超过 60s 自动刷新。"""
    global _SESSION_TS
    now = time.time()
    if _SESSION_TS is None or now - _SESSION_TS > 60:
        _SESSION_TS = now
    return int(_SESSION_TS * 1000)


def _request_json(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    referer: str = POST_PAGE,
    timeout: int = 20,
    retries: int = 2,
    cache_ttl: float = 0.0,
) -> Dict[str, Any]:
    """统一请求入口：TTL 缓存 + 指数退避重试。

    cache_ttl > 0 时按 (method, path, body, referer) 缓存响应，
    避免同一会话重复拉取字典类接口。
    """
    body_text = json.dumps(body, ensure_ascii=False) if body is not None else ""
    cache_key = (method.upper(), path, body_text, referer)
    if cache_ttl > 0 and cache_key in _REQUEST_CACHE:
        cached_at, cached = _REQUEST_CACHE[cache_key]
        if time.time() - cached_at < cache_ttl:
            return cached

    sep = "&" if "?" in path else "?"
    url = f"{BASE}{path}{sep}timestamp={_bump_timestamp()}"
    try:
        _validate_url(url)
    except ValueError as e:
        return {"status": -1, "message": str(e), "data": None}
    headers = {**HEADERS, "Referer": referer}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json;charset=UTF-8"

    last_error: Dict[str, Any] = {"status": -1, "message": "请求失败", "data": None}
    for attempt in range(max(1, retries + 1)):
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                result = json.loads(raw)
            if cache_ttl > 0:
                _REQUEST_CACHE[cache_key] = (time.time(), result)
            return result
        except urllib.error.HTTPError as e:
            last_error = {"status": -1, "message": f"HTTP {e.code}: {e.reason}", "data": None}
        except urllib.error.URLError as e:
            last_error = {"status": -1, "message": f"网络错误: {e}", "data": None}
        except json.JSONDecodeError as e:
            last_error = {"status": -1, "message": f"JSON 解析失败: {e}", "data": None}
        except Exception as e:
            last_error = {"status": -1, "message": f"未知错误: {e}", "data": None}
        if attempt < retries:
            time.sleep(min(0.4 * (2 ** attempt), 3.0))
    return last_error


def _map_parallel(fn: Callable[[Any], Any], items: Sequence[Any], workers: int = 6) -> List[Any]:
    """并发映射。详情类 I/O 绑定调用必须走它，串行会把延迟线性叠加。

    与 fetch_recruit_info.py 的同名实现保持一致；两脚本各自独立、不跨文件依赖。
    """
    items = list(items)
    if not items:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as pool:
        return list(pool.map(fn, items))


def _as_int_list(value: Optional[str]) -> List[int]:
    if not value:
        return []
    out = []
    for part in re.split(r"[,，\s]+", value.strip()):
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            pass
    return out


def _normalize_page_size(value: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = DEFAULT_PAGE_SIZE
    return max(1, min(MAX_PAGE_SIZE, n))


def _flatten_project_ids(items: Iterable[Dict[str, Any]]) -> List[int]:
    ids = []
    for item in items or []:
        children = item.get("subDictionary") or []
        if children:
            ids.extend(_flatten_project_ids(children))
        else:
            try:
                ids.append(int(item.get("code")))
            except (TypeError, ValueError):
                pass
    return sorted(set(ids))


def get_all_project_ids() -> List[int]:
    data = _request_json("GET", "/position/getAllProject", cache_ttl=86400.0)
    ids = _flatten_project_ids(data.get("data") or []) if data.get("status") == 0 else []
    return ids or DEFAULT_PROJECT_IDS


def get_dicts() -> Dict[str, Any]:
    dictionary = _request_json("GET", "/dictionary/?types=RecruitType,BusinessGroup,RecruitProjectPostList", cache_ttl=86400.0)
    projects = _request_json("GET", "/position/getAllProject", cache_ttl=86400.0)
    families = _request_json("GET", "/position/getPositionFamily?lang=zh-cn", cache_ttl=86400.0)
    work_cities = _request_json("GET", "/position/getPositionWorkCities?lang=zh-cn", cache_ttl=86400.0)
    recruit_cities = _request_json("GET", "/position/getRecruitCity?lang=zh-cn", cache_ttl=86400.0)
    return {
        "success": all(x.get("status") == 0 for x in [dictionary, projects, families, work_cities, recruit_cities]),
        "source": "join.qq.com",
        "dictionary": dictionary.get("data"),
        "projects": projects.get("data"),
        "position_families": families.get("data"),
        "work_cities": work_cities.get("data"),
        "recruit_cities": recruit_cities.get("data"),
    }


def _build_search_body(
    keyword: str = "",
    project_ids: Optional[List[int]] = None,
    bg_ids: Optional[List[int]] = None,
    work_city_ids: Optional[List[int]] = None,
    recruit_city_ids: Optional[List[int]] = None,
    position_family_ids: Optional[List[int]] = None,
    page_index: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Dict[str, Any]:
    return {
        "projectIdList": project_ids or get_all_project_ids(),
        "keyword": (keyword or "").strip()[:30],
        "bgList": bg_ids or [],
        "workCountryType": 0,
        "workCityList": work_city_ids or [],
        "recruitCityList": recruit_city_ids or [],
        "positionFidList": position_family_ids or [],
        "pageIndex": max(1, int(page_index or 1)),
        "pageSize": _normalize_page_size(page_size),
    }


def _first_text(data: Dict[str, Any], *keys: str) -> str:
    """按字段优先级取第一个非空文本；青云岗位会用 topicDetail/topicRequirement 承载 JD。"""
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _field_source(data: Dict[str, Any], *keys: str) -> str:
    """返回第一个非空文本字段名，便于排查官网字段来源。"""
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return key
    return ""


def _format_list_item(item: Dict[str, Any]) -> Dict[str, Any]:
    post_id = str(item.get("postId") or "")
    return {
        "post_id": post_id,
        "position_id": item.get("id"),
        "position_code": item.get("position"),
        "title": item.get("positionTitle") or "",
        "direction_id": item.get("positionFamily"),
        "project_id": item.get("projectId"),
        "project_name": item.get("projectName") or "",
        "recruit_label": item.get("recruitLabelName") or "",
        "bgs": (item.get("bgs") or "").strip(),
        "work_cities": (item.get("workCities") or "").strip(),
        "source": item.get("positionSource") or "join.qq.com",
        "apply_url": DETAIL_PAGE.format(post_id=urllib.parse.quote(post_id)) if post_id else POST_PAGE,
    }


def _search_positions_api(
    keyword: str = "",
    project_ids: Optional[List[int]] = None,
    bg_ids: Optional[List[int]] = None,
    work_city_ids: Optional[List[int]] = None,
    recruit_city_ids: Optional[List[int]] = None,
    position_family_ids: Optional[List[int]] = None,
    page_index: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Dict[str, Any]:
    body = _build_search_body(
        keyword=keyword,
        project_ids=project_ids,
        bg_ids=bg_ids,
        work_city_ids=work_city_ids,
        recruit_city_ids=recruit_city_ids,
        position_family_ids=position_family_ids,
        page_index=page_index,
        page_size=page_size,
    )
    data = _request_json("POST", "/position/searchPosition", body=body)
    payload = data.get("data") or {}
    raw_items = payload.get("positionList") or []
    items = [_format_list_item(x) for x in raw_items]
    return {
        "success": data.get("status") == 0,
        "source": "join.qq.com",
        "query": body,
        "count": payload.get("count", len(items)),
        "page_index": body["pageIndex"],
        "page_size": body["pageSize"],
        "positions": items,
        "message": data.get("message") or ("ok" if data.get("status") == 0 else "接口返回异常"),
    }


def _keyword_terms(keyword: str) -> List[str]:
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    lower_keyword = keyword.lower()
    terms: List[str] = []
    known_terms = list(PROJECT_KEYWORDS.keys()) + TECH_TERMS + CITY_TERMS + ["青云", "青云计划", "qingyun"]
    for term in known_terms:
        if term.lower() in lower_keyword:
            terms.append("青云" if term.lower() == "qingyun" else term)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.]{1,20}", keyword):
        terms.append(token)
    if not terms:
        terms.extend(x for x in re.split(r"[\s,，/、|]+", keyword) if x)
    return list(dict.fromkeys(x.lower() for x in terms if x.strip()))



def _local_match_count(item: Dict[str, Any], keyword: str) -> int:
    """统计岗位摘要中命中的关键词数；至少命中 1 个即算匹配。"""
    terms = _keyword_terms(keyword)
    if not terms:
        return 1
    haystack = " ".join(str(item.get(k) or "") for k in [
        "title", "project_name", "recruit_label", "bgs", "work_cities", "position_code"
    ]).lower()
    return sum(1 for term in terms if term in haystack)


def _merge_positions(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for group in groups:
        for item in group or []:
            key = item.get("post_id") or item.get("position_id") or item.get("title")
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


LOCAL_RECALL_TERMS = tuple(PROJECT_KEYWORDS.keys()) + tuple(CITY_TERMS)
CATALOG_MAX_PAGES = 12


def _needs_local_recall(keyword: str, api_total: int, recall: Optional[bool]) -> bool:
    """是否做「全量抓取 + 本地字段补召回」。

    实测（全量 997 岗位）：地点词与招聘批次词的补召回收益极大（深圳 +601、
    实习 +556、青云 +99），而职能与技能词收益恒为 0（后台/算法/产品/数据/
    测试/运营/Python 全是 0）。所以默认只对前两类补扫；api_total == 0
    （标题完全没命中）时也补扫，这样任意地名都能兜住。
    需要强制或禁用时用 recall 参数（CLI: --recall / --no-recall）。
    """
    if recall is not None:
        return recall
    kw = (keyword or "").strip()
    if not kw:
        return False
    if api_total == 0:
        return True
    return any(term in kw for term in LOCAL_RECALL_TERMS)


def search_positions(
    keyword: str = "",
    project_ids: Optional[List[int]] = None,
    bg_ids: Optional[List[int]] = None,
    work_city_ids: Optional[List[int]] = None,
    recruit_city_ids: Optional[List[int]] = None,
    position_family_ids: Optional[List[int]] = None,
    page_index: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    recall: Optional[bool] = None,
    recall_max_pages: int = CATALOG_MAX_PAGES,
) -> Dict[str, Any]:
    api_result = _search_positions_api(
        keyword=keyword,
        project_ids=project_ids,
        bg_ids=bg_ids,
        work_city_ids=work_city_ids,
        recruit_city_ids=recruit_city_ids,
        position_family_ids=position_family_ids,
        page_index=page_index,
        page_size=page_size,
    )
    keyword = (keyword or "").strip()
    if not keyword or not api_result.get("success"):
        return api_result

    api_total = int(api_result.get("count") or 0)
    api_items = api_result.get("positions") or []
    api_result["api_total"] = api_total
    api_result["api_title_match_count"] = len(api_items)
    if not _needs_local_recall(keyword, api_total, recall):
        api_result["local_field_match_count"] = 0
        api_result["local_recall"] = "skipped"
        return api_result

    # 补召回必须扫完整目录。旧实现的 needed_pages 启发式在 api_total 小时只扫 2-3 页，
    # 城市/批次类关键词会静默丢召回（实测 深圳 真实 601，旧逻辑只拿到约 300）。
    all_result = fetch_all_positions(
        max_pages=max(1, int(recall_max_pages or CATALOG_MAX_PAGES)),
        page_size=100,
        keyword=keyword,
        project_ids=project_ids,
        bg_ids=bg_ids,
        work_city_ids=work_city_ids,
        recruit_city_ids=recruit_city_ids,
        position_family_ids=position_family_ids,
    )
    local_matches = (all_result.get("positions") or []) if all_result.get("success") else []
    merged = _merge_positions(api_items, local_matches)
    api_result["positions"] = merged
    api_result["count"] = len(merged)
    api_result["local_field_match_count"] = len(local_matches)
    api_result["local_recall"] = "full-sweep"
    if local_matches:
        api_result["note"] = "官网 keyword 搜索可能只匹配岗位标题；已补充全量岗位中的招聘标签、项目名称等字段本地匹配，避免青云等岗位漏召回。"
    return api_result


def get_jd_detail(post_id: str) -> Dict[str, Any]:
    post_id = (post_id or "").strip()
    if not post_id or len(post_id) > 80 or not re.fullmatch(r"[A-Za-z0-9_-]+", post_id):
        return {"success": False, "source": "join.qq.com", "message": "无效 postId", "post_id": post_id, "data": None}
    referer = DETAIL_PAGE.format(post_id=urllib.parse.quote(post_id))
    data = _request_json("GET", f"/jobDetails/getJobDetailsByPostId?postId={urllib.parse.quote(post_id)}", referer=referer)
    d = data.get("data") or {}
    if data.get("status") != 0 or not d:
        return {"success": False, "source": "join.qq.com", "message": data.get("message") or "未获取到岗位详情", "post_id": post_id}
    description_keys = ("desc", "topicDetail", "introduction")
    requirement_keys = ("request", "topicRequirement")
    detail = {
        "post_id": str(d.get("postId") or post_id),
        "title": d.get("title") or "",
        "direction": d.get("tidName") or "",
        "project_name": d.get("projectName") or "",
        "recruit_label": d.get("recruitLabelName") or "",
        "description": _first_text(d, *description_keys),
        "requirements": _first_text(d, *requirement_keys),
        "description_source_field": _field_source(d, *description_keys),
        "requirements_source_field": _field_source(d, *requirement_keys),
        "graduate_bonus": d.get("graduateBonus") or "",
        "intern_bonus": d.get("internBonus") or "",
        "introduction": d.get("introduction") or "",
        "work_cities": d.get("workCityList") or [],
        "recruit_cities": d.get("recruitCityList") or [],
        "is_qingyun": bool(d.get("isQingyun")),
        "apply_url": DETAIL_PAGE.format(post_id=urllib.parse.quote(str(d.get("postId") or post_id))),
    }
    return {"success": True, "source": "join.qq.com", "jd": detail}


def fetch_all_positions(
    max_pages: int = 50,
    page_size: int = 100,
    keyword: str = "",
    project_ids: Optional[List[int]] = None,
    bg_ids: Optional[List[int]] = None,
    work_city_ids: Optional[List[int]] = None,
    recruit_city_ids: Optional[List[int]] = None,
    position_family_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    max_pages = max(1, int(max_pages or 1))
    page_size = _normalize_page_size(page_size)
    all_items = []
    total = None
    for page in range(1, max_pages + 1):
        result = _search_positions_api(
            keyword="",
            project_ids=project_ids,
            bg_ids=bg_ids,
            work_city_ids=work_city_ids,
            recruit_city_ids=recruit_city_ids,
            position_family_ids=position_family_ids,
            page_index=page,
            page_size=page_size,
        )
        if not result.get("success"):
            return {"success": False, "source": "join.qq.com", "message": result.get("message"), "positions": all_items}
        if total is None:
            total = result.get("count")
        items = result.get("positions") or []
        if not items:
            break
        all_items.extend(items)
        if total is not None and len(all_items) >= int(total):
            break
    if keyword:
        scored = [(_local_match_count(x, keyword), x) for x in all_items]
        matched_items = [x for n, x in scored if n > 0]
        matched_items.sort(key=lambda x: _local_match_count(x, keyword), reverse=True)
    else:
        matched_items = all_items
    return {
        "success": True,
        "source": "join.qq.com",
        "count": len(matched_items) if keyword else (total or len(all_items)),
        "fetched": len(all_items),
        "positions": matched_items,
        "keyword": keyword or "",
        "note": "已全量抓取后按岗位标题、招聘标签、项目名称、BG、工作地等字段本地匹配。" if keyword else "已全量抓取官网岗位摘要。",
    }



def _extract_terms(text: str) -> Tuple[List[str], List[str], List[int]]:
    text = text or ""
    lower_text = text.lower()
    terms = []
    for term in TECH_TERMS:
        if term.lower() in lower_text:
            terms.append(term)
    cities = [city for city in CITY_TERMS if city in text]
    project_ids = []
    for key, ids in PROJECT_KEYWORDS.items():
        if key in text:
            project_ids.extend(ids)
    english_words = re.findall(r"[A-Za-z][A-Za-z0-9+#.]{1,20}", text)
    for word in english_words:
        if word not in terms and len(terms) < 20:
            terms.append(word)
    return list(dict.fromkeys(terms))[:20], list(dict.fromkeys(cities))[:8], sorted(set(project_ids))


def _score_text(haystack: str, terms: List[str], cities: List[str]) -> Tuple[int, List[str]]:
    haystack_lower = haystack.lower()
    score = 0
    reasons = []
    for term in terms:
        if term and term.lower() in haystack_lower:
            score += 3 if len(term) > 2 else 1
            if len(reasons) < 4:
                reasons.append(f"技能/经历关键词匹配：{term}")
    for city in cities:
        if city and city in haystack:
            score += 2
            if len(reasons) < 4:
                reasons.append(f"工作地偏好匹配：{city}")
    return score, reasons


def match_resume(text: str, top_n: int = 5, detail_candidates: int = 30) -> Dict[str, Any]:
    terms, cities, project_ids = _extract_terms(text)
    keyword = " ".join(terms[:3]) if terms else ""
    project_filter = project_ids or None
    # recall=True：简历匹配要最大召回。search_positions 在本轮已扫完全量目录，
    # 旧实现在候选不足 10 条时又叠了一次 fetch_all_positions(8 页)，是重复扫描。
    first = search_positions(keyword=keyword, project_ids=project_filter, page_index=1, page_size=100, recall=True)
    candidates = first.get("positions") or []

    scored = []
    for item in candidates:
        text_for_score = " ".join([
            item.get("title", ""), item.get("project_name", ""), item.get("recruit_label", ""),
            item.get("bgs", ""), item.get("work_cities", ""),
        ])
        score, reasons = _score_text(text_for_score, terms, cities)
        if score > 0:
            scored.append((score, item, reasons))
    scored.sort(key=lambda x: x[0], reverse=True)
    shortlist = scored[: max(top_n, detail_candidates)] or [(0, x, []) for x in candidates[:detail_candidates]]

    picked = shortlist[:detail_candidates]
    details = _map_parallel(lambda pair: get_jd_detail(pair[1].get("post_id", "")), picked)
    enriched = []
    for (base_score, item, base_reasons), detail in zip(picked, details):
        jd = detail.get("jd") or {}
        jd_text = " ".join([
            jd.get("title", ""), jd.get("direction", ""), jd.get("description", ""), jd.get("requirements", ""),
            jd.get("graduate_bonus", ""), jd.get("intern_bonus", ""), " ".join(jd.get("work_cities") or []),
        ])
        extra_score, extra_reasons = _score_text(jd_text, terms, cities)
        reasons = list(dict.fromkeys(base_reasons + extra_reasons))[:4]
        if not reasons:
            reasons = ["岗位信息来自腾讯校招官网，可进一步结合简历细节判断"]
        enriched.append((base_score + extra_score, {**item, "jd": jd, "match_reasons": reasons}))
    enriched.sort(key=lambda x: x[0], reverse=True)
    matches = [x[1] for x in enriched[:top_n]]

    return {
        "success": True,
        "source": "join.qq.com",
        "extracted_terms": terms,
        "city_preferences": cities,
        "project_filter": project_filter or "all",
        "matches": matches,
        "note": "岗位与 JD 均来自腾讯校招官网公开接口；对用户展示时不要输出分数或匹配百分比。",
    }


LIST_LIMIT_DEFAULT = 30


def _render(result: Dict[str, Any], limit: int, full: bool, pretty: bool) -> str:
    """统一出口闸门：岗位/匹配列表默认截断并标注总数。

    默认路径曾一次渲染 997 条岗位（402 KB），会把上下文直接打爆；需要全量时显式 --full。
    """
    if not full and limit > 0:
        for key in ("positions", "matches"):
            value = result.get(key)
            if isinstance(value, list) and len(value) > limit:
                result[f"{key}_total"] = len(value)
                result[key] = value[:limit]
                result["truncated"] = True
    return _json_dumps(result, pretty=pretty)


def _common_args() -> argparse.ArgumentParser:
    """公共输出开关：同时挂在主解析器和子解析器上，写在子命令前后都能生效。

    默认值用 SUPPRESS，避免子解析器的默认值覆盖主解析器已解析到的值。
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--compact", action="store_true", default=argparse.SUPPRESS, help="紧凑 JSON（默认）")
    common.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="缩进输出，便于人读")
    common.add_argument("--full", action="store_true", default=argparse.SUPPRESS, help="不截断列表，输出全部结果")
    common.add_argument("--limit", type=int, default=argparse.SUPPRESS, help=f"列表最多渲染条数，默认 {LIST_LIMIT_DEFAULT}")
    return common


def main() -> int:
    common = _common_args()
    parser = argparse.ArgumentParser(description="腾讯校招官网岗位 JD 抓取与匹配兜底工具", parents=[common])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="搜索官网岗位列表", parents=[common])
    p_search.add_argument("--keyword", default="", help="搜索关键词，最多取前 30 字")
    p_search.add_argument("--project-ids", default="", help="招聘项目 ID，逗号分隔；为空时自动取官网全部项目")
    p_search.add_argument("--bg-ids", default="", help="BG code，逗号分隔")
    p_search.add_argument("--work-city-ids", default="", help="工作城市 code，逗号分隔")
    p_search.add_argument("--recruit-city-ids", default="", help="面试城市 code，逗号分隔")
    p_search.add_argument("--position-family-ids", default="", help="岗位类别 code，逗号分隔，如技术=2、产品=3")
    p_search.add_argument("--page-index", type=int, default=1)
    p_search.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    p_search.add_argument("--recall", dest="recall", action="store_true", default=None, help="强制全量补召回")
    p_search.add_argument("--no-recall", dest="recall", action="store_false", help="禁用全量补召回（省下 2-12 次请求）")
    p_search.add_argument("--recall-pages", type=int, default=CATALOG_MAX_PAGES, help=f"补召回最多扫几页，默认 {CATALOG_MAX_PAGES}")

    p_detail = sub.add_parser("detail", help="按 postId 获取完整 JD", parents=[common])
    p_detail.add_argument("post_id")

    p_all = sub.add_parser("all", help="分页拉取岗位摘要", parents=[common])
    p_all.add_argument("--keyword", default="")
    p_all.add_argument("--max-pages", type=int, default=50)
    p_all.add_argument("--page-size", type=int, default=100)

    p_match = sub.add_parser("match", help="根据简历/背景文本匹配官网岗位", parents=[common])
    p_match.add_argument("text", help="简历或背景文本")
    p_match.add_argument("--top-n", type=int, default=5)
    p_match.add_argument("--detail-candidates", type=int, default=30)

    sub.add_parser("dicts", help="获取官网筛选字典", parents=[common])

    args = parser.parse_args()
    pretty = bool(getattr(args, "pretty", False)) and not bool(getattr(args, "compact", False))
    full = bool(getattr(args, "full", False))
    limit = max(1, int(getattr(args, "limit", LIST_LIMIT_DEFAULT) or LIST_LIMIT_DEFAULT))

    if args.cmd == "search":
        has_filters = any([
            (args.keyword or "").strip(),
            (args.project_ids or "").strip(),
            (args.bg_ids or "").strip(),
            (args.work_city_ids or "").strip(),
            (args.recruit_city_ids or "").strip(),
            (args.position_family_ids or "").strip(),
        ])
        if not has_filters and args.page_index == 1 and args.page_size == DEFAULT_PAGE_SIZE:
            result = fetch_all_positions(max_pages=CATALOG_MAX_PAGES, page_size=100)
            result["note"] = "未提供筛选条件，已自动改为全量抓取；输出默认只渲染前若干条，需要全部请加 --full。"
        else:
            result = search_positions(
                keyword=args.keyword,
                project_ids=_as_int_list(args.project_ids),
                bg_ids=_as_int_list(args.bg_ids),
                work_city_ids=_as_int_list(args.work_city_ids),
                recruit_city_ids=_as_int_list(args.recruit_city_ids),
                position_family_ids=_as_int_list(args.position_family_ids),
                page_index=args.page_index,
                page_size=args.page_size,
                recall=args.recall,
                recall_max_pages=args.recall_pages,
            )
    elif args.cmd == "detail":
        result = get_jd_detail(args.post_id)
    elif args.cmd == "all":
        result = fetch_all_positions(max_pages=args.max_pages, page_size=args.page_size, keyword=args.keyword)
    elif args.cmd == "match":
        result = match_resume(args.text, top_n=args.top_n, detail_candidates=args.detail_candidates)
    elif args.cmd == "dicts":
        result = get_dicts()
    else:
        parser.print_help()
        return 1

    print(_render(result, limit, full, pretty))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
