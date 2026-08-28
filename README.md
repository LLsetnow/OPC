# OPC CLI

OPC 工具集命令行界面 —— 命令采用「模态 + 动词」两级结构：`opc <模态> <动词> [参数]`。覆盖媒体下载/总结、音乐理解/生成、图片理解/生成、视频理解/生成、语音合成/识别、本地TTS、本地/云扉 ComfyUI、AI日报。

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

`.env.example` 包含当前代码读取的配置项及详细说明。

## 命令一览

```
opc                             显示帮助
opc media download <URL>        媒体下载/总结（B站/抖音/X/网易云，URL 自动识别平台；--summarize 下载→ASR→总结）
opc music understand <音频>     音乐理解：使用 Qwen3-Omni Captioner 分析音频
opc music beats <音频>          librosa 鼓点检测：BPM、节拍和起音时刻
opc music generate <描述>       音乐生成：使用阿里云 Fun-Music / MiniMax 生成歌曲或纯音乐
opc image understand <图片>     图片理解：使用视觉模型分析图片内容
opc image generate <描述>       文生图/图生图/图像编辑（--engine qwen | gpt-image）
opc video understand <视频>     视频理解：使用 Qwen3-VL 分析视频和镜头运动
opc video generate <描述>       视频生成：使用 MiniMax H3 生成并下载 MP4
opc speech tts <文本>           文字转语音（CosyVoice / GLM-TTS，支持音色克隆）
opc speech asr <音频>           语音识别：音频 → SRT/JSON 字幕
opc local-tts                   本地语音合成 + 服务管理（Qwen3-TTS）
opc comfyui                     ComfyUI 进程管理 + 工作流提交
opc aigate                      云扉 AIGate ComfyUI 实例管理 + 工作流提交
opc check-api                   检查 .env 中 API 的连通性
opc news                        AI 日报：自动收集 AI 新闻并生成简报
```

---

## 环境变量速查

| 环境变量 | 用途 | 涉及命令 |
|---|---|---|
| `DEEPSEEK_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | DeepSeek 通用 LLM（总结/日报/提示词丰富） | media download --summarize, news, speech asr --llm-fix, image generate --engine gpt-image, check-api |
| `ZHIPU_API_KEY` / `ZHIPU_BASE_URL` | 智谱 API（GLM-TTS、音色克隆、视觉模型） | speech tts --engine glm-tts, image understand, check-api |
| `ALIYUN_API_KEY` / `ASR_MODEL` / `QWEN_TTS_MODEL` / `IMAGE_MODEL` / `AUDIO_MODEL` / `VIDEO_MODEL` | 阿里云 DashScope 统一凭证：ASR、CosyVoice TTS、Qwen Image 3.0、Qwen3-Omni 音乐理解、Qwen3-VL 视频理解 | speech asr, media download --summarize, speech tts (默认), image generate, music understand, video understand, music generate (aliyun) |
| `VIDEO_BASE_URL` / `VIDEO_MODEL` | Qwen3-VL 视频理解的 OpenAI 兼容接口和模型 | video understand |
| `MUSIC_GEN_PROVIDER` / `MUSIC_GEN_MODEL` / `MUSIC_GEN_WORKSPACE_ID` / `MUSIC_GEN_BASE_URL` | 阿里云 Fun-Music 音乐生成配置 | music generate --provider aliyun |
| `MINIMAX_API_KEY` / `MINIMAX_MUSIC_MODEL` / `MINIMAX_MUSIC_BASE_URL` | MiniMax Music 音乐生成配置 | music generate --provider minimax |
| `MINIMAX_API_KEY` / `MINIMAX_VIDEO_MODEL` / `MINIMAX_VIDEO_BASE_URL` | MiniMax H3 视频生成配置 | video generate |
| `GPT_IMAGE_API_KEY` / `GPT_IMAGE_BASE_URL` / `GPT_IMAGE_MODEL` | GPT-Image-2 文生图 | image generate --engine gpt-image |
| `GPT_IMG_PROXY` | gpt-image 代理，WSL 下自动启用 | image generate --engine gpt-image (--proxy) |
| `YT_DLP_COOKIES` | yt-dlp cookies 文件路径 | media download |
| `BILI_FOLDER` | B站默认输出目录 | media download |
| `DOUYIN_FOLDER` | 抖音默认输出目录 | media download |
| `X_FOLDER` | X 视频默认输出目录 | media download |
| `MUSIC_FOLDER` | 网易云音乐默认输出目录 | media download |
| `NEWS_FOLDER` | news 默认输出目录 | news |
| `COMFYUI_ROOT` | ComfyUI 根目录 | comfyui --start |
| `AIGATE_TOKEN` | 云扉 Bearer Token | aigate |
| `AIGATE_SKU_NAME` / `AIGATE_AREA_NAME` / `AIGATE_IMAGE_ID` / `AIGATE_IMAGE_TYPE` | 显式创建云扉实例的预设 GPU、区域和镜像 | aigate --start --create |

---

## media download — 统一媒体下载/总结

从 B站/抖音/X/网易云链接下载媒体，URL 自动识别平台。B站/抖音/X 可加 `--summarize` 走「下载音频 → ASR 转写 → 内容总结」流水线（多平台通用）；网易云下载为带 ID3 元数据的 MP3。

### 使用范例

```bash
# 完整流程：下载 → ASR → 总结（B站/抖音/X 通用）
opc media download "https://www.bilibili.com/video/BV1xx" --summarize

