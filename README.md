# 批量 TTS（语音克隆）

读取 txt（一行一条），在真实的句末标点后插入 `[]`，逐条调用语音克隆接口，把音频原样写入 `output/`，
并对结果做拖沓检测——不合格就重抽，仍不合格就丢弃不保存。

- 所有设置都在 `config.yaml`；
- 命令行只接受一个可选参数：要跑的 txt 文件；
- 运行日志记在 `output/run.log`，只记成功与失败。

## 目录结构

```
tts/
├─ main.py              入口脚本（很薄，只把项目目录交给 ttsgen）
├─ requirements.txt     依赖：openai、pyyaml
├─ config.yaml          全部配置
├─ ttsgen/              实现包
│  ├─ cli.py            参数解析、装配、退出码
│  ├─ config.py         config.yaml → 不可变配置对象
│  ├─ text.py           读文本、挑行、文件名片段
│  ├─ pause.py          停顿标记规则
│  ├─ quality.py        静音/语速分析、拖沓判定
│  ├─ api.py            合成请求、错误分类、退避
│  ├─ ratelimit.py      令牌桶、自适应并发、硬超时
│  ├─ runlog.py         TSV 日志
│  ├─ runner.py         批处理流水线
│  └─ console.py        控制台编码、线程安全输出
├─ input.txt            待合成文本，一行一条
├─ example.txt          示例文本
├─ source.wav           参考音频
└─ output/              输出目录（音频 + run.log）
```

## 安装

```bash
py -m pip install -r requirements.txt
```

## 运行

```bash
py main.py                 # 跑 config.yaml 里 paths.input 指定的文件
py main.py 别的.txt         # 跑指定的 txt，其余设置仍走 config.yaml
py -m ttsgen               # 等价入口
```

支持的退出码：`0` 全部成功 / `1` 有条目失败 / `2` 配置或文件问题 / `130` 被 Ctrl+C 中断。

## 快速开始

1. 装依赖；
2. 改 `config.yaml`（确认 `paths.voice`、`api.api_key`；`paths.input` 是默认文本）；
3. 打开预览（不花钱）：

   ```yaml
   run:
     dry_run: true
   ```

   ```bash
   py main.py
   ```

4. 预览没问题就把 `dry_run` 改回 `false`，正式跑。

## 想改什么，去哪个文件

| 需求 | 改哪里 |
| --- | --- |
| 腔调、语速、设备感 | `config.yaml` 的 `prompt` |
| 停顿标记的判定规则 | `ttsgen/pause.py` |
| 静音/语速阈值、重抽次数 | `config.yaml` 的 `quality` |
| 重抽流程本身（比如加重抽上限、换判定顺序） | `ttsgen/runner.py` 的 `_run_pool` |
| 并发、限速、超时、退避 | `config.yaml` 的 `request` + `ttsgen/api.py` / `ratelimit.py` |
| 日志字段 | `ttsgen/runlog.py` |
| 新增一个配置项 | `config.yaml` + `ttsgen/config.py` 的 dataclass |

## config.yaml 说明

### api

| 键 | 说明 |
| --- | --- |
| `base_url` | 接口地址 |
| `model` | 模型 ID，如 `mimo-v2.5-tts-voiceclone` |
| `api_key` | 密钥；留空则读环境变量 `MIMO_API_KEY`（环境变量优先） |
| `audio_format` | 输出格式，同时决定文件后缀 |
| `voice_mime` | 参考音频打包成 data URL 时的 MIME |

### paths / prompt / pause

- `paths`：`input` 默认文本、`output` 音频目录、`voice` 参考音频；相对路径以 `config.yaml` 所在目录为基准。
- `prompt`：`user` 消息里的风格指令，用 `|` 块写多行。
- `pause`：`enabled` 开关、`marker` 标记文本、`scope`（`sentence`/`clause`）、`repeat` 每个位置插几个。

