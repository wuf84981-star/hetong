"""OpenTelemetry 链路追踪 + contextvars 上下文穿透。

侑夕《你不知道的 Agent》: "Trace 是排查的前提,事件流做底座。"

设计要点:
1. OTel SDK 的 import 全部延迟到函数体内,保证 OTel 不可用时模块仍可 import。
2. `_DummyTracer` / `_DummySpan` 在 get_tracer() 走兜底分支时启用,
   避免业务方 `with tracer.start_as_current_span(...)` 因异常崩溃。
3. `set_request_id` / `get_request_id` 基于 contextvars,跨 asyncio.Task
   与 (Celery worker 进程内) 协程传递 request_id。
4. `init_tracing(provider=...)` 支持测试注入 InMemorySpanExporter。
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger(__name__)

# ── 上下文穿透 — 跨 asyncio task / Celery 任务传递 request_id ──
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_initialized: bool = False
_tracer: Optional[object] = None  # trace.Tracer | _DummyTracer


# ── contextvars API ───────────────────────────────────────────


def set_request_id(rid: str) -> None:
    """设置当前上下文的 request_id。"""
    _request_id_var.set(rid)


def get_request_id() -> str:
    """获取当前上下文的 request_id(默认空字符串)。"""
    return _request_id_var.get()


# ── 追踪初始化 ───────────────────────────────────────────────


def init_tracing(
    service_name: str = "fencun-contract",
    console_output: bool = False,
    provider: object | None = None,
) -> None:
    """初始化 OTel。

    Args:
        service_name: 服务名(OTel resource attribute)
        console_output: 是否输出到 console(开发模式)
        provider: 注入测试用 provider;生产为 None 时创建新
    """
    global _initialized, _tracer

    # ── 测试注入分支 ──
    if provider is not None:
        _initialized = True
        _tracer = provider.get_tracer(service_name)
        return

    if _initialized:
        return

    try:
        # 延迟 import — 让 OTel 不可用时模块仍能 import
        from opentelemetry import trace as _ot_trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource

        # settings 是可选依赖 — 单独 try,失败也无所谓
        try:
            from ..config import settings
            otel_enabled = bool(getattr(settings, "OTEL_ENABLED", False))
            otel_endpoint = getattr(
                settings,
                "OTEL_EXPORTER_OTLP_ENDPOINT",
                "http://localhost:4317",
            )
            configured_service = getattr(
                settings, "OTEL_SERVICE_NAME", service_name
            )
        except Exception:  # noqa: BLE001 — 任何导入失败都不阻断
            otel_enabled = False
            otel_endpoint = "http://localhost:4317"
            configured_service = service_name

        # 让外部传入的 service_name 优先,其次用 settings
        effective_name = (
            service_name if service_name != "fencun-contract"
            else configured_service
        )

        resource = Resource.create({"service.name": effective_name})
        new_provider = TracerProvider(resource=resource)

        if otel_enabled:
            try:
                from opentelemetry.sdk.trace.export import BatchSpanProcessor
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )
                new_provider.add_span_processor(
                    BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_endpoint))
                )
            except ImportError:
                logger.warning("OTLP exporter 不可用,跳过 OTLP 导出")

        if console_output:
            try:
                from opentelemetry.sdk.trace.export import (
                    BatchSpanProcessor,
                    ConsoleSpanExporter,
                )
                new_provider.add_span_processor(
                    BatchSpanProcessor(ConsoleSpanExporter())
                )
            except ImportError:
                logger.warning("Console exporter 不可用")

        _ot_trace.set_tracer_provider(new_provider)
        _tracer = new_provider.get_tracer(effective_name)
        _initialized = True
        logger.info("OpenTelemetry 初始化完成 service=%s", effective_name)
    except ImportError:
        logger.warning("OTel SDK 不可用,链路追踪已禁用")
        _initialized = True
    except Exception as e:  # noqa: BLE001 — 追踪不应让进程启动崩溃
        logger.warning("OTel 初始化失败: %s", e)
        _initialized = True


def get_tracer(name: str = "fencun-contract"):
    """获取 tracer 实例。

    未初始化时尝试按需初始化;OTel 不可用则返回 `_DummyTracer`。
    """
    global _tracer

    if _tracer is not None:
        return _tracer

    try:
        from opentelemetry import trace as _ot_trace
        _tracer = _ot_trace.get_tracer(name)
    except ImportError:
        _tracer = _DummyTracer()

    return _tracer


# ── 兜底实现 — OTel 不可用时不阻塞业务调用 ───────────────────


class _DummyTracer:
    """OTel 不可用时的兜底实现。"""

    def start_span(self, name: str, **kwargs):
        return _DummySpan()

    def start_as_current_span(self, name: str, **kwargs):
        return _DummySpan()


class _DummySpan:
    """空 Span 实现。"""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def set_attribute(self, key: str, value) -> None:
        return None

    def set_status(self, status) -> None:
        return None

    def add_event(self, name: str, attributes=None) -> None:
        return None
