"""结构化 Bad Case — 文章核心理念: 结构化才能被 LLM 高效复用。"""
from __future__ import annotations
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List


@dataclass
class IdentifiedRisk:
    """单条识别的风险(可关联到具体条款)。"""
    clause_id: str = ""
    clause_text_snippet: str = ""
    risk_type: str = ""
    risk_category: str = ""
    severity: str = "medium"
    description: str = ""


RISK_CATEGORIES = [
    "责任范围", "付款条款", "期限", "违约责任",
    "争议解决", "知识产权", "保密", "管辖法律",
    "不可抗力", "终止条件", "其他",
]


@dataclass
class StructuredBadCase:
    """完整 Bad Case — 文章核心 schema。"""
    review_id: str
    case_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    contract_type: str = ""
    industry: str = ""
    deal_size: str = ""
    identified_risks: List[IdentifiedRisk] = field(default_factory=list)
    problematic_clauses_summary: str = ""
    suggestion_or_lesson: str = ""
    keywords_for_retrieval: List[str] = field(default_factory=list)
    full_contract_text: str = ""
    input_summary: str = ""
    signal_type: str = ""
    severity: str = "medium"
    judge_score: float | None = None
    judge_rationale: str = ""
    state_warnings: List[str] = field(default_factory=list)
    state_degraded_steps: List[str] = field(default_factory=list)
    resolved: bool = False
    resolution: str = ""
    resolution_commit: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StructuredBadCase":
        risks_data = data.pop("identified_risks", [])
        bc = cls(**data)
        bc.identified_risks = [IdentifiedRisk(**r) for r in risks_data]
        return bc


def auto_extract_keywords(text: str, top_n: int = 20) -> List[str]:
    """自动从文本提取关键词(中文 n-gram + 停用词过滤)。"""
    if not text:
        return []
    stopwords = {
        "的", "是", "在", "和", "与", "或", "但", "也", "有", "为",
        "由", "对", "可", "应", "须", "将", "本", "该", "如", "等",
        "此", "它", "这", "那", "并", "且",
    }
    text_clean = re.sub(r"[^一-鿿]+", "", text)
    candidates = []
    # 4-gram 先(更长的 n-gram 更接近真实关键词,优先进入 top_n)
    for i in range(len(text_clean)):
        if i + 4 <= len(text_clean):
            candidates.append(text_clean[i:i+4])
    for i in range(len(text_clean)):
        if i + 3 <= len(text_clean):
            candidates.append(text_clean[i:i+3])
    for i in range(len(text_clean)):
        if i + 2 <= len(text_clean):
            candidates.append(text_clean[i:i+2])
    from collections import Counter
    counter = Counter(w for w in candidates if w not in stopwords)
    return [w for w, _ in counter.most_common(top_n)]


__all__ = ["StructuredBadCase", "IdentifiedRisk", "RISK_CATEGORIES", "auto_extract_keywords"]
