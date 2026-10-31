from pydantic import BaseModel


class DiagnosticReport(BaseModel):
    review_id: str
    timestamp: str

    rules_result: dict | None = None
    similar_feedback: list[dict] = []
    similar_bad_cases: list[dict] = []
    similar_good_signatures: list[dict] = []

    # v2 新增: Loop 节点深度分析
    deep_analyses: list[dict] = []

    hypothesis: str = ""
    recommended_actions: list[str] = []

    state_warnings: list[str] = []
    state_degraded_steps: list[str] = []
    judge_score: float | None = None