# 指定输出目录
opc media download "https://..." -o ./my_output --summarize

# 仅下载 B站音频并转为 MP3（带 ID3 元数据）
opc media download "https://..." --audio-only

# 指定 MP3 比特率，或跳过元数据写入
opc media download "https://..." --audio-only --bitrate 320
opc media download "https://..." --audio-only --no-metadata

# 跳过下载，从 output 目录自动查找已有音频文件
opc media download "URL" --summarize --skip-download

# 跳过下载，手动指定音频文件
opc media download "URL" --summarize --skip-download --audio-file ./output/audio.m4a

# 跳过下载和 ASR，从 output 目录自动查找已有字幕文件生成总结
opc media download "URL" --summarize --skip-download --skip-asr

# 跳过 ASR，手动指定字幕文件
opc media download "URL" --summarize --skip-download --skip-asr --asr-file ./output/audio.srt

# 使用 cookies 下载需要登录的视频
opc media download "https://..." --cookies ./cookies.txt

# 抖音视频下载为 MP4
opc media download "https://www.douyin.com/video/7644571768053571003"

# 抖音视频下载到指定目录（登录可见或受限视频使用 cookies）
opc media download "https://www.douyin.com/video/7644571768053571003" -o ./videos --cookies ./cookies.txt

# X (Twitter) 视频下载（通常需要 cookies）
opc media download "https://x.com/i/status/2038177089082261736" --cookies ~/cookies.txt

# 网易云音乐下载（单曲/专辑/歌单）
opc media download "https://music.163.com/song?id=2143914149"

# 网易云音乐下载到指定目录 + 高比特率
opc media download "https://music.163.com/playlist?id=xxx" -o ./music --bitrate 320
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `url` | | | 媒体链接，自动识别平台：bilibili.com / b23.tv / douyin.com / x.com / twitter.com / music.163.com |
| `--output-dir` | `-o` | 按平台读 `BILI_FOLDER`/`DOUYIN_FOLDER`/`X_FOLDER`/`MUSIC_FOLDER` 或 `./output` | 输出目录 |
| `--cookies` | | `YT_DLP_COOKIES` | yt-dlp cookies 文件路径 |
| `--audio-only` | | `false` | 仅下载音频并转为 MP3（仅 bilibili 生效） |
| `--bitrate` | | `192` | MP3 比特率（`--audio-only` 或网易云时生效） |
| `--no-metadata` | | `false` | 跳过 MP3 的 ID3 元数据写入 |
| `--playlist` | | `false` | 下载全部曲目（网易云专辑/歌单/歌手链接默认已启用） |
| `--summarize` | | `false` | 下载音频 → ASR 转写 → 内容总结（B站/抖音/X 通用） |
| `--skip-download` | | `false` | 跳过下载，从 output-dir 自动查找音频（需 `--summarize`） |
| `--audio-file` | | | 手动指定已有音频文件路径（需 `--summarize`） |
| `--skip-asr` | | `false` | 跳过 ASR，从 output-dir 自动查找字幕文件（需 `--summarize`） |
| `--asr-file` | | | 手动指定 ASR JSON 或 SRT 文件路径（需 `--summarize`） |
| `--llm-fix` | | `false` | 使用 LLM 修复 ASR 断词和标点错误 |
| `--env-file` | | | 自定义 .env 文件路径 |

