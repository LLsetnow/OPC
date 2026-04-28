"""API 连通性检查：逐个测试 .env 中配置的所有 API"""

import os
import time
from typing import Optional

import requests
from openai import OpenAI
from rich.table import Table

from .config import (
    load_env,
    get_llm_config,
    get_api_config,
    get_vision_config,
    get_image_config,
    get_gpt_image_config,
    get_gpt_img_proxy,
)


# ── 检查结果 ──────────────────────────────────────────────────────

class CheckResult:
    def __init__(self, name: str, ok: bool, detail: str, latency_ms: int = 0):
        self.name = name
        self.ok = ok
        self.detail = detail
        self.latency_ms = latency_ms


# ── 各 API 检查函数 ──────────────────────────────────────────────

def check_llm() -> CheckResult:
    """测试 LLM API（发送最简短请求）"""
    try:
        api_key, base_url, model = get_llm_config()
    except SystemExit:
        return CheckResult("LLM", False, "未配置 LLM_API_KEY")

    t0 = time.time()
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=30)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5,
        )
        latency = int((time.time() - t0) * 1000)
        content = resp.choices[0].message.content or ""
        return CheckResult("LLM", True, f"model={model} url={base_url} resp={content[:30]}", latency)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return CheckResult("LLM", False, f"{type(e).__name__}: {e}", latency)


def check_zhipu() -> CheckResult:
    """测试智谱 TTS API（列出音色）"""
    try:
        api_key, base_url = get_api_config()
    except SystemExit:
        return CheckResult("ZhiPu (TTS)", False, "未配置 ZHIPU_API_KEY")

    t0 = time.time()
    try:
        url = f"{base_url}/voice/list?page=1&page_size=1&voice_type=OFFICIAL"
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(url, headers=headers, timeout=15)
        latency = int((time.time() - t0) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            count = len(data.get("data", {}).get("voices", []))
            return CheckResult("ZhiPu (TTS)", True, f"url={base_url} voices_ok", latency)
        elif resp.status_code == 401:
            return CheckResult("ZhiPu (TTS)", False, f"认证失败 (401) url={base_url}", latency)
        else:
            return CheckResult("ZhiPu (TTS)", False, f"HTTP {resp.status_code}: {resp.text[:100]}", latency)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return CheckResult("ZhiPu (TTS)", False, f"{type(e).__name__}: {e}", latency)


def check_asr() -> CheckResult:
    """测试阿里云 DashScope ASR API（验证 key 有效性）"""
    try:
        from .config import get_asr_config
        api_key, model = get_asr_config()
    except SystemExit:
        return CheckResult("ASR (DashScope)", False, "未配置 IMAGE_API_KEY 或 ASR_API_KEY")

    t0 = time.time()
    try:
        # 使用 DashScope 模型列表接口验证 key 有效性
        url = "https://dashscope.aliyuncs.com/api/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(url, headers=headers, timeout=15)
        latency = int((time.time() - t0) * 1000)

        if resp.status_code == 200:
            return CheckResult("ASR (DashScope)", True, f"model={model} key_ok", latency)
        elif resp.status_code == 401:
            return CheckResult("ASR (DashScope)", False, f"认证失败 (401) model={model}", latency)
        else:
            return CheckResult("ASR (DashScope)", True, f"model={model} key_probably_ok (HTTP {resp.status_code})", latency)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return CheckResult("ASR (DashScope)", False, f"{type(e).__name__}: {e}", latency)


def check_vision() -> CheckResult:
    """测试视觉模型 API（发送最简短文本请求验证连通性）"""
    try:
        api_key, base_url, model = get_vision_config()
    except SystemExit:
        return CheckResult("Vision", False, "未配置 VISION_API_KEY")

    t0 = time.time()
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=30)
        # 纯文本请求验证 key 有效性（不需要图片）
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "1+1=?"}],
            max_tokens=5,
        )
        latency = int((time.time() - t0) * 1000)
        content = resp.choices[0].message.content or ""
        return CheckResult("Vision", True, f"model={model} url={base_url} resp={content[:30]}", latency)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return CheckResult("Vision", False, f"{type(e).__name__}: {e}", latency)


