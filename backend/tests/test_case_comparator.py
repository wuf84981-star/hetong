"""TwoStageComparator — v2 核心 (两阶段 + Loop 节点)。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.structured_bad_case import IdentifiedRisk, StructuredBadCase
from src.services.case_comparator import DeepAnalysisResult, TwoStageComparator


@pytest.mark.asyncio
async def test_stage1_quick_scan_runs_first():
    """阶段 1: 通用规则先扫一遍(0 token LLM)。"""
    comparator = TwoStageComparator()
    bc_dict = {
        "review_id": "r1",
        "input_summary": "甲方承担无上限责任",
        "full_contract_text": "甲方承担无上限责任...",
        "contract_type": "服务合同",
        "industry": "互联网",
    }
    report = await comparator.diagnose(bc_dict)
    assert report.rules_result is not None
    assert "found_risk_types" in report.rules_result


@pytest.mark.asyncio
async def test_stage3_loop_calls_llm_per_case():
    """阶段 3: 每个 Bad Case 单独 LLM 调用。"""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=DeepAnalysisResult(
        similarity_score=8.0, pattern_match="high",
        specific_risk="unlimited_liability",
        actionable_advice=["建议 1", "建议 2"],
    ))
    mock_llm.with_structured_output = MagicMock(return_value=mock_structured)

    # 阶段 2 检索必须有候选，循环才会逐个调 LLM——显式 mock repo，
    # 不再隐式依赖本机 data 目录里的存量 bad case
    mock_repo = MagicMock()
    mock_repo.list_all = AsyncMock(return_value=[StructuredBadCase(review_id="hist", contract_type="服务合同")])

    with patch("src.services.case_comparator.get_llm", return_value=mock_llm), \
         patch("src.services.case_comparator.BadCaseRepository", return_value=mock_repo):
        comparator = TwoStageComparator()
        bc_dict = {
            "review_id": "r1",
            "input_summary": "服务合同测试",
            "full_contract_text": "...",
        }
        await comparator.diagnose(bc_dict)
        assert mock_llm.with_structured_output.called


@pytest.mark.asyncio
async def test_retrieval_priority_clause_over_type_over_industry():
    """检索优先级: 条款相似 > 合同类型 > 行业。"""
    bc_clause = StructuredBadCase(
        review_id="r-clause", contract_type="买卖合同",
        identified_risks=[IdentifiedRisk(clause_id="c1", risk_type="vague_terms",
                                        severity="high", description="x")],
    )
    bc_type = StructuredBadCase(review_id="r-type", contract_type="服务合同")
    bc_industry = StructuredBadCase(review_id="r-industry", industry="金融")

    mock_repo = MagicMock()
    mock_repo.list_all = AsyncMock(return_value=[bc_clause, bc_type, bc_industry])

    with patch("src.services.case_comparator.BadCaseRepository", return_value=mock_repo):
        comparator = TwoStageComparator()
        bc_dict = {
            "review_id": "r1",
            "input_summary": "无上限",
            "contract_type": "服务合同",
            "industry": "金融",
            "identified_risks": [{"clause_id": "c1", "risk_type": "vague_terms",
                                  "clause_text_snippet": "无上限"}],
        }
        related = await comparator._retrieve_related_cases(bc_dict)
        assert len(related) == 3
        # clause-match 排第一
        assert related[0].review_id == "r-clause"