### 输出文件（--summarize 模式）

| 文件 | 说明 |
|---|---|
| `{title}.m4a` | 下载的音频文件 |
| `{title}.mp3` | `--audio-only` 模式生成的 MP3（默认含标题、UP主和封面） |
| `{title}.srt` | SRT 字幕文件 |
| `{title}.asr.json` | ASR 原始结果（JSON） |
| `{title}.md` | Markdown 内容总结（含视频时间线链接） |

抖音的登录、年龄限制或反爬校验可能要求导出登录后的 cookies；X 大量视频对未登录用户不可见，报 "No video could be found" 时请用 `--cookies` 重试。请只下载有权保存或使用的视频。

---

## speech asr — 语音识别

将音频文件转写为 SRT 字幕和 JSON 文件。使用阿里云 DashScope fun-asr-realtime 模型，支持精确时间戳、LLM 智能断句纠错。

### 使用范例

```bash
# 基本转写
opc speech asr audio.wav

# 指定输出目录
opc speech asr recording.mp3 -o ./subtitles

# 不进行自动重断句（保留 ASR 原始切分）
opc speech asr audio.wav --no-resegment

# 使用 LLM 修复断词和标点错误
opc speech asr audio.wav --llm-fix

# 只识别前 N 秒（方便测试）
opc speech asr audio.wav -t 60
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

## speech tts — 文字转语音（CosyVoice + GLM-TTS）

默认使用阿里云 CosyVoice v3-flash 模型，音色为 **龙呼呼（天真烂漫女童）**。同时支持智谱 GLM-TTS 引擎（`--engine glm-tts`）。本地 Qwen3-TTS 使用独立命令 `opc local-tts`。

### 使用范例

```bash
# 默认 (CosyVoice v3-flash + 龙呼呼音色)
opc speech tts "你好，今天天气真不错" -o output.wav

# 指定 CosyVoice 音色
opc speech tts "欢迎收听" -o output.wav --voice longhuhu_v3
opc speech tts "新闻播报" -o output.wav --voice longshuo_v3

# 切换回智谱引擎
opc speech tts "你好" -o output.wav --engine glm-tts --voice tongtong

# 调节语速
opc speech tts "你好" --speed 1.2

# 智谱引擎克隆音色
opc speech tts "我是克隆的声音" -o output.wav --engine glm-tts --clone --ref-audio ref.wav

# 克隆时指定参考文本和音色名称
opc speech tts "你好世界" -o out.wav --engine glm-tts --clone --ref-audio ref.wav --ref-text "参考音频的文字" --voice-name my_voice
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

## image understand — 图片理解

使用视觉模型分析图片内容，支持本地图片和网络 URL，自动压缩超大图片。

### 使用范例

```bash
# 分析本地图片
opc image understand photo.jpg

# 分析网络图片
opc image understand "https://example.com/image.jpg"

# 自定义提问
opc image understand photo.jpg -p "这张图片里有什么动物？"

# 输出结果到文件
opc image understand photo.jpg -o result.txt

# 增大 max_tokens 获取更详细的回答
opc image understand photo.jpg --max-tokens 4096

# 分析 UI 控件的像素位置
opc image understand ui.png -p "每个控件的相对位置和像素大小是什么"
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
- API 凭证：视觉模型统一使用 `ZHIPU_API_KEY`

---

## video understand — Qwen3-VL 视频理解

使用阿里云 DashScope 的 Qwen3-VL 分析视频内容、镜头运动、构图、主体动作和时间线。API Key 使用 `.env` 中的 `ALIYUN_API_KEY`，默认模型为 `qwen3-vl-235b-a22b-instruct`。

### 使用范例

```bash
# 分析本地视频
opc video understand ./input/video.mp4

