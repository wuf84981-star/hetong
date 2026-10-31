"""Bad case 结构化记录 — Tier 3 存储的最小数据单元(v1,告警用)。"""
from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum


class BadCaseSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BadCaseSignal(str, Enum):
    LOW_JUDGE_SCORE = "low_judge_score"
    HUMAN_REJECT = "human_reject"
    HUMAN_MODIFY = "human_modify"
    SCHEMA_FAILURE = "schema_failure"
    MULTIPLE_DEGRADED = "multiple_degraded"
    HIGH_RISK_MISSED = "high_risk_keyword_missed"
    USER_REPORTED = "user_reported"
    RULE_MISMATCH = "rule_mismatch"
    CLAUSE_REVIEW_REJECT = "clause_review_reject"
    CLAUSE_REVIEW_MISSED = "clause_review_missed"


@dataclass
class BadCase:
    review_id: str
    signal_type: str
    severity: str = BadCaseSeverity.MEDIUM.value
    case_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    tenant_id: str = ""
    input_summary: str = ""
    predicted_output: dict = field(default_factory=dict)
    expected_output: dict | None = None
    judge_score: float | None = None
    judge_rationale: str = ""
    model_version: str = ""
    prompt_version: str = ""
    state_warnings: list[str] = field(default_factory=list)
    state_degraded_steps: list[str] = field(default_factory=list)
    industry: str = ""
    contract_type: str = ""
    resolved: bool = False
    resolution: str = ""
    resolution_commit: str = ""
    signature_id: str = ""
    structured_case_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BadCase":
        return cls(**data)


__all__ = ["BadCase", "BadCaseSeverity", "BadCaseSignal"]