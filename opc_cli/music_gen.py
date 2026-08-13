"""阿里云 Fun-Music 和 MiniMax Music 音乐生成。"""

from pathlib import Path
from typing import Optional

import requests


MUSIC_GENERATION_PATH = "/services/audio/music/generation"
SUPPORTED_MODELS = {"fun-music-v1", "fun-music-preview"}
MINIMAX_SUPPORTED_MODELS = {"music-3.0", "music-3.0-free"}
SUPPORTED_FORMATS = {"mp3", "wav"}
SUPPORTED_GENDERS = {"female", "male"}
SUPPORTED_PROVIDERS = {"aliyun", "minimax"}


def generate_music(
    *,
    prompt: Optional[str] = None,
    lyrics: Optional[str] = None,
    is_instrumental: bool = False,
    gender: str = "female",
    api_key: str,
    base_url: str = "https://dashscope.aliyuncs.com/api/v1",
    model: str = "fun-music-v1",
    format: str = "mp3",
    provider: str = "aliyun",
    lyrics_optimizer: bool | None = None,
) -> dict:
    """调用指定音乐服务商并返回本地下载所需的音频 URL及元数据。"""
    selected_provider = provider.strip().lower()
    if selected_provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"不支持的音乐服务商: {provider}（支持 aliyun/minimax）"
        )

    format = format.lower()
    if format not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的音频格式: {format}（支持 mp3/wav）")

    if selected_provider == "minimax":
        return _generate_minimax_music(
            prompt=prompt,
            lyrics=lyrics,
            is_instrumental=is_instrumental,
            api_key=api_key,
            base_url=base_url,
            model=model,
            format=format,
            lyrics_optimizer=lyrics_optimizer,
        )

    return _generate_aliyun_music(
        prompt=prompt,
        lyrics=lyrics,
        is_instrumental=is_instrumental,
        gender=gender,
        api_key=api_key,
        base_url=base_url,
        model=model,
        format=format,
    )


def _generate_aliyun_music(
    *,
    prompt: Optional[str],
    lyrics: Optional[str],
    is_instrumental: bool,
    gender: str,
    api_key: str,
    base_url: str,
    model: str,
    format: str,
) -> dict:
    """调用阿里云 Fun-Music 非流式接口。"""
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"不支持的 Fun-Music 模型: {model}（支持 fun-music-v1/fun-music-preview）")

    gender = gender.lower()
    if gender not in SUPPORTED_GENDERS:
        raise ValueError(f"不支持的声音性别: {gender}（支持 female/male）")

    has_prompt = bool(prompt and prompt.strip())
    has_lyrics = bool(lyrics and lyrics.strip())
    if not has_prompt and not has_lyrics:
        raise ValueError("prompt 和 lyrics 至少提供一个")
    if model == "fun-music-preview" and not has_prompt:
        raise ValueError("fun-music-preview 必须提供 prompt")

    input_data = {
        "is_instrumental": is_instrumental,
        "format": format,
    }
    if has_prompt:
        input_data["prompt"] = prompt
    if has_lyrics:
        input_data["lyrics"] = lyrics
    if model == "fun-music-v1" and not is_instrumental:
        input_data["gender"] = gender

    url = f"{base_url.rstrip('/')}{MUSIC_GENERATION_PATH}"
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": model, "input": input_data},
        timeout=300,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        detail = response.text[:500]
        raise RuntimeError(f"Fun-Music API 请求失败: HTTP {response.status_code} {detail}") from error

    try:
        data = response.json()
    except ValueError as error:
        raise RuntimeError("Fun-Music API 返回了无效 JSON") from error

    if data.get("code") not in (None, "", "200", 200):
        raise RuntimeError(f"Fun-Music API 错误: {data.get('code')} {data.get('message', '')}".strip())

    audio = data.get("output", {}).get("audio", {})
    audio_url = audio.get("url")
    if not audio_url:
        raise RuntimeError("Fun-Music API 未返回音频 URL")

    extra_info = data.get("output", {}).get("extra_info", {}) or {}
    usage = data.get("usage", {}) or {}
    return {
        "audio_url": audio_url,
        "lyrics": extra_info.get("lyrics"),
        "duration": usage.get("duration"),
        "request_id": data.get("request_id"),
        "model": model,
        "format": format,
    }


