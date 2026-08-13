"""视频理解：使用 Qwen3-VL 分析本地视频或可直接访问的视频 URL。"""

import base64
import mimetypes
from pathlib import Path
from typing import Any

from .config import get_video_config


DEFAULT_VIDEO_MODEL = "qwen3-vl-235b-a22b-instruct"
SUPPORTED_VIDEO_SUFFIXES = {
    ".mp4",
    ".webm",
    ".mov",
    ".mkv",
    ".avi",
    ".m4v",
}


class VideoUnderstandingError(RuntimeError):
    """视频理解请求失败。"""


def _is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _validate_video_path(video_path: str) -> Path:
    path = Path(video_path)
    if not path.is_file():
        raise VideoUnderstandingError(f"视频文件不存在: {video_path}")
    if path.suffix.lower() not in SUPPORTED_VIDEO_SUFFIXES:
        suffixes = "/".join(sorted(SUPPORTED_VIDEO_SUFFIXES))
        raise VideoUnderstandingError(
            f"不支持的视频格式: {path.suffix}（支持 {suffixes}）"
        )
    return path


def encode_video(video_path: str) -> str:
    """将本地视频编码为 Qwen3-VL 可接受的 data URI。"""
    path = _validate_video_path(video_path)
    mime_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_text(response: Any) -> str:
    """兼容 OpenAI 兼容接口返回的字符串或分段 content。"""
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError) as error:
        raise VideoUnderstandingError("模型返回格式异常，未找到文本结果") from error

    if isinstance(content, str):
        return content.strip()

    parts = []
    for item in content or []:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and item.get("text"):
            parts.append(str(item["text"]))
    return "\n".join(parts).strip()


def _error_message(error: Exception, api_key: str) -> str:
    """格式化异常，同时避免把 API key 写入终端或日志。"""
    message = str(error)
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    return f"{type(error).__name__}: {message}"


def understand_video(
    video: str,
    prompt: str = "请详细分析这个视频的内容、镜头运动、构图、主体动作和时间线。",
    model: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """调用 Qwen3-VL 理解视频并返回模型文本。

    ``video`` 可以是本地视频路径，也可以是模型服务能够直接访问的 HTTP(S)
    视频 URL。X/Bilibili 帖子页面 URL 不是直接视频 URL，需先下载视频。
    """
    from openai import OpenAI

    api_key, base_url, configured_model = get_video_config()
    selected_model = model or configured_model or DEFAULT_VIDEO_MODEL

    if _is_url(video):
        video_url = video
    else:
        video_url = encode_video(video)

    try:
        client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
        response = client.chat.completions.create(
            model=selected_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "video_url", "video_url": {"url": video_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as error:
        raise VideoUnderstandingError(
            f"Qwen3-VL 请求失败（{_error_message(error, api_key)}）"
        ) from error

    result = _extract_text(response)
    if not result:
        raise VideoUnderstandingError("模型未返回文本结果")
    return result
