import pytest
from src.alerts.notifier import Notifier, notifier


@pytest.mark.asyncio
async def test_notifier_send(caplog):
    n = Notifier()
    with caplog.at_level("INFO", logger="alerts"):
        await n.send("test", "test message", severity="info", review_id="r1")
    assert any("[alert:test]" in r.message and "test message" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_notifier_send_bad_case(caplog):
    with caplog.at_level("INFO", logger="alerts"):
        await notifier.send_bad_case("c1", "r1", "high")
    assert any("c1" in r.message and "r1" in r.message for r in caplog.records)