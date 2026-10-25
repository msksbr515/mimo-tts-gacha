# -*- coding: utf-8 -*-
"""读取并校验 config.yaml，整理成不可变的配置对象。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_FILE = "config.yaml"
DOTENV_FILE = ".env"


class ConfigError(Exception):
    """config.yaml 读取或校验失败。"""


def load_dotenv(path: Path) -> None:
    """把 .env 里的 KEY=VALUE 补进 os.environ（不覆盖已存在的变量）。

    只处理最简单的写法：一行一对、支持 # 注释、可选引号、可带 export 前缀。
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def need(cfg: dict, dotted: str):
    """按 a.b.c 取配置项，缺了就报错并指出具体键。"""
    node = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ConfigError(f"config.yaml 缺少 {dotted}")
        node = node[part]
    return node


def optional(cfg: dict, dotted: str, default):
    """取可选配置项，缺失时返回默认值。"""
    node = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


@dataclass(frozen=True)
class ApiConfig:
    base_url: str
    model: str
    api_key: str
    audio_format: str
    voice_mime: str


@dataclass(frozen=True)
class Paths:
    input: Path
    output: Path
    voice: Path
    timestamped: bool = True


@dataclass(frozen=True)
class PauseConfig:
    enabled: bool
    marker: str
    scope: str
    repeat: int


@dataclass(frozen=True)
class QualityConfig:
    retry: int
    max_silence: float
    max_gap: float
    min_wpm: float
    min_words: int
    duration_factor: float
    duration_bonus: float


@dataclass(frozen=True)
class RequestConfig:
    concurrency: int
    rpm: float
    retries: int
    timeout: float
    delay: float


@dataclass(frozen=True)
class RunConfig:
    start: int
    limit: int
    force: bool
    dry_run: bool


@dataclass(frozen=True)
class LogConfig:
    enabled: bool
    dir: Path


@dataclass(frozen=True)
class Settings:
    base: Path
    api: ApiConfig
    paths: Paths
    prompt: str
    pause: PauseConfig
    quality: QualityConfig
    request: RequestConfig
    run: RunConfig
    log: LogConfig

    @classmethod
    def load(cls, base: Path, input_override: Path | None = None) -> "Settings":
        """读 <base>/config.yaml；input_override 用于命令行指定的 txt。"""
        load_dotenv(base / DOTENV_FILE)
        path = base / CONFIG_FILE
        if not path.is_file():
            raise ConfigError(f"找不到配置文件：{path}")
        try:
            with path.open(encoding="utf-8") as handle:
                cfg = yaml.safe_load(handle) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"config.yaml 语法错误：{exc}") from exc
        if not isinstance(cfg, dict):
            raise ConfigError("config.yaml 顶层必须是映射（key: value）")

        # 优先级：环境变量 > .env > config.yaml 里写死的值
        api_key = (os.environ.get("MIMO_API_KEY", "").strip()
                   or str(need(cfg, "api.api_key") or "").strip())

        return cls(
            base=base,
            api=ApiConfig(
                base_url=str(need(cfg, "api.base_url")),
                model=str(need(cfg, "api.model")),
                api_key=api_key,
                audio_format=str(need(cfg, "api.audio_format")),
                voice_mime=str(need(cfg, "api.voice_mime")),
            ),
            paths=Paths(
                input=input_override or (base / need(cfg, "paths.input")),
                output=base / need(cfg, "paths.output"),
                voice=base / need(cfg, "paths.voice"),
                timestamped=bool(optional(cfg, "paths.timestamped", True)),
            ),
            prompt=str(need(cfg, "prompt")),
            pause=PauseConfig(
                enabled=bool(need(cfg, "pause.enabled")),
                marker=str(need(cfg, "pause.marker")),
                scope=str(need(cfg, "pause.scope")),
                repeat=int(need(cfg, "pause.repeat")),
            ),
            quality=QualityConfig(
                retry=int(need(cfg, "quality.retry")),
                max_silence=float(need(cfg, "quality.max_silence")),
                max_gap=float(need(cfg, "quality.max_gap")),
                min_wpm=float(need(cfg, "quality.min_wpm")),
                min_words=int(need(cfg, "quality.min_words")),
                duration_factor=float(need(cfg, "quality.duration_factor")),
                duration_bonus=float(need(cfg, "quality.duration_bonus")),
            ),
            request=RequestConfig(
                concurrency=int(need(cfg, "request.concurrency")),
                rpm=float(need(cfg, "request.rpm")),
                retries=int(need(cfg, "request.retries")),
                timeout=float(need(cfg, "request.timeout")),
                delay=float(need(cfg, "request.delay")),
            ),
            run=RunConfig(
                start=int(need(cfg, "run.start")),
                limit=int(need(cfg, "run.limit")),
                force=bool(need(cfg, "run.force")),
                dry_run=bool(need(cfg, "run.dry_run")),
            ),
            log=LogConfig(
                enabled=bool(need(cfg, "log.enabled")),
                dir=base / optional(cfg, "log.dir", "logs"),
            ),
        )

    def speak_text(self, text: str) -> str:
        """按停顿配置处理一行文本。"""
        from .pause import insert_pause_markers

        if not self.pause.enabled:
            return text
        return insert_pause_markers(text, self.pause.marker,
                                    self.pause.scope, self.pause.repeat)
