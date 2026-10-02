#!/usr/bin/env python3
"""
taxue 技能体系质量门 (Quality Gate) v1
自动检查所有 taxue skill 的版本一致性、必备章节完整性、反模式合规性。

用法:
  python3 taxue-quality-gate.py [--verbose]

--verbose: 输出每条检查细节

返回码: 0 = 全通过, 1 = 有告警, 2 = 有错误
"""

from _common import read_json, read_text, json_out
import json
import os
import re
import sys
from pathlib import Path

SKILLS_DIR = Path.home() / ".agents" / "skills"
TAXUE_DIR = SKILLS_DIR / "taxue"
SKILL_REGISTRY_PATH = TAXUE_DIR / "references" / "skill_registry.json"
COMBO_MAP_PATH = TAXUE_DIR / "references" / "combo_map.json"

# 已退役技能名——曾存在于路由体系、后被合并或删除。
# 任何 SKILL.md / references 再引用它们即为死链（2026-10-02 清理过一次）。
RETIRED_SKILLS = ["relate", "business", "roundtable", "speak", "talk",
                  "weread", "traffic", "material", "breakdown"]

# 必备章节（按优先级）
REQUIRED_SECTIONS = {
    "anti_patterns": {
        "patterns": [r"反模式声明", r"常见失败"],
        "label": "反模式声明",
        "severity": "error",
        "reason": "每个子 skill 必须有反模式声明，记录已知失败模式"
    },
    "do_not": {
        "patterns": [r"## DO NOT", r"DO NOT"],
        "label": "DO NOT 边界声明",
        "severity": "error",
        "reason": "每个子 skill 必须明确声明不处理什么"
    },
    "shared_rules_ref": {
        "patterns": [r"shared-rules\.md", r"共享规则"],
        "label": "共享规则引用",
        "severity": "warning",
        "reason": "子 skill 应引用 shared-rules.md 继承通用规则"
    },
    "version_footer": {
        "patterns": [r"\*taxue-.*v\d+\.\d+\.\d+.*\*"],
        "label": "版本脚注",
        "severity": "warning",
        "reason": "末尾应有版本号脚注"
    },
}

# 质量门检查 - 新的必备章节（从 v3.5.0 开始）
QUALITY_GATE_SECTIONS = {
    "outcome_contract": {
        "patterns": [r"Outcome Contract", r"产出契约"],
        "label": "Outcome Contract",
        "severity": "warning",
        "reason": "建议每个子 skill 有产出契约明确交付边界"
    },
    "quality_gate": {
        "patterns": [r"质量门", r"输出前.*查", r"自查"],
        "label": "输出前质量门",
        "severity": "warning",
        "reason": "建议每个子 skill 有输出前强制自查机制"
    },
}

# 纪律遵循检查 - shared-rules 执行层纪律
# 度量子 skill 是否显式内化了 taxue 体系的执行层纪律（非调度层）。
# 调度层纪律（连招收尾/记忆后置）由主入口 + combo_map 负责，子技能通过 shared-rules 继承即可，
# 不在子技能层重复检查（避免检查层级错误产生噪音）。
DISCIPLINE_SECTIONS = {
    "evidence_source": {
        "patterns": [r"来源", r"证据", r"引用", r"标注.*可靠"],
        "label": "证据来源",
        "severity": "warning",
        "reason": "shared-rules 核心：结论必须可追到来源，禁止无源断言"
    },
    "result_first": {
        "patterns": [r"结果优先", r"先结果", r"先给结果", r"先交付"],
        "label": "结果优先",
        "severity": "warning",
        "reason": "shared-rules 核心：先交付立场与可验证动作，过程只在改变质量时写入"
    },
}


