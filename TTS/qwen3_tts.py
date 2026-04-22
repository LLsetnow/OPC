"""Qwen3-TTS 本地语音合成脚本

支持三种模型变体：
  - CustomVoice: 9 种预设音色 + 自然语言控制语气/情感
  - VoiceDesign: 用自然语言描述来设计全新音色
  - Base: 3 秒快速语音克隆（提供参考音频）

模型文件从本地 models/ 目录加载。
"""

import argparse
import os
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

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

def load_model(mode: str, device: str = "cuda:0", attn: str = "flash_attention_2"):
    """加载 Qwen3-TTS 模型"""
    import torch
    from qwen_tts import Qwen3TTSModel

    model_path = MODEL_PATHS.get(mode)
    if not model_path or not model_path.exists():
        print(f"错误: 模型路径不存在: {model_path}")
        print(f"可用模型: {', '.join(str(p.name) for p in MODELS_DIR.iterdir() if p.is_dir())}")
        sys.exit(1)

    # 检查 Tokenizer
    if not TOKENIZER_PATH.exists():
        print(f"错误: Tokenizer 不存在: {TOKENIZER_PATH}")
        sys.exit(1)

    print(f"加载模型: {model_path.name}")
    print(f"设备: {device}, 精度: bfloat16, 注意力: {attn}")

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

    print("模型加载完成")
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

    wavs, sr = model.generate_custom_voice(**kwargs)

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    sf.write(output_path, wavs[0], sr)
    file_size = os.path.getsize(output_path)
    print(f"语音生成完成: {output_path} ({file_size / 1024:.1f} KB)")


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

    wavs, sr = model.generate_voice_design(
        text=text,
        language=language,
        instruct=instruct,
    )

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    sf.write(output_path, wavs[0], sr)
    file_size = os.path.getsize(output_path)
    print(f"语音生成完成: {output_path} ({file_size / 1024:.1f} KB)")


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

    wavs, sr = model.generate_voice_clone(**kwargs)

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    sf.write(output_path, wavs[0], sr)
    file_size = os.path.getsize(output_path)
    print(f"语音生成完成: {output_path} ({file_size / 1024:.1f} KB)")


# ── CLI 入口 ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Qwen3-TTS 本地语音合成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 预设音色
  python qwen3_tts.py "你好，今天天气真不错" -m custom -s Vivian -o output.wav

  # 指令控制语气
  python qwen3_tts.py "你居然敢这样说我" -m custom -s Vivian --instruct "用特别愤怒的语气说"

  # 设计新音色
  python qwen3_tts.py "欢迎收听今天的节目" -m design --instruct "磁性低沉的男中音，播报风格" -o output.wav

  # 语音克隆
  python qwen3_tts.py "我是克隆的声音" -m base --ref-audio ref.wav --ref-text "参考音频的文字" -o output.wav

可用音色 (custom 模式):
  Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee

支持语言: Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian
        """,
    )

    parser.add_argument("text", help="要转换的文本")
    parser.add_argument("-o", "--output", default="output.wav", help="输出文件路径（默认: output.wav）")
    parser.add_argument(
        "-m", "--mode",
        choices=["custom", "design", "base"],
        default="custom",
        help="模型变体: custom=预设音色, design=设计音色, base=语音克隆（默认: custom）",
    )
    parser.add_argument("-s", "--speaker", default="Vivian", help="预设音色名称（custom 模式，默认: Vivian）")
    parser.add_argument("-l", "--language", default="Chinese", help="语言（默认: Chinese）")
    parser.add_argument("--instruct", default="", help="自然语言指令（custom 模式控制语气 / design 模式描述音色）")
    parser.add_argument("--ref-audio", help="参考音频路径（base 模式）")
    parser.add_argument("--ref-text", help="参考音频对应文本（base 模式，可选）")
    parser.add_argument("--device", default="cuda:0", help="设备（默认: cuda:0）")
    parser.add_argument("--attn", default="flash_attention_2", choices=["flash_attention_2", "sdpa", "eager"], help="注意力实现（默认: flash_attention_2）")
    parser.add_argument("--list-speakers", action="store_true", help="列出预设音色")

    args = parser.parse_args()

    # 列出音色
    if args.list_speakers:
        print("\n预设音色 (custom 模式):")
        print("-" * 50)
        for name, desc in PRESET_SPEAKERS.items():
            print(f"  {name:<12} {desc}")
        print()
        return

    # 参数校验
    if args.mode == "base" and not args.ref_audio:
        parser.error("base 模式需要 --ref-audio 参数")

    if args.mode == "design" and not args.instruct:
        parser.error("design 模式需要 --instruct 参数描述音色")

    # 加载模型
    model = load_model(args.mode, device=args.device, attn=args.attn)

    # 生成
    if args.mode == "custom":
        generate_custom_voice(
            model, args.text,
            speaker=args.speaker,
            language=args.language,
            instruct=args.instruct,
            output_path=args.output,
        )
    elif args.mode == "design":
        generate_voice_design(
            model, args.text,
            instruct=args.instruct,
            language=args.language,
            output_path=args.output,
        )
    elif args.mode == "base":
        generate_voice_clone(
            model, args.text,
            ref_audio=args.ref_audio,
            ref_text=args.ref_text or "",
            language=args.language,
            output_path=args.output,
        )


if __name__ == "__main__":
    main()