# 重点分析运镜并保存结果
opc video understand ./input/video.mp4 -p "按时间段分析镜头运动、景别、推拉摇移和主体动作" -o ./output/video-analysis.txt

# 分析模型能够直接访问的远程视频 URL
opc video understand "https://example.com/video.mp4"
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `video` | | | 本地视频路径或可直接访问的视频 URL |
| `--prompt` | `-p` | 分析内容、镜头运动、构图、动作和时间线 | 提问内容 |
| `--output` | `-o` | 终端输出 | 将结果保存到 UTF-8 文本文件 |
| `--model` | | `.env` 的 `VIDEO_MODEL` | Qwen3-VL 模型名称 |
| `--max-tokens` | | `4096` | 最大输出 token 数 |
| `--temperature` | | `0.7` | 生成温度 [0, 1] |
| `--env-file` | | | 自定义 `.env` 文件路径 |

本地视频会编码为 `data:` URI 后发送；X/Bilibili 帖子页面 URL 不是直接视频 URL，需要先下载视频（`opc media download <URL>`）再调用此命令。

---

## video generate — MiniMax H3 视频生成

使用 MiniMax H3 当前 v2 异步接口生成视频：命令先创建任务，再轮询任务状态，成功后自动把结果下载为 MP4。API Key 使用 `.env` 中的 `MINIMAX_API_KEY`，默认中国区地址为 `https://api.minimaxi.com`，默认模型为 `MiniMax-H3`。

### 使用范例

```bash
# 文生视频
opc video generate "一只橘猫在雨夜街头撑伞慢慢走过，电影感，环境声自然" \
  --duration 5 --resolution 2K --ratio 16:9 -o output/cat.mp4

# 首帧生视频；画面比例由首帧图片决定，无需传 --ratio
opc video generate "让首帧中的人物自然转身并走向远处" \
  --first-frame "https://example.com/first.png" -o output/first-frame.mp4

# 首尾帧与多模态参考素材（各参数可重复指定）
opc video generate "保持人物和场景一致，平滑完成镜头过渡" \
  --first-frame "https://example.com/first.png" \
  --last-frame "https://example.com/last.png" \
  --reference-audio "https://example.com/voice.wav" \
  -o output/transition.mp4
```

### 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `prompt` | | 英文或中文视频提示词，最多 7000 字符 |
| `--duration` | `5` | 视频时长，4–15 秒整数 |
| `--resolution` | `2K` | `768P` 或 `2K` |
| `--ratio` | `16:9` | 仅文生视频使用；可选 `1:1`、`16:9`、`4:3`、`3:2`、`2:3`、`3:4`、`9:16`、`21:9`；带素材时由输入决定 |
| `--first-frame` / `--last-frame` | | 首帧/尾帧图片公网 URL 或 data URI |
| `--reference-image` | | 参考图片 URL，可重复指定，最多 9 张（含首尾帧） |
| `--reference-video` | | 参考视频 URL，可重复指定，最多 3 个 |
| `--reference-audio` | | 参考音频 URL，可重复指定，最多 3 个 |
| `--model` | `.env` 的 `MINIMAX_VIDEO_MODEL` | 默认 `MiniMax-H3` |
| `--output` / `-o` | `output/minimax_h3_<时间戳>.mp4` | 输出视频路径 |
| `--timeout` | `900` | 最长等待任务时间（秒） |
| `--poll-interval` | `10` | 任务轮询间隔（秒） |

MiniMax H3 视频生成按输出时长计费；提交真实任务前请确认 API Key 和费用配置。图片、视频和音频参考素材需要 MiniMax 服务端可访问的公网 URL 或 data URI，本地路径不会自动上传。

---

## music understand / music beats — 音乐理解与鼓点检测

使用阿里云 `qwen3-omni-30b-a3b-captioner` 分析本地音频，自动描述曲风、乐器、音色、情绪、氛围和段落结构。API Key 从 `.env` 的 `ALIYUN_API_KEY` 读取。`music beats` 使用 librosa 在本地检测 BPM、节拍和起音时刻，不调用云端模型。

