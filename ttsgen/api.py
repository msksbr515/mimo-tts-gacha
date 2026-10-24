# -*- coding: utf-8 -*-
"""接口层：错误分类、请求封装、语音合成。"""

from __future__ import annotations

import base64
import random
import time

from openai import OpenAI

from .config import Settings
from .console import log
from .ratelimit import AdaptiveGate, RateLimiter, call_with_deadline

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def http_status(exc: BaseException) -> int | None:
    """从异常里取 HTTP 状态码，取不到返回 None（连接 / 超时类错误）。"""
    for attr in ("status_code", "http_status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def is_retryable(status: int | None) -> bool:
    """408/429/5xx 和连接类错误才值得重试；其余 4xx 直接失败。"""
    return True if status is None else status in RETRYABLE_STATUS


def retry_after(exc: BaseException) -> float | None:
    """读取 429 响应里的 Retry-After（秒）。"""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if not headers:
        return None
    try:
        return max(0.0, float(headers.get("retry-after")))
    except (TypeError, ValueError):
        return None


class Synthesizer:
    """持有客户端与并发/限速设施，按配置合成单条音频。

    返回音频原始字节，不做任何后处理。
    """

    def __init__(self, settings: Settings, limiter: RateLimiter | None = None,
                 gate: AdaptiveGate | None = None) -> None:
        self.settings = settings
        self.limiter = limiter
        self.gate = gate
        self.client = OpenAI(api_key=settings.api.api_key,
                             base_url=settings.api.base_url, max_retries=0)
        self._voice_uri = self._build_voice_uri(settings)

    @staticmethod
    def _build_voice_uri(settings: Settings) -> str:
        """参考音频整段 base64 成 data URL，只在启动时算一次。"""
        encoded = base64.b64encode(settings.paths.voice.read_bytes()).decode("utf-8")
        return f"data:{settings.api.voice_mime};base64,{encoded}"

    def synthesize(self, text: str) -> bytes:
        """合成一条文本；失败按 request.retries 重试，429 会通知闸门降速。"""
        cfg = self.settings.api
        req = self.settings.request
        last_error: Exception | None = None

        for attempt in range(1, max(1, req.retries) + 1):
            if self.limiter is not None:
                self.limiter.acquire()
            if self.gate is not None:
                self.gate.acquire()
            success = False
            try:
                completion = call_with_deadline(
                    lambda: self.client.chat.completions.create(
                        model=cfg.model,
                        messages=[
                            {"role": "user", "content": self.settings.prompt},
                            {"role": "assistant", "content": text},
                        ],
                        audio={"format": cfg.audio_format, "voice": self._voice_uri},
                        timeout=req.timeout,
                    ),
                    req.timeout,
                )
                message = completion.choices[0].message
                audio = getattr(message, "audio", None)
                if audio is None or not getattr(audio, "data", None):
                    raise ValueError(f"接口没有返回音频数据（message={message!r}）")
                success = True
                return base64.b64decode(audio.data)

            except Exception as exc:
                last_error = exc
                status = http_status(exc)
                if not is_retryable(status):
                    raise RuntimeError(f"请求被拒绝（HTTP {status}）：{exc}") from exc
                if attempt >= req.retries:
                    break

                wait = self._backoff(exc, status, attempt)
                self._report(exc, status, wait, attempt)
                time.sleep(wait + random.uniform(0.0, wait * 0.25))
            finally:
                if self.gate is not None:
                    self.gate.release(success)

        raise RuntimeError(f"重试 {req.retries} 次仍失败：{last_error}")

    def _backoff(self, exc: Exception, status: int | None, attempt: int) -> float:
        """超时立刻重发；429 优先用 Retry-After，其余指数退避。"""
        timed_out = isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower()
        if timed_out:
            return 1.0
        wait = min(2 ** (attempt - 1), 30)
        wait = max(wait, retry_after(exc) or 0.0)
        if status == 429:
            wait = max(wait, min(5.0 * 2 ** (attempt - 1), 45.0))
        return wait

    def _report(self, exc: Exception, status: int | None, wait: float, attempt: int) -> None:
        timed_out = isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower()
        if timed_out:
            log(f"    第 {attempt} 次超时（{self.settings.request.timeout:g}s），"
                f"{wait:.0f}s 后重发", err=True)
        elif status == 429:
            new_limit = None
            if self.gate is not None:
                new_limit = self.gate.penalize(cooldown=max(5.0, wait))
            if self.limiter is not None:
                self.limiter.cooldown(min(wait, 20))
            limit_text = f"，并发降到 {new_limit}" if new_limit else ""
            log(f"    触发限流 429{limit_text}，暂停 {wait:.0f}s 后重试", err=True)
        else:
            log(f"    第 {attempt} 次失败：{exc}，{wait:.0f}s 后重试", err=True)
