import pytest
from src.models.structured_bad_case import (
    StructuredBadCase,
    IdentifiedRisk,
    RISK_CATEGORIES,
)


def test_identified_risk_has_clause_location():
    risk = IdentifiedRisk(
        clause_id="c1",
        clause_text_snippet="甲方承担无上限的所有损失",
        risk_type="unlimited_liability",
        risk_category="责任范围",
        severity="critical",
        description="无上限责任",
    )
    assert risk.clause_id == "c1"
    assert "无上限" in risk.clause_text_snippet
    assert risk.risk_type == "unlimited_liability"


def test_structured_bad_case_required_fields():
    bc = StructuredBadCase(
        review_id="r1",
        contract_type="服务合同",
        industry="互联网",
        identified_risks=[
            IdentifiedRisk(
                clause_id="c3", risk_type="unlimited_liability",
                severity="high", description="无上限责任",
            )
        ],
        problematic_clauses_summary="服务条款中的责任限制条款过于宽松",
        suggestion_or_lesson="下次审查时重点关注责任上限百分比",
        keywords_for_retrieval=["无上限", "责任", "服务合同", "互联网"],
    )
    assert bc.industry == "互联网"
    assert len(bc.identified_risks) == 1
    assert bc.suggestion_or_lesson


def test_structured_bad_case_preserves_full_text():
    bc = StructuredBadCase(
        review_id="r1",
        full_contract_text="x" * 50000,
        input_summary="短摘要",
    )
    assert len(bc.full_contract_text) == 50000
    assert len(bc.input_summary) < 1000


def test_keywords_for_retrieval_automatic_extraction():
    from src.models.structured_bad_case import auto_extract_keywords
    keywords = auto_extract_keywords("甲方承担无上限责任,且自动续约一年。")
    assert "无上限" in keywords or "责任" in keywords
    assert "自动续约" in keywords


def test_to_dict_includes_all_structured_fields():
    bc = StructuredBadCase(
        review_id="r1",
        identified_risks=[
            IdentifiedRisk(clause_id="c1", risk_type="x", severity="low", description="y")
        ],
    )
    data = bc.to_dict()
    assert len(data["identified_risks"]) == 1
    assert data["identified_risks"][0]["clause_id"] == "c1"
