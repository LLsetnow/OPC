"""GPT-Image-2 官方渠道文生图（apimart.ai 异步接口）

API 参考: https://docs.apimart.ai/

特点：
  - 异步处理：提交返回 task_id，轮询获取结果
  - 模型: gpt-image-2-official（OpenAI 官方模型）
  - 支持 15 种宽高比 + auto，全比例支持 1K/2K/4K
  - 新增 quality / output_format / output_compression 等参数
  - 支持文生图 / 图生图 / 局部重绘（mask）三合一
  - 单次最多 4 张，参考图最多 16 张
"""

import base64
import json
import re
import time
from pathlib import Path
from typing import Optional

import requests
from openai import OpenAI


# ── API 端点 ──────────────────────────────────────────────────────

GENERATIONS_URL = "/images/generations"
TASKS_URL = "/tasks/"

# 支持的宽高比（新增 3:1 / 1:3 / auto）
SUPPORTED_SIZES = [
    "auto", "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5",
    "16:9", "9:16", "2:1", "1:2", "3:1", "1:3", "21:9", "9:21",
]

# 支持的分辨率档位
SUPPORTED_RESOLUTIONS = ["1k", "2k", "4k"]

# 4K 现已支持全比例（不再限制）
SIZE_4K_ONLY = set()  # 保留为空，兼容旧代码调用

# 默认值
DEFAULT_MODEL = "gpt-image-2-official"
DEFAULT_SIZE = "2:3"
DEFAULT_RESOLUTION = "1k"

# 轮询配置
POLL_INITIAL_DELAY = 15   # 首次查询前等待（秒）
POLL_INTERVAL = 5          # 轮询间隔（秒）
POLL_TIMEOUT = 300         # 最大等待时间（秒）

# LLM 丰富提示词的系统指令
ENHANCE_SYSTEM_PROMPT = """你是一位专业的 AI 绘图提示词专家，专门为 GPT-Image-2 模型优化提示词。用户会给你一段简短的图片描述，你需要将其扩展为结构化的 JSON 提示词。

要求：
1. 保持用户原始意图不变
2. 将描述拆分为以下字段，用英文填写每个字段的值：
   - style_and_tech: 画风、技术、摄影风格、质感（如 "cinematic lighting, shallow depth of field, 35mm film, warm tones"）
   - subject: 主体描述（如人物外貌、年龄、特征、场景物体等）
   - pose: 姿势、动作、构图描述
   - expression: 表情、情绪描述（如无人物可省略）
   - clothing: 服装、穿搭描述（如无人物可省略）
   - vibe: 整体氛围、感觉、情绪基调
   - aspect ratio: 宽高比（保持用户原始选择，默认 "2:3"）
3. 如果用户描述中不涉及某个字段（如无人物则不需要 expression/clothing/pose），则省略该字段
4. 每个字段的值用英文自然语言详细描述，用逗号分隔关键词
5. 严格输出 JSON 格式，不要输出任何其他内容

输出格式示例：
```json
{
  "prompt": {
    "style_and_tech": "cinematic lighting, shallow depth of field, 35mm film grain, warm golden hour tones, soft bokeh background",
    "subject": "young woman with long wavy hair, standing in a flower field",
    "pose": "looking over shoulder, gentle turn, hands holding a bouquet",
    "expression": "serene and contemplative, soft smile",
    "clothing": "flowing white linen dress, straw hat",
    "vibe": "dreamy, nostalgic, peaceful summer afternoon",
    "aspect ratio": "2:3"
  }
}
```"""


