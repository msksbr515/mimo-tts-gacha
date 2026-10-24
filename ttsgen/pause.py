# -*- coding: utf-8 -*-
"""停顿标记：只在真实的句末标点后插入 []。

ASCII 标点（. ! ?）后面必须跟空格才算句子边界，中间允许夹收尾引号；
M.E.G. / J. Smith / Mr. / e.g. / 3.5 不算；全角标点不要求空格；行尾不插。
"""

from __future__ import annotations

CLOSERS = set("\"'”’）)]}】")

ABBREV_WORDS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "inc", "ltd", "co", "corp", "dept", "fig", "vol", "approx", "al",
}


def _looks_like_abbrev(text: str, dot_index: int) -> bool:
    """判断句点是否属于缩写：M.E.G. / U.S.、J. Smith、Mr. / Prof. / e.g.。"""
    start = dot_index
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    word = text[start:dot_index]
    if not word:
        return False
    if "." in word:
        return True
    if len(word) == 1 and word.isupper():
        return True
    return word.lower() in ABBREV_WORDS


def insert_pause_markers(text: str, marker: str = "[]", scope: str = "sentence",
                         repeat: int = 1) -> str:
    """在真实的句末标点后插入停顿标记，返回新文本。"""
    if not marker or repeat <= 0:
        return text
    marker = marker * repeat

    positions: dict[int, str] = {}

    for i, ch in enumerate(text):
        j = i + 1
        while j < len(text) and text[j] in CLOSERS:
            j += 1
        spaced = j < len(text) and text[j].isspace()
        tail = j - 1 if j > i + 1 else i

        if ch in "。！？…":
            if j < len(text):
                positions[tail] = positions.get(tail, "") + marker
        elif ch in "!?":
            if spaced:
                positions[tail] = positions.get(tail, "") + marker
        elif ch == ".":
            if spaced and not _looks_like_abbrev(text, i):
                positions[tail] = positions.get(tail, "") + marker
        elif scope == "clause":
            if ch in "，、；：":
                positions[tail] = positions.get(tail, "") + marker
            elif ch in ",;:—" and spaced:
                positions[tail] = positions.get(tail, "") + marker

    if not positions:
        return text

    out: list[str] = []
    for i, ch in enumerate(text):
        out.append(ch)
        if i in positions:
            out.append(positions[i])
    return "".join(out)
