import pytest
from httpx import ASGITransport, AsyncClient
from src.api.main import app
import os

# AUTH 跳过
os.environ["AUTH_DISABLED"] = "true"


@pytest.mark.asyncio
async def test_list_bad_cases_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/bad-cases?min_severity=medium")
    assert resp.status_code in (200, 401)
    if resp.status_code == 200:
        data = resp.json()
        assert "total" in data
        assert "items" in data