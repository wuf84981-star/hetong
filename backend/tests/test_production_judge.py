"""ProductionJudgeRunner 测试 — 采样 + 告警保存。

注意: tests/test_config.py 的 _reload_config 会从 sys.modules 删除 src.* 模块,
可能导致 module-level @patch 失效。这里的 fixture 在每个测试前重新导入
src.services.production_judge,确保 @patch 作用在最新模块实例上。
"""
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def production_judge_module():
    """每个测试都拿到一个 fresh 模块引用,避免 test_config 的 sys.modules 清理造成问题。"""
    # 如果当前不在 sys.modules(被 test_config 清掉了),重新导入
    if "src.services.production_judge" not in sys.modules:
        from src.services import production_judge
    else:
        from src.services import production_judge
    return production_judge


@pytest.mark.asyncio
async def test_judge_returns_none_when_not_sampled(production_judge_module):
    runner = production_judge_module.ProductionJudgeRunner(sample_rate=0.0)
    result = await runner.judge_if_sampled(state=MagicMock())
    assert result is None


@pytest.mark.asyncio
@patch("src.services.production_judge.LLMJudge")
async def test_judge_returns_result_when_sampled(mock_judge_cls, production_judge_module):
    from eval.judge import JudgeResult
    mock_judge = MagicMock()
    mock_judge.judge_clause_extraction = AsyncMock(return_value=JudgeResult(
        completeness=8, accuracy=8, critical_info_preserved=8,
        overall=8, rationale="ok"
    ))
    mock_judge_cls.return_value = mock_judge

    runner = production_judge_module.ProductionJudgeRunner(sample_rate=1.0)
    result = await runner.judge_if_sampled(state=MagicMock(raw_text="x", clauses=[]))
    assert result.overall == 8


@pytest.mark.asyncio
@patch("src.services.production_judge.LLMJudge")
@patch("src.services.production_judge.bad_case_repo")
async def test_low_score_saves_bad_case(mock_repo, mock_judge_cls, production_judge_module):
    from eval.judge import JudgeResult
    mock_judge = MagicMock()
    mock_judge.judge_clause_extraction = AsyncMock(return_value=JudgeResult(
        completeness=3, accuracy=3, critical_info_preserved=3,
        overall=3, rationale="严重漏检"
    ))
    mock_judge_cls.return_value = mock_judge
    mock_repo.save = AsyncMock()

    runner = production_judge_module.ProductionJudgeRunner(sample_rate=1.0, alert_threshold=6)
    state = MagicMock(review_id="r1", raw_text="x", clauses=[], tenant_id="t1")
    await runner.judge_if_sampled(state=state)
    mock_repo.save.assert_called_once()