"""Agent 侧 RAG 引用记账工具——把结构化检索结果转成可持久化的 RagRef。"""

from __future__ import annotations

from ..pipeline.state import RagRef

SNIPPET_LEN = 200


def make_rag_refs(hits: list[dict], limit: int = 2) -> list[RagRef]:
    """RAGRetriever.retrieve_structured() 的结果 → RagRef 列表。

    透出只取前 limit 条（默认 2）、snippet 截 200 字：喂给 LLM 的上下文（top_k=3）
    与给人类看的引用可以不对称，透出从简，保证卷宗记录不膨胀。
    """
    refs = []
    for r in hits[:limit]:
        meta = r.get("metadata") or {}
        snippet = (r.get("text") or "").strip()
        if len(snippet) > SNIPPET_LEN:
            snippet = snippet[:SNIPPET_LEN] + "…"
        refs.append(
            RagRef(
                doc_title=meta.get("doc_title") or meta.get("source") or "",
                clause_title=meta.get("title", ""),
                category=meta.get("category", ""),
                score=round(float(r.get("score", 0.0)), 3),
                snippet=snippet,
            )
        )
    return refs
