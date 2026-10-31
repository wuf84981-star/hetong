"""Pydantic schema 验证测试。"""
import pytest
from pydantic import ValidationError

from src.agents.structured import (
    ClauseExtractionSchema,
    ClauseSchema,
    RiskIdentificationSchema,
    RiskFindingSchema,
)


def test_clause_schema_rejects_invalid_category():
    """非法枚举值应触发 ValidationError。"""
    with pytest.raises(ValidationError) as exc:
        ClauseSchema(
            title="付款",
            content="30日内付款",
            category="payments",  # 非法: 应该是 "payment"
            section_number="1",
        )
    assert "category" in str(exc.value)


def test_clause_extraction_schema_requires_clauses():
    """clauses 字段缺失应触发 ValidationError。"""
    with pytest.raises(ValidationError) as exc:
        ClauseExtractionSchema(contract_type="买卖合同")  # 缺少 clauses
    assert "clauses" in str(exc.value)


def test_clause_extraction_schema_accepts_valid():
    """合法数据应通过。"""
    schema = ClauseExtractionSchema(
        contract_type="买卖合同",
        clauses=[ClauseSchema(title="付款", content="...", category="payment", section_number="1")],
        entities=[],
    )
    assert schema.contract_type == "买卖合同"
    assert len(schema.clauses) == 1


def test_risk_identification_schema_validates_risk_level():
    """risk_level 必须是 LOW/MEDIUM/HIGH 之一。"""
    with pytest.raises(ValidationError):
        RiskIdentificationSchema(
            risk_findings=[
                RiskFindingSchema(
                    clause_id="c1",
                    risk_level="extreme",  # 非法
                    risk_type="无限责任",
                    description="乙方承担无上限责任",
                )
            ],
            overall_risk_level="high",
            risk_summary="存在高风险",
        )


def test_validate_extraction_raises_on_invalid():
    """非法数据应抛 ValueError 触发 LLM 重试。"""
    from src.agents.clause_extraction import ClauseExtractionAgent
    invalid_data = {"contract_type": "买卖合同", "clauses": [{"category": "invalid_enum"}]}
    with pytest.raises(ValueError, match="Schema validation failed"):
        ClauseExtractionAgent._validate_extraction(invalid_data)


def test_validate_extraction_raises_on_non_dict():
    """非 dict 输入应抛 ValueError。"""
    from src.agents.clause_extraction import ClauseExtractionAgent
    with pytest.raises(ValueError, match="Expected dict"):
        ClauseExtractionAgent._validate_extraction("not a dict")


def test_validate_extraction_accepts_valid():
    """合法数据应通过校验并返回 dict。"""
    from src.agents.clause_extraction import ClauseExtractionAgent
    valid_data = {
        "contract_type": "买卖合同",
        "clauses": [
            {
                "title": "付款",
                "content": "30日内付款",
                "category": "payment",
                "section_number": "1",
            }
        ],
        "entities": [],
    }
    out = ClauseExtractionAgent._validate_extraction(valid_data)
    assert isinstance(out, dict)
    assert out["contract_type"] == "买卖合同"
    assert out["clauses"][0]["category"] == "payment"