"""结构化 LLM 调用 — Schema 校验 + 失败自动「修复重试」。

背景：早期实现只做了一次 `parse_llm_json`，没有「校验不符则重试」（虽然八股/话术宣称有）。
本模块补齐该闭环：
1. 调 LLM → parse_llm_json 得到 dict；
2. 用调用方提供的 validator 校验结构（缺字段/类型不符则视为失败）；
3. 失败时，把「上次的错误 + 原始输出」作为纠正消息回传给模型，要求「只输出合法 JSON」，重试；
4. 达到 max_repair_retries 仍失败则抛出，由 Agent 走各自的规则回退方案。

与 resilience.resilient_call 的分工：
- resilient_call 处理网络层（超时/连接失败/熔断）的重试；
- 本模块处理内容层（JSON 不合法 / schema 不符）的「修复重试」。
两者叠加即：网络抖动重连 + 输出不规范自我纠正。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from ..parsers.json_parser import LLMJSONParseError, parse_llm_json
from ..pipeline.state import ClauseCategory, ComplianceStatus, RiskLevel

logger = logging.getLogger(__name__)


class StructuredOutputError(ValueError):
    """多次修复重试后仍无法得到符合 schema 的结构化输出。"""


async def structured_llm_call(
    llm,
    messages: list,
    *,
    validator: Callable[[Any], Any] | None = None,
    max_repair_retries: int = 1,
    schema: type | None = None,
) -> Any:
    """调用 LLM 并返回经校验的结构化数据（dict/list）。

    Args:
        llm: LangChain Chat 模型（需支持 ainvoke）
        messages: 初始消息列表（SystemMessage + HumanMessage）
        validator: 可选校验函数，入参为已解析 JSON，返回「清洗后的数据」或抛异常表示不合法
        max_repair_retries: 内容不合法时的最大修复重试次数
        schema: 可选 Pydantic schema 类；传入后会作为第二关键字参数传给 validator

    Returns:
        校验通过的数据

    Raises:
        StructuredOutputError: 修复重试用尽仍失败
    """
    convo = list(messages)
    last_err: Exception | None = None

    for attempt in range(max_repair_retries + 1):
        response = await llm.ainvoke(convo)
        content = (response.content or "").strip()

        try:
            data = parse_llm_json(content)
            if validator is not None:
                if schema is not None:
                    return validator(data, schema=schema)
                return validator(data)
            return data
        except (LLMJSONParseError, ValueError, KeyError, TypeError) as e:
            last_err = e
            logger.warning(
                "结构化输出校验失败 attempt=%d/%d: %s",
                attempt + 1, max_repair_retries + 1, e,
            )
            if attempt >= max_repair_retries:
                break
            # 追加纠正消息，要求模型只输出合法 JSON
            convo = convo + [
                AIMessage(content=content),
                HumanMessage(content=(
                    "你上一次的输出无法被解析为符合要求的 JSON，错误信息："
                    f"{e}。请**只输出**严格合法的 JSON（不要任何解释、不要 Markdown 代码围栏），"
                    "字段名和枚举值必须与系统提示中的约定完全一致。"
                )),
            ]

    raise StructuredOutputError(f"多次重试后仍无法得到合法结构化输出：{last_err}")


# ── Pydantic Schemas（约束编码化：枚举非法值 → ValidationError）───────
# 依据侑夕《你不知道的 Agent》：把约束编码为代码（类型/枚举/必填），
# 而不是写在 System Prompt 里让 LLM 自我约束。
# 4 个 Agent 输出 schema 统一在此，Agent 调用方可直接用作 validator 或
# parser.with_structured_output() 的 target。

class EntitySchema(BaseModel):
    """实体 schema。"""
    entity_type: str
    value: str
    location: str = ""


class ClauseSchema(BaseModel):
    """条款 schema — 强制枚举约束。"""
    title: str
    content: str
    category: ClauseCategory
    section_number: str = ""


class ClauseExtractionSchema(BaseModel):
    """条款提取 Agent 输出 schema。"""
    contract_type: str = "未识别"
    clauses: list[ClauseSchema]
    entities: list[EntitySchema] = Field(default_factory=list)


class RiskFindingSchema(BaseModel):
    """风险发现 schema。"""
    clause_id: str
    risk_level: RiskLevel
    risk_type: str
    description: str
    buyer_impact: str = ""
    seller_impact: str = ""
    rationale: str = ""


class RiskIdentificationSchema(BaseModel):
    """风险识别 Agent 输出 schema。"""
    risk_findings: list[RiskFindingSchema]
    overall_risk_level: RiskLevel = RiskLevel.NONE
    risk_summary: str = ""
    needs_human_review: bool = False


class ComplianceFindingSchema(BaseModel):
    """合规发现 schema。"""
    clause_id: str
    status: ComplianceStatus
    regulation: str
    issue: str
    recommendation: str = ""


class ComplianceCheckSchema(BaseModel):
    """合规检查 Agent 输出 schema。"""
    compliance_findings: list[ComplianceFindingSchema] = Field(default_factory=list)
    overall_compliance: ComplianceStatus = ComplianceStatus.NEEDS_REVIEW
    missing_clauses: list[str] = Field(default_factory=list)


class SuggestionSchema(BaseModel):
    """修改建议 schema。"""
    clause_id: str
    original_text: str
    suggested_text: str
    reason: str
    priority: RiskLevel = RiskLevel.MEDIUM


class SuggestionOutputSchema(BaseModel):
    """建议生成 Agent 输出 schema。"""
    suggestions: list[SuggestionSchema] = Field(default_factory=list)


__all__ = [
    "StructuredOutputError",
    "structured_llm_call",
    "EntitySchema",
    "ClauseSchema",
    "ClauseExtractionSchema",
    "RiskFindingSchema",
    "RiskIdentificationSchema",
    "ComplianceFindingSchema",
    "ComplianceCheckSchema",
    "SuggestionSchema",
    "SuggestionOutputSchema",
]
