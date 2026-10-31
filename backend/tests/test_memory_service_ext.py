"""MemoryService 扩展字段测试 — bad_clauses / missed_clauses。"""
import json
import pytest


def test_record_outcome_supports_bad_clauses(tmp_path):
    from src.memory_service import MemoryService
    mem = MemoryService(tenant_id="t1", storage_path=str(tmp_path))
    mem.record_outcome(
        review_id="r1",
        decision="reject",
        comments="风险识别不全",
        high_risk_clauses=["c1"],
        bad_clauses=["c3"],
        missed_clauses=["c5"],
    )
    entry = json.loads(tmp_path.joinpath("t1.jsonl").read_text(encoding="utf-8").strip().split("\n")[0])
    assert "bad_clauses" in entry
    assert "missed_clauses" in entry
    assert entry["bad_clauses"] == ["c3"]
    assert entry["missed_clauses"] == ["c5"]
    assert entry["high_risk_clauses"] == ["c1"]
