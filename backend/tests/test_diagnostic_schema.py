from src.api.schemas.diagnostic import DiagnosticReport


def test_diagnostic_report_minimal():
    r = DiagnosticReport(review_id="r1", timestamp="t")
    assert r.review_id == "r1"
    assert r.deep_analyses == []
    assert r.recommended_actions == []


def test_diagnostic_report_with_deep_analyses():
    r = DiagnosticReport(
        review_id="r1",
        timestamp="t",
        deep_analyses=[{"similarity_score": 8, "actionable_advice": ["建议 X"]}],
    )
    assert len(r.deep_analyses) == 1