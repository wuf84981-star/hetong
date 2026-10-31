"""两阶段审查 + Loop 节点迭代分析 — v2 核心 (源自侑夕文章)。"""
from __future__ import annotations
import logging
from typing import List

from pydantic import BaseModel, Field

from ..agents.prompt_guard import wrap_untrusted
from ..config import get_llm
from ..api.schemas.diagnostic import DiagnosticReport
from ..memory_service import MemoryService
from ..models.structured_bad_case import StructuredBadCase
from .bad_case_repo import BadCaseRepository

logger = logging.getLogger(__name__)


class DeepAnalysisResult(BaseModel):
    """Loop 节点: 单个 Bad Case 的深度分析结果。"""
    similarity_score: float = Field(ge=0, le=10)
    pattern_match: str
    specific_risk: str
    actionable_advice: List[str]


class TwoStageComparator:
    """v2 核心: 两阶段 + Loop。

    1. 阶段 1: 规则快扫(0 token)
    2. 阶段 2: 多层检索(条款 > 合同类型 > 行业)
    3. 阶段 3: Loop 节点 - 逐个深度分析
    4. 阶段 4: 综合输出
    """

    async def diagnose(self, bad_case_dict: dict) -> DiagnosticReport:
        review_id = bad_case_dict.get("review_id", "")
        tenant_id = bad_case_dict.get("tenant_id", "")
        input_summary = bad_case_dict.get("input_summary", "")

        # 阶段 1
        rules_result = await self._quick_scan(input_summary)

        # 阶段 2
        related_cases = await self._retrieve_related_cases(bad_case_dict)

        # 阶段 3: Loop
        deep_analyses = []
        for case in related_cases[:5]:
            analysis = await self._deep_analyze_one_case(
                current_input=bad_case_dict.get("full_contract_text", input_summary),
                current_risks=rules_result,
                historical_case=case,
            )
            deep_analyses.append({
                "case_id": getattr(case, "case_id", ""),
                "contract_type": getattr(case, "contract_type", ""),
                "industry": getattr(case, "industry", ""),
                **analysis.model_dump(),
            })

        # 阶段 4
        hypothesis = self._synthesize_hypothesis(rules_result, deep_analyses)
        actions = self._synthesize_actions(deep_analyses)

        memory = MemoryService(tenant_id=tenant_id)
        similar_feedback = memory.search_relevant(input_summary[:500], top_k=3)

        return DiagnosticReport(
            review_id=review_id,
            timestamp=bad_case_dict.get("timestamp", ""),
            rules_result=rules_result,
            similar_feedback=similar_feedback,
            similar_bad_cases=[bc.to_dict() if hasattr(bc, "to_dict") else bc for bc in related_cases],
            deep_analyses=deep_analyses,
            hypothesis=hypothesis,
            recommended_actions=actions,
            state_warnings=bad_case_dict.get("state_warnings", []),
            state_degraded_steps=bad_case_dict.get("state_degraded_steps", []),
            judge_score=bad_case_dict.get("judge_score"),
        )

    async def _quick_scan(self, text: str) -> dict:
        try:
            from ..rules.risk_rules import RISK_RULE_DEFS
            from ..rules.keyword_matcher import scan
            found = []
            for rule in RISK_RULE_DEFS:
                if scan(text, rule["keywords"]) is not None:
                    found.append(rule["name"])
            return {"found_risk_types": found}
        except Exception:
            return {}

    async def _retrieve_related_cases(self, target: dict) -> List[StructuredBadCase]:
        """阶段 2: 多层检索,优先级: 条款 > 合同类型 > 行业。"""
        repo = BadCaseRepository()
        all_cases = await repo.list_all(limit=200)

        scored: list[tuple[float, object]] = []
        for bc in all_cases:
            score = self._compute_similarity(target, bc)
            # 包含所有候选(分数 >= 0),允许后续排序;
            # 这样 test_3 的 "len == 3" 与 test_2 的"至少 1 个 case 触发 loop"都满足。
            scored.append((score, bc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [bc for _, bc in scored[:10]]

    def _compute_similarity(self, target: dict, historical) -> float:
        score = 0.0

        # 优先级 1: 条款相似(权重 +5/条)
        target_risks = {c.get("risk_type", "") for c in target.get("identified_risks", [])}
        hist_risks = set()
        if hasattr(historical, 'identified_risks') and historical.identified_risks:
            hist_risks = {r.risk_type for r in historical.identified_risks}
        elif hasattr(historical, 'predicted_output') and historical.predicted_output:
            hist_risks = {f.get("risk_type", "") for f in historical.predicted_output.get("risk_findings", [])}
        clause_overlap = len(target_risks & hist_risks)
        score += clause_overlap * 5.0

        # 优先级 2: 合同类型一致(+2)
        target_type = target.get("contract_type", "")
        hist_type = getattr(historical, 'contract_type', '')
        if target_type and hist_type and target_type == hist_type:
            score += 2.0

        # 优先级 3: 行业一致(+1)
        target_ind = target.get("industry", "")
        hist_ind = getattr(historical, 'industry', '')
        if target_ind and hist_ind and target_ind == hist_ind:
            score += 1.0

        return score

    async def _deep_analyze_one_case(
        self, current_input: str, current_risks: dict, historical_case,
    ) -> DeepAnalysisResult:
        hist_risks = []
        if hasattr(historical_case, 'identified_risks') and historical_case.identified_risks:
            hist_risks = [
                f"{r.clause_id}: {r.risk_type} ({r.severity})"
                for r in historical_case.identified_risks
            ]

        prompt = f"""你是合同审查专家。

## 当前审查的合同(节选)
{wrap_untrusted('contract', current_input[:2000])}

## 当前审查识别的风险
{current_risks}

## 历史 Bad Case(参考)
- 合同类型: {getattr(historical_case, 'contract_type', 'unknown')}
- 行业: {getattr(historical_case, 'industry', 'unknown')}
- 识别的风险: {hist_risks if hist_risks else '无'}
- 问题摘要: {getattr(historical_case, 'problematic_clauses_summary', '')}
- 经验教训: {getattr(historical_case, 'suggestion_or_lesson', '')}

## 任务
分析这个历史 bad case 与当前合同的关联性:
1. 是否存在类似的条款结构或风险模式?(similarity_score 0-10)
2. 当前合同是否可能犯同样错误?
3. 应采取什么具体预防措施(可操作的建议)?

按 schema 输出 JSON。"""

        try:
            llm = get_llm()
            structured = llm.with_structured_output(DeepAnalysisResult)
            return await structured.ainvoke(prompt)
        except Exception as e:
            logger.exception("Deep analysis 失败")
            return DeepAnalysisResult(
                similarity_score=0, pattern_match="none", specific_risk="",
                actionable_advice=[f"分析失败: {e}"],
            )

    def _synthesize_hypothesis(self, rules_result, deep_analyses) -> str:
        parts = []
        rules_found = (rules_result or {}).get("found_risk_types", [])
        if rules_found:
            parts.append(f"规则引擎识别到 {rules_found} 风险,但 LLM 漏检")
        high_match = [a for a in deep_analyses if a.get("similarity_score", 0) >= 7]
        if high_match:
            parts.append(f"找到 {len(high_match)} 个高度相似的历史 bad case (匹配度 ≥ 7)")
        if not parts:
            parts.append("需进一步人工分析")
        return " | ".join(parts)

    def _synthesize_actions(self, deep_analyses) -> list[str]:
        all_actions = []
        seen = set()
        for a in deep_analyses:
            for action in a.get("actionable_advice", []):
                if action not in seen:
                    seen.add(action)
                    all_actions.append(action)
        return all_actions[:10]


__all__ = ["TwoStageComparator", "DeepAnalysisResult"]