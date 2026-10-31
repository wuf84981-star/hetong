"""
文档解析器 — 支持PDF和DOCX格式的合同文档解析。

将合同文档转换为纯文本，保留结构信息（标题层级、段落分隔）。
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document as DocxDocument
from PyPDF2 import PdfReader


class DocumentParser:
    """统一的文档解析入口，根据文件后缀自动选择解析策略。"""

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}

    def parse(self, file_path: str | Path) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {ext}")

        if ext == ".pdf":
            return self._parse_pdf(path)
        elif ext in (".docx", ".doc"):
            return self._parse_docx(path)
        else:
            return path.read_text(encoding="utf-8")

    def _parse_pdf(self, path: Path) -> str:
        reader = PdfReader(str(path))
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        return "\n\n".join(pages)

    def _parse_docx(self, path: Path) -> str:
        doc = DocxDocument(str(path))
        paragraphs: list[str] = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            style = para.style.name if para.style else ""
            if "Heading" in style:
                paragraphs.append(f"\n{'#' * self._heading_level(style)} {text}")
            else:
                paragraphs.append(text)
        return "\n\n".join(paragraphs)

    @staticmethod
    def _heading_level(style_name: str) -> int:
        match = re.search(r"(\d+)", style_name)
        return int(match.group(1)) if match else 1


def parse_raw_text_to_sections(text: str) -> list[dict]:
    """
    将原始合同文本按章节切分。
    识别常见的中文合同章节格式：
    - 第一条、第二条...
    - 一、二、三...
    - 1. 2. 3. / 1、2、3
    """
    patterns = [
        r"(第[一二三四五六七八九十百]+条\s*.+)",
        r"(第\d+条\s*.+)",
        r"([一二三四五六七八九十]+、\s*.+)",
        r"(\d+[\.、]\s*.+)",
        r"(#+\s*.+)",
    ]

    combined = "|".join(patterns)
    sections: list[dict] = []
    last_pos = 0
    last_title = "前言"
    heading_matched = False

    for match in re.finditer(combined, text):
        heading_matched = True
        if last_pos > 0 or match.start() > 0:
            content = text[last_pos : match.start()].strip()
            if content:
                sections.append({"title": last_title, "content": content})

        last_title = match.group(0).strip()
        last_pos = match.end()

    remaining = text[last_pos:].strip()
    if remaining:
        # 没有任何标题匹配时（如纯叙述文本），默认标题用「全文」
        sections.append({"title": last_title if heading_matched else "全文", "content": remaining})

    if not sections and text.strip():
        sections.append({"title": "全文", "content": text.strip()})

    return sections
