"""审查相关请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    """提交审查请求。"""
    text: str = Field(description="合同文本内容", min_length=1)
    with_human_review: bool = Field(default=True, description="是否启用人工审核")
    position: str = Field(default="neutral", pattern="^(buyer|seller|neutral)$",
                          description="审查立场：buyer=买方/甲方, seller=卖方/乙方, neutral=中立")


class StepEventSchema(BaseModel):
    """步骤事件（进度推送）。"""
    step: str
    status: str  # running / done / error
    message: str = ""
    started_at: str = ""
    finished_at: str | None = None


class ReviewResponse(BaseModel):
    """审查提交响应（摘要）。"""
    review_id: str
    status: str
    contract_type: str = ""
    position: str = "neutral"
    clauses_count: int = 0
    risk_summary: str = ""
    overall_risk_level: str = ""
    overall_compliance: str = ""
    suggestions_count: int = 0
    needs_human_review: bool = False
    filename: str = ""
    created_at: str = ""
    updated_at: str = ""
    current_step: str = ""
    progress: float = 0.0
    step_log: list[StepEventSchema] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    """人工审核反馈请求 (v2: 含颗粒度字段)。"""
    reviewer: str = Field(description="审核人姓名", min_length=1)
    decision: str = Field(description="决定：approve / reject / modify")
    comments: str = Field(default="", description="审核意见")
    modified_suggestions: list | None = None
    bad_clauses: list[str] | None = None
    missed_clauses: list[str] | None = None
    overall_rating: int | None = None
    industry: str = ""
    contract_type_hint: str = ""


class DetailedReviewResponse(BaseModel):
    """审查详情响应（完整数据）。"""
    review_id: str
    status: str
    contract_type: str
    position: str = "neutral"
    filename: str = ""
    created_at: str = ""
    updated_at: str = ""
    clauses: list[dict]
    risk_findings: list[dict]
    risk_summary: str
    overall_risk_level: str
    risk_score: float = 0.0
    compliance_findings: list[dict]
    missing_clauses: list[str]
    overall_compliance: str
    suggestions: list[dict]
    version_diff: str
    needs_human_review: bool
    human_feedback: dict | None = None
    errors: list[str]
    current_step: str = ""
    progress: float = 0.0
    step_log: list[StepEventSchema] = Field(default_factory=list)

    # P0-3: 暴露降级状态
    warnings: list[str] = Field(default_factory=list)
    degraded_steps: list[str] = Field(default_factory=list)
    has_quality_issues: bool = False


class TaskResponse(BaseModel):
    """异步任务响应。"""
    review_id: str
    task_id: str = ""
    status: str = "pending"
    message: str = ""


class BatchReviewItem(BaseModel):
    """批量审查中的单个文件。"""
    review_id: str
    filename: str
    status: str = "pending"
    error: str = ""


class BatchReviewResponse(BaseModel):
    """批量审查响应。"""
    batch_id: str
    total: int
    completed: int
    failed: int
    status: str  # pending / processing / completed / partial_failure
    items: list[BatchReviewItem]


class BatchStatusResponse(BaseModel):
    """批量审查状态查询响应。"""
    batch_id: str
    total: int
    completed: int
    failed: int
    in_progress: int
    status: str
    items: list[BatchReviewItem]


class ReviewHistoryItem(BaseModel):
    """审查历史列表项。"""
    review_id: str
    status: str
    contract_type: str = ""
    overall_risk_level: str = "none"
    overall_compliance: str = "needs_review"
    needs_human_review: bool = False
    risk_summary: str = ""
    filename: str = ""
    created_at: str = ""
    updated_at: str = ""


class ReviewHistoryResponse(BaseModel):
    """审查历史列表响应。"""
    total: int
    items: list[ReviewHistoryItem]
