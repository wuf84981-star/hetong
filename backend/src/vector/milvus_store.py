"""Milvus 向量存储 — 语义检索的唯一向量后端。

Schema：id（主键自增）/ vector（FLOAT_VECTOR，AUTOINDEX+IP）/ doc_id / deleted /
emb_model / text / meta（JSON 字符串）。语义设计：
- 软删除只改 deleted 标记、物理向量不回收，检索照常返回，由 RAGRetriever 过采过滤；
- 原文（text）随行走标量字段落库，换嵌入模型时可据此重建，无需重新上传原件；
- save() 为空操作（持久化在服务端），load() 即"集合存在且有数据"。

已知限制：单块 text/meta 受 Milvus VARCHAR 65535 字节上限约束（超限 add 抛
ValueError，路由层映射 400）；检索为同步网络调用（pymilvus 同步库），高并发
场景下会占用事件循环时间片，单机部署可接受。
"""

from __future__ import annotations

import json
import logging

import numpy as np
from pymilvus import DataType, MilvusClient

from ..config import settings

logger = logging.getLogger(__name__)

VARCHAR_MAX = 65535      # Milvus VARCHAR 单字段字节上限
_QUERY_PAGE = 16384      # 单次读取上限（query / query_iterator 分批）
_EMBED_BATCH = 32        # 重建时的嵌入分批大小（远程 API 友好）
_INSERT_BATCH = 500


def _client() -> MilvusClient:
    return MilvusClient(uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN or "")


def _check_varchar(value: str, what: str) -> str:
    size = len(value.encode("utf-8"))
    if size > VARCHAR_MAX:
        raise ValueError(
            f"{what}超过 Milvus 单字段 64KB 上限（{size} 字节）——"
            f"请拆分法条切块或调低单文档内容长度后分批入库"
        )
    return value