### quality（拖沓检测与重抽）

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `retry` | 5 | 判定拖沓后重抽几次；用光仍不合格 → 丢弃不保存 |
| `max_silence` | 0.55 | 静音占比上限 |
| `max_gap` | 0.90 | 最长静音（秒）上限 |
| `min_wpm` | 90 | 语速下限，仅对 ≥ `min_words` 的句子生效 |
| `min_words` | 6 | 少于这么多词就不看语速 |
| `duration_factor` / `duration_bonus` | 0.9 / 3.0 | 时长上限 = 词数 × factor + bonus |

### request / run / log

- `request`：`concurrency`、`rpm`、`retries`、`timeout`、`delay`。
- `run`：`start`、`limit`、`force`、`dry_run`。
- `log`：`enabled`、`path`（默认 `output/run.log`）。

## 停顿标记规则

关键是「标点后面有没有空格」——只有后面跟空格的标点才算真正的句子边界。

| 输入 | 结果 | 原因 |
| --- | --- | --- |
| `Low. Next` | `Low.[] Next` | 句点后跟空格 → 句子边界 |
| `M.E.G. Base` | 不插 | 词内含点，缩写 |
| `J. Smith` | 不插 | 单个大写字母 = 姓名首字母 |
| `Mr. Lee` / `e.g. this` | 不插 | 缩写词表 |
| `3.5 dollars` | 不插 | 点后是数字 |
| `no space.Here` | 不插 | 点后没有空格 |
| `"Stop!" Next` | `"Stop!"[] Next` | 跳过收尾引号后是空格，标记放引号外 |
| `你好。再见` | `你好。[]再见` | 全角标点不要求空格 |
| 行尾的 `.` `!` | 不插 | 避免多余的尾部静音 |

## 日志

`output/run.log`，TSV，可直接用 Excel 打开：

```
time	status	line	file	duration	silence	max_gap	wpm	retries	note
2026-10-25 01:41:01	OK	1	0001_Warning_Sanity_low.wav	1.65	3%	0.05	112	0
2026-10-25 01:41:01	FAIL	2	0002_Attention_all_personnel.wav					2	重抽 2 次仍太拖沓（静音 80%，最长停顿 2.40s），已丢弃不保存
```

- 只记 `OK` 和 `FAIL`；跳过的（已存在）不写；
- 追加写入，不覆盖历史。

## 并发与限速

TTS 模型官方限制均为 **RPM 100 / TPM 10M**（[速率限制](https://mimo.mi.com/docs/zh-CN/api/guidance/rate-limit)），
按「账号 + 模型 + 所有 Key 合计」计算，另有账号级并发上限，超出返回 429。

- 令牌桶按 `request.rpm` 限速；
- 并发从 2 起步，每成功 5 次加 1 路，遇 429 立即减半并全局冷却——`concurrency` 只是上限；
- 429 优先用 `Retry-After`；只重试 408/429/5xx 和连接类错误。

## 超时与失败

- SDK 内置重试已关闭（`max_retries=0`），重试完全由 `request.retries` 控制；
- 每次请求有墙钟超时（`request.timeout`），到点放弃并 1s 后重发；
- 单条最终失败或判定拖沓 → 不落盘、记一条 `FAIL`、退出码 1；重跑会自动再试。

## 常见问题

**`[配置错误] config.yaml 缺少 xxx`** — 配置缺键，按提示补上。
**`[配置错误] 找不到配置文件`** — 从别的目录调用时，配置按脚本目录找；确认 `config.yaml` 和 `main.py` 同级。
**命令行为什么不能加 `--xxx`** — 只有位置参数（txt），其余设置走 `config.yaml`。
**`429` 频繁** — 把 `request.rpm` 降到 10~20，比调 `concurrency` 有效。
**某条一直失败** — 看 `run.log` 的 `note`；若是判拖沓，先听同批其他文件，再调 `quality` 阈值。
