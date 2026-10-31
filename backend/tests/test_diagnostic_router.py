import pytest
from httpx import ASGITransport, AsyncClient
from src.api.main import app
import os
os.environ["AUTH_DISABLED"] = "true"


@pytest.mark.asyncio
async def test_diagnose_bad_case_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/diagnostics/bad-cases/nonexistent")
    assert resp.status_code in (404, 401)


@pytest.mark.asyncio
async def test_diagnose_review_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/diagnostics/reviews/nonexistent")
    assert resp.status_code in (404, 401)