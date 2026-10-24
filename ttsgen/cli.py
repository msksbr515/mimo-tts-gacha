# -*- coding: utf-8 -*-
"""命令行入口：只接受一个可选的 txt 位置参数，其余设置全在 config.yaml。"""

from __future__ import annotations

import sys
from pathlib import Path

from .config import ConfigError, Settings
from .console import setup_console
from .runner import run

USAGE = ("用法：python main.py [文本文件]\n"
         "其余设置都在 config.yaml 里。")


def resolve_input(base: Path, args: list[str]) -> Path | None:
    """把命令行里的 txt 解析成绝对路径：先按当前目录，再按脚本目录。"""
    if not args:
        return None
    given = Path(args[0]).expanduser()
    if given.is_absolute():
        return given
    from_cwd = Path.cwd() / given
    return from_cwd if from_cwd.exists() else base / given


def main(base: Path | None = None, argv: list[str] | None = None) -> int:
    """程序主入口；base 是 config.yaml 所在目录。"""
    setup_console()

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) > 1 or (args and args[0].startswith("-")):
        print(USAGE, file=sys.stderr)
        return 2

    base = (base or Path.cwd()).resolve()
    try:
        settings = Settings.load(base, resolve_input(base, args))
    except ConfigError as exc:
        print(f"[配置错误] {exc}", file=sys.stderr)
        return 2

    return run(settings)
