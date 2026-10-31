"""BadCaseDetector 信号检测测试。"""
import pytest
from src.pipeline.state import ContractReviewState, ReviewStatus, RiskLevel, RiskFinding
from src.services.bad_case_detector import BadCaseDetector


def _state(**kw):
    defaults = {
        "review_id": "r1",
        "status": ReviewStatus.COMPLETED,
        "risk_findings": [],
        "schema_failures": [],
        "warnings": [],
        "degraded_steps": set(),
        "raw_text": "普通合同",
        "overall_risk_level": RiskLevel.NONE,
    }
    defaults.update(kw)
    return ContractReviewState(**defaults)


def test_no_signals_on_clean_state():
    detector = BadCaseDetector()
    s = _state()
    assert detector.check(s) == []


def test_multiple_schema_failures_is_signal():
    detector = BadCaseDetector()
    s = _state(schema_failures=[{"step": "x", "error": "e"}] * 2)
    assert any(sig.type == "schema_failure" for sig in detector.check(s))


def test_multiple_degraded_steps_is_signal():
    detector = BadCaseDetector()
    s = _state(degraded_steps={"a", "b"})
    assert any(sig.type == "multiple_degraded" for sig in detector.check(s))


def test_high_risk_keyword_missed_critical_signal():
    detector = BadCaseDetector()
    s = _state(
        raw_text="甲方承担无上限责任,乙方须双倍赔偿",
        overall_risk_level=RiskLevel.LOW,
        risk_findings=[
            RiskFinding(
                clause_id="c1",
                risk_level=RiskLevel.LOW,
                risk_type="其他",
                description="...",
            )
        ],
    )
    signals = detector.check(s)
    assert any(sig.severity == "critical" for sig in signals)
    assert any(sig.type == "high_risk_keyword_missed" for sig in signals)