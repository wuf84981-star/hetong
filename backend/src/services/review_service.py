"""审查服务 — 合同审查的核心业务逻辑编排。

人机协同（P0）：
- 启用 with_human_review 时，流水线编译时带 checkpointer + interrupt_before=["human_review"]。
- 首次执行 ainvoke 到 suggestion 后，若为高风险会在进入 human_review **之前**中断；
  服务检测到中断（aget_state().next 含 human_review）后把状态置为 AWAITING_HUMAN 并持久化。
- 人工反馈通过 submit_feedback -> aupdate_state(注入 human_feedback) + ainvoke(None) 真正 resume，
  由 process_feedback 应用反馈后走到 complete。
- checkpointer 为进程级持久实例（redis/sqlite/memory），保证中断态跨请求/跨进程可恢复。

异步任务后端（P0）：
- TASK_BACKEND=celery：投递到 Celery（Redis broker），任务持久、可重试、进程重启可续跑。
- TASK_BACKEND=inprocess：asyncio.create_task（仅开发/单机，重启即丢）。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path

from ..config import settings
from ..pipeline.checkpointer import get_checkpointer, init_checkpointer
from ..pipeline.graph import (
    create_review_pipeline,
    graph_is_awaiting_human,
    set_progress_callback,
)
from ..pipeline.state import (
    ContractReviewState,
    HumanFeedback,
    ReviewStatus,
)
from ..tracing import get_tracer
from .storage_service import StorageService
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}

# 批量审查配置
BATCH_MAX_FILES = 10
BATCH_MAX_CONCURRENT = 3

# 防止 asyncio.create_task 的任务被 GC（仅 inprocess 后端）
_BACKGROUND_TASKS: set[asyncio.Task] = set()

# 进程内共享的 RAG 检索器（懒加载；知识库上传/删除后可强制重建）
_RAG_RETRIEVER = None
_RAG_INIT_TRIED = False
_RAG_LOCK = threading.Lock()


def _build_rag_retriever():
    """从向量库重建检索器，返回 (retriever, 向量数)；集合为空时 retriever 为 None。

    失败时向上抛异常，由调用方决定回退策略。
    """
    from ..vector.embeddings import create_embedding_model
    from ..vector.milvus_store import MilvusStore
    from ..vector.rag import RAGRetriever

    model = create_embedding_model()  # 按 EMBEDDING_SOURCE 选本地/远程，与知识库写路径同源
    store = MilvusStore(embedding_model=model)
    if store.load():
        return RAGRetriever(store=store), store.size
    return None, 0


def _load_rag_retriever():
    """按 RAG_ENABLED 懒加载共享 RAG 检索器；失败返回 None（普通模式）。"""
    global _RAG_RETRIEVER, _RAG_INIT_TRIED
    if not settings.RAG_ENABLED:
        return None
    if _RAG_INIT_TRIED:
        return _RAG_RETRIEVER
    _RAG_INIT_TRIED = True
    try:
        retriever, size = _build_rag_retriever()
        if retriever is not None:
            _RAG_RETRIEVER = retriever
            logger.info("RAG 已启用，索引包含 %d 条记录", size)
        else:
            logger.warning("RAG_ENABLED=true 但未找到向量索引，回退为普通模式。"
                           "可先运行 scripts/build_index.py 建样例索引，"
                           "或在「知识库」页上传法规条例。")
    except Exception as e:
        logger.error("RAG 初始化失败，回退为普通模式: %s", e)
    return _RAG_RETRIEVER


def reload_rag_retriever() -> dict:
    """知识库写入（上传/软删）后重建进程内检索器单例。

    与懒加载不同：失败会重置 _RAG_INIT_TRIED 允许下次审查再试——
    知识库刚写完，一次瞬时故障不该把本进程检索永久禁用。
    锁防并发写路径的交错重建；返回 {"ready","size","reason"} 供状态展示。
    """
    global _RAG_RETRIEVER, _RAG_INIT_TRIED
    with _RAG_LOCK:
        _RAG_RETRIEVER = None
        _RAG_INIT_TRIED = settings.RAG_ENABLED
        if not settings.RAG_ENABLED:
            return {"ready": False, "size": 0, "reason": "rag_disabled"}
        try:
            retriever, size = _build_rag_retriever()
        except Exception as e:
            logger.error("RAG 热重载失败: %s", e)
            return {"ready": False, "size": 0, "reason": str(e)}
        if retriever is None:
            return {"ready": False, "size": 0, "reason": "index_missing"}
        _RAG_RETRIEVER = retriever
        logger.info("RAG 热重载完成，索引包含 %d 条记录", size)
        return {"ready": True, "size": size, "reason": ""}


class ReviewService:
    """审查服务：编排流水线执行、存储、反馈处理。"""

    def __init__(self, storage: StorageService) -> None:
        self._storage = storage
        self._tenant_id = storage._tenant_id
        self._user_id = ""  # 由调用方在需要时设置
        self._memory = storage._memory

    # ── 任务分发（inprocess / celery）─────────────────────────

    def _dispatch(
        self,
        review_id: str,
        initial_state: ContractReviewState,
        with_human_review: bool,
        user_id: str,
    ) -> None:
        """按 TASK_BACKEND 分发后台流水线执行。"""
        if settings.TASK_BACKEND == "celery":
            # 投递到 Celery（持久、可重试、可续跑）
            from ..worker.tasks import run_review_task

            run_review_task.delay(
                review_id=review_id,
                raw_text=initial_state.raw_text,
                document_path=initial_state.document_path,
                original_filename=initial_state.original_filename,
                position=initial_state.position,
                with_human_review=with_human_review,
                tenant_id=self._tenant_id,
                user_id=user_id,
            )
            logger.info("已投递 Celery 审查任务 review_id=%s", review_id)
            return

        task = asyncio.create_task(
            self._run_pipeline_with_progress(
                review_id=review_id,
                initial_state=initial_state,
                with_human_review=with_human_review,
                user_id=user_id,
            )
        )
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)

    # ── 创建审查（异步提交，立即返回 review_id）───────────────

    async def start_from_text(
        self,
        text: str,
        with_human_review: bool = True,
        user_id: str = "",
        position: str = "neutral",
    ) -> str:
        review_id = str(uuid.uuid4())
        # P0-4: 写入 uploads 目录而非塞进 state
        file_path = UPLOAD_DIR / f"{review_id}.txt"
        file_path.write_text(text, encoding="utf-8")

        initial_state = ContractReviewState(
            review_id=review_id,
            raw_text="",  # 不再写,改用 path
            raw_text_path=str(file_path),  # P0-4 新字段
            position=position,
            status=ReviewStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        await self._persist_state(initial_state, user_id=user_id or self._user_id)
        self._dispatch(review_id, initial_state, with_human_review, user_id or self._user_id)
        return review_id

    async def start_from_file(
        self,
        filename: str,
        content: bytes,
        with_human_review: bool = True,
        user_id: str = "",
        position: str = "neutral",
    ) -> str:
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {ext}")

        file_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{file_id}{ext}"
        file_path.write_bytes(content)

        review_id = str(uuid.uuid4())
        initial_state = ContractReviewState(
            review_id=review_id,
            document_path=str(file_path),
            raw_text_path=str(file_path),  # P0-4: 同时记文件路径
            original_filename=filename,
            position=position,
            status=ReviewStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        await self._persist_state(initial_state, user_id=user_id or self._user_id)
        self._dispatch(review_id, initial_state, with_human_review, user_id or self._user_id)
        return review_id

    # ── 创建审查（同步等待完整结果）─────────────────────────────

    async def create_from_text(
        self,
        text: str,
        with_human_review: bool = True,
        position: str = "neutral",
    ) -> ContractReviewState:
        review_id = await self.start_from_text(
            text, with_human_review=with_human_review, position=position
        )
        return await self._wait_for_review(review_id)

    async def create_from_file(
        self,
        filename: str,
        content: bytes,
        with_human_review: bool = True,
        position: str = "neutral",
    ) -> ContractReviewState:
        review_id = await self.start_from_file(
            filename, content, with_human_review=with_human_review, position=position
        )
        return await self._wait_for_review(review_id)

    async def _wait_for_review(
        self, review_id: str, poll_interval: float = 0.3, timeout: float = 300.0
    ) -> ContractReviewState:
        """等待后台审查任务达到终态或 AWAITING_HUMAN。"""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            state = await self._load_state_detached(review_id)
            if state is None:
                raise RuntimeError(f"审查记录丢失: {review_id}")
            if state.status in (
                ReviewStatus.COMPLETED,
                ReviewStatus.APPROVED,
                ReviewStatus.REJECTED,
                ReviewStatus.AWAITING_HUMAN,
            ):
                return state
            last_error_step = next((e for e in reversed(state.step_log) if e.status == "error"), None)
            if last_error_step is not None and state.current_step == "":
                await asyncio.sleep(poll_interval)
                return await self._load_state_detached(review_id) or state
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(f"审查超时: {review_id}")
            await asyncio.sleep(poll_interval)

    # ── 查询审查 ──────────────────────────────────────────────

    async def get(self, review_id: str) -> ContractReviewState | None:
        return await self._storage.load(review_id)

    async def list(self, offset: int = 0, limit: int = 20) -> list[dict]:
        return await self._storage.list_reviews(offset=offset, limit=limit)

    async def count(self) -> int:
        return await self._storage.count_reviews()

    # ── 人工反馈（真正 resume 流水线）──────────────────────────

    async def submit_feedback(
        self,
        review_id: str,
        reviewer: str,
        decision: str,
        comments: str = "",
        modified_suggestions: list | None = None,
        bad_clauses: list[str] | None = None,
        missed_clauses: list[str] | None = None,
        industry: str = "",                # v2
        contract_type_hint: str = "",      # v2
    ) -> ReviewStatus:
        """提交人工审核反馈，从中断点 resume 流水线，返回最终状态。"""
        state = await self._storage.load(review_id)
        if state is None:
            raise ValueError(f"审查记录不存在: {review_id}")

        if state.status != ReviewStatus.AWAITING_HUMAN:
            raise ValueError(
                f"审查 {review_id} 当前状态为 {state.status.value}，不处于待人工审核状态"
            )

        feedback = HumanFeedback(
            reviewer=reviewer,
            decision=decision,
            comments=comments,
            modified_suggestions=modified_suggestions or [],
            timestamp=datetime.now(),
        )

        checkpointer = await self._ensure_checkpointer()
        config = {"configurable": {"thread_id": review_id}}
        pipeline = create_review_pipeline(
            with_human_review=True,
            checkpointer=checkpointer,
            rag_retriever=_load_rag_retriever(),
        )

        # 校验该 thread 确实暂停在 human_review 中断点（跨进程恢复的前提是共享 checkpointer）
        snapshot = await pipeline.aget_state(config)
        if not graph_is_awaiting_human(snapshot):
            raise ValueError(
                f"未找到 {review_id} 的中断点。请确认 CHECKPOINT_BACKEND 为 redis/sqlite "
                "且该 thread 的 checkpoint 未过期（memory 后端无法跨进程/重启恢复）。"
            )

        # 注入反馈并从中断点恢复执行
        await pipeline.aupdate_state(config, {"human_feedback": feedback})
        result = await pipeline.ainvoke(None, config=config)
        final_state = self._coerce_state(result)
        final_state.updated_at = datetime.now()
        await self._persist_state(final_state, user_id=self._user_id)
        logger.info("人工反馈已处理并 resume review_id=%s status=%s",
                    review_id, final_state.status.value)

        # P1-3: 沉淀经验到跨会话记忆库（失败不应阻塞主流程返回）
        try:
            from ..memory_service import MemoryService

            memory = MemoryService(tenant_id=self._tenant_id)
            memory.record_outcome(
                review_id=review_id,
                decision=decision,
                comments=comments,
                high_risk_clauses=[
                    f.clause_id
                    for f in final_state.risk_findings
                    if f.risk_level.value == "high"
                ],
                bad_clauses=bad_clauses,
                missed_clauses=missed_clauses,
            )
        except Exception:
            logger.exception("MemoryService.record_outcome 失败 review_id=%s", review_id)

        # v2: 如果是 reject/modify 且有颗粒度反馈,创建 StructuredBadCase
        if decision in ("reject", "modify") and (bad_clauses or missed_clauses):
            try:
                from .bad_case_repo import BadCaseRepository
                from ..models.structured_bad_case import (
                    StructuredBadCase, IdentifiedRisk, auto_extract_keywords,
                )

                repo = BadCaseRepository()
                bc = StructuredBadCase(
                    review_id=review_id,
                    contract_type=contract_type_hint or state.contract_type,
                    industry=industry,
                    identified_risks=[
                        *[
                            IdentifiedRisk(
                                clause_id=cid, risk_type="identified_incorrectly",
                                severity="high", description=comments[:200],
                            )
                            for cid in (bad_clauses or [])
                        ],
                        *[
                            IdentifiedRisk(
                                clause_id=cid, risk_type="missed_by_llm",
                                severity="high", description=comments[:200],
                            )
                            for cid in (missed_clauses or [])
                        ],
                    ],
                    problematic_clauses_summary=comments,
                    suggestion_or_lesson=comments,
                    full_contract_text=state.raw_text or "",
                    input_summary=(state.raw_text or "")[:500],
                    keywords_for_retrieval=auto_extract_keywords(
                        (state.raw_text or "") + " " + comments
                    ),
                    signal_type="human_reject" if decision == "reject" else "human_modify",
                    severity="high",
                )
                await repo.save(bc)
            except Exception:
                logger.exception("StructuredBadCase 创建失败 review_id=%s", review_id)

        return final_state.status

    # ── 删除与重跑 ──────────────────────────────────────────────

    async def delete(self, review_id: str) -> bool:
        return await self._storage.delete(review_id)

    async def rerun(
        self,
        review_id: str,
        with_human_review: bool = True,
        async_mode: bool = False,
        user_id: str = "",
    ) -> ContractReviewState | str:
        old = await self._storage.load(review_id)
        if old is None:
            raise ValueError(f"审查记录不存在: {review_id}")

        new_id = str(uuid.uuid4())
        initial_state = ContractReviewState(
            review_id=new_id,
            raw_text=old.raw_text,
            raw_text_path=old.raw_text_path,  # P0-4: 同步保留文件路径
            document_path=old.document_path,
            original_filename=old.original_filename,
            position=old.position,  # 重跑沿用原卷宗立场
            status=ReviewStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        await self._persist_state(initial_state, user_id=user_id or self._user_id)
        self._dispatch(new_id, initial_state, with_human_review, user_id or self._user_id)

        if async_mode:
            return new_id
        return await self._wait_for_review(new_id)

    # ── 批量审查 ──────────────────────────────────────────────

    async def create_batch(
        self,
        files: list[tuple[str, bytes]],
        with_human_review: bool = True,
        position: str = "neutral",
    ) -> tuple[str, list[dict]]:
        if len(files) > BATCH_MAX_FILES:
            raise ValueError(f"单次最多上传 {BATCH_MAX_FILES} 个文件")

        batch_id = str(uuid.uuid4())[:12]
        items: list[dict] = []
        review_ids = []
        for filename, content in files:
            ext = Path(filename).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                items.append({"review_id": "", "filename": filename, "status": "failed",
                              "error": f"不支持的文件格式: {ext}"})
                continue
            file_id = str(uuid.uuid4())
            file_path = UPLOAD_DIR / f"{file_id}{ext}"
            file_path.write_bytes(content)
            rid = str(uuid.uuid4())
            review_ids.append((rid, str(file_path), filename))
            items.append({"review_id": rid, "filename": filename, "status": "pending", "error": ""})

        semaphore = asyncio.Semaphore(BATCH_MAX_CONCURRENT)
        checkpointer = await self._ensure_checkpointer() if with_human_review else None

        async def _process_one(rid: str, fpath: str, fname: str, idx: int):
            async with semaphore:
                try:
                    initial_state = ContractReviewState(
                        review_id=rid, document_path=fpath, original_filename=fname,
                        position=position,
                        status=ReviewStatus.PENDING,
                    )
                    state = await self._run_pipeline_core(
                        rid, initial_state, with_human_review, checkpointer
                    )
                    await self._persist_state(state, user_id=self._user_id)
                    items[idx]["status"] = state.status.value
                    items[idx]["review_id"] = rid
                except Exception as e:
                    logger.error("批量审查失败 file=%s: %s", fname, e)
                    items[idx]["status"] = "failed"
                    items[idx]["error"] = str(e)

        await asyncio.gather(*[
            _process_one(rid, fpath, fname, i)
            for i, (rid, fpath, fname) in enumerate(review_ids)
        ])
        return batch_id, items

    async def get_batch_status(self, batch_id: str) -> dict | None:
        return None

    # ── 内部：执行流水线 ──────────────────────────────────────

    async def _ensure_checkpointer(self):
        cp = get_checkpointer()
        if cp is None:
            cp = await init_checkpointer()
        return cp

    @staticmethod
    def _coerce_state(result) -> ContractReviewState:
        if isinstance(result, ContractReviewState):
            return result
        if isinstance(result, dict):
            return ContractReviewState(**result)
        return ContractReviewState.model_validate(result)

    @staticmethod
    def _resolve_status(decision: str) -> ReviewStatus:
        """把人工决策字符串映射为 ReviewStatus。

        - approve -> APPROVED
        - reject  -> REJECTED
        - modify / 其他未知值 -> COMPLETED（视为带修改意见通过）
        """
        if not decision:
            return ReviewStatus.COMPLETED
        normalized = str(decision).strip().lower()
        if normalized == "approve":
            return ReviewStatus.APPROVED
        if normalized == "reject":
            return ReviewStatus.REJECTED
        return ReviewStatus.COMPLETED

    async def _run_pipeline_core(
        self,
        review_id: str,
        initial_state: ContractReviewState,
        with_human_review: bool,
        checkpointer,
    ) -> ContractReviewState:
        """执行一次流水线；若在 human_review 前中断则返回 AWAITING_HUMAN 状态。"""
        pipeline = create_review_pipeline(
            with_human_review=with_human_review,
            checkpointer=checkpointer,
            rag_retriever=_load_rag_retriever(),
        )
        config = {"configurable": {"thread_id": review_id}}
        initial_state.status = ReviewStatus.IN_PROGRESS
        result = await pipeline.ainvoke(initial_state.model_dump(), config=config)
        state = self._coerce_state(result)

        if with_human_review and checkpointer is not None:
            snapshot = await pipeline.aget_state(config)
            if graph_is_awaiting_human(snapshot):
                state.status = ReviewStatus.AWAITING_HUMAN
                state.needs_human_review = True
        return state

    async def _run_pipeline_with_progress(
        self,
        review_id: str,
        initial_state: ContractReviewState,
        with_human_review: bool,
        user_id: str = "",
    ) -> ContractReviewState:
        """后台执行流水线，每步持久化进度；支持人机协同中断。"""
        tracer = get_tracer()
        with tracer.start_as_current_span("review_pipeline", attributes={
            "review_id": review_id,
            "tenant_id": self._tenant_id,
            "user_id": user_id,
            "with_human_review": with_human_review,
        }) as span:
            try:
                async def _on_progress(state: ContractReviewState) -> None:
                    state.updated_at = datetime.now()
                    await self._persist_state(state, user_id=user_id)

                set_progress_callback(review_id, _on_progress)
                try:
                    checkpointer = await self._ensure_checkpointer() if with_human_review else None
                    initial_state.status = ReviewStatus.IN_PROGRESS
                    initial_state.updated_at = datetime.now()
                    await self._persist_state(initial_state, user_id=user_id)

                    final_state = await self._run_pipeline_core(
                        review_id, initial_state, with_human_review, checkpointer
                    )
                    final_state.updated_at = datetime.now()
                    await self._persist_state(final_state, user_id=user_id)
                    logger.info("审查完成 review_id=%s status=%s progress=%.0f%%",
                                review_id, final_state.status.value, final_state.progress * 100)

                    # P1-7: BadCaseDetector — 反向信号落库(高危/严重)
                    try:
                        from .bad_case_detector import BadCaseDetector

                        detector = BadCaseDetector()
                        signals = detector.check(final_state)

                        if any(s.severity in ("high", "critical") for s in signals):
                            from .bad_case_repo import BadCaseRepository
                            from ..models.bad_case import BadCase

                            repo = BadCaseRepository()
                            for sig in signals:
                                if sig.severity in ("high", "critical"):
                                    await repo.save(BadCase(
                                        review_id=review_id,
                                        tenant_id=self._tenant_id,
                                        signal_type=sig.type,
                                        severity=sig.severity,
                                        input_summary=(final_state.raw_text or "")[:500],
                                        state_warnings=list(final_state.warnings),
                                        state_degraded_steps=list(final_state.degraded_steps),
                                    ))
                    except Exception:
                        logger.exception("BadCaseDetector 集成失败")

                    # 异步跑 judge(采样,不阻塞主流程)
                    try:
                        from .production_judge import ProductionJudgeRunner

                        judge = ProductionJudgeRunner(sample_rate=0.05)
                        asyncio.create_task(judge.judge_if_sampled(final_state))
                    except Exception:
                        logger.exception("ProductionJudgeRunner 启动失败")

                    # P1-8: SignatureService 分层抽样签名(Good Case 沉淀)
                    try:
                        from .signature_service import SignatureService

                        SignatureService().maybe_record(final_state)
                    except Exception:
                        logger.exception("SignatureService.maybe_record 失败")

                    # P1-1: 记录完整状态到 span
                    span.set_attribute("status", final_state.status.value)
                    span.set_attribute("degraded_steps", ",".join(final_state.degraded_steps))
                    span.set_attribute("warnings_count", len(final_state.warnings))

                    return final_state
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR))
                    try:
                        current = await self._storage.load(review_id)
                        if current is not None:
                            err_msg = f"pipeline: {e}"
                            if err_msg not in current.errors:
                                current.errors.append(err_msg)
                            current.status = ReviewStatus.COMPLETED
                            current.updated_at = datetime.now()
                            await self._persist_state(current, user_id=user_id)
                    except Exception:
                        logger.exception("持久化错误状态失败")
                    raise
                finally:
                    set_progress_callback(review_id, None)
            except Exception:
                # 如果连 span 都异常,再 set_status 一次
                span.set_status(Status(StatusCode.ERROR))
                raise

    async def _load_state_detached(self, review_id: str) -> ContractReviewState | None:
        """绕开请求级 session，每次用新 session/memory 读取最新状态（用于轮询）。"""
        if not self._storage.is_persistent:
            data = self._memory.get(review_id)
            return ContractReviewState(**data) if data else None
        from ..db.session import async_session_factory
        from ..db.crud import get_review as crud_get
        if async_session_factory is None:
            data = self._memory.get(review_id)
            return ContractReviewState(**data) if data else None
        async with async_session_factory() as session:
            return await crud_get(session, review_id, tenant_id=self._tenant_id)

    async def _persist_state(self, state: ContractReviewState, user_id: str = "") -> None:
        """把 state 持久化到存储（DB 模式每次开短事务；内存模式写共享 MemoryStore）。"""
        try:
            if not self._storage.is_persistent:
                self._memory.set(state.review_id, state.model_dump(mode="json"))
                return
            from ..db.session import async_session_factory
            from ..db.crud import save_review as crud_save
            if async_session_factory is None:
                self._memory.set(state.review_id, state.model_dump(mode="json"))
                return
            async with async_session_factory() as session:
                async with session.begin():
                    await crud_save(
                        session, state,
                        tenant_id=self._tenant_id,
                        user_id=user_id or self._user_id,
                    )
        except Exception:
            logger.exception("后台持久化 state 失败 review_id=%s", state.review_id)
