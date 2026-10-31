"""知识库服务单元测试 — 校验、注册表、软删除与状态聚合（假 MilvusStore/探针，不触碰真实服务）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.config import settings
from src.services import knowledge_service as ks
from src.services.knowledge_service import CATEGORIES, KnowledgeError, KnowledgeService


def _probe_result(total=0, active=0, model="", error="", exists=None):
    """伪造 milvus_store.probe() 返回体。"""
    return {
        "index_exists": (total > 0) if exists is None else exists,
        "total_chunks": total,
        "active_chunks": active,
        "embedding_model": model,
        "error": error,
    }


@pytest.fixture
def env(monkeypatch, tmp_path):
    """重定向数据路径到 tmp，伪造 MilvusStore/probe/EmbeddingModel/reload。"""
    monkeypatch.setattr(settings, "KNOWLEDGE_DIR", tmp_path / "knowledge_docs")
    monkeypatch.setattr(settings, "KNOWLEDGE_REGISTRY_PATH", tmp_path / "knowledge_docs.json")
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    # 隔离真实 .env 的新嵌入配置：走 local 源 + 假模型名 + 假工厂
    monkeypatch.setattr(settings, "EMBEDDING_SOURCE", "local")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "test/fake-model")
    # 单测不连 Milvus 服务：状态探针与存储对象全是假的
    monkeypatch.setattr(ks, "probe", lambda: _probe_result())

    fake_store = MagicMock()
    fake_store.load.return_value = False
    fake_store.mark_deleted.return_value = 3
    fake_store.size = 0
    fake_store.saved_model_name.return_value = ""
    fake_store.iter_live_chunks.return_value = []
    monkeypatch.setattr(ks, "create_embedding_model", lambda: MagicMock())
    monkeypatch.setattr(ks, "MilvusStore", lambda embedding_model=None: fake_store)
    monkeypatch.setattr(
        "src.services.review_service.reload_rag_retriever",
        lambda: {"ready": False, "size": 0, "reason": "rag_disabled"},
    )
    return tmp_path, fake_store, monkeypatch


class TestValidation:
    def test_add_text_requires_title(self, env):
        _, _, _ = env
        svc = KnowledgeService()
        with pytest.raises(KnowledgeError, match="标题"):
            svc.add_text(title="  ", category="civil", content="第一条 测试")

    def test_add_text_rejects_bad_category(self, env):
        svc = KnowledgeService()
        with pytest.raises(KnowledgeError, match="类别"):
            svc.add_text(title="测试", category="criminal", content="第一条 测试")

    def test_add_text_rejects_overlong_content(self, env):
        _, _, monkeypatch = env
        monkeypatch.setattr(ks, "MAX_TEXT_CHARS", 100)
        svc = KnowledgeService()
        with pytest.raises(KnowledgeError, match="过长"):
            svc.add_text(title="测试", category="civil", content="字" * 101)

    def test_chunk_limit_gate(self, env):
        _, _, monkeypatch = env
        monkeypatch.setattr(settings, "KNOWLEDGE_MAX_CHUNKS_PER_DOC", 2)
        svc = KnowledgeService()
        with pytest.raises(KnowledgeError, match="上限"):
            svc.add_text(
                title="测试", category="civil",
                content="第一条 甲\n第二条 乙\n第三条 丙",
            )

    def test_empty_parse_raises(self, env):
        _, _, monkeypatch = env
        # 全空白内容切块后无有效块
        svc = KnowledgeService()
        with pytest.raises(KnowledgeError, match="解析"):
            svc.add_text(title="测试", category="civil", content="   \n\n  ")


class TestIngest:
    def test_texts_concat_and_metadata_shape(self, env):
        _, fake_store, _ = env
        svc = KnowledgeService()
        result = svc.add_text(
            title="民法典·合同编", category="civil",
            content="第五百八十五条 当事人可以约定违约金。\n第五百六十三条 有下列情形之一的，当事人可以解除合同。",
        )
        assert result["chunk_count"] == 2
        texts, metas = fake_store.add.call_args.kwargs["texts"], fake_store.add.call_args.kwargs["metadata"]
        # 「标题：内容」拼接惯例，标题进向量
        assert texts[0].startswith("第五百八十五条：")
        for m in metas:
            assert m["doc_id"] == result["doc_id"]
            assert m["doc_title"] == "民法典·合同编"
            assert m["category"] == "civil"
            assert m["deleted"] is False

    def test_registry_roundtrip(self, env):
        tmp_path, _, _ = env
        svc = KnowledgeService()
        r = svc.add_text(title="测试库", category="labor", content="第一条 劳动者每日工作不超过八小时。")
        docs = svc.list()["docs"]
        assert len(docs) == 1
        assert docs[0]["doc_id"] == r["doc_id"]
        assert docs[0]["source_type"] == "text"
        assert docs[0]["title"] == "测试库"

    def test_corrupt_registry_reads_empty(self, env):
        tmp_path, _, _ = env
        tmp_path.joinpath("knowledge_docs.json").write_text("{坏文件", encoding="utf-8")
        svc = KnowledgeService()
        assert svc._read_registry() == []

    def test_add_file_keeps_copy(self, env, monkeypatch):
        tmp_path, _, _ = env
        parser = MagicMock()
        parser.parse.return_value = "第一条 测试条文"
        monkeypatch.setattr(ks, "DocumentParser", lambda: parser)
        svc = KnowledgeService()
        r = svc.add_file(filename="民法典.txt", content="第一条 测试条文".encode("utf-8"), category="civil")
        copies = list((tmp_path / "knowledge_docs").glob(f"{r['doc_id']}.txt"))
        assert copies, "上传副本应落盘"
        docs = svc.list()["docs"]
        assert docs[0]["filename"] == "民法典.txt"
        assert docs[0]["source_type"] == "upload"

    def test_add_file_parse_failure_removes_copy(self, env, monkeypatch):
        tmp_path, _, _ = env
        parser = MagicMock()
        parser.parse.side_effect = RuntimeError("解析炸了")
        monkeypatch.setattr(ks, "DocumentParser", lambda: parser)
        svc = KnowledgeService()
        with pytest.raises(KnowledgeError, match="解析失败"):
            svc.add_file(filename="坏文件.txt", content=b"xx", category="civil")
        assert not (tmp_path / "knowledge_docs").exists() or not list((tmp_path / "knowledge_docs").glob("*"))

    def test_capacity_valueerror_maps_to_knowledge_error(self, env):
        """Milvus VARCHAR 64KB 上限等容量校验（ValueError）应转成业务 400。"""
        _, fake_store, _ = env
        fake_store.add.side_effect = ValueError("条文文本超过 Milvus 单字段 64KB 上限")
        svc = KnowledgeService()
        with pytest.raises(KnowledgeError, match="64KB"):
            svc.add_text(title="测试", category="civil", content="第一条 测试")

    def test_model_mismatch_blocks_append(self, env):
        _, fake_store, _ = env
        fake_store.load.return_value = True
        fake_store.saved_model_name.return_value = "some/old-model"
        svc = KnowledgeService()
        with pytest.raises(KnowledgeError, match="不一致"):
            svc.add_text(title="测试", category="civil", content="第一条 测试")
        fake_store.add.assert_not_called()


class TestDelete:
    def test_delete_unknown_doc_raises_keyerror(self, env):
        svc = KnowledgeService()
        with pytest.raises(KeyError):
            svc.delete("ffffffff")

    def test_delete_marks_soft_and_removes_registry(self, env, monkeypatch):
        tmp_path, fake_store, _ = env
        parser = MagicMock()
        parser.parse.return_value = "第一条 测试条文"
        monkeypatch.setattr(ks, "DocumentParser", lambda: parser)
        svc = KnowledgeService()
        r = svc.add_file(filename="劳动法.txt", content=b"x", category="labor")
        # 副本存在
        assert list((tmp_path / "knowledge_docs").glob(f"{r['doc_id']}.*"))
        out = svc.delete(r["doc_id"])
        assert out["chunks_marked_deleted"] == 3
        fake_store.mark_deleted.assert_called_once_with(r["doc_id"])
        assert svc.list()["docs"] == []
        assert not list((tmp_path / "knowledge_docs").glob(f"{r['doc_id']}.*")), "副本应物理删除"


class TestStatus:
    def test_not_ready_when_rag_disabled(self, env, monkeypatch):
        monkeypatch.setattr(
            ks, "probe", lambda: _probe_result(total=1, active=1, model=settings.EMBEDDING_MODEL)
        )
        st = KnowledgeService().status()
        assert st["index_exists"] is True
        assert st["ready"] is False
        assert "RAG_ENABLED" in st["reason"]

    def test_active_vs_total(self, env, monkeypatch):
        monkeypatch.setattr(settings, "RAG_ENABLED", True)
        monkeypatch.setattr(ks, "probe", lambda: _probe_result(total=3, active=2))
        st = KnowledgeService().status()
        assert st["total_chunks"] == 3
        assert st["active_chunks"] == 2
        assert st["ready"] is True

    def test_model_mismatch_reported(self, env, monkeypatch):
        monkeypatch.setattr(settings, "RAG_ENABLED", True)
        monkeypatch.setattr(
            ks, "probe", lambda: _probe_result(total=1, active=1, model="old/model")
        )
        st = KnowledgeService().status()
        assert st["model_mismatch"] is True
        assert st["ready"] is False

    def test_no_index_reason_mentions_upload(self, env):
        st = KnowledgeService().status()
        assert st["index_exists"] is False
        assert "上传" in st["reason"]

    def test_unreachable_probe_shows_startup_hint(self, env, monkeypatch):
        """服务不可达不炸接口：错误进探针 error 字段，reason 给启动指引。"""
        monkeypatch.setattr(settings, "RAG_ENABLED", True)
        monkeypatch.setattr(
            ks, "probe", lambda: _probe_result(error="Milvus（http://localhost:19530）不可达：connection refused")
        )
        st = KnowledgeService().status()
        assert st["ready"] is False
        assert "docker compose --profile milvus" in st["reason"]


def test_categories_whitelist():
    assert CATEGORIES == {"civil", "labor", "commercial", "other"}


class TestStatusEmbeddingSource:
    """EMBEDDING_SOURCE=api 时的探针差异：不查 sentence-transformers、查 key。"""

    def test_api_mode_missing_key_reports_reason(self, env, monkeypatch):
        monkeypatch.setattr(
            ks, "probe", lambda: _probe_result(total=1, model="test/fake-model")
        )
        monkeypatch.setattr(settings, "RAG_ENABLED", True)
        monkeypatch.setattr(settings, "EMBEDDING_SOURCE", "api")
        monkeypatch.setattr(settings, "SILICONFLOW_API_KEY", "")
        st = KnowledgeService().status()
        assert st["ready"] is False
        assert "SILICONFLOW_API_KEY" in st["reason"]

    def test_api_mode_with_key_is_ready(self, env, monkeypatch):
        monkeypatch.setattr(
            ks, "probe", lambda: _probe_result(total=1, model="test/fake-model")
        )
        monkeypatch.setattr(settings, "RAG_ENABLED", True)
        monkeypatch.setattr(settings, "EMBEDDING_SOURCE", "api")
        monkeypatch.setattr(settings, "SILICONFLOW_API_KEY", "sk-fake")
        st = KnowledgeService().status()
        assert st["ready"] is True  # api 模式不该因缺 sentence-transformers 报依赖


class _UnreachableStore:
    """服务不可达替身：任何属性访问都抛连接异常。"""

    def __init__(self, embedding_model=None):
        pass

    @property
    def size(self):
        raise ConnectionError("Milvus（http://localhost:19530）连接被拒")


class TestRebuildIndex:
    """换嵌入模型的启动自动重建（假 store，断言服务层分支与传参）。"""

    def _prepare_store(self, fake_store, saved_model, chunks):
        fake_store.size = len(chunks)
        fake_store.saved_model_name.return_value = saved_model
        fake_store.iter_live_chunks.return_value = chunks

    def test_no_index_skips(self, env):
        assert ks.rebuild_index_if_model_changed()["reason"] == "no_index"

    def test_model_match_skips(self, env):
        _, fake_store, _ = env
        self._prepare_store(fake_store, "test/fake-model", [("t0", {"title": "a"})])
        out = ks.rebuild_index_if_model_changed()
        assert out["rebuilt"] is False and out["reason"] == "model_match"
        fake_store.replace_all.assert_not_called()

    def test_rebuild_passes_live_chunks_to_replace_all(self, env):
        _, fake_store, _ = env
        chunks = [(f"条文{i}", {"title": f"T{i}"}) for i in range(3)]
        self._prepare_store(fake_store, "old/bge-small", chunks)
        out = ks.rebuild_index_if_model_changed()
        assert out["rebuilt"] is True
        assert out["from_model"] == "old/bge-small" and out["to_model"] == "test/fake-model"
        assert out["chunks"] == 3
        # 重建全权交给 replace_all（all-or-nothing 语义在存储层，真机测试覆盖）
        texts, metas = fake_store.replace_all.call_args.args
        assert texts == [f"条文{i}" for i in range(3)]
        assert metas == [{"title": f"T{i}"} for i in range(3)]

    def test_unreachable_skips_without_failing_startup(self, env, monkeypatch):
        monkeypatch.setattr(ks, "MilvusStore", _UnreachableStore)
        out = ks.rebuild_index_if_model_changed()
        assert out["rebuilt"] is False and out["reason"] == "unreachable"

    def test_all_deleted_returns_nothing(self, env, monkeypatch):
        _, fake_store, _ = env
        factory = MagicMock()
        monkeypatch.setattr(ks, "create_embedding_model", factory)
        self._prepare_store(fake_store, "old/bge-small", [])
        fake_store.size = 5  # 集合非空，但活块为零
        out = ks.rebuild_index_if_model_changed()
        assert out["rebuilt"] is False and out["reason"] == "nothing_to_rebuild"
        factory.assert_not_called()
        fake_store.replace_all.assert_not_called()

    def test_embedder_unavailable_reports_reason(self, env, monkeypatch):
        _, fake_store, _ = env

        def _boom():
            raise RuntimeError("未设置 SILICONFLOW_API_KEY")
        monkeypatch.setattr(ks, "create_embedding_model", _boom)
        self._prepare_store(fake_store, "old/bge-small", [("a", {"title": "a"})])
        out = ks.rebuild_index_if_model_changed()
        assert out["rebuilt"] is False and out["reason"] == "embedder_error"
        fake_store.replace_all.assert_not_called()

    def test_replace_all_failure_reports_reason(self, env):
        _, fake_store, _ = env
        self._prepare_store(fake_store, "old/bge-small", [("a", {"title": "a"})])
        fake_store.replace_all.side_effect = RuntimeError("Milvus 写入失败")
        out = ks.rebuild_index_if_model_changed()
        assert out["rebuilt"] is False and out["reason"] == "rebuild_failed"
