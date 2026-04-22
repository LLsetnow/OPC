"""图片理解：使用视觉模型分析图片内容"""

import base64
import io
import os
import sys
from pathlib import Path

from .config import get_vision_config


# ── 图片编码 ──────────────────────────────────────────────────────

def compress_image(image_path: str, max_size_mb: float = 10.0) -> str:
    """
    压缩图片使其不超过指定大小。
    返回 base64 编码字符串。优先 WebP，再缩放 + JPEG。
    """
    from PIL import Image

    max_bytes = int(max_size_mb * 1024 * 1024)
    img = Image.open(image_path)

    if img.mode in ("P", "PA"):
        img = img.convert("RGBA")
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    # 尝试 WebP 压缩
    for quality in [85, 75, 65, 55, 45, 35, 25]:
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=quality)
        if buf.tell() <= max_bytes:
            return base64.b64encode(buf.getvalue()).decode("utf-8")

    # 缩放 + JPEG
    scale = 0.9
    while scale >= 0.1:
        w, h = img.size
        resized = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        for quality in [85, 70, 55, 40, 25]:
            buf = io.BytesIO()
            save_img = resized.convert("RGB") if resized.mode == "RGBA" else resized
            save_img.save(buf, format="JPEG", quality=quality)
            if buf.tell() <= max_bytes:
                return base64.b64encode(buf.getvalue()).decode("utf-8")
        scale -= 0.1

    # 兜底
    tiny = img.resize((256, int(256 * img.size[1] / img.size[0])), Image.LANCZOS)
    buf = io.BytesIO()
    tiny.convert("RGB").save(buf, format="JPEG", quality=30)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def encode_image(image_path: str, max_size_mb: float = 10.0) -> str:
    """将本地图片编码为 base64 字符串，超限时自动压缩"""
    file_size = os.path.getsize(image_path)
    if file_size <= max_size_mb * 1024 * 1024:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    print(f"图片过大 ({file_size / 1024 / 1024:.1f}MB > {max_size_mb:.0f}MB)，正在自动压缩...")
    return compress_image(image_path, max_size_mb)


def _is_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")


# ── 图片理解 ──────────────────────────────────────────────────────

def understand_image(
    image: str,
    prompt: str = "请详细描述这张图片的内容",
    model: str = "glm-5v-turbo",
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """
    调用视觉模型理解图片内容。

    Args:
        image: 本地图片路径或网络 URL
        prompt: 提问内容
        model: 视觉模型名称
        max_tokens: 最大输出 token 数
        temperature: 生成温度

    Returns:
        模型返回的文本
    """
    from openai import OpenAI

    api_key, base_url = get_vision_config()

    # 构建 image_url
    if _is_url(image):
        image_url = image
    else:
        if not os.path.exists(image):
            print(f"错误: 图片文件不存在: {image}")
            sys.exit(1)
        file_size = os.path.getsize(image)
        print(f"编码图片: {image} ({file_size / 1024:.1f} KB)")
        image_url = encode_image(image)

    # 智谱官方 base_url 已包含 /v4，直接使用
    client_base_url = base_url.rstrip("/")
    if not client_base_url.endswith(("/v4", "/v1")):
        client_base_url += "/v1"

    client = OpenAI(api_key=api_key, base_url=client_base_url)

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    print(f"调用模型: {model}")
    print(f"提问: {prompt}")

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    return response.choices[0].message.content
