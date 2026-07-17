# OPC CLI

OPC 工具集命令行界面 —— B站视频转写 + 语音合成 + 本地TTS + 图片理解 + UI转Vue + 文生图 + 本地/云扉 ComfyUI + AI日报。

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

项目使用 `.env` 文件管理 API Key 和路径配置。复制模版后编辑：

```bash
cp .env.example .env
# 然后编辑 .env 填入 API Key
```

`.env.example` 包含所有可用配置项及详细说明，也有 API Key 回退链的优先级说明。

## 命令一览

```
opc                  显示帮助
opc bili             B站视频下载 + ASR 转写 + 内容总结
opc asr              语音识别：音频 → SRT/JSON 字幕
opc tts              文字转语音（支持音色克隆）
opc local-tts        本地语音合成 + 服务管理（Qwen3-TTS）
opc read-img         图片理解：使用视觉模型分析图片内容
opc ui2vue           UI截图转Vue：分析 UI 截图生成 Vue 3 组件代码
opc gpt-img          GPT-Image-2 文生图
opc Z-image          阿里云 z-image-turbo 文生图
opc comfyui          ComfyUI 进程管理 + 工作流提交
opc aigate           云扉 AIGate ComfyUI 实例管理 + 工作流提交
opc check-api        检查 .env 中 API 的连通性
opc news             AI 日报：自动收集 AI 新闻并生成简报
```

---

## 环境变量速查

| 环境变量 | 用途 | 涉及命令 |
|---|---|---|
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | LLM 大模型（总结/日报/提示词丰富/代码生成） | bili, news, asr --llm-fix, gpt-img, Z-image, ui2vue, check-api |
| `ZHIPU_API_KEY` / `ZHIPU_BASE_URL` | 智谱 API（TTS 引擎/音色克隆），也作为 Vision/LLM 回退 | tts --engine glm-tts, check-api |
| `QWEN_TTS_API_KEY` / `QWEN_TTS_MODEL` / `VOICE_ID1/2` | 阿里云 CosyVoice TTS（默认引擎） | tts (默认) |
| `VISION_API_KEY` / `VISION_BASE_URL` / `VISION_MODEL` | 视觉模型（图片理解/UI 分析） | read-img, ui2vue |
| `DASHSCOPE_API_KEY` / `ASR_API_KEY` / `ASR_MODEL` | 阿里云 ASR 语音识别 | asr, bili |
| `IMAGE_API_KEY` / `IMAGE_MODEL` | 阿里云文生图，也作为 ASR/TTS/GPT-Img 回退 | Z-image |
| `GPT_IMAGE_API_KEY` / `GPT_IMAGE_BASE_URL` / `GPT_IMAGE_MODEL` | GPT-Image-2 文生图 | gpt-img |
| `GPT_IMG_PROXY` | gpt-img 代理，WSL 下自动启用 | gpt-img (--proxy) |
| `YT_DLP_COOKIES` | B站 cookies 文件路径 | bili, bilimusic |
| `BILI_FOLDER` | bili 默认输出目录 | bili |
| `NEWS_FOLDER` | news 默认输出目录 | news |
| `COMFYUI_ROOT` | ComfyUI 根目录 | comfyui --start |
| `AIGATE_TOKEN` | 云扉 Bearer Token | aigate |
| `AIGATE_SKU_NAME` / `AIGATE_AREA_NAME` / `AIGATE_IMAGE_ID` / `AIGATE_IMAGE_TYPE` | 显式创建云扉实例的预设 GPU、区域和镜像 | aigate --start --create |

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

## asr — 语音识别

将音频文件转写为 SRT 字幕和 JSON 文件。使用阿里云 DashScope fun-asr-realtime 模型，支持精确时间戳、LLM 智能断句纠错。

### 使用范例

```bash
# 基本转写
opc asr audio.wav

# 指定输出目录
opc asr recording.mp3 -o ./subtitles

# 不进行自动重断句（保留 ASR 原始切分）
opc asr audio.wav --no-resegment

# 使用 LLM 修复断词和标点错误
opc asr audio.wav --llm-fix

# 只识别前 N 秒（方便测试）
opc asr audio.wav -t 60
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `audio` | | | 输入音频文件（.wav/.mp3/.m4a/.webm/.ogg/.opus 等） |
| `--output-dir` | `-o` | 输入文件同目录 | 输出目录 |
| `--no-resegment` | | `false` | 禁用自动重断句（保留 ASR 原始切分） |
| `--llm-fix` | | `false` | 使用 LLM 修复断词和标点错误 |
| `--trim` | `-t` | 全文件 | 只识别音频的前 N 秒 |

### 输出文件

| 文件 | 说明 |
|---|---|
| `{audio}.srt` | SRT 字幕文件（已断句、去标点） |
| `{audio}.asr.json` | ASR 原始结果（JSON，含精确时间戳） |

### 处理流程

```
音频文件 → fun-asr-realtime 转写 → 保存原始 JSON
                                    ↓
                              自动重断句（按逗号逐句切分）
                                    ↓
                              [可选] LLM 断句纠错
                                    ↓
                              生成 SRT 字幕
