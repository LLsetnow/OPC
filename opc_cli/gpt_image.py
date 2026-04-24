"""GPT-Image-2 文生图（apimart.ai 异步接口）

特点：
  - 异步处理：提交返回 task_id，轮询获取结果
  - 支持 13 种宽高比
  - 支持 1k / 2k / 4k 分辨率档位
  - 支持图生图（参考图 URL 或 base64）
"""

import base64
import time
from pathlib import Path
from typing import Optional

import requests


# ── API 端点 ──────────────────────────────────────────────────────

GENERATIONS_URL = "/images/generations"
TASKS_URL = "/tasks/"

# 支持的宽高比
SUPPORTED_SIZES = [
    "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5",
    "16:9", "9:16", "2:1", "1:2", "21:9", "9:21",
]

# 支持的分辨率档位
SUPPORTED_RESOLUTIONS = ["1k", "2k", "4k"]

# 4K 仅支持的比例
SIZE_4K_ONLY = {"16:9", "9:16", "2:1", "1:2", "21:9", "9:21"}

# 默认值
DEFAULT_SIZE = "2:3"
DEFAULT_RESOLUTION = "1k"

# 轮询配置
POLL_INITIAL_DELAY = 15   # 首次查询前等待（秒）
POLL_INTERVAL = 5          # 轮询间隔（秒）
POLL_TIMEOUT = 300         # 最大等待时间（秒）


def _build_proxies(proxy: Optional[str] = None) -> Optional[dict]:
    """构建 requests proxies 字典"""
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def submit_generation(
    prompt: str,
    api_key: str,
    base_url: str,
    model: str = "gpt-image-2",
    size: str = DEFAULT_SIZE,
    resolution: str = DEFAULT_RESOLUTION,
    image_urls: Optional[list[str]] = None,
    n: int = 1,
    proxies: Optional[dict] = None,
) -> dict:
    """提交 GPT-Image-2 文生图任务

    Args:
        prompt: 图像描述
        api_key: API Key
        base_url: API Base URL
        model: 模型名称
        size: 宽高比，如 "2:3", "16:9"
        resolution: 分辨率档位: "1k" / "2k" / "4k"
        image_urls: 参考图列表（URL 或 base64 data URI）
        n: 生成张数（固定为 1）
        proxies: requests 代理字典

    Returns:
        dict: {"task_id": "...", "status": "submitted"}
    """
    # 参数校验
    if size not in SUPPORTED_SIZES:
        raise ValueError(f"不支持的宽高比 '{size}'，可选: {', '.join(SUPPORTED_SIZES)}")

    if resolution not in SUPPORTED_RESOLUTIONS:
        raise ValueError(f"不支持的分辨率 '{resolution}'，可选: {', '.join(SUPPORTED_RESOLUTIONS)}")

    if resolution == "4k" and size not in SIZE_4K_ONLY:
        raise ValueError(f"4K 仅支持比例: {', '.join(sorted(SIZE_4K_ONLY))}，当前 '{size}' 不支持 4K")

    # 构建请求体
    body = {
        "model": model,
        "prompt": prompt,
        "n": n,
        "size": size,
        "resolution": resolution,
    }

    if image_urls:
        if len(image_urls) > 16:
            raise ValueError("参考图最多 16 张")
        body["image_urls"] = image_urls

    # 发送请求
    url = f"{base_url.rstrip('/')}{GENERATIONS_URL}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    resp = requests.post(url, json=body, headers=headers, timeout=60, proxies=proxies)
    data = resp.json()

    # 检查错误
    if "error" in data:
        err = data["error"]
        raise RuntimeError(f"GPT-Image API 错误 [{err.get('code')}]: {err.get('message', '未知错误')}")

    if data.get("code") != 200:
        raise RuntimeError(f"GPT-Image API 错误 [{data.get('code')}]: {data.get('message', '未知错误')}")

    tasks = data.get("data", [])
    if not tasks:
        raise RuntimeError("API 未返回任务信息")

    return {
        "task_id": tasks[0].get("task_id", ""),
        "status": tasks[0].get("status", "submitted"),
    }


