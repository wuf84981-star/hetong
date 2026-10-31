"""邮件发送 — 注册验证码。stdlib smtplib，零新依赖。

配置口径：SMTP_HOST/SMTP_USER/SMTP_PASSWORD 缺一即视为未配置（抛
SMTPNotConfiguredError，路由映射 503）；SMTP_FROM 留空退回 SMTP_USER。
QQ/163 等服务商的"授权码"填 SMTP_PASSWORD，不是邮箱登录密码。
"""

from __future__ import annotations

import asyncio
import logging
from email.message import EmailMessage

from ..config import settings

logger = logging.getLogger(__name__)


class SMTPNotConfiguredError(Exception):
    """SMTP 配置不完整——发码端点映射 503。"""


def _send_sync(msg: EmailMessage) -> None:
    """同步 SMTP 发送（由 to_thread 在线程池调用，勿在事件循环里直接跑）。

    465 端口走隐式 SSL（QQ/163 的标准配置）；其余端口明文连接后 starttls。
    """
    import smtplib

    if settings.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as client:
            client.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            client.send_message(msg)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as client:
            client.starttls()
            client.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            client.send_message(msg)


async def send_verification_code(to: str, code: str) -> None:
    """发送注册验证码邮件。

    SMTPException（鉴权失败/网络不通等）原样上抛，由调用方回滚验证码并映射 502。
    """
    if not (settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD):
        raise SMTPNotConfiguredError("邮件服务未配置（需 SMTP_HOST / SMTP_USER / SMTP_PASSWORD）")

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to
    msg["Subject"] = "分寸合同 · 注册验证码"
    msg.set_content(
        f"您的注册验证码：{code}\n\n"
        "验证码 5 分钟内有效；请输入到注册页面的「邮箱验证码」一栏。\n"
        "若非本人操作，请忽略本邮件。\n"
    )
    await asyncio.to_thread(_send_sync, msg)
    logger.info("注册验证码已发往 %s", to.split("@")[0] + "@***")
