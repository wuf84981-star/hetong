import json
import pytest

from src.pipeline.state import ContractReviewState, ReviewStatus, RiskLevel, Clause
from src.services.signature_service import SignatureService, ReviewSignature


@pytest.fixture
def sig_service(tmp_path):
    return SignatureService(storage_path=str(tmp_path))


def _make_state(review_id, contract_type="买卖合同", industry="",
                risk_level=RiskLevel.LOW, clauses_count=10, degraded_steps=None):
    s = ContractReviewState(
        review_id=review_id,
        status=ReviewStatus.COMPLETED,
        contract_type=contract_type,
        clauses=[
            Clause.model_construct(id=f"c{i}", title="", content="")
            for i in range(clauses_count)
        ],
        risk_findings=[],
        overall_risk_level=risk_level,
    )
    if degraded_steps:
        s.degraded_steps = set(degraded_steps)
    if industry:
        s.industry = industry
    return s


def test_high_risk_always_sampled(sig_service):
    state = _make_state("r1", risk_level=RiskLevel.HIGH)
    should, reason = sig_service.should_sample(state)
    assert should is True
    assert "high_risk" in reason


def test_degraded_step_always_sampled(sig_service):
    state = _make_state("r1", degraded_steps={"clause_extraction"})
    should, reason = sig_service.should_sample(state)
    assert should is True
    assert "degraded" in reason


def test_stratified_weight_rare_contracts(sig_service):
    state = _make_state("r1", contract_type="涉外合同")
    sampled = sum(1 for _ in range(100) if sig_service.should_sample(state)[0])
    assert sampled >= 5


def test_stratified_weight_rare_industries(sig_service):
    state = _make_state("r1", industry="金融")
    sampled = sum(1 for _ in range(100) if sig_service.should_sample(state)[0])
    assert sampled >= 5


def test_industry_rare_takes_precedence(sig_service):
    state = _make_state("r1", contract_type="买卖合同", industry="金融")
    sampled = sum(1 for _ in range(100) if sig_service.should_sample(state)[0])
    assert sampled >= 5


def test_stratified_weight_common_contracts(sig_service):
    state = _make_state("r1", contract_type="买卖合同")
    sampled = sum(1 for _ in range(1000) if sig_service.should_sample(state)[0])
    assert sampled < 50


def test_maybe_record_writes_to_jsonl(sig_service, tmp_path):
    state = _make_state("r1", risk_level=RiskLevel.HIGH)
    sig_service.maybe_record(state)
    file = tmp_path / "signatures.jsonl"
    assert file.exists()
    entry = json.loads(file.read_text(encoding="utf-8").strip().split("\n")[0])
    assert entry["review_id"] == "r1"
    assert entry["contract_type"] == "买卖合同"


def test_signature_extract_no_pii(sig_service):
    state = ContractReviewState(
        review_id="r1",
        raw_text="敏感合同内容 - 包含身份证号 110101199001011234",
        clauses=[],
    )
    sig_service.maybe_record(state, force=True)
    file = sig_service.path
    if file.exists():
        content = file.read_text(encoding="utf-8")
        assert "110101199001011234" not in content
        assert "敏感合同内容" not in content