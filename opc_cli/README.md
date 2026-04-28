# OPC CLI

OPC 工具集命令行界面 —— B站视频转写 + 语音合成 + 本地TTS + 图片理解 + UI转Vue + 文生图 + AI日报。

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
# ── LLM 模型配置 ──
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_MODEL=glm-4-flash

# ── 智谱 AI API（TTS/ASR 共用）──
ZHIPU_API_KEY=your_api_key_here
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ASR_MODEL=glm-asr-2512

# ── 视觉模型配置（优先级：VISION_ > ZHIPU_ > LLM_）──
# VISION_API_KEY=your_vision_api_key_here
# VISION_BASE_URL=https://open.bigmodel.cn/api/paas/v4
# VISION_MODEL=glm-5v-turbo

# ── 文生图（阿里云百炼）──
IMAGE_API_KEY=your_image_api_key_here

# ── GPT-Image 文生图 ──
# GPT_IMAGE_API_KEY=your_gpt_image_api_key_here
# GPT_IMAGE_BASE_URL=https://api.apimart.ai/v1
# GPT_IMAGE_MODEL=gpt-image-2

# ── 代理 ──
# GPT_IMG_PROXY=http://127.0.0.1:7897

# ── B站 cookies ──
# YT_DLP_COOKIES=./cookies.txt
```

## 命令一览

```
opc                  显示帮助
opc bili             B站视频下载 + ASR 转写 + 内容总结
opc tts              文字转语音（支持音色克隆）
opc local-tts        本地语音合成 + 服务管理（Qwen3-TTS）
opc read-img         图片理解：使用视觉模型分析图片内容
opc ui2vue           UI截图转Vue：分析 UI 截图生成 Vue 3 组件代码
opc gpt-img          GPT-Image-2 文生图
opc Z-image          阿里云 z-image-turbo 文生图
opc check-api        检查 .env 中 API 的连通性
opc news             AI 日报：自动收集 AI 新闻并生成简报
```

---

## bili — B站视频转写

从 Bilibili 视频下载音频，进行 ASR 语音识别，生成 SRT 字幕和 Markdown 内容总结。

### 使用范例

```bash
# 完整流程：下载 → ASR → 总结
opc bili "https://www.bilibili.com/video/BV1xx"

# 指定输出目录
opc bili "https://..." -o ./my_output

# 仅下载音频，不做转写
opc bili "https://..." --audio-only

# 跳过下载，从 output 目录自动查找已有音频文件
opc bili --skip-download

# 跳过下载，手动指定音频文件
opc bili --skip-download --audio-file ./output/audio.m4a

# 跳过下载和 ASR，从 output 目录自动查找已有字幕文件生成总结
opc bili --skip-download --skip-asr

# 跳过 ASR，手动指定字幕文件
opc bili "https://..." --skip-download --skip-asr --asr-file ./output/audio.srt

# 使用 cookies 下载需要登录的视频
opc bili "https://..." --cookies ./cookies.txt
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `url` | | | Bilibili 视频链接（`--skip-download` 时可省略） |
| `--output-dir` | `-o` | `./output` | 输出目录 |
| `--cookies` | | | yt-dlp cookies 文件路径 |
| `--audio-only` | | `false` | 仅下载音频，不进行 ASR |
| `--skip-download` | | `false` | 跳过下载，从 output-dir 自动查找音频 |
| `--audio-file` | | | 手动指定已有音频文件路径 |
| `--skip-asr` | | `false` | 跳过 ASR，从 output-dir 自动查找字幕文件 |
| `--asr-file` | | | 手动指定 ASR JSON 或 SRT 文件路径 |
| `--env-file` | | | 自定义 .env 文件路径 |

### 输出文件

| 文件 | 说明 |
|---|---|
| `{title}.m4a` | 下载的音频文件 |
| `{title}.srt` | SRT 字幕文件 |
| `{title}.asr.json` | ASR 原始结果（JSON） |
| `{title}.md` | Markdown 内容总结（含视频时间线链接） |

