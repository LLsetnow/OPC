"""Qwen3-TTS 本地语音合成

支持三种模型变体：
  - CustomVoice: 9 种预设音色 + 自然语言控制语气/情感
  - VoiceDesign: 用自然语言描述来设计全新音色
  - Base: 3 秒快速语音克隆（提供参考音频）

模型文件从本地 models/ 目录加载。
"""

import os
import sys
import time
from pathlib import Path

# 模型目录：优先读取环境变量 TTS_MODELS_DIR，否则自动检测
def _resolve_models_dir() -> Path:
    env = os.environ.get("TTS_MODELS_DIR")
    if env:
        return Path(env)
    # Windows 默认路径
    win_path = Path(r"D:\github\OPC\models")
    if win_path.exists():
        return win_path
    # WSL 映射路径
    wsl_path = Path("/mnt/d/github/OPC/models")
    if wsl_path.exists():
        return wsl_path
    # 项目相对路径
    rel_path = Path(__file__).resolve().parent.parent / "models"
    if rel_path.exists():
        return rel_path
    return win_path  # 兜底返回 Windows 路径

MODELS_DIR = _resolve_models_dir()

# ── 模型路径常量 ──────────────────────────────────────────────────

MODEL_PATHS = {
    "custom": MODELS_DIR / "Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "design": MODELS_DIR / "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "base": MODELS_DIR / "Qwen3-TTS-12Hz-1.7B-Base",
}

TOKENIZER_PATH = MODELS_DIR / "Qwen3-TTS-Tokenizer-12Hz"

# ── 预设音色 ──────────────────────────────────────────────────────

PRESET_SPEAKERS = {
    "Vivian": "明亮略带锋芒的年轻女声（中文）",
    "Serena": "温柔温暖的年轻女声（中文）",
    "Uncle_Fu": "沉稳醇厚的低音男声（中文）",
    "Dylan": "清爽自然的北京男声（中文·京腔）",
    "Eric": "活泼略带沙哑的成都男声（中文·川普）",
    "Ryan": "节奏感强的动感男声（英语）",
    "Aiden": "阳光清晰的美式男声（英语）",
    "Ono_Anna": "轻快俏皮的日系女声（日语）",
    "Sohee": "温暖富有情感的韩语女声（韩语）",
}

SUPPORTED_LANGUAGES = [
    "Chinese", "English", "Japanese", "Korean",
    "German", "French", "Russian", "Portuguese", "Spanish", "Italian",
]


# ── 模型加载 ──────────────────────────────────────────────────────

def is_model_available(mode: str) -> bool:
    """检查指定模式的本地模型文件是否存在"""
    model_path = MODEL_PATHS.get(mode)
    return bool(model_path and model_path.exists() and TOKENIZER_PATH.exists())


def load_model(mode: str, device: str = "cuda:0", attn: str = "sdpa"):
    """加载 Qwen3-TTS 模型。模型文件不存在时抛出 FileNotFoundError。"""
    import torch
    from qwen_tts import Qwen3TTSModel

    model_path = MODEL_PATHS.get(mode)
    if not model_path or not model_path.exists():
        available = [p.name for p in MODELS_DIR.iterdir() if p.is_dir()] if MODELS_DIR.exists() else []
        raise FileNotFoundError(
            f"模型路径不存在: {model_path}，可用模型: {', '.join(available) if available else '无'}"
        )

    if not TOKENIZER_PATH.exists():
        raise FileNotFoundError(f"Tokenizer 不存在: {TOKENIZER_PATH}")

    print(f"加载模型: {model_path.name}")
    print(f"设备: {device}, 精度: bfloat16, 注意力: {attn}")

    t0 = time.time()
    try:
        model = Qwen3TTSModel.from_pretrained(
            str(model_path),
            device_map=device,
            dtype=torch.bfloat16,
            attn_implementation=attn,
        )
    except Exception as e:
        if "flash_attention" in str(e).lower():
            print("FlashAttention 不可用，回退到 sdpa...")
            model = Qwen3TTSModel.from_pretrained(
                str(model_path),
                device_map=device,
                dtype=torch.bfloat16,
                attn_implementation="sdpa",
            )
        else:
            raise

    elapsed = time.time() - t0
    print(f"模型加载完成 (耗时: {elapsed:.1f}s)")
    return model


# ── CustomVoice 合成 ─────────────────────────────────────────────

