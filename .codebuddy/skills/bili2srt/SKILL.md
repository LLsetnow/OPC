---
name: bili2srt
description: >
  This skill should be used when the user wants to download a Bilibili video's audio,
  extract subtitles via ASR (speech-to-text), and generate a structured Markdown summary
  with clickable timestamps that jump to the corresponding video position.
  It handles the full pipeline: audio download -> ASR transcription -> SRT subtitle generation -> LLM summarization.
  Trigger phrases include "download bilibili video", "extract bilibili subtitles", "summarize bilibili video",
  "B站视频转文字", "B站视频总结", "下载B站音频", "提取字幕", "视频转写".
---

# Bilibili Video to SRT & Summary (bili2srt)

## Purpose

Automate the end-to-end pipeline of extracting content from Bilibili videos:

1. **Download audio** from a Bilibili video URL using yt-dlp
2. **Transcribe speech** using GLM-ASR (ZhipuAI) with automatic audio chunking for long videos
3. **Generate SRT subtitle file** with timestamps
4. **Produce a Markdown summary** with structured sections (overview, key points, detailed content, conclusion) and clickable timestamps linking back to the video

## When to Use

- When the user provides a Bilibili video URL and wants a text summary or subtitles
- When the user wants to convert a Bilibili video's speech content to text
- When the user says things like "summarize this Bilibili video", "extract subtitles from this video", "transcribe this B站 video"
- When the user has an existing audio file and wants to run ASR + summarization on it

## Prerequisites

### Environment Variables (`.env` file)

| Variable | Required | Default | Description |
|---|---|---|---|
| `ZHIPU_API_KEY` | Yes | - | ZhipuAI API key (obtain at https://open.bigmodel.cn/) |
| `ZHIPU_BASE_URL` | No | `https://open.bigmodel.cn/api/paas/v4` | ZhipuAI API base URL |
| `ASR_MODEL` | No | `glm-asr-2512` | ASR model name |
| `LLM_API_KEY` | No | Falls back to `ZHIPU_API_KEY` | Separate API key for LLM summarization |
| `LLM_BASE_URL` | No | Falls back to `ZHIPU_BASE_URL` | Separate base URL for LLM |
| `LLM_MODEL` | No | `glm-4-flash` | LLM model for summarization |
| `YT_DLP_COOKIES` | No | - | Path to yt-dlp cookies file (for login-required videos) |

### System Dependencies

- **ffmpeg** (recommended): For audio format conversion and extraction. Without it, audio will be downloaded in original format.
- **Python packages**: `zhipuai`, `openai`, `yt-dlp`, `soundfile`, `numpy` (see `scripts/requirements.txt`)

## Workflow

### Step 1: Prepare Environment

1. Ensure the `.env` file exists in the project root with at least `ZHIPU_API_KEY` set
2. Install Python dependencies:

```bash
pip install -r scripts/requirements.txt
```

3. (Recommended) Install ffmpeg for best audio quality

### Step 2: Run the Pipeline

Execute the `bili2srt.py` script with the Bilibili video URL:

```bash
python scripts/bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD"
```

**Common options:**

| Option | Description |
|---|---|
| `-o DIR` | Output directory (default: `./output`) |
| `--cookies FILE` | yt-dlp cookies file path |
| `--audio-only` | Only download audio, skip ASR |
| `--skip-download` | Skip download, use existing audio file |
| `--audio-file PATH` | Specify existing audio file (with `--skip-download`) |
| `--skip-asr` | Skip ASR, generate summary from existing subtitle file (`.asr.json` or `.srt`) |
| `--asr-file PATH` | Specify existing ASR JSON or SRT file (with `--skip-asr`) |
| `--env-file PATH` | Path to .env file (default: `.env`) |

**Examples:**

```bash
# Basic usage
python scripts/bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD"

# Custom output directory
python scripts/bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD" -o ./my_output

# With cookies for login-required videos
python scripts/bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD" --cookies cookies.txt

# Process existing audio file (skip download)
python scripts/bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD" --skip-download --audio-file ./output/video.m4a

# Skip both download and ASR, regenerate summary from existing subtitles
python scripts/bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD" --skip-download --skip-asr

# Skip ASR with specific subtitle file
python scripts/bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD" --skip-download --skip-asr --asr-file ./output/video.asr.json
python scripts/bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD" --skip-download --skip-asr --asr-file ./output/video.srt
```

### Step 3: Review Output

The script generates the following files in the output directory:

| File | Description |
|---|---|
| `{title}.m4a` (or `.mp3`, `.webm`) | Downloaded audio file |
| `{title}.srt` | SRT subtitle file with timestamps |
| `{title}.md` | Markdown summary with clickable video timestamps |
| `{title}.asr.json` | Raw ASR result in JSON format |

### Markdown Output Format

The generated Markdown file has the following structure:

```markdown
# Video Title
> 🎬 视频链接: [https://www.bilibili.com/video/BVxxxx](https://www.bilibili.com/video/BVxxxx)

## 概述
1-2 paragraph summary of the video's core content.

## 要点
- **Key point 1**: Description [00:01:26](https://www.bilibili.com/video/BVxxxx?t=86)
- **Key point 2**: Description [00:02:36](https://www.bilibili.com/video/BVxxxx?t=156)

## 详细内容
### Section Title [00:00:00 - 00:01:04]
Detailed summary of this section.

## 结论
Final conclusion or core viewpoint.
```

Key features of the Markdown output:
- **Video link** at the top for quick access to the original video
- **Clickable timestamps** in the key points section — clicking `[00:01:26](...?t=86)` opens the video at that exact position on Bilibili
- **Time ranges** in the detailed content section for reference

## Pipeline Details

### Audio Download
- Uses `yt-dlp` to extract the best audio stream from Bilibili
- If `ffmpeg` is available, extracts audio and converts to M4A format
- Falls back to downloading the raw audio stream without conversion if `ffmpeg` is unavailable
- Cookie file support for login-required or member-only videos

### ASR Transcription
- Uses ZhipuAI's `glm-asr-2512` model via the `zhipuai` Python SDK
- Audio is automatically converted to MP3/WAV format (ASR only accepts these formats)
- Long audio (>25 seconds) is automatically split into chunks and processed sequentially
- Each chunk's text is further split by sentences with estimated timestamps
- Results are merged into a unified timeline

### LLM Summarization
- Uses an OpenAI-compatible API (default: ZhipuAI's `glm-4-flash`) to generate the summary
- The transcript with timestamps is fed to the LLM with instructions to produce structured output
- After generation, timestamps in `[MM:SS]` or `[HH:MM:SS]` format are automatically converted to clickable Bilibili links with `?t=seconds` parameter
- The video URL is inserted as a clickable link at the top of the document

## Troubleshooting

| Issue | Solution |
|---|---|
| `ZHIPU_API_KEY not set` | Create `.env` file with `ZHIPU_API_KEY=your_key` |
| Audio download fails | Try providing cookies via `--cookies` or set `YT_DLP_COOKIES` in `.env` |
| ASR quality poor | Ensure audio is clear speech; background music may affect accuracy |
| Timestamps inaccurate | Timestamps are estimated based on text length distribution; long segments may have offset drift |
| ffmpeg not found | Install ffmpeg or accept lower audio quality without format conversion |
| `soundfile` import error | Run `pip install soundfile numpy` |
