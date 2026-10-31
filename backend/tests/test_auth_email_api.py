"""邮箱验证码注册的 API 集成测试 — send-code / register / login 双通道全链路。

sqlite 文件库（override get_db）+ MemoryCache（注入 verification_service）
+ 假 SMTP（patch mail_service._send_sync 记录出站消息），不发真实网络请求。
用 httpx.AsyncClient(ASGITransport) 而非 TestClient：所有请求与惰性创建的
async engine 都在 pytest-asyncio 的同一事件循环里，天然避开跨循环连接炸点。

注意 fixture 库为空 → 第一次注册会落 bootstrap（免码建 admin）分支；
测自助注册路径的用例须先 env.seed_first_user() 占位。
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.auth.security import create_access_token, hash_password
from src.api.main import create_app
from src.cache import MemoryCache
from src.config import settings
from src.db.models import Base, UserRecord
from src.db.session import get_db
from src.services import mail_service, verification_service as vs

# pytest-asyncio 默认 strict 模式：本文件全部 async 用例统一标注
pytestmark = pytest.mark.asyncio


def _auth(role: str, tenant: str = "t-admin") -> dict:
    token = create_access_token(subject=f"u-{role}", role=role, tenant_id=tenant)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def env(monkeypatch, tmp_path):
    """装配：sqlite override + 假缓存 + 假 SMTP。"""
    # 1) 验证码缓存：注入共享 MemoryCache（跳过探测、可被测试直接读写）
    cache = MemoryCache()
    monkeypatch.setattr(vs, "_vc_cache", cache)

    # 2) SMTP 配置齐但发送是假的（记录消息，不发网络）
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "SMTP_USER", "bot@test")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(settings, "SMTP_FROM", "")
    sent: list = []
    monkeypatch.setattr(mail_service, "_send_sync", lambda msg: sent.append(msg))

    # 3) sqlite 文件库，engine 在本循环惰性创建（单测试单循环）
    box: dict = {}

    async def _factory():
        if "f" not in box:
            eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/t.sqlite")
            async with eng.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            box["f"] = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
            box["eng"] = eng
        return box["f"]

    async def _get_db():
        f = await _factory()
        async with f() as s:
            async with s.begin():
                yield s

    async def _seed_first_user():
        """预置首管理员，把后续注册挤进自助分支（库非空 = 不再 bootstrap）。"""
        f = await _factory()
        async with f() as s:
            async with s.begin():
                s.add(UserRecord(
                    tenant_id="t-seed", username="root", email="root@test",
                    hashed_password=hash_password("rootpw"), role="admin",
                ))

    app = create_app()
    app.dependency_overrides[get_db] = _get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield SimpleNamespace(client=client, cache=cache, sent=sent,
                              db=_factory, seed_first_user=_seed_first_user)

    if "eng" in box:
        await box["eng"].dispose()


async def _register_self_service(env, username="alice", email="a@b.com", password="secret1", code=""):
    return await env.client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": password, "code": code},
    )


class TestSendCode:
    async def test_smtp_missing_503(self, env, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_HOST", "")
        r = await env.client.post("/api/v1/auth/send-code", json={"email": "a@b.com"})
        assert r.status_code == 503
        assert "SMTP" in r.json()["detail"]

    async def test_success_caches_code_and_sends(self, env):
        r = await env.client.post("/api/v1/auth/send-code", json={"email": "a@b.com"})
        assert r.status_code == 200
        data = await env.cache.get("vc:register:a@b.com")
        assert data and len(data["code"]) == 6
        assert len(env.sent) == 1
        assert data["code"] in env.sent[0].get_content()

    async def test_cooldown_429(self, env):
        await vs.start_cooldown("a@b.com")
        r = await env.client.post("/api/v1/auth/send-code", json={"email": "a@b.com"})
        assert r.status_code == 429
        assert not env.sent

    async def test_email_already_registered_409(self, env):
        await env.seed_first_user()  # 库里已有 root@test，再占一个 a@b.com
        r1 = await env.client.post(
            "/api/v1/auth/register", headers=_auth("admin"),
            json={"username": "occ", "email": "a@b.com", "password": "secret1", "role": "reviewer"},
        )
        assert r1.status_code == 201, r1.text
        r2 = await env.client.post("/api/v1/auth/send-code", json={"email": "a@b.com"})
        assert r2.status_code == 409
        assert "已注册" in r2.json()["detail"]

    async def test_bad_email_422(self, env):
        r = await env.client.post("/api/v1/auth/send-code", json={"email": "not-an-email"})
        assert r.status_code == 422

    async def test_send_failure_502_and_rolls_back(self, env, monkeypatch):
        def _boom(msg):
            raise RuntimeError("连不上 smtp.test")
        monkeypatch.setattr(mail_service, "_send_sync", _boom)
        r = await env.client.post("/api/v1/auth/send-code", json={"email": "a@b.com"})
        assert r.status_code == 502
        # 码回滚、不占冷却：用户可立即重试
        assert await env.cache.get("vc:register:a@b.com") is None
        assert await vs.cooldown_remaining("a@b.com") == 0


class TestRegister:
    async def test_no_token_no_code_400_not_401(self, env):
        """H1 回归锁：匿名请求必须穿过认证依赖、落在验证码门上（400 而非 401）。"""
        await env.seed_first_user()
        r = await _register_self_service(env)
        assert r.status_code == 400
        assert "验证码" in r.json()["detail"]

    async def test_self_service_reviewer_independent_tenant(self, env):
        await env.seed_first_user()
        code = await vs.issue_code("a@b.com")
        r = await _register_self_service(env, code=code)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["role"] == "reviewer"
        assert body["tenant_id"] not in ("", "t-seed")
        # 一次性：验证码已核销删除
        assert await env.cache.get("vc:register:a@b.com") is None
        # 再注册一个自助账号：租户互不相同
        code2 = await vs.issue_code("c@d.com")
        r2 = await _register_self_service(env, username="bob", email="c@d.com", code=code2)
        assert r2.json()["tenant_id"] != body["tenant_id"]

    async def test_wrong_code_increments_then_voids(self, env):
        await env.seed_first_user()
        code = await vs.issue_code("a@b.com")
        wrong = "000001" if code != "000001" else "000002"
        r = await _register_self_service(env, code=wrong)
        assert r.status_code == 400
        data = await env.cache.get("vc:register:a@b.com")
        assert data["attempts"] == 1
        for _ in range(vs.MAX_ATTEMPTS):
            await _register_self_service(env, code=wrong)
        # 作废后连正确码也不认
        r2 = await _register_self_service(env, code=code)
        assert r2.status_code == 400

    async def test_expired_deadline_400(self, env):
        await env.seed_first_user()
        await env.cache.set(
            "vc:register:a@b.com",
            {"code": "123456", "attempts": 0, "deadline": time.time() - 1},
            ttl=300,
        )
        r = await _register_self_service(env, code="123456")
        assert r.status_code == 400
        assert "过期" in r.json()["detail"]

    async def test_admin_creates_role_without_code(self, env):
        await env.seed_first_user()
        r = await env.client.post(
            "/api/v1/auth/register", headers=_auth("admin"),
            json={"username": "staff", "email": "a@b.com", "password": "secret1", "role": "reviewer"},
        )
        assert r.status_code == 201
        assert r.json()["role"] == "reviewer"
        assert r.json()["tenant_id"] == "t-admin"  # 归属管理员租户

    async def test_viewer_cannot_self_elevate(self, env):
        await env.seed_first_user()
        r = await env.client.post(
            "/api/v1/auth/register", headers=_auth("viewer", tenant="t-x"),
            json={"username": "sneak", "email": "a@b.com", "password": "secret1", "role": "admin"},
        )
        assert r.status_code == 403

    async def test_bootstrap_first_user_admin_without_code(self, env):
        """空库首用户：SMTP 没配也能出第一个管理员（鸡生蛋防线）。"""
        r = await _register_self_service(env)
        assert r.status_code == 201
        assert r.json()["role"] == "admin"

    async def test_email_case_normalized(self, env):
        await env.seed_first_user()
        code = await vs.issue_code("a@b.com")  # 键按小写邮箱
        r = await _register_self_service(env, email="A@B.com", code=code)
        assert r.status_code == 201, r.text
        assert r.json()["email"] == "a@b.com"

    async def test_garbage_token_401(self, env):
        """坏凭证不许静默降级成匿名。"""
        r = await env.client.post(
            "/api/v1/auth/register", headers={"Authorization": "Bearer not.a.jwt"},
            json={"username": "u", "email": "a@b.com", "password": "secret1"},
        )
        assert r.status_code == 401


class TestLoginDualChannel:
    async def _make_user(self, env):
        """bootstrap 建一个 a@b.com 账号（免码），供登录用例复用。"""
        r = await _register_self_service(env)
        assert r.status_code == 201, r.text

    async def test_login_by_username(self, env):
        await self._make_user(env)
        r = await env.client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret1"})
        assert r.status_code == 200

    async def test_login_by_email_case_insensitive(self, env):
        await self._make_user(env)
        for ident in ("a@b.com", "A@B.com", "a@B.com"):
            r = await env.client.post("/api/v1/auth/login", json={"username": ident, "password": "secret1"})
            assert r.status_code == 200, ident

    async def test_login_wrong_password_401(self, env):
        await self._make_user(env)
        r = await env.client.post("/api/v1/auth/login", json={"username": "a@b.com", "password": "nope"})
        assert r.status_code == 401

    async def test_login_inactive_403(self, env):
        await self._make_user(env)
        f = await env.db()
        async with f() as s:
            async with s.begin():
                u = (await s.execute(select(UserRecord).where(UserRecord.email == "a@b.com"))).scalar_one()
                u.is_active = False
        r = await env.client.post("/api/v1/auth/login", json={"username": "a@b.com", "password": "secret1"})
        assert r.status_code == 403
