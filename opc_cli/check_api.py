"""API 连通性检查：逐个测试 .env 中配置的所有 API"""

import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

import requests
from openai import OpenAI
from rich.table import Table

from .config import (
    load_env,
    get_llm_config,
    get_api_config,
    get_vision_config,
    get_video_config,
    get_image_config,
    get_gpt_img_proxy,
)
from .codex_image import codex_available as _codex_available


# ── 检查结果 ──────────────────────────────────────────────────────

class CheckResult:
    def __init__(self, name: str, ok: bool, detail: str, latency_ms: int = 0):
        self.name = name
        self.ok = ok
        self.detail = detail
        self.latency_ms = latency_ms


@dataclass(frozen=True)
class CommandAvailability:
    """描述一个 opc 命令在当前环境中的可用程度。"""

    command: str
    status: str
    required: str
    detail: str

    @property
    def available(self) -> bool:
        """命令至少有一种可用模式。"""
        return self.status != "不可用"


def _configured_key(*names: str) -> tuple[str, str]:
    """返回第一个已配置的环境变量名和值，不暴露 key 内容。"""
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return name, value
    return "", ""


def _key_source(*names: str) -> str:
    """返回第一个已配置的 key 名称。"""
    return _configured_key(*names)[0]


def get_command_availability() -> list[CommandAvailability]:
    """根据当前环境变量，列出每个 opc 命令的可用程度。

    这里仅检查配置是否存在，不会发起网络请求，也不会输出 API key 的内容。
    ``部分可用`` 表示命令仍有无需该凭证或使用其他引擎的模式。
    """
    deepseek_source = _key_source("DEEPSEEK_API_KEY")
    zhipu_source = _key_source("ZHIPU_API_KEY")
    vision_source = zhipu_source
    asr_source = _key_source("ALIYUN_API_KEY")
    image_source = asr_source
    qwen_tts_source = asr_source
    audio_source = _key_source("ALIYUN_API_KEY")
    video_source = _key_source("ALIYUN_API_KEY")
    minimax_music_source = _key_source("MINIMAX_API_KEY")
    minimax_video_source = _key_source("MINIMAX_API_KEY")
    music_gen_source = _key_source("ALIYUN_API_KEY", "MINIMAX_API_KEY")
    codex_available_ = _codex_available()
    aigate_source = _key_source("AIGATE_TOKEN")
    comfyui_source = _key_source("COMFYUI_ROOT")

    full_bili = bool(asr_source and deepseek_source)
    bili_missing = []
    if not asr_source:
        bili_missing.append("ALIYUN")
    if not deepseek_source:
        bili_missing.append("DEEPSEEK")

    tts_modes = bool(qwen_tts_source), bool(zhipu_source)
    if all(tts_modes):
        tts_status = "可用"
        tts_detail = "Qwen TTS 默认引擎 + GLM-TTS 引擎均可用"
    elif any(tts_modes):
        tts_status = "部分可用"
        tts_detail = "仅可用 " + ("Qwen TTS" if qwen_tts_source else "GLM-TTS") + " 引擎"
    else:
        tts_status = "不可用"
        tts_detail = "未配置 ALIYUN_API_KEY 或 ZHIPU_API_KEY"

    if audio_source and minimax_music_source:
        music_gen_detail = "阿里云 Fun-Music + MiniMax Music 均可用"
    elif audio_source:
        music_gen_detail = "仅阿里云 Fun-Music 可用；缺少 MINIMAX_API_KEY"
    elif minimax_music_source:
        music_gen_detail = "仅 MiniMax Music 可用；缺少 ALIYUN_API_KEY"
    else:
        music_gen_detail = "缺少 ALIYUN_API_KEY 和 MINIMAX_API_KEY"

    image_gen_status = "不可用"
    if image_source and codex_available_:
        image_gen_status = "可用"
        image_gen_detail = "Qwen Image + GPT-Image（经 codex CLI）双引擎均可用"
    elif image_source:
        image_gen_status = "部分可用"
        image_gen_detail = "仅 Qwen Image 引擎可用（--engine qwen）；缺少 codex CLI（需 0.147+ 并登录 ChatGPT）"
    elif codex_available_:
        image_gen_status = "部分可用"
        image_gen_detail = "仅 GPT-Image 引擎可用（--engine gpt-image，经 codex CLI）；缺少 ALIYUN_API_KEY"
    else:
        image_gen_detail = "缺少 ALIYUN_API_KEY 与 codex CLI（gpt-image 引擎需要）"

    return [
        CommandAvailability(
            "media download",
            "可用" if full_bili else "部分可用",
            "ALIYUN + DEEPSEEK（--summarize 总结）",
            "下载可用；--summarize 内容总结缺少 " + "、".join(bili_missing)
            if not full_bili
            else "下载 + --summarize 内容总结均可用",
        ),
        CommandAvailability(
            "music understand",
            "可用" if audio_source else "不可用",
            "ALIYUN_API_KEY",
            f"使用 {audio_source}" if audio_source else "缺少 ALIYUN_API_KEY",
        ),
        CommandAvailability("music beats", "可用", "无需 API Key", "librosa 本地鼓点检测可用"),
        CommandAvailability(
            "music generate",
            "可用" if music_gen_source else "不可用",
            "ALIYUN_API_KEY 或 MINIMAX_API_KEY",
            music_gen_detail,
        ),
        CommandAvailability(
            "image understand",
            "可用" if vision_source else "不可用",
            "ZHIPU_API_KEY",
            f"使用 {vision_source}" if vision_source else "缺少 ZHIPU_API_KEY",
        ),
        CommandAvailability(
            "image generate",
            image_gen_status,
            "ALIYUN_API_KEY 或 codex CLI",
            image_gen_detail,
        ),
        CommandAvailability(
            "video understand",
            "可用" if video_source else "不可用",
            "ALIYUN_API_KEY",
            f"使用 {video_source}" if video_source else "缺少 ALIYUN_API_KEY",
        ),
        CommandAvailability(
            "video generate",
            "可用" if minimax_video_source else "不可用",
            "MINIMAX_API_KEY",
            f"使用 {minimax_video_source}（MiniMax H3）"
            if minimax_video_source
            else "缺少 MINIMAX_API_KEY",
        ),
        CommandAvailability(
            "speech tts",
            tts_status,
            "ALIYUN_API_KEY 或 ZHIPU_API_KEY",
            tts_detail,
        ),
        CommandAvailability(
            "speech asr",
            "可用" if asr_source else "不可用",
            "ALIYUN_API_KEY",
            f"使用 {asr_source}" if asr_source else "缺少 ALIYUN_API_KEY",
        ),
        CommandAvailability("local-tts", "可用", "无需 API Key", "使用本地 Qwen3-TTS 模型"),
        CommandAvailability(
            "comfyui",
            "可用" if comfyui_source else "部分可用",
            "--start 需要 COMFYUI_ROOT",
            "可查看/控制已运行服务；--start 缺少 COMFYUI_ROOT"
            if not comfyui_source
            else f"使用 {comfyui_source} 启动本地服务",
        ),
        CommandAvailability(
            "aigate",
            "可用" if aigate_source else "部分可用",
            "AIGATE_TOKEN（--workflows 除外）",
            f"使用 {aigate_source}" if aigate_source else "仅本地 --workflows 可用；缺少 AIGATE_TOKEN",
        ),
        CommandAvailability("news", "可用" if deepseek_source else "不可用", "DEEPSEEK_API_KEY", f"使用 {deepseek_source}" if deepseek_source else "缺少 DEEPSEEK_API_KEY"),
        CommandAvailability("check-api", "可用", "无需 API Key", "配置检查和连通性检查可用"),
    ]


