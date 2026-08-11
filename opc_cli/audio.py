"""音乐理解：使用 Qwen3-Omni Captioner 分析音频内容。"""

import base64
from pathlib import Path
from typing import Any

import dashscope

from .config import get_audio_config


DEFAULT_AUDIO_MODEL = "qwen3-omni-30b-a3b-captioner"
SUPPORTED_AUDIO_SUFFIXES = {
    ".wav",
    ".mp3",
    ".m4a",
    ".mp4",
    ".webm",
    ".ogg",
    ".opus",
    ".mov",
    ".mkv",
}


class AudioUnderstandingError(RuntimeError):
    """音乐理解请求失败。"""


def _extract_text(response: Any) -> str:
    """从 DashScope SDK 响应中提取模型文本。"""
    try:
        content = response.output.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError):
        if not isinstance(response, dict):
            content = []
        else:
            choices = response.get("output", {}).get("choices", [])
            message = choices[0].get("message", {}) if choices else {}
            content = message.get("content", [])

    if isinstance(content, str):
        return content.strip()

    parts = []
    for item in content or []:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and item.get("text"):
            parts.append(item["text"])
    return "\n".join(parts).strip()


def _check_response(response: Any) -> None:
    """把 SDK 的错误响应转换成不泄露密钥的 CLI 异常。"""
    status_code = getattr(response, "status_code", None)
    if status_code not in (None, 200):
        message = getattr(response, "message", "请求失败")
        raise AudioUnderstandingError(f"DashScope 请求失败（HTTP {status_code}）: {message}")

    if isinstance(response, dict) and response.get("code"):
        raise AudioUnderstandingError(
            f"DashScope 请求失败（{response['code']}）: {response.get('message', '请求失败')}"
        )


def analyze_audio(audio_path: str, model: str = "") -> str:
    """调用 Qwen3-Omni Captioner 分析本地音频并返回文本。

    Captioner 的本地文件调用使用 data URI 音频输入，不附加文本消息；
    该模型会自动生成包含声音、音乐风格、乐器和氛围等内容的描述。
    """
    path = Path(audio_path)
    if not path.is_file():
        raise AudioUnderstandingError(f"音频文件不存在: {audio_path}")
    if path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
        suffixes = "/".join(sorted(SUPPORTED_AUDIO_SUFFIXES))
        raise AudioUnderstandingError(f"不支持的音频格式: {path.suffix}（支持 {suffixes}）")

    api_key, configured_model = get_audio_config()
    selected_model = model or configured_model or DEFAULT_AUDIO_MODEL

    with path.open("rb") as audio_file:
        encoded_audio = base64.b64encode(audio_file.read()).decode("ascii")

    # Captioner 官方本地文件格式为 data:;base64,<内容>，且不附加文本 prompt。
    dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"
    try:
        response = dashscope.MultiModalConversation.call(
            api_key=api_key,
            model=selected_model,
            messages=[
                {
                    "role": "user",
                    "content": [{"audio": f"data:;base64,{encoded_audio}"}],
                }
            ],
        )
    except Exception as error:
        message = str(error).replace(api_key, "[REDACTED]")
        raise AudioUnderstandingError(
            f"DashScope 请求失败（{type(error).__name__}）: {message}"
        ) from error
    _check_response(response)

    text = _extract_text(response)
    if not text:
        raise AudioUnderstandingError("模型未返回文本结果")
    return text