### 使用范例

```bash
# 直接输出音乐分析
opc music understand Hypervoid.m4a

# 保存分析结果
opc music understand Hypervoid.m4a -o Hypervoid.analysis.txt

# 覆盖默认模型
opc music understand Hypervoid.m4a --model qwen3-omni-30b-a3b-captioner

# 独立使用 librosa 检测 BPM、节拍和鼓点候选时刻（默认每秒最多保留 1 个）
opc music beats Hypervoid.m4a

# 提高阈值，进一步减少弱鼓点；调整最小间隔
opc music beats Hypervoid.m4a --beat-strength-threshold 0.35 --beat-min-interval 1.0
```

### 参数（understand）

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `audio` | | | 输入音频路径 |
| `--output` | `-o` | 终端输出 | 将分析结果保存到文本文件 |
| `--model` | | `.env` 中的 `AUDIO_MODEL` | 音乐理解模型，默认 `qwen3-omni-30b-a3b-captioner` |
| `--env-file` | | | 自定义 `.env` 文件路径 |

### 参数（beats）

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `audio` | | | 输入音频路径 |
| `--output` | `-o` | 终端输出 | 将分析结果保存到文本文件 |
| `--beat-strength-threshold` | `--beat-threshold` | `0.2` | 只保留相对强度不低于该值的事件（0～1） |
| `--beat-min-interval` | | `1.0` 秒 | 每个时间窗口只保留最强事件 |
| `--env-file` | | | 自定义 `.env` 文件路径 |

`opc music beats <音频>` 会合并 `beat_times` 和 `onset_times` 候选，先按 `beat_strength` 阈值过滤，再按 `beat-min-interval` 窗口只保留最强事件。`beat_times` 是节拍网格，`onset_times` 是更密集的起音候选；`beat_strengths` / `onset_strengths` 是相对于全曲峰值的 0～1 强度估计，不等同于原始鼓机力度。

---

## image generate — 文生图 / 图生图 / 图像编辑

两个生成引擎统一入口：默认 `--engine qwen`（阿里云 Qwen Image 3.0），`--engine gpt-image` 切换为 GPT-Image（经本机 codex CLI 调用）。qwen 引擎支持文生图和图像编辑（`--image`）；gpt-image 引擎支持文生图/图生图（`--ref`）和批量生成（`--n`）。

> **`image-gen` 生成图像（codex + gpt-image）**
> gpt-image 引擎统一使用本机 `codex exec` 生成：codex 内置 `image_gen__imagegen` 工具（由 gpt-image 驱动，需 ChatGPT 账号登录，本机已验证 codex-cli 0.147+ 可用）。图片由 codex 保存到本地路径，不再依赖 `GPT_IMAGE_API_KEY`。

### 使用范例

