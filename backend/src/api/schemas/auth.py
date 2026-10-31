"""认证相关请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """用户注册请求。自助注册须带邮箱验证码；管理员建号免码。"""
    username: str = Field(description="用户名", min_length=3, max_length=50)
    email: EmailStr = Field(description="邮箱（验证码收件地址，全局唯一）")
    password: str = Field(description="密码", min_length=6)
    role: str = Field(default="", description="角色（仅管理员调用时生效；自助注册恒为 reviewer）")
    code: str = Field(default="", description="邮箱验证码（自助注册必填）")


class SendCodeRequest(BaseModel):
    """发送注册邮箱验证码。"""
    email: EmailStr = Field(description="收件邮箱")


class LoginRequest(BaseModel):
    """用户登录请求。username 可填用户名或注册邮箱。"""
    username: str = Field(description="用户名或邮箱")
    password: str = Field(description="密码")


class TokenResponse(BaseModel):
    """Token 响应。"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="过期时间（秒）")


class UserResponse(BaseModel):
    """用户信息响应。"""
    id: str
    tenant_id: str = ""
    username: str
    email: str
    role: str
    is_active: bool
