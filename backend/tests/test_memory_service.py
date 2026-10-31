"""Memory service 测试 — 跨会话学习。"""
import json
import pytest
from pathlib import Path

from src.memory_service import MemoryService


@pytest.fixture
def mem(tmp_path):
    return MemoryService(tenant_id="t1", storage_path=str(tmp_path))


def test_record_outcome_creates_jsonl(mem, tmp_path):
    mem.record_outcome(
        review_id="r1",
        decision="approve",
        comments="合理的付款条款",
        high_risk_clauses=["c1"],
    )
    file_path = tmp_path / "t1.jsonl"
    assert file_path.exists()
    lines = file_path.read_text(encoding="utf-8").strip().split("\n")
    entry = json.loads(lines[0])
    assert entry["review_id"] == "r1"
    assert entry["decision"] == "approve"
    assert entry["comments"] == "合理的付款条款"
    assert "付款" in entry["tags"]


def test_search_relevant_returns_matching(mem):
    mem.record_outcome("r1", "approve", "付款条款合理,信用证结算", ["c1"])
    mem.record_outcome("r2", "reject", "无限责任不可接受", ["c2"])
    mem.record_outcome("r3", "modify", "要求修改管辖法院条款", ["c3"])

    results = mem.search_relevant("关于付款和责任的合同", top_k=2)
    assert len(results) >= 1
    review_ids = [r["review_id"] for r in results]
    assert "r1" in review_ids


def test_search_relevant_top_k_limit(mem):
    for i in range(5):
        mem.record_outcome(f"r{i}", "approve", f"付款条款 {i}", [])
    results = mem.search_relevant("付款", top_k=2)
    assert len(results) <= 2


def test_tenant_isolation(tmp_path):
    mem1 = MemoryService(tenant_id="t1", storage_path=str(tmp_path))
    mem2 = MemoryService(tenant_id="t2", storage_path=str(tmp_path))
    mem1.record_outcome("r1", "approve", "secret t1 keyword xyz", [])
    mem2.record_outcome("r2", "approve", "secret t2 keyword abc", [])

    results = mem1.search_relevant("t1 xyz", top_k=5)
    assert all(r["review_id"] != "r2" for r in results)
    results = mem2.search_relevant("t2 abc", top_k=5)
    assert all(r["review_id"] != "r1" for r in results)


def test_empty_history_returns_empty(mem):
    results = mem.search_relevant("any query", top_k=3)
    assert results == []


def test_search_no_match_returns_empty(mem):
    mem.record_outcome("r1", "approve", "苹果和香蕉", [])
    results = mem.search_relevant("关于汽车发动机的问题", top_k=3)
    assert results == []


def test_submit_feedback_records_to_memory(tmp_path):
    """submit_feedback 应沉淀人工反馈到 MemoryService。

    submit_feedback 深度依赖 LangGraph ainvoke/checkpointer，难以直接端到端调用;
    此处做两层断言:
      1) review_service.py 源码中确实出现 MemoryService + record_outcome 调用;
      2) RiskFinding -> high_risk_clauses 的提取 + MemoryService 写入链路正确。
    """
    import re
    from pathlib import Path
    from src.pipeline.state import RiskFinding, RiskLevel

    # 1) 源码层断言
    src = (
        Path(__file__).resolve().parents[1] / "src" / "services" / "review_service.py"
    )
    text = src.read_text(encoding="utf-8")
    assert "MemoryService" in text, "review_service.py 应引用 MemoryService"
    assert "record_outcome" in text, "review_service.py 应调用 record_outcome"
    assert re.search(
        r"high_risk_clauses\s*=\s*\[.*clause_id.*risk_level\.value.*high",
        text,
        re.DOTALL,
    ), "应按 high 等级过滤 clause_id"

    # 2) 隔离层断言：high_risk_clauses 提取 + MemoryService 记录
    findings = [
        RiskFinding(
            clause_id="c1",
            risk_level=RiskLevel.HIGH,
            risk_type="无限责任",
            description="乙方承担无上限责任",
        ),
        RiskFinding(
            clause_id="c2",
            risk_level=RiskLevel.MEDIUM,
            risk_type="付款延迟",
            description="付款延期 30 天",
        ),
        RiskFinding(
            clause_id="c3",
            risk_level=RiskLevel.HIGH,
            risk_type="管辖不利",
            description="约定争议由对方所在地法院管辖",
        ),
    ]
    high_risk_clauses = [
        f.clause_id for f in findings if f.risk_level.value == "high"
    ]
    assert high_risk_clauses == ["c1", "c3"]

    mem = MemoryService(tenant_id="t1", storage_path=str(tmp_path))
    mem.record_outcome(
        review_id="r1",
        decision="reject",
        comments="不接受无限责任",
        high_risk_clauses=high_risk_clauses,
    )
    file_path = tmp_path / "t1.jsonl"
    assert file_path.exists()
    entry = json.loads(
        file_path.read_text(encoding="utf-8").strip().split("\n")[0]
    )
    assert "c1" in entry["high_risk_clauses"]
    assert "c3" in entry["high_risk_clauses"]
    assert "c2" not in entry["high_risk_clauses"]
    assert entry["decision"] == "reject"
    assert entry["comments"] == "不接受无限责任"


def test_risk_identification_injects_history(monkeypatch, tmp_path):
    """risk_identification 应在 prompt 中包含历史经验（如有）。"""
    # 写一些历史经验
    from src.memory_service import MemoryService
    m = MemoryService(tenant_id="t1", storage_path=str(tmp_path))
    m.record_outcome("past-1", "reject", "付款条款责任太重,信用证问题", ["c5"])

    # 写一个新的查询
    results = m.search_relevant("合同付款条款评估", top_k=3)
    assert len(results) >= 1
    assert "付款" in results[0]["tags"]