def enhance_prompt(
    prompt: str,
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str,
    aspect_ratio: str = DEFAULT_SIZE,
) -> dict:
    """使用 LLM 将简短提示词丰富为结构化 JSON 提示词"""
    client = OpenAI(api_key=llm_api_key, base_url=llm_base_url)

    user_msg = f"原始描述: {prompt}\n宽高比: {aspect_ratio}"
    response = client.chat.completions.create(
        model=llm_model,
        messages=[
            {"role": "system", "content": ENHANCE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.8,
        max_tokens=1024,
    )

    content = response.choices[0].message.content.strip()

    json_match = re.search(r'\{[\s\S]*\}', content)
    fallback = {"flat": prompt[:800], "json_str": prompt[:800], "json_dict": {}}
    if not json_match:
        return fallback

    try:
        data = json.loads(json_match.group())
        prompt_obj = data.get("prompt", data)
        parts = []
        for key, value in prompt_obj.items():
            if key == "aspect ratio":
                continue
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        flat = ", ".join(parts) if parts else prompt
        return {
            "flat": flat[:800],
            "json_str": json.dumps(data, ensure_ascii=False),
            "json_dict": data,
        }
    except (json.JSONDecodeError, AttributeError):
        return fallback


def _build_proxies(proxy: Optional[str] = None) -> Optional[dict]:
    """构建 requests proxies 字典"""
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def submit_generation(
    prompt: str,
    api_key: str,
    base_url: str,
    model: str = DEFAULT_MODEL,
    size: str = DEFAULT_SIZE,
    resolution: str = DEFAULT_RESOLUTION,
    quality: str = "auto",
    image_urls: Optional[list[str]] = None,
    mask_url: Optional[str] = None,
    n: int = 1,
    output_format: str = "png",
    output_compression: Optional[int] = None,
    moderation: str = "auto",
    proxies: Optional[dict] = None,
    prompt_json: Optional[str] = None,
) -> dict:
    """提交 GPT-Image-2-Official 文生图任务

    Args:
        prompt: 图像描述
        api_key: API Key
        base_url: API Base URL
        model: 模型名称（默认 gpt-image-2-official）
        size: 宽高比（如 "2:3", "16:9", "auto"，也支持像素如 "1024*1024"）
        resolution: 分辨率档位 "1k" / "2k" / "4k"
        quality: 图片质量 "auto" / "low" / "medium" / "high"
        image_urls: 参考图列表（URL 或 base64 data URI，最多 16 张）
        mask_url: 遮罩图 URL（局部重绘用）
        n: 生成张数（1 ~ 4）
        output_format: 输出格式 "png" / "jpeg" / "webp"
        output_compression: 压缩强度 0-100（仅 jpeg/webp）
        moderation: 审核强度 "auto" / "low"
        proxies: requests 代理字典
        prompt_json: 结构化 JSON 提示词（优先于 prompt）

    Returns:
        dict: {"task_id": "...", "status": "submitted"}
    """
    # 参数校验
    if size not in SUPPORTED_SIZES and "x" not in size.replace("*", "x").lower():
        raise ValueError(f"不支持的宽高比 '{size}'，可选: {', '.join(SUPPORTED_SIZES)}，或传入像素如 1024*1536")

    if resolution not in SUPPORTED_RESOLUTIONS:
        raise ValueError(f"不支持的分辨率 '{resolution}'，可选: {', '.join(SUPPORTED_RESOLUTIONS)}")

    if n < 1 or n > 4:
        raise ValueError("n 取值范围: 1 ~ 4")

    if image_urls and len(image_urls) > 16:
        raise ValueError("参考图最多 16 张")

    if output_format not in ("png", "jpeg", "webp"):
        raise ValueError("output_format 可选: png / jpeg / webp")

    if output_compression is not None and not (0 <= output_compression <= 100):
        raise ValueError("output_compression 范围: 0 ~ 100")

    # 构建请求体
    body = {
        "model": model,
        "prompt": prompt_json if prompt_json else prompt,
        "n": n,
        "size": size,
        "resolution": resolution,
        "quality": quality,
        "output_format": output_format,
        "moderation": moderation,
    }

    if output_compression is not None:
        body["output_compression"] = output_compression

    if image_urls:
        body["image_urls"] = image_urls

    if mask_url:
        body["mask_url"] = mask_url

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
        code = err.get("code", "")
        msg = err.get("message", "未知错误")
        raise RuntimeError(f"GPT-Image API 错误 [{code}]: {msg}")

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
    on_status: Optional[callable] = None,
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
        on_status: 状态变更回调

    Returns:
        dict: {status, image_url, expires_at, actual_time, task_id, cost, progress}
    """
    url = f"{base_url.rstrip('/')}{TASKS_URL}{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    last_status = "submitted"

    # 首次延迟
    time.sleep(initial_delay)

    start = time.time()
    while True:
        resp = requests.get(url, headers=headers, timeout=30, proxies=proxies)
        data = resp.json()

        task_data = data.get("data", {})
        status = task_data.get("status", "")

        # 状态变更回调
        if status and status != last_status and on_status:
            on_status(status, task_id)
            last_status = status

        if status == "completed":
            images = task_data.get("result", {}).get("images", [])
            if not images:
                raise RuntimeError("任务完成但未返回图片")

            image_url = (
                images[0].get("url", [""])[0]
                if isinstance(images[0].get("url"), list)
                else images[0].get("url", "")
            )
            expires_at = images[0].get("expires_at", 0)

            return {
                "status": "completed",
                "image_url": image_url,
                "expires_at": expires_at,
                "actual_time": task_data.get("actual_time", 0),
                "cost": task_data.get("cost", 0),
                "progress": task_data.get("progress", 100),
                "task_id": task_id,
            }

        elif status == "failed":
            err_msg = task_data.get("error", {}).get("message", "未知错误")
            raise RuntimeError(f"任务失败: {err_msg}")

        # 检查超时
        elapsed = time.time() - start
        if elapsed > timeout:
            raise RuntimeError(f"任务超时（等待 {timeout}s），task_id: {task_id}")

        time.sleep(interval)


def submit_and_wait(
    prompt: str,
    api_key: str,
    base_url: str,
    model: str = DEFAULT_MODEL,
    size: str = DEFAULT_SIZE,
    resolution: str = DEFAULT_RESOLUTION,
    quality: str = "auto",
    image_urls: Optional[list[str]] = None,
    mask_url: Optional[str] = None,
    n: int = 1,
    output_format: str = "png",
    output_compression: Optional[int] = None,
    moderation: str = "auto",
    timeout: int = POLL_TIMEOUT,
    on_status: Optional[callable] = None,
    proxies: Optional[dict] = None,
    prompt_json: Optional[str] = None,
) -> dict:
    """提交任务并等待完成（一站式调用）"""
    submit_result = submit_generation(
        prompt=prompt,
        api_key=api_key,
        base_url=base_url,
        model=model,
        size=size,
        resolution=resolution,
        quality=quality,
        image_urls=image_urls,
        mask_url=mask_url,
        n=n,
        output_format=output_format,
        output_compression=output_compression,
        moderation=moderation,
        proxies=proxies,
        prompt_json=prompt_json,
    )

    task_id = submit_result["task_id"]
    if on_status:
        on_status("submitted", task_id)

    result = poll_task(
        task_id=task_id,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        proxies=proxies,
        on_status=on_status,
    )

    return result


def load_image_as_base64(file_path: str) -> str:
    """将本地图片文件转为 base64 data URI"""
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
    """下载图片到本地"""
    save_path = str(save_path)
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)

    resp = requests.get(url, timeout=60, stream=True, proxies=proxies)
    resp.raise_for_status()

    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    return save_path
