"""知识库管理 API — 法规条例上传/粘贴入库、列表、软删除、状态查询。

权限：列表 admin + reviewer（注册表含文件名/上传人，属内部面，不对 viewer 开放）；
上传/粘贴/删除仅 admin——知识库为全租户共享语料，自助注册即可获得 reviewer，
写权限收口到管理员，防止任意注册账号污染审查依据。
写端点为同步 def（FastAPI 落 threadpool），嵌入计算不阻塞事件循环。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..auth.dependencies import CurrentUser, require_role
from ..upload_guard import UploadValidationError, validate_upload
from ...services.knowledge_service import (
    KnowledgeError,
    get_knowledge_service,
)
from ..schemas.knowledge import (
    KnowledgeDeleteResult,
    KnowledgeListResponse,
    KnowledgeTextRequest,
    KnowledgeWriteResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])

# 统一异常映射：业务校验→400，未知文档→404，依赖缺失→503，模型加载失败→503
_DEPS_HINT = (
    "检索依赖未安装：请在 backend/ 目录执行 "
    "uv pip install pymilvus sentence-transformers 后重启后端"
)
_MODEL_HINT = (
    "Embedding 模型加载失败（多为模型未本地缓存且网络不可达）："
    "可在 .env 设置 HF_ENDPOINT=https://hf-mirror.com 后重启，"
    "或设置 EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5 换用已缓存模型"
)


def _guard(fn, *args, **kwargs):
    """执行服务调用并把异常映射为 HTTP 状态码。"""
    try:
        return fn(*args, **kwargs)
    except KnowledgeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UploadValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="文档不存在或已删除")
    except ImportError as e:
        logger.warning("知识库依赖缺失: %s", e)
        raise HTTPException(status_code=503, detail=_DEPS_HINT)
    except (OSError, RuntimeError) as e:
        # sentence-transformers/torch 加载失败的主要形态
        logger.warning("Embedding 模型加载失败: %s", e)
        raise HTTPException(status_code=503, detail=f"{_MODEL_HINT}；原始错误：{e}")


def _user_id(user: CurrentUser | None) -> str:
    return user.id if user else "system"


@router.get("", response_model=KnowledgeListResponse)
async def list_knowledge(
    user: CurrentUser | None = Depends(require_role("admin", "reviewer")),
):
    """文档列表 + 聚合状态。"""
    return get_knowledge_service().list()


@router.post("/upload", response_model=KnowledgeWriteResult, status_code=201)
def upload_knowledge_doc(
    file: UploadFile = File(..., description="法规文档（.pdf/.docx/.doc/.txt）"),
    category: str = Form("other", description="civil/labor/commercial/other"),
    title: str = Form("", description="文档名，留空取文件名"),
    user: CurrentUser | None = Depends(require_role("admin")),
):
    """上传文件入库：校验→解析→切块→嵌入→落索引→热重载。"""
    content = file.file.read()
    try:
        safe_name = validate_upload(file.filename or "unnamed", content)
    except UploadValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    svc = get_knowledge_service()
    return _guard(
        svc.add_file,
        filename=safe_name,
        content=content,
        category=category,
        title=title,
        user_id=_user_id(user),
    )


@router.post("/text", response_model=KnowledgeWriteResult, status_code=201)
def create_knowledge_text(
    body: KnowledgeTextRequest,
    user: CurrentUser | None = Depends(require_role("admin")),
):
    """粘贴条文入库（按「第X条/一、/1.」自动切块）。"""
    svc = get_knowledge_service()
    return _guard(
        svc.add_text,
        title=body.title,
        category=body.category,
        content=body.content,
        user_id=_user_id(user),
    )


@router.delete("/{doc_id}", response_model=KnowledgeDeleteResult)
def delete_knowledge_doc(
    doc_id: str,
    user: CurrentUser | None = Depends(require_role("admin")),
):
    """软删除：向量标记退出检索（物理向量不回收），注册表移除，原件副本删除。"""
    svc = get_knowledge_service()
    return _guard(svc.delete, doc_id)
