"""注册验证码的签发与核销 — 建在 cache.py 双后端之上，带探测兜底。

三条设计约束（改动前请读懂）：
1. value 存**绝对 deadline 时间戳**，错一次重设 attempts 时用剩余 TTL——
   cache.set 每次重写都会重置整个 TTL，天真写法会让验证码被错试无限续命；
2. value 只用 JSON-safe 类型（str/int/float）——RedisCache 走 json 往返、
   MemoryCache 存对象原样，datetime 混进去会两边类型漂移；验证码必须 str
   （int 会吞前导零，f"{randbelow(1e6):06d}" 生成的就是字符串）；
3. cache.get_cache() 的内存降级是死代码（aioredis.from_url 懒连接、永不抛），
   Redis 实际不可用时其写操作静默失败——本模块首次取缓存时做一次"写入+回读"
   探测，探活失败退回进程内 MemoryCache。兜底后多副本部署会跨 pod 失效，
   生产须保 Redis 可用（探活失败时有 warning 日志）。
"""

from __future__ import annotations

import logging
import secrets
import time

from ..cache import MemoryCache, get_cache

logger = logging.getLogger(__name__)

# 时效参数：不做配置项（YAGNI），要改直接改这三个常量
VC_TTL_SECONDS = 300
COOLDOWN_SECONDS = 60
MAX_ATTEMPTS = 5


class VerificationError(Exception):
    """核销失败（路由映射 400，detail 即可展示文案）。"""


# 模块级缓存实例（一次性探测）。测试直接 monkeypatch 本模块 _vc_cache 注入假缓存。
_vc_cache = None


async def _cache():
    global _vc_cache
    if _vc_cache is None:
        c = get_cache()
        try:
            await c.set("vc:probe", 1, ttl=5)
            alive = (await c.get("vc:probe")) == 1
        except Exception:
            alive = False
        if alive:
            _vc_cache = c
        else:
            _vc_cache = MemoryCache()
            logger.warning(
                "缓存后端探测失败，验证码退回进程内存——单副本部署可用；"
                "多副本部署请修复 Redis，否则验证码跨 pod 失效"
            )
    return _vc_cache


def _vc_key(email: str) -> str:
    return f"vc:register:{email}"


def _cd_key(email: str) -> str:
    return f"vc:cooldown:{email}"


async def issue_code(email: str) -> str:
    """生成并写入 6 位验证码（含绝对 deadline），返回码明文供发信。"""
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = time.time()
    cache = await _cache()
    await cache.set(
        _vc_key(email),
        {"code": code, "attempts": 0, "deadline": now + VC_TTL_SECONDS},
        ttl=VC_TTL_SECONDS,
    )
    return code


async def revoke_code(email: str) -> None:
    """发信失败时回滚刚写入的验证码（失败不该占用一个码位，用户可立即重发）。"""
    cache = await _cache()
    await cache.delete(_vc_key(email))


async def consume_code(email: str, input_code: str) -> None:
    """核销验证码：通过则删键放行，失败抛 VerificationError（文案可直接给用户）。

    错一次 attempts+1 并以剩余 TTL 重设——绝不允许错误尝试延长有效期。
    """
    cache = await _cache()
    key = _vc_key(email)
    data = await cache.get(key)
    if not isinstance(data, dict):
        raise VerificationError("验证码未发送或已过期，请先点击「发送验证码」")

    now = time.time()
    if now > float(data.get("deadline", 0)):
        await cache.delete(key)
        raise VerificationError("验证码已过期，请重新发送")
    if int(data.get("attempts", 0)) >= MAX_ATTEMPTS:
        await cache.delete(key)
        raise VerificationError("验证码错误次数过多已作废，请重新发送")

    if str(data.get("code", "")) != input_code.strip():
        remaining = max(1, int(float(data["deadline"]) - now))
        await cache.set(
            key,
            {**data, "attempts": int(data.get("attempts", 0)) + 1},
            ttl=remaining,
        )
        raise VerificationError("验证码错误")

    await cache.delete(key)


async def cooldown_remaining(email: str) -> int:
    """距下次可发送的剩余秒数；0 表示可发。"""
    cache = await _cache()
    item = await cache.get(_cd_key(email))
    if not isinstance(item, dict):
        return 0
    return max(0, int(COOLDOWN_SECONDS - (time.time() - float(item.get("sent_at", 0)))))


async def start_cooldown(email: str) -> None:
    """仅在发信成功后调用——失败的发送不该让用户干等 60 秒。"""
    cache = await _cache()
    await cache.set(_cd_key(email), {"sent_at": time.time()}, ttl=COOLDOWN_SECONDS)
