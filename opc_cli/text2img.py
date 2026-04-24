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
ENHANCE_SYSTEM_PROMPT = """你是一位专业的 AI 绘图提示词专家。用户会给你一段简短的图片描述，你需要将其扩展为一段详细、自然的文生图提示词。

要求：
1. 保持用户原始意图不变
2. 用自然语言详细描述画面：场景、人物、动作、表情、服装、环境等具体细节
3. 补充光影与氛围：光线方向、色温、天气、时间（清晨/黄昏/夜晚等）
4. 补充构图与视角：景别（特写/近景/中景/远景）、拍摄角度、景深
5. 补充画风与质感：如油画、水彩、写实摄影、赛博朋克、宫崎骏风格等
6. 用中文自然语言描述，像在向画家详细说明一幅画的每个细节
7. 最终提示词控制在 800 字符以内
8. 只输出丰富后的提示词，不要任何解释或前缀"""


def enhance_prompt(
    prompt: str,
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str,
) -> str:
    """使用 LLM 丰富提示词

    Args:
        prompt: 原始简短提示词
        llm_api_key: LLM API Key
        llm_base_url: LLM API Base URL
        llm_model: LLM 模型名称

    Returns:
        丰富后的提示词
    """
    client = OpenAI(api_key=llm_api_key, base_url=llm_base_url)

    response = client.chat.completions.create(
        model=llm_model,
        messages=[
            {"role": "system", "content": ENHANCE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        max_tokens=1024,
    )

    enhanced = response.choices[0].message.content.strip()
    # 截断超长提示词
    return enhanced[:800]


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