def generate_custom_voice(
    model,
    text: str,
    speaker: str = "Vivian",
    language: str = "Chinese",
    instruct: str = "",
    output_path: str = "output.wav",
):
    """使用预设音色生成语音"""
    import soundfile as sf

    print(f"CustomVoice 合成: speaker={speaker}, language={language}")
    if instruct:
        print(f"  指令: {instruct}")

    kwargs = dict(
        text=text,
        language=language,
        speaker=speaker,
    )
    if instruct:
        kwargs["instruct"] = instruct

    t0 = time.time()
    wavs, sr = model.generate_custom_voice(**kwargs)
    gen_time = time.time() - t0

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    sf.write(output_path, wavs[0], sr)
    file_size = os.path.getsize(output_path)
    duration = len(wavs[0]) / sr
    print(f"语音生成完成: {output_path} ({file_size / 1024:.1f} KB, 音频时长: {duration:.1f}s, 生成耗时: {gen_time:.1f}s, RTF: {gen_time / duration:.2f})")


# ── VoiceDesign 合成 ─────────────────────────────────────────────

def generate_voice_design(
    model,
    text: str,
    instruct: str,
    language: str = "Chinese",
    output_path: str = "output.wav",
):
    """用自然语言描述设计音色并生成语音"""
    import soundfile as sf

    print(f"VoiceDesign 合成: language={language}")
    print(f"  音色描述: {instruct}")

    t0 = time.time()
    wavs, sr = model.generate_voice_design(
        text=text,
        language=language,
        instruct=instruct,
    )
    gen_time = time.time() - t0

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    sf.write(output_path, wavs[0], sr)
    file_size = os.path.getsize(output_path)
    duration = len(wavs[0]) / sr
    print(f"语音生成完成: {output_path} ({file_size / 1024:.1f} KB, 音频时长: {duration:.1f}s, 生成耗时: {gen_time:.1f}s, RTF: {gen_time / duration:.2f})")


# ── Voice Clone 合成 ─────────────────────────────────────────────

def generate_voice_clone(
    model,
    text: str,
    ref_audio: str,
    ref_text: str = "",
    language: str = "Chinese",
    output_path: str = "output.wav",
):
    """3 秒快速语音克隆"""
    import soundfile as sf

    if not os.path.exists(ref_audio):
        print(f"错误: 参考音频不存在: {ref_audio}")
        sys.exit(1)

    print(f"Voice Clone 合成: language={language}")
    print(f"  参考音频: {ref_audio}")
    if ref_text:
        print(f"  参考文本: {ref_text}")

    kwargs = dict(
        text=text,
        language=language,
        ref_audio=ref_audio,
    )
    if ref_text:
        kwargs["ref_text"] = ref_text

    t0 = time.time()
    wavs, sr = model.generate_voice_clone(**kwargs)
    gen_time = time.time() - t0

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    sf.write(output_path, wavs[0], sr)
    file_size = os.path.getsize(output_path)
    duration = len(wavs[0]) / sr
    print(f"语音生成完成: {output_path} ({file_size / 1024:.1f} KB, 音频时长: {duration:.1f}s, 生成耗时: {gen_time:.1f}s, RTF: {gen_time / duration:.2f})")


# ── 音色列表 ──────────────────────────────────────────────────────

def list_speakers() -> dict:
    """返回预设音色字典"""
    return dict(PRESET_SPEAKERS)


# ── 文本分块（用于流式 TTS） ──────────────────────────────────────

import re

def split_text_to_chunks(text: str, max_chars: int = 30) -> list[str]:
    """将文本拆分为适合流式 TTS 的短句块。

    按标点层级逐步拆分：强标点（句号等）→ 逗号/顿号 → 空格。
    每个分隔符处都独立拆分，以加速流式首包响应。
    """
    text = text.strip()
    if not text:
        return []

    # ── 第一步：按强标点拆分为句子 ──
    strong_parts = re.split(r'([。！？；\n.!?;])', text)
    sentences = []
    buf = ""
    for i in range(0, len(strong_parts), 2):
        sentence = strong_parts[i]
        delimiter = strong_parts[i + 1] if i + 1 < len(strong_parts) else ""
        buf += sentence + delimiter
        if delimiter or (i + 2 >= len(strong_parts)):
            if buf.strip():
                sentences.append(buf.strip())
            buf = ""

    if not sentences:
        return [text]

    # ── 第二步：按逗号/顿号拆分（每个逗号处独立拆分） ──
    comma_parts = []
    for s in sentences:
        if '，' not in s and '、' not in s and ',' not in s:
            comma_parts.append(s)
            continue
        parts = re.split(r'([，、,])', s)
        for i in range(0, len(parts), 2):
            seg = parts[i]
            sep = parts[i + 1] if i + 1 < len(parts) else ""
            chunk = (seg + sep).strip()
            if chunk:
                comma_parts.append(chunk)

    if not comma_parts:
        return [text]

    # ── 第三步：按空格拆分（每个空格处独立拆分） ──
    fine_parts = []
    for s in comma_parts:
        if ' ' not in s and '\t' not in s:
            fine_parts.append(s)
            continue
        space_parts = re.split(r'\s+', s)
        for seg in space_parts:
            if seg.strip():
                fine_parts.append(seg.strip())

    if not fine_parts:
        return [text]

    return fine_parts
