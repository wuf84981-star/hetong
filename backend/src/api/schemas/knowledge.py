"""知识库 API 数据模型 — 与前端 types/index.ts 的 Knowledge* 类型一一对应。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeStatus(BaseModel):
    """知识库聚合状态（状态卡数据源）。"""

    rag_enabled: bool
    deps_ok: bool
    index_exists: bool
    ready: bool
    active_chunks: int
    total_chunks: int
    doc_count: int
    embedding_model: str
    index_model: str
    model_mismatch: bool
    reason: str = ""


class KnowledgeDoc(BaseModel):
    """注册表中的一份已入库文档。"""

    doc_id: str
    title: str
    filename: str = ""
    category: str
    chunk_count: int
    source_type: str = Field(description="upload=文件上传 | text=粘贴条文")
    uploaded_by: str = ""
    uploaded_at: str = ""


class KnowledgeListResponse(BaseModel):
    docs: list[KnowledgeDoc]
    status: KnowledgeStatus


class RagReloadInfo(BaseModel):
    """写操作后检索器热重载结果。"""

    ready: bool
    size: int = 0
    reason: str = ""


class KnowledgeWriteResult(BaseModel):
    doc_id: str
    chunk_count: int
    rag: RagReloadInfo


class KnowledgeDeleteResult(BaseModel):
    doc_id: str
    chunks_marked_deleted: int
    rag: RagReloadInfo


class KnowledgeTextRequest(BaseModel):
    """粘贴条文入库请求。"""

    title: str = Field(min_length=1, max_length=200)
    category: str = Field(pattern="^(civil|labor|commercial|other)$")
    content: str = Field(min_length=1)
