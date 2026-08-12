"""共享配置：环境变量加载、API 配置"""

import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_env(env_file: str = None):
    """加载 .env 文件，不覆盖已存在的环境变量"""
    if env_file and os.path.exists(env_file):
        load_dotenv(env_file, override=False)
        return

    # 依次尝试：指定路径 → 当前目录 → 项目根目录
    candidates = [".env"]
    project_root = Path(__file__).resolve().parent.parent
    candidates.append(str(project_root / ".env"))

    for p in candidates:
        if os.path.exists(p):
            load_dotenv(p, override=False)
            break


def get_api_config() -> tuple:
    """获取智谱 API 配置，返回 (api_key, base_url)"""
    api_key = os.environ.get("ZHIPU_API_KEY", "")
    base_url = os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")

    if not api_key:
        print("错误: 未设置 ZHIPU_API_KEY 环境变量")
        print("请在 .env 文件中添加: ZHIPU_API_KEY=your_api_key")
        sys.exit(1)

    return api_key, base_url.rstrip("/")


def get_llm_config() -> tuple:
    """获取 DeepSeek LLM 配置，返回 (api_key, base_url, model)。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("LLM_MODEL", "deepseek-v4-flash")

    if not api_key:
        print("错误: 未设置 DEEPSEEK_API_KEY 环境变量")
        sys.exit(1)

    return api_key, base_url, model


def get_vision_config() -> tuple:
    """
    获取视觉模型 API 配置，返回 (api_key, base_url, model)。
    使用 ZHIPU_API_KEY，并允许通过 VISION_BASE_URL / VISION_MODEL 覆盖模型配置。
    """
    api_key = os.environ.get("ZHIPU_API_KEY", "")
    base_url = os.environ.get("VISION_BASE_URL", "")
    model = os.environ.get("VISION_MODEL", "glm-5v-turbo")
    base_url = base_url or os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    if not api_key:
        print("错误: 未设置视觉 API 密钥")
        print("请在 .env 文件中添加 ZHIPU_API_KEY")
        sys.exit(1)

    return api_key, base_url.rstrip("/"), model


def get_image_config() -> tuple:
    """
    获取阿里云 Qwen Image 文生图/图像编辑配置，返回 (api_key, model)。
    使用 ALIYUN_API_KEY / IMAGE_MODEL。
    """
    api_key = os.environ.get("ALIYUN_API_KEY", "")
    model = os.environ.get("IMAGE_MODEL", "qwen-image-3.0")

    if not api_key:
        print("错误: 未设置 ALIYUN_API_KEY 环境变量")
        print("请在 .env 文件中添加: ALIYUN_API_KEY=your_aliyun_api_key")
        sys.exit(1)

    return api_key, model


def get_gpt_image_config() -> tuple:
    """
    获取 GPT-Image-2 文生图 API 配置，返回 (api_key, base_url, model)。
    使用 GPT_IMAGE_API_KEY / GPT_IMAGE_BASE_URL / GPT_IMAGE_MODEL。
    """
    api_key = os.environ.get("GPT_IMAGE_API_KEY", "")
    base_url = os.environ.get("GPT_IMAGE_BASE_URL", "https://api.apimart.ai/v1")
    model = os.environ.get("GPT_IMAGE_MODEL", "gpt-image-2-official")

    if not api_key:
        print("错误: 未设置 GPT_IMAGE_API_KEY 环境变量")
        print("请在 .env 文件中添加: GPT_IMAGE_API_KEY=your_api_key")
        sys.exit(1)

    return api_key, base_url.rstrip("/"), model


def get_asr_config() -> tuple:
    """
    获取 ASR 语音识别 API 配置，返回 (api_key, model)。
    使用 DashScope SDK 的 Recognition 类（非 OpenAI 兼容模式）。
    使用 ALIYUN_API_KEY。
    """
    api_key = os.environ.get("ALIYUN_API_KEY", "")
    model = os.environ.get("ASR_MODEL", "fun-asr-realtime")

    if not api_key:
        print("错误: 未设置 ALIYUN_API_KEY 环境变量")
        print("请在 .env 文件中添加: ALIYUN_API_KEY=your_aliyun_api_key")
        sys.exit(1)

    return api_key, model


def get_audio_config() -> tuple:
    """获取音乐理解配置，返回 (api_key, model)。"""
    api_key = os.environ.get("ALIYUN_API_KEY", "")
    model = os.environ.get("AUDIO_MODEL", "qwen3-omni-30b-a3b-captioner")

    if not api_key:
        print("错误: 未设置 ALIYUN_API_KEY 环境变量")
        print("请在 .env 文件中添加: ALIYUN_API_KEY=your_aliyun_api_key")
        sys.exit(1)

    return api_key, model


def get_qwen_tts_config() -> tuple:
    """
    获取阿里云 Qwen TTS（CosyVoice）API 配置，返回 (api_key, model)。
    使用 DashScope SDK 的 SpeechSynthesizer 类（WebSocket 协议）。
    使用 ALIYUN_API_KEY / QWEN_TTS_MODEL。
    """
    api_key = os.environ.get("ALIYUN_API_KEY", "")
    model = os.environ.get("QWEN_TTS_MODEL", "cosyvoice-v3-flash")

    if not api_key:
        print("错误: 未设置 ALIYUN_API_KEY 环境变量")
        print("请在 .env 文件中添加: ALIYUN_API_KEY=your_aliyun_api_key")
        sys.exit(1)

    return api_key, model


def _is_wsl() -> bool:
    """检测是否在 WSL 中运行"""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def _get_wsl_host_ip() -> Optional[str]:
    """WSL2 中获取 Windows 宿主 IP（从 /etc/resolv.conf）"""
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                if line.startswith("nameserver"):
                    return line.split()[1]
    except Exception:
        pass
    return None


def get_gpt_img_proxy() -> Optional[str]:
    """获取 gpt-img 代理地址，自动检测 WSL/Windows 环境

    端口号从 GPT_IMG_PROXY 配置中提取，未配置则默认 7897。
    IP 根据当前环境自动选择：
      - WSL → 自动从 /etc/resolv.conf 获取 Windows 宿主 IP（总是启用代理）
      - Windows → 127.0.0.1（仅当 GPT_IMG_PROXY 已配置时启用）
    """
    proxy_url = os.environ.get("GPT_IMG_PROXY")

    # 提取端口号
    port = 7897
    if proxy_url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(proxy_url)
            if parsed.port:
                port = parsed.port
        except Exception:
            pass

    if _is_wsl():
        # WSL 下总是使用代理（直连不通）
        host_ip = _get_wsl_host_ip()
        if host_ip:
            return f"http://{host_ip}:{port}"
        return proxy_url  # 回退

    # Windows：仅当显式配置了代理才启用
    if proxy_url:
        return f"http://127.0.0.1:{port}"

    return None


def get_comfyui_config() -> str:
    """获取 ComfyUI 根目录路径"""
    comfyui_root = os.environ.get("COMFYUI_ROOT", "")
    if not comfyui_root:
        print("错误: 未设置 COMFYUI_ROOT 环境变量")
        print("请在 .env 文件中添加: COMFYUI_ROOT=/path/to/ComfyUI")
        sys.exit(1)
    return comfyui_root


def get_bili_folder() -> Optional[str]:
    """获取 B站视频默认输出目录，未设置则返回 None"""
    return os.environ.get("BILI_FOLDER")


def get_douyin_folder() -> Optional[str]:
    """获取抖音视频默认输出目录，未设置则返回 None"""
    return os.environ.get("DOUYIN_FOLDER")


def get_x_folder() -> Optional[str]:
    """获取 X (Twitter) 视频默认输出目录，未设置则返回 None"""
    return os.environ.get("X_FOLDER")


def get_music_folder() -> Optional[str]:
    """获取网易云音乐默认输出目录，未设置则返回 None"""
    return os.environ.get("MUSIC_FOLDER")


def get_news_folder() -> Optional[str]:
    """获取 AI日报默认输出目录，未设置则返回 None"""
    return os.environ.get("NEWS_FOLDER")
