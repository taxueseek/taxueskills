#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""taxue-note-archiver 主脚本：从 NoteSync.db 提取原子笔记，分门别类增量归档到踏雪素材库。

用法：
  python3 archive_notes.py                # 默认源，增量归档（跳过已归档 guid）
  python3 archive_notes.py --since 2      # 只处理最近 2 天的笔记（按 cacheTime）
  python3 archive_notes.py --dry-run      # 只统计不写文件
  python3 archive_notes.py --db PATH      # 指定其他数据库
  python3 archive_notes.py --all          # 全量重跑（忽略增量，覆盖目标文件前先备份）

设计：
- 提取：NoteCache 表（guid 去重取最新）→ HTML 转纯文本
- 分类：视觉/生图类 16 桶 + 其他类 6 桶（关键词表在 categories.py）
- 增量：读目标归档文件已有 guid，只写新增条目，guid 可回溯
- 输出：分类统计 + 归档路径 + 提炼提示
"""
import argparse
import html
import os
import re
import sqlite3
import sys
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import categories as C


def html_to_text(h):
    """原子笔记 contentNote 是 HTML，转纯文本。"""
    if not h:
        return ''
    h = re.sub(r'<br[^>]*>', '\n', h)
    h = re.sub(r'</p>', '\n', h)
    h = re.sub(r'<[^>]+>', '', h)
    return html.unescape(h).strip()


def load_notes(db_path, since_days=None):
    """读 NoteCache，guid 去重取最新，返回 [(guid, text), ...]。"""
    if not os.path.exists(db_path):
        sys.exit(f"数据库不存在: {db_path}")
    db = sqlite3.connect(db_path)
    cur = db.cursor()
    sql = "SELECT guid, contentNote, cacheTime FROM NoteCache"
    params = ()
    if since_days:
        cutoff = int((datetime.datetime.now() - datetime.timedelta(days=since_days)).timestamp() * 1000)
        sql += " WHERE cacheTime >= ?"
        params = (cutoff,)
    cur.execute(sql, params)
    rows = cur.fetchall()
    db.close()

    latest = {}
    for guid, content, ct in sorted(rows, key=lambda r: r[2]):  # cacheTime 升序，后者覆盖 = 取最新（不依赖 sqlite 默认顺序）
        text = html_to_text(content)
        if text:
            latest[guid] = text
    items = list(latest.items())
    print(f"源 {os.path.basename(db_path)}：{len(rows)} 条缓存 → 去重后 {len(items)} 条笔记")
    return items


def is_visual(text):
    return any(kw in text for kw in C.VISUAL_KW)


def classify_visual(text):
    for name, kws in C.VISUAL_CATS:
        if not kws:
            continue
        if any(kw in text for kw in kws):
            return name
    return C.VISUAL_CATS[-1][0]


def classify_other(text):
    for name, kws in C.OTHER_CATS:
        if not kws:
            continue
        if any(kw in text for kw in kws):
            return name
    return C.OTHER_CATS[-1][0]


def existing_guids_all(vis_dir, oth_dir):
    """读所有归档文件（视觉+其他全部桶）的 guid 并集，跨桶全局去重。"""
    known = set()
    for d in (vis_dir, oth_dir):
        if not os.path.isdir(d):
            continue
        for p in Path(d).glob('*.md'):
            known |= set(re.findall(r'guid[`：:]\s*`?([0-9a-f]{32})', p.read_text(encoding='utf-8')))
    return known


def fmt_entry(guid, text, seq):
    title = text.split('\n')[0].strip()[:40] if text else '(空)'
    return (f"### {title}\n"
            f"- 笔记序号：{seq} ｜ guid：`{guid}`\n"
            f"- 内容：\n```\n{text}\n```\n")


def ensure_header(path, title, desc):
    """文件不存在时写头部；写入路径必须落在素材根目录内。"""
    p = Path(path)
    if '..' in str(p) or Path(C.BASE_MATERIAL).resolve() not in p.resolve().parents:
        raise ValueError(f"归档路径越界: {p}")
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# {title}\n\n> 来源：vivo 原子笔记（NoteSync 缓存自动归档）\n"
                 f"> 说明：{desc}。guid 保留可回溯。\n\n---\n\n", encoding='utf-8')


def archive(items, dry_run):
    """分类 + 增量写入，返回统计。"""
    buckets = {}
    seq = 0
    for guid, text in items:
        seq += 1
        if is_visual(text):
            cat = classify_visual(text)
            if cat == '05_雕塑摆件':
                # 雕塑桶严格词修正：命中核心词才留桶，否则掉其他视觉
                if not any(kw in text[:500] for kw in C.SCULPT_STRICT_KW):
                    cat = '15_其他视觉'
        else:
            cat = classify_other(text)
        buckets.setdefault(cat, []).append((guid, text, seq))

    vis_dir = Path(C.BASE_MATERIAL) / C.VISUAL_DIR
    oth_dir = Path(C.BASE_MATERIAL) / C.OTHER_DIR
    vis_names = {name for name, _ in C.VISUAL_CATS}
    stats = {'visual': {}, 'other': {}}
    total_new = 0
    known_all = existing_guids_all(vis_dir, oth_dir)

    oth_names = {name for name, _ in C.OTHER_CATS}
    for cat, notes in sorted(buckets.items()):
        if cat not in vis_names and cat not in oth_names:
            cat = C.OTHER_CATS[-1][0]  # 防御：分类名必须出自白名单，路径不可被注入
        is_vis_cat = cat in vis_names
        target_dir = vis_dir if is_vis_cat else oth_dir
        path = target_dir / f'{cat}.md'
        new = [(g, t, s) for g, t, s in notes if g not in known_all]
        known_all |= {g for g, _, _ in new}
        total_new += len(new)

        if is_vis_cat:
            stats['visual'][cat] = (len(notes), len(new))
        else:
            stats['other'][cat] = (len(notes), len(new))

        if not dry_run and new:
            desc = '自动分类归档' if is_vis_cat else '非视觉提示词归档'
            ensure_header(path, cat, desc)
            with open(path, 'a', encoding='utf-8') as f:
                for g, t, s in new:
                    f.write(fmt_entry(g, t, s))

    print(f"\n新增待归档 {total_new} 条（去重后），dry_run={'是' if dry_run else '否'}")
    print("\n== 视觉/生图类 ==")
    for cat, (n, new) in sorted(stats['visual'].items()):
        print(f"  {cat}: 本次 {n} 条 / 新增 {new} 条")
    print("\n== 其他类 ==")
    for cat, (n, new) in sorted(stats['other'].items()):
        print(f"  {cat}: 本次 {n} 条 / 新增 {new} 条")
    if not dry_run and total_new:
        print(f"\n已写入：{vis_dir}（视觉）、{oth_dir}（其他）")
    return total_new


def main():
    ap = argparse.ArgumentParser(description='原子笔记提示词提取归档')
    ap.add_argument('--db', default=C.DEFAULT_DB, help='NoteSync.db 路径')
    ap.add_argument('--since', type=int, default=None, help='只处理最近 N 天（按缓存时间）')
    ap.add_argument('--dry-run', action='store_true', help='只统计不写文件')
    ap.add_argument('--all', action='store_true', help='全量重跑（忽略增量，重复 guid 自动跳过）')
    args = ap.parse_args()

    items = load_notes(args.db, since_days=args.since)
    if not items:
        print('无笔记，退出')
        return 0
    archive(items, args.dry_run)

    print('\n提示：新增条目的精品提炼方向见 taxue-creative-style/memory/vivo-notes-refined.md')
    print('      （新条目如需提炼，先跑本脚本归档，再按提炼稿模板操作）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
