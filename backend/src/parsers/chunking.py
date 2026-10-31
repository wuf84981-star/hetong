"""长文本分块 — 按条款/段落边界切分，避免超长合同被直接截断丢信息。

早期实现把超过 15000 字的合同直接 `raw_text[:15000]` 截断，后半部分条款完全丢失。
本模块按「章节边界」把长文本切成多个不超过 max_chars 的块，供 Agent 逐块提取后合并，
从而覆盖完整合同（代价是多次 LLM 调用）。
"""

from __future__ import annotations


def chunk_sections(
    raw_text: str,
    sections: list[dict],
    max_chars: int = 12000,
) -> list[str]:
    """将合同按章节边界分块。

    Args:
        raw_text: 合同全文（sections 为空时按定长窗口兜底切分）
        sections: parse_raw_text_to_sections 的输出，每项含 title/content
        max_chars: 单块最大字符数

    Returns:
        分块后的文本列表；每块尽量保持章节完整。若全文本身不超限则返回单元素列表。
    """
    if len(raw_text) <= max_chars:
        return [raw_text] if raw_text else []

    if not sections:
        return _window_split(raw_text, max_chars)

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def _flush():
        nonlocal buf, buf_len
        if buf:
            chunks.append("\n\n".join(buf))
            buf = []
            buf_len = 0

    for sec in sections:
        title = sec.get("title", "")
        content = sec.get("content", "")
        block = f"{title}\n{content}".strip() if title else content
        if not block:
            continue

        if len(block) > max_chars:
            # 单个章节就超限：先冲掉缓冲，再把该章节按窗口拆分
            _flush()
            chunks.extend(_window_split(block, max_chars))
            continue

        if buf_len + len(block) > max_chars:
            _flush()
        buf.append(block)
        buf_len += len(block)

    _flush()
    return chunks


def _window_split(text: str, max_chars: int) -> list[str]:
    """定长窗口切分，尽量在换行处断开以减少切碎句子。"""
    parts: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            nl = text.rfind("\n", start, end)
            if nl > start + int(max_chars * 0.5):
                end = nl
        parts.append(text[start:end])
        start = end
    return parts
