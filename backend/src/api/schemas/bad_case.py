from pydantic import BaseModel


class BadCaseItem(BaseModel):
    case_id: str
    review_id: str
    signal_type: str
    severity: str
    timestamp: str
    judge_score: float | None = None
    judge_rationale: str = ""
    state_warnings: list[str] = []
    state_degraded_steps: list[str] = []
    resolved: bool = False
    resolution: str = ""
    resolution_commit: str = ""


class BadCaseListResponse(BaseModel):
    total: int
    items: list[BadCaseItem]


class BadCaseResolveRequest(BaseModel):
    commit: str = ""
    notes: str = ""