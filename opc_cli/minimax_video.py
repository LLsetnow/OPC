"""MiniMax H3 视频生成客户端（当前 v2 异步接口）。"""

import time
from pathlib import Path
from typing import Callable, Iterable, Optional

import requests


VIDEO_GENERATION_PATH = "/v2/video_generation"
VIDEO_QUERY_PATH = "/v2/query/video_generation"
SUPPORTED_RESOLUTIONS = {"768P", "2K"}
SUPPORTED_RATIOS = {
    "adaptive",
    "1:1",
    "16:9",
    "4:3",
    "3:2",
    "2:3",
    "3:4",
    "9:16",
    "21:9",
}
MAX_PROMPT_LENGTH = 7000
MAX_CONTENT_ITEMS = 12
MAX_IMAGES = 9
MAX_VIDEOS = 3
MAX_AUDIOS = 3


class MiniMaxVideoError(RuntimeError):
    """MiniMax H3 视频生成请求失败。"""


def _is_http_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _validate_reference(value: str, label: str) -> str:
    """校验素材引用，避免把本机路径误发给远端 API。"""
    value = value.strip()
    if not value:
        raise MiniMaxVideoError(f"{label} 不能为空")
    if _is_http_url(value) or value.startswith("data:"):
        return value
    path = Path(value)
    if path.exists():
        raise MiniMaxVideoError(
            f"{label} 是本地文件；MiniMax H3 v2 素材参数需要公网 HTTP(S) URL 或 data URI: {value}"
        )
    raise MiniMaxVideoError(
        f"{label} 必须是公网 HTTP(S) URL 或 data URI: {value}"
    )


def _append_references(
    content: list[dict],
    values: Iterable[str],
    *,
    item_type: str,
    role: str,
    field_name: str,
) -> None:
    for value in values:
        url = _validate_reference(value, field_name)
        content.append({
            "type": item_type,
            item_type: {"url": url},
            "role": role,
        })


def build_video_payload(
    *,
    prompt: str,
    duration: int,
    resolution: str,
    ratio: str,
    first_frame: Optional[str] = None,
    last_frame: Optional[str] = None,
    reference_images: Optional[Iterable[str]] = None,
    reference_videos: Optional[Iterable[str]] = None,
    reference_audios: Optional[Iterable[str]] = None,
) -> dict:
    """构造 MiniMax H3 v2 ``/video_generation`` 请求体。"""
    prompt = prompt.strip()
    if not prompt:
        raise MiniMaxVideoError("提示词不能为空")
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise MiniMaxVideoError(
            f"提示词过长：当前 {len(prompt)} 字符，MiniMax H3 上限为 {MAX_PROMPT_LENGTH} 字符"
        )
    if not 4 <= duration <= 15:
        raise MiniMaxVideoError("duration 必须是 4 到 15 秒之间的整数")

    resolution = resolution.strip().upper()
    if resolution not in SUPPORTED_RESOLUTIONS:
        raise MiniMaxVideoError(
            f"不支持的分辨率: {resolution}（支持 768P/2K）"
        )

    ratio = ratio.strip()
    if ratio not in SUPPORTED_RATIOS:
        supported = "/".join(sorted(SUPPORTED_RATIOS))
        raise MiniMaxVideoError(f"不支持的画面比例: {ratio}（支持 {supported}）")

    content: list[dict] = [{"type": "text", "text": prompt}]
    if first_frame:
        content.append({
            "type": "image_url",
            "image_url": {"url": _validate_reference(first_frame, "--first-frame")},
            "role": "first_frame",
        })
    if last_frame:
        content.append({
            "type": "image_url",
            "image_url": {"url": _validate_reference(last_frame, "--last-frame")},
            "role": "last_frame",
        })

    _append_references(
        content,
        reference_images or [],
        item_type="image_url",
        role="reference_image",
        field_name="--reference-image",
    )
    _append_references(
        content,
        reference_videos or [],
        item_type="video_url",
        role="reference_video",
        field_name="--reference-video",
    )
    _append_references(
        content,
        reference_audios or [],
        item_type="audio_url",
        role="reference_audio",
        field_name="--reference-audio",
    )

    image_count = sum(item["type"] == "image_url" for item in content)
    video_count = sum(item["type"] == "video_url" for item in content)
    audio_count = sum(item["type"] == "audio_url" for item in content)
    if len(content) > MAX_CONTENT_ITEMS:
        raise MiniMaxVideoError(f"参考素材总数不能超过 {MAX_CONTENT_ITEMS} 个")
    if image_count > MAX_IMAGES:
        raise MiniMaxVideoError(f"图片素材不能超过 {MAX_IMAGES} 个")
    if video_count > MAX_VIDEOS:
        raise MiniMaxVideoError(f"视频素材不能超过 {MAX_VIDEOS} 个")
    if audio_count > MAX_AUDIOS:
        raise MiniMaxVideoError(f"音频素材不能超过 {MAX_AUDIOS} 个")

    has_media = len(content) > 1
    if not has_media and ratio == "adaptive":
        raise MiniMaxVideoError("文生视频不能使用 --ratio adaptive，请指定如 16:9")

    payload = {
        "content": content,
        "duration": duration,
        "resolution": resolution,
    }
    # H3 图生/参考素材模式的画面比例由输入素材决定，官方请求示例不发送 ratio。
    if not has_media:
        payload["ratio"] = ratio
    return payload


