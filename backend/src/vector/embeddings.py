"""Embedding 模型封装 — 基于 sentence-transformers 的中文法律文本嵌入。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "shibing624/text2vec-base-chinese"


class EmbeddingModel:
    """sentence-transformers 封装，支持懒加载和中文法律文本嵌入。"""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model = None

    def _load_model(self):
        """懒加载模型，仅在首次调用时加载。"""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers 未安装。请运行: "
                "pip install sentence-transformers>=2.2.0"
            )
        logger.info("加载 Embedding 模型: %s", self._model_name)
        self._model = SentenceTransformer(self._model_name)
        logger.info("模型加载完成，维度: %d", self._model.get_sentence_embedding_dimension())

    @property
    def model_name(self) -> str:
        """模型名称（索引落盘记名、状态页比对防混用；无需加载模型即可读）。"""
        return self._model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        """将文本列表转换为向量。"""
        self._load_model()
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()

    def embed_single(self, text: str) -> list[float]:
        """将单个文本转换为向量。"""
        return self.embed([text])[0]

    @property
    def dimension(self) -> int:
        """返回嵌入向量维度。"""
        self._load_model()
        return self._model.get_sentence_embedding_dimension()


class RemoteEmbeddingModel:
    """OpenAI 兼容 /embeddings 远程嵌入（默认硅基流动 SiliconFlow）。

    与本地 EmbeddingModel 接口同形（embed/embed_single/model_name），
    上层 MilvusStore/RAGRetriever 无感知。请求带 normalize=True 保证
    向量归一化——内积（IP）度量的相似度依赖这一点。
    注意：api 模式下被向量化的文本（含审查时的合同条款）会发送给所配置的服务商。
    """

    def __init__(self, model_name: str, base_url: str, api_key: str, timeout: float = 30.0):
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    @property
    def model_name(self) -> str:
        """模型名称（索引落盘记名、混用防线比对用）。"""
        return self._model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量远程嵌入，按 OpenAI 兼容协议的 index 顺序还原。"""
        import httpx

        if not texts:
            return []
        try:
            resp = httpx.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model_name, "input": texts, "normalize": True},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
        except httpx.HTTPStatusError as e:
            body = e.response.text[:200]
            raise RuntimeError(f"远程嵌入 API 返回 {e.response.status_code}：{body}") from e
        except httpx.HTTPError as e:
            raise RuntimeError(f"远程嵌入 API 不可达：{e}") from e
        if len(data) != len(texts):
            raise RuntimeError(f"远程嵌入返回 {len(data)} 条，期望 {len(texts)} 条")
        ordered = sorted(data, key=lambda d: d.get("index", 0))
        vectors = [d["embedding"] for d in ordered]
        if any(len(v) != len(vectors[0]) for v in vectors):
            raise RuntimeError("远程嵌入返回的向量维度不一致")
        return vectors

    def embed_single(self, text: str) -> list[float]:
        """单条远程嵌入。"""
        return self.embed([text])[0]


def create_embedding_model():
    """按 EMBEDDING_SOURCE 构造嵌入模型（配置统一入口，杜绝各调用点自行 new）。

    - local：sentence-transformers 本地推理（首次使用需能加载模型）
    - api  ：远程 OpenAI 兼容接口，须配 SILICONFLOW_API_KEY
    """
    from ..config import settings

    if settings.EMBEDDING_SOURCE == "api":
        key = settings.SILICONFLOW_API_KEY
        if not key or key.startswith("your_"):
            raise RuntimeError(
                "EMBEDDING_SOURCE=api 但未设置真实 SILICONFLOW_API_KEY——"
                "请在 backend/.env 填入硅基流动 API Key，或改回 EMBEDDING_SOURCE=local"
            )
        return RemoteEmbeddingModel(
            model_name=settings.EMBEDDING_MODEL,
            base_url=settings.EMBEDDING_BASE_URL,
            api_key=key,
        )
    return EmbeddingModel(model_name=settings.EMBEDDING_MODEL)
