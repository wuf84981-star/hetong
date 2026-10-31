"""可复现评测集与纯指标函数测试。"""

from __future__ import annotations

from eval.metrics import prf_from_sets
from eval.run_eval import detect_rules, load_dataset, run


def test_prf_from_sets_uses_micro_average():
    result = prf_from_sets(
        [{"a", "b"}, {"c"}],
        [{"a"}, {"c", "d"}],
    )

    assert result.tp == 2
    assert result.fp == 1
    assert result.fn == 1
    assert result.precision == 2 / 3
    assert result.recall == 2 / 3
    assert result.f1 == 2 / 3


def test_empty_prediction_and_gold_is_perfect():
    result = prf_from_sets([set()], [set()])

    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0


def test_dataset_has_positive_negative_and_negation_cases():
    cases = load_dataset()["cases"]

    assert len(cases) >= 6
    assert any(case["gold_risk_types"] for case in cases)
    assert any(not case["gold_risk_types"] for case in cases)
    assert any("不构成" in case["text"] for case in cases)


def test_rule_predictions_match_gold_dataset():
    for case in load_dataset()["cases"]:
        assert detect_rules(case["text"]) == set(case["gold_risk_types"]), case["id"]


def test_rule_eval_is_deterministic_across_repeats():
    assert run("rules", consistency=3) == 0
