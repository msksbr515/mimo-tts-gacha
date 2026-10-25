# 贡献指南

欢迎提 Issue 与 Pull Request。改动前请先读一遍本文件，能省掉大半来回。

## 1. 环境准备

```bash
py -m pip install -r requirements.txt
cp .env.example .env        # 填入自己的 MIMO_API_KEY
```

`.env`、`*.txt`（除 `example.txt`）、`*.wav`、`output/`、`logs/`、`saved/` 都在 `.gitignore` 里，
**不要**用 `git add -f` 强行提交这些文件，也不要提交任何密钥。

## 2. 先自测，再发 PR

不需要真的调接口也能验证大部分改动：

```yaml
# config.yaml
run:
  dry_run: true          # 只打印插入停顿标记后的文本，零请求
  limit: 1               # 需要真跑时，先只跑一条
```

- 改文字处理（`pause.py`）：用 `dry_run` 跑一遍自己的用例，确认插入位置符合 README 第 9 章那张判定表；
- 改检测阈值（`config.yaml` 的 `quality`）：跑 3～5 条，看 `logs/report_*.md` 里的 `silence / max_gap / wpm` 三列是否合理；
- 改流程（`runner.py`）：至少验证「成功一条」「拖沓丢弃一条」「已存在跳过」三种路径。

提交前建议顺手跑一下：

```bash
py -m compileall -q .
```

## 3. 代码结构与改动入口

| 想改什么 | 改哪里 |
| --- | --- |
| 停顿标记规则 | `ttsgen/pause.py` |
| 拖沓判定 | `ttsgen/quality.py` + `config.yaml` 的 `quality` |
| 重抽流程 | `ttsgen/runner.py` 的 `_run_pool` |
| 接口调用与退避 | `ttsgen/api.py` |
| 限速与并发 | `ttsgen/ratelimit.py` |
| 日志字段 | `ttsgen/runlog.py` |
| 报告内容 | `ttsgen/report.py` |
| 新增配置项 | `config.yaml` + `ttsgen/config.py` 的 dataclass |

原则：**能在 `config.yaml` 调的不写死在代码里**，新增配置项要带中文注释与默认值。

## 4. 提交规范

- 一个提交只做一件事，标题一句话说清做了什么；
- 涉及行为变化时，在提交正文里写明「改前 / 改后」；
- 同步更新 README 对应章节（配置项、目录结构、判定规则都写在 README 里）。

## 5. 提 Issue

请附上：

- 复现步骤（`config.yaml` 里相关的几段，**去掉密钥**）；
- 报错信息或 `run.log` 的相关行（去掉台词正文）；
- 若是音频质量问题，说明具体哪一条、期望与实际差在哪（拖沓 / 漏词 / 标记被念出来）。

## 6. 关于许可

本项目以 [MIT](LICENSE) 发布，提交的代码视为同意以同一许可发布。