```bash
# ── qwen 引擎（默认，阿里云 Qwen Image 3.0）──

# 基本文生图
opc image generate "一只穿着宇航服的猫"

# 指定输出路径
opc image generate "山水画" -o ./output/landscape.png

# 图像编辑：提供一张本地图片、公开 URL 或 data URI
opc image generate "把天空改成绚丽的晚霞" --image ./input/landscape.png

# 多图编辑/融合，最多 3 张参考图
opc image generate "把图 1 的人物换成图 2 的服装" \
  --image ./input/person.png \
  --image ./input/clothes.png

# 指定宽高比 / 像素分辨率
opc image generate "人像" -s 3:4
opc image generate "高清图" -s 2048*2048

# 启用智能提示词改写（默认开启，可 --no-prompt-extend 关闭）
opc image generate "风景" --prompt-extend

# 指定随机种子（可复现结果）
opc image generate "测试" --seed 42

# 仅返回图片 URL
opc image generate "测试图" --no-download

# ── gpt-image 引擎（经 codex CLI，GPT-Image 驱动）──

# 基本文生图（保存到 output/gpt_img_<时间戳>.png）
opc image generate "一只穿着宇航服的猫" --engine gpt-image

# 指定宽高比和输出路径
opc image generate "人像" --engine gpt-image -s 3:4 -o ./output/portrait.png

# 不使用模型提示词优化（默认会优化/丰富提示词）
opc image generate "a cute cat" --engine gpt-image --no-enhance

# 图生图：指定参考图（可多张，作为风格/构图/内容参考）
opc image generate "换成赛博朋克风格" --engine gpt-image --ref original.png
opc image generate "融合这些风格" --engine gpt-image --ref img1.png --ref img2.png

# 批量生成 4 个变体（自动保存为 _1/_2/_3/_4 后缀）
opc image generate "多种方案" --engine gpt-image --n 4 -o ./output/variants.png
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `prompt` | | | 文生图提示词或编辑指令（中英文） |
| `--engine` | | `qwen` | 生成引擎：`qwen`（阿里云 Qwen Image）/ `gpt-image`（GPT-Image，经 codex CLI） |
| `--output` | `-o` | 自动生成 | 输出图片路径（gpt-image 引擎批量时自动加 _1/_2/...） |
| `--size` | `-s` | `2:3` | 宽高比（如 2:3, 16:9）或像素（如 1024*1536） |
| `--model` | | `.env` 的 `IMAGE_MODEL` | qwen 引擎模型名称，默认为 `qwen-image-3.0` |
| `--image` | `-i` | | qwen 引擎编辑输入图片，可重复指定，最多 3 张 |
| `--negative-prompt` | | | qwen 引擎负向提示词 |
| `--n` | | `1` | 生成张数（qwen: 1~6；gpt-image: 1~4 个变体） |
| `--prompt-extend` | | `true` | qwen 引擎智能提示词改写 |
| `--seed` | | 随机 | qwen 引擎随机种子（0~2147483647） |
| `--watermark` | | `false` | qwen 引擎是否添加水印 |
| `--ref` | | | gpt-image 引擎参考图路径（可多次指定，经 codex exec --image 附到会话） |
| `--enhance` | | `true` | gpt-image 引擎是否允许模型优化/丰富提示词 |
| `--timeout` | | `600` | gpt-image 引擎 codex exec 最大等待时间（秒） |
| `--resolution` / `--quality` / `--moderation` / `--output-format` / `--output-compression` / `--proxy` | | | 旧 API 模式参数，codex 模式下已忽略（会提示） |
| `--no-download` | | `false` | qwen 引擎仅返回图片 URL；gpt-image 引擎无额外效果（输出即本地文件） |
| `--env-file` | | | 自定义 .env 文件路径 |

---

## music generate — 阿里云 Fun-Music / MiniMax Music

`opc music generate` 支持两个音乐服务商：阿里云 Fun-Music，以及新版 MiniMax Music 3.0。默认使用阿里云；使用 `--provider minimax` 或设置 `MUSIC_GEN_PROVIDER=minimax` 切换到 MiniMax 的 `music-3.0`。

阿里云根据音乐风格/场景提示词或自定义歌词生成完整歌曲，也可以生成纯音乐。`fun-music-v1` 支持男声/女声；`fun-music-preview` 需要提示词且不支持声音性别参数。MiniMax 使用 `POST /v1/music_generation`，请求包含 `model=music-3.0`、`audio_setting.sample_rate`、`audio_setting.bitrate`、`audio_setting.format` 和 `output_format=url`；音频 URL 需要在 24 小时内下载。根据 MiniMax 官方公告，`music-3.0-free` 等免费音乐 API 已停止服务，`music-3.0` 仅面向历史付费/Token Plan 用户。

Fun-Music 使用 `ALIYUN_API_KEY`，MiniMax 使用 `MINIMAX_API_KEY`。MiniMax 中国区默认 API 地址为 `https://api.minimaxi.com`，国际区可配置为 `https://api.minimax.io`。

### 使用范例

