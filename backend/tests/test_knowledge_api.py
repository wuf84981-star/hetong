"""知识库 API 集成测试 — 鉴权门、写入、列表与删除的状态码映射。

用 fake MilvusStore/EmbeddingModel 隔离真实嵌入栈；.txt 上传走真实解析管线。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.auth.dependencies import get_current_user  # noqa: F401  (确认模块可导入)
from src.api.auth.security import create_access_token
from src.api.main import create_app
from src.config import settings
from src.db.session import get_db
from src.services import knowledge_service as ks


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "KNOWLEDGE_DIR", tmp_path / "knowledge_docs")
    monkeypatch.setattr(settings, "KNOWLEDGE_REGISTRY_PATH", tmp_path / "knowledge_docs.json")
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    monkeypatch.setattr(settings, "EMBEDDING_SOURCE", "local")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "test/fake-model")

    fake_store = MagicMock()
    fake_store.load.return_value = False
    fake_store.mark_deleted.return_value = 2
    # 假 store + 假探针：API 测试不连 Milvus 服务、不加载真实嵌入栈
    monkeypatch.setattr(ks, "probe", lambda: {
        "index_exists": False, "total_chunks": 0, "active_chunks": 0,
        "embedding_model": "", "error": "",
    })
    monkeypatch.setattr(ks, "create_embedding_model", lambda: MagicMock())
    monkeypatch.setattr(ks, "MilvusStore", lambda embedding_model=None: fake_store)
    monkeypatch.setattr(
        "src.services.review_service.reload_rag_retriever",
        lambda: {"ready": False, "size": 0, "reason": "rag_disabled"},
    )

    app = create_app()

    async def _no_db():
        yield None

    app.dependency_overrides[get_db] = _no_db
    return TestClient(app)


def _auth(role: str) -> dict:
    token = create_access_token(subject=f"u-{role}", role=role, tenant_id="t1")
    return {"Authorization": f"Bearer {token}"}


class TestAuthGate:
    def test_no_token_401(self, client):
        assert client.get("/api/v1/knowledge").status_code == 401

    def test_viewer_403(self, client):
        assert client.get("/api/v1/knowledge", headers=_auth("viewer")).status_code == 403

    def test_viewer_cannot_write(self, client):
        r = client.post(
            "/api/v1/knowledge/text",
            headers=_auth("viewer"),
            json={"title": "x", "category": "civil", "content": "第一条 测试"},
        )
        assert r.status_code == 403

    def test_reviewer_can_read_not_write(self, client):
        """知识库全局共享：注册开放给自助 reviewer 后，读得到但写不进。"""
        assert client.get("/api/v1/knowledge", headers=_auth("reviewer")).status_code == 200
        r = client.post(
            "/api/v1/knowledge/text",
            headers=_auth("reviewer"),
            json={"title": "x", "category": "civil", "content": "第一条 测试"},
        )
        assert r.status_code == 403
        assert client.delete("/api/v1/knowledge/deadbeef", headers=_auth("reviewer")).status_code == 403


class TestTextFlow:
    def test_create_list_delete(self, client):
        h = _auth("admin")
        r = client.post(
            "/api/v1/knowledge/text", headers=h,
            json={"title": "民法典·合同编", "category": "civil",
                  "content": "第五百八十五条 当事人可以约定违约金。\n第五百六十三条 当事人可以解除合同。"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["chunk_count"] == 2
        assert body["rag"]["ready"] is False  # RAG_ENABLED=False 如实回传

        listed = client.get("/api/v1/knowledge", headers=h).json()
        assert listed["status"]["doc_count"] == 1
        assert listed["docs"][0]["title"] == "民法典·合同编"
        assert listed["docs"][0]["uploaded_by"] == "u-admin"

        d = client.delete(f"/api/v1/knowledge/{body['doc_id']}", headers=h)
        assert d.status_code == 200
        assert d.json()["chunks_marked_deleted"] == 2
        assert client.get("/api/v1/knowledge", headers=h).json()["docs"] == []

    def test_bad_category_422(self, client):
        r = client.post(
            "/api/v1/knowledge/text", headers=_auth("admin"),
            json={"title": "x", "category": "criminal", "content": "第一条 测试"},
        )
        assert r.status_code == 422

    def test_delete_unknown_404(self, client):
        assert client.delete("/api/v1/knowledge/ffffffff", headers=_auth("admin")).status_code == 404


class TestUploadFlow:
    def test_txt_upload_201(self, client):
        content = "第一条 为了保障合同当事人的合法权益。\n第二条 本法所称合同是平等主体的协议。".encode("utf-8")
        r = client.post(
            "/api/v1/knowledge/upload", headers=_auth("admin"),
            files={"file": ("合同法.txt", content, "text/plain")},
            data={"category": "civil", "title": ""},
        )
        assert r.status_code == 201, r.text
        assert r.json()["chunk_count"] == 2

    def test_reviewer_upload_403(self, client):
        """上传端点同样收紧：reviewer 只能读列表，不能入库。"""
        r = client.post(
            "/api/v1/knowledge/upload", headers=_auth("reviewer"),
            files={"file": ("test.txt", "第一条 测试".encode("utf-8"), "text/plain")},
            data={"category": "civil", "title": ""},
        )
        assert r.status_code == 403

    def test_bad_extension_400(self, client):
        r = client.post(
            "/api/v1/knowledge/upload", headers=_auth("admin"),
            files={"file": ("病毒.exe", b"MZ\x90\x00", "application/octet-stream")},
            data={"category": "other", "title": ""},
        )
        assert r.status_code == 400
        assert "格式" in r.json()["detail"]

    def test_empty_file_400(self, client):
        r = client.post(
            "/api/v1/knowledge/upload", headers=_auth("admin"),
            files={"file": ("空.txt", b"", "text/plain")},
            data={"category": "other", "title": ""},
        )
        assert r.status_code == 400
