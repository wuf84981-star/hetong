"""认证模块单元测试。"""

from __future__ import annotations

import time

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from src.db.models import Base, UserRecord


# ── Fixtures ──────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


# ── 密码哈希测试 ──────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_password(self):
        hashed = hash_password("test123")
        assert hashed != "test123"
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_verify_correct_password(self):
        hashed = hash_password("correct_password")
        assert verify_password("correct_password", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_different_hashes(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2  # bcrypt 每次生成不同的盐


# ── JWT Token 测试 ──────────────────────────────────────

class TestJWTToken:
    def test_create_and_decode_token(self):
        token = create_access_token(subject="user-001", role="admin", tenant_id="tenant-abc")
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user-001"
        assert payload["role"] == "admin"
        assert payload["tenant_id"] == "tenant-abc"
        assert "exp" in payload

    def test_decode_invalid_token(self):
        payload = decode_access_token("invalid.token.here")
        assert payload is None

    def test_decode_tampered_token(self):
        token = create_access_token(subject="user-001", role="viewer")
        # 篡改 token
        tampered = token[:-5] + "XXXXX"
        payload = decode_access_token(tampered)
        assert payload is None

    def test_token_with_custom_expiry(self):
        from datetime import timedelta
        token = create_access_token(
            subject="user-002",
            role="reviewer",
            expires_delta=timedelta(seconds=1),
        )
        payload = decode_access_token(token)
        assert payload is not None
        # Token 有效
        assert payload["sub"] == "user-002"


# ── 数据库用户测试 ──────────────────────────────────────

class TestUserRecord:
    @pytest.mark.asyncio
    async def test_create_user(self, db_session):
        user = UserRecord(
            tenant_id="tenant-001",
            username="testuser",
            email="test@example.com",
            hashed_password=hash_password("password123"),
            role="viewer",
        )
        db_session.add(user)
        await db_session.flush()

        assert user.id is not None
        assert user.tenant_id == "tenant-001"
        assert user.username == "testuser"
        assert user.is_active is True

    @pytest.mark.asyncio
    async def test_user_role_default(self, db_session):
        user = UserRecord(
            tenant_id="tenant-002",
            username="newuser",
            email="new@example.com",
            hashed_password=hash_password("pass"),
        )
        db_session.add(user)
        await db_session.flush()

        assert user.role == "viewer"


# ── 验证码核销测试 ────────────────────────────────────────

class TestVerificationService:
    """verification_service 单元逻辑（直喂 MemoryCache，不触 Redis/SMTP）。"""

    @pytest.fixture(autouse=True)
    def fake_cache(self, monkeypatch):
        from src.cache import MemoryCache
        from src.services import verification_service as vs
        monkeypatch.setattr(vs, "_vc_cache", MemoryCache())
        return monkeypatch

    @pytest.mark.asyncio
    async def test_consume_correct_code(self):
        from src.services import verification_service as vs
        code = await vs.issue_code("a@b.com")
        assert len(code) == 6 and code.isdigit()
        await vs.consume_code("a@b.com", code)  # 通过不抛
        # 一次性：核销后键已删
        with pytest.raises(vs.VerificationError, match="未发送或已过期"):
            await vs.consume_code("a@b.com", code)

    @pytest.mark.asyncio
    async def test_wrong_code_does_not_extend_deadline(self):
        """H3 回归锁：错误尝试重设 attempts，但绝对 deadline 不许被推后。"""
        from src.services import verification_service as vs
        code = await vs.issue_code("a@b.com")
        cache = await vs._cache()
        before = await cache.get("vc:register:a@b.com")
        for _ in range(3):
            with pytest.raises(vs.VerificationError, match="验证码错误"):
                await vs.consume_code("a@b.com", code + "x")  # 7 字符恒不等于 6 位码
        after = await cache.get("vc:register:a@b.com")
        assert after["deadline"] == before["deadline"]
        assert after["attempts"] == 3
        assert after["code"] == before["code"]

    @pytest.mark.asyncio
    async def test_max_attempts_voids_code(self):
        from src.services import verification_service as vs
        code = await vs.issue_code("a@b.com")
        for _ in range(vs.MAX_ATTEMPTS):
            with pytest.raises(vs.VerificationError):
                await vs.consume_code("a@b.com", "000000" if code != "000000" else "111111")
        # 作废后连正确码也不认
        with pytest.raises(vs.VerificationError, match="作废|未发送或已过期"):
            await vs.consume_code("a@b.com", code)

    @pytest.mark.asyncio
    async def test_expired_deadline_rejected_even_if_code_matches(self):
        """不 hack 时钟：直接种一个 deadline 在过去的 payload。"""
        from src.services import verification_service as vs
        cache = await vs._cache()
        await cache.set("vc:register:a@b.com", {"code": "123456", "attempts": 0, "deadline": time.time() - 1}, ttl=300)
        with pytest.raises(vs.VerificationError, match="已过期"):
            await vs.consume_code("a@b.com", "123456")

    @pytest.mark.asyncio
    async def test_cooldown_flow(self):
        from src.services import verification_service as vs
        assert await vs.cooldown_remaining("a@b.com") == 0
        await vs.start_cooldown("a@b.com")
        assert await vs.cooldown_remaining("a@b.com") > 0