def check_image() -> CheckResult:
    """测试阿里云百炼文生图 API（用最小请求验证 key 有效性）"""
    try:
        api_key, model = get_image_config()
    except SystemExit:
        return CheckResult("Image (DashScope)", False, "未配置 IMAGE_API_KEY")

    t0 = time.time()
    try:
        # 调用百炼模型列表接口验证 key
        url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # 发一个会快速失败的请求（空 prompt），只看认证是否通过
        body = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": [{"text": "test"}]}]},
        }
        resp = requests.post(url, json=body, headers=headers, timeout=15)
        latency = int((time.time() - t0) * 1000)

        if resp.status_code == 401:
            return CheckResult("Image (DashScope)", False, f"认证失败 (401)", latency)
        elif resp.status_code == 400:
            # 400 说明认证通过了，只是参数不对
            return CheckResult("Image (DashScope)", True, f"model={model} auth_ok", latency)
        elif resp.status_code == 200:
            return CheckResult("Image (DashScope)", True, f"model={model}", latency)
        else:
            # 其他状态码也可能是认证通过的
            data = resp.text[:100]
            return CheckResult("Image (DashScope)", True, f"model={model} HTTP={resp.status_code}", latency)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return CheckResult("Image (DashScope)", False, f"{type(e).__name__}: {e}", latency)


def check_gpt_image() -> CheckResult:
    """测试 GPT-Image API（验证 key 和 base_url 连通性）"""
    try:
        api_key, base_url, model = get_gpt_image_config()
    except SystemExit:
        return CheckResult("GPT-Image", False, "未配置 GPT_IMAGE_API_KEY")

    t0 = time.time()
    try:
        # 尝试调用 models 接口验证 key
        url = f"{base_url}/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(url, headers=headers, timeout=15)
        latency = int((time.time() - t0) * 1000)

        if resp.status_code == 401:
            return CheckResult("GPT-Image", False, f"认证失败 (401) url={base_url}", latency)
        elif resp.status_code == 200:
            return CheckResult("GPT-Image", True, f"model={model} url={base_url}", latency)
        else:
            return CheckResult("GPT-Image", True, f"model={model} url={base_url} HTTP={resp.status_code}", latency)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return CheckResult("GPT-Image", False, f"{type(e).__name__}: {e}", latency)


def check_proxy() -> CheckResult:
    """测试代理连通性"""
    proxy = get_gpt_img_proxy()
    if not proxy:
        return CheckResult("GPT_IMG_PROXY", True, "未配置（直连）")

    t0 = time.time()
    try:
        proxies = {"http": proxy, "https": proxy}
        resp = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=10)
        latency = int((time.time() - t0) * 1000)

        if resp.status_code == 200:
            ip = resp.json().get("origin", "?")
            return CheckResult("GPT_IMG_PROXY", True, f"proxy={proxy} exit_ip={ip}", latency)
        else:
            return CheckResult("GPT_IMG_PROXY", False, f"HTTP {resp.status_code}", latency)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return CheckResult("GPT_IMG_PROXY", False, f"{type(e).__name__}: {e}", latency)


def check_cookies() -> CheckResult:
    """检查 cookies 文件是否存在"""
    cookies_path = os.environ.get("YT_DLP_COOKIES", "")
    if not cookies_path:
        return CheckResult("YT_DLP_COOKIES", True, "未配置（可选）")

    from pathlib import Path
    p = Path(cookies_path)
    if p.exists():
        size = p.stat().st_size
        return CheckResult("YT_DLP_COOKIES", True, f"path={cookies_path} ({size}B)")
    else:
        return CheckResult("YT_DLP_COOKIES", False, f"文件不存在: {cookies_path}")


# ── 主流程 ──────────────────────────────────────────────────────

# 可用的 API 名称 → 检查函数
CHECK_MAP: dict[str, callable] = {
    "llm": check_llm,
    "zhipu": check_zhipu,
    "asr": check_asr,
    "vision": check_vision,
    "image": check_image,
    "gpt-image": check_gpt_image,
    "proxy": check_proxy,
    "cookies": check_cookies,
}


def run_check_api(env_file: Optional[str] = None, only: Optional[list[str]] = None) -> list[CheckResult]:
    """运行 API 检查，返回结果列表

    Args:
        env_file: .env 文件路径
        only: 只检查指定 API，如 ["llm", "vision"]；为 None 则检查全部
    """
    load_env(env_file)

    if only:
        # 大小写不敏感匹配
        name_map = {k.lower(): k for k in CHECK_MAP}
        selected = []
        for name in only:
            key = name.lower()
            if key in name_map:
                selected.append(CHECK_MAP[name_map[key]])
            else:
                available = ", ".join(sorted(CHECK_MAP.keys()))
                console_msg = f"未知 API: {name}，可用: {available}"
                raise ValueError(console_msg)
        checks = selected
    else:
        checks = list(CHECK_MAP.values())

    results = []
    for check_fn in checks:
        result = check_fn()
        results.append(result)

    return results
