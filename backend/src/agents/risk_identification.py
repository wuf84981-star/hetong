"""
风险识别Agent — 多Agent流水线第二步。

职责：
1. 对每个条款进行风险评分（高/中/低）
2. 识别不合理条款（无限责任、单方解除权等）
3. 买卖方偏向分析
4. 综合风险评估

采用规则引擎 + 大模型双引擎架构：
- 规则引擎：处理确定性风险检查（速度快、100%确定）
- 大模型：处理需要语义理解的风险分析
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import settings, get_llm
from ..parsers.json_parser import parse_llm_json
from ..pipeline.state import (
    Clause,
    ContractReviewState,
    RagRef,
    ReviewStatus,
    RiskFinding,
    RiskLevel,
    position_directive,
)
from ..resilience import get_agent_breaker, resilient_call
from .prompt_guard import wrap_untrusted
from .rag_utils import make_rag_refs

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一名资深的法律风险评估专家。你的任务是分析合同条款中的潜在风险。

请对每个条款进行风险评估，输出严格的JSON格式（不要输出其他内容）：

{
  "findings": [
    {
      "clause_id": "条款ID",
      "risk_level": "high/medium/low/none",
      "risk_type": "风险类型",
      "description": "风险描述",
      "buyer_impact": "对买方/甲方的影响",
      "seller_impact": "对卖方/乙方的影响",
      "rationale": "判断依据"
    }
  ],
  "overall_risk_level": "high/medium/low/none",
  "risk_summary": "风险总结（50字以内）"
}

常见风险类型包括：
- unlimited_liability: 无限责任
- unilateral_termination: 单方解除权
- unfair_penalty: 不合理违约金
- vague_terms: 模糊条款
- missing_protection: 缺少保护条款
- ip_risk: 知识产权风险
- payment_risk: 付款风险
- confidentiality_risk: 保密风险
- jurisdiction_risk: 管辖权风险
- auto_renewal_risk: 自动续约风险

风险等级判断标准：
- high: 可能导致重大经济损失或法律纠纷
- medium: 存在潜在风险，建议修改
- low: 轻微风险，建议关注
- none: 无明显风险"""


# ── 规则引擎预筛（第一层：确定性检查）──────────────────────────
# 规则数据来自 src/rules/risk_rules.py（单一事实来源，eval 与 Agent 共用）。

from ..rules.risk_rules import RISK_RULE_DEFS

_LEVEL_MAP = {
    "high": RiskLevel.HIGH,
    "medium": RiskLevel.MEDIUM,
    "low": RiskLevel.LOW,
    "none": RiskLevel.NONE,
}

RISK_RULES = [
    {
        "name": r["name"],
        "keywords": r["keywords"],
        "risk_level": _LEVEL_MAP.get(r["risk_level"], RiskLevel.MEDIUM),
        "description": r["description"],
    }
    for r in RISK_RULE_DEFS
]


