# OPC CLI

OPC 工具集命令行界面 —— B站视频转写 + 语音合成 + 音色克隆。

## 安装

```bash
# 创建虚拟环境（推荐）
python3 -m venv ~/opc-venv
source ~/opc-venv/bin/activate

# 安装
pip install -e .
```

安装后即可全局使用 `opc` 命令。

## 环境配置

在项目根目录创建 `.env` 文件：

```bash
# 必填：智谱 AI API Key（TTS、ASR 共用）
ZHIPU_API_KEY=your_api_key_here

# 可选：API 地址（默认智谱官方）
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4

# 可选：ASR 模型（默认 glm-asr-2512）
ASR_MODEL=glm-asr-2512

# 可选：LLM 总结模型配置（未设置时回退到 ZHIPU_API_KEY）
LLM_API_KEY=your_llm_api_key_here
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_MODEL=glm-4-flash

# 可选：B站 cookies 文件（下载需要登录的视频时使用）
# YT_DLP_COOKIES=./cookies.txt
```

## 命令一览

```
opc                  显示帮助
opc bili             B站视频下载 + ASR 转写 + 内容总结
opc tts              文字转语音（支持音色克隆）
opc voices           列出可用音色
```

## bili — B站视频转写

从 Bilibili 视频下载音频，进行 ASR 语音识别，生成 SRT 字幕和 Markdown 内容总结。

### 基本用法

```bash
# 完整流程：下载 → ASR → 总结
opc bili "https://www.bilibili.com/video/BV1xx"

# 指定输出目录
opc bili "https://..." -o ./my_output

# 仅下载音频，不做转写
opc bili "https://..." --audio-only
```

### 高级用法

```bash
# 跳过下载，使用已有音频文件
opc bili "https://..." --skip-download --audio-file ./output/audio.m4a

# 跳过 ASR，使用已有字幕文件生成总结
opc bili "https://..." --skip-download --skip-asr --asr-file ./output/audio.srt

# 使用 cookies 下载需要登录的视频
opc bili "https://..." --cookies ./cookies.txt
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `url` | | | Bilibili 视频链接 |
| `--output-dir` | `-o` | `./output` | 输出目录 |
| `--cookies` | | | yt-dlp cookies 文件路径 |
| `--audio-only` | | `false` | 仅下载音频，不进行 ASR |
| `--skip-download` | | `false` | 跳过下载，使用已有音频 |
| `--audio-file` | | | 指定已有音频文件路径 |
| `--skip-asr` | | `false` | 跳过 ASR，使用已有字幕 |
| `--asr-file` | | | 指定已有 ASR JSON 或 SRT 文件 |
| `--env-file` | | | 自定义 .env 文件路径 |

### 输出文件

运行后在输出目录生成：

| 文件 | 说明 |
|---|---|
| `{title}.m4a` | 下载的音频文件 |
| `{title}.srt` | SRT 字幕文件 |
| `{title}.asr.json` | ASR 原始结果（JSON） |
| `{title}.md` | Markdown 内容总结（含视频时间线链接） |

## tts — 文字转语音

使用智谱 GLM-TTS 模型将文本转为语音，支持 7 种预设音色和音色克隆。

### 基本用法

```bash
# 默认音色（彤彤）
opc tts "你好，今天天气真不错" -o output.wav

# 指定音色
opc tts "你好" -o output.wav --voice xiaochen

# 调节语速和音量
opc tts "你好" --speed 1.2 --volume 1.5
```

### 音色克隆

```bash
# 用参考音频克隆音色并合成
opc tts "我是克隆的声音" -o output.wav --clone --ref-audio ref.wav

# 克隆时指定参考文本和音色名称
opc tts "你好世界" -o out.wav --clone --ref-audio ref.wav --ref-text "参考音频的文字" --voice-name my_voice
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `text` | | | 要转换的文本 |
| `--output` | `-o` | `output.wav` | 输出音频文件路径 |
| `--voice` | | `tongtong` | 音色名称或克隆音色 ID |
| `--speed` | | `1.0` | 语速 [0.5, 2] |
| `--volume` | | `1.0` | 音量 (0, 10] |
| `--format` | | `wav` | 音频格式：`wav` / `pcm` |
| `--watermark` | | `false` | 添加 AI 生成水印 |
| `--clone` | | `false` | 启用音色克隆模式 |
| `--ref-audio` | | | 克隆参考音频（mp3/wav，≤10MB） |
| `--ref-text` | | | 参考音频对应文本（可选） |
| `--voice-name` | | | 克隆音色命名（可选） |
| `--env-file` | | | 自定义 .env 文件路径 |

### 预设音色

| 音色 ID | 名称 |
|---|---|
| `tongtong` | 彤彤（默认） |
| `xiaochen` | 小陈 |
| `chuichui` | 锤锤 |
| `jam` | jam |
| `kazi` | kazi |
| `douji` | douji |
| `luodo` | luodo |

### 长文本处理

文本超过 1024 字符时自动按句号、问号、叹号分段合成，拼接为完整音频。

## voices — 查看音色

```bash
# 查看系统预设音色
opc voices

# 查看已克隆的音色
opc voices --clone
```

## 项目结构

```
opc_cli/
├── __init__.py     # 包初始化
├── cli.py          # CLI 入口（typer 子命令定义）
├── config.py       # 共享配置（环境变量、API Key）
├── bili.py         # B站视频下载 + ASR 转写 + 内容总结
└── tts.py          # GLM-TTS 语音合成 + 音色克隆
```

## 依赖

- **typer** — CLI 框架
- **rich** — 终端美化输出
- **requests** — HTTP 请求（TTS / 音色克隆）
- **python-dotenv** — .env 文件加载
- **openai** — LLM 内容总结
- **zhipuai** — 智谱 ASR 语音识别
- **yt-dlp** — B站视频下载
- **soundfile** + **numpy** — 音频分片处理

## 常见问题

**Q: `pip install -e .` 报 `externally-managed-environment` 错误**

需要先创建虚拟环境：
```bash
sudo apt install python3.12-venv   # Debian/Ubuntu
python3 -m venv ~/opc-venv
source ~/opc-venv/bin/activate
pip install -e .
```

**Q: TTS 生成的音频开头有"嘟嘟"声**

这是 AI 水印音，默认已关闭。如果仍有，确认使用最新版本代码（`watermark_enabled` 默认 `false`）。

**Q: 长文本只读了一半就结束了**

GLM-TTS 单次请求限制 1024 字符，CLI 会自动分段合成拼接。如仍截断，请检查文本中是否有特殊字符影响分段。

**Q: B站视频下载失败**

- 确保安装了 `yt-dlp` 和 `ffmpeg`
- 部分视频需要登录，使用 `--cookies` 参数提供 cookies 文件
- 使用浏览器扩展 "Get cookies.txt LOCALLY" 导出 B站 cookies
