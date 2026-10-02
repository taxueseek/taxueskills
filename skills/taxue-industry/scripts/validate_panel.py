#!/usr/bin/env python3
"""validate_panel.py — Persona Studio 面板 schema 校验器

校验面板 JSON 是否符合 panel-schema.md 契约。
可离线运行，无外部依赖（仅标准库）。

用法：
  python3 validate_panel.py panels/<slug>.json
  python3 validate_panel.py panels/           # 校验整个目录
  python3 validate_panel.py --init           # 初始化面板目录 + 空 index.json
  python3 validate_panel.py --self-test      # 运行自检（S 级验收）

退出码：0 = 全部通过；1 = 存在失败项
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "1.0"
REQUIRED_DIMENSIONS = [
    "identity", "pain_points", "motivations", "behaviors",
    "decision_path", "language", "anti_persona",
]
VALID_CONFIDENCE = {"L1", "L2", "L3"}
VALID_PANEL_TYPES = {"user", "market", "competitor", "gtm"}
SLUG_RE = re.compile(r"^[a-z0-9-]+$")

PANELS_DIR = Path.home() / ".taxue" / "panels"


def validate_panel(path: Path) -> list[str]:
    """校验单个面板，返回错误列表（空 = 通过）。"""
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"JSON 解析失败: {e}"]

    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version 应为 {SCHEMA_VERSION}，实际 {data.get('schema_version')}")

    slug = data.get("slug", "")
    if not SLUG_RE.match(slug):
        errors.append(f"slug 应匹配 ^[a-z0-9-]+$，实际 '{slug}'")

    ptype = data.get("panel_type", "user")  # 兼容旧面板（默认 user）
    if ptype not in VALID_PANEL_TYPES:
        errors.append(f"panel_type 应为 user/market/competitor/gtm，实际 '{ptype}'")
        return errors

    if ptype == "user":
        errors.extend(_validate_user_panel(data))
    else:
        errors.extend(_validate_business_panel(data))

    conf = data.get("confidence")
    if conf not in VALID_CONFIDENCE:
        errors.append(f"confidence 应为 L1/L2/L3，实际 '{conf}'")

    return errors


def _validate_user_panel(data: dict) -> list[str]:
    """用户画像 7 维校验。"""
    errors: list[str] = []
    dims = data.get("dimensions", {})
    for dim in REQUIRED_DIMENSIONS:
        if dim not in dims:
            errors.append(f"缺少维度: {dim}")
            continue
        attrs = dims[dim].get("attributes", [])
        if not attrs:
            errors.append(f"维度 {dim} 的 attributes 为空")
            continue
        for i, attr in enumerate(attrs):
            if not attr.get("evidence"):
                errors.append(f"维度 {dim} 第 {i} 条 attribute 缺 evidence 字段")
    return errors


def _validate_business_panel(data: dict) -> list[str]:
    """商业面板 payload 校验（market/competitor/gtm）。"""
    errors: list[str] = []
    ptype = data.get("panel_type")
    payload = data.get("payload", {})

    if ptype == "market":
        if not payload.get("tam"):
            errors.append("market 面板缺 payload.tam")
        if not payload.get("verdict"):
            errors.append("market 面板缺 payload.verdict（值得进/谨慎/不进）")
    elif ptype == "competitor":
        comps = payload.get("competitors", [])
        if not comps:
            errors.append("competitor 面板缺 payload.competitors（≥1）")
        for i, c in enumerate(comps):
            if not c.get("name"):
                errors.append(f"competitor[{i}] 缺 name")
        if not payload.get("verdict"):
            errors.append("competitor 面板缺 payload.verdict")
    elif ptype == "gtm":
        if not payload.get("north_star_market"):
            errors.append("gtm 面板缺 payload.north_star_market")
        if not payload.get("value_proposition"):
            errors.append("gtm 面板缺 payload.value_proposition")

    if not data.get("evidence"):
        errors.append("商业面板缺顶层 evidence（来源链接列表）")
    return errors


def validate_index() -> list[str]:
    """校验 index.json 注册表的引用完整性。"""
    errors: list[str] = []
    index_path = PANELS_DIR / "index.json"
    if not index_path.exists():
        return ["缺少 index.json 注册表"]
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"index.json 解析失败: {e}"]

    panels = index.get("panels", [])
    existing = {p.stem for p in PANELS_DIR.glob("*.json") if p.name != "index.json"}
    for p in panels:
        slug = p.get("slug", "")
        if slug not in existing:
            errors.append(f"注册表引用不存在的面板: {slug}")
    for f in existing:
        if not any(p.get("slug") == f for p in panels):
            errors.append(f"面板 {f}.json 未注册到 index.json")
    return errors


def run_self_test() -> int:
    """内置自检：验证校验器自身逻辑正确。"""
    import tempfile

    failures = 0

    # 有效面板应通过
    valid = {
        "schema_version": "1.0", "slug": "test-panel", "name": "测试",
        "created": "2026-08-04", "updated": "2026-08-04", "confidence": "L2",
        "dimensions": {
            d: {"summary": "x", "attributes": [{"name": "a", "value": "b", "evidence": "C-01", "confidence": "high"}]}
            for d in REQUIRED_DIMENSIONS
        },
        "evidence_log": [], "sources": [],
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "valid.json"
        p.write_text(json.dumps(valid, ensure_ascii=False), encoding="utf-8")
        if validate_panel(p):
            failures += 1
            print("❌ 有效面板被误报")

    # 缺维度应失败
    bad = dict(valid)
    bad["dimensions"] = {"identity": {"attributes": []}}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "bad.json"
        p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        errs = validate_panel(p)
        if not errs:
            failures += 1
            print("❌ 无效面板未被检出")

    # 缺 evidence 应失败
    no_ev = dict(valid)
    no_ev["dimensions"]["identity"] = {
        "attributes": [{"name": "a", "value": "b"}],
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "noev.json"
        p.write_text(json.dumps(no_ev, ensure_ascii=False), encoding="utf-8")
        errs = validate_panel(p)
        if not any("evidence" in e for e in errs):
            failures += 1
            print("❌ 缺 evidence 未被检出")

    # ─── 商业面板（market）───
    base_biz = {
        "schema_version": "1.0", "slug": "m-1", "name": "市场", "panel_type": "market",
        "created": "2026-08-04", "updated": "2026-08-04", "confidence": "L1",
        "evidence": ["src"], "payload": {},
    }
    good_market = dict(base_biz)
    good_market["payload"] = {"tam": {"value": "1亿", "source": "x"}, "verdict": "值得进"}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m-ok.json"
        p.write_text(json.dumps(good_market, ensure_ascii=False), encoding="utf-8")
        if validate_panel(p):
            failures += 1
            print("❌ 有效 market 面板被误报")

    bad_market = dict(base_biz)
    bad_market["payload"] = {}  # 缺 tam + verdict
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m-bad.json"
        p.write_text(json.dumps(bad_market, ensure_ascii=False), encoding="utf-8")
        errs = validate_panel(p)
        if not any("tam" in e for e in errs) or not any("verdict" in e for e in errs):
            failures += 1
            print("❌ 无效 market 面板未被检出")

    # ─── 商业面板（competitor）───
    good_comp = dict(base_biz)
    good_comp["slug"] = "c-1"
    good_comp["panel_type"] = "competitor"
    good_comp["payload"] = {"competitors": [{"name": "A"}], "verdict": "差异化"}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "c-ok.json"
        p.write_text(json.dumps(good_comp, ensure_ascii=False), encoding="utf-8")
        if validate_panel(p):
            failures += 1
            print("❌ 有效 competitor 面板被误报")

    bad_comp = dict(good_comp)
    bad_comp["payload"] = {"competitors": []}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "c-bad.json"
        p.write_text(json.dumps(bad_comp, ensure_ascii=False), encoding="utf-8")
        errs = validate_panel(p)
        if not any("competitors" in e for e in errs):
            failures += 1
            print("❌ 无效 competitor 面板未被检出")

    # ─── 商业面板（gtm）───
    good_gtm = dict(base_biz)
    good_gtm["slug"] = "g-1"
    good_gtm["panel_type"] = "gtm"
    good_gtm["payload"] = {"north_star_market": "x", "value_proposition": {"for": "a"}}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "g-ok.json"
        p.write_text(json.dumps(good_gtm, ensure_ascii=False), encoding="utf-8")
        if validate_panel(p):
            failures += 1
            print("❌ 有效 gtm 面板被误报")

    bad_gtm = dict(good_gtm)
    bad_gtm["payload"] = {}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "g-bad.json"
        p.write_text(json.dumps(bad_gtm, ensure_ascii=False), encoding="utf-8")
        errs = validate_panel(p)
        if not any("north_star" in e for e in errs):
            failures += 1
            print("❌ 无效 gtm 面板未被检出")

    # 无效 panel_type 应失败
    bad_type = dict(valid)
    bad_type["panel_type"] = "bogus"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t-bad.json"
        p.write_text(json.dumps(bad_type, ensure_ascii=False), encoding="utf-8")
        errs = validate_panel(p)
        if not any("panel_type" in e for e in errs):
            failures += 1
            print("❌ 非法 panel_type 未被检出")

    if failures:
        print(f"自检失败: {failures} 项")
        return 1
    print("自检通过: 校验器逻辑正确")
    return 0

def init_panels_dir() -> int:
    """初始化面板目录 + index.json。"""
    PANELS_DIR.mkdir(parents=True, exist_ok=True)
    index_path = PANELS_DIR / "index.json"
    if not index_path.exists():
        index_path.write_text(
            json.dumps({"schema_version": SCHEMA_VERSION, "panels": []}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(f"面板目录已初始化: {PANELS_DIR}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--self-test":
        return run_self_test()
    if args and args[0] == "--init":
        return init_panels_dir()

    if not args:
        print(__doc__)
        return 1

    target = Path(args[0])
    if target.is_dir():
        # index.json 是注册表，不是面板，单独走 validate_index
        files = sorted(f for f in target.glob("*.json") if f.name != "index.json")
        all_errors = {}
        for f in files:
            errs = validate_panel(f)
            if errs:
                all_errors[f.name] = errs
        idx_errs = validate_index() if target == PANELS_DIR else []
        if idx_errs:
            all_errors["index.json"] = idx_errs
        if all_errors:
            for name, errs in all_errors.items():
                print(f"❌ {name}:")
                for e in errs:
                    print(f"   - {e}")
            return 1
        print(f"✅ {len(files)} 个面板全部通过校验（index.json 引用完整）")
        return 0

    errs = validate_panel(target)
    if errs:
        for e in errs:
            print(f"❌ {e}")
        return 1
    print(f"✅ 面板校验通过: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
