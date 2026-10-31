"""
LangGraph流水线编排 — 四Agent流水线 + 人机协同。

核心设计：
1. 使用LangGraph StateGraph构建有向图
2. 四个Agent节点顺序执行
3. 人机协同通过interrupt实现
4. 支持checkpoint持久化，可从任意步骤恢复
5. 条件路由：根据风险等级决定是否需要人工审核
6. 进度回调：每步开始/结束时通知外部，用于实时进度展示

面试亮点：
- LangGraph StateGraph vs MessageGraph 的区别
- interrupt/resume机制的实现原理
- checkpoint的序列化和反序列化
- 条件边(conditional edge)的使用场景
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Literal

from langgraph.graph import END, StateGraph

from ..agents.clause_extraction import ClauseExtractionAgent
from ..agents.risk_identification import RiskIdentificationAgent
from ..agents.compliance_check import ComplianceCheckAgent
from ..agents.suggestion import SuggestionAgent
from .state import (
    ContractReviewState,
    PIPELINE_STEPS,
    ReviewStatus,
    RiskLevel,
    STEP_LABELS,
    StepEvent,
)

logger = logging.getLogger(__name__)

# 按 review_id 注册的进度回调表（支持并发流水线互不干扰）。
# 签名：(state) -> Awaitable[None]
_progress_callbacks: dict[str, Callable[[ContractReviewState], Awaitable[None]]] = {}


def set_progress_callback(
    review_id: str,
    cb: Callable[[ContractReviewState], Awaitable[None]] | None,
) -> None:
    """注册/注销某个 review_id 的进度回调。"""
    if cb is None:
        _progress_callbacks.pop(review_id, None)
    else:
        _progress_callbacks[review_id] = cb


def _fire_progress(state: ContractReviewState) -> Awaitable[None] | None:
    cb = _progress_callbacks.get(state.review_id)
    if cb is not None:
        return cb(state)
    return None


def _now() -> datetime:
    return datetime.now()


def _step_message(state: ContractReviewState, step_key: str) -> str:
    """根据当前 state 生成步骤完成时的可读消息。"""
    if step_key == "clause_extraction":
        return f"提取了 {len(state.clauses)} 条条款"
    if step_key == "risk_identification":
        n = len(state.risk_findings)
        high = sum(1 for r in state.risk_findings if r.risk_level == RiskLevel.HIGH)
        return f"发现 {n} 个风险（高风险 {high} 个）"
    if step_key == "compliance_check":
        n = len(state.compliance_findings)
        m = len(state.missing_clauses)
        return f"合规检查完成，{n} 项不合规，缺失 {m} 项必备条款"
    if step_key == "suggestion":
        return f"生成了 {len(state.suggestions)} 条修改建议"
    return STEP_LABELS.get(step_key, step_key) + "完成"


def _with_progress(step_key: str, agent: Any) -> Callable[..., Awaitable[dict]]:
    """高阶函数：将 Agent 节点包一层进度事件记录。

    - 进入节点时：追加 running 事件，更新 current_step，触发回调。
    - 节点成功返回后：标记事件为 done，推进 progress，触发回调。
    - 异常时：标记事件为 error，追加到 state.errors，触发回调后重抛。
    """
    label = STEP_LABELS.get(step_key, step_key)

    async def _wrapped(state: ContractReviewState) -> dict:
        event = StepEvent(
            step=step_key,
            status="running",
            message=f"{label}中...",
            started_at=_now(),
        )
        state.step_log.append(event)
        state.current_step = step_key
        coro = _fire_progress(state)
        if coro is not None:
            try:
                await coro
            except Exception:
                logger.exception("进度回调异常 step=%s", step_key)

        try:
            result = await agent(state)
        except Exception as e:
            event.status = "error"
            event.finished_at = _now()
            event.message = f"{label}失败: {e}"
            state.errors.append(f"{step_key}: {e}")
            coro = _fire_progress(state)
            if coro is not None:
                try:
                    await coro
                except Exception:
                    logger.exception("进度回调异常 step=%s", step_key)
            raise

        # agent 返回部分更新字典，需要先应用到 state 以拿到最新字段计数
        for k, v in (result or {}).items():
            if hasattr(state, k):
                try:
                    setattr(state, k, v)
                except Exception:
                    pass

        event.status = "done"
        event.finished_at = _now()
        event.message = _step_message(state, step_key)
        try:
            idx = PIPELINE_STEPS.index(step_key)
            state.progress = round((idx + 1) / len(PIPELINE_STEPS), 3)
        except ValueError:
            pass
        state.current_step = ""
        coro = _fire_progress(state)
        if coro is not None:
            try:
                await coro
            except Exception:
                logger.exception("进度回调异常 step=%s", step_key)

        return result or {}

    _wrapped.__name__ = f"wrapped_{step_key}"
    return _wrapped


async def _run_parallel_analysis(
    state: ContractReviewState,
    risk_agent: Any,
    compliance_agent: Any,
) -> dict:
    """并发执行只依赖条款提取结果的风险识别与合规检查。"""
    started_at = _now()
    risk_event = StepEvent(
        step="risk_identification",
        status="running",
        message=f"{STEP_LABELS['risk_identification']}中...",
        started_at=started_at,
    )
    compliance_event = StepEvent(
        step="compliance_check",
        status="running",
        message=f"{STEP_LABELS['compliance_check']}中...",
        started_at=started_at,
    )
    state.step_log.extend([risk_event, compliance_event])
    state.current_step = "risk_identification,compliance_check"
    coro = _fire_progress(state)
    if coro is not None:
        try:
            await coro
        except Exception:
            logger.exception("并行分析开始进度回调异常")

    risk_state = state.model_copy(deep=True)
    compliance_state = state.model_copy(deep=True)
    try:
        risk_result, compliance_result = await __import__("asyncio").gather(
            risk_agent(risk_state),
            compliance_agent(compliance_state),
        )
    except Exception as exc:
        finished_at = _now()
        risk_event.status = "error"
        compliance_event.status = "error"
        risk_event.finished_at = finished_at
        compliance_event.finished_at = finished_at
        risk_event.message = f"并行分析失败: {exc}"
        compliance_event.message = f"并行分析失败: {exc}"
        state.current_step = ""
        state.errors.append(f"parallel_analysis: {exc}")
        raise

    merged = {**(risk_result or {}), **(compliance_result or {})}
    errors: list[str] = []
    for source in (state.errors, (risk_result or {}).get("errors", []), (compliance_result or {}).get("errors", [])):
        for error in source:
            if error not in errors:
                errors.append(error)
    if errors:
        merged["errors"] = errors

    for key, value in merged.items():
        if hasattr(state, key):
            setattr(state, key, value)

    finished_at = _now()
    risk_event.status = "done"
    risk_event.finished_at = finished_at
    risk_event.message = _step_message(state, "risk_identification")
    compliance_event.status = "done"
    compliance_event.finished_at = finished_at
    compliance_event.message = _step_message(state, "compliance_check")
    state.progress = 0.75
    state.current_step = ""
    merged.update({
        "step_log": state.step_log,
        "progress": state.progress,
        "current_step": state.current_step,
    })

    coro = _fire_progress(state)
    if coro is not None:
        try:
            await coro
        except Exception:
            logger.exception("并行分析完成进度回调异常")
    return merged


def _parallel_analysis_node(risk_agent: Any, compliance_agent: Any) -> Callable[..., Awaitable[dict]]:
    async def _wrapped(state: ContractReviewState) -> dict:
        return await _run_parallel_analysis(state, risk_agent, compliance_agent)

    _wrapped.__name__ = "parallel_risk_and_compliance"
    return _wrapped


def _complete_with_progress(node: Callable) -> Callable[..., Awaitable[dict]]:
    """包装 complete 节点：完成时把 progress 置 1.0 并触发回调。"""
    async def _wrapped(state: ContractReviewState) -> dict:
        out = node(state)
        if hasattr(out, "__await__"):
            out = await out
        state.progress = 1.0
        state.current_step = ""
        coro = _fire_progress(state)
        if coro is not None:
            try:
                await coro
            except Exception:
                logger.exception("进度回调异常 step=complete")
        return out or {}
    _wrapped.__name__ = "wrapped_complete"
    return _wrapped


def should_human_review(state: ContractReviewState) -> Literal["human_review", "complete"]:
    """条件路由：判断是否需要人工审核。"""
    if state.needs_human_review:
        return "human_review"
    return "complete"


def human_review_node(state: ContractReviewState) -> dict:
    """
    人机协同节点 — 真正的中断点。

    流水线编译时设置了 interrupt_before=["human_review"]，因此执行会在**进入本节点之前**
    暂停（此时 suggestion 已完成）。ReviewService 检测到暂停后把状态置为 AWAITING_HUMAN 并持久化。
    人工提交反馈后，通过 update_state 注入 human_feedback，再 ainvoke(None) 从此处恢复：
    本节点作为恢复入口执行（记录日志），随后进入 process_feedback 应用反馈。
    """
    logger.info("从人工审核中断点恢复 review_id=%s", state.review_id)
    return {}


def process_human_feedback(state: ContractReviewState) -> dict:
    """处理人工反馈后的后续逻辑。"""
    feedback = state.human_feedback
    if feedback is None:
        return {"status": ReviewStatus.COMPLETED}

    if feedback.decision == "approve":
        return {"status": ReviewStatus.APPROVED}
    elif feedback.decision == "reject":
        return {"status": ReviewStatus.REJECTED}
    else:
        if feedback.modified_suggestions:
            return {
                "suggestions": feedback.modified_suggestions,
                "status": ReviewStatus.COMPLETED,
            }
        return {"status": ReviewStatus.COMPLETED}


def complete_node(state: ContractReviewState) -> dict:
    """流水线完成节点。"""
    logger.info(
        "审查完成 review_id=%s 条款=%d 风险=%d 合规=%d 建议=%d",
        state.review_id,
        len(state.clauses),
        len(state.risk_findings),
        len(state.compliance_findings),
        len(state.suggestions),
    )
    return {"status": ReviewStatus.COMPLETED}


def build_review_graph(
    with_human_review: bool = True,
    rag_retriever=None,
) -> StateGraph:
    """
    构建合同审查流水线的LangGraph有向图。

    流程：
    clause_extraction → risk_identification → compliance_check
        → suggestion → [human_review | complete] → END

    Args:
        with_human_review: 是否启用人机协同节点
        rag_retriever: 可选的 RAG 检索器，用于增强 Agent 上下文

    Returns:
        编译后的StateGraph
    """

    clause_agent = ClauseExtractionAgent()
    risk_agent = RiskIdentificationAgent(rag_retriever=rag_retriever)
    compliance_agent = ComplianceCheckAgent(rag_retriever=rag_retriever)
    suggestion_agent = SuggestionAgent(rag_retriever=rag_retriever)

    graph = StateGraph(ContractReviewState)

    graph.add_node("clause_extraction", _with_progress("clause_extraction", clause_agent))
    graph.add_node(
        "parallel_analysis",
        _parallel_analysis_node(risk_agent, compliance_agent),
    )
    graph.add_node("suggestion", _with_progress("suggestion", suggestion_agent))
    graph.add_node("complete", _complete_with_progress(complete_node))

    if with_human_review:
        graph.add_node("human_review", human_review_node)
        graph.add_node("process_feedback", process_human_feedback)

    graph.set_entry_point("clause_extraction")
    graph.add_edge("clause_extraction", "parallel_analysis")
    graph.add_edge("parallel_analysis", "suggestion")

    if with_human_review:
        graph.add_conditional_edges(
            "suggestion",
            should_human_review,
            {
                "human_review": "human_review",
                "complete": "complete",
            },
        )
        graph.add_edge("human_review", "process_feedback")
        graph.add_edge("process_feedback", "complete")
    else:
        graph.add_edge("suggestion", "complete")

    graph.add_edge("complete", END)

    return graph


HUMAN_REVIEW_NODE = "human_review"


def create_review_pipeline(
    with_human_review: bool = True,
    checkpointer=None,
    rag_retriever=None,
):
    """
    创建完整的审查流水线。

    Args:
        with_human_review: 是否启用人机协同节点
        checkpointer: LangGraph checkpoint saver。启用人机协同时**必须**提供，
            否则无法在 human_review 前中断（会退化为一次性跑完的旧行为）。
            由 src.pipeline.checkpointer.get_checkpointer() 提供进程级持久实例。
        rag_retriever: 可选的 RAG 检索器，用于增强 Agent 上下文

    Returns:
        编译后的可执行图
    """
    graph = build_review_graph(
        with_human_review=with_human_review,
        rag_retriever=rag_retriever,
    )

    compile_kwargs: dict = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
        if with_human_review:
            # 真正的中断：进入 human_review 之前暂停，状态由 checkpointer 持久化
            compile_kwargs["interrupt_before"] = [HUMAN_REVIEW_NODE]
    elif with_human_review:
        logger.warning(
            "启用了 with_human_review 但未提供 checkpointer，"
            "流水线将无法在人工审核点中断（退化为一次性执行）。"
        )

    return graph.compile(**compile_kwargs)


def graph_is_awaiting_human(snapshot) -> bool:
    """判断某个 thread 是否正暂停在 human_review 中断点。

    Args:
        snapshot: pipeline.aget_state(config) 返回的 StateSnapshot
    """
    try:
        return HUMAN_REVIEW_NODE in (snapshot.next or ())
    except AttributeError:
        return False



async def run_review(
    raw_text: str = "",
    document_path: str = "",
    with_human_review: bool = True,
    with_rag: bool = False,
) -> ContractReviewState:
    """
    执行合同审查流水线。

    Args:
        raw_text: 合同原始文本
        document_path: 合同文档路径
        with_human_review: 是否启用人工审核
        with_rag: 是否启用 RAG 检索增强
    """
    rag_retriever = None
    if with_rag:
        try:
            from ..vector.embeddings import EmbeddingModel
            from ..vector.milvus_store import MilvusStore
            from ..vector.rag import RAGRetriever
            from ..config import Settings

            settings = Settings()
            model = EmbeddingModel(model_name=settings.EMBEDDING_MODEL)
            store = MilvusStore(embedding_model=model)
            if store.load():
                rag_retriever = RAGRetriever(store=store)
                logger.info("RAG 检索器已初始化，索引包含 %d 条记录", store.size)
            else:
                logger.info("未找到向量索引，跳过 RAG 增强")
        except Exception as e:
            logger.warning("RAG 初始化失败，使用普通模式: %s", e)

    checkpointer = None
    if with_human_review:
        from .checkpointer import init_checkpointer
        checkpointer = await init_checkpointer()

    pipeline = create_review_pipeline(
        with_human_review=with_human_review,
        checkpointer=checkpointer,
        rag_retriever=rag_retriever,
    )

    initial_state = ContractReviewState(
        raw_text=raw_text,
        document_path=document_path,
        status=ReviewStatus.IN_PROGRESS,
    )

    config = {"configurable": {"thread_id": initial_state.review_id}}
    result = await pipeline.ainvoke(initial_state.model_dump(), config=config)

    return ContractReviewState(**result)
