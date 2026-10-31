"""state.warnings / state.degraded 字段测试。"""
from src.pipeline.state import ContractReviewState, ReviewStatus


def test_state_default_warnings_empty():
    state = ContractReviewState(review_id="x")
    assert state.warnings == []
    assert state.degraded_steps == set()


def test_state_warnings_append():
    state = ContractReviewState(review_id="x")
    state.warnings.append("LLM 超时")
    state.degraded_steps.add("clause_extraction")
    assert "LLM 超时" in state.warnings
    assert "clause_extraction" in state.degraded_steps


def test_state_schema_failures():
    state = ContractReviewState(review_id="x")
    state.schema_failures.append({
        "step": "clause_extraction",
        "error": "ValidationError: ...",
    })
    assert len(state.schema_failures) == 1


def test_state_serialization_roundtrip():
    state = ContractReviewState(review_id="x")
    state.warnings.append("test warning")
    state.degraded_steps.add("clause_extraction")
    data = state.model_dump(mode="json")
    assert data["warnings"] == ["test warning"]
    assert "clause_extraction" in data["degraded_steps"]
    state2 = ContractReviewState(**data)
    assert state2.warnings == state.warnings


def test_review_detail_response_includes_warnings():
    """响应 schema 应包含 warnings / degraded_steps / has_quality_issues。"""
    from src.api.schemas.review import DetailedReviewResponse
    resp = DetailedReviewResponse(
        review_id="x",
        status="completed",
        contract_type="",
        clauses=[],
        risk_findings=[],
        risk_summary="",
        overall_risk_level="none",
        compliance_findings=[],
        missing_clauses=[],
        overall_compliance="needs_review",
        suggestions=[],
        version_diff="",
        needs_human_review=False,
        errors=[],
        warnings=["LLM 超时"],
        degraded_steps=["clause_extraction"],
        has_quality_issues=True,
    )
    assert resp.warnings == ["LLM 超时"]
    assert resp.degraded_steps == ["clause_extraction"]
    assert resp.has_quality_issues is True