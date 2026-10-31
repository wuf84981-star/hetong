"""合同文件工具 — 让 Agent 按需读取合同上下文。

侑夕《你不知道的 Agent》: "文件系统天然适合做这个接口——
工具调用经常返回大量 JSON,直接写入文件,Agent 通过 grep/rg 按需读取。"
"""
from __future__ import annotations
import json
import re
from pathlib import Path


class ReadContractTextTool:
    """让 Agent 按需读取合同文本(全量 / 分段 / grep 搜索)。"""

    def __init__(self, path: str, max_chars: int = 12000, sections_path: str | None = None):
        self.path = Path(path)
        self.max_chars = max_chars
        # sidecar 文件: clause_extraction 提取后写入,供下游 Agent 用
        self.sections_path = Path(sections_path) if sections_path else self.path.with_suffix(".sections.json")

    def read_full(self) -> str:
        if not self.path.exists():
            raise FileNotFoundError(f"合同文件不存在: {self.path}")
        return self.path.read_text(encoding="utf-8")

    def read_section(self, section_id: str) -> str:
        sections_path = Path(self.sections_path)  # 兼容 str/Path 赋值
        if not sections_path.exists():
            raise ValueError(f"section '{section_id}' 不存在:sidecar 不可用,需先跑 clause_extraction ({sections_path})")
        sections = json.loads(sections_path.read_text(encoding="utf-8"))
        for s in sections:
            if s["id"] == section_id:
                return s["content"]
        raise ValueError(f"section '{section_id}' 不存在,可选: {[s['id'] for s in sections]}")

    def grep(self, pattern: str, context_lines: int = 2) -> str:
        if not self.path.exists():
            return ""
        text = self.path.read_text(encoding="utf-8")
        lines = text.split("\n")
        regex = re.compile(pattern)
        matches = []
        for i, line in enumerate(lines):
            if regex.search(line):
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                block = "\n".join(f"{j+1}: {lines[j]}" for j in range(start, end))
                matches.append(block)
        return "\n---\n".join(matches) if matches else "未找到匹配"