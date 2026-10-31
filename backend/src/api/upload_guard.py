"""上传文件安全校验 — 大小限制、扩展名/魔数一致性、文件名净化。

防护点：
- 大小上限（MAX_UPLOAD_SIZE_MB），防止超大文件打爆解析器/磁盘。
- 扩展名与文件头「魔数」一致性校验，防止伪装扩展名（如把可执行文件改名 .pdf）。
- 文件名净化：只保留 basename，剥离路径分隔符，防目录穿越。
"""

from __future__ import annotations

import os

from ..config import settings

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}

# 文件头魔数（扩展名 → 允许的起始字节序列）
_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF",),
    ".docx": (b"PK\x03\x04",),          # docx 是 zip 容器
    ".doc": (b"\xd0\xcf\x11\xe0",),     # 旧版 OLE 复合文档
    ".txt": (),                          # 纯文本不校验魔数
}


class UploadValidationError(ValueError):
    """上传文件不合法。"""


def sanitize_filename(filename: str) -> str:
    """净化文件名：只取 basename，替换危险字符。"""
    name = os.path.basename(filename or "").replace("\\", "_").replace("/", "_")
    name = name.strip().lstrip(".") or "unnamed"
    return name[:255]


def validate_upload(filename: str, content: bytes) -> str:
    """校验上传文件，返回净化后的文件名；不合法时抛 UploadValidationError。"""
    safe_name = sanitize_filename(filename)
    ext = os.path.splitext(safe_name)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(f"不支持的文件格式: {ext or '(无扩展名)'}")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) == 0:
        raise UploadValidationError("文件为空")
    if len(content) > max_bytes:
        raise UploadValidationError(
            f"文件过大（{len(content) / 1024 / 1024:.1f}MB），上限为 {settings.MAX_UPLOAD_SIZE_MB}MB"
        )

    magics = _MAGIC.get(ext, ())
    if magics and not any(content.startswith(m) for m in magics):
        raise UploadValidationError(
            f"文件内容与扩展名 {ext} 不匹配（可能是伪装的文件类型）"
        )

    if ext == ".txt":
        # 纯文本需可按 UTF-8/GBK 解码，避免二进制伪装
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content.decode("gbk")
            except UnicodeDecodeError:
                raise UploadValidationError("文本文件编码无法识别（需 UTF-8 或 GBK）")

    return safe_name
