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


def _validate_audio_path(audio_path: str) -> Path:
    """校验并返回音频路径。"""
    path = Path(audio_path)
    if not path.is_file():
        raise AudioUnderstandingError(f"音频文件不存在: {audio_path}")
    if path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
        suffixes = "/".join(sorted(SUPPORTED_AUDIO_SUFFIXES))
        raise AudioUnderstandingError(f"不支持的音频格式: {path.suffix}（支持 {suffixes}）")
    return path


def detect_beats(audio_path: str) -> dict[str, Any]:
    """使用 librosa 检测 BPM、节拍时刻和起音时刻。"""
    path = _validate_audio_path(audio_path)

    try:
        import librosa
    except ImportError as error:
        raise AudioUnderstandingError(
            "使用 `opc audio librosa` 需要安装 librosa，请执行: pip install librosa"
        ) from error

    try:
        y, sample_rate = librosa.load(str(path), sr=None, mono=True)
        hop_length = 512
        tempo, beat_frames = librosa.beat.beat_track(
            y=y, sr=sample_rate, units="frames", hop_length=hop_length
        )
        onset_frames = librosa.onset.onset_detect(
            y=y,
            sr=sample_rate,
            units="frames",
            backtrack=False,
            hop_length=hop_length,
        )
        onset_envelope = librosa.onset.onset_strength(
            y=y, sr=sample_rate, hop_length=hop_length
        )
        beat_times = librosa.frames_to_time(
            beat_frames, sr=sample_rate, hop_length=hop_length
        )
        onset_times = librosa.frames_to_time(
            onset_frames, sr=sample_rate, hop_length=hop_length
        )
    except Exception as error:
        raise AudioUnderstandingError(
            f"librosa 鼓点检测失败（{type(error).__name__}）: {error}"
        ) from error

    # librosa 0.10 返回 float，较新版本可能返回只有一个元素的 ndarray。
    try:
        tempo_bpm = float(tempo[0])
    except (IndexError, TypeError):
        tempo_bpm = float(tempo)

    envelope = [float(value) for value in onset_envelope]
    envelope_peak = max(envelope, default=0.0)
    if envelope_peak <= 0:
        beat_strengths = [0.0 for _ in beat_frames]
    else:
        beat_strengths = [
            max(0.0, min(1.0, envelope[min(int(frame), len(envelope) - 1)] / envelope_peak))
            for frame in beat_frames
        ]

    return {
        "tempo_bpm": tempo_bpm,
        "beat_times": [float(value) for value in beat_times],
        "beat_strengths": beat_strengths,
        "onset_times": [float(value) for value in onset_times],
        "onset_strengths": [
            max(0.0, min(1.0, envelope[min(int(frame), len(envelope) - 1)] / envelope_peak))
            if envelope_peak > 0
            else 0.0
            for frame in onset_frames
        ],
    }


def filter_beat_events(
    analysis: dict[str, Any],
    strength_threshold: float = 0.2,
    min_interval: float = 1.0,
) -> dict[str, Any]:
    """按相对强度和时间窗口筛选节拍/起音事件。

    每个时间窗口只保留强度最高的一个事件，因此合并后的事件频率
    不会高于约 ``1 / min_interval`` 次/秒。
    """
    if not 0 <= strength_threshold <= 1:
        raise AudioUnderstandingError("beat_strength 阈值必须在 0 到 1 之间")
    if min_interval <= 0:
        raise AudioUnderstandingError("beat 最小间隔必须大于 0 秒")

    candidates = []
    for kind, times_key, strengths_key in (
        ("beat", "beat_times", "beat_strengths"),
        ("onset", "onset_times", "onset_strengths"),
    ):
        for time, strength in zip(analysis[times_key], analysis[strengths_key]):
            if strength >= strength_threshold:
                candidates.append(
                    {"time": float(time), "strength": float(strength), "kind": kind}
                )

    # 将时间划分为固定窗口，每个窗口只保留最强事件。
    selected_by_window = {}
    for event in candidates:
        window = int(event["time"] // min_interval)
        previous = selected_by_window.get(window)
        if previous is None or event["strength"] > previous["strength"]:
            selected_by_window[window] = event

    selected = sorted(selected_by_window.values(), key=lambda event: event["time"])
    filtered = {
        "strength_threshold": strength_threshold,
        "min_interval": min_interval,
        "events": selected,
        "beat_times": [event["time"] for event in selected if event["kind"] == "beat"],
        "beat_strengths": [
            event["strength"] for event in selected if event["kind"] == "beat"
        ],
        "onset_times": [event["time"] for event in selected if event["kind"] == "onset"],
        "onset_strengths": [
            event["strength"] for event in selected if event["kind"] == "onset"
        ],
    }
    return filtered


def format_librosa_analysis(analysis: dict[str, Any], values_per_line: int = 12) -> str:
    """将 librosa 检测结果格式化为可读文本。"""
    filtered = analysis.get("filtered") or {
        "strength_threshold": 0.0,
        "min_interval": 0.0,
        "events": [
            {
                "time": time,
                "strength": strength,
                "kind": "beat",
            }
            for time, strength in zip(analysis["beat_times"], analysis["beat_strengths"])
        ],
        "beat_times": analysis["beat_times"],
        "beat_strengths": analysis["beat_strengths"],
        "onset_times": analysis["onset_times"],
        "onset_strengths": analysis.get("onset_strengths", []),
    }
    lines = [
        "## Librosa 鼓点检测",
        f"估计 BPM: {analysis['tempo_bpm']:.2f}",
        f"原始节拍数量: {len(analysis['beat_times'])}",
        f"原始起音数量: {len(analysis['onset_times'])}",
        f"筛选阈值: {filtered['strength_threshold']:.2f}",
        f"最小间隔: {filtered['min_interval']:.2f}s",
        f"筛选后事件总数: {len(filtered['events'])}",
    ]

    for label, key in (
        ("筛选后节拍时刻（beat_times，单位：秒）", "beat_times"),
        ("筛选后起音/打击候选时刻（onset_times，单位：秒）", "onset_times"),
    ):
        values = filtered[key]
        lines.append(f"{label}:")
        if not values:
            lines.append("（无）")
            continue
        formatted = [f"{value:.3f}" for value in values]
        for start in range(0, len(formatted), values_per_line):
            lines.append(", ".join(formatted[start : start + values_per_line]))

    beat_pairs = [
        f"{time:.3f}s:{strength:.2f}"
        for time, strength in zip(filtered["beat_times"], filtered["beat_strengths"])
    ]
    onset_pairs = [
        f"{time:.3f}s:{strength:.2f}"
        for time, strength in zip(filtered["onset_times"], filtered["onset_strengths"])
    ]
    lines.append("筛选后节拍时刻与相对强度（beat_times:beat_strengths，0-1）:")
    for start in range(0, len(beat_pairs), values_per_line):
        lines.append(", ".join(beat_pairs[start : start + values_per_line]))
    lines.append("筛选后起音时刻与相对强度（onset_times:onset_strengths，0-1）:")
    for start in range(0, len(onset_pairs), values_per_line):
        lines.append(", ".join(onset_pairs[start : start + values_per_line]))

    return "\n".join(lines)


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
    path = _validate_audio_path(audio_path)

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
