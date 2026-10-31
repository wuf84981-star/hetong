"""LLM-as-judge: 第二层自动评估。

侑夕《你不知道的 Agent》: "两层可观测性 — 人工抽样标注 + LLM 自动评估。"
"""
from __future__ import annotations
import json

from pydantic import BaseModel, Field

from src.config import get_llm
from src.agents.prompt_guard import wrap_untrusted


class JudgeResult(BaseModel):
    """Judge 输出 schema。"""
    completeness: int = Field(ge=0, le=10, description="完整性(0-10)")
    accuracy: int = Field(ge=0, le=10, description="准确性(0-10)")
    critical_info_preserved: int = Field(ge=0, le=10, description="关键信息保留度(0-10)")
    overall: int = Field(ge=0, le=10, description="综合评分(0-10)")
    rationale: str = Field(max_length=500, description="评估理由(≤500字)")


class LLMJudge:
    """LLM-as-judge 评估器(默认与生产不同的模型)。"""

    def __init__(self, model_name: str | None = None):
        from src.config import settings
        self.model_name = model_name or getattr(settings, "LLM_JUDGE_MODEL", "gpt-4o-mini")

    async def judge_clause_extraction(
        self,
        contract_text: str,
        gold_clauses: list[dict],
        predicted_clauses: list[dict],
    ) -> JudgeResult:
        prompt = f"""你是合同审查评测专家。

## 合同原文
{wrap_untrusted("contract", contract_text)}

## 金标准条款
{json.dumps(gold_clauses, ensure_ascii=False, indent=2)}

## 预测条款
{json.dumps(predicted_clauses, ensure_ascii=False, indent=2)}

评估预测相对金标准的质量(0-10):
- completeness: 0-10(是否漏掉条款)
- accuracy: 0-10(分类是否正确)
- critical_info_preserved: 0-10(金额/期限/责任主体保留度)
- overall: 0-10(综合)
- rationale: ≤500 字说明

按 schema 输出 JSON。"""
        llm = get_llm()
        structured = llm.with_structured_output(JudgeResult)
        return await structured.ainvoke(prompt)