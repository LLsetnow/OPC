#!/usr/bin/env python3
"""
GLM-TTS 语音合成脚本

支持两种模式：
  1. 普通合成 (--no-clone)：使用预设音色将文本转为语音
  2. 音色克隆 (--clone)：上传参考音频，克隆音色后生成语音(大小限制不超过10M，建议音频时长在3秒到30秒之间)

环境变量：
  ZHIPU_API_KEY   - 智谱 API Key（必填）
  ZHIPU_BASE_URL  - API Base URL（默认 https://open.bigmodel.cn/api/paas/v4）

示例：
  # 普通合成（默认音色 彤彤）
  python glm_tts.py "你好，今天天气真不错" -o output.wav

  # 指定音色
  python glm_tts.py "你好，今天天气真不错" -o output.wav --voice xiaochen

  # 音色克隆
  python glm_tts.py "你好，我是克隆的声音" -o output.wav --clone --ref-audio ref.wav

  # 克隆时提供参考文本
  python glm_tts.py "你好，我是克隆的声音" -o output.wav --clone --ref-audio ref.wav --ref-text "这是参考音频的文字"

  # 使用已克隆的音色 ID 直接生成
  python glm_tts.py "你好" -o output.wav --voice voice_clone_20240315_143052_001
"""

import argparse
import os
import sys
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv


# ── 环境配置 ────────────────────────────────────────────────────────

def load_env(env_file: str = None):
    """加载 .env 文件和环境变量"""
    if env_file and os.path.exists(env_file):
        load_dotenv(env_file)
    else:
        # 尝试当前目录和项目根目录
        for p in [".env", os.path.join(os.path.dirname(__file__), "..", ".env")]:
            if os.path.exists(p):
                load_dotenv(p)
                break


def get_api_config():
    """获取 API 配置"""
    api_key = os.environ.get("ZHIPU_API_KEY", "")
    base_url = os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")

    if not api_key:
        print("错误: 未设置 ZHIPU_API_KEY 环境变量")
        print("请在 .env 文件中添加: ZHIPU_API_KEY=your_api_key")
        sys.exit(1)

    return api_key, base_url.rstrip("/")


# ── 文件上传 ────────────────────────────────────────────────────────

def upload_file(api_key: str, base_url: str, file_path: str, purpose: str = "voice-clone-input") -> str:
    """上传文件到智谱平台，返回 file_id"""
    url = f"{base_url}/files"
    headers = {"Authorization": f"Bearer {api_key}"}

    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f)}
        data = {"purpose": purpose}

        resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
        resp.raise_for_status()
        result = resp.json()

    file_id = result.get("id", "")
    print(f"文件上传成功: {file_id} ({os.path.basename(file_path)})")
    return file_id


# ── 音色克隆 ────────────────────────────────────────────────────────

def clone_voice(
    api_key: str,
    base_url: str,
    ref_audio_path: str,
    voice_name: str = None,
    ref_text: str = "",
    sample_text: str = "",
) -> dict:
    """
    音色克隆：上传参考音频，创建克隆音色。

    返回: {"voice": "voice_clone_xxx", "file_id": "file_xxx", ...}
    """
    # Step 1: 上传参考音频
    file_id = upload_file(api_key, base_url, ref_audio_path, purpose="voice-clone-input")

    # Step 2: 调用音色复刻接口
    url = f"{base_url}/voice/clone"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if not voice_name:
        voice_name = f"clone_{uuid.uuid4().hex[:8]}"

    payload = {
        "model": "glm-tts-clone",
        "voice_name": voice_name,
        "file_id": file_id,
        "input": sample_text or "欢迎使用音色复刻服务。",
    }
    if ref_text:
        payload["text"] = ref_text

    request_id = f"req_{uuid.uuid4().hex[:12]}"
    payload["request_id"] = request_id

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    result = resp.json()

    cloned_voice = result.get("voice", "")
    print(f"音色克隆成功: voice_id={cloned_voice}, voice_name={voice_name}")
    return result


# ── 文本转语音 ──────────────────────────────────────────────────────

