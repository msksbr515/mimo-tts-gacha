# -*- coding: utf-8 -*-
"""读文本、挑出待合成条目、生成文件名片段。"""

from __future__ import annotations

import re
from pathlib import Path

ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")

_UNSAFE_CHARS = re.compile(r"[^\w\u3400-\u4dbf\u4e00-\u9fff\-]+", re.UNICODE)


def read_text_file(path: Path, encodings: tuple[str, ...] = ENCODINGS) -> list[str]:
    """读文本文件，自动识别 UTF-8 / UTF-8-BOM / GBK(GB18030)。"""
    data = path.read_bytes()
    for encoding in encodings:
        try:
            return data.decode(encoding).splitlines()
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace").splitlines()


def collect_items(lines: list[str]) -> list[tuple[int, str]]:
    """挑出非空行，返回 [(行号, 文本)]，行号即 txt 里的真实行号。"""
    return [(lineno, raw.strip())
            for lineno, raw in enumerate(lines, start=1) if raw.strip()]


def slugify(text: str, max_len: int = 40) -> str:
    """把一行文本压成安全的文件名片段。"""
    slug = _UNSAFE_CHARS.sub("_", text).strip("_-")
    slug = re.sub(r"_+", "_", slug).strip("_-")
    if not slug:
        return "line"
    return slug[:max_len].strip("_-") or "line"


def preview(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."
