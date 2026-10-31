"""LangGraph checkpoint 后端工厂 — 人机协同 interrupt/resume 的持久化基础。

背景：早期实现把 `MemorySaver()` 硬编码进流水线，这意味着：
  1. 中断态只存在于单个进程的内存里，进程重启即丢失；
  2. 多副本部署时 A 副本产生的中断态，B 副本读不到，resume 必然失败。

本模块提供一个「进程级共享、可持久化」的 checkpointer：
  - redis  : 跨进程 / 多副本持久（生产推荐，与系统已有 Redis 对齐）
  - sqlite : 单机文件持久（单节点部署够用）
  - memory : 仅单进程（开发，重启即丢，会打印告警）

生命周期由 FastAPI lifespan / Celery worker 启动时 `init_checkpointer()` 建立，
关闭时 `close_checkpointer()` 释放。`get_checkpointer()` 返回同一个实例，
确保「首次 ainvoke 到中断点」与「提交反馈后 resume」用的是同一份持久化存储。
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import settings

logger = logging.getLogger(__name__)

# 进程级单例
_checkpointer: Any | None = None
# 对于以异步上下文管理器形式创建的 saver（redis/sqlite），需保留 CM 以便退出时关闭
_checkpointer_cm: Any | None = None
_backend_in_use: str = "memory"


def _build_memory():
    from langgraph.checkpoint.memory import MemorySaver

    logger.warning(
        "CHECKPOINT_BACKEND=memory：中断态仅存于当前进程内存，"
        "重启或多副本会导致 resume 失败。生产请使用 redis 或 sqlite。"
    )
    return MemorySaver(), None


async def _build_redis():
    """基于 Redis 的持久 checkpointer（需要 langgraph-checkpoint-redis）。"""
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver

    cm = AsyncRedisSaver.from_conn_string(settings.REDIS_URL)
    saver = await cm.__aenter__()
    # 首次使用需建立索引/键结构
    setup = getattr(saver, "asetup", None) or getattr(saver, "setup", None)
    if setup is not None:
        res = setup()
        if hasattr(res, "__await__"):
            await res
    logger.info("checkpoint 后端=redis (%s)", settings.REDIS_URL)
    return saver, cm


async def _build_sqlite():
    """基于本地 SQLite 文件的持久 checkpointer（需要 langgraph-checkpoint-sqlite）。"""
    from pathlib import Path

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    Path(settings.CHECKPOINT_SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
    cm = AsyncSqliteSaver.from_conn_string(settings.CHECKPOINT_SQLITE_PATH)
    saver = await cm.__aenter__()
    logger.info("checkpoint 后端=sqlite (%s)", settings.CHECKPOINT_SQLITE_PATH)
    return saver, cm


async def init_checkpointer() -> Any:
    """按配置初始化进程级 checkpointer。失败时降级为 memory 并告警。"""
    global _checkpointer, _checkpointer_cm, _backend_in_use

    if _checkpointer is not None:
        return _checkpointer

    backend = settings.CHECKPOINT_BACKEND
    try:
        if backend == "redis":
            _checkpointer, _checkpointer_cm = await _build_redis()
        elif backend == "sqlite":
            _checkpointer, _checkpointer_cm = await _build_sqlite()
        else:
            _checkpointer, _checkpointer_cm = _build_memory()
        _backend_in_use = backend
    except Exception as e:  # 包未安装 / 连接失败 → 降级为 memory，保证可用但打印告警
        logger.error(
            "初始化 checkpoint 后端 '%s' 失败（%s），降级为 memory。"
            "生产环境请安装并连通对应后端。",
            backend, e,
        )
        _checkpointer, _checkpointer_cm = _build_memory()
        _backend_in_use = "memory"

    return _checkpointer


def get_checkpointer() -> Any | None:
    """返回已初始化的 checkpointer（未初始化返回 None）。"""
    return _checkpointer


def backend_in_use() -> str:
    return _backend_in_use


async def close_checkpointer() -> None:
    global _checkpointer, _checkpointer_cm, _backend_in_use
    if _checkpointer_cm is not None:
        try:
            await _checkpointer_cm.__aexit__(None, None, None)
        except Exception:
            logger.exception("关闭 checkpoint 后端失败")
    _checkpointer = None
    _checkpointer_cm = None
    _backend_in_use = "memory"
