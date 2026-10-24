# -*- coding: utf-8 -*-
"""并发与限速：自适应并发闸门、令牌桶、硬超时调用。"""

from __future__ import annotations

import threading
import time


def call_with_deadline(func, seconds: float):
    """在子线程里执行阻塞调用，超过 seconds 秒就放弃等待。"""
    if seconds <= 0:
        return func()

    outcome: dict = {}

    def runner() -> None:
        try:
            outcome["value"] = func()
        except BaseException as exc:  # noqa: BLE001 - 原样抛回主线程
            outcome["error"] = exc

    thread = threading.Thread(target=runner, name="tts-call", daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        raise TimeoutError(f"请求超过 {seconds:g}s 未返回")
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


class AdaptiveGate:
    """自适应并发闸门：成功若干次加一路，遇 429 减半并冷却。"""

    def __init__(self, ceiling: int, start: int = 2, grow_after: int = 5) -> None:
        self.ceiling = max(1, ceiling)
        self.limit = max(1, min(start, self.ceiling))
        self.grow_after = max(1, grow_after)
        self.inflight = 0
        self._streak = 0
        self._cooldown_until = 0.0
        self._cv = threading.Condition()

    def acquire(self) -> None:
        """占一个并发位；被限流冷却时在这里等待。"""
        with self._cv:
            while True:
                now = time.monotonic()
                if now < self._cooldown_until:
                    self._cv.wait(min(0.5, self._cooldown_until - now))
                    continue
                if self.inflight < self.limit:
                    self.inflight += 1
                    return
                self._cv.wait(0.2)

    def release(self, success: bool) -> None:
        with self._cv:
            self.inflight = max(0, self.inflight - 1)
            if success:
                self._streak += 1
                if self._streak >= self.grow_after and self.limit < self.ceiling:
                    self.limit += 1
                    self._streak = 0
            self._cv.notify_all()

    def penalize(self, cooldown: float = 4.0) -> int:
        """429：并发减半并冷却，返回新的并发上限。"""
        with self._cv:
            self.limit = max(1, self.limit // 2)
            self._streak = 0
            self._cooldown_until = max(self._cooldown_until, time.monotonic() + cooldown)
            self._cv.notify_all()
            return self.limit


class RateLimiter:
    """跨线程共享的令牌桶限速器。"""

    def __init__(self, rpm: float, burst: int = 1) -> None:
        self.rate = rpm / 60.0 if rpm > 0 else 0.0
        self.capacity = max(1.0, float(burst)) if self.rate else 0.0
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """取一个令牌；不够就睡到够为止。"""
        if self.rate <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self.capacity,
                                   self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self.rate
            time.sleep(min(wait, 1.0))

    def cooldown(self, seconds: float) -> None:
        """遇到 429 时让所有线程一起停一下。"""
        if self.rate <= 0:
            return
        with self._lock:
            self._tokens = 0.0
            self._updated = max(self._updated, time.monotonic()) + max(0.0, seconds)
