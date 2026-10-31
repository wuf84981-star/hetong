"""MilvusStore 真机集成测试 — 需 docker compose --profile milvus up -d；服务不可达自动 skip。

用确定性假向量（8 维 one-hot）隔离嵌入栈，只验证存储契约：
写入→检索→软删→重建→容量限制。
"""
import time
import uuid

import pytest
from pymilvus import MilvusClient

from src.config import settings
from src.vector.milvus_store import MilvusStore


class _FakeModel:
    """确定性 8 维 one-hot 假向量：同文本同向量，便于命中断言。"""

    model_name = "test/fake-milvus"

    @staticmethod
    def _vec(text: str) -> list[float]:
        seed = sum(text.encode("utf-8")) % 8
        v = [0.0] * 8
        v[seed] = 1.0
        return v

    def embed(self, texts):
        return [self._vec(t) for t in texts]

    def embed_single(self, text):
        return self._vec(text)


def _reachable() -> bool:
    try:
        MilvusClient(uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN or "").list_collections()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _reachable(),
    reason="Milvus 未启动：docker compose --profile milvus up -d",
)


@pytest.fixture
def store(monkeypatch):
    collection = f"it_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(settings, "MILVUS_COLLECTION", collection)
    st = MilvusStore(embedding_model=_FakeModel())
    yield st
    try:
        st._get_client().drop_collection(collection)
    except Exception:
        pass


def _wait_size(st: MilvusStore, n: int, timeout: float = 10.0) -> bool:
    """等待写入可见（Milvus 一致性窗口容忍）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if st.size == n:
            return True
        time.sleep(0.3)
    return False


def _wait_active(st: MilvusStore, n: int, timeout: float = 10.0) -> bool:
    """等待软删标记传播到过滤视图——delete 生效晚于 insert 可见，需轮询。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if st.active_size == n:
            return True
        time.sleep(0.3)
    return st.active_size == n


def test_add_search_and_soft_delete_roundtrip(store):
    store.add(
        texts=["第一条 民事主体平等", "第二条 自愿订立合同"],
        metadata=[
            {"doc_id": "d1", "doc_title": "民法典·示例", "title": "第一条", "deleted": False},
            {"doc_id": "d1", "doc_title": "民法典·示例", "title": "第二条", "deleted": False},
        ],
    )
    assert _wait_size(store, 2), "Milvus 写入可见性超时"

    hits: list[dict] = []
    for _ in range(20):
        hits = store.search("第一条 民事主体平等", top_k=2)
        if len(hits) == 2:
            break
        time.sleep(0.3)
    assert len(hits) == 2
    assert hits[0]["metadata"]["title"] == "第一条"
    assert "民事主体平等" in hits[0]["text"]
    assert hits[0]["score"] >= hits[1]["score"]

    assert store.saved_model_name() == "test/fake-milvus"

    assert store.mark_deleted("d1") == 2
    assert _wait_size(store, 2)  # 软删不物理回收，检索侧过采过滤
    assert _wait_active(store, 0), "软删标记传播超时"
    assert store.iter_live_chunks() == []
    assert store.mark_deleted("nope") == 0


def test_replace_all_rebuilds_collection(store):
    store.add(texts=["旧甲"], metadata=[{"doc_id": "d1", "title": "旧甲", "deleted": False}])
    assert _wait_size(store, 1)

    class _NewModel(_FakeModel):
        model_name = "test/new-model"

    store._model = _NewModel()
    store.replace_all(
        texts=["新甲", "新乙"],
        metadata=[
            {"doc_id": "d2", "title": "新甲", "deleted": False},
            {"doc_id": "d2", "title": "新乙", "deleted": False},
        ],
    )
    assert _wait_size(store, 2)
    assert store.saved_model_name() == "test/new-model"
    assert {t for t, _ in store.iter_live_chunks()} == {"新甲", "新乙"}


def test_reject_oversize_chunk(store):
    huge = "字" * 30000  # UTF-8 每字 3 字节，远超 VARCHAR 64KB 上限
    with pytest.raises(ValueError, match="64KB"):
        store.add(texts=[huge], metadata=[{"doc_id": "d1"}])
