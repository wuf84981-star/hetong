"""跨会话经验库 — 侑夕《你不知道的 Agent》: "MEMORY.md,跨会话保持一致性的关键。"

V1 实现: JSONL 持久化 + 关键词 Jaccard 检索。
V2 (P2): 升级到 embedding 检索。
"""
from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path


class MemoryService:
    """跨审查沉淀的经验库 — JSONL 持久化,中文关键词 Jaccard 检索。"""

    # 中文常用停用词（与合同审查领域无关的通用词）
    _STOPWORDS = {
        "的", "是", "在", "和", "与", "或", "但", "也", "有", "为",
        "由", "对", "可", "应", "须", "将", "本", "该", "如", "等",
        "此", "它", "这", "那", "并", "且",
    }

    def __init__(self, tenant_id: str, storage_path: str = "memory"):
        self.tenant_id = tenant_id
        self.path = Path(storage_path) / f"{tenant_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record_outcome(
        self,
        review_id: str,
        decision: str,
        comments: str,
        high_risk_clauses: list[str],
        bad_clauses: list[str] | None = None,
        missed_clauses: list[str] | None = None,
    ) -> None:
        """人工反馈后记录经验。"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "review_id": review_id,
            "decision": decision,
            "comments": comments,
            "high_risk_clauses": high_risk_clauses,
            "bad_clauses": bad_clauses or [],
            "missed_clauses": missed_clauses or [],
            "tags": sorted(self._extract_tags(comments)),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def search_relevant(self, query: str, top_k: int = 3) -> list[dict]:
        """按 Jaccard 相似度检索相关历史经验。"""
        if not self.path.exists():
            return []
        query_tags = self._extract_tags(query)
        if not query_tags:
            return []

        results: list[tuple[float, dict]] = []
        for entry in self._iter_entries():
            entry_tags = set(entry.get("tags", []))
            sim = self._jaccard(query_tags, entry_tags)
            if sim > 0:
                results.append((sim, entry))
        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results[:top_k]]

    def _iter_entries(self) -> list[dict]:
        """遍历 JSONL 文件所有条目。"""
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    @classmethod
    def _extract_tags(cls, text: str) -> set[str]:
        """简单中文关键词提取:中文连续段内切 2/3 字滑动窗口,过滤含停用字的窗口。

        使用滑动窗口而非单次贪婪匹配,可同时保留如 "付款" 与 "付款条款",
        让 Jaccard 检索在粒度不同时仍能命中。
        """
        if not text:
            return set()
        # 仅取连续中文段,在段内做 2 字 / 3 字滑窗
        segments = re.findall(r"[一-鿿]+", text)
        grams: set[str] = set()
        for seg in segments:
            for n in (2, 3):
                for i in range(len(seg) - n + 1):
                    grams.add(seg[i : i + n])
        return {w for w in grams if not any(c in cls._STOPWORDS for c in w)}

    @staticmethod
    def _jaccard(a: set, b: set) -> float:
        """Jaccard 相似度 = |A∩B| / |A∪B|。"""
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)