---

## tts — 文字转语音（智谱 GLM-TTS）

使用智谱 GLM-TTS 模型将文本转为语音，支持 7 种预设音色和音色克隆。

### 使用范例

```bash
# 默认音色（彤彤）
opc tts "你好，今天天气真不错" -o output.wav

# 指定音色
opc tts "你好" -o output.wav --voice xiaochen

# 调节语速和音量
opc tts "你好" --speed 1.2 --volume 1.5

# 列出系统预设音色
opc tts --list-voices

# 列出已克隆的音色
opc tts --list-cloned

# 用参考音频克隆音色并合成
opc tts "我是克隆的声音" -o output.wav --clone --ref-audio ref.wav

# 克隆时指定参考文本和音色名称
opc tts "你好世界" -o out.wav --clone --ref-audio ref.wav --ref-text "参考音频的文字" --voice-name my_voice
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `text` | | | 要转换的文本（`--list-voices` 时可省略） |
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
| `--list-voices` | | `false` | 列出系统预设音色 |
| `--list-cloned` | | `false` | 列出已克隆的音色 |
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

---

## local-tts — 本地语音合成（Qwen3-TTS）

使用本地 Qwen3-TTS 模型进行语音合成，支持预设音色、音色设计、语音克隆三种模式。常驻服务模式下模型只加载一次，后续请求即时响应。

### 使用范例

```bash
# ── 服务管理 ──

# 启动 TTS 常驻服务（默认 custom 模式）
opc local-tts --serve

# 启动指定模式的常驻服务
opc local-tts --serve --mode design
opc local-tts --serve --mode base

# 查看服务状态
opc local-tts --status

# 释放模型缓存（服务保持运行）
opc local-tts --unload

# 停止服务
opc local-tts --stop

# ── 语音合成（通过常驻服务）──

# 使用预设音色（默认 Vivian）
opc local-tts "你好，我是本地TTS" -o output.wav

# 指定预设音色
opc local-tts "今天天气不错" -o output.wav --speaker Ethan

# 用自然语言控制语气
opc local-tts "快跑！" -o output.wav --instruct "用焦急紧张的语气"

# 音色设计模式：用自然语言描述想要的音色
opc local-tts "欢迎收听本期播客" -o output.wav --mode design --instruct "低沉磁性男声，像深夜电台主持人"

# 语音克隆模式：3 秒参考音频即可克隆
opc local-tts models/test/Test_TTS.md  --mode base --ref-audio models/voice/ref.mp3 --ref-text "光辉的结晶啊，请降下恩典"

opc local-tts "这是克隆的声音" -o output.wav --mode base --ref-audio models/voice/ref.wav --ref-text "参考音频的文字内容"

# 列出预设音色
opc local-tts --list-speakers

# 不使用常驻服务，直接加载模型合成
opc local-tts "你好" -o output.wav --no-server
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `text` | | | 要转换的文本（serve/stop/status/unload 时可省略） |
| `--output` | `-o` | `output.wav` | 输出文件路径 |
| `--mode` | `-m` | `custom` | 模型变体：`custom`=预设音色 / `design`=设计音色 / `base`=语音克隆 |
| `--speaker` | `-s` | `Vivian` | 预设音色名称（custom 模式） |
| `--language` | `-l` | `Chinese` | 语言 |
| `--instruct` | | | 自然语言指令（custom 控制语气 / design 描述音色） |
| `--ref-audio` | | | 参考音频路径（base 模式） |
| `--ref-text` | | | 参考音频对应文本（base 模式必填） |
| `--device` | | `cuda:0` | 设备 |
| `--attn` | | `sdpa` | 注意力实现：sdpa / flash_attention_2 / eager |
| `--list-speakers` | | `false` | 列出预设音色 |
| `--no-server` | | `false` | 不使用常驻服务，直接加载模型 |
| `--serve` | | `false` | 启动 TTS 常驻服务 |
| `--stop` | | `false` | 停止 TTS 常驻服务 |
| `--status` | | `false` | 查看 TTS 服务状态 |
| `--unload` | | `false` | 释放模型缓存 |
| `--port` | `-p` | `9900` | 服务端口 |

