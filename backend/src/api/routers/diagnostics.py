from fastapi import APIRouter, HTTPException

from ..schemas.diagnostic import DiagnosticReport
from ...services.bad_case_repo import BadCaseRepository

router = APIRouter(prefix="/api/v1/diagnostics", tags=["diagnostics"])


@router.get("/bad-cases/{case_id}", response_model=DiagnosticReport)
async def diagnose_bad_case(case_id: str):
    repo = BadCaseRepository()
    cases = await repo.list_all(limit=1000)
    target = next((bc for bc in cases if bc.case_id == case_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"bad case {case_id} not found")

    return DiagnosticReport(
        review_id=target.review_id,
        timestamp=target.timestamp,
        rules_result=None,
        similar_feedback=[],
        similar_bad_cases=[target.to_dict()],
        deep_analyses=[],
        hypothesis="简易诊断(待 TwoStageComparator 接入后升级)",
        recommended_actions=["查看 judge_score", "检查 state_warnings"],
        state_warnings=target.state_warnings,
        state_degraded_steps=target.state_degraded_steps,
        judge_score=target.judge_score,
    )


@router.get("/reviews/{review_id}", response_model=DiagnosticReport)
async def diagnose_review(review_id: str):
    repo = BadCaseRepository()
    cases = await repo.list_all(limit=1000)
    target = next((bc for bc in cases if bc.review_id == review_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"review {review_id} has no bad case record")
    return DiagnosticReport(
        review_id=target.review_id,
        timestamp=target.timestamp,
        similar_bad_cases=[target.to_dict()],
        hypothesis="简易诊断",
        recommended_actions=[],
        state_warnings=target.state_warnings,
        state_degraded_steps=target.state_degraded_steps,
        judge_score=target.judge_score,
    )