class MilvusStore:
    """Milvus 集合封装；embedding_model 仅写入/检索需要，统计类操作可为 None。"""

    def __init__(self, embedding_model=None):
        self._model = embedding_model
        self._name = settings.MILVUS_COLLECTION
        self._client: MilvusClient | None = None

    # ── 连接与集合 ────────────────────────────────────────

    def _get_client(self) -> MilvusClient:
        if self._client is None:
            self._client = _client()
        return self._client

    def _ensure_collection(self, dim: int) -> None:
        c = self._get_client()
        if c.has_collection(self._name):
            return
        schema = c.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field("doc_id", DataType.VARCHAR, max_length=64)
        schema.add_field("deleted", DataType.BOOL)
        schema.add_field("emb_model", DataType.VARCHAR, max_length=256)
        schema.add_field("text", DataType.VARCHAR, max_length=VARCHAR_MAX)
        schema.add_field("meta", DataType.VARCHAR, max_length=VARCHAR_MAX)
        index_params = c.prepare_index_params()
        index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="IP")
        c.create_collection(self._name, schema=schema, index_params=index_params)
        logger.info("已创建 Milvus 集合 %s（dim=%d，内积度量）", self._name, dim)

    # ── 写入 ──────────────────────────────────────────────

    def _rows(self, texts: list[str], metadata: list[dict], vectors: np.ndarray) -> list[dict]:
        model_name = getattr(self._model, "model_name", "") if self._model else ""
        rows = []
        for t, m, v in zip(texts, metadata, vectors):
            meta_json = json.dumps(m, ensure_ascii=False)
            rows.append({
                "vector": [float(x) for x in v],
                "doc_id": str(m.get("doc_id", ""))[:64],
                "deleted": bool(m.get("deleted", False)),
                "emb_model": model_name,
                "text": _check_varchar(t, "条文文本"),
                "meta": _check_varchar(meta_json, "条文元数据"),
            })
        return rows

    def add(self, texts: list[str], metadata: list[dict]) -> None:
        """嵌入并插入；集合不存在时按首向量维度自动建集合。"""
        if not texts:
            return
        if len(texts) != len(metadata):
            raise ValueError(f"texts ({len(texts)}) 和 metadata ({len(metadata)}) 长度不一致")
        if self._model is None:
            raise ValueError("add 需要嵌入模型（当前实例为只读模式）")
        vectors = np.asarray(self._model.embed(texts), dtype=np.float32)
        self._ensure_collection(vectors.shape[1])
        rows = self._rows(texts, metadata, vectors)
        self._get_client().insert(self._name, data=rows)
        logger.info("Milvus 添加 %d 条记录（集合 %s，总计 %d 条）", len(rows), self._name, self.size)

    def mark_deleted(self, doc_id: str) -> int:
        """软删除：读出该行组，deleted 置真后原向量重插（换主键，物理向量不回收）。

        检索侧过采过滤即可排除被删块；不做 upsert 是因
        auto_id 集合对显式主键回写支持不稳，delete+insert 组合语义等价。
        """
        c = self._get_client()
        rows = c.query(
            self._name,
            filter=f'doc_id == "{doc_id}" and deleted == false',
            output_fields=["id", "doc_id", "emb_model", "text", "meta", "vector"],
            limit=_QUERY_PAGE,
        )
        if not rows:
            return 0
        new_rows = []
        for r in rows:
            m = json.loads(r.get("meta") or "{}")
            m["deleted"] = True
            new_rows.append({
                "vector": r["vector"],
                "doc_id": r["doc_id"],
                "deleted": True,
                "emb_model": r.get("emb_model", ""),
                "text": r["text"],
                "meta": json.dumps(m, ensure_ascii=False),
            })
        c.delete(self._name, ids=[r["id"] for r in rows])
        c.insert(self._name, data=new_rows)
        return len(new_rows)

    def replace_all(self, texts: list[str], metadata: list[dict]) -> None:
        """整库重建（换嵌入模型路径）：先全部重嵌入，全成功后才删旧集合重写。

        嵌入阶段不碰存储，失败则旧数据分毫未动；只有删旧后的写入阶段可能
        留下半截新数据（服务此时不可达），据实上抛由调用方报告。
        """
        if not texts:
            raise ValueError("replace_all 拒绝空列表——避免误清整库")
        if self._model is None:
            raise ValueError("replace_all 需要嵌入模型")
        batches = []
        for start in range(0, len(texts), _EMBED_BATCH):
            batch = texts[start:start + _EMBED_BATCH]
            batches.append(np.asarray(self._model.embed(batch), dtype=np.float32))
        vectors = np.vstack(batches)

        c = self._get_client()
        if c.has_collection(self._name):
            c.drop_collection(self._name)
        self._ensure_collection(vectors.shape[1])
        rows = self._rows(texts, metadata, vectors)
        for start in range(0, len(rows), _INSERT_BATCH):
            c.insert(self._name, data=rows[start:start + _INSERT_BATCH])
        logger.info("Milvus 集合 %s 已整体重建：%d 块", self._name, len(rows))

    # ── 检索 ──────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """向量检索；软删块照常返回（由 RAGRetriever 过采过滤）。"""
        if self.size == 0:
            return []
        if self._model is None:
            raise ValueError("search 需要嵌入模型（当前实例为只读模式）")
        qv = [float(x) for x in self._model.embed_single(query)]
        res = self._get_client().search(
            self._name, data=[qv], limit=top_k, output_fields=["text", "meta"],
        )
        out = []
        for hit in res[0]:
            ent = hit.get("entity", {})
            out.append({
                "text": ent.get("text", ""),
                "metadata": json.loads(ent.get("meta") or "{}"),
                "score": float(hit.get("distance", 0.0)),
            })
        return out

    # ── 统计与元信息 ──────────────────────────────────────

    @property
    def size(self) -> int:
        c = self._get_client()
        if not c.has_collection(self._name):
            return 0
        return _count_rows(c, self._name)

    @property
    def active_size(self) -> int:
        try:
            return _count_rows(self._get_client(), self._name, "deleted == False")
        except Exception:
            return 0

    def saved_model_name(self) -> str:
        """集合内记录的建库模型名（取一行）；空集合返回空串。"""
        c = self._get_client()
        if not c.has_collection(self._name):
            return ""
        rows = c.query(self._name, filter="id >= 0", output_fields=["emb_model"], limit=1)
        return str(rows[0].get("emb_model", "")) if rows else ""

    def iter_live_chunks(self) -> list[tuple[str, dict]]:
        """(原文, 元数据)——未软删的块，换嵌入模型重建据此重嵌入。"""
        if self.size == 0:
            return []
        c = self._get_client()
        out: list[tuple[str, dict]] = []
        # pymilvus 2.6 的 MilvusClient 无 scroll，分页读统一走 query_iterator
        it = c.query_iterator(
            self._name, batch_size=_QUERY_PAGE,
            filter="deleted == False", output_fields=["text", "meta"],
        )
        try:
            while True:
                page = it.next()
                if not page:
                    break
                for row in page:
                    out.append((row.get("text", ""), json.loads(row.get("meta") or "{}")))
        finally:
            it.close()
        return out

    # ── 契约对齐项 ────────────────────────────────────────

    def save(self, path: str | None = None) -> None:
        """空操作：持久化在 Milvus 服务端，插入即落库。"""

    def load(self, path: str | None = None) -> bool:
        """集合存在且有数据即视为加载成功；服务不可达按空索引处理并告警。"""
        try:
            return self.size > 0
        except Exception as e:
            logger.warning("Milvus 连接不可达，本次按空索引处理: %s", e)
            return False


def _count_rows(c, name: str, filter_expr: str = "id >= 0") -> int:
    """行数统计：pymilvus 2.6 移除了 MilvusClient.count，统一用 query 聚合 count(*)。"""
    rows = c.query(name, filter=filter_expr, output_fields=["count(*)"])
    return int(rows[0].get("count(*)", 0)) if rows else 0


def probe() -> dict:
    """状态页统计（不构建嵌入模型、不抛异常——连接失败进 error 字段）。"""
    res = {"index_exists": False, "total_chunks": 0, "active_chunks": 0,
           "embedding_model": "", "error": ""}
    try:
        c = _client()
        name = settings.MILVUS_COLLECTION
        if not c.has_collection(name):
            return res
        res["total_chunks"] = _count_rows(c, name)
        res["index_exists"] = res["total_chunks"] > 0
        res["active_chunks"] = _count_rows(c, name, "deleted == False")
        rows = c.query(name, filter="id >= 0", output_fields=["emb_model"], limit=1)
        res["embedding_model"] = str(rows[0].get("emb_model", "")) if rows else ""
    except Exception as e:
        res["error"] = f"Milvus（{settings.MILVUS_URI}）不可达：{e}"
    return res
