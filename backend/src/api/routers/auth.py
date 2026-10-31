"""认证路由 — 注册（邮箱验证码）、登录（用户名/邮箱双通道）、用户信息。"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...db.models import UserRecord
from ...db.session import get_db
from ...services import mail_service, verification_service
from ..auth.dependencies import CurrentUser, get_optional_current_user
from ..auth.security import create_access_token, decode_access_token, hash_password, verify_password
from ..schemas.auth import (
    LoginRequest,
    RegisterRequest,
    SendCodeRequest,
    TokenResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_ELEVATED_ROLES = {"admin", "reviewer"}
_VALID_ROLES = {"admin", "reviewer", "viewer"}


@router.post("/send-code", status_code=status.HTTP_200_OK)
async def send_register_code(request: SendCodeRequest, db: AsyncSession = Depends(get_db)):
    """发送注册邮箱验证码（同一邮箱 60 秒冷却，验证码 5 分钟有效）。"""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库不可用，注册功能暂不可用",
        )

    email = request.email.strip().lower()

    # 已注册直接明说（register 本就返回 409，此处装聋只会让"忘记密码"的用户干等）
    dup = (await db.execute(select(UserRecord).where(UserRecord.email == email))).scalar_one_or_none()
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已注册，请直接登录；忘记密码请联系管理员重置",
        )

    remaining = await verification_service.cooldown_remaining(email)
    if remaining:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"验证码刚刚已发送，请 {remaining} 秒后重试",
            headers={"Retry-After": str(remaining)},
        )

    code = await verification_service.issue_code(email)
    try:
        await mail_service.send_verification_code(email, code)
    except mail_service.SMTPNotConfiguredError as e:
        await verification_service.revoke_code(email)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{e}——请管理员在 backend/.env 配置 SMTP 后重启",
        )
    except Exception as e:
        # 发送失败回滚验证码且不占冷却——用户可以立刻重试
        await verification_service.revoke_code(email)
        logger.error("验证码邮件发送失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="邮件发送失败，请稍后重试或联系管理员",
        )

    await verification_service.start_cooldown(email)
    return {"sent": True, "expires_in": verification_service.VC_TTL_SECONDS}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser | None = Depends(get_optional_current_user),
):
    """用户注册。

    权限策略（防任意提权，免码依据只看 token 里的角色、不看请求体字段）：
    - 系统首个用户（users 表为空）：bootstrap 初始化为 admin（默认），免验证码
      ——新机器 SMTP 往往还没配，首管理员不能被邮件卡死。
    - 已登录 admin 调用：可建任意角色账号，免验证码，归属 admin 的租户。
    - 其余一律自助注册：必须通过邮箱验证码，角色固定 reviewer，独立新租户
      （卷宗按租户隔离，注册者之间互不可见）。
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库不可用",
        )

    email = request.email.strip().lower()
    user_count = (await db.execute(select(func.count(UserRecord.id)))).scalar() or 0
    requested_role = (request.role or "").lower()
    is_bootstrap = user_count == 0
    is_admin = current is not None and current.role == "admin"

    if is_bootstrap:
        role = requested_role if requested_role in _VALID_ROLES else "admin"
        tenant_id = str(uuid.uuid4())
    elif is_admin:
        role = requested_role if requested_role in _VALID_ROLES else "viewer"
        tenant_id = current.tenant_id or str(uuid.uuid4())
    elif requested_role in _ELEVATED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="创建 admin/reviewer 账号需要管理员权限；自助注册默认获得 reviewer 角色",
        )
    else:
        try:
            await verification_service.consume_code(email, request.code)
        except verification_service.VerificationError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        role = "reviewer"
        tenant_id = str(uuid.uuid4())

    stmt = select(UserRecord).where(UserRecord.username == request.username)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    stmt = select(UserRecord).where(UserRecord.email == email)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已被注册")

    user = UserRecord(
        tenant_id=tenant_id,
        username=request.username,
        email=email,
        hashed_password=hash_password(request.password),
        role=role,
    )
    db.add(user)
    await db.flush()

    return UserResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录，返回 JWT Token。"""
    if db is None:
        # 无数据库时的内置账号仅用于本地开发，需显式 DEV_MEMORY_LOGIN=true 开启
        if settings.DEV_MEMORY_LOGIN and request.username == "admin" and request.password == "admin123":
            token = create_access_token(
                subject="admin-001",
                role="admin",
                tenant_id="tenant-001",
            )
            return TokenResponse(
                access_token=token,
                expires_in=settings.JWT_EXPIRE_MINUTES * 60,
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库不可用，且未开启开发内置登录（DEV_MEMORY_LOGIN）",
        )

    # 双通道：先按用户名查，未命中再按邮箱（小写匹配）。
    # 顺序两段查询而非 or_ 一把梭——防"某人用户名恰等于他人邮箱"时多行命中抛错。
    identifier = request.username.strip()
    stmt = select(UserRecord).where(UserRecord.username == identifier)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None and "@" in identifier:
        stmt = select(UserRecord).where(UserRecord.email == identifier.lower())
        user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名/邮箱或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    token = create_access_token(
        subject=user.id,
        role=user.role,
        tenant_id=user.tenant_id,
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
):
    """获取当前用户信息。"""
    if not credentials:
        if settings.DEV_MEMORY_LOGIN:
            return UserResponse(
                id="admin-001",
                tenant_id="tenant-001",
                username="admin",
                email="admin@example.com",
                role="admin",
                is_active=True,
            )
        raise HTTPException(status_code=401, detail="未提供认证凭据")

    from ..auth.security import decode_access_token
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="无效Token")

    user_id = payload.get("sub")

    if db is None:
        return UserResponse(
            id=user_id,
            tenant_id=payload.get("tenant_id", ""),
            username=payload.get("username", "admin"),
            email=f"{payload.get('username', 'admin')}@example.com",
            role=payload.get("role", "viewer"),
            is_active=True,
        )

    stmt = select(UserRecord).where(UserRecord.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return UserResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
    )