def text_to_speech(
    api_key: str,
    base_url: str,
    text: str,
    voice: str = "tongtong",
    output_path: str = "output.wav",
    speed: float = 1.0,
    volume: float = 1.0,
    response_format: str = "wav",
    watermark: bool = False,
) -> str:
    """
    文本转语音：使用 GLM-TTS 模型将文本转为语音文件。

    支持系统预设音色和克隆音色。
    长文本（>1024字符）会自动分段合成后拼接。
    """
    # 检查文本长度，超过 1024 字符需分段
    MAX_LEN = 1024
    if len(text) <= MAX_LEN:
        return _tts_single(
            api_key, base_url, text, voice, output_path, speed, volume, response_format, watermark,
        )

    # 长文本分段：按句号/问号/叹号/换行分割
    segments = _split_text(text, max_len=MAX_LEN)
    print(f"文本较长({len(text)}字)，分为 {len(segments)} 段合成")

    # 逐段合成
    segment_files = []
    for i, seg in enumerate(segments):
        seg_path = output_path.replace(".wav", f"_part{i}.wav").replace(".mp3", f"_part{i}.mp3")
        print(f"  合成第 {i+1}/{len(segments)} 段: {seg[:30]}...")
        _tts_single(api_key, base_url, seg, voice, seg_path, speed, volume, response_format, watermark)
        segment_files.append(seg_path)

    # 拼接音频文件
    _concat_wav_files(segment_files, output_path)

    # 清理临时文件
    for f in segment_files:
        try:
            os.remove(f)
        except OSError:
            pass

    file_size = os.path.getsize(output_path)
    print(f"语音拼接完成: {output_path} ({file_size / 1024:.1f} KB)")
    return output_path


def _split_text(text: str, max_len: int = 1024) -> list:
    """按标点符号将长文本分段，每段不超过 max_len"""
    # 按句子分割
    import re
    sentences = re.split(r'([。！？\n])', text)

    segments = []
    current = ""
    for i, s in enumerate(sentences):
        # 标点符号附加到前一句
        if i % 2 == 1 and s in "。！？\n":
            current += s
        else:
            if len(current) + len(s) > max_len and current:
                segments.append(current.strip())
                current = s
            else:
                current += s

    if current.strip():
        segments.append(current.strip())

    return segments if segments else [text]


def _concat_wav_files(wav_files: list, output_path: str):
    """拼接多个 WAV 文件"""
    import struct

    # 读取所有 WAV 数据（跳过头部）
    audio_data = b""
    sample_rate = 24000
    channels = 1
    bits_per_sample = 16

    for f in wav_files:
        with open(f, "rb") as fh:
            data = fh.read()
            # 解析 WAV 头获取参数
            if data[:4] == b"RIFF" and len(data) > 44:
                # 从第一个文件获取音频参数
                if not audio_data:
                    channels = struct.unpack_from("<H", data, 22)[0]
                    sample_rate = struct.unpack_from("<I", data, 24)[0]
                    bits_per_sample = struct.unpack_from("<H", data, 34)[0]
                # 找到 data chunk
                data_start = data.find(b"data")
                if data_start >= 0:
                    data_size = struct.unpack_from("<I", data, data_start + 4)[0]
                    audio_data += data[data_start + 8 : data_start + 8 + data_size]

    # 写入新 WAV
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(audio_data)
    file_size = 36 + data_size

    with open(output_path, "wb") as f:
        # WAV header
        f.write(b"RIFF")
        f.write(struct.pack("<I", file_size))
        f.write(b"WAVE")
        # fmt chunk
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))  # chunk size
        f.write(struct.pack("<H", 1))   # PCM format
        f.write(struct.pack("<H", channels))
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", byte_rate))
        f.write(struct.pack("<H", block_align))
        f.write(struct.pack("<H", bits_per_sample))
        # data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(audio_data)


def _tts_single(
    api_key: str,
    base_url: str,
    text: str,
    voice: str,
    output_path: str,
    speed: float,
    volume: float,
    response_format: str,
    watermark: bool,
) -> str:
    """单次 TTS 请求"""
    url = f"{base_url}/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "glm-tts",
        "input": text,
        "voice": voice,
        "speed": speed,
        "volume": volume,
        "response_format": response_format,
        "watermark_enabled": watermark,
    }

    print(f"正在生成语音: voice={voice}, text={text[:50]}...")
    resp = requests.post(url, headers=headers, json=payload, timeout=120)

    if resp.status_code != 200:
        try:
            error = resp.json()
            print(f"错误: {error.get('error', {}).get('message', resp.text)}")
        except Exception:
            print(f"错误: HTTP {resp.status_code} - {resp.text[:200]}")
        sys.exit(1)

    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "wb") as f:
        f.write(resp.content)

    file_size = os.path.getsize(output_path)
    print(f"语音生成完成: {output_path} ({file_size / 1024:.1f} KB)")
    return output_path


# ── 音色列表 ────────────────────────────────────────────────────────

def list_voices(api_key: str, base_url: str, voice_type: str = None) -> list:
    """获取可用音色列表"""
    url = f"{base_url}/voice/list"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {}
    if voice_type:
        params["voiceType"] = voice_type

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    result = resp.json()

    voices = result.get("voice_list", [])
    return voices


# ── 主流程 ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="GLM-TTS 语音合成（支持普通合成和音色克隆）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  # 普通合成（默认音色 彤彤）
  python glm_tts.py "你好，今天天气真不错" -o output.wav

  # 指定音色
  python glm_tts.py "你好" -o output.wav --voice xiaochen

  # 音色克隆
  python glm_tts.py "我是克隆的声音" -o output.wav --clone --ref-audio ref.wav

  # 列出可用音色
  python glm_tts.py --list-voices
