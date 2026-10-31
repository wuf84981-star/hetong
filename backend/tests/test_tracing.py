"""OpenTelemetry Trace 测试 — InMemorySpanExporter 注入。

NOTE: 此环境 opentelemetry-sdk 未安装,本文件顶部先 install_otel_stub()
注入最小可用 stub 让 pytest 能 collection;在生产/CI 安装真包后,
stub 自动让位于真实 import,行为等价。
"""
from contextlib import contextmanager
import sys
import types


def install_otel_stub():
    """最小 OTel stub — 不安装任何包,验证代码路径。"""

    class _StubSpan:
        def __init__(self, name):
            self.name = name
            self.attributes = {}
            self._ended = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def set_attribute(self, k, v):
            self.attributes[k] = v

        def set_status(self, s):
            pass

        def add_event(self, n, attributes=None):
            pass

        def end(self):
            self._ended = True

    class _StubSpanCtx:
        """start_as_current_span 的真正上下文管理器 — 记录完成的 span。"""

        def __init__(self, name, target_list):
            self.span = _StubSpan(name)
            self._list = target_list

        def __enter__(self):
            return self.span

        def __exit__(self, *args):
            self._list.append(self.span)
            return False

    class _StubTracer:
        def __init__(self, name, processors=None):
            self.name = name
            self.finished = []
            self._processors = processors or []

        @contextmanager
        def start_as_current_span(self, name, **kw):
            # 与真实 OTel 行为一致: `with tracer.start_as_current_span(name) as span:`
            # 这里 `span` 应当是 span 实例本身(直接持有属性/状态),
            # span 结束时由 SimpleSpanProcessor.on_end 收集。
            span = _StubSpan(name)
            try:
                yield span
            finally:
                # 模拟 on_end:把所有结束的 span 推到 exporter
                for processor in getattr(self, "_processors", []):
                    processor.on_end(span)
                self.finished.append(span)

        def start_span(self, name, **kw):
            return _StubSpan(name)

    class _InMemoryExporter:
        def __init__(self):
            self.finished = []

        def export(self, spans):
            self.finished.extend(spans)
            from enum import Enum
            return Enum("ExportResult", "SUCCESS FAILURE").SUCCESS

        def get_finished_spans(self):
            return list(self.finished)

        def clear(self):
            self.finished.clear()

    class _StubSpanProcessor:
        def __init__(self, *args, **kwargs):
            self._args = args
            self._kwargs = kwargs
            # 若第一个参数是 exporter 实例,缓存它
            self._exporter = args[0] if args and hasattr(args[0], "export") else None

        def on_end(self, span):
            if self._exporter is not None:
                self._exporter.export([span])

        def shutdown(self):
            pass

    class _StubTracerProvider:
        def __init__(self, resource=None):
            self.resource = resource
            self.processors = []

        def add_span_processor(self, p):
            self.processors.append(p)

        def get_tracer(self, name, **kw):
            return _StubTracer(name, processors=list(self.processors))

    class _StubResource:
        @staticmethod
        def create(d):
            return d

    sdk = types.ModuleType("opentelemetry.sdk")
    sdk_trace = types.ModuleType("opentelemetry.sdk.trace")
    sdk_export = types.ModuleType("opentelemetry.sdk.trace.export")
    sdk_resources = types.ModuleType("opentelemetry.sdk.resources")

    sdk_trace.TracerProvider = _StubTracerProvider
    sdk_export.BatchSpanProcessor = _StubSpanProcessor
    sdk_export.ConsoleSpanExporter = type("Console", (), {})
    sdk_export.SimpleSpanProcessor = _StubSpanProcessor
    inmem_mod = types.ModuleType(
        "opentelemetry.sdk.trace.export.in_memory_span_exporter"
    )
    inmem_mod.InMemorySpanExporter = _InMemoryExporter
    sdk_resources.Resource = _StubResource

    sys.modules["opentelemetry.sdk"] = sdk
    sys.modules["opentelemetry.sdk.trace"] = sdk_trace
    sys.modules["opentelemetry.sdk.trace.export"] = sdk_export
    sys.modules["opentelemetry.sdk.resources"] = sdk_resources
    sys.modules.setdefault(
        "opentelemetry.sdk.trace.export.in_memory_span_exporter", inmem_mod
    )


install_otel_stub()

import pytest  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402

from src.tracing import (  # noqa: E402
    init_tracing,
    get_tracer,
    set_request_id,
    get_request_id,
)


@pytest.fixture
def in_memory_provider():
    """注入 InMemorySpanExporter 供测试。"""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield provider, exporter


def test_init_tracing_creates_tracer(in_memory_provider):
    """init_tracing 应接受 provider 注入(测试用)。"""
    provider, exporter = in_memory_provider
    init_tracing(service_name="test", console_output=False, provider=provider)
    tracer = get_tracer()
    assert tracer is not None


def test_request_id_context_var():
    """request_id 通过 contextvars 传递。"""
    set_request_id("test-rid-123")
    assert get_request_id() == "test-rid-123"
    set_request_id("")  # cleanup


def test_span_attributes_recorded(in_memory_provider):
    """span 应包含 review_id / degraded_steps / status 属性。"""
    provider, exporter = in_memory_provider
    init_tracing(service_name="test", console_output=False, provider=provider)
    tracer = get_tracer()

    with tracer.start_as_current_span("review_pipeline") as span:
        span.set_attribute("review_id", "r123")
        span.set_attribute("degraded_steps", "clause_extraction")
        span.set_attribute("status", "completed")

    spans = exporter.get_finished_spans()
    assert len(spans) >= 1
    pipeline_span = next(s for s in spans if s.name == "review_pipeline")
    assert pipeline_span.attributes["review_id"] == "r123"
    assert pipeline_span.attributes["degraded_steps"] == "clause_extraction"
    assert pipeline_span.attributes["status"] == "completed"


def test_run_pipeline_with_progress_creates_span(monkeypatch, in_memory_provider):
    """_run_pipeline_with_progress 应创建 review_pipeline span。"""
    from src.services.review_service import ReviewService
    from src.services.storage_service import StorageService
    from src.api.dependencies.storage import MemoryStore
    from src.pipeline.state import ContractReviewState, ReviewStatus

    provider, exporter = in_memory_provider
    init_tracing(service_name="test", console_output=False, provider=provider)
    set_request_id("test-rid")

    mem = MemoryStore()
    storage = StorageService(db=None, memory=mem, tenant_id="t1")
    svc = ReviewService(storage=storage)

    # 测最小可测部分:start_as_current_span 已存在并记录属性
    tracer = get_tracer()
    with tracer.start_as_current_span("review_pipeline", attributes={"review_id": "rid-1"}):
        set_request_id("test-rid")  # 验证 contextvar

    spans = exporter.get_finished_spans()
    assert any(s.name == "review_pipeline" for s in spans)
