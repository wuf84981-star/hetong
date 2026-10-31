"""Bad Case 管理 API。"""
from fastapi import APIRouter, Query

from ..schemas.bad_case import BadCaseListResponse, BadCaseItem, BadCaseResolveRequest
from ...services.bad_case_repo import BadCaseRepository

router = APIRouter(prefix="/api/v1/bad-cases", tags=["bad-cases"])


@router.get("", response_model=BadCaseListResponse)
async def list_bad_cases(
    min_severity: str = Query("medium", pattern="^(low|medium|high|critical)$"),
    limit: int = Query(50, ge=1, le=200),
):
    repo = BadCaseRepository()
    cases = await repo.list_unresolved(min_severity=min_severity)
    cases = cases[:limit]
    return BadCaseListResponse(
        total=len(cases),
        items=[
            BadCaseItem(
                case_id=bc.case_id,
                review_id=bc.review_id,
                signal_type=bc.signal_type,
                severity=bc.severity,
                timestamp=bc.timestamp,
                judge_score=bc.judge_score,
                judge_rationale=bc.judge_rationale,
                state_warnings=bc.state_warnings,
                state_degraded_steps=bc.state_degraded_steps,
                resolved=bc.resolved,
                resolution=bc.resolution,
                resolution_commit=bc.resolution_commit,
            )
            for bc in cases
        ],
    )


@router.post("/{case_id}/resolve")
async def resolve_bad_case(case_id: str, body: BadCaseResolveRequest):
    repo = BadCaseRepository()
    await repo.mark_resolved(case_id, commit=body.commit, notes=body.notes)
    return {"case_id": case_id, "resolved": True}