# ── 各 API 检查函数 ──────────────────────────────────────────────

def check_llm() -> CheckResult:
    """测试 LLM API（发送最简短请求）"""
    if not _key_source("DEEPSEEK_API_KEY"):
        return CheckResult("DeepSeek (LLM)", False, "未配置 DEEPSEEK_API_KEY")

    try:
        api_key, base_url, model = get_llm_config()
    except SystemExit:
        return CheckResult("DeepSeek (LLM)", False, "未配置 DEEPSEEK_API_KEY")

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
        return CheckResult("DeepSeek (LLM)", True, f"model={model} url={base_url} resp={content[:30]}", latency)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return CheckResult("DeepSeek (LLM)", False, f"{type(e).__name__}: {e}", latency)


def check_zhipu() -> CheckResult:
    """测试智谱 TTS API（列出音色）"""
    if not _key_source("ZHIPU_API_KEY"):
        return CheckResult("ZhiPu (TTS)", False, "未配置 ZHIPU_API_KEY")

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
    if not _key_source("ALIYUN_API_KEY"):
        return CheckResult("ASR (DashScope)", False, "未配置 ALIYUN_API_KEY")

    try:
        from .config import get_asr_config
        api_key, model = get_asr_config()
    except SystemExit:
        return CheckResult("ASR (DashScope)", False, "未配置 ALIYUN_API_KEY")

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
    if not _key_source("ZHIPU_API_KEY"):
        return CheckResult("Vision", False, "未配置 ZHIPU_API_KEY")

    try:
        api_key, base_url, model = get_vision_config()
    except SystemExit:
        return CheckResult("Vision", False, "未配置 ZHIPU_API_KEY")

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