def parse_frontmatter(content):
    """提取 frontmatter（无 yaml 依赖版）。

    支持标准 key: value 格式，不依赖 PyYAML（macOS 系统 Python 无预装）。
    跳过数组/嵌套结构——taxue 的 frontmatter 只用简单键值对。
    """
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return {}
    meta = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # 去掉引号
        if (val.startswith('"') and val.endswith('"')) or \
           (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        # 多行 description
        if val == "|":
            meta[key] = val
            continue
        meta[key] = val
    return meta


def parse_description(content, meta):
    """从 content 中提取完整的 description（处理 | 多行语法）。

    YAML frontmatter 中的 description: | 意味着后续缩进行都属于它；
    无 yaml 库时需手动拼接。
    """
    if meta.get("description") != "|":
        return meta.get("description", "")
    # 已由 parse_frontmatter 返回了文字描述
    return meta.get("description", "")


def check_version(metadata, name):
    """检查版本号。

    只校验格式：缺失 → warning（技能没写版本号不算坏），格式异常 → error。
    原来的「主版本线」检查已删除——决策系本身就是多版本线（3.4.1 / 3.5.4 /
    3.6.0 / 4.1.0），拿一条线去卡等于每次全量误报，把真问题埋了。
    """
    issues = []
    version = metadata.get("version", "")
    if not version:
        issues.append({
            "file": name,
            "severity": "warning",
            "field": "version",
            "desc": "缺少 version 字段"
        })
    elif not re.match(r'^\d+\.\d+\.\d+$', version):
        issues.append({
            "file": name,
            "severity": "error",
            "field": "version",
            "desc": f"版本号格式异常: {version}"
        })
    return issues


def check_required_sections(content, name, sections_to_check):
    """检查必备章节"""
    issues = []
    for section_id, config in sections_to_check.items():
        found = False
        for pattern in config["patterns"]:
            if re.search(pattern, content, re.IGNORECASE):
                found = True
                break
        if not found:
            issues.append({
                "file": name,
                "severity": config["severity"],
                "field": section_id,
                "desc": f"缺少 {config['label']}: {config['reason']}"
            })
    return issues


def check_anti_patterns(content, name):
    """额外检查：反模式应该至少有 3 条"""
    patterns = re.findall(r'###\s+失败\s+\d+', content)
    if len(patterns) == 0:
        # 也可能是 "失败 1：XXX" 格式
        patterns = re.findall(r'失败\s+\d+[：:]', content)
    if len(patterns) < 2:
        return [{
            "file": name,
            "severity": "warning",
            "field": "anti_pattern_count",
            "desc": f"反模式只有 {len(patterns)} 条，建议至少 3 条"
        }]
    return []


def check_output_boundary(content, name):
    """检查输出末尾是否导流到主入口"""
    issues = []
    if re.search(r'输出末尾', content) and not re.search(r'主入口', content):
        issues.append({
            "file": name,
            "severity": "warning",
            "field": "output_boundary",
            "desc": "有「输出末尾」章节但未提及导流交给主入口"
        })
    return issues


def check_shared_rules_integrity():
    """检查 shared-rules 真源是否包含全部核心纪律。

    纪律是继承机制：子 skill 通过引用 shared-rules 继承，不重复写。
    因此核心纪律只需在真源层验证一次（error 级），而非每个子 skill 各检查一次。
    """
    issues = []
    sr_path = TAXUE_DIR / "references" / "shared-rules.md"
    if not sr_path.exists():
        return [{
            "file": "shared-rules",
            "skill": "shared-rules",
            "severity": "error",
            "field": "shared_rules_missing",
            "desc": "shared-rules.md 真源不存在"
        }]
    content = read_text(sr_path)
    # 真源必须包含的纪律章节（与 DISCIPLINE_SECTIONS 对应）
    required = {
        "combo_followup": (r"连招收尾|可以接着|combo", "连招收尾纪律"),
        "memory_later": (r"记忆后置|开场不读|不读跨会话", "记忆后置纪律"),
        "evidence_source": (r"证据硬门|来源|证据", "证据来源纪律"),
        "result_first": (r"结果优先|先结果", "结果优先纪律"),
    }
    for fid, (pattern, label) in required.items():
        if not re.search(pattern, content):
            issues.append({
                "file": "shared-rules",
                "skill": "shared-rules",
                "severity": "error",
                "field": f"shared_rules_{fid}",
                "desc": f"shared-rules 真源缺少 {label}"
            })
    return issues


def load_skill_registry():
    """加载 SKILL_REGISTRY，不存在时返回 None."""
    if not SKILL_REGISTRY_PATH.exists():
        return None
    try:
        return read_json(SKILL_REGISTRY_PATH)
    except (json.JSONDecodeError, OSError):
        return None


def _routed_skill_names():
    """从主入口 SKILL.md 两张路由表的「路由」列抽取技能名。

    主入口路由表、registry aliases、子技能 description、combo_map 是同一份路由
    信息的四处副本，靠手工同步。这里把「路由表 ↔ registry」这一对变成机器可校验。
    """
    main = TAXUE_DIR / "SKILL.md"
    if not main.exists():
        return set()
    found = set()
    in_route_section = False
    for line in read_text(main).splitlines():
        if line.startswith("#"):
            # 只看路由表 / 组合信号表。主入口还有参考文件表、话术对照表，
            # 一并扫会把 grep、whisper、taxue-diagnosis 这类词误判成技能名。
            in_route_section = ("路由" in line) or ("组合信号" in line)
            continue
        if not in_route_section or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 2:
            continue
        for token in re.split(r"[+/、,，\s]+", cells[1]):
            token = token.strip("`*")
            if re.fullmatch(r"[a-z][a-z-]{2,}", token):
                found.add(token)
    return found


def check_registry_consistency(skills):
    """校验 registry ↔ 文件系统 ↔ 主入口路由表 三者一致。

    不再拿 `taxue-*` 通配跟 registry 比——那会把 19 个生图/视觉技能全判成
    「未注册」，是原来 202 条告警里的一大块噪声。改为只校验决策系：
    registry 登记的必须有目录；路由表出现的必须已登记；已登记的必须被路由到。
    """
    registry = load_skill_registry()
    if not registry:
        return [{
            "file": "taxue",
            "skill": "taxue",
            "severity": "warning",
            "field": "registry",
            "desc": "SKILL_REGISTRY 不存在，跳过一致性检查"
        }]

    issues = []
    registered = set(registry.get("skills", {}).keys())

    for name in sorted(registered):
        if not (SKILLS_DIR / ("taxue-" + name) / "SKILL.md").exists():
            issues.append({
                "file": name,
                "skill": name,
                "severity": "error",
                "field": "registry_orphan",
                "desc": "registry 登记了 %s，但文件系统无 taxue-%s/SKILL.md" % (name, name)
            })

    routed = _routed_skill_names()
    for name in sorted(routed - registered):
        issues.append({
            "file": name,
            "skill": name,
            "severity": "error",
            "field": "route_unregistered",
            "desc": "主入口路由到 %s，但 registry 未登记（路由表与 registry 已脱节）" % name
        })
    for name in sorted(registered - routed):
        issues.append({
            "file": name,
            "skill": name,
            "severity": "warning",
            "field": "route_missing",
            "desc": "registry 登记了 %s，但主入口路由表未出现该技能" % name
        })

    return issues


def _imported_by_sibling(scripts_dir, fname):
    """scripts/ 下被同目录其他脚本 import 的文件是库，不该要求 SKILL.md 引用它。"""
    if not fname.endswith(".py"):
        return False
    module = fname[:-3]
    if not module:
        return False
    pattern = re.compile(r"(?:^|\n)\s*(?:import|from)\s+%s\b" % re.escape(module))
    for sib in scripts_dir.glob("*.py"):
        if sib.name != fname and pattern.search(read_text(sib)):
            return True
    return False


def check_reference_orphans(skills):
    """检查技能自带的 references/scripts 是否被它自己的 SKILL.md 引用。

    「能力迁移」最常见的失败形态是搬了半截：文件到位了，SKILL.md 没写导航，
    于是这份能力在运行时根本不可达——等于没找回。2026-09-27 的重构就是这样
    丢掉 146 KB 的。这条检查把「到达性」变成机器可验证的。
    """
    issues = []
    for skill in skills:
        base = skill["path"].parent
        content = skill["content"]
        for sub in ("references", "scripts"):
            d = base / sub
            if not d.is_dir():
                continue
            for f in sorted(d.iterdir()):
                if f.is_dir() or f.name.startswith((".", "__")):
                    continue
                if sub == "scripts" and _imported_by_sibling(d, f.name):
                    continue
                if f.name not in content:
                    issues.append({
                        "file": skill["name"],
                        "skill": skill["name"],
                        "severity": "warning",
                        "field": "orphan_asset",
                        "desc": f"{sub}/{f.name} 未被 SKILL.md 引用（能力到位但运行时不可达）"
                    })
    return issues


def scan_all_skills():
    """扫描决策系技能文件。

    只扫 skill_registry.json 登记的子技能 + 主入口。原来的 `taxue-*` 通配会把
    生图/视觉家族（taxue-artist / taxue-photo-studio 等 19 个）一起卷进来，再
    用决策系的章节模板去卡它们，结果必然是 0 pass + 上百条噪声告警——门禁因此
    失去信号，等于没有质检。registry 已是单点真源，扫描名单从它派生。
    """
    skills = []

    main_file = TAXUE_DIR / "SKILL.md"
    if main_file.exists():
        skills.append({"name": "taxue", "path": main_file, "content": read_text(main_file)})

    registry = load_skill_registry() or {}
    for name in sorted(registry.get("skills", {})):
        d = SKILLS_DIR / ("taxue-" + name)
        skill_file = d / "SKILL.md"
        if skill_file.exists():
            skills.append({"name": d.name, "path": skill_file, "content": read_text(skill_file)})

    return skills


def check_combo_map():
    """校验 combo_map 自身与它对 registry 的一致。

    覆盖 2026-10-02 审计发现的三类真实事故：
    - 自环（next == 当前技能）→ 收束时会推荐「接着用自己」，与「已闭环干净停」冲突
    - registry.combo_exits 与 combo_map 实际 next 集合漂移（两份真源各说各话）
    - next 指向未登记技能（死出口）
    """
    issues = []
    if not COMBO_MAP_PATH.exists():
        return [{
            "file": "combo_map", "skill": "taxue", "severity": "error",
            "field": "combo_map_missing", "desc": "combo_map.json 不存在"
        }]
    try:
        combo = read_json(COMBO_MAP_PATH)
    except (json.JSONDecodeError, OSError) as e:
        return [{
            "file": "combo_map", "skill": "taxue", "severity": "error",
            "field": "combo_map_invalid", "desc": f"combo_map.json 解析失败: {e}"
        }]

    registry = load_skill_registry() or {}
    registered = set(registry.get("skills", {}).keys())
    combos = combo.get("combos", {})

    for skill_key, signals in combos.items():
        short = skill_key.replace("taxue-", "", 1)
        if short not in registered:
            issues.append({
                "file": "combo_map", "skill": "taxue", "severity": "error",
                "field": "combo_unregistered",
                "desc": f"combo_map 含未登记技能 {skill_key}"
            })
        for sig, sv in signals.items():
            nxt = sv.get("next", "")
            nxt_short = nxt.replace("taxue-", "", 1)
            if nxt == skill_key:
                issues.append({
                    "file": "combo_map", "skill": "taxue", "severity": "error",
                    "field": "combo_self_loop",
                    "desc": f"自环: {skill_key}.{sig} 的 next 指向自身"
                })
            if nxt_short not in registered:
                issues.append({
                    "file": "combo_map", "skill": "taxue", "severity": "error",
                    "field": "combo_dead_exit",
                    "desc": f"死出口: {skill_key}.{sig} → {nxt} 未在 registry 登记"
                })

    for name in sorted(registered):
        cm_exits = {sv.get("next", "").replace("taxue-", "", 1)
                    for sv in combos.get("taxue-" + name, {}).values()}
        reg_exits = set(registry["skills"][name].get("combo_exits", []))
        if cm_exits != reg_exits:
            issues.append({
                "file": "combo_map", "skill": "taxue", "severity": "error",
                "field": "combo_registry_drift",
                "desc": (f"{name} 出口漂移: registry-only={sorted(reg_exits - cm_exits)}, "
                         f"combo-only={sorted(cm_exits - reg_exits)}")
            })
    return issues


def check_dead_references(skills):
    """扫描决策系全部文本，引用已退役技能名即为死链。

    只匹配代码反引号或「去/用 X」语境，避免把正文普通词（如 business）误判。
    """
    issues = []
    targets = [(s["name"], s["content"]) for s in skills]
    for ref in (TAXUE_DIR / "references").glob("*.md"):
        targets.append((f"taxue/references/{ref.name}", read_text(ref)))
    for name, content in targets:
        for retired in RETIRED_SKILLS:
            if re.search(r"`%s`" % retired, content) or \
               re.search(r"[去用]\s*%s\b" % retired, content):
                issues.append({
                    "file": name, "skill": name, "severity": "error",
                    "field": "dead_reference",
                    "desc": f"引用已退役技能 {retired}（死链）"
                })
    return issues


def run_quality_gate(verbose=False, repair=False):
    """运行质量门"""
    all_issues = []
    stats = {"scanned": 0, "errors": 0, "warnings": 0, "pass": 0}
    
    skills = scan_all_skills()
    stats["scanned"] = len(skills)
    
    for skill in skills:
        name = skill["name"]
        content = skill["content"]
        metadata = parse_frontmatter(content)
        
        if verbose:
            version = metadata.get("version", "N/A")
            print(f"  [{name}] v{version}")
        
        issues = []
        
        is_main = name == "taxue"

        # 1. 版本检查（主入口也查）
        issues.extend(check_version(metadata, name))

        if not is_main:
            # 子技能模板：必备章节 / 质量门 / 纪律 / 反模式 / 输出边界。
            # 主入口是路由器，结构本就不同——拿子技能模板去卡它只会产出
            # 固定噪声（原来 5 条常驻告警），属检查层级错误。
            issues.extend(check_required_sections(content, name, REQUIRED_SECTIONS))
            issues.extend(check_required_sections(content, name, QUALITY_GATE_SECTIONS))
            issues.extend(check_required_sections(content, name, DISCIPLINE_SECTIONS))
            issues.extend(check_anti_patterns(content, name))
            issues.extend(check_output_boundary(content, name))
        
        for issue in issues:
            issue["skill"] = name
            all_issues.append(issue)
            if issue["severity"] == "error":
                stats["errors"] += 1
            else:
                stats["warnings"] += 1
        
        if not issues:
            stats["pass"] += 1
    
    # ------- 新检查：SKILL_REGISTRY 一致性 -------
    # 注册表中的技能名必须与 filesystem 上的子 skill 目录一一对应
    registry_issues = check_registry_consistency(skills)
    all_issues.extend(registry_issues)
    for issue in registry_issues:
        if issue["severity"] == "error":
            stats["errors"] += 1
        else:
            stats["warnings"] += 1

    # ------- 新检查：shared-rules 真源完整性 -------
    # 纪律继承机制：真源缺纪律 = 全部子技能继承失败（error 级，单点检查）
    sr_issues = check_shared_rules_integrity()
    all_issues.extend(sr_issues)
    for issue in sr_issues:
        if issue["severity"] == "error":
            stats["errors"] += 1
        else:
            stats["warnings"] += 1

    # ------- 新检查：自带资产的可达性 -------
    # 文件搬到位但 SKILL.md 没写导航 = 运行时不可达（2026-09-27 重构翻车的形态）
    orphan_issues = check_reference_orphans(skills)
    all_issues.extend(orphan_issues)
    for issue in orphan_issues:
        if issue["severity"] == "error":
            stats["errors"] += 1
        else:
            stats["warnings"] += 1

    # ------- 新检查：combo_map 与 registry 的出口一致性 -------
    combo_issues = check_combo_map()
    all_issues.extend(combo_issues)
    for issue in combo_issues:
        if issue["severity"] == "error":
            stats["errors"] += 1
        else:
            stats["warnings"] += 1

    # ------- 新检查：退役技能死链 -------
    dead_issues = check_dead_references(skills)
    all_issues.extend(dead_issues)
    for issue in dead_issues:
        if issue["severity"] == "error":
            stats["errors"] += 1
        else:
            stats["warnings"] += 1

    return all_issues, stats


def print_report(issues, stats, verbose=False):
    """打印质量报告"""
    from datetime import date
    print("=" * 60)
    print("taxue 技能体系质量门报告")
    print(f"扫描时间: {date.today().isoformat()}")
    print("=" * 60)
    print(f"\n扫描: {stats['scanned']} 个技能")
    print(f"通过: {stats['pass']} 个")
    print(f"错误: {stats['errors']} 个")
    print(f"告警: {stats['warnings']} 个")
    print()
    
    if not issues:
        print("所有检查通过！")
        return 0
    
    # 按严重程度分组
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    
    if errors:
        print("--- 错误（必须修复）---")
        for e in errors:
            print(f"  [{e['skill']}] {e['desc']}")
        print()
    
    if warnings:
        print("--- 告警（建议修复）---")
        for w in warnings:
            print(f"  [{w['skill']}] {w['desc']}")
        print()
    
    if verbose:
        print("--- 逐技能详情 ---")
        skills = scan_all_skills()
        for skill in skills:
            name = skill["name"]
            content = skill["content"]
            metadata = parse_frontmatter(content)
            version = metadata.get("version", "N/A")
            
            skill_issues = [i for i in issues if i["skill"] == name]
            has = "✓" if not skill_issues else f"✗ ({len(skill_issues)} issues)"
            
            # 检查是否有 Outcome Contract
            has_oc = "✓" if re.search(r"Outcome Contract|产出契约", content) else " "
            has_qg = "✓" if re.search(r"质量门", content) else " "
            
            print(f"  {name:25s} v{version:8s}  OC:{has_oc}  QG:{has_qg}  → {has}")
    
    if stats["errors"] > 0:
        return 2
    if stats["warnings"] > 0:
        return 1
    return 0


def main():
    verbose = "--verbose" in sys.argv
    repair = "--repair" in sys.argv
    
    issues, stats = run_quality_gate(verbose, repair)
    exit_code = print_report(issues, stats, verbose)
    
    print(f"\n总评: {'✓ 全部通过' if exit_code == 0 else '⚠ 有改进空间' if exit_code == 1 else '✗ 需修复'}")
    print(f"质量门版本: v1.0 — 政策版本: v3.5.0")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