def _response_json(response: requests.Response, action: str) -> dict:
    try:
        response.raise_for_status()
    except requests.RequestException as error:
        detail = getattr(response, "text", "")[:500]
        raise MiniMaxVideoError(
            f"MiniMax H3 {action}失败: HTTP {response.status_code} {detail}"
        ) from error

    try:
        data = response.json()
    except ValueError as error:
        raise MiniMaxVideoError(f"MiniMax H3 {action}返回了无效 JSON") from error
    if not isinstance(data, dict):
        raise MiniMaxVideoError(f"MiniMax H3 {action}返回格式异常")
    return data


def _check_base_response(data: dict, action: str) -> None:
    base_resp = data.get("base_resp") or {}
    status_code = base_resp.get("status_code")
    if status_code not in (None, "", 0, "0", 200, "200"):
        status_msg = base_resp.get("status_msg") or base_resp.get("message") or ""
        raise MiniMaxVideoError(
            f"MiniMax H3 {action}返回错误: {status_code} {status_msg}".strip()
        )


def create_video_task(
    *,
    api_key: str,
    base_url: str,
    model: str,
    payload: dict,
    request_timeout: int = 120,
) -> str:
    """创建 H3 异步视频任务并返回 task_id。"""
    url = f"{base_url.rstrip('/')}{VIDEO_GENERATION_PATH}"
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": model, **payload},
            timeout=request_timeout,
        )
    except requests.RequestException as error:
        raise MiniMaxVideoError(f"MiniMax H3 创建任务失败: {error}") from error

    data = _response_json(response, "创建任务")
    _check_base_response(data, "创建任务")
    task_id = data.get("task_id") or (data.get("task") or {}).get("task_id")
    if not task_id:
        raise MiniMaxVideoError("MiniMax H3 创建任务未返回 task_id")
    return str(task_id)


def query_video_task(
    *,
    api_key: str,
    base_url: str,
    task_id: str,
    request_timeout: int = 60,
) -> tuple[str, Optional[str]]:
    """查询任务，返回 ``(status, video_url_or_none)``。"""
    url = f"{base_url.rstrip('/')}{VIDEO_QUERY_PATH}/{task_id}"
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=request_timeout,
        )
    except requests.RequestException as error:
        raise MiniMaxVideoError(f"MiniMax H3 查询任务失败: {error}") from error

    data = _response_json(response, "查询任务")
    _check_base_response(data, "查询任务")
    task = data.get("task") or data
    status = str(task.get("status", "")).strip().lower()
    if not status:
        raise MiniMaxVideoError("MiniMax H3 查询任务未返回 status")

    if status in {"succeeded", "success", "completed", "finished"}:
        content = task.get("content") or {}
        video_url = content.get("url") if isinstance(content, dict) else None
        video_url = video_url or task.get("video_url") or task.get("url")
        if not video_url:
            raise MiniMaxVideoError("MiniMax H3 任务成功但未返回视频 URL")
        return status, str(video_url)

    if status in {"failed", "cancelled", "canceled", "error"}:
        error_detail = task.get("error") or task.get("message") or "未知错误"
        raise MiniMaxVideoError(f"MiniMax H3 视频任务{status}: {error_detail}")

    return status, None


def download_video(video_url: str, output: str, *, request_timeout: int = 300) -> str:
    """下载 H3 结果视频到本地。"""
    output_path = Path(output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(video_url, stream=True, timeout=request_timeout)
        response.raise_for_status()
        with output_path.open("wb") as file_handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_handle.write(chunk)
    except (requests.RequestException, OSError) as error:
        try:
            output_path.unlink()
        except OSError:
            pass
        raise MiniMaxVideoError(f"下载 MiniMax H3 视频失败: {error}") from error
    return str(output_path)


def generate_video(
    *,
    prompt: str,
    api_key: str,
    base_url: str,
    model: str = "MiniMax-H3",
    duration: int = 5,
    resolution: str = "2K",
    ratio: str = "16:9",
    first_frame: Optional[str] = None,
    last_frame: Optional[str] = None,
    reference_images: Optional[Iterable[str]] = None,
    reference_videos: Optional[Iterable[str]] = None,
    reference_audios: Optional[Iterable[str]] = None,
    output: str = "output/minimax_h3.mp4",
    timeout: int = 900,
    poll_interval: int = 10,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict:
    """创建、轮询并下载一个 MiniMax H3 视频任务。"""
    if timeout <= 0:
        raise MiniMaxVideoError("timeout 必须大于 0 秒")
    if poll_interval <= 0:
        raise MiniMaxVideoError("poll-interval 必须大于 0 秒")

    payload = build_video_payload(
        prompt=prompt,
        duration=duration,
        resolution=resolution,
        ratio=ratio,
        first_frame=first_frame,
        last_frame=last_frame,
        reference_images=reference_images,
        reference_videos=reference_videos,
        reference_audios=reference_audios,
    )
    task_id = create_video_task(
        api_key=api_key,
        base_url=base_url,
        model=model,
        payload=payload,
    )

    deadline = time.monotonic() + timeout
    last_status = ""
    while True:
        status, video_url = query_video_task(
            api_key=api_key,
            base_url=base_url,
            task_id=task_id,
        )
        last_status = status
        if video_url:
            output_path = download_video(video_url, output)
            return {
                "task_id": task_id,
                "status": status,
                "video_url": video_url,
                "output": output_path,
                "model": model,
                "duration": duration,
                "resolution": payload["resolution"],
                "ratio": payload.get("ratio", "adaptive"),
            }

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MiniMaxVideoError(
                f"等待 MiniMax H3 任务超时（task_id={task_id}, 最后状态={last_status}）"
            )
        sleep_fn(min(poll_interval, remaining))
