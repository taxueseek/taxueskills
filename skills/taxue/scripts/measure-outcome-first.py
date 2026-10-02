#!/usr/bin/env python3
"""
taxue 结果优先（outcome-first）结构度量。

对比 baseline（git tag / 路径）与当前文件，量化：
  - 强制步骤剧本密度（process script density）
  - 结果优先信号密度（outcome-first signals）
  - 用户可见问卷强迫（forced dialogue）
  - 预计 token（chars/4）

用法:
  python3 measure-outcome-first.py
  python3 measure-outcome-first.py --baseline /path/to/dir
  python3 measure-outcome-first.py --git-tag taxue-pre-outcome-first-20260715
"""

from __future__ import annotations

from _common import read_json, read_text, json_out

import argparse
import re
import subprocess
import sys
from pathlib import Path

SKILLS_DIR = Path.home() / ".agents" / "skills"

# 决策核心文件（本实验改动面）
TARGETS = [
    "taxue/SKILL.md",
    "taxue-solve/SKILL.md",
    "taxue-diagnosis/SKILL.md",
    "taxue/references/shared-rules.md",
]

# 步骤剧本：强制顺序、编号流程、流水线语言
PROCESS_SCRIPT = [
    r"按顺序过",
    r"任何一步",
    r"不往下走",
    r"第一步[：:]",
    r"第二步[：:]",
    r"第三步[：:]",
    r"###\s*1\.\d",
    r"逐项检验",
    r"等回应后再进入",
    r"不要一次性跑完",
    r"以下六步",
    r"六步清洗",
]

# 结果优先：交付物、边界、内部检查、首轮交付
OUTCOME_FIRST = [
    r"结果优先",
    r"先写结果",
    r"先交付",
    r"这轮要交付",
    r"硬边界",
    r"内部检查表",
    r"不外露",
    r"最多问 1 个",
    r"标假设",
    r"可验证动作",
    r"Outcome Contract",
    r"产出契约",
    r"跟进 refinement",
    r"过程本身",
]

# 强迫用户走问卷/流水线
FORCED_DIALOGUE = [
    r"停下来跟用户对话",
    r"任何一问不通过",
    r"继续追问",
    r"等回应后再",
    r"必须都过",
]


def count_patterns(text: str, patterns: list[str]) -> int:
    n = 0
    for p in patterns:
        n += len(re.findall(p, text))
    return n


def score_text(text: str) -> dict:
    proc = count_patterns(text, PROCESS_SCRIPT)
    outc = count_patterns(text, OUTCOME_FIRST)
    forced = count_patterns(text, FORCED_DIALOGUE)
    chars = len(text)
    tokens_est = chars / 4.0
    # composite: higher better for outcome-first skill design
    # reward outcome signals, penalize process scripts & forced dialogue
    composite = outc * 2 - proc * 3 - forced * 2
    return {
        "chars": chars,
        "tokens_est": round(tokens_est, 1),
        "process_script": proc,
        "outcome_first": outc,
        "forced_dialogue": forced,
        "composite": composite,
    }


def read_current(rel: str) -> str:
    path = SKILLS_DIR / rel
    return read_text(path) if path.exists() else ""


def read_git_tag(tag: str, rel: str) -> str:
    # path inside repo: skills/<rel>
    repo = Path.home() / ".agents"
    blob = f"{tag}:skills/{rel}"
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "show", blob],
            stderr=subprocess.DEVNULL,
        )
        return out.decode("utf-8")
    except subprocess.CalledProcessError:
        return ""


def read_baseline_dir(base: Path, rel: str) -> str:
    p = base / rel
    return read_text(p) if p.exists() else ""


def fmt_row(name: str, b: dict, c: dict) -> str:
    def d(key):
        bv, cv = b[key], c[key]
        delta = cv - bv
        sign = "+" if delta > 0 else ""
        return f"{bv} → {cv} ({sign}{delta})"

    return (
        f"  {name}\n"
        f"    process_script : {d('process_script')}\n"
        f"    outcome_first  : {d('outcome_first')}\n"
        f"    forced_dialogue: {d('forced_dialogue')}\n"
        f"    tokens_est     : {d('tokens_est')}\n"
        f"    composite      : {d('composite')}\n"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--git-tag", default="taxue-pre-outcome-first-20260715")
    ap.add_argument("--baseline", default=None, help="baseline root dir containing taxue/...")
    args = ap.parse_args()

    totals_b = {
        "process_script": 0,
        "outcome_first": 0,
        "forced_dialogue": 0,
        "tokens_est": 0.0,
        "composite": 0,
        "chars": 0,
    }
    totals_c = {k: 0 if k != "tokens_est" else 0.0 for k in totals_b}

    print("=== taxue outcome-first measurement ===")
    print(f"baseline: git tag {args.git_tag}" if not args.baseline else f"baseline: {args.baseline}")
    print(f"current : {SKILLS_DIR}")
    print()

    missing_baseline = []
    for rel in TARGETS:
        if args.baseline:
            bt = read_baseline_dir(Path(args.baseline), rel)
        else:
            bt = read_git_tag(args.git_tag, rel)
        ct = read_current(rel)
        if not bt:
            missing_baseline.append(rel)
            bt = ct  # fall back: no delta
        bs, cs = score_text(bt), score_text(ct)
        print(fmt_row(rel, bs, cs))
        for k in totals_b:
            totals_b[k] += bs[k]
            totals_c[k] += cs[k]

    print("--- TOTALS ---")
    print(fmt_row("ALL targets", totals_b, totals_c))

    # Pass criteria for experiment
    ok_process = totals_c["process_script"] < totals_b["process_script"]
    ok_outcome = totals_c["outcome_first"] > totals_b["outcome_first"]
    ok_forced = totals_c["forced_dialogue"] <= totals_b["forced_dialogue"]
    ok_composite = totals_c["composite"] > totals_b["composite"]

    print("--- PASS/FAIL (structure gates) ---")
    gates = [
        ("process_script ↓", ok_process),
        ("outcome_first ↑", ok_outcome),
        ("forced_dialogue ≤", ok_forced),
        ("composite ↑", ok_composite),
    ]
    for name, ok in gates:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    if missing_baseline:
        print("\nWARN: missing baseline for:", ", ".join(missing_baseline))

    all_pass = all(ok for _, ok in gates)
    print("\nRESULT:", "STRUCTURE PASS" if all_pass else "STRUCTURE FAIL")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
