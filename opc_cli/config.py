"""共享配置：环境变量加载、API 配置"""

import os
import sys
from pathlib import Path

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
    """获取 LLM 配置，返回 (api_key, base_url, model)"""
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("ZHIPU_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL") or os.environ.get(
        "ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
    )
    model = os.environ.get("LLM_MODEL", "glm-4-flash")

    if not api_key:
        print("错误: 未设置 LLM_API_KEY 或 ZHIPU_API_KEY 环境变量")
        sys.exit(1)

    return api_key, base_url, model


def get_vision_config() -> tuple:
    """
    获取视觉模型 API 配置，返回 (api_key, base_url, model)。
    优先使用 VISION_API_KEY / VISION_BASE_URL / VISION_MODEL，
    其次回退到 ZHIPU_API_KEY / ZHIPU_BASE_URL，
    最后回退到 LLM_API_KEY / LLM_BASE_URL。
    """
    api_key = os.environ.get("VISION_API_KEY", "")
    base_url = os.environ.get("VISION_BASE_URL", "")
    model = os.environ.get("VISION_MODEL", "glm-5v-turbo")
    if api_key:
        return api_key, base_url.rstrip("/"), model


def get_image_config() -> tuple:
    """
    获取文生图 API 配置，返回 (api_key, model)。
    优先使用 IMAGE_API_KEY / IMAGE_MODEL，
    其次回退到 DASHSCOPE_API_KEY。
    """
    api_key = os.environ.get("IMAGE_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "")
    model = os.environ.get("IMAGE_MODEL", "z-image-turbo")

    if not api_key:
        print("错误: 未设置 IMAGE_API_KEY 或 DASHSCOPE_API_KEY 环境变量")
        print("请在 .env 文件中添加: IMAGE_API_KEY=your_dashscope_api_key")
        sys.exit(1)

    return api_key, model

    api_key = os.environ.get("ZHIPU_API_KEY", "")
    base_url = os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    if api_key:
        return api_key, base_url.rstrip("/"), model


def get_image_config() -> tuple:
    """
    获取文生图 API 配置，返回 (api_key, model)。
    优先使用 IMAGE_API_KEY / IMAGE_MODEL，
    其次回退到 DASHSCOPE_API_KEY。
    """
    api_key = os.environ.get("IMAGE_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "")
    model = os.environ.get("IMAGE_MODEL", "z-image-turbo")

    if not api_key:
        print("错误: 未设置 IMAGE_API_KEY 或 DASHSCOPE_API_KEY 环境变量")
        print("请在 .env 文件中添加: IMAGE_API_KEY=your_dashscope_api_key")
        sys.exit(1)

    return api_key, model

    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    if not api_key:
        print("错误: 未设置视觉 API 密钥")
        print("请在 .env 文件中添加 VISION_API_KEY 或 ZHIPU_API_KEY")
        sys.exit(1)

    return api_key, base_url.rstrip("/"), model


def get_image_config() -> tuple:
    """
    获取文生图 API 配置，返回 (api_key, model)。
    优先使用 IMAGE_API_KEY / IMAGE_MODEL，
    其次回退到 DASHSCOPE_API_KEY。
    """
    api_key = os.environ.get("IMAGE_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "")
    model = os.environ.get("IMAGE_MODEL", "z-image-turbo")

    if not api_key:
        print("错误: 未设置 IMAGE_API_KEY 或 DASHSCOPE_API_KEY 环境变量")
        print("请在 .env 文件中添加: IMAGE_API_KEY=your_dashscope_api_key")
        sys.exit(1)

    return api_key, model


def get_image_config() -> tuple:
    """
    获取文生图 API 配置，返回 (api_key, model)。
    优先使用 IMAGE_API_KEY / IMAGE_MODEL，
    其次回退到 DASHSCOPE_API_KEY。
    """
    api_key = os.environ.get("IMAGE_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "")
    model = os.environ.get("IMAGE_MODEL", "z-image-turbo")

    if not api_key:
        print("错误: 未设置 IMAGE_API_KEY 或 DASHSCOPE_API_KEY 环境变量")
        print("请在 .env 文件中添加: IMAGE_API_KEY=your_dashscope_api_key")
        sys.exit(1)

    return api_key, model
