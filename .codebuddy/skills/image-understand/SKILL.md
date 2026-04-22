---
name: image-understand
description: This skill should be used when the user wants to understand, describe, or analyze image content. It supports local image files and image URLs, automatically compresses oversized images, and uses multimodal vision models (e.g., GLM-5V-Turbo) via OpenAI-compatible APIs. Trigger examples include understanding images, describing image content, analyzing photos, and asking what is in an image.
---

# Image Understanding Skill

Use visual models (GLM-5V-Turbo, etc.) to understand, describe, and analyze image content. Supports local files and URLs with automatic compression for oversized images.

## When to Use

- User asks to understand, describe, or analyze an image
- User provides an image file path and wants a text description
- User wants to ask questions about image content
- User needs OCR or visual content extraction from images

## Workflow

### Step 1: Identify Image Source

Determine whether the user provides:
- A **local file path** (e.g., `images/photo.jpg`, `/path/to/image.png`)
- A **URL** (e.g., `https://example.com/photo.jpg`)

If no image is specified, ask the user to provide one.

### Step 2: Determine the Prompt

If the user specifies a question or analysis goal, use that as the prompt. Otherwise, default to "请详细描述这张图片的内容" (describe the image content in detail).

Common prompt patterns:
- Description: "请详细描述这张图片的内容"
- OCR: "请识别图片中的所有文字"
- Analysis: "分析这张图片的构图和色彩"
- Question: "图片中的XXX是什么？"

### Step 3: Execute the Script

Run the image understanding script:

```bash
python {skill_dir}/scripts/img_understand.py {image} [-p PROMPT] [-o OUTPUT] [--model MODEL] [--max-tokens N] [--temperature T]
```

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `image` | (required) | Image file path or URL |
| `-p, --prompt` | 请详细描述这张图片的内容 | Question/prompt for the model |
| `-o, --output` | (none, print to terminal) | Output file path |
| `--model` | glm-5v-turbo | Vision model name |
| `--max-tokens` | 1024 | Max output tokens |
| `--temperature` | 0.7 | Generation temperature (0-1) |
| `--env-file` | (auto-detect .env) | Custom .env file path |

**Examples:**

```bash
# Describe an image
python {skill_dir}/scripts/img_understand.py photo.jpg

# Ask a specific question
python {skill_dir}/scripts/img_understand.py photo.jpg -p "图片中有几个人？"

# Analyze a URL image and save result
python {skill_dir}/scripts/img_understand.py "https://example.com/photo.jpg" -p "分析构图" -o analysis.txt

# Use a different model
python {skill_dir}/scripts/img_understand.py photo.jpg --model glm-4v-plus
```

### Step 4: Present Results

Present the model's response to the user. If the output was saved to a file, inform the user of the file path.

## API Configuration

The script reads API credentials from environment variables, loaded from the project's `.env` file. Priority order:

1. **`VISION_API_KEY`** / **`VISION_BASE_URL`** — Dedicated vision API (highest priority)
2. **`ZHIPU_API_KEY`** / **`ZHIPU_BASE_URL`** — ZhipuAI official API (recommended for vision models)
3. **`LLM_API_KEY`** / **`LLM_BASE_URL`** — General LLM API (fallback)

If the user's default LLM API proxy does not support vision models, configure `VISION_API_KEY` with ZhipuAI's official API key from https://open.bigmodel.cn/.

**Supported vision models:**
| Model | Provider | Notes |
|-------|----------|-------|
| `glm-5v-turbo` | ZhipuAI Official | Recommended, 200K context |
| `glm-4v-plus` | ZhipuAI Official | Previous generation |
| `glm-4v-flash` | ZhipuAI Official | Fast, cost-effective |

**Note:** Third-party API proxies may use different model names (e.g., `glm-5-turbo` instead of `glm-5v-turbo`). Use `--model` to specify the correct name for the proxy.

## Image Processing

- Images over 10MB are **automatically compressed** (WebP → JPEG with quality reduction → downscaling)
- Local images are encoded as base64 for API transmission
- URL images are passed directly to the API
- Supported formats: JPG, PNG, GIF, WebP, BMP

## Dependencies

- `openai` — OpenAI-compatible API client
- `python-dotenv` — Environment variable loading
- `Pillow` — Image compression