def _generate_minimax_music(
    *,
    prompt: Optional[str],
    lyrics: Optional[str],
    is_instrumental: bool,
    api_key: str,
    base_url: str,
    model: str,
    format: str,
    lyrics_optimizer: bool | None,
) -> dict:
    """调用 MiniMax Music Generation API 并请求临时音频 URL。"""
    if model not in MINIMAX_SUPPORTED_MODELS:
        raise ValueError(
            f"不支持的 MiniMax 音乐模型: {model}（支持 music-3.0/music-3.0-free）"
        )

    has_prompt = bool(prompt and prompt.strip())
    has_lyrics = bool(lyrics and lyrics.strip())
    if not has_prompt and not has_lyrics:
        raise ValueError("prompt 和 lyrics 至少提供一个")
    if has_prompt and len(prompt.strip()) > 2000:
        raise ValueError("MiniMax prompt 最多 2000 个字符")
    if has_lyrics and len(lyrics.strip()) > 3500:
        raise ValueError("MiniMax lyrics 最多 3500 个字符")
    if is_instrumental and not has_prompt:
        raise ValueError("MiniMax 纯音乐模式必须提供 prompt")

    payload = {
        "model": model,
        "audio_setting": {"format": format},
        "output_format": "url",
        "is_instrumental": is_instrumental,
    }
    if has_prompt:
        payload["prompt"] = prompt
    if has_lyrics:
        payload["lyrics"] = lyrics

    # Music 3.0 支持根据 prompt 自动生成歌词；默认让 prompt-only 命令可直接生成歌曲。
    if lyrics_optimizer is None:
        lyrics_optimizer = not is_instrumental and not has_lyrics
    if lyrics_optimizer:
        payload["lyrics_optimizer"] = True

    url = _minimax_music_url(base_url)
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=300,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        detail = response.text[:500]
        raise RuntimeError(
            f"MiniMax Music API 请求失败: HTTP {response.status_code} {detail}"
        ) from error

    try:
        data = response.json()
    except ValueError as error:
        raise RuntimeError("MiniMax Music API 返回了无效 JSON") from error

    base_resp = data.get("base_resp", {}) or {}
    status_code = base_resp.get("status_code")
    if status_code not in (None, 0, "0"):
        raise RuntimeError(
            f"MiniMax Music API 错误: {status_code} {base_resp.get('status_msg', '')}".strip()
        )

    result_data = data.get("data", {}) or {}
    if result_data.get("status") not in (None, 2, "2"):
        raise RuntimeError(
            f"MiniMax Music API 生成未完成: status={result_data.get('status')}"
        )
    audio_url = result_data.get("audio")
    if not isinstance(audio_url, str) or not audio_url.startswith(("http://", "https://")):
        raise RuntimeError(
            "MiniMax Music API 未返回音频 URL（请确认 output_format=url）"
        )

    extra_info = data.get("extra_info", {}) or {}
    duration_ms = extra_info.get("music_duration")
    duration = None
    if isinstance(duration_ms, (int, float)):
        duration = duration_ms / 1000
    return {
        "audio_url": audio_url,
        "lyrics": lyrics if has_lyrics else None,
        "duration": duration,
        "request_id": data.get("trace_id"),
        "model": model,
        "format": format,
        "provider": "minimax",
    }


def _minimax_music_url(base_url: str) -> str:
    """兼容 MiniMax API 根地址和已经带 ``/v1`` 的自定义地址。"""
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/music_generation"
    return f"{normalized}/v1/music_generation"


def download_music(url: str, save_path: str) -> str:
    """下载 Fun-Music 返回的临时音频 URL。"""
    destination = Path(save_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(url, timeout=120, stream=True)
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError(f"音频下载请求失败: {error}") from error

    with destination.open("wb") as file:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                file.write(chunk)
    return str(destination)
