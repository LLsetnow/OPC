# Qwen3-TTS 1.7B 本地部署指南

Qwen3-TTS 1.7B 有 **3 个变体**，按需选择：

| 模型 | 用途 |
|---|---|
| `Qwen3-TTS-12Hz-1.7B-CustomVoice` | 9 种预设音色 + 自然语言控制语气/情感 |
| `Qwen3-TTS-12Hz-1.7B-VoiceDesign` | 用自然语言描述来设计全新音色 |
| `Qwen3-TTS-12Hz-1.7B-Base` | 3 秒快速语音克隆（提供参考音频） |

---

## 1. 环境准备

```bash
conda create -n qwen3-tts python=3.12 -y
conda activate qwen3-tts

# 安装核心包
pip install -U qwen-tts

# 推荐：安装 FlashAttention 2（减少显存占用）
# 内存 < 96GB 时加 MAX_JOBS=4
pip install -U flash-attn --no-build-isolation
```

## 2. 下载模型（可选，运行时自动下载）

```bash
# 国内推荐用 ModelScope
pip install -U modelscope

# Tokenizer（必下载）
modelscope download --model Qwen/Qwen3-TTS-Tokenizer-12Hz --local_dir models/Qwen3-TTS-Tokenizer-12Hz

# 按需下载模型
modelscope download --model Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice --local_dir models/Qwen3-TTS-12Hz-1.7B-CustomVoice
modelscope download --model Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --local_dir models/Qwen3-TTS-12Hz-1.7B-VoiceDesign
modelscope download --model Qwen/Qwen3-TTS-12Hz-1.7B-Base --local_dir models/Qwen3-TTS-12Hz-1.7B-Base
```

## 3. Python 推理代码

### CustomVoice（预设音色 + 指令控制）

```python
import torch, soundfile as sf
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
)

# 单条推理
wavs, sr = model.generate_custom_voice(
    text="其实我真的有发现，我是一个特别善于观察别人情绪的人。",
    language="Chinese",
    speaker="Vivian",
    instruct="用特别愤怒的语气说",  # 可选
)
sf.write("output.wav", wavs[0], sr)
```

**支持的预设音色：**

| Speaker | 描述 | 母语 |
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

### VoiceDesign（文字描述设计音色）

```python
model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    device_map="cuda:0", dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
)

wavs, sr = model.generate_voice_design(
    text="哥哥，你回来啦，人家等了你好久好久了，要抱抱！",
    language="Chinese",
    instruct="体现撒娇稚嫩的萝莉女声，音调偏高且起伏明显，营造出黏人、做作又刻意卖萌的听觉效果。",
)
sf.write("output.wav", wavs[0], sr)
```

### Voice Clone（3 秒快速克隆）

```python
model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    device_map="cuda:0", dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
)

wavs, sr = model.generate_voice_clone(
    text="你好，我是克隆的声音。",
    language="Chinese",
    ref_audio="./reference.wav",     # 参考音频（3秒即可）
    ref_text="参考音频对应的文字内容",
)
sf.write("output.wav", wavs[0], sr)
```

## 4. Web UI Demo

```bash
# CustomVoice
qwen-tts-demo Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice --ip 0.0.0.0 --port 8000

# VoiceDesign
qwen-tts-demo Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --ip 0.0.0.0 --port 8000

# Base（语音克隆，建议 HTTPS）
qwen-tts-demo Qwen/Qwen3-TTS-12Hz-1.7B-Base --ip 0.0.0.0 --port 8000
```

## 5. 显存需求参考

1.7B 模型 BF16 精度下约需 **4-6 GB 显存**（不含 Tokenizer），加上 Tokenizer 约 **8-10 GB**。推荐至少 12GB 显存的 GPU（如 RTX 3060 12G / RTX 4070 等）。

## 6. 支持语言

中文、英语、日语、韩语、德语、法语、俄语、葡萄牙语、西班牙语、意大利语
