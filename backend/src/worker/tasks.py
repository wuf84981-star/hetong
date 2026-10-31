"""Celery 任务定义 — 合同审查异步任务（持久、可重试、可续跑）。

设计要点：
- review_id 固定，save_review 为 upsert 语义 → 任务天然幂等，acks_late + 重试安全。
- Worker 进程独立初始化 DB / checkpointer，与 Web 进程共享同一 PostgreSQL 和
  同一 Redis checkpoint 后端，因此人机协同的中断态可在 Web 进程 resume。
- 失败重试用尽后，把审查状态标记为 failed 落库，前端可见并可触发 rerun。
"""

from __future__ import annotations

import asyncio
import logging

from .app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="worker.run_review",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    task_reject_on_worker_lost=True,
)
def run_review_task(
    self,
    review_id: str,
    raw_text: str = "",
    document_path: str = "",
    original_filename: str = "",
    position: str = "neutral",
    with_human_review: bool = True,
    tenant_id: str = "",
    user_id: str = "",
) -> dict:
    """异步执行审查流水线并持久化结果。

    返回: {"review_id": str, "status": str, "error": str | None}
    """
    logger.info("开始异步审查 review_id=%s retries=%d", review_id, self.request.retries)
    try:
        status = asyncio.run(
            _arun_review(
                review_id=review_id,
                raw_text=raw_text,
                document_path=document_path,
                original_filename=original_filename,
                position=position,
                with_human_review=with_human_review,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        )
        logger.info("异步审查完成 review_id=%s status=%s", review_id, status)
        return {"review_id": review_id, "status": status, "error": None}
    except Exception as exc:
        logger.error("异步审查失败 review_id=%s: %s", review_id, exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        # 重试用尽：标记 failed 落库
        try:
            asyncio.run(_mark_failed(review_id, tenant_id, str(exc)))
        except Exception:
            logger.exception("标记 failed 状态失败 review_id=%s", review_id)
        return {"review_id": review_id, "status": "failed", "error": str(exc)}


async def _arun_review(
    review_id: str,
    raw_text: str,
    document_path: str,
    original_filename: str,
    with_human_review: bool,
    tenant_id: str,
    user_id: str,
    position: str = "neutral",
) -> str:
    from ..config import settings
    from ..db import session as db_session
    from ..db.models import Base
    from ..api.dependencies.storage import MemoryStore
    from ..pipeline.checkpointer import close_checkpointer, init_checkpointer
    from ..pipeline.state import ContractReviewState, ReviewStatus
    from ..services.review_service import ReviewService
    from ..services.storage_service import StorageService

    db_session.init_db(settings.DATABASE_URL)
    async with db_session.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await init_checkpointer()

    try:
        async with db_session.async_session_factory() as session:
            storage = StorageService(db=session, memory=MemoryStore(), tenant_id=tenant_id)
            svc = ReviewService(storage)
            svc._user_id = user_id
            initial_state = ContractReviewState(
                review_id=review_id,
                raw_text=raw_text,
                document_path=document_path,
                original_filename=original_filename,
                position=position,
                status=ReviewStatus.PENDING,
            )
            state = await svc._run_pipeline_with_progress(
                review_id=review_id,
                initial_state=initial_state,
                with_human_review=with_human_review,
                user_id=user_id,
            )
            return state.status.value
    finally:
        await close_checkpointer()
        await db_session.close_db()


async def _mark_failed(review_id: str, tenant_id: str, error: str) -> None:
    from ..config import settings
    from ..db import session as db_session
    from ..db.crud import get_review, save_review
    from ..pipeline.state import ReviewStatus

    if db_session.async_session_factory is None:
        db_session.init_db(settings.DATABASE_URL)
    async with db_session.async_session_factory() as session:
        async with session.begin():
            state = await get_review(session, review_id, tenant_id=tenant_id)
            if state is None:
                return
            state.status = ReviewStatus.COMPLETED
            if f"pipeline: {error}" not in state.errors:
                state.errors.append(f"pipeline: {error}")
            await save_review(session, state, tenant_id=tenant_id)