### 模型文件

| mode | 模型路径 |
|---|---|
| `custom` | `models/Qwen3-TTS-12Hz-1.7B-CustomVoice` |
| `design` | `models/Qwen3-TTS-12Hz-1.7B-VoiceDesign` |
| `base` | `models/Qwen3-TTS-12Hz-1.7B-Base` |

---

## read-img — 图片理解

使用视觉模型分析图片内容，支持本地图片和网络 URL，自动压缩超大图片。

### 使用范例

```bash
# 分析本地图片
opc read-img photo.jpg

# 分析网络图片
opc read-img "https://example.com/image.jpg"

# 自定义提问
opc read-img photo.jpg -p "这张图片里有什么动物？"

# 输出结果到文件
opc read-img photo.jpg -o result.txt

# 增大 max_tokens 获取更详细的回答
opc read-img photo.jpg --max-tokens 4096

# 分析 UI 控件的像素位置
opc read-img ui.png -p "每个控件的相对位置和像素大小是什么"
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `image` | | | 图片路径或 URL |
| `--prompt` | `-p` | `请详细描述这张图片的内容` | 提问内容 |
| `--output` | `-o` | 终端输出 | 输出到文件 |
| `--model` | | 从 .env 读取 `VISION_MODEL` | 视觉模型名称 |
| `--max-tokens` | | `4096` | 最大输出 token 数 |
| `--temperature` | | `0.7` | 生成温度 [0, 1] |
| `--env-file` | | | 自定义 .env 文件路径 |

### 图片大小限制

- 单张图片最大 **10MB**，超出时自动压缩（WebP → JPEG → 缩放）
- API 配置优先级：`VISION_API_KEY` > `ZHIPU_API_KEY` > `LLM_API_KEY`

---

## ui2vue — UI截图转Vue

分析 UI 界面截图，使用视觉模型生成 Vue 3 单文件组件代码。三步流程：视觉分析 → 生成 Vue 代码 → 创建工程并自动修复。

### 使用范例

```bash
# 完整流程：分析截图 → 生成代码 → 创建 Vue 工程
opc ui2vue ui-screenshot.png

# 使用 Element Plus 组件库
opc ui2vue ui-screenshot.png -f element-plus

# 使用 Tailwind CSS
opc ui2vue ui-screenshot.png -f tailwind

# 指定组件名称和输出目录
opc ui2vue ui-screenshot.png -c UserProfile -o ./components

# 分析网络图片
opc ui2vue "https://example.com/ui-design.png"

# 使用已有分析结果（跳过步骤1），直接生成代码
opc ui2vue --analysis ./output/ui_analysis_20260427.md

# 只生成代码，不创建 Vue 工程
opc ui2vue ui.png --no-create-project

# 不自动保存 .vue 文件（仅输出到终端/日志）
opc ui2vue ui.png --no-save-vue

# 指定 Vue 项目名称
opc ui2vue ui.png -p my-dashboard
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `image` | | | UI 截图路径或 URL（`--analysis` 时可省略） |
| `--framework` | `-f` | `default` | UI 框架（见下表） |
| `--component` | `-c` | 自动命名 | 组件名称 |
| `--output` | `-o` | 当前目录 | 输出目录 |
| `--project` | `-p` | `vue-app` | Vue 项目名称 |
| `--vision-model` | | 从 .env 读取 `VISION_MODEL` | 视觉模型名称 |
| `--llm-model` | | 从 .env 读取 `LLM_MODEL` | LLM 模型名称 |
| `--max-tokens` | | `16384` | 最大输出 token 数 |
| `--temperature` | | `0.3` | 生成温度 [0, 1] |
| `--max-retries` | | `3` | 步骤3 最大自动修复重试次数 |
| `--analysis` | | | 已有分析 md 文件路径（跳过步骤1） |
| `--save-vue` | | `true` | 自动提取并保存 .vue 文件 |
| `--create-project` | | `true` | 创建 Vue 工程并自动修复（步骤3） |
| `--env-file` | | | 自定义 .env 文件路径 |

