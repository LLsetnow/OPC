---
name: glm-tts
description: >
  This skill should be used when the user wants to convert text to speech (TTS) using ZhipuAI's GLM-TTS model,
  or clone a voice from a reference audio sample using GLM-TTS-Clone.
  It supports both standard TTS with preset voices and voice cloning from a 3-30 second audio sample.
  Trigger phrases include "text to speech", "TTS", "语音合成", "文字转语音", "音色克隆", "克隆声音",
  "voice clone", "generate audio", "生成语音".
---

# GLM-TTS Voice Synthesis (glm-tts)

## Purpose

Provide text-to-speech synthesis using ZhipuAI's GLM-TTS model with two modes:

1. **Standard TTS** — Convert text to natural speech using 7 preset voices (tongtong, xiaochen, chuichui, jam, kazi, douji, luodo) or previously cloned voice IDs
2. **Voice Clone** — Upload a 3-30 second reference audio, clone the voice, and generate speech in that voice

Key features:
- Long text (>1024 chars) is automatically split into segments and concatenated
- Watermark audio is disabled by default
- Adjustable speed and volume
- WAV and PCM output formats

## When to Use

- When the user wants to convert text to speech/audio
- When the user wants to clone a voice from a reference audio file
- When the user says things like "text to speech", "语音合成", "生成语音", "克隆声音", "用XX的声音朗读"
- When the user has text content and needs an audio version
- When the user wants to list available or cloned voices

## Prerequisites

### Environment Variables (`.env` file)

| Variable | Required | Default | Description |
|---|---|---|---|
| `ZHIPU_API_KEY` | Yes | - | ZhipuAI API key (obtain at https://open.bigmodel.cn/) |
| `ZHIPU_BASE_URL` | No | `https://open.bigmodel.cn/api/paas/v4` | ZhipuAI API base URL |

### System Dependencies

- **Python packages**: `requests`, `python-dotenv` (see `scripts/requirements.txt`)

## Workflow

### Step 1: Prepare Environment

1. Ensure the `.env` file exists in the project root with at least `ZHIPU_API_KEY` set
2. Install Python dependencies:

```bash
pip install -r scripts/requirements.txt
```

### Step 2: Run TTS

**Standard TTS (preset voice):**

```bash
python scripts/glm_tts.py "你好，今天天气真不错" -o output.wav
```

**Voice Clone:**

```bash
python scripts/glm_tts.py "我是克隆的声音" -o output.wav --clone --ref-audio ref.wav
```

### All Options

| Option | Description |
|---|---|
| `text` | Text to convert to speech (positional) |
| `-o PATH` | Output audio file path (default: `output.wav`) |
| `--voice NAME` | Voice name or cloned voice ID (default: `tongtong`) |
| `--clone` | Enable voice clone mode |
| `--ref-audio PATH` | Reference audio file for cloning (with `--clone`) |
| `--ref-text TEXT` | Text content of the reference audio (optional) |
| `--voice-name NAME` | Custom name for the cloned voice (optional) |
| `--speed FLOAT` | Speech speed [0.5, 2] (default: 1.0) |
| `--volume FLOAT` | Volume (0, 10] (default: 1.0) |
| `--format FORMAT` | Audio format: `wav` or `pcm` (default: `wav`) |
| `--watermark` | Enable AI watermark (disabled by default) |
| `--list-voices` | List available system voices |
| `--list-clone-voices` | List previously cloned voices |
| `--env-file PATH` | Path to .env file |

### Examples

```bash
# Basic TTS with default voice (tongtong)
python scripts/glm_tts.py "你好，今天天气真不错" -o output.wav

# Use a different preset voice
python scripts/glm_tts.py "你好" -o output.wav --voice xiaochen

# Voice clone from reference audio
python scripts/glm_tts.py "我是克隆的声音" -o output.wav --clone --ref-audio ref.wav

# Voice clone with reference text (improves quality)
python scripts/glm_tts.py "你好世界" -o output.wav --clone --ref-audio ref.wav --ref-text "参考音频的文字内容"

# Use a previously cloned voice ID
python scripts/glm_tts.py "你好" -o output.wav --voice voice_clone_20240315_143052_001

# Adjust speed and volume
python scripts/glm_tts.py "快一点说" -o output.wav --speed 1.5 --volume 2.0

# List available voices
python scripts/glm_tts.py --list-voices

# List cloned voices
python scripts/glm_tts.py --list-clone-voices
```

## Preset Voices

| Voice ID | Name | Description |
|---|---|---|
| `tongtong` | 彤彤 | Default voice, bright young female |
| `xiaochen` | 小陈 | Gentle warm young female |
| `chuichui` | 锤锤 | - |
| `jam` | jam | 动动动物圈 jam |
| `kazi` | kazi | 动动动物圈 kazi |
| `douji` | douji | 动动动物圈 douji |
| `luodo` | luodo | 动动动物圈 luodo |

## Voice Clone Workflow

1. **Upload** the reference audio file (mp3/wav, 3-30 seconds recommended, max 10MB) to ZhipuAI
2. **Clone** the voice via `glm-tts-clone` API, which returns a `voice_id`
3. **Generate** speech using the cloned `voice_id` via `glm-tts` API

When using `--clone`, steps 1-3 are executed automatically. The resulting `voice_id` can be reused in future calls with `--voice`.

## Long Text Handling

- GLM-TTS API has a 1024-character limit per request
- Text exceeding 1024 characters is automatically split by sentence boundaries (。！？\n)
- Each segment is synthesized separately, then WAV files are concatenated
- Temporary segment files are cleaned up automatically

## Troubleshooting

| Issue | Solution |
|---|---|
| `ZHIPU_API_KEY not set` | Create `.env` file with `ZHIPU_API_KEY=your_key` |
| Audio has beep at start | Watermark is disabled by default; if present, ensure you're using the latest script version |
| Text cut off early | Long text is auto-split; if still truncated, check for special characters |
| Clone quality poor | Use clear reference audio (3-30 sec, no background noise); provide `--ref-text` for better results |
| Reference audio too large | Max 10MB; compress or trim the audio file |
| `音色id不存在` | Voice ID not found; use `--list-voices` or `--list-clone-voices` to check available IDs |
