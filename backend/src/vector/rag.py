"""RAG 检索器 — 从向量存储中检索相关条文，为 Agent 提供上下文增强。"""

from __future__ import annotations


class RAGRetriever:
    """RAG 检索器，为不同 Agent 提供定制化的上下文检索。

    store 为 MilvusStore（检索契约：
    search(query, top_k) → [{text, metadata, score}]）。
    """

    def __init__(self, store):
        self._store = store

    def retrieve_structured(self, query: str, top_k: int = 3, oversample: int = 3) -> list[dict]:
        """结构化检索：过采 top_k*oversample → 过滤软删除块 → 截断 top_k。

        返回 [{text, metadata, score}]，供 Agent 侧记录"引用出处"（rag_refs）；
        软删除只改 metadata 标记、物理向量原地保留，
        故必须过采再过滤，否则被删块会白白挤占名额。
        """
        raw = self._store.search(query, top_k=top_k * oversample)
        live = [r for r in raw if not (r.get("metadata") or {}).get("deleted")]
        return live[:top_k]

    def format_context(self, results: list[dict]) -> str:
        """将结构化检索结果格式化为 LLM 可读的上下文文本。"""
        parts = []
        for i, r in enumerate(results, 1):
            meta = r.get("metadata") or {}
            title = meta.get("title", "未知条款")
            # 出处优先取知识库文档名，退回原始文件名；旧样例数据两者皆无时只显类别
            doc_title = meta.get("doc_title") or meta.get("source") or ""
            category = meta.get("category", "")
            if doc_title and category:
                provenance = f"（出处：{doc_title} · 类别：{category}）"
            elif doc_title:
                provenance = f"（出处：{doc_title}）"
            elif category:
                provenance = f"（类别：{category}）"
            else:
                provenance = ""
            part = f"[参考条文 {i}] {title}{provenance}"
            part += f"\n相似度：{r['score']:.2f}\n内容：{r['text']}"
            parts.append(part)
        return "\n\n".join(parts)

    def _retrieve(self, clause_text: str, top_k: int = 3) -> str:
        """共享检索逻辑（字符串版，向后兼容）。"""
        return self.format_context(self.retrieve_structured(clause_text, top_k))

    def retrieve_for_risk(self, clause_text: str, top_k: int = 3) -> str:
        """为风险识别 Agent 检索相似条款的法律条文。"""
        return self._retrieve(clause_text, top_k)

    def retrieve_for_compliance(self, clause_text: str, top_k: int = 3) -> str:
        """为合规检查 Agent 检索相似条款的法律条文。"""
        return self._retrieve(clause_text, top_k)

    def retrieve_for_suggestion(self, clause_text: str, top_k: int = 3) -> str:
        """为修改建议 Agent 检索相似条款的规范写法。"""
        return self._retrieve(clause_text, top_k)

    # 兼容历史调用方/测试直接引用私有名
    _format_context = format_context