### 支持的 UI 框架

| 框架 ID | 说明 |
|---|---|
| `default` | 纯 Vue 3 + 自定义 CSS（默认） |
| `element-plus` | Element Plus 组件库 |
| `ant-design-vue` | Ant Design Vue 组件库 |
| `naive-ui` | Naive UI 组件库 |
| `vuetify` | Vuetify 组件库 |
| `tailwind` | Tailwind CSS 工具类 |
| `pure` | 纯 HTML/CSS，无 UI 框架 |

### 输出文件

| 文件 | 说明 |
|---|---|
| `output/ui_analysis_*.md` | 步骤1 UI 结构分析结果 |
| `src/components/*.vue` | 提取的 Vue 单文件组件 |
| `src/App.vue` | 自动生成的入口组件 |

---

## gpt-img — GPT-Image-2 文生图

使用 GPT-Image-2 模型根据提示词生成高质量图片，默认使用 LLM 丰富提示词。

### 使用范例

```bash
# 基本文生图
opc gpt-img "一只穿着宇航服的猫"

# 指定输出路径
opc gpt-img "山水画" -o ./output/landscape.png

# 指定宽高比和分辨率
opc gpt-img "人像" -s 3:4 -r 2k
opc gpt-img "风景" -s 16:9 -r 1k

# 不使用 LLM 丰富提示词
opc gpt-img "a cute cat" --no-enhance

# 图生图：指定参考图
opc gpt-img "换成赛博朋克风格" --ref original.png

# 多张参考图
opc gpt-img "融合这些风格" --ref img1.png --ref img2.png

# 使用代理
opc gpt-img "风景" --proxy

# 仅返回图片 URL，不下载
opc gpt-img "测试图" --no-download
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `prompt` | | | 提示词（中英文） |
| `--output` | `-o` | 自动生成 | 输出图片路径 |
| `--size` | `-s` | `2:3` | 宽高比：1:1, 2:3, 3:2, 4:3, 3:4, 5:4, 4:5, 16:9, 9:16 等 |
| `--resolution` | `-r` | `1k` | 分辨率档位：1k / 2k / 4k |
| `--enhance` | | `true` | 使用 LLM 丰富提示词 |
| `--ref` | | | 参考图路径或 URL（可多次指定，最多16张） |
| `--no-download` | | `false` | 仅返回图片 URL |
| `--proxy` | | `false` | 使用 GPT_IMG_PROXY 代理 |
| `--timeout` | | `300` | 最大等待时间（秒） |
| `--env-file` | | | 自定义 .env 文件路径 |

---

## Z-image — 阿里云文生图

使用阿里云百炼 z-image-turbo 模型根据提示词生成图片，默认使用 LLM 丰富提示词。

### 使用范例

```bash
# 基本文生图
opc Z-image "一只穿着宇航服的猫"

# 指定输出路径
opc Z-image "山水画" -o ./output/landscape.png

# 指定宽高比
opc Z-image "人像" -s 3:4
opc Z-image "横版风景" -s 16:9

# 指定像素分辨率
opc Z-image "高清图" -s 2048*2048

# 不使用 LLM 丰富提示词
opc Z-image "a cute cat" --no-enhance

# 启用智能提示词改写（会增加时间和费用）
opc Z-image "风景" --prompt-extend

# 指定随机种子（可复现结果）
opc Z-image "测试" --seed 42

