import pytest
from datetime import datetime
from src.models.bad_case import BadCase, BadCaseSeverity, BadCaseSignal


def test_bad_case_minimal_required_fields():
    bc = BadCase(
        review_id="r1",
        signal_type="low_judge_score",
        severity=BadCaseSeverity.HIGH,
    )
    assert bc.review_id == "r1"
    assert bc.signal_type == "low_judge_score"
    assert bc.severity == BadCaseSeverity.HIGH
    assert bc.case_id
    assert bc.timestamp


def test_bad_case_signal_enum():
    expected = {"low_judge_score", "human_reject", "schema_failure",
                "multiple_degraded", "high_risk_keyword_missed"}
    actual = {s.value for s in BadCaseSignal}
    assert expected.issubset(actual)


def test_bad_case_serialization_roundtrip():
    bc = BadCase(
        review_id="r2",
        signal_type="human_reject",
        severity=BadCaseSeverity.CRITICAL,
        judge_score=3.5,
        judge_rationale="漏检了无上限责任条款",
        input_summary="甲方承担...",
        predicted_output={"risk_findings": []},
    )
    data = bc.to_dict()
    bc2 = BadCase.from_dict(data)
    assert bc2.review_id == bc.review_id
    assert bc2.judge_score == 3.5