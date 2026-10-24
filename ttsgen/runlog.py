# -*- coding: utf-8 -*-
"""运行日志：TSV，只记成功(OK)与失败(FAIL)，跳过的条目不写。"""

from __future__ import annotations

import threading
import time
from pathlib import Path


class RunLog:
    HEADER = ("time", "status", "line", "file", "duration", "silence",
              "max_gap", "wpm", "retries", "note")

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.enabled = enabled
        self.path = path
        self._handle = None
        self._lock = threading.Lock()
        if not enabled:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists() or path.stat().st_size == 0
        self._handle = path.open("a", encoding="utf-8", newline="")
        if is_new:
            self._handle.write("\t".join(self.HEADER) + "\n")
            self._handle.flush()

    def write(self, status: str, line_no: int, filename: str, *, duration: str = "",
              silence: str = "", max_gap: str = "", wpm: str = "", retries: int = 0,
              note: str = "") -> None:
        if not self._handle:
            return
        row = [time.strftime("%Y-%m-%d %H:%M:%S"), status, str(line_no), filename,
               duration, silence, max_gap, wpm, str(retries), note]
        with self._lock:
            self._handle.write("\t".join(value.replace("\t", " ") for value in row) + "\n")
            self._handle.flush()

    def close(self) -> None:
        if not self._handle:
            return
        with self._lock:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "RunLog":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
