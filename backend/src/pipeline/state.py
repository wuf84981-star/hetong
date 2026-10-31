"""
共享状态定义 — 多Agent流水线的核心数据模型。

所有Agent通过共享状态通信，LangGraph负责状态的传递和持久化。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


# ── 枚举类型 ──────────────────────────────────────────────────

class RiskLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class ComplianceStatus(str, Enum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    NEEDS_REVIEW = "needs_review"


class ClauseCategory(str, Enum):
    PAYMENT = "payment"
    LIABILITY = "liability"
    CONFIDENTIALITY = "confidentiality"
    TERMINATION = "termination"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    DISPUTE_RESOLUTION = "dispute_resolution"
    FORCE_MAJEURE = "force_majeure"
    WARRANTY = "warranty"
    INDEMNIFICATION = "indemnification"
    GOVERNING_LAW = "governing_law"
    OTHER = "other"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_HUMAN = "awaiting_human"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


# ── 数据模型 ──────────────────────────────────────────────────

class ContractEntity(BaseModel):
    """合同中识别出的实体"""
    entity_type: str = Field(description="实体类型：party_a, party_b, amount, date, subject")
    value: str = Field(description="实体值")
    location: str = Field(default="", description="在文档中的位置")


class Clause(BaseModel):
    """结构化条款"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = Field(description="条款标题")
    content: str = Field(description="条款内容")
    category: ClauseCategory = Field(default=ClauseCategory.OTHER)
    section_number: str = Field(default="", description="章节编号")
    entities: list[ContractEntity] = Field(default_factory=list)


class RagRef(BaseModel):
    """RAG 检索引用——记录本条结论审查时参考过的知识库条文，让"判断依据"可审计。"""
    doc_title: str = Field(default="", description="出处文档（法名/文件名）")
    clause_title: str = Field(default="", description="条文标题，如 第五百八十五条")
    category: str = Field(default="", description="civil/labor/commercial/other")
    score: float = Field(default=0.0, description="相似度 0-1")
    snippet: str = Field(default="", description="命中内容摘要（≤200字）")


class RiskFinding(BaseModel):
    """风险发现"""
    clause_id: str = Field(description="关联的条款ID")
    risk_level: RiskLevel = Field(description="风险等级")
    risk_type: str = Field(description="风险类型")
    description: str = Field(description="风险描述")
    buyer_impact: str = Field(default="", description="对买方的影响")
    seller_impact: str = Field(default="", description="对卖方的影响")
    rationale: str = Field(default="", description="判断依据")
    source: str = Field(default="llm", description="发现来源：rule=规则引擎 / llm=大模型 / conflict=双引擎分歧")
    rag_refs: list[RagRef] = Field(default_factory=list, description="审查时命中的知识库条文引用")


class ComplianceFinding(BaseModel):
    """合规发现"""
    clause_id: str = Field(description="关联的条款ID")
    status: ComplianceStatus = Field(description="合规状态")
    regulation: str = Field(description="相关法规")
    issue: str = Field(description="合规问题描述")
    recommendation: str = Field(default="", description="改进建议")
    rag_refs: list[RagRef] = Field(default_factory=list, description="审查时命中的知识库条文引用")


class Suggestion(BaseModel):
    """修改建议"""
    clause_id: str = Field(description="关联的条款ID")
    original_text: str = Field(description="原始文本")
    suggested_text: str = Field(description="建议修改后的文本")
    reason: str = Field(description="修改原因")
    priority: RiskLevel = Field(description="优先级")
    rag_refs: list[RagRef] = Field(default_factory=list, description="生成改稿时命中的知识库条文引用")


class HumanFeedback(BaseModel):
    """人工反馈"""
    reviewer: str = Field(description="审核人")
    decision: str = Field(description="决定：approve/reject/modify")
    comments: str = Field(default="", description="审核意见")
    modified_suggestions: list[Suggestion] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)


class StepEvent(BaseModel):
    """流水线步骤事件（用于进度追踪）。"""
    step: str = Field(description="步骤 key：clause_extraction/risk_identification/compliance_check/suggestion")
    status: str = Field(description="状态：running/done/error")
    message: str = Field(default="", description="步骤描述信息，如「提取了 12 条条款」")
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: datetime | None = None


# 流水线步骤顺序与中文标签
PIPELINE_STEPS = [
    "clause_extraction",
    "risk_identification",
    "compliance_check",
    "suggestion",
]

