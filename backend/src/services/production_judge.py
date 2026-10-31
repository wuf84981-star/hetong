"""生产环境 LLM-as-judge 自动评分 + 告警。"""
from __future__ import annotations
import logging
import random
from typing import TYPE_CHECKING

from eval.judge import LLMJudge, JudgeResult
from ..models.bad_case import BadCase, BadCaseSeverity, BadCaseSignal
from .bad_case_repo import BadCaseRepository

if TYPE_CHECKING:
    from ..pipeline.state import ContractReviewState

logger = logging.getLogger(__name__)


# 模块级默认仓库,方便测试通过 patch 替换
bad_case_repo = BadCaseRepository()


class ProductionJudgeRunner:
    def __init__(
        self,
        sample_rate: float = 0.10,
        alert_threshold: float = 6.0,
        judge: LLMJudge | None = None,
        bad_case_repo: BadCaseRepository | None = None,
    ):
        self.sample_rate = sample_rate
        self.alert_threshold = alert_threshold
        self.judge = judge or LLMJudge()
        # 缺省走模块级 bad_case_repo,便于测试 patch
        self.bad_case_repo = bad_case_repo if bad_case_repo is not None else globals()["bad_case_repo"]

    async def judge_if_sampled(self, state) -> JudgeResult | None:
        if random.random() > self.sample_rate:
            return None

        try:
            result = await self.judge.judge_clause_extraction(
                contract_text=state.raw_text or "",
                gold_clauses=[c.model_dump() if hasattr(c, "model_dump") else c for c in state.clauses],
                predicted_clauses=[],
            )
        except Exception:
            logger.exception("judge 失败 review_id=%s", state.review_id)
            return None

        if result.overall < self.alert_threshold:
            bad_case = BadCase(
                review_id=state.review_id,
                tenant_id=getattr(state, "tenant_id", ""),
                signal_type=BadCaseSignal.LOW_JUDGE_SCORE.value,
                severity=BadCaseSeverity.HIGH.value,
                judge_score=result.overall,
                judge_rationale=result.rationale,
                input_summary=(state.raw_text or "")[:500],
                state_warnings=list(state.warnings),
                state_degraded_steps=list(state.degraded_steps),
            )
            await self.bad_case_repo.save(bad_case)
            logger.warning("bad case detected review_id=%s judge_score=%.1f",
                           state.review_id, result.overall)

        return result