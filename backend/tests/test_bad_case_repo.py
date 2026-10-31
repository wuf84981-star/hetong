import json
import pytest
from src.models.bad_case import BadCase, BadCaseSeverity
from src.services.bad_case_repo import BadCaseRepository


@pytest.fixture
def repo(tmp_path):
    return BadCaseRepository(storage_path=str(tmp_path))


@pytest.mark.asyncio
async def test_save_creates_jsonl(repo, tmp_path):
    bc = BadCase(review_id="r1", signal_type="low_judge_score",
                  severity=BadCaseSeverity.HIGH, judge_score=3.0)
    await repo.save(bc)
    file = tmp_path / "summaries.jsonl"
    assert file.exists()
    entry = json.loads(file.read_text(encoding="utf-8").strip().split("\n")[0])
    assert entry["review_id"] == "r1"


@pytest.mark.asyncio
async def test_save_truncates_input_summary(repo):
    bc = BadCase(review_id="r1", signal_type="low_judge_score",
                  input_summary="x" * 1000)
    await repo.save(bc)
    cases = await repo.list_all()
    assert len(cases[0].input_summary) == 500


@pytest.mark.asyncio
async def test_save_structured_creates_two_files(repo, tmp_path):
    from src.models.structured_bad_case import StructuredBadCase, IdentifiedRisk
    bc = StructuredBadCase(
        review_id="r1",
        contract_type="服务合同",
        industry="互联网",
        identified_risks=[
            IdentifiedRisk(clause_id="c1", risk_type="unlimited_liability",
                          severity="critical", description="无上限责任"),
        ],
        full_contract_text="x" * 50000,
        input_summary="x" * 1000,
    )
    await repo.save(bc)

    summary_file = tmp_path / "summaries.jsonl"
    assert summary_file.exists()
    summary = json.loads(summary_file.read_text(encoding="utf-8").strip().split("\n")[0])
    assert len(summary["input_summary"]) == 500

    full_file = tmp_path / "full.jsonl"
    assert full_file.exists()
    full = json.loads(full_file.read_text(encoding="utf-8").strip().split("\n")[0])
    assert len(full["full_contract_text"]) == 50000
    assert len(full["identified_risks"]) == 1


@pytest.mark.asyncio
async def test_load_full_returns_complete_data(repo):
    from src.models.structured_bad_case import StructuredBadCase
    bc = StructuredBadCase(review_id="r1", contract_type="服务合同",
                            full_contract_text="完整原文", input_summary="短摘要")
    await repo.save(bc)
    loaded = await repo.load_full(bc.case_id)
    assert loaded["full_contract_text"] == "完整原文"
    assert loaded["contract_type"] == "服务合同"


@pytest.mark.asyncio
async def test_list_unresolved_critical(repo):
    for sev in ["critical", "high", "medium", "low"]:
        await repo.save(BadCase(review_id=f"r-{sev}",
                                 signal_type="low_judge_score",
                                 severity=sev, resolved=(sev == "low")))
    cases = await repo.list_unresolved(min_severity="high")
    assert len(cases) == 2
    severities = {c.severity for c in cases}
    assert severities == {"critical", "high"}


@pytest.mark.asyncio
async def test_mark_resolved(repo):
    bc = BadCase(review_id="r1", signal_type="human_reject", severity="high")
    await repo.save(bc)
    await repo.mark_resolved(bc.case_id, commit="abc123", notes="修了 prompt")
    cases = await repo.list_unresolved()
    assert len(cases) == 0