# 仅返回图片 URL
opc Z-image "测试图" --no-download
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `prompt` | | | 提示词（中英文） |
| `--output` | `-o` | 自动生成 | 输出图片路径 |
| `--size` | `-s` | `2:3` | 宽高比（如 2:3）或像素（如 1024*1536） |
| `--model` | | `z-image-turbo` | 模型名称 |
| `--enhance` | | `true` | 使用 LLM 丰富提示词 |
| `--prompt-extend` | | `false` | 启用智能提示词改写 |
| `--seed` | | 随机 | 随机种子（0~2147483647） |
| `--no-download` | | `false` | 仅返回图片 URL |
| `--env-file` | | | 自定义 .env 文件路径 |

---

## check-api — API 连通性检查

检查 `.env` 中配置的 API 是否可用，显示状态、耗时和详情。

### 使用范例

```bash
# 检查全部 API
opc check-api

# 只检查 LLM 和 Vision
opc check-api --only llm --only vision

# 只检查文生图相关
opc check-api --only image --only gpt-image

# 指定 .env 文件
opc check-api --env-file /path/to/.env
```

### 可检查的 API 名称

`llm` / `zhipu` / `vision` / `image` / `gpt-image` / `proxy` / `cookies`

---

## news — AI 日报

自动收集当日 AI 技术/科研/项目新闻，使用 LLM 整合输出专业简报。信息来源：36氪、虎嗅、IT之家、InfoQ、GitHub、Arxiv。

### 使用范例

```bash
# 生成今日 AI 日报
opc news

# 指定输出目录（文件名自动为 ai_daily_YYYY-MM-DD.md）
opc news -d ./my_reports

# 指定完整输出路径
opc news -o ./report.md

# 仅输出原始素材，不调用 LLM
opc news --no-llm

# 额外保存原始 JSON 数据
opc news --save-raw

# 指定 .env 文件
opc news --env-file /path/to/.env
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `--output` | `-o` | | 输出文件完整路径（优先级高于 --output-dir） |
| `--output-dir` | `-d` | `./output` | 输出目录，文件名默认 `ai_daily_YYYY-MM-DD.md` |
| `--no-llm` | | `false` | 不调用 LLM，仅输出原始素材 |
| `--save-raw` | | `false` | 额外保存原始 JSON 数据 |
| `--env-file` | | | 自定义 .env 文件路径 |

---

## 项目结构

```
opc_cli/
├── __init__.py     # 包初始化
├── cli.py          # CLI 入口（typer 子命令定义）
├── config.py       # 共享配置（环境变量、API Key）
├── logger.py       # 日志系统（TeeWriter 双输出）
├── bili.py         # B站视频下载 + ASR 转写 + 内容总结
├── tts.py          # GLM-TTS 语音合成 + 音色克隆
├── local_tts.py    # Qwen3-TTS 本地语音合成
├── tts_server.py   # TTS 常驻服务（Flask）
├── vision.py       # 图片理解（视觉模型）
├── ui2vue.py       # UI 截图转 Vue 组件代码
├── check_api.py    # API 连通性检查
├── gpt_img.py      # GPT-Image-2 文生图
├── text2img.py     # 阿里云 z-image-turbo 文生图
└── ai_daily.py     # AI 日报
```

## 依赖

- **typer** — CLI 框架
- **rich** — 终端美化输出
- **requests** — HTTP 请求（TTS / 音色克隆）
- **python-dotenv** — .env 文件加载
- **openai** — LLM 内容总结 / 图片理解
- **zhipuai** — 智谱 ASR 语音识别
- **yt-dlp** — B站视频下载
- **soundfile** + **numpy** — 音频分片处理
- **Pillow** — 图片压缩处理

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

**Q: `local-tts` 报 `No module named 'torch'`**

`opc` 通过 pipx 安装的环境不包含 torch。需在有 torch 的 venv 中安装 opc：
```bash
source ~/qwen3-tts-venv/bin/activate
~/qwen3-tts-venv/bin/pip install -e /mnt/d/github/OPC
```

**Q: `read-img` 输出为空**

可能是 `--max-tokens` 不够，模型推理过程消耗了配额。尝试增大：
```bash
opc read-img photo.jpg --max-tokens 4096
```