def poll_task(
    task_id: str,
    api_key: str,
    base_url: str,
    timeout: int = POLL_TIMEOUT,
    initial_delay: int = POLL_INITIAL_DELAY,
    interval: int = POLL_INTERVAL,
    proxies: Optional[dict] = None,
) -> dict:
    """轮询任务结果

    Args:
        task_id: 任务 ID
        api_key: API Key
        base_url: API Base URL
        timeout: 最大等待时间（秒）
        initial_delay: 首次查询前等待（秒）
        interval: 轮询间隔（秒）
        proxies: requests 代理字典

    Returns:
        dict: 任务结果，包含 image_url, status 等
    """
    url = f"{base_url.rstrip('/')}{TASKS_URL}{task_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    # 首次延迟
    time.sleep(initial_delay)

    start = time.time()
    while True:
        resp = requests.get(url, headers=headers, timeout=30, proxies=proxies)
        data = resp.json()

        task_data = data.get("data", {})
        status = task_data.get("status", "")

        if status == "completed":
            images = task_data.get("result", {}).get("images", [])
            if not images:
                raise RuntimeError("任务完成但未返回图片")

            image_url = images[0].get("url", [""])[0] if images[0].get("url") else ""
            expires_at = images[0].get("expires_at", 0)

            return {
                "status": "completed",
                "image_url": image_url,
                "expires_at": expires_at,
                "actual_time": task_data.get("actual_time", 0),
                "task_id": task_id,
            }

        elif status == "failed":
            err_msg = task_data.get("error", {}).get("message", "未知错误")
            raise RuntimeError(f"任务失败: {err_msg}")

        # 检查超时
        elapsed = time.time() - start
        if elapsed > timeout:
            raise RuntimeError(f"任务超时（等待 {timeout}s），task_id: {task_id}")

        # 等待后重试
        time.sleep(interval)


def submit_and_wait(
    prompt: str,
    api_key: str,
    base_url: str,
    model: str = "gpt-image-2",
    size: str = DEFAULT_SIZE,
    resolution: str = DEFAULT_RESOLUTION,
    image_urls: Optional[list[str]] = None,
    timeout: int = POLL_TIMEOUT,
    on_status: Optional[callable] = None,
    proxies: Optional[dict] = None,
) -> dict:
    """提交任务并等待完成（一站式调用）

    Args:
        prompt: 图像描述
        api_key: API Key
        base_url: API Base URL
        model: 模型名称
        size: 宽高比
        resolution: 分辨率档位
        image_urls: 参考图列表
        timeout: 最大等待时间
        on_status: 状态回调函数
        proxies: requests 代理字典

    Returns:
        dict: 最终结果
    """
    # 提交任务
    submit_result = submit_generation(
        prompt=prompt,
        api_key=api_key,
        base_url=base_url,
        model=model,
        size=size,
        resolution=resolution,
        image_urls=image_urls,
        proxies=proxies,
    )

    task_id = submit_result["task_id"]
    if on_status:
        on_status(f"submitted", task_id)

    # 轮询结果
    result = poll_task(
        task_id=task_id,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        proxies=proxies,
    )

    return result


def load_image_as_base64(file_path: str) -> str:
    """将本地图片文件转为 base64 data URI

    Args:
        file_path: 图片文件路径

    Returns:
        str: data:image/xxx;base64,... 格式字符串
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"图片文件不存在: {file_path}")

    ext = path.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }

    mime = mime_map.get(ext)
    if not mime:
        raise ValueError(f"不支持的图片格式: {ext}，支持: {', '.join(mime_map.keys())}")

    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime};base64,{encoded}"


def download_image(url: str, save_path: str, proxies: Optional[dict] = None) -> str:
    """下载图片到本地

    Args:
        url: 图片 URL
        save_path: 保存路径
        proxies: requests 代理字典

    Returns:
        保存的文件路径
    """
    save_path = str(save_path)
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)

    resp = requests.get(url, timeout=60, stream=True, proxies=proxies)
    resp.raise_for_status()

    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    return save_path