def check_video() -> CheckResult:
    """测试 Qwen3-VL 视频理解 API（发送最简短文本请求验证连通性）。"""
    if not _key_source("ALIYUN_API_KEY"):
        return CheckResult("Video (Qwen3-VL)", False, "未配置 ALIYUN_API_KEY")

    try:
        api_key, base_url, model = get_video_config()
    except SystemExit:
        return CheckResult("Video (Qwen3-VL)", False, "未配置 ALIYUN_API_KEY")

    t0 = time.time()
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=30)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "1+1=?"}],
            max_tokens=5,
        )
        latency = int((time.time() - t0) * 1000)
        content = resp.choices[0].message.content or ""
        return CheckResult(
            "Video (Qwen3-VL)",
            True,
            f"model={model} url={base_url} resp={content[:30]}",
            latency,
        )
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return CheckResult("Video (Qwen3-VL)", False, f"{type(e).__name__}: {e}", latency)


def check_image() -> CheckResult:
    """测试阿里云百炼文生图 API（用最小请求验证 key 有效性）"""
    if not _key_source("ALIYUN_API_KEY"):
        return CheckResult("Image (DashScope)", False, "未配置 ALIYUN_API_KEY")

    try:
        api_key, model = get_image_config()
    except SystemExit:
        return CheckResult("Image (DashScope)", False, "未配置 ALIYUN_API_KEY")

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
    """检查 GPT-Image 引擎（经本机 codex CLI 驱动）是否可用。

    gpt-image 引擎不再直接调用 OpenAI 兼容 API，而是通过 codex exec 的
    内置 image_gen 工具生成（需 codex-cli 0.147+ 并已用 ChatGPT 账号登录）。
    """
    if not _codex_available():
        return CheckResult(
            "GPT-Image (codex)",
            False,
            "未安装 codex CLI（需要 0.147+，且已用 ChatGPT 账号登录）",
        )

    t0 = time.time()
    try:
        result = subprocess.run(
            ["codex", "--version"], capture_output=True, text=True, timeout=15
        )
        latency = int((time.time() - t0) * 1000)
        version = (result.stdout or result.stderr).strip()
        return CheckResult("GPT-Image (codex)", True, f"codex {version}", latency)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return CheckResult("GPT-Image (codex)", False, f"{type(e).__name__}: {e}", latency)


def _check_dashscope_key(
    name: str,
    api_key: str,
    model: str,
) -> CheckResult:
    """通过 DashScope 模型列表接口检查一个服务共用的 API key。"""
    t0 = time.time()
    try:
        url = "https://dashscope.aliyuncs.com/api/v1/models"
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        latency = int((time.time() - t0) * 1000)
        if resp.status_code == 200:
            return CheckResult(name, True, f"model={model} key_ok", latency)
        if resp.status_code == 401:
            return CheckResult(name, False, f"认证失败 (401) model={model}", latency)
        return CheckResult(name, True, f"model={model} key_probably_ok (HTTP {resp.status_code})", latency)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return CheckResult(name, False, f"{type(e).__name__}: {e}", latency)


def check_audio() -> CheckResult:
    """测试阿里云 Qwen3-Omni 音乐理解 API。"""
    if not _key_source("ALIYUN_API_KEY"):
        return CheckResult("Audio (Qwen3-Omni)", False, "未配置 ALIYUN_API_KEY")

    from .config import get_audio_config
    api_key, model = get_audio_config()
    return _check_dashscope_key("Audio (Qwen3-Omni)", api_key, model)


def check_qwen_tts() -> CheckResult:
    """测试阿里云 CosyVoice TTS API。"""
    if not _key_source("ALIYUN_API_KEY"):
        return CheckResult("Qwen TTS (DashScope)", False, "未配置 ALIYUN_API_KEY")

    from .config import get_qwen_tts_config
    api_key, model = get_qwen_tts_config()
    return _check_dashscope_key("Qwen TTS (DashScope)", api_key, model)


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
    "deepseek": check_llm,
    "zhipu": check_zhipu,
    "asr": check_asr,
    "audio": check_audio,
    "qwen-tts": check_qwen_tts,
    "vision": check_vision,
    "video": check_video,
    "image": check_image,
    "gpt-image": check_gpt_image,
    "proxy": check_proxy,
    "cookies": check_cookies,
}


def run_check_api(env_file: Optional[str] = None, only: Optional[list[str]] = None) -> list[CheckResult]:
    """运行 API 检查，返回结果列表

    Args:
        env_file: .env 文件路径
        only: 只检查指定 API，如 ["deepseek", "vision"]；为 None 则检查全部
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
        # ``llm`` 是 ``deepseek`` 的兼容别名，避免全量检查重复请求同一个 API。
        checks = []
        for check_fn in CHECK_MAP.values():
            if check_fn not in checks:
                checks.append(check_fn)

    results = []
    for check_fn in checks:
        result = check_fn()
        results.append(result)

    return results