```bash
# 阿里云 Fun-Music（默认）
opc music generate "夏日清新民谣，木吉他与口琴伴奏，适合旅行 Vlog" --gender female -o summer.mp3

# 从歌词文件生成歌曲
opc music generate --lyrics-file lyrics.txt --gender male -o song.wav --format wav

# 生成纯音乐
opc music generate "宁静的钢琴曲，适合深夜阅读的背景音乐" --instrumental -o reading.mp3

# MiniMax Music 3.0：根据风格描述自动生成歌词
opc music generate --provider minimax "梦幻电子流行，明亮女声，适合夜晚城市漫步" -o minimax-song.mp3

# MiniMax Music 3.0：使用自定义歌词
opc music generate --provider minimax \
  --lyrics-file lyrics.txt \
  --model music-3.0 \
  -o minimax-with-lyrics.mp3

# MiniMax 纯音乐
opc music generate --provider minimax "电影感钢琴与弦乐，逐渐推进，温暖收束" \
  --instrumental -o minimax-instrumental.mp3
```

### 参数

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `prompt` | | | 音乐风格、场景和情绪描述；与 `--lyrics`/`--lyrics-file` 至少提供一个 |
| `--lyrics` | | | 自定义歌词；同时提供 prompt 时歌词优先 |
| `--lyrics-file` | | | 从 UTF-8 文本文件读取自定义歌词 |
| `--provider` | | `.env` 的 `MUSIC_GEN_PROVIDER` 或 `aliyun` | `aliyun` / `minimax` |
| `--gender` | | `female` | `female` / `male`，仅阿里云 `fun-music-v1` 的歌曲模式生效 |
| `--instrumental` | | `false` | 生成纯音乐，忽略歌词和声音性别 |
| `--model` | | 由服务商配置决定 | 阿里云：`fun-music-v1` / `fun-music-preview`；MiniMax：`music-3.0` / `music-2.6` |
| `--lyrics-optimizer` | | MiniMax 无歌词时自动启用 | 根据 prompt 自动生成歌词；可用 `--no-lyrics-optimizer` 关闭 |
| `--format` | | `mp3` | 输出格式：`mp3` / `wav` |
| `--output` | `-o` | 自动生成 | 输出音频路径 |
| `--env-file` | | | 自定义 `.env` 文件路径 |

两个服务商的接口返回临时音频 URL，命令会自动下载到本地；如需保存歌词，请使用 `--lyrics` 或 `--lyrics-file` 保留输入内容。MiniMax 的 URL 有效期为 24 小时，命令会立即下载。

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

`--start` 只会启动已有的实例，避免一次任务意外创建计费资源。创建新实例必须同时使用 `--create`，并配置 SKU、区域和镜像；即使云扉控制台中已有实例，也会按请求创建新的实例。

### 使用范例

```bash
# 查看当前实例和状态
opc aigate --status

# 查询当前账户可创建实例的 GPU SKU（默认查询华东一区和华东二区）；可用 --area 按区域筛选
opc aigate --gpus
opc aigate --gpus --area 华东一区

# 查询当前账户的个人镜像（创建实例时使用 --image-type 3）
opc aigate --images

# 查询特定区域和 GPU 可用的社区镜像
opc aigate --community-images --area 华东一区 --sku 4090D-48G

# 列出仓库 workflows/ 中可提交的本地 ComfyUI 工作流（无需 Token）
opc aigate --workflows

# 启动指定的已有实例，并等待 ComfyUI 服务可用
opc aigate --start --instance INSTANCE_ID

# 启动实例后，立即提交工作流；输入图会上传到云端，结果下载到本地目录
opc aigate --start --instance INSTANCE_ID --run \
  -w workflow_api.json -i photo.png -p "去除背景" -o ./results

# 已有实例正在运行时，可直接提交
opc aigate --run -w workflow_api.json -i photo.png -o ./results

# 视频工作流：上传驱动视频和参考图片
opc aigate --run -w video_workflow_api.json \
  --video input.mp4 --reference-image character.png -o ./results

# 明确创建一台新实例（该操作可能产生云资源费用）
opc aigate --start --create \
  --sku GPU_SKU --area AREA --image-id IMAGE_ID --image-type 2

# 关闭实例：必须明确指定 ID，避免误关其他实例
opc aigate --stop --instance INSTANCE_ID

# 释放实例：会删除实例资源，必须明确指定 ID
opc aigate --release --instance INSTANCE_ID
```

工作流应为 ComfyUI 的 API JSON 格式。CLI 会自动识别 `LoadImage`、`KSampler`、`SaveImage` 与带 `prompt`/`text` 输入的节点；对于特殊工作流，可沿用 `--load-image-node`、`--prompt-node` 等节点覆盖参数。

