# TTS 语音合成工具集

本目录包含两种语音合成方案：智谱 GLM-TTS（云端 API）和 Qwen3-TTS（本地 GPU 推理）。

## 文件说明

| 文件 | 说明 |
|---|---|
| `glm_tts.py` | 智谱 GLM-TTS 云端 API 脚本（需联网、需 API Key） |
| `qwen3_tts.py` | Qwen3-TTS 本地推理脚本（需 GPU、需下载模型） |
| `Qwen3-TTS-本地部署指南.md` | Qwen3-TTS 环境搭建与模型下载指南 |
| `voice/` | 参考音频存放目录（用于音色克隆） |

## 方案对比

| | GLM-TTS（云端） | Qwen3-TTS（本地） |
|---|---|---|
| 运行方式 | 调用智谱 API | 本地 GPU 推理 |
| 硬件要求 | 无 | GPU ≥ 12GB 显存 |
| 网络要求 | 需联网 | 仅下载模型时需要 |
| 费用 | 按字符计费 | 免费 |
| 音色 | 7 种预设 + 克隆 | 9 种预设 + 设计 + 克隆 |
| 语气控制 | 不支持 | 支持（自然语言指令） |
| 延迟 | ~400ms 首帧 | 取决于 GPU 性能 |
| 适合场景 | 快速验证、无 GPU | 批量生成、隐私敏感、离线 |

---

## GLM-TTS（云端 API）

### 前置条件

1. 在 [智谱开放平台](https://open.bigmodel.cn/) 注册获取 API Key
2. 在项目根目录 `.env` 中配置 `ZHIPU_API_KEY`
3. 安装依赖：`pip install requests python-dotenv`

### 使用方式

```bash
# 普通合成（默认音色：彤彤）
python TTS/glm_tts.py "你好，今天天气真不错" -o output.wav

# 指定音色
python TTS/glm_tts.py "你好" -o output.wav --voice xiaochen

# 调节语速和音量
python TTS/glm_tts.py "你好" --speed 1.2 --volume 1.5

# 音色克隆
python TTS/glm_tts.py "我是克隆的声音" --clone --ref-audio TTS/voice/菲比音色.MP3

# 克隆 + 参考文本
python TTS/glm_tts.py "你好世界" --clone --ref-audio ref.wav --ref-text "参考音频的文字"

# 查看可用音色
python TTS/glm_tts.py --list-voices
```

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

### 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `text` | | 要转换的文本 |
| `-o` | `output.wav` | 输出文件路径 |
| `--voice` | `tongtong` | 音色名称或克隆音色 ID |
| `--speed` | `1.0` | 语速 [0.5, 2] |
| `--volume` | `1.0` | 音量 (0, 10] |
| `--format` | `wav` | 音频格式：wav / pcm |
| `--clone` | `false` | 启用音色克隆 |
| `--ref-audio` | | 克隆参考音频（mp3/wav，≤10MB） |
| `--ref-text` | | 参考音频对应文本 |
| `--voice-name` | | 克隆音色命名 |
| `--watermark` | `false` | 添加 AI 生成水印 |
| `--list-voices` | | 列出系统音色 |
| `--list-clone-voices` | | 列出已克隆音色 |

---

## Qwen3-TTS（本地 GPU）

### 前置条件

1. GPU 显存 ≥ 12GB（RTX 3060 12G / RTX 4070 等）
2. 安装依赖：
   ```bash
   pip install qwen-tts soundfile torch
   pip install flash-attn --no-build-isolation  # 推荐加速
   ```
3. 模型文件已下载到 `models/` 目录（详见 `Qwen3-TTS-本地部署指南.md`）

### 三种模型变体

| 参数 `-m` | 模型 | 用途 |
|---|---|---|
| `custom` | CustomVoice | 9 种预设音色 + 自然语言控制语气 |
| `design` | VoiceDesign | 用自然语言描述设计全新音色 |
| `base` | Base | 3 秒快速语音克隆 |

### 使用方式

```bash
# 预设音色
python TTS/qwen3_tts.py "你好，今天天气真不错" -m custom -s Vivian -o output.wav

# 指令控制语气
python TTS/qwen3_tts.py "你居然敢这样说我" -m custom -s Vivian --instruct "用特别愤怒的语气说"

# 设计新音色
python TTS/qwen3_tts.py "欢迎收听今天的节目" -m design --instruct "磁性低沉的男中音，播报风格" -o output.wav

# 语音克隆
python TTS/qwen3_tts.py "我是克隆的声音" -m base --ref-audio TTS/voice/菲比音色.MP3 -o output.wav

# 克隆 + 参考文本（更精准）
python TTS/qwen3_tts.py "你好世界" -m base --ref-audio ref.wav --ref-text "参考音频的文字" -o output.wav

# 查看预设音色
python TTS/qwen3_tts.py --list-speakers
```

### 预设音色（custom 模式）

| 音色 | 描述 | 母语 |
|---|---|---|
| Vivian | 明亮略带锋芒的年轻女声 | 中文 |
| Serena | 温柔温暖的年轻女声 | 中文 |
| Uncle_Fu | 沉稳醇厚的低音男声 | 中文 |
| Dylan | 清爽自然的北京男声 | 中文（京腔） |
| Eric | 活泼略带沙哑的成都男声 | 中文（川普） |
| Ryan | 节奏感强的动感男声 | 英语 |
| Aiden | 阳光清晰的美式男声 | 英语 |
| Ono_Anna | 轻快俏皮的日系女声 | 日语 |
| Sohee | 温暖富有情感的韩语女声 | 韩语 |

### 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `text` | | 要转换的文本 |
| `-o` | `output.wav` | 输出文件路径 |
| `-m` | `custom` | 模型变体：custom / design / base |
| `-s` | `Vivian` | 预设音色（custom 模式） |
| `-l` | `Chinese` | 语言 |
| `--instruct` | | 语气/音色描述（custom 控制语气 / design 描述音色） |
| `--ref-audio` | | 参考音频路径（base 模式必需） |
| `--ref-text` | | 参考音频对应文本（base 模式可选） |
| `--device` | `cuda:0` | 推理设备 |
| `--attn` | `flash_attention_2` | 注意力实现（不可用自动回退 sdpa） |

### 支持语言

中文、英语、日语、韩语、德语、法语、俄语、葡萄牙语、西班牙语、意大利语
