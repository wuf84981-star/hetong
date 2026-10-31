"""
条款提取Agent — 多Agent流水线第一步。

职责：
1. 解析合同文档 (PDF/DOCX → 纯文本)
2. 按条款切分文本
3. 识别条款类别 (付款、违约、保密等)
4. 提取关键实体 (甲乙方、金额、日期、标的物)
5. 输出结构化条款数据

弹性机制：
- LLM 调用超时 60 秒
- 失败自动重试 2 次（指数退避）
- 连续失败 3 次后熔断，直接走回退方案
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import settings, get_llm
from ..parsers.chunking import chunk_sections
from ..parsers.document_parser import DocumentParser, parse_raw_text_to_sections
from ..parsers.json_parser import parse_llm_json
from ..resilience import CircuitBreaker, get_agent_breaker, resilient_call
from .prompt_guard import wrap_untrusted
from .structured import (
    ClauseExtractionSchema,
    ClauseSchema,
    EntitySchema,
    structured_llm_call,
)
from ..pipeline.state import (
    Clause,
    ClauseCategory,
    ContractEntity,
    ContractReviewState,
    ReviewStatus,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个专业的法律合同条款提取专家。你的任务是从合同文本中提取结构化条款信息。

请严格按照以下JSON格式输出（不要输出其他内容）：

{
  "contract_type": "合同类型（如：买卖合同、劳动合同、租赁合同等）",
  "clauses": [
    {
      "title": "条款标题",
      "content": "条款完整内容",
      "category": "条款类别",
      "section_number": "章节编号"
    }
  ],
  "entities": [
    {
      "entity_type": "实体类型",
      "value": "实体值",
      "location": "出现位置"
    }
  ]
}

条款类别(category)只能是以下之一：
- payment: 付款条款
- liability: 责任条款
- confidentiality: 保密条款
- termination: 终止/解除条款
- intellectual_property: 知识产权条款
- dispute_resolution: 争议解决条款
- force_majeure: 不可抗力条款
- warranty: 保证/担保条款
- indemnification: 赔偿条款
- governing_law: 适用法律条款
- other: 其他条款

实体类型(entity_type)包括：
- party_a: 甲方
- party_b: 乙方
- amount: 金额
- date: 日期
- subject: 标的物/服务内容
- duration: 期限
- address: 地址"""


