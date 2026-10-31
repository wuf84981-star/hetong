"""远程嵌入（OpenAI 兼容 /embeddings，默认硅基流动）与模型工厂测试 — 不发真实网络请求。"""

from __future__ import annotations

import httpx
import pytest

from src.config import settings
from src.vector.embeddings import (
    EmbeddingModel,
    RemoteEmbeddingModel,
    create_embedding_model,
)


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            req = httpx.Request("POST", "https://api.test/v1/embeddings")
            resp = httpx.Response(self.status_code, request=req, text="auth failed")
            raise httpx.HTTPStatusError("4xx", request=req, response=resp)

    def json(self) -> dict:
        return self._payload


def _model() -> RemoteEmbeddingModel:
    return RemoteEmbeddingModel(
        model_name="BAAI/bge-m3",
        base_url="https://api.test/v1",
        api_key="sk-fake",
    )


class TestRemoteEmbeddingModel:
    def test_batch_order_restored_by_index(self, monkeypatch):
        """API 返回乱序时按 index 字段还原，保证与输入一一对应。"""
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(url=url, headers=headers, body=json)
            data = [
                {"index": 1, "embedding": [0.2, 0.2]},
                {"index": 0, "embedding": [0.1, 0.1]},
            ]
            return FakeResponse({"data": data})

        monkeypatch.setattr(httpx, "post", fake_post)
        vectors = _model().embed(["条文甲", "条文乙"])
        assert vectors == [[0.1, 0.1], [0.2, 0.2]]
        assert captured["url"] == "https://api.test/v1/embeddings"
        assert captured["headers"]["Authorization"] == "Bearer sk-fake"
        # 协议体：model + input 批量 + normalize（IndexFlatIP 内积依赖归一化）
        assert captured["body"] == {"model": "BAAI/bge-m3", "input": ["条文甲", "条文乙"], "normalize": True}

    def test_empty_input_no_request(self, monkeypatch):
        def never(*a, **k):
            raise AssertionError("空列表不应发起请求")
        monkeypatch.setattr(httpx, "post", never)
        assert _model().embed([]) == []

    def test_count_mismatch_raises(self, monkeypatch):
        monkeypatch.setattr(
            httpx, "post",
            lambda *a, **k: FakeResponse({"data": [{"index": 0, "embedding": [0.1]}]}),
        )
        with pytest.raises(RuntimeError, match="期望 2 条"):
            _model().embed(["甲", "乙"])

    def test_dimension_mismatch_raises(self, monkeypatch):
        monkeypatch.setattr(
            httpx, "post",
            lambda *a, **k: FakeResponse({"data": [
                {"index": 0, "embedding": [0.1, 0.2]},
                {"index": 1, "embedding": [0.1]},
            ]}),
        )
        with pytest.raises(RuntimeError, match="维度不一致"):
            _model().embed(["甲", "乙"])

    def test_http_error_maps_to_runtime(self, monkeypatch):
        """HTTP 层失败必须转 RuntimeError——知识库写路径与启动重建都按此类型兜住。"""
        def fake_post(*a, **k):
            raise httpx.ConnectError("连接被拒绝", request=httpx.Request("POST", "https://api.test/v1/embeddings"))
        monkeypatch.setattr(httpx, "post", fake_post)
        with pytest.raises(RuntimeError, match="不可达"):
            _model().embed(["甲"])

    def test_status_error_maps_to_runtime(self, monkeypatch):
        monkeypatch.setattr(
            httpx, "post", lambda *a, **k: FakeResponse({}, status=401),
        )
        with pytest.raises(RuntimeError, match="返回 401"):
            _model().embed(["甲"])

    def test_embed_single(self, monkeypatch):
        monkeypatch.setattr(
            httpx, "post",
            lambda *a, **k: FakeResponse({"data": [{"index": 0, "embedding": [0.5]}]}),
        )
        assert _model().embed_single("甲") == [0.5]

    def test_model_name_without_request(self):
        assert _model().model_name == "BAAI/bge-m3"


class TestEmbeddingFactory:
    def test_local_source_builds_local_model(self, monkeypatch):
        monkeypatch.setattr(settings, "EMBEDDING_SOURCE", "local")
        monkeypatch.setattr(settings, "EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
        model = create_embedding_model()
        assert isinstance(model, EmbeddingModel)
        assert model.model_name == "BAAI/bge-small-zh-v1.5"

    def test_api_source_builds_remote(self, monkeypatch):
        monkeypatch.setattr(settings, "EMBEDDING_SOURCE", "api")
        monkeypatch.setattr(settings, "EMBEDDING_MODEL", "BAAI/bge-m3")
        monkeypatch.setattr(settings, "SILICONFLOW_API_KEY", "sk-real")
        monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
        model = create_embedding_model()
        assert isinstance(model, RemoteEmbeddingModel)
        assert model.model_name == "BAAI/bge-m3"

    def test_api_source_missing_key_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "EMBEDDING_SOURCE", "api")
        monkeypatch.setattr(settings, "SILICONFLOW_API_KEY", "")
        with pytest.raises(RuntimeError, match="SILICONFLOW_API_KEY"):
            create_embedding_model()

    def test_api_source_placeholder_key_raises(self, monkeypatch):
        """照抄 .env.example 占位符不能当成真 key 发请求。"""
        monkeypatch.setattr(settings, "EMBEDDING_SOURCE", "api")
        monkeypatch.setattr(settings, "SILICONFLOW_API_KEY", "your_siliconflow_api_key_here")
        with pytest.raises(RuntimeError, match="SILICONFLOW_API_KEY"):
            create_embedding_model()