---

## check-api — API 连通性检查

根据当前 `.env` 中的凭证配置，先列出每个 `opc` 命令的可用程度，再检查 API 的连通性、状态、耗时和详情。

命令状态分为：

- **可用**：命令的主要功能所需配置齐全。
- **部分可用**：命令仍有部分模式可用，例如 `media download`（仅下载，缺总结所需凭证）。
- **不可用**：缺少该命令所需的 API Key 或 Token。

检查只会显示正在使用的环境变量名，不会打印 API Key 内容。缺少凭证时会直接显示配置问题，不会因为配置读取函数退出而产生重复错误提示。

### 使用范例

```bash
# 检查全部 API
opc check-api

# 只检查 DeepSeek 和 Vision
opc check-api --only deepseek --only vision

# 只检查 Qwen3-VL 视频理解
opc check-api --only video

# 只检查文生图相关
opc check-api --only image --only gpt-image

# 指定 .env 文件
opc check-api --env-file /path/to/.env
```

### 可检查的 API 名称

`deepseek`（兼容别名 `llm`）/ `zhipu` / `asr` / `audio` / `qwen-tts` / `vision` / `video` / `image` / `gpt-image` / `proxy` / `cookies`

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
├── cli.py          # CLI 入口（typer 模态组 + 动词子命令定义）
├── config.py       # 共享配置（环境变量、API Key）
├── logger.py       # 日志系统（TeeWriter 双输出）
├── media.py        # 统一媒体下载：平台识别 + 下载/总结分发
├── bili.py         # B站流水线（下载音频 + ASR 转写 + 内容总结）
├── audio.py        # Qwen3-Omni 音乐理解 + librosa 鼓点检测
├── video.py        # Qwen3-VL 视频理解
├── minimax_video.py # MiniMax H3 视频生成（v2 异步接口）
├── tts.py          # GLM-TTS 语音合成 + 音色克隆
├── local_tts.py    # Qwen3-TTS 本地语音合成
├── tts_server.py   # TTS 常驻服务（Flask）
├── vision.py       # 图片理解（视觉模型）
├── comfyui.py      # ComfyUI 进程管理 + 工作流提交
├── aigate.py       # 云扉 AIGate ComfyUI 实例管理 + 工作流提交
├── check_api.py    # API 连通性检查
├── codex_image.py  # GPT-Image 文生图（经本机 codex CLI 的内置 image_gen 工具）
├── gpt_image.py    # 旧版 GPT-Image API 客户端（已不再被 CLI 使用）
├── text2img.py     # 阿里云 Qwen Image 3.0 文生图与图像编辑
└── ai_daily.py     # AI 日报
```

## 依赖

- **typer** — CLI 框架
- **rich** — 终端美化输出
- **requests** — HTTP 请求（TTS / 音色克隆）
- **python-dotenv** — .env 文件加载
- **openai** — LLM 内容总结 / 图片理解
- **zhipuai** — 智谱 ASR 语音识别
- **yt-dlp** — 媒体下载（B站/抖音/X/网易云）
- **soundfile** + **numpy** — 音频分片处理
- **dashscope** — 阿里云 Qwen3-Omni 音乐理解 / ASR / TTS API
- **librosa** — BPM、节拍和起音时刻检测
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

**Q: 视频下载失败**

- 确保安装了 `yt-dlp` 和 `ffmpeg`
- 部分视频需要登录，使用 `--cookies` 参数提供 cookies 文件
- 使用浏览器扩展 "Get cookies.txt LOCALLY" 导出相应站点的 cookies

**Q: `local-tts` 报 `No module named 'torch'`**

`opc` 通过 pipx 安装的环境不包含 torch。需在有 torch 的 venv 中安装 opc：
```bash
source ~/qwen3-tts-venv/bin/activate
~/qwen3-tts-venv/bin/pip install -e /mnt/d/github/OPC
```

**Q: `image understand` 输出为空**

可能是 `--max-tokens` 不够，模型推理过程消耗了配额。尝试增大：
```bash
opc image understand photo.jpg --max-tokens 4096
```
