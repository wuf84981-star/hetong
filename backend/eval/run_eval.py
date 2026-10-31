#!/usr/bin/env python3
"""合同风险识别评测器 — 让对外指标可复现。

两种模式：
  rules : 仅用规则引擎（确定性、无需 LLM Key、无需重依赖）。适合 CI 回归与快速验证。
  full  : 跑完整四 Agent 流水线（需配置 LLM Key 与依赖）。度量规则+大模型合并后的效果。

用法：
  python eval/run_eval.py --mode rules
  python eval/run_eval.py --mode full        # 需要 .env 里的 LLM Key
  python eval/run_eval.py --mode rules --consistency 3   # 跑 3 次校验确定性

指标：基于 (样本, risk_type) 对的 micro precision / recall / F1。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.metrics import prf_from_sets  # noqa: E402


def _split_clauses(text: str) -> list[str]:
    """轻量条款切分（无需重依赖）：按「第X条」或换行切分。"""
    parts = re.split(r"(?=第[一二三四五六七八九十百零\d]+条)", text)
    parts = [p.strip() for p in parts if p.strip()]
    return parts or [text]


def detect_rules(text: str) -> set[str]:
    """规则模式：用共享规则数据 + 关键词匹配器（含否定/正则）识别 risk_type。"""
    from src.rules.keyword_matcher import scan
    from src.rules.risk_rules import RISK_RULE_DEFS

    found: set[str] = set()
    for clause in _split_clauses(text):
        for rule in RISK_RULE_DEFS:
            if scan(clause, rule["keywords"]) is not None:
                found.add(rule["name"])
    return found


async def detect_full(text: str) -> set[str]:
    """全流水线模式：跑真实流水线，收集 risk_findings 的 risk_type。"""
    from src.pipeline.graph import run_review

    state = await run_review(raw_text=text, with_human_review=False)
    return {f.risk_type for f in state.risk_findings}


def load_dataset() -> dict:
    with open(Path(__file__).parent / "dataset.json", encoding="utf-8") as f:
        return json.load(f)


def run(mode: str, consistency: int) -> int:
    data = load_dataset()
    cases = data["cases"]
    gold = [set(c["gold_risk_types"]) for c in cases]

    runs: list[list[set]] = []
    for _ in range(max(1, consistency)):
        if mode == "rules":
            preds = [detect_rules(c["text"]) for c in cases]
        else:
            preds = [asyncio.run(detect_full(c["text"])) for c in cases]
        runs.append(preds)

    prf = prf_from_sets(runs[0], gold)

    # 一致性：多次运行结果是否完全一致
    consistent = all(runs[i] == runs[0] for i in range(len(runs)))

    print(f"=== 评测模式: {mode} | 样本数: {len(cases)} | 重复: {len(runs)} 次 ===")
    for c, pred in zip(cases, runs[0]):
        g = set(c["gold_risk_types"])
        print(f"  [{c['id']}] 预测={sorted(pred)} 金标={sorted(g)} "
              f"{'✔' if pred == g else '�“漏/误”'}")
    m = prf.as_dict()
    print(f"\nPrecision={m['precision']} Recall={m['recall']} F1={m['f1']} "
          f"(TP={m['tp']} FP={m['fp']} FN={m['fn']})")
    print(f"一致性({len(runs)}次): {'100% 完全一致' if consistent else '不一致（存在随机性）'}")

    # 规则模式应完全确定；作为回归门槛
    if mode == "rules" and not consistent:
        print("错误：规则模式应当确定性一致但出现分歧", file=sys.stderr)
        return 2
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["rules", "full"], default="rules")
    ap.add_argument("--consistency", type=int, default=1, help="重复运行次数以校验一致性")
    args = ap.parse_args()
    sys.exit(run(args.mode, args.consistency))


if __name__ == "__main__":
    main()