```

---

## tts — 文字转语音（CosyVoice + GLM-TTS）

默认使用阿里云 CosyVoice v3-flash 模型，音色为 **龙呼呼（天真烂漫女童）**。同时支持智谱 GLM-TTS 引擎（`--engine glm-tts`）。

### 使用范例

```bash
# 默认 (CosyVoice v3-flash + 龙呼呼音色)
opc tts "你好，今天天气真不错" -o output.wav

# 指定 CosyVoice 音色
opc tts "欢迎收听" -o output.wav --voice longhuhu_v3
opc tts "新闻播报" -o output.wav --voice longshuo_v3

# 切换回智谱引擎
opc tts "你好" -o output.wav --engine glm-tts --voice tongtong

# 调节语速
opc tts "你好" --speed 1.2

# 智谱引擎克隆音色
opc tts "我是克隆的声音" -o output.wav --engine glm-tts --clone --ref-audio ref.wav

# 克隆时指定参考文本和音色名称
opc tts "你好世界" -o out.wav --engine glm-tts --clone --ref-audio ref.wav --ref-text "参考音频的文字" --voice-name my_voice
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `text` | | | 要转换的文本（`--list-voices` 时可省略） |
| `--output` | `-o` | `output.wav` | 输出音频文件路径 |
| `--voice` | | `tongtong` | 音色名称（qwen-tts 引擎默认 `longhuhu_v3`） |
| `--speed` | | `1.0` | 语速 [0.5, 2] |
| `--volume` | | `1.0` | 音量 (0, 10]（仅 glm-tts 引擎） |
| `--format` | | `wav` | 音频格式：`wav` / `pcm` |
| `--engine` | | `qwen-tts` | TTS 引擎：`qwen-tts`（CosyVoice）/ `glm-tts`（智谱） |
| `--watermark` | | `false` | 添加 AI 生成水印（仅 glm-tts 引擎） |
| `--clone` | | `false` | 启用音色克隆模式（仅 glm-tts 引擎） |
| `--ref-audio` | | | 克隆参考音频（mp3/wav，≤10MB） |
| `--ref-text` | | | 参考音频对应文本（可选） |
| `--voice-name` | | | 克隆音色命名（可选） |
| `--list-voices` | | `false` | 列出系统预设音色 |
| `--list-cloned` | | `false` | 列出已克隆的音色 |
| `--env-file` | | | 自定义 .env 文件路径 |

### CosyVoice 预设音色（默认引擎）

qwen-tts 引擎支持 60+ 系统音色，涵盖童声、语音助手、社交陪伴、有声书、方言、新闻播报、直播带货等类别。

| 类别 | 代表音色 |
|---|---|
| 童声 | `longhuhu_v3` 龙呼呼, `longpaopao_v3` 龙泡泡, `longniuniu_v3` 龙牛牛 |
| 标杆 | `longanyang` 龙安洋（阳光大男孩）, `longanhuan` 龙安欢（欢脱元气女） |
| 语音助手 | `longxiaochun_v3` 龙小淳, `longxiaoxia_v3` 龙小夏, `longyumi_v3` YUMI |
| 社交陪伴 | `longhua_v3` 龙华, `longcheng_v3` 龙橙, `longyan_v3` 龙颜 |
| 有声书 | `longmiao_v3` 龙妙, `longyue_v3` 龙悦, `longxiu_v3` 龙修 |
| 方言 | `longjiaxin_v3` 龙嘉欣（粤语）, `longlaotie_v3` 龙老铁（东北） |
| 新闻播报 | `longshuo_v3` 龙硕, `loongbella_v3` Bella3.0 |
| 直播带货 | `longanran_v3` 龙安燃, `longanxuan_v3` 龙安宣 |

完整音色列表见代码 `opc_cli/tts.py` 中的 `QWEN_TTS_VOICES_V3`。

### GLM-TTS 预设音色（`--engine glm-tts`）

| 音色 ID | 名称 |
|---|---|
| `tongtong` | 彤彤（glm-tts 默认） |
| `xiaochen` | 小陈 |
| `chuichui` | 锤锤 |
| `jam` | jam |
| `kazi` | kazi |
| `douji` | douji |
| `luodo` | luodo |

