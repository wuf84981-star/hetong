"""评测指标 — 纯函数，无外部依赖，可单独单元测试。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PRF:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int

    def as_dict(self) -> dict:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "tp": self.tp, "fp": self.fp, "fn": self.fn,
        }


def prf_from_sets(predicted: list[set], gold: list[set]) -> PRF:
    """按 (样本, 标签) 对做 micro 平均的 precision/recall/f1。

    Args:
        predicted: 每个样本预测出的标签集合列表
        gold: 每个样本的金标准标签集合列表（与 predicted 等长、对齐）
    """
    assert len(predicted) == len(gold), "predicted 与 gold 数量不一致"
    tp = fp = fn = 0
    for pred, g in zip(predicted, gold):
        tp += len(pred & g)
        fp += len(pred - g)
        fn += len(g - pred)

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return PRF(precision, recall, f1, tp, fp, fn)
