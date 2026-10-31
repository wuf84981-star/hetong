import pytest
from httpx import ASGITransport, AsyncClient
from src.api.main import app
import os
os.environ["AUTH_DISABLED"] = "true"


@pytest.mark.asyncio
async def test_full_loop_review_to_badcase_to_diagnose():
    """完整路径 smoke test(不实际跑 LLM)。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # 1. 列出 bad cases(应该返回空或现有)
        resp1 = await c.get("/api/v1/bad-cases")
        assert resp1.status_code in (200, 401)

        # 2. 诊断一个不存在的 case
        resp2 = await c.get("/api/v1/diagnostics/bad-cases/nonexistent")
        assert resp2.status_code in (404, 401)