class RiskIdentificationAgent:
    """风险识别Agent：规则预筛 + 大模型深度分析。"""

    def __init__(self, rag_retriever=None):
        self.llm = None
        self._rag = rag_retriever
        self._breaker = get_agent_breaker("risk_identification")

    def _ensure_llm(self):
        if self.llm is None:
            self.llm = get_llm()

    async def __call__(self, state: ContractReviewState) -> dict:
        """LangGraph节点函数：执行风险识别。"""
        logger.info("风险识别Agent开始处理 review_id=%s", state.review_id)

        if not state.clauses:
            return {
                "risk_findings": [],
                "overall_risk_level": RiskLevel.NONE,
                "risk_summary": "无条款可供分析",
            }

        # P1-3: 检索相关历史经验，注入到 prompt
        tenant_id = getattr(state, "tenant_id", "") or ""
        history_context = ""
        if tenant_id:
            try:
                from ..memory_service import MemoryService
                memory = MemoryService(tenant_id=tenant_id)
                # 用 raw_text 前 500 字作为 query
                query_text = (state.raw_text or "")[:500] or "合同审查"
                past_experience = memory.search_relevant(query_text, top_k=3)
                if past_experience:
                    history_lines = []
                    for e in past_experience:
                        history_lines.append(
                            f"- [{e['decision']}] {e['comments']} (review={e['review_id']})"
                        )
                    history_context = (
                        f"\n\n## 历史审查经验（来自过去 {len(past_experience)} 次相似合同）\n"
                        f"{wrap_untrusted('memory_history', chr(10).join(history_lines))}\n"
                    )
            except Exception:
                # memory 不可用不应阻塞主流程
                pass

        try:
            rule_findings = self._rule_based_scan(state.clauses)

            self._ensure_llm()
            llm_findings = await resilient_call(
                self._llm_analysis,
                state.clauses,
                history_context,
                position_directive(state.position),
                max_retries=settings.LLM_MAX_RETRIES,
                timeout_seconds=settings.LLM_TIMEOUT,
                circuit_breaker=self._breaker,
            )

            merged, conflicts = self._merge_findings(rule_findings, llm_findings)
            overall = self._calculate_overall_risk(merged)
            summary = self._generate_summary(merged, overall)
            if conflicts:
                summary += f" 检测到 {len(conflicts)} 处规则/大模型判定分歧，已标记人工复核。"

            logger.info(
                "风险识别完成：%d个发现，整体风险=%s，分歧=%d",
                len(merged), overall.value, len(conflicts),
            )

            return {
                "risk_findings": merged,
                "overall_risk_level": overall,
                "risk_summary": summary,
                # 高风险 或 双引擎分歧 → 需要人工复核
                "needs_human_review": overall == RiskLevel.HIGH or bool(conflicts),
            }

        except Exception as e:
            logger.exception("风险识别Agent异常 review_id=%s", state.review_id)
            rule_findings = self._rule_based_scan(state.clauses)
            overall = self._calculate_overall_risk(rule_findings)
            return {
                "risk_findings": rule_findings,
                "overall_risk_level": overall,
                "risk_summary": f"大模型分析失败，仅展示规则引擎结果。错误: {str(e)}",
                "errors": state.errors + [f"风险识别LLM分析失败: {str(e)}"],
                "warnings": state.warnings + [f"风险识别异常：{type(e).__name__}: {e}"],
                "degraded_steps": state.degraded_steps | {"risk_identification"},
                "schema_failures": state.schema_failures,
            }

    def _rule_based_scan(self, clauses: list[Clause]) -> list[RiskFinding]:
        """第一层：规则引擎快速扫描（支持正则 + 否定语境过滤）。"""
        from ..rules.keyword_matcher import scan

        findings = []
        for clause in clauses:
            for rule in RISK_RULES:
                hit = scan(clause.content, rule["keywords"])
                if hit is not None:
                    findings.append(
                        RiskFinding(
                            clause_id=clause.id,
                            risk_level=rule["risk_level"],
                            risk_type=rule["name"],
                            description=f"{rule['description']}（命中：{hit.matched_text}）",
                            rationale=f"规则引擎检测：条款「{clause.title}」中匹配到「{hit.matched_text}」",
                            source="rule",
                        )
                    )
        return findings

    async def _llm_analysis(
        self, clauses: list[Clause], history_context: str = "", stance: str = ""
    ) -> list[RiskFinding]:
        """第三层：大模型深度语义分析。"""
        clauses_text = "\n\n".join(
            f"[条款ID: {c.id}] {c.title}\n{c.content}" for c in clauses
        )

        # RAG 上下文增强：逐条款检索并记账引用，"判断依据"可溯源到知识库条文
        rag_context = ""
        refs_by_clause: dict[str, list[RagRef]] = {}
        if self._rag:
            context_parts = []
            for c in clauses:
                hits = self._rag.retrieve_structured(c.content, top_k=3)
                if not hits:
                    continue
                context_parts.append(self._rag.format_context(hits))
                refs_by_clause[c.id] = make_rag_refs(hits)
            if context_parts:
                rag_context = (
                    "\n\n以下是相似条款的法律条文，供参考：\n\n"
                    + "\n\n---\n\n".join(context_parts)
                    + "\n\n"
                )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"{rag_context}"
                    f"请分析以下合同条款的风险：\n\n{wrap_untrusted('contract', clauses_text)}"
                    f"{stance}"
                    f"{history_context}"
                )
            ),
        ]
        response = await self.llm.ainvoke(messages)
        content = response.content.strip()
        result = parse_llm_json(content)
        findings = []
        for item in result.get("findings", []):
            try:
                level = RiskLevel(item.get("risk_level", "none"))
            except ValueError:
                level = RiskLevel.LOW
            findings.append(
                RiskFinding(
                    clause_id=item.get("clause_id", ""),
                    risk_level=level,
                    risk_type=item.get("risk_type", "unknown"),
                    description=item.get("description", ""),
                    buyer_impact=item.get("buyer_impact", ""),
                    seller_impact=item.get("seller_impact", ""),
                    rationale=item.get("rationale", ""),
                    source="llm",
                    rag_refs=refs_by_clause.get(item.get("clause_id", ""), []),
                )
            )
        return findings

    def _merge_findings(
        self, rule_findings: list[RiskFinding], llm_findings: list[RiskFinding]
    ) -> tuple[list[RiskFinding], list[tuple[str, str]]]:
        """合并规则引擎与大模型结果，去重取更高风险，并显式标注双引擎分歧。

        返回 (合并后的发现, 分歧键列表)。分歧包括：
        - 同一(条款,类型)两引擎风险等级不一致（取更高并标注需人工复核）；
        - 规则判定高风险但大模型未在该条款报告任何风险（可能漏报，标注复核）。
        """
        priority = {RiskLevel.HIGH: 3, RiskLevel.MEDIUM: 2, RiskLevel.LOW: 1, RiskLevel.NONE: 0}
        seen: dict[tuple[str, str], RiskFinding] = {}
        conflicts: list[tuple[str, str]] = []

        for f in rule_findings:
            seen[(f.clause_id, f.risk_type)] = f

        llm_clause_ids = {f.clause_id for f in llm_findings}

        for f in llm_findings:
            key = (f.clause_id, f.risk_type)
            existing = seen.get(key)
            if existing is None:
                seen[key] = f
                continue
            if f.risk_level != existing.risk_level:
                higher = f if priority[f.risk_level] > priority[existing.risk_level] else existing
                higher.rationale = (
                    (higher.rationale or "")
                    + f"｜双引擎分歧：规则与大模型对该条款风险等级判定不一致"
                    f"（取较高等级 {higher.risk_level.value}，建议人工复核）"
                )
                higher.source = "conflict"
                seen[key] = higher
                conflicts.append(key)
            # 等级一致：保留其一即可

        # 规则报高风险但大模型对该条款只字未提 → 可能漏报
        for f in rule_findings:
            if f.risk_level == RiskLevel.HIGH and f.clause_id not in llm_clause_ids:
                f.rationale = (
                    (f.rationale or "")
                    + "｜双引擎分歧：规则判定为高风险但大模型未在该条款报告风险，建议人工复核"
                )
                f.source = "conflict"
                conflicts.append((f.clause_id, f.risk_type))

        return list(seen.values()), conflicts

    def _calculate_overall_risk(self, findings: list[RiskFinding]) -> RiskLevel:
        if any(f.risk_level == RiskLevel.HIGH for f in findings):
            return RiskLevel.HIGH
        if any(f.risk_level == RiskLevel.MEDIUM for f in findings):
            return RiskLevel.MEDIUM
        if any(f.risk_level == RiskLevel.LOW for f in findings):
            return RiskLevel.LOW
        return RiskLevel.NONE

    def _generate_summary(self, findings: list[RiskFinding], overall: RiskLevel) -> str:
        high = sum(1 for f in findings if f.risk_level == RiskLevel.HIGH)
        medium = sum(1 for f in findings if f.risk_level == RiskLevel.MEDIUM)
        low = sum(1 for f in findings if f.risk_level == RiskLevel.LOW)
        return (
            f"整体风险等级：{overall.value}。"
            f"发现 {high} 个高风险、{medium} 个中风险、{low} 个低风险问题。"
        )