STEP_LABELS: dict[str, str] = {
    "clause_extraction": "条款提取",
    "risk_identification": "风险识别",
    "compliance_check": "合规检查",
    "suggestion": "修改建议",
}

# 审查立场：递交人指定我方身份，风险与建议均以此立场衡量
POSITION_LABELS: dict[str, str] = {
    "buyer": "买方/甲方",
    "seller": "卖方/乙方",
    "neutral": "中立",
}


def position_directive(position: str) -> str:
    """生成注入风险识别提示的立场指令；中立立场返回空串（保持原行为）。"""
    if position == "buyer":
        return (
            "\n\n【审查立场】本次审查站在买方（甲方）立场进行："
            "请把对买方不利的条款作为重点，如实详述 buyer_impact；"
            "对买方有利但对卖方明显不公、可能在磋商中被退回的条款，按中等风险提示即可。"
        )
    if position == "seller":
        return (
            "\n\n【审查立场】本次审查站在卖方（乙方）立场进行："
            "请把对卖方不利的条款作为重点，如实详述 seller_impact；"
            "对卖方有利但对买方明显不公、可能在磋商中被退回的条款，按中等风险提示即可。"
        )
    return ""


def position_suggestion_directive(position: str) -> str:
    """生成注入修改建议提示的立场指令；中立立场返回空串（保持原行为）。"""
    label = POSITION_LABELS.get(position, "")
    if not label or position == "neutral":
        return ""
    return (
        f"\n\n【审查立场】本次审查站在{label}立场进行："
        "请在合法合规的前提下，让建议修改后的表述向我方倾斜"
        "（如责任上限、付款节奏、违约救济等），并说明对我方的助益。"
    )


# ── LangGraph 流水线状态 ──────────────────────────────────────

class ContractReviewState(BaseModel):
    """
    LangGraph流水线的共享状态。

    所有Agent读写此状态对象，LangGraph负责状态的传递、
    checkpoint保存和interrupt/resume机制。
    """
    # 基础信息
    review_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: ReviewStatus = Field(default=ReviewStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = Field(default=None, description="最近更新时间")

    # 输入
    document_path: str = Field(default="", description="合同文档存储路径")
    original_filename: str = Field(default="", description="上传时的原始文件名")
    raw_text: str = Field(default="", description="合同原始文本")
    raw_text_path: str = ""  # P0-4: 文件路径(新路径);raw_text 保留向后兼容
    position: str = Field(default="neutral", description="审查立场：buyer / seller / neutral")

    # Agent 1: 条款提取结果
    clauses: list[Clause] = Field(default_factory=list)
    entities: list[ContractEntity] = Field(default_factory=list)
    contract_type: str = Field(default="", description="合同类型")
    industry: str = Field(default="", description="行业维度（用于分层抽样）")

    # Agent 2: 风险识别结果
    risk_findings: list[RiskFinding] = Field(default_factory=list)
    overall_risk_level: RiskLevel = Field(default=RiskLevel.NONE)
    risk_summary: str = Field(default="")

    # Agent 3: 合规检查结果
    compliance_findings: list[ComplianceFinding] = Field(default_factory=list)
    overall_compliance: ComplianceStatus = Field(default=ComplianceStatus.NEEDS_REVIEW)
    missing_clauses: list[str] = Field(default_factory=list)

    # Agent 4: 修改建议
    suggestions: list[Suggestion] = Field(default_factory=list)
    version_diff: str = Field(default="", description="版本对比结果")

    # 人机协同
    needs_human_review: bool = Field(default=False)
    human_feedback: HumanFeedback | None = Field(default=None)

    # 错误处理
    errors: list[str] = Field(default_factory=list)

    # 进度追踪
    current_step: str = Field(default="", description="当前正在执行的步骤 key")
    step_log: list[StepEvent] = Field(default_factory=list, description="步骤事件日志")
    progress: float = Field(default=0.0, description="完成进度 0.0-1.0")

    # LangGraph消息追踪
    messages: Annotated[list[Any], add_messages] = Field(default_factory=list)

    # P0-3: 新增字段（侑夕《Harness 验证基线》原则）
    warnings: list[str] = Field(default_factory=list)
    degraded_steps: set[str] = Field(default_factory=set)
    schema_failures: list[dict] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
