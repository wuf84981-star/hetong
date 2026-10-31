"""检测可疑的审查结果 — 反向信号源。"""
from __future__ import annotations
from dataclasses import dataclass

from ..models.bad_case import BadCaseSeverity, BadCaseSignal
from ..pipeline.state import ContractReviewState


@dataclass
class BadCaseSignal_:
    type: str
    severity: str
    detail: str


class BadCaseDetector:
    _HIGH_RISK_KEYWORDS = [
        "无上限", "一切责任", "所有损失", "全部赔偿",
        "单方解除", "自动续约", "双倍赔偿", "排他管辖",
    ]

    def check(self, state: ContractReviewState) -> list[BadCaseSignal_]:
        signals: list[BadCaseSignal_] = []

        if len(state.schema_failures) >= 2:
            signals.append(BadCaseSignal_(
                type=BadCaseSignal.SCHEMA_FAILURE.value,
                severity=BadCaseSeverity.HIGH.value,
                detail=f"schema_failures count = {len(state.schema_failures)}"
            ))

        if len(state.degraded_steps) >= 2:
            signals.append(BadCaseSignal_(
                type=BadCaseSignal.MULTIPLE_DEGRADED.value,
                severity=BadCaseSeverity.HIGH.value,
                detail=f"degraded_steps = {state.degraded_steps}"
            ))

        if self._has_high_risk_keywords_but_low_rating(state):
            signals.append(BadCaseSignal_(
                type=BadCaseSignal.HIGH_RISK_MISSED.value,
                severity=BadCaseSeverity.CRITICAL.value,
                detail="合同含高风险关键词但 LLM 没标 high"
            ))

        return signals

    def _has_high_risk_keywords_but_low_rating(self, state) -> bool:
        if state.overall_risk_level.value != "low":
            return False
        if not state.raw_text:
            return False
        if not any(f.risk_level.value == "high" for f in state.risk_findings):
            if any(kw in state.raw_text for kw in self._HIGH_RISK_KEYWORDS):
                return True
        return False