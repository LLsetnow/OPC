"""图片理解脚本 - 使用多模态视觉模型理解图片内容

支持本地图片路径和网络图片 URL，自动压缩超限图片。
通过 OpenAI 兼容 API 调用智谱 GLM 系列视觉模型。

用法:
    python img_understand.py <image> [-p PROMPT] [-o OUTPUT] [--model MODEL]
"""

import argparse
import base64
import io
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


# ── 环境配置 ──────────────────────────────────────────────────────

def load_env(env_file: str = None):
    """加载 .env 文件"""
    if env_file and os.path.exists(env_file):
        load_dotenv(env_file, override=False)
        return

    candidates = [".env"]
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    candidates.append(str(project_root / ".env"))

    for p in candidates:
        if os.path.exists(p):
            load_dotenv(p, override=False)
            break


def get_api_config() -> tuple:
    """
    获取 API 配置，返回 (api_key, base_url)。
    优先使用 VISION_API_KEY / VISION_BASE_URL，
    其次回退到 ZHIPU_API_KEY / ZHIPU_BASE_URL，
    最后回退到 LLM_API_KEY / LLM_BASE_URL。
    """
    api_key = os.environ.get("VISION_API_KEY", "")
    base_url = os.environ.get("VISION_BASE_URL", "")
    if api_key:
        return api_key, base_url.rstrip("/")

    api_key = os.environ.get("ZHIPU_API_KEY", "")
    base_url = os.environ.get("ZHIPU_BASE_URL", "")
    if api_key:
        return api_key, base_url.rstrip("/")

    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "")
    if not api_key:
        print("错误: 未设置视觉 API 密钥")
        print("请在 .env 文件中添加 VISION_API_KEY 或 ZHIPU_API_KEY")
        sys.exit(1)

    return api_key, base_url.rstrip("/")


# ── 图片编码 ──────────────────────────────────────────────────────

def compress_image(image_path: str, max_size_mb: float = 10.0) -> str:
    """
    压缩图片使其不超过指定大小。
    返回 base64 编码字符串（无 data URI 前缀）。
    优先尝试转 webp，再逐步降低 JPEG 质量。
    """
    from PIL import Image

    max_bytes = int(max_size_mb * 1024 * 1024)
    img = Image.open(image_path)

    if img.mode in ("P", "PA"):
        img = img.convert("RGBA")
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    # 尝试 WebP 压缩（通常压缩率更好）
    for quality in [85, 75, 65, 55, 45, 35, 25]:
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=quality)
        if buf.tell() <= max_bytes:
            return base64.b64encode(buf.getvalue()).decode("utf-8")

    # WebP 仍太大，尝试缩放 + JPEG
    scale = 0.9
    while scale >= 0.1:
        w, h = img.size
        new_size = (int(w * scale), int(h * scale))
        resized = img.resize(new_size, Image.LANCZOS)
        for quality in [85, 70, 55, 40, 25]:
            buf = io.BytesIO()
            save_img = resized.convert("RGB") if resized.mode == "RGBA" else resized
            save_img.save(buf, format="JPEG", quality=quality)
            if buf.tell() <= max_bytes:
                return base64.b64encode(buf.getvalue()).decode("utf-8")
        scale -= 0.1

    # 最终兜底：缩到很小
    tiny = img.resize((256, int(256 * img.size[1] / img.size[0])), Image.LANCZOS)
    buf = io.BytesIO()
    tiny.convert("RGB").save(buf, format="JPEG", quality=30)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def encode_image(image_path: str, auto_compress: bool = True, max_size_mb: float = 10.0) -> str:
    """将本地图片编码为 base64 字符串（无 data URI 前缀），超限时自动压缩"""
    file_size = os.path.getsize(image_path)

    if not auto_compress or file_size <= max_size_mb * 1024 * 1024:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    print(f"图片过大 ({file_size / 1024 / 1024:.1f}MB > {max_size_mb:.0f}MB)，正在自动压缩...")
    return compress_image(image_path, max_size_mb)


def is_url(text: str) -> bool:
    """判断是否为 URL"""
    return text.startswith("http://") or text.startswith("https://")


# ── 图片理解 ──────────────────────────────────────────────────────

def understand_image(
    api_key: str,
    base_url: str,
    image: str,
    prompt: str = "请详细描述这张图片的内容",
    model: str = "glm-5v-turbo",
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """
    调用视觉模型理解图片内容。

    Args:
        api_key: API 密钥
        base_url: API 基础地址
        image: 本地图片路径或网络 URL
        prompt: 提问内容
        model: 模型名称
        max_tokens: 最大输出 token 数
        temperature: 生成温度

    Returns:
        模型返回的文本内容
    """
    from openai import OpenAI

    # 构建 image_url
    if is_url(image):
        image_url = image
    else:
        if not os.path.exists(image):
            print(f"错误: 图片文件不存在: {image}")
            sys.exit(1)
        file_size = os.path.getsize(image)
        print(f"编码图片: {image} ({file_size / 1024:.1f} KB)")
        image_url = encode_image(image)

    # 构建 base_url：智谱官方含 /v4，第三方代理可能需要 /v1
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

    result = response.choices[0].message.content
    return result


# ── CLI 入口 ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="图片理解 - 使用视觉模型理解图片内容",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 描述图片
  python img_understand.py photo.jpg

  # 自定义提问
  python img_understand.py photo.jpg -p "这张图片里有什么有趣的东西？"

  # 使用网络图片 URL
  python img_understand.py "https://example.com/photo.jpg" -p "描述这张图片"

  # 输出到文件
  python img_understand.py photo.jpg -p "详细描述" -o result.txt

  # 使用其他模型
  python img_understand.py photo.jpg --model glm-4v-plus
        """,
    )

    parser.add_argument("image", help="图片路径或 URL")
    parser.add_argument("-p", "--prompt", default="请详细描述这张图片的内容", help="提问内容（默认: 描述图片内容）")
    parser.add_argument("-o", "--output", help="输出到文件（默认打印到终端）")
    parser.add_argument("--model", default="glm-5v-turbo", help="模型名称（默认: glm-5v-turbo）")
    parser.add_argument("--max-tokens", type=int, default=1024, help="最大输出 token 数（默认: 1024）")
    parser.add_argument("--temperature", type=float, default=0.7, help="生成温度 0-1（默认: 0.7）")
    parser.add_argument("--env-file", help="自定义 .env 文件路径")

    args = parser.parse_args()

    # 加载环境变量
    load_env(args.env_file)
    api_key, base_url = get_api_config()

    # 调用模型
    result = understand_image(
        api_key, base_url,
        image=args.image,
        prompt=args.prompt,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    # 输出结果
    if args.output:
        output_dir = os.path.dirname(args.output)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"\n结果已保存: {args.output}")
    else:
        print("\n" + "=" * 50)
        print(result)
        print("=" * 50)


if __name__ == "__main__":
    main()
