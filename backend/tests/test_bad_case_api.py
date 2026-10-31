from src.api.schemas.bad_case import BadCaseItem, BadCaseListResponse, BadCaseResolveRequest


def test_bad_case_item_basic():
    item = BadCaseItem(
        case_id="c1", review_id="r1",
        signal_type="low_judge_score", severity="high",
        timestamp="2026-07-05T00:00:00",
    )
    assert item.case_id == "c1"
    assert item.severity == "high"


def test_list_response():
    resp = BadCaseListResponse(total=10, items=[
        BadCaseItem(case_id=f"c{i}", review_id=f"r{i}",
                    signal_type="x", severity="low", timestamp="t")
        for i in range(10)
    ])
    assert resp.total == 10
    assert len(resp.items) == 10


def test_resolve_request():
    req = BadCaseResolveRequest(commit="abc123", notes="修了 prompt")
    assert req.commit == "abc123"