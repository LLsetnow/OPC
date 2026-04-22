"""GLM-TTS 语音合成 + 音色克隆"""

import os
import re
import struct
import sys
import uuid
from pathlib import Path

import requests

from .config import get_api_config


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
    """上传参考音频，创建克隆音色。返回克隆结果 dict"""
    file_id = upload_file(api_key, base_url, ref_audio_path, purpose="voice-clone-input")

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
    payload["request_id"] = f"req_{uuid.uuid4().hex[:12]}"

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
    """文本转语音。长文本（>1024字符）自动分段合成后拼接"""
    MAX_LEN = 1024
    if len(text) <= MAX_LEN:
        return _tts_single(api_key, base_url, text, voice, output_path, speed, volume, response_format, watermark)

    segments = _split_text(text, max_len=MAX_LEN)
    print(f"文本较长({len(text)}字)，分为 {len(segments)} 段合成")

    segment_files = []
    for i, seg in enumerate(segments):
        seg_path = output_path.replace(".wav", f"_part{i}.wav").replace(".mp3", f"_part{i}.mp3")
        print(f"  合成第 {i+1}/{len(segments)} 段: {seg[:30]}...")
        _tts_single(api_key, base_url, seg, voice, seg_path, speed, volume, response_format, watermark)
        segment_files.append(seg_path)

    _concat_wav_files(segment_files, output_path)

    for f in segment_files:
        try:
            os.remove(f)
        except OSError:
            pass

    file_size = os.path.getsize(output_path)
    print(f"语音拼接完成: {output_path} ({file_size / 1024:.1f} KB)")
    return output_path


def _split_text(text: str, max_len: int = 1024) -> list:
    """按标点符号将长文本分段"""
    sentences = re.split(r'([。！？\n])', text)
    segments = []
    current = ""
    for i, s in enumerate(sentences):
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
    audio_data = b""
    sample_rate = 24000
    channels = 1
    bits_per_sample = 16

    for f in wav_files:
        with open(f, "rb") as fh:
            data = fh.read()
            if data[:4] == b"RIFF" and len(data) > 44:
                if not audio_data:
                    channels = struct.unpack_from("<H", data, 22)[0]
                    sample_rate = struct.unpack_from("<I", data, 24)[0]
                    bits_per_sample = struct.unpack_from("<H", data, 34)[0]
                data_start = data.find(b"data")
                if data_start >= 0:
                    data_size = struct.unpack_from("<I", data, data_start + 4)[0]
                    audio_data += data[data_start + 8 : data_start + 8 + data_size]

    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(audio_data)
    file_size = 36 + data_size

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", file_size))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))
        f.write(struct.pack("<H", 1))
        f.write(struct.pack("<H", channels))
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", byte_rate))
        f.write(struct.pack("<H", block_align))
        f.write(struct.pack("<H", bits_per_sample))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(audio_data)


def _tts_single(
    api_key: str, base_url: str, text: str, voice: str, output_path: str,
    speed: float, volume: float, response_format: str, watermark: bool,
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
    return result.get("voice_list", [])
