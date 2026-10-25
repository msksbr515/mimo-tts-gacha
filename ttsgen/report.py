# -*- coding: utf-8 -*-
"""每次运行生成一份 Markdown 报告，便于留痕与复盘。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings

PIPE = chr(124)
FENCE = "```"


@dataclass
class ItemRecord:
    """单条合成结果，报告表格的一行。"""

    lineno: int
    text: str
    filename: str = ""
    status: str = "ok"
    duration: str = ""
    silence: str = ""
    max_gap: str = ""
    wpm: str = ""
    retries: int = 0
    note: str = ""


@dataclass
class RunRecords:
    """一次运行的全部记录。"""

    items: list[ItemRecord] = field(default_factory=list)


def _cell(value: str, limit: int = 40) -> str:
    """表格单元格转义：竖线会破坏表格，超长截断。"""
    text = str(value).replace(PIPE, "／").replace(chr(10), " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _prompt_summary(prompt: str, limit: int = 60) -> str:
    text = " ".join(prompt.split())
    if not text:
        return "（空，使用接口默认风格）"
    return text if len(text) <= limit else text[: limit - 3] + "..."


def render(*, stamp: str, started_at: float, elapsed: float, settings: Settings,
           input_path: Path, total_lines: int, planned: int, output_dir: Path,
           log_path: Path, records: list[ItemRecord], skipped: int) -> str:
    """生成报告文本。"""
    ok = [r for r in records if r.status == "ok"]
    failed = [r for r in records if r.status != "ok"]
    retried = [r for r in records if r.retries > 0]
    total_retries = sum(r.retries for r in records)

    lines: list[str] = [
        f"# 合成报告 {stamp}",
        "",
        "## 1. 概况",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 开始时间 | {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(started_at))} |",
        f"| 用时 | {elapsed:.1f} 秒 |",
        f"| 输入文件 | {_cell(input_path.name)}（共 {total_lines} 行，本次 {planned} 条） |",
        f"| 输出目录 | {_cell(str(output_dir), 80)} |",
        f"| 运行日志 | {_cell(log_path.name if log_path else '（关闭）', 60)} |",
        f"| 模型 | {_cell(settings.api.model)} |",
        f"| 停顿标记 | "
        f"{_cell(settings.pause.marker) + ' / ' + settings.pause.scope + ' / ×' + str(settings.pause.repeat) if settings.pause.enabled else '关闭'} |",
        f"| 风格提示 | {_cell(_prompt_summary(settings.prompt), 80)} |",
        "",
        "## 2. 结果统计",
        "",
        "| 指标 | 数量 |",
        "| --- | --- |",
        f"| 成功 | {len(ok)} |",
        f"| 跳过（历史已存在） | {skipped} |",
        f"| 失败 | {len(failed)} |",
        f"| 触发重抽的条目 | {len(retried)} |",
        f"| 重抽总次数 | {total_retries} |",
        "",
    ]

    lines += [
        "## 3. 成功条目",
        "",
    ]
    if ok:
        lines += [
            "| 行号 | 文件 | 时长(s) | 静音 | 最长停顿(s) | 语速(wpm) | 重抽 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for record in sorted(ok, key=lambda r: r.lineno):
            lines.append(
                f"| {record.lineno} | {_cell(record.filename, 46)} | {record.duration} | "
                f"{record.silence} | {record.max_gap} | {record.wpm} | {record.retries} |"
            )
    else:
        lines.append("本次没有新生成的音频。")

    lines += ["", "## 4. 失败条目", ""]
    if failed:
        lines += [
            "| 行号 | 文本片段 | 原因 |",
            "| --- | --- | --- |",
        ]
        for record in sorted(failed, key=lambda r: r.lineno):
            lines.append(
                f"| {record.lineno} | {_cell(record.text, 40)} | {_cell(record.note, 90)} |"
            )
        lines += ["", "> 失败或判定拖沓的条目不会生成音频，重跑时会自动重试。"]
    else:
        lines.append("无。")

    lines += [
        "",
        "## 5. 本次配置",
        "",
        f"- 拖沓重抽上限：{settings.quality.retry} 次",
        f"- 静音占比上限：{settings.quality.max_silence}",
        f"- 最长静音上限：{settings.quality.max_gap} 秒",
        f"- 语速下限：{settings.quality.min_wpm} wpm（不少于 {settings.quality.min_words} 词时判定）",
        f"- 并发上限：{settings.request.concurrency}，限速 {settings.request.rpm:g} RPM",
        f"- 单次请求超时：{settings.request.timeout:g} 秒，失败重试 {settings.request.retries} 次",
        "",
    ]
    return chr(10).join(lines)


def write(path: Path, text: str) -> Path:
    """写报告文件；目录不存在时自动创建。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