""",
    )

    parser.add_argument("text", nargs="?", help="要转换为语音的文本")
    parser.add_argument("-o", "--output", default="output.wav", help="输出音频文件路径（默认: output.wav）")
    parser.add_argument("--env-file", default=None, help=".env 文件路径")

    # 音色选择
    parser.add_argument(
        "--voice",
        default="tongtong",
        help="音色名称。系统音色: tongtong(彤彤), xiaochen(小陈), chuichui(锤锤), jam, kazi, douji, luodo；或已克隆的音色 ID（默认: tongtong）",
    )

    # 音色克隆
    parser.add_argument("--clone", action="store_true", help="使用音色克隆模式")
    parser.add_argument("--ref-audio", help="克隆参考音频文件路径（与 --clone 配合使用）")
    parser.add_argument("--ref-text", default="", help="参考音频对应的文本内容（可选）")
    parser.add_argument("--voice-name", default=None, help="克隆音色名称（可选，默认自动生成）")

    # TTS 参数
    parser.add_argument("--speed", type=float, default=1.0, help="语速 [0.5, 2]（默认: 1.0）")
    parser.add_argument("--volume", type=float, default=1.0, help="音量 (0, 10]（默认: 1.0）")
    parser.add_argument("--format", choices=["wav", "pcm"], default="wav", help="音频输出格式（默认: wav）")
    parser.add_argument(
        "--watermark", action="store_true",
        help="添加 AI 生成水印（默认关闭，开启后音频开头会有提示音）",
    )

    # 工具
    parser.add_argument("--list-voices", action="store_true", help="列出可用音色")
    parser.add_argument("--list-clone-voices", action="store_true", help="列出已克隆的音色")

    args = parser.parse_args()

    # 加载环境变量
    load_env(args.env_file)
    api_key, base_url = get_api_config()

    # 列出音色
    if args.list_voices:
        voices = list_voices(api_key, base_url)
        print("\n系统音色:")
        print(f"  {'音色 ID':<30} {'名称':<20} {'类型':<10}")
        print("  " + "-" * 60)
        for v in voices:
            if v.get("voice_type") == "OFFICIAL":
                print(f"  {v.get('voice', ''):<30} {v.get('voice_name', ''):<20} {v.get('voice_type', ''):<10}")
        return

    if args.list_clone_voices:
        voices = list_voices(api_key, base_url, voice_type="PRIVATE")
        if not voices:
            print("暂无克隆音色")
            return
        print("\n已克隆音色:")
        print(f"  {'音色 ID':<40} {'名称':<20} {'创建时间':<20}")
        print("  " + "-" * 80)
        for v in voices:
            print(f"  {v.get('voice', ''):<40} {v.get('voice_name', ''):<20} {v.get('create_time', ''):<20}")
        return

    # 检查文本参数
    if not args.text:
        parser.error("请提供要转换的文本，或使用 --list-voices 查看可用音色")

    voice = args.voice

    # 音色克隆模式
    if args.clone:
        if not args.ref_audio:
            parser.error("克隆模式需要指定 --ref-audio 参考音频文件")

        if not os.path.exists(args.ref_audio):
            print(f"错误: 参考音频文件不存在: {args.ref_audio}")
            sys.exit(1)

        # 检查文件格式
        ext = Path(args.ref_audio).suffix.lower()
        if ext not in (".mp3", ".wav"):
            print(f"错误: 参考音频格式不支持: {ext}，仅支持 mp3 和 wav")
            sys.exit(1)

        # 检查文件大小（10MB 限制）
        file_size = os.path.getsize(args.ref_audio)
        if file_size > 10 * 1024 * 1024:
            print(f"错误: 参考音频文件过大: {file_size / 1024 / 1024:.1f}MB，最大支持 10MB")
            sys.exit(1)

        print(f"=== 音色克隆模式 ===")
        print(f"参考音频: {args.ref_audio} ({file_size / 1024:.1f} KB)")
        if args.ref_text:
            print(f"参考文本: {args.ref_text}")

        # 执行克隆
        clone_result = clone_voice(
            api_key,
            base_url,
            ref_audio_path=args.ref_audio,
            voice_name=args.voice_name,
            ref_text=args.ref_text,
            sample_text=args.text,
        )
        voice = clone_result.get("voice", "")
        if not voice:
            print("错误: 克隆失败，未获取到音色 ID")
            sys.exit(1)
        print(f"使用克隆音色: {voice}")

    # 文本转语音
    text_to_speech(
        api_key,
        base_url,
        text=args.text,
        voice=voice,
        output_path=args.output,
        speed=args.speed,
        volume=args.volume,
        response_format=args.format,
        watermark=args.watermark,
    )


if __name__ == "__main__":
    main()
