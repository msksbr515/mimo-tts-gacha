# -*- coding: utf-8 -*-
"""拖沓检测：只看静音分布和语速，不改动音频本身。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioStats:
    duration: float
    silence: float
    max_gap: float
    speech: float

    @property
    def silence_percent(self) -> float:
        return self.silence * 100

    def wpm(self, words: int) -> float:
        return words / self.speech * 60


def analyze_wav(data: bytes) -> AudioStats | None:
    """粗测 wav 的时长、静音占比、最长静音；解析失败返回 None。

    10ms 一帧、每帧抽 1/5 采样估能量，只用来判断拖不拖沓，不追求精确。
    """
    try:
        if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            return None
        pos = 12
        channels = rate = bits = 0
        pcm = b""
        while pos + 8 <= len(data):
            chunk_id = data[pos:pos + 4]
            size = int.from_bytes(data[pos + 4:pos + 8], "little")
            body = data[pos + 8:pos + 8 + size]
            if chunk_id == b"fmt " and size >= 16:
                channels = int.from_bytes(body[2:4], "little")
                rate = int.from_bytes(body[4:8], "little")
                bits = int.from_bytes(body[14:16], "little")
            elif chunk_id == b"data":
                pcm = body
                break
            pos += 8 + size + (size & 1)
        if not pcm or bits != 16 or rate <= 0 or channels <= 0:
            return None

        frame_bytes = 2 * channels
        hop = max(frame_bytes, int(rate * 0.01) * frame_bytes)
        stride = frame_bytes * 5
        levels = []
        for start in range(0, len(pcm) - hop + 1, hop):
            window = pcm[start:start + hop:stride]
            total = count = 0
            for i in range(0, len(window) - 1, 2):
                total += abs(int.from_bytes(window[i:i + 2], "little", signed=True))
                count += 1
            if count:
                levels.append(total / count)
        if not levels:
            return None

        threshold = max(max(levels) * 0.02, 40)
        runs, run = [], 0
        for value in levels:
            if value < threshold:
                run += 1
            elif run:
                runs.append(run)
                run = 0
        if run:
            runs.append(run)

        duration = len(levels) * 0.01
        silence = sum(runs) * 0.01
        return AudioStats(
            duration=duration,
            silence=silence / duration if duration else 0.0,
            max_gap=max(runs, default=0) * 0.01,
            speech=max(0.001, duration - silence),
        )
    except Exception:
        return None


def judge_drag(stats: AudioStats | None, words: int, quality) -> tuple[bool, str]:
    """判断这条是否太拖沓，返回 (是否拖沓, 原因)。quality 需有阈值属性。"""
    if stats is None:
        return False, ""

    reasons: list[str] = []
    if stats.duration > words * quality.duration_factor + quality.duration_bonus:
        reasons.append(f"时长 {stats.duration:.1f}s")
    if stats.silence > quality.max_silence:
        reasons.append(f"静音 {stats.silence_percent:.0f}%")
    if stats.max_gap > quality.max_gap:
        reasons.append(f"最长停顿 {stats.max_gap:.2f}s")
    if words >= quality.min_words and stats.wpm(words) < quality.min_wpm:
        reasons.append(f"语速 {stats.wpm(words):.0f}wpm")
    return bool(reasons), "，".join(reasons)