class ClauseExtractionAgent:
    """条款提取Agent：合同文档解析 + 条款分割 + 实体识别 + 条款分类。"""

    def __init__(self):
        self.parser = DocumentParser()
        self.llm = None
        self._breaker = get_agent_breaker("clause_extraction")

    def _ensure_llm(self):
        if self.llm is None:
            self.llm = get_llm()

    async def __call__(self, state: ContractReviewState) -> dict:
        """LangGraph节点函数：执行条款提取。"""
        logger.info("条款提取Agent开始处理 review_id=%s", state.review_id)

        raw_text = ""  # 解析出的正文需在 except 分支可见（文件模式下 state.raw_text 为空，正文只在本地）
        try:
            # P0-4: 优先 raw_text，其次 document_path，再次 raw_text_path
            raw_text = state.raw_text
            if not raw_text and state.document_path:
                raw_text = self.parser.parse(state.document_path)
            if not raw_text and getattr(state, "raw_text_path", ""):
                # 用 file_tools 读取（避免把整个文本塞 state）
                from .file_tools import ReadContractTextTool
                tool = ReadContractTextTool(path=state.raw_text_path)
                raw_text = tool.read_full()

            if not raw_text:
                return {
                    "errors": state.errors + ["合同文本为空，无法进行条款提取"],
                    "status": ReviewStatus.COMPLETED,
                }

            sections = parse_raw_text_to_sections(raw_text)

            # P0-4: 把 sections 写入 sidecar，供下游 Agent 用 read_section
            if getattr(state, "raw_text_path", ""):
                from pathlib import Path
                import json
                sidecar = Path(state.raw_text_path).with_suffix(".sections.json")
                # 为每个 section 添加 id 字段，供 ReadContractTextTool.read_section 使用
                sections_with_id = [
                    {"id": f"s{i+1}", **s} for i, s in enumerate(sections)
                ]
                sidecar.write_text(
                    json.dumps(sections_with_id, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            self._ensure_llm()

            # 分块提取（超长合同按章节分块，逐块提取后合并，避免截断丢条款）
            clauses, entities, contract_type = await self._extract_all(raw_text, sections)

            logger.info(
                "条款提取完成：%d个条款，%d个实体，合同类型=%s",
                len(clauses), len(entities), contract_type,
            )

            return {
                "raw_text": raw_text,
                "clauses": clauses,
                "entities": entities,
                "contract_type": contract_type,
                "status": ReviewStatus.IN_PROGRESS,
            }

        except Exception as e:
            logger.exception("条款提取Agent异常 review_id=%s", state.review_id)
            return {
                "errors": state.errors + [f"条款提取失败: {str(e)}"],
                "warnings": state.warnings + [f"条款提取异常：{type(e).__name__}: {e}"],
                "degraded_steps": state.degraded_steps | {"clause_extraction"},
                "schema_failures": state.schema_failures,
                "status": ReviewStatus.IN_PROGRESS,
                "raw_text": raw_text,
                "clauses": self._fallback_extraction(raw_text),
                "entities": [],
                "contract_type": "未识别",
            }

    async def _extract_all(
        self, raw_text: str, sections: list[dict]
    ) -> tuple[list[Clause], list[ContractEntity], str]:
        """按章节分块提取并合并结果，覆盖完整合同（不再截断）。"""
        chunks = chunk_sections(raw_text, sections, max_chars=settings.LLM_CHUNK_CHARS)
        if not chunks:
            return [], [], "未识别"

        all_clauses: list[Clause] = []
        all_entities: list[ContractEntity] = []
        contract_type = ""

        for idx, chunk in enumerate(chunks):
            result = await resilient_call(
                self._extract_with_llm,
                chunk,
                max_retries=settings.LLM_MAX_RETRIES,
                timeout_seconds=settings.LLM_TIMEOUT,
                circuit_breaker=self._breaker,
            )
            all_clauses.extend(self._parse_clauses(result))
            all_entities.extend(self._parse_entities(result))
            if contract_type in ("", "未识别"):
                contract_type = (result.get("contract_type") or "").strip() or contract_type
            logger.debug("分块 %d/%d 提取完成", idx + 1, len(chunks))

        return all_clauses, self._dedupe_entities(all_entities), (contract_type or "未识别")

    @staticmethod
    def _dedupe_entities(entities: list[ContractEntity]) -> list[ContractEntity]:
        """跨分块去重实体（按 type+value）。"""
        seen: set[tuple[str, str]] = set()
        out: list[ContractEntity] = []
        for e in entities:
            key = (e.entity_type, e.value.strip())
            if key in seen or not e.value.strip():
                continue
            seen.add(key)
            out.append(e)
        return out

    @staticmethod
    def _validate_extraction(data, schema=None) -> dict:
        """先用 Pydantic schema 校验,失败抛 ValueError 触发 LLM 修复。"""
        if schema is None:
            schema = ClauseExtractionSchema
        if isinstance(data, dict):
            try:
                validated = schema.model_validate(data)
                return validated.model_dump(mode="json")
            except Exception as e:
                raise ValueError(f"Schema validation failed: {e}")
        # 不是 dict 时也抛错
        raise ValueError(f"Expected dict, got {type(data).__name__}")

    async def _extract_with_llm(self, text: str) -> dict:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=(
                f"请提取以下合同的条款信息：\n\n"
                f"{wrap_untrusted('contract', text)}"
            )),
        ]
        # 结构化调用：解析 + Pydantic schema 校验 + 不合法自我修复重试
        return await structured_llm_call(
            self.llm,
            messages,
            validator=self._validate_extraction,
            max_repair_retries=settings.LLM_REPAIR_RETRIES,
            schema=ClauseExtractionSchema,
        )

    def _parse_clauses(self, result: dict) -> list[Clause]:
        clauses = []
        for item in result.get("clauses", []):
            try:
                category = ClauseCategory(item.get("category", "other"))
            except ValueError:
                category = ClauseCategory.OTHER
            clauses.append(
                Clause(
                    title=item.get("title", "未命名条款"),
                    content=item.get("content", ""),
                    category=category,
                    section_number=item.get("section_number", ""),
                )
            )
        return clauses

    def _parse_entities(self, result: dict) -> list[ContractEntity]:
        entities = []
        for item in result.get("entities", []):
            entities.append(
                ContractEntity(
                    entity_type=item.get("entity_type", "other"),
                    value=item.get("value", ""),
                    location=item.get("location", ""),
                )
            )
        return entities

    def _fallback_extraction(self, raw_text: str) -> list[Clause]:
        """LLM调用失败时的回退方案：基于规则切分条款。"""
        sections = parse_raw_text_to_sections(raw_text)
        return [
            Clause(
                title=s["title"],
                content=s["content"],
                category=ClauseCategory.OTHER,
            )
            for s in sections
        ]
