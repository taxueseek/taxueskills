#!/usr/bin/env python3
"""
taxue-memory.py — 踏雪决策记忆系统

记录 taxue 每次决策（子 skill 使用、收束结论），存为 JSONL 格式，
支持独立查询、趋势分析；export 可导出通用摘要 JSONL。

用法:
  python3 taxue-memory.py record --skill solve --query "创业方向" --note "推荐先做行业调研"
  python3 taxue-memory.py query --skill solve                    # 查某技能历史
  python3 taxue-memory.py query --recent 5                       # 最近 5 条
  python3 taxue-memory.py query --search "创业"                  # 关键词搜索
  python3 taxue-memory.py stats                                  # 统计概览
  python3 taxue-memory.py export --since 2026-07-01              # 导出通用摘要

存储位置: ~/.taxue/decisions.jsonl
"""

from _common import read_json, read_text, json_out
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TAXUE_DIR = Path.home() / ".taxue"
DECISIONS_PATH = TAXUE_DIR / "decisions.jsonl"

# ── 记录 ──


def record_decision(skill, query, outcome_note, satisfaction="", context=""):
    """记录一条 taxue 决策到 JSONL."""
    TAXUE_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "type": "taxue_decision",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skill": skill,
        "query": query[:500],
        "outcome": outcome_note[:500],
        "satisfaction": satisfaction,
        "context": context[:200] if context else "",
        "session_source": "taxue",
    }
    with open(DECISIONS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


# ── 查询 ──


def _iter_decisions(path=None):
    """Yield parsed decision entries, newest first."""
    path = path or DECISIONS_PATH
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def query_by_skill(skill, limit=10):
    """按子 skill 名查询历史决策."""
    results = []
    for entry in _iter_decisions():
        if entry.get("skill") == skill:
            results.append(entry)
            if len(results) >= limit:
                break
    return results


def query_recent(limit=5):
    """最近 N 条决策."""
    results = []
    for entry in _iter_decisions():
        results.append(entry)
        if len(results) >= limit:
            break
    return results


def query_by_keyword(keyword, limit=10):
    """关键词搜索（query/outcome 字段）。"""
    kw = keyword.lower()
    results = []
    for entry in _iter_decisions():
        text = (entry.get("query", "") + " " + entry.get("outcome", "")).lower()
        if kw in text:
            results.append(entry)
            if len(results) >= limit:
                break
    return results


def query_by_timerange(since, until=None):
    """按时间范围查询."""
    results = []
    for entry in _iter_decisions():
        ts = entry.get("timestamp", "")
        if ts >= since:
            if until is None or ts <= until:
                results.append(entry)
    return results


# ── 统计 ──


def compute_stats():
    """统计：总决策数、按技能分布、按日趋势."""
    total = 0
    by_skill = {}
    by_date = {}
    for entry in _iter_decisions():
        total += 1
        skill = entry.get("skill", "unknown")
        by_skill[skill] = by_skill.get(skill, 0) + 1
        date = entry.get("timestamp", "")[:10]
        if date:
            by_date[date] = by_date.get(date, 0) + 1
    return {
        "total": total,
        "by_skill": dict(sorted(by_skill.items(), key=lambda x: -x[1])),
        "by_date": dict(sorted(by_date.items())),
    }


# ── 导出（通用摘要 JSONL）──


def export_for_sd(since=""):
    """导出为通用决策摘要 JSONL（一行一条）。"""
    entries = list(_iter_decisions())
    if since:
        entries = [e for e in entries if e.get("timestamp", "") >= since]

    for entry in entries:
        summary = json.dumps(
            {
                "_type": "taxue_decision_summary",
                "query_intent": entry.get("query", "")[:100],
                "analysis": "决策: %s | 结果: %s" % (
                    entry.get("skill", ""),
                    entry.get("outcome", "")[:200],
                ),
                "timestamp": entry.get("timestamp", ""),
                "memory_tier": "periodic",
            },
            ensure_ascii=False,
        )
        print(summary)


# ── CLI ──


def main():
    parser = argparse.ArgumentParser(description="踏雪决策记忆系统")
    sub = parser.add_subparsers(dest="cmd")

    # record
    r = sub.add_parser("record", help="记录一条决策")
    r.add_argument("--skill", required=True)
    r.add_argument("--query", default="")
    r.add_argument("--note", default="", dest="outcome_note")
    r.add_argument("--satisfaction", default="")
    r.add_argument("--context", default="")

    # query
    q = sub.add_parser("query", help="查询决策历史")
    q.add_argument("--skill", default="")
    q.add_argument("--recent", type=int, default=0)
    q.add_argument("--search", default="")
    q.add_argument("--since", default="")
    q.add_argument("--limit", type=int, default=10)

    # stats
    sub.add_parser("stats", help="统计概览")

    # export
    e = sub.add_parser("export", help="导出通用摘要 JSONL")
    e.add_argument("--since", default="")

    args = parser.parse_args()

    if args.cmd == "record":
        entry = record_decision(
            skill=args.skill,
            query=args.query,
            outcome_note=args.outcome_note,
            satisfaction=args.satisfaction,
            context=args.context,
        )
        print("[taxue-memory] 已记录: %s → %s" % (args.skill, entry["timestamp"]))
        return

    if args.cmd == "query":
        if args.recent:
            results = query_recent(limit=args.recent)
        elif args.skill:
            results = query_by_skill(args.skill, limit=args.limit)
        elif args.search:
            results = query_by_keyword(args.search, limit=args.limit)
        elif args.since:
            results = query_by_timerange(args.since)
        else:
            results = query_recent(limit=args.limit)

        if not results:
            print("(无匹配决策记录)")
            return
        for r in results:
            ts = r.get("timestamp", "?")[:19]
            skill = r.get("skill", "?")
            query = r.get("query", "")[:60]
            note = r.get("outcome", "")[:80]
            print("  [%s] %s: %s" % (ts, skill, query))
            if note:
                print("         → %s" % note)
        return

    if args.cmd == "stats":
        s = compute_stats()
        print("taxue 决策记忆统计")
        print("  总决策数: %s" % s["total"])
        print("  按技能分布:")
        for skill, count in s["by_skill"].items():
            bar = "█" * count
            print("    %-15s %3d %s" % (skill, count, bar))
        print("  按日期:")
        for date, count in s["by_date"].items():
            print("    %s: %d" % (date, count))
        return

    if args.cmd == "export":
        export_for_sd(since=args.since)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