### 长文本处理

超长文本自动按标点分段合成，拼接为完整音频。

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

## gpt-img — GPT-Image-2-Official 文生图

使用 GPT-Image-2-Official（OpenAI 官方模型）根据提示词生成高质量图片，
异步接口，支持文生图 / 图生图 / 批量生成。默认使用 LLM 丰富提示词。

### 使用范例

```bash
# 基本文生图
opc gpt-img "一只穿着宇航服的猫"

# 指定输出路径
opc gpt-img "山水画" -o ./output/landscape.png

# 指定宽高比和分辨率
opc gpt-img "人像" -s 3:4 -r 2k
opc gpt-img "风景" -s 16:9 -r 1k

# 指定图片质量
opc gpt-img "海报" --quality high

# 指定输出格式和压缩强度
opc gpt-img "照片" --output-format jpeg --output-compression 85

# 不使用 LLM 丰富提示词
opc gpt-img "a cute cat" --no-enhance

# 图生图：指定参考图
opc gpt-img "换成赛博朋克风格" --ref original.png

# 多张参考图
opc gpt-img "融合这些风格" --ref img1.png --ref img2.png

# 批量生成 4 张
opc gpt-img "多种方案" --n 4

# WSL 下代理自动启用，Windows 下需手动指定
opc gpt-img "风景" --proxy

# 仅返回图片 URL，不下载
opc gpt-img "测试图" --no-download
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `prompt` | | | 提示词（中英文） |
| `--output` | `-o` | 自动生成 | 输出图片路径 |
| `--size` | `-s` | `2:3` | 宽高比或像素：15种比例 + auto + 像素（如 1024*1536） |
| `--resolution` | `-r` | `1k` | 分辨率档位：1k / 2k / 4k（全比例支持 4K） |
| `--quality` | | `auto` | 图片质量：auto / low / medium / high |
| `--enhance` | | `true` | 使用 LLM 丰富提示词 |
| `--ref` | | | 参考图路径或 URL（可多次指定，最多16张） |
| `--n` | | `1` | 生成张数（1 ~ 4） |
| `--output-format` | | `png` | 输出格式：png / jpeg / webp |
| `--output-compression` | | | 压缩强度 0-100（仅 jpeg/webp） |
| `--moderation` | | `auto` | 审核强度：auto / low |
| `--no-download` | | `false` | 仅返回图片 URL |
| `--proxy` | | `false` | WSL 下默认启用，此参数可手动开关 |
| `--timeout` | | `600` | 最大等待时间（秒） |
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

---

## comfyui — ComfyUI 进程管理 + 工作流提交

启动/停止 Windows 下的 ComfyUI 服务，提交自定义工作流处理图片。自动检测工作流节点（LoadImage / KSampler / SaveImage / 提示词节点），无需手动配置节点 ID。

### 使用范例

```bash
# ── 进程管理 ──

# 启动 ComfyUI（WSL 下自动转换路径）
opc comfyui --start

# 指定端口
opc comfyui --start --port 8189

# 检查运行状态
opc comfyui --status

# 关闭 ComfyUI
opc comfyui --stop

# ── 工作流提交 ──

# 使用默认工作流（confyui/Qwen_remove.json）处理图片
opc comfyui --run -i photo.jpg

# 指定输出目录
opc comfyui --run -i photo.jpg -o ./results

# 指定工作流文件
opc comfyui --run -w confyui/my_workflow.json -i photo.jpg

# 带提示词（用于 Qwen_edit 等支持 prompt 的工作流）
opc comfyui --run -i photo.jpg -p "去除背景，保持人物不变"

# 指定随机种子（可复现结果）
opc comfyui --run -i photo.jpg -s 12345

# 自定义采样参数
opc comfyui --run -i photo.jpg --steps 8 --cfg 2.0 --denoise 0.8

# 指定 ComfyUI 服务地址（WSL2 下会自动检测，通常无需手动指定）
opc comfyui --run -i photo.jpg --server http://172.30.64.1:8188

