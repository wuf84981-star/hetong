"""关键词匹配器 — 支持正则、否定/例外语境判定，供风险/合规规则引擎共用。

修复与增强早期实现的两个问题：
1. 早期 `keyword in clause.content` 是**字面子串**匹配，导致像 `"仅由.*法院管辖"` 这样
   含正则元字符的规则**永远命中不了**（把 `.*` 当普通字符找）。本模块自动识别正则并用 re 匹配。
2. 早期无否定/例外判断，`"本条不构成无限责任"` 会被 `"无限责任"` 误命中。本模块在命中位置
   前的小窗口内检测否定线索（不构成/不承担/无需/除…外 等），命中则判为「被否定」不计入。

注意：这是启发式的中文语境判断，用于降低明显误报，不追求 NLP 级精度；语义层判断仍交给大模型。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 正则元字符（出现其一即按正则处理）
_REGEX_META = set(".*+?[]()|^$\\{}")

# 命中位置前窗口内的否定/例外线索
_NEGATION_CUES = (
    "不构成", "不属于", "不视为", "不承担", "不得", "不会", "不存在", "无需",
    "毋须", "免于", "免除", "并非", "而非", "均不", "没有", "无此",
)
# 命中位置后窗口内的例外线索
_EXCEPTION_CUES_AFTER = ("除外", "的除外", "情形除外")

_NEG_WINDOW_BEFORE = 12
_EXC_WINDOW_AFTER = 8


@dataclass
class KeywordHit:
    keyword: str
    matched_text: str
    start: int
    end: int
    negated: bool


def _is_regex(pattern: str) -> bool:
    return any(ch in _REGEX_META for ch in pattern)


def _is_negated(text: str, start: int, end: int) -> bool:
    """判断命中片段是否处于否定/例外语境。"""
    before = text[max(0, start - _NEG_WINDOW_BEFORE):start]
    if any(cue in before for cue in _NEGATION_CUES):
        return True
    after = text[end:end + _EXC_WINDOW_AFTER]
    if any(cue in after for cue in _EXCEPTION_CUES_AFTER):
        return True
    return False


def find_hit(text: str, keyword: str) -> KeywordHit | None:
    """在 text 中查找 keyword（自动区分正则/字面），返回首个「非否定」命中。

    若所有命中都处于否定语境，返回 None（视为未命中）。
    """
    if not text or not keyword:
        return None

    if _is_regex(keyword):
        try:
            pattern = re.compile(keyword)
        except re.error:
            # 非法正则退化为字面查找
            return _literal_hit(text, keyword)
        for m in pattern.finditer(text):
            negated = _is_negated(text, m.start(), m.end())
            hit = KeywordHit(keyword, m.group(0), m.start(), m.end(), negated)
            if not negated:
                return hit
        return None

    return _literal_hit(text, keyword)


def _literal_hit(text: str, keyword: str) -> KeywordHit | None:
    start = 0
    while True:
        idx = text.find(keyword, start)
        if idx == -1:
            return None
        end = idx + len(keyword)
        negated = _is_negated(text, idx, end)
        if not negated:
            return KeywordHit(keyword, keyword, idx, end, False)
        start = end


def scan(text: str, keywords: list[str]) -> KeywordHit | None:
    """扫描一组关键词，返回首个非否定命中；全部未命中或被否定则返回 None。"""
    for kw in keywords:
        hit = find_hit(text, kw)
        if hit is not None:
            return hit
    return None
