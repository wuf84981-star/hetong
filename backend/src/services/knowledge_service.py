"""知识库服务 — 法规条例向量入库的唯一写入口。

职责：文档注册表（data/knowledge_docs.json）+ Milvus 向量集合：
切块→嵌入→入库 + 检索器热重载。所有写路径经模块级 _WRITE_LOCK 串行化；
注册表落盘用临时文件原子替换，读方（列表/状态）无需加锁。路由层只做
参数校验与错误映射。

模型混用防线：集合侧行内 emb_model 字段记录建库模型名，与当前
EMBEDDING_MODEL 不一致时拒绝追加并给出重建指引——两种 embedding 向量
在同一集合里做内积只会产出静默的垃圾结果。
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

from ..config import settings
from ..parsers.document_parser import DocumentParser, parse_raw_text_to_sections
from ..vector.embeddings import create_embedding_model
from ..vector.milvus_store import MilvusStore, probe

logger = logging.getLogger(__name__)

# 类别白名单（与前端 Regulations.tsx CATEGORY_MAP 对齐并补 other）
CATEGORIES = {"civil", "labor", "commercial", "other"}
# 粘贴文本服务端上限（字符）
MAX_TEXT_CHARS = 500_000

# 写路径全局锁：embed→add→落库→registry→reload 串行（单写者显式化）
_WRITE_LOCK = threading.Lock()


class KnowledgeError(ValueError):
    """业务校验失败（路由映射为 400）。"""


# 条文起始标记：第X条/款/项/章（中文或阿拉伯数字）、（X）、顿号序号、数字序号
_ARTICLE_HEAD = re.compile(
    r"^\s*(第[一二三四五六七八九十百千0-9]+[条款项章]、?|（[一二三四五六七八九十0-9]+）|[一二三四五六七八九十]+、|\d+[.、])\s*(.*)$"
)


def _split_articles(text: str) -> list[dict]:
    """法条逐行切块：以条文标记起行的行开启新块，后续普通行并入当前块。

    parse_raw_text_to_sections 面向章节式合同（标题独立成行），整行「第X条 正文」
    会被它连正文一起吞进标题——法条粘贴场景须用本切分器。首个标记前的引言丢弃
    （文档名已承担出处标题）。无标记命中返回空列表，由调用方兜底。
    """
    sections: list[dict] = []
    title: str | None = None
    lines: list[str] = []

    def flush() -> None:
        if title is None:
            return
        content = "\n".join(lines).strip()
        if content:
            sections.append({"title": title, "content": content})

    for line in text.splitlines():
        m = _ARTICLE_HEAD.match(line)
        if m:
            flush()
            title = m.group(1).rstrip("、")
            rest = m.group(2).strip()
            lines = [rest] if rest else []
        elif title is not None and line.strip():
            lines.append(line)
    flush()
    return sections


def _new_doc_id() -> str:
    return uuid.uuid4().hex[:8]


class KnowledgeService:
    """知识库编排：注册表读写、文件/文本入库、软删除、状态聚合。"""

    # ── 注册表 ────────────────────────────────────────────

    def _read_registry(self) -> list[dict]:
        p = settings.KNOWLEDGE_REGISTRY_PATH
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("知识库注册表不可读，按空处理: %s", p)
            return []
        return list(data.get("docs", []))

    def _write_registry(self, docs: list[dict]) -> None:
        p = settings.KNOWLEDGE_REGISTRY_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"docs": docs}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(p)  # 原子替换，读方永远不会看到半截文件

    # ── 索引 ──────────────────────────────────────────────

    def _open_store(self) -> MilvusStore:
        """构建 Milvus 集合句柄（空集合也可，add 时自动建集合）。

        ImportError（缺依赖）/模型加载失败原样上抛，由路由映射 503。
        """
        model = create_embedding_model()
        store = MilvusStore(embedding_model=model)
        if store.load():
            saved = store.saved_model_name()
            if saved and saved != settings.EMBEDDING_MODEL:
                raise KnowledgeError(
                    f"现有索引由 Embedding 模型「{saved}」建成，与当前配置"
                    f"「{settings.EMBEDDING_MODEL}」不一致，两种模型不能共用索引——"
                    f"请将 EMBEDDING_MODEL 改回「{saved}」，或删除索引重建后重新上传"
                )
        return store

    @staticmethod
    def _sections_to_payload(
        doc_id: str, doc_title: str, category: str, source: str, sections: list[dict]
    ) -> tuple[list[str], list[dict]]:
        """[{title,content}] → (texts, metadatas)。

        texts 采用「标题：内容」拼接（沿用 build_index.py 惯例，标题进向量提升检索）。
        """
        texts: list[str] = []
        metas: list[dict] = []
        for s in sections:
            title = (s.get("title") or "全文").strip() or "全文"
            content = (s.get("content") or "").strip()
            if not content:
                continue
            texts.append(f"{title}：{content}")
            metas.append({
                "doc_id": doc_id,
                "doc_title": doc_title,
                "title": title,
                "category": category,
                "source": source,
                "deleted": False,
            })
        return texts, metas

    def _ingest(
        self, *, doc_id: str, doc_title: str, category: str, source: str,
        text: str, user_id: str, filename: str, source_type: str,
        copy_path: Path | None,
    ) -> dict:
        """校验切块 → 持锁嵌入入库 → 写注册表 → 热重载。失败时清理副本。"""
        if category not in CATEGORIES:
            raise KnowledgeError(f"类别不合法：{category}（可选 civil/labor/commercial/other）")
        # 逐行法条切分优先；纯叙述文本退回章节切分器（整篇作「全文」一块）
        sections = _split_articles(text) or parse_raw_text_to_sections(text)
        texts, metas = self._sections_to_payload(doc_id, doc_title, category, source, sections)
        if not texts:
            if copy_path:
                copy_path.unlink(missing_ok=True)
            raise KnowledgeError("未能从内容中解析出文本")
        if len(texts) > settings.KNOWLEDGE_MAX_CHUNKS_PER_DOC:
            if copy_path:
                copy_path.unlink(missing_ok=True)
            raise KnowledgeError(
                f"切块数 {len(texts)} 超过单文档上限 {settings.KNOWLEDGE_MAX_CHUNKS_PER_DOC}，请拆分后分批上传"
            )

        # 延迟导入避免模块环依赖（review_service 不反向依赖本服务）
        from .review_service import reload_rag_retriever

        with _WRITE_LOCK:
            store = self._open_store()
            try:
                store.add(texts=texts, metadata=metas)
            except ValueError as e:
                # 容量类校验（Milvus VARCHAR 64KB 上限）→ 业务 400
                if copy_path:
                    copy_path.unlink(missing_ok=True)
                raise KnowledgeError(str(e)) from e
            except Exception:
                if copy_path:
                    copy_path.unlink(missing_ok=True)
                raise
            docs = self._read_registry()
            docs.append({
                "doc_id": doc_id,
                "title": doc_title,
                "filename": filename,
                "category": category,
                "chunk_count": len(texts),
                "source_type": source_type,
                "uploaded_by": user_id,
                "uploaded_at": datetime.now().isoformat(timespec="seconds"),
            })
            self._write_registry(docs)
            rag = reload_rag_retriever()
        logger.info("知识库入库《%s》：%d 块，检索器 %s", doc_title, len(texts), rag)
        return {"doc_id": doc_id, "chunk_count": len(texts), "rag": rag}

    # ── 对外动作 ──────────────────────────────────────────

    def add_file(self, *, filename: str, content: bytes, category: str,
                 title: str = "", user_id: str = "") -> dict:
        """上传文件入库。filename 须已过 validate_upload（路由层）。"""
        settings.KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        doc_id = _new_doc_id()
        ext = Path(filename).suffix.lower()
        copy_path = settings.KNOWLEDGE_DIR / f"{doc_id}{ext}"
        copy_path.write_bytes(content)
        try:
            text = DocumentParser().parse(copy_path)
        except Exception as e:
            copy_path.unlink(missing_ok=True)
            raise KnowledgeError(f"文档解析失败：{e}") from e
        doc_title = title.strip() or Path(filename).stem
        return self._ingest(
            doc_id=doc_id, doc_title=doc_title, category=category,
            source=filename, text=text, user_id=user_id,
            filename=filename, source_type="upload", copy_path=copy_path,
        )

    def add_text(self, *, title: str, category: str, content: str, user_id: str = "") -> dict:
        """粘贴条文入库。"""
        doc_title = title.strip()
        if not doc_title:
            raise KnowledgeError("标题不能为空")
        if len(content) > MAX_TEXT_CHARS:
            raise KnowledgeError(f"粘贴内容过长（上限 {MAX_TEXT_CHARS} 字符），请分批")
        return self._ingest(
            doc_id=_new_doc_id(), doc_title=doc_title, category=category,
            source="粘贴条文", text=content, user_id=user_id,
            filename="", source_type="text", copy_path=None,
        )

    def delete(self, doc_id: str) -> dict:
        """软删除：集合行标记 deleted（物理向量不回收）+ 注册表移除 + 副本物理删除。"""
        with _WRITE_LOCK:
            docs = self._read_registry()
            if not any(d["doc_id"] == doc_id for d in docs):
                raise KeyError(doc_id)
            store = self._open_store()
            marked = store.mark_deleted(doc_id)
            self._write_registry([d for d in docs if d["doc_id"] != doc_id])
            if settings.KNOWLEDGE_DIR.exists():
                for p in settings.KNOWLEDGE_DIR.glob(f"{doc_id}.*"):
                    p.unlink(missing_ok=True)
            from .review_service import reload_rag_retriever
            rag = reload_rag_retriever()
        logger.info("知识库删除 %s：%d 块退出检索", doc_id, marked)
        return {"doc_id": doc_id, "chunks_marked_deleted": marked, "rag": rag}

    def status(self) -> dict:
        """聚合状态：依赖探针 / 集合存在 / 开关联动 / 模型一致性 / 块数统计。"""
        api_mode = settings.EMBEDDING_SOURCE == "api"
        deps_ok = True
        key_missing = False
        try:
            import pymilvus  # noqa: F401
            if not api_mode:
                import sentence_transformers  # noqa: F401
        except ImportError:
            deps_ok = False
        if api_mode and not settings.SILICONFLOW_API_KEY:
            deps_ok = False
            key_missing = True

        res = probe()
        index_exists = res["index_exists"]
        total_chunks = res["total_chunks"]
        active_chunks = res["active_chunks"]
        index_model = res["embedding_model"]

        mismatch = bool(index_model) and index_model != settings.EMBEDDING_MODEL
        ready = deps_ok and index_exists and settings.RAG_ENABLED and not mismatch
        if not deps_ok:
            if key_missing:
                reason = "已配置远程嵌入（EMBEDDING_SOURCE=api）但缺少 SILICONFLOW_API_KEY，请在 backend/.env 填入"
            elif api_mode:
                reason = "检索依赖未安装（api 模式仅需 pymilvus）"
            else:
                reason = "检索依赖未安装（需 pymilvus；本地嵌入另需 sentence-transformers）"
        elif res["error"]:
            reason = f"{res['error']}；请启动服务：docker compose --profile milvus up -d"
        elif not index_exists:
            reason = "尚未建立索引——在本页上传法规文档即自动建库，或先运行 scripts/build_index.py 建样例索引"
        elif mismatch:
            reason = f"索引由模型「{index_model}」建成，与当前配置「{settings.EMBEDDING_MODEL}」不一致，请改回配置或删除索引重建后重新上传"
        elif not settings.RAG_ENABLED:
            reason = "索引已就绪，但 RAG_ENABLED 开关未打开——开启后审查即启用检索"
        else:
            reason = ""
        return {
            "rag_enabled": settings.RAG_ENABLED,
            "deps_ok": deps_ok,
            "index_exists": index_exists,
            "ready": ready,
            "active_chunks": active_chunks,
            "total_chunks": total_chunks,
            "doc_count": len(self._read_registry()),
            "embedding_model": settings.EMBEDDING_MODEL,
            "index_model": index_model,
            "model_mismatch": mismatch,
            "reason": reason,
        }

    def list(self) -> dict:
        return {"docs": self._read_registry(), "status": self.status()}


# 模块级共享实例（无状态，线程安全靠锁与原子写）
_knowledge_service: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service


# ── 换嵌入模型的自动重建（启动钩子）────────────────────────


def rebuild_index_if_model_changed() -> dict:
    """集合记录的模型与当前配置不一致时，用集合内存的原文本重嵌入重建。

    启动时调用（main.py lifespan）。重建不依赖上传原件——集合侧本就
    存有全部原文，软删块直接淘汰。先全部重嵌入、全部成功后才删旧集合
    重写（all-or-nothing），嵌入阶段任一批失败旧集合分毫未动。返回结果
    仅供日志/状态，不抛异常——模型切换失败不应阻塞应用启动。
    """
    with _WRITE_LOCK:
        reader = MilvusStore()  # 只读统计/原文，无需嵌入模型
        try:
            if reader.size == 0:
                return {"rebuilt": False, "reason": "no_index"}
            saved = reader.saved_model_name()
            if saved == settings.EMBEDDING_MODEL:
                return {"rebuilt": False, "reason": "model_match"}
            chunks = reader.iter_live_chunks()
        except Exception as e:
            logger.warning("Milvus 不可达，跳过启动重建: %s", e)
            return {"rebuilt": False, "reason": "unreachable", "error": str(e)}
        if not chunks:
            return {"rebuilt": False, "reason": "nothing_to_rebuild"}
        texts = [t for t, _ in chunks]
        metas = [m for _, m in chunks]

        from .review_service import reload_rag_retriever  # 延迟导入防环依赖

        try:
            model = create_embedding_model()
        except (RuntimeError, ImportError) as e:
            logger.warning("重建索引失败——嵌入模型不可用: %s", e)
            return {"rebuilt": False, "reason": "embedder_error", "error": str(e)}

        writer = MilvusStore(embedding_model=model)
        try:
            writer.replace_all(texts, metas)
        except Exception as e:
            logger.warning("重建索引失败（%s → %s）: %s", saved, settings.EMBEDDING_MODEL, e)
            return {"rebuilt": False, "reason": "rebuild_failed", "error": str(e)}
        rag = reload_rag_retriever()
    logger.info(
        "嵌入模型切换 %s → %s：已用 %d 块原文本重建 Milvus 集合（软删块已淘汰），检索器 %s",
        saved or "(未记录)", settings.EMBEDDING_MODEL, len(texts), rag,
    )
    return {
        "rebuilt": True,
        "from_model": saved,
        "to_model": settings.EMBEDDING_MODEL,
        "chunks": len(texts),
        "rag": rag,
    }