# 增大超时时间（大图处理较慢时）
opc comfyui --run -i photo.jpg -t 600
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| **进程管理** | | | |
| `--start` | | `false` | 启动 ComfyUI 服务 |
| `--stop` | | `false` | 关闭 ComfyUI 服务 |
| `--status` | | 默认行为 | 检查运行状态 |
| `--listen` | | `0.0.0.0` | 监听地址 |
| `--port` | | `8188` | 监听端口 |
| **工作流提交** | | | |
| `--run` | | `false` | 提交工作流到 ComfyUI 执行 |
| `--workflow` | `-w` | `confyui/Qwen_remove.json` | 工作流 JSON 文件路径 |
| `--image` | `-i` | | 输入图片路径 |
| `--prompt` | `-p` | | 提示词（用于编辑类工作流） |
| `--seed` | `-s` | 自动生成 | 随机种子 |
| `--output` | `-o` | 当前目录 | 输出目录 |
| `--server` | | `http://127.0.0.1:8188` | ComfyUI 服务地址（WSL2 自动检测） |
| `--timeout` | `-t` | `300` | 最大等待时间（秒） |
| `--steps` | | | 采样步数 |
| `--cfg` | | | CFG scale |
| `--denoise` | | | 去噪强度 |
| `--output-prefix` | | | 输出文件名前缀 |
| **高级：节点覆盖** | | | |
| `--load-image-node` | | 自动检测 | LoadImage 节点 ID |
| `--ksampler-node` | | 自动检测 | KSampler 节点 ID |
| `--save-image-node` | | 自动检测 | SaveImage 节点 ID |
| `--prompt-node` | | 自动检测 | 提示词节点 ID |
| `--seed-node` | | 自动检测 | 种子节点 ID |

### 工作流文件

工作流 JSON 文件放在 `confyui/` 目录下。关键节点会自动检测：

- **LoadImage** — 输入图片（自动设置文件名）
- **KSampler** — 采样器（自动设置 seed）
- **SaveImage** — 输出保存（自动设置前缀）
- **Prompt 节点** — 含 `prompt` 或 `text` 输入的节点

特殊工作流可通过 `--*-node` 系列参数手动指定节点 ID。

### 环境配置

```bash
# ComfyUI 安装目录（包含 python/python.exe 和 main.py）
COMFYUI_ROOT=/mnt/d/AI_Graph/ConfyUI-aki/ComfyUI-aki-v1
```

### WSL2 注意事项

- ComfyUI 的 `python.exe` 是 Windows 程序，`--start` 自动转换 WSL→Windows 路径
- WSL2 下 `127.0.0.1` 不通 Windows，`--run` 自动从 `/etc/resolv.conf` 获取宿主 IP
- 加载 20GB 模型需足够虚拟内存，建议页面文件 ≥ 16GB

---

## aigate — 云扉 AIGate ComfyUI

管理云扉中的 ComfyUI 实例，并通过其公开的原生 ComfyUI API 上传输入图、提交 API 格式工作流、等待完成并下载输出。Token 仅用于云扉 OpenAPI；访问实例的 ComfyUI 接口时不会携带 Token。

### 环境配置

```bash
# 必填：云扉控制台的 Bearer Token（可带或不带 "Bearer " 前缀）
AIGATE_TOKEN=your_aigate_token

# 仅在明确创建一台新实例时需要；不要将账户专属镜像 ID 写进共享配置。
AIGATE_SKU_NAME=your_gpu_sku
AIGATE_AREA_NAME=your_area
AIGATE_IMAGE_ID=your_image_id
AIGATE_IMAGE_TYPE=2
```

`--start` 只会启动已有的实例，避免一次任务意外创建计费资源。创建新实例必须同时使用 `--create`，并且为避免重复计费，云扉控制台中已有任何实例时会被拒绝。

### 使用范例

```bash
# 查看当前实例和状态
opc aigate --status

# 启动指定的已有实例，并等待 ComfyUI 服务可用
opc aigate --start --instance INSTANCE_ID

# 启动实例后，立即提交工作流；输入图会上传到云端，结果下载到本地目录
opc aigate --start --instance INSTANCE_ID --run \
  -w workflow_api.json -i photo.png -p "去除背景" -o ./results

# 已有实例正在运行时，可直接提交
opc aigate --run -w workflow_api.json -i photo.png -o ./results

# 明确创建一台新实例（该操作可能产生云资源费用）
opc aigate --start --create \
  --sku GPU_SKU --area AREA --image-id IMAGE_ID --image-type 2

# 关闭实例：必须明确指定 ID，避免误关其他实例
opc aigate --stop --instance INSTANCE_ID
```

工作流应为 ComfyUI 的 API JSON 格式。CLI 会自动识别 `LoadImage`、`KSampler`、`SaveImage` 与带 `prompt`/`text` 输入的节点；对于特殊工作流，可沿用 `--load-image-node`、`--prompt-node` 等节点覆盖参数。

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
├── comfyui.py      # ComfyUI 进程管理 + 工作流提交
├── aigate.py       # 云扉 AIGate ComfyUI 实例管理 + 工作流提交
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
