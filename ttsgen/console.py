# -*- coding: utf-8 -*-
"""控制台：编码适配 + 线程安全输出。"""

from __future__ import annotations

import os
import sys
import threading

_PRINT_LOCK = threading.Lock()


def _is_windows_console(stream) -> bool:
    """这个流是否绑在真正的 Windows 控制台上（cmd / PowerShell / Windows Terminal）。"""
    try:
        import ctypes
        import msvcrt

        handle = msvcrt.get_osfhandle(stream.fileno())
        mode = ctypes.c_uint()
        return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))
    except Exception:
        return False


def setup_console() -> None:
    """固定 stdout/stderr 编码：控制台交给 Python 的宽字符 API，管道统一 UTF-8。"""
    if os.name != "nt":
        return

    override = (os.environ.get("TTS_CONSOLE_ENCODING") or "").strip()

    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            if _is_windows_console(stream):
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding=override or "utf-8", errors="replace")
        except Exception:
            pass


def log(message: str, *, err: bool = False) -> None:
    """线程安全的整行输出。"""
    with _PRINT_LOCK:
        print(message, file=sys.stderr if err else sys.stdout, flush=True)
