# -*- coding: utf-8 -*-
"""批处理流程：遍历条目 → 合成 → 拖沓检测（不合格重抽）→ 落盘 → 记账。"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .api import Synthesizer
from .config import Settings
from .console import log
from .quality import analyze_wav, judge_drag
from .ratelimit import AdaptiveGate, RateLimiter
from .runlog import RunLog
from .text import collect_items, preview, read_text_file, slugify


def run(settings: Settings) -> int:
    """按配置跑一批，返回进程退出码：0 全成功，1 有失败，2 参数/文件问题。"""
    input_path = settings.paths.input
    if not input_path.is_file():
        print(f"[错误] 找不到文本文件：{input_path}", file=sys.stderr)
        return 2

    lines = read_text_file(input_path)
    items = collect_items(lines)
    if not items:
        print(f"[错误] {input_path} 里没有任何非空行。", file=sys.stderr)
        return 2

    items = items[max(1, settings.run.start) - 1:]
    if settings.run.limit > 0:
        items = items[: settings.run.limit]
    if not items:
        print("[错误] 配置里的 run.start 之后没有剩余的文本了。", file=sys.stderr)
        return 2

    if settings.run.dry_run:
        for lineno, text in items:
            print(f"[行 {lineno}] {settings.speak_text(text)}")
        return 0

    voice_path = settings.paths.voice
    if not voice_path.is_file():
        print(f"[错误] 找不到参考音频：{voice_path}", file=sys.stderr)
        return 2

    if not settings.api.api_key:
        print("[错误] 没有可用的 API key：在项目根目录的 .env 里写 "
              "MIMO_API_KEY=sk-xxx（可参考 .env.example），或设置同名环境变量。",
              file=sys.stderr)
        return 2

    workers = max(1, min(settings.request.concurrency, len(items), 32))
    limiter = RateLimiter(settings.request.rpm, burst=workers) if settings.request.rpm > 0 else None
    gate = AdaptiveGate(ceiling=workers, start=min(2, workers))
    synthesizer = Synthesizer(settings, limiter=limiter, gate=gate)

    stamp = time.strftime("%Y_%m_%d_%H_%M_%S")
    base_output = settings.paths.output
    output_dir = base_output / stamp if settings.paths.timestamped else base_output
    existing = collect_existing(base_output)
    ext = "." + settings.api.audio_format.strip(".").lower()
    width = max(4, len(str(max(lineno for lineno, _ in items))))

    log_path = settings.log.dir / f"run_{stamp}.log"
    started_at = time.time()
    with RunLog(log_path, settings.log.enabled) as run_log:
        _print_header(settings, input_path, output_dir, len(lines), len(items), workers, gate,
                      existing, log_path)
        done, skipped, failures, interrupted = _run_pool(
            settings, synthesizer, run_log, items, output_dir, existing, ext, width, workers)

    _print_summary(settings, output_dir, done, skipped, failures,
                   time.time() - started_at, workers)
    if interrupted:
        return 130
    return 1 if failures else 0


def collect_existing(root: Path) -> set[str]:
    """收集输出根目录下（含历次时间戳子目录）已存在的文件名，用于断点续跑。"""
    names: set[str] = set()
    if not root.exists():
        return names
    try:
        for entry in root.rglob("*"):
            if entry.is_file():
                names.add(entry.name)
    except OSError:
        pass
    return names


def _print_header(settings: Settings, input_path: Path, output_dir: Path, total_lines: int,
                  count: int, workers: int, gate: AdaptiveGate,
                  existing: set[str], log_path: Path) -> None:
    print(f"文本文件：{input_path.resolve()}   共 {total_lines} 行，待合成 {count} 条")
    print(f"输出目录：{output_dir.resolve()}")
    if output_dir.parent.exists() and settings.paths.timestamped:
        print(f"历史产物：{output_dir.parent.resolve()} 下已有 {len(existing)} 个文件，"
              f"同名条目会自动跳过")
    print(f"参考音频：{settings.paths.voice}")
    print(f"停顿标记：{settings.pause.marker if settings.pause.enabled else '关闭'}")
    print(f"拖沓重抽：{settings.quality.retry} 次   日志："
          f"{log_path if settings.log.enabled else '关闭'}")
    print()
    rate_text = f"限速 {settings.request.rpm:g} RPM" if settings.request.rpm > 0 else "不限速"
    log(f"开始合成：{count} 条，并发上限 {workers}（自适应，起始 {gate.limit}），{rate_text}")


def _run_pool(settings: Settings, synthesizer: Synthesizer, run_log: RunLog,
              items: list[tuple[int, str]], output_dir: Path, existing: set[str],
              ext: str, width: int,
              workers: int) -> tuple[int, int, list[tuple[int, str, str]], bool]:
    """并发跑完所有条目，返回 (成功数, 跳过数, 失败清单, 是否被中断)。"""
    total = len(items)
    done = skipped = 0
    failures: list[tuple[int, str, str]] = []
    interrupted = False

    def handle_item(index: int, lineno: int, text: str) -> tuple[str, int, str, str]:
        """单条：合成 → 检测（不合格重抽）→ 落盘。返回 (状态, 行号, 文本, 错误)。"""
        filename = f"{lineno:0{width}d}_{slugify(text)}{ext}"
        target = output_dir / filename
        tag = f"[{index}/{total}] 行 {lineno}"
        started = time.time()

        if filename in existing and not settings.run.force:
            log(f"{tag} 已存在，跳过：{filename}")
            return "skipped", lineno, text, ""

        words = max(1, len(text.split()))
        retried = 0
        try:
            audio_bytes = synthesizer.synthesize(settings.speak_text(text))
            stats = analyze_wav(audio_bytes)
            dragging, reason = judge_drag(stats, words, settings.quality)

            while dragging and retried < settings.quality.retry:
                retried += 1
                log(f"{tag} 太拖沓（{reason}），第 {retried} 次重抽…", err=True)
                audio_bytes = synthesizer.synthesize(settings.speak_text(text))
                stats = analyze_wav(audio_bytes)
                dragging, reason = judge_drag(stats, words, settings.quality)

            if dragging:
                raise RuntimeError(f"重抽 {retried} 次仍太拖沓（{reason}），已丢弃不保存")

            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f"{target.stem}.part{ext}")
            tmp.write_bytes(audio_bytes)
            tmp.replace(target)

            duration = f"{stats.duration:.2f}" if stats else ""
            silence = f"{stats.silence_percent:.0f}%" if stats else ""
            max_gap = f"{stats.max_gap:.2f}" if stats else ""
            wpm = f"{stats.wpm(words):.0f}" if stats else ""
            run_log.write("OK", lineno, filename, duration=duration, silence=silence,
                          max_gap=max_gap, wpm=wpm, retries=retried)
            log(f"{tag} ok {filename}  {duration}s  静音 {silence}／最长停顿 {max_gap}s"
                f"／{wpm}wpm  重抽 {retried}  ({time.time() - started:.1f}s)")
            return "ok", lineno, text, ""

        except Exception as exc:
            run_log.write("FAIL", lineno, filename, retries=retried, note=str(exc))
            log(f"{tag} 失败：{filename}  ::  {exc}", err=True)
            return "failed", lineno, text, str(exc)
        finally:
            if settings.request.delay > 0:
                time.sleep(settings.request.delay)

    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tts")
    futures: list = []
    try:
        futures = [pool.submit(handle_item, index, lineno, text)
                   for index, (lineno, text) in enumerate(items, start=1)]
        for future in as_completed(futures):
            try:
                status, lineno, text, error = future.result()
            except Exception as exc:
                failures.append((0, "", f"任务异常：{exc}"))
                continue
            if status == "ok":
                done += 1
            elif status == "skipped":
                skipped += 1
            else:
                failures.append((lineno, text, error))
    except KeyboardInterrupt:
        interrupted = True
        log("[中断] 取消尚未开始的任务，进行中的任务会写完当前文件。", err=True)
    finally:
        for future in futures:
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)

    return done, skipped, failures, interrupted


def _print_summary(settings: Settings, output_dir: Path, done: int, skipped: int,
                   failures: list[tuple[int, str, str]], elapsed: float, workers: int) -> None:
    print()
    print("=" * 64)
    print(f"完成：新合成 {done} 条，跳过 {skipped} 条，失败 {len(failures)} 条，"
          f"用时 {elapsed:.1f}s（并发上限 {workers}）")
    if output_dir.exists():
        print(f"输出目录：{output_dir.resolve()}")
    else:
        print(f"输出目录：本次未产生文件（目录 {output_dir.name} 未创建）")
    if failures:
        failures.sort(key=lambda entry: entry[0])
        print(f"有 {len(failures)} 条失败（重跑会自动重试，失败的不落盘）：")
        for lineno, text, err in failures:
            print(f"  行 {lineno}：{preview(text, 30)}  ::  {err}")
