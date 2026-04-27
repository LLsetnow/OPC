"""阿里云百炼 z-image-turbo 文生图"""

import os
import time
from pathlib import Path
from typing import Optional

import requests
from openai import OpenAI


# ── API 端点 ──────────────────────────────────────────────────────

IMAGE_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

# 推荐分辨率（总像素 1280*1280 档位）
RECOMMENDED_SIZES = {
    "1:1": "1280*1280",
    "2:3": "1024*1536",
    "3:2": "1536*1024",
    "3:4": "1104*1472",
    "4:3": "1472*1104",
    "7:9": "1120*1440",
    "9:7": "1440*1120",
    "9:16": "864*1536",
    "9:21": "720*1680",
    "16:9": "1536*864",
    "21:9": "1680*720",
}

DEFAULT_SIZE = "1024*1536"  # 2:3 竖图

# LLM 丰富提示词的系统指令
ENHANCE_SYSTEM_PROMPT = """你是一位专业的 AI 绘图提示词专家。用户会给你一段简短的图片描述，你需要将其扩展为结构化的 JSON 提示词。

要求：
1. 保持用户原始意图不变
2. 将描述拆分为以下字段，用英文填写每个字段的值：
   - style_and_tech: 画风、技术、摄影风格、质感（如 "mobile phone photo, CCD camera, grainy, candid snapshot"）
   - subject: 主体描述（如人物外貌、年龄、特征等）
   - pose: 姿势、动作描述
   - expression: 表情、情绪描述
   - clothing: 服装、穿搭描述
   - vibe: 整体氛围、感觉、情绪基调
   - aspect ratio: 宽高比（保持用户原始选择，默认 "2:3"）
3. 如果用户描述中不涉及某个字段（如无人物则不需要 expression/clothing/pose），则省略该字段
4. 每个字段的值用英文自然语言详细描述，用逗号分隔关键词
5. 严格输出 JSON 格式，不要输出任何其他内容

输出格式示例：
```json
{
  "prompt": {
    "style_and_tech": "mobile phone photo, old CCD camera aesthetic, harsh flash, grainy, dim messy indoor lighting, candid snapshot feeling, slight motion blur",
    "subject": "young Korean female idol, soft innocent look",
    "pose": "mid-action, slightly turning head toward camera as if just noticed being photographed, shoulders slightly raised",
    "expression": "eyes widened slightly, lips parted in surprise, shy and caught-off-guard expression",
    "clothing": "loose soft homewear, thin cardigan + inner top, slightly slipping off one shoulder",
    "vibe": "unprepared, intimate, accidental moment, evokes curiosity and protectiveness",
    "aspect ratio": "9:16"
  }
}
```"""


def enhance_prompt(
    prompt: str,
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str,
    aspect_ratio: str = "2:3",
) -> dict:
    """使用 LLM 丰富提示词为结构化 JSON

    Args:
        prompt: 原始简短提示词
        llm_api_key: LLM API Key
        llm_base_url: LLM API Base URL
        llm_model: LLM 模型名称
        aspect_ratio: 宽高比

    Returns:
        dict: {
            "flat": "逗号拼接的扁平提示词（用于 text2img 等）",
            "json_str": "完整 JSON 字符串（用于 GPT-Image 等支持结构化 prompt 的 API）",
            "json_dict": {"prompt": {...}} 原始 dict
        }
        解析失败时 flat 和 json_str 均为原始 prompt
    """
    import json
    import re

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

    # 提取 JSON（兼容 markdown 代码块包裹）
    json_match = re.search(r'\{[\s\S]*\}', content)
    fallback = {"flat": prompt[:800], "json_str": prompt[:800], "json_dict": {}}
    if not json_match:
        return fallback

    try:
        data = json.loads(json_match.group())
        prompt_obj = data.get("prompt", data)
        # 拼接所有字段值（排除 aspect ratio）为扁平提示词
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


def generate_image(
    prompt: str,
    api_key: str,
    size: Optional[str] = None,
    model: str = "z-image-turbo",
    prompt_extend: bool = False,
    seed: Optional[int] = None,
) -> dict:
    """调用 z-image-turbo 生成图片

    Args:
        prompt: 正向提示词（中英文，≤800字符）
        api_key: 阿里云百炼 API Key
        size: 输出分辨率，格式为 宽*高，如 1024*1536
        model: 模型名称
        prompt_extend: 是否启用智能提示词改写
        seed: 随机种子

    Returns:
        dict: 包含 image_url, text, width, height 等信息
    """
    # 解析 size 参数
    actual_size = _resolve_size(size)

    # 构建请求体
    body = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt[:800]}],  # 截断超长提示词
                }
            ]
        },
        "parameters": {
            "size": actual_size,
            "prompt_extend": prompt_extend,
        },
    }

    if seed is not None:
        body["parameters"]["seed"] = seed

    # 发送请求
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    resp = requests.post(IMAGE_API_URL, json=body, headers=headers, timeout=120)
    data = resp.json()

    # 检查错误
    if "code" in data:
        raise RuntimeError(
            f"文生图 API 错误 [{data.get('code')}]: {data.get('message', '未知错误')}"
        )

    # 解析结果
    choices = data.get("output", {}).get("choices", [])
    if not choices:
        raise RuntimeError("API 未返回生成结果")

    message = choices[0].get("message", {})
    content = message.get("content", [])

    image_url = None
    text_out = ""
    for item in content:
        if "image" in item:
            image_url = item["image"]
        if "text" in item:
            text_out = item["text"]

    usage = data.get("usage", {})

    return {
        "image_url": image_url,
        "text": text_out,
        "width": usage.get("width", 0),
        "height": usage.get("height", 0),
        "size": actual_size,
        "request_id": data.get("request_id", ""),
    }


def download_image(url: str, save_path: str) -> str:
    """下载图片到本地

    Args:
        url: 图片 URL
        save_path: 保存路径

    Returns:
        保存的文件路径
    """
    save_path = str(save_path)
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)

    resp = requests.get(url, timeout=60, stream=True)
    resp.raise_for_status()

    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    return save_path


def _resolve_size(size: Optional[str]) -> str:
    """解析分辨率参数

    支持格式:
      - 宽*高 如 1024*1536
      - 宽高比 如 2:3, 16:9
      - None → 默认 2:3 竖图
    """
    if not size:
        return DEFAULT_SIZE

    # 已经是 宽*高 格式
    if "*" in size:
        return size

    # 宽高比格式 如 2:3
    if size in RECOMMENDED_SIZES:
        return RECOMMENDED_SIZES[size]

    # 尝试解析 n:n 格式
    if ":" in size:
        # 找不到预定义的，给出提示
        available = ", ".join(RECOMMENDED_SIZES.keys())
        raise ValueError(
            f"不支持的宽高比 '{size}'，可选: {available}\n"
            f"或直接指定分辨率，如 1024*1536"
        )

    raise ValueError(
        f"无法解析分辨率 '{size}'，请使用 宽*高（如 1024*1536）或宽高比（如 2:3）格式"
    )
