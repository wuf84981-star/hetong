"""版本对比路由 — 文本差异比较。

合同文本往往整段无换行，逐行比较毫无意义；
这里按中文句读（。；！？、换行）切段后用 difflib 对齐，
再对「改前/改后」的段落做句内字符级标注。
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/diff", tags=["diff"])

# 一段 = 一句或一行：句子主体 + 可选的句末标点
_SEGMENT_RE = re.compile(r"[^。；;！？!?\n]+[。；;！？!?\n]?")


class DiffRequest(BaseModel):
    old_text: str
    new_text: str


def _split_segments(text: str) -> list[str]:
    """把合同文本切成句子段，丢弃空白。"""
    return [m.group(0).strip() for m in _SEGMENT_RE.finditer(text) if m.group(0).strip()]


def _inline_change(old_seg: str, new_seg: str) -> tuple[str, str]:
    """段内再做字符级比较，返回 (改前含【】标删除, 改后含【】标新增)。"""
    sm = SequenceMatcher(None, old_seg, new_seg, autojunk=False)
    old_out, new_out = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        old_part, new_part = old_seg[i1:i2], new_seg[j1:j2]
        if tag == "equal":
            old_out.append(old_part)
            new_out.append(new_part)
        elif tag == "delete":
            old_out.append(f"【{old_part}】")
        elif tag == "insert":
            new_out.append(f"【{new_part}】")
        else:  # replace
            old_out.append(f"【{old_part}】")
            new_out.append(f"【{new_part}】")
    return "".join(old_out), "".join(new_out)


@router.post("")
async def compare_diff(request: DiffRequest):
    """比较两个文本的差异（句子段级对齐 + 段内字符级标注）。"""
    old_segs = _split_segments(request.old_text)
    new_segs = _split_segments(request.new_text)

    matcher = SequenceMatcher(None, old_segs, new_segs, autojunk=False)

    items: list[dict] = []
    added = removed = changed = unchanged = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for seg in old_segs[i1:i2]:
                items.append({"type": "unchanged", "line": len(items) + 1, "content": seg})
                unchanged += 1
        elif tag == "delete":
            for seg in old_segs[i1:i2]:
                items.append({"type": "removed", "line": len(items) + 1, "content": seg, "old_value": seg})
                removed += 1
        elif tag == "insert":
            for seg in new_segs[j1:j2]:
                items.append({"type": "added", "line": len(items) + 1, "content": seg, "new_value": seg})
                added += 1
        else:  # replace：两侧段落配对呈现
            old_block = "".join(old_segs[i1:i2])
            new_block = "".join(new_segs[j1:j2])
            old_marked, new_marked = _inline_change(old_block, new_block)
            items.append({
                "type": "changed",
                "line": len(items) + 1,
                "content": f"{old_block} → {new_block}",
                "old_value": old_marked,
                "new_value": new_marked,
            })
            changed += 1

    total = added + removed + changed
    if total == 0:
        summary = "两份文本逐段一致，未发现改动。"
    else:
        summary = (
            f"共发现 {total} 处改动：新增 {added} 段、删除 {removed} 段、修改 {changed} 段，"
            f"未变 {unchanged} 段。改动处以【】标出。"
        )

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
        "items": items,
        "summary": summary,
    }
