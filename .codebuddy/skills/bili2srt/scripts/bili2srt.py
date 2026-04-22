#!/usr/bin/env python3
"""
Bilibili 视频音频提取 + ASR 语音转写 + 内容总结

流程:
1. 使用 yt-dlp 从 Bilibili 下载音频
2. 使用 GLM-ASR-2512 模型提取人声内容，生成 SRT 字幕
3. 使用 LLM 总结视频内容为 Markdown 文件（含时间线引用）

环境变量（从 .env 文件加载）:
- ZHIPU_API_KEY:      智谱AI API Key（必填）
- ZHIPU_BASE_URL:     智谱AI API Base URL（默认 https://open.bigmodel.cn/api/paas/v4）
- ASR_MODEL:          ASR 模型名称（默认 glm-asr-2512）
- LLM_MODEL:          用于总结的 LLM 模型名称（默认 glm-4-flash）
- YT_DLP_COOKIES:     yt-dlp cookies 文件路径（可选，用于需要登录的视频）
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# ── .env 加载 ─────────────────────────────────────────────────────

def load_env(env_path: str = ".env"):
    """从 .env 文件加载环境变量，不覆盖已存在的环境变量。"""
    env_file = Path(env_path)
    if not env_file.exists():
        return
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


# ── Step 1: 下载 Bilibili 音频 ────────────────────────────────────

def download_audio(url: str, output_dir: str, cookies: str = None) -> str:
    """使用 yt-dlp 从 Bilibili 下载音频，返回音频文件路径。"""
    # 确保 yt-dlp 已安装
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("正在安装 yt-dlp...")
        subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)

    # 先获取视频信息
    print(f"获取视频信息: {url}")
    info_cmd = ["yt-dlp", "--dump-json", "--no-playlist"]
    if cookies:
        info_cmd += ["--cookies", cookies]
    info_cmd.append(url)

    result = subprocess.run(info_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"获取视频信息失败: {result.stderr}")

    info = json.loads(result.stdout)
    title = info.get("title", "unknown")
    # 清理文件名中的非法字符
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
    print(f"视频标题: {title}")
    print(f"UP主: {info.get('uploader', 'unknown')}")
    print(f"时长: {info.get('duration_string', 'unknown')}")

    # 检测 ffmpeg 是否可用
    has_ffmpeg = False
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        has_ffmpeg = True
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("警告: 未找到 ffmpeg，将以原始格式下载音频（不进行格式转换）")

    output_template = os.path.join(output_dir, f"{safe_title}.%(ext)s")

    if has_ffmpeg:
        # 有 ffmpeg：提取音频并转为 m4a
        dl_cmd = [
            "yt-dlp",
            "-f", "bestaudio/best",
            "-x", "--audio-format", "m4a",
            "--audio-quality", "0",
            "-o", output_template,
            "--no-playlist",
        ]
    else:
        # 无 ffmpeg：直接下载最佳音频流，不做后处理转换
        dl_cmd = [
            "yt-dlp",
            "-f", "bestaudio/best",
            "-o", output_template,
            "--no-playlist",
            "--remux-video", "mp4",  # 尝试 remux 而非 ffmpeg 转码
        ]

    if cookies:
        dl_cmd += ["--cookies", cookies]
    dl_cmd.append(url)

    print("下载音频...")
    result = subprocess.run(dl_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # 如果带 remux 也失败了，尝试最简单的方式
        if not has_ffmpeg:
            print("remux 失败，尝试直接下载原始音频流...")
            dl_cmd = [
                "yt-dlp",
                "-f", "bestaudio/best",
                "-o", output_template,
                "--no-playlist",
            ]
            if cookies:
                dl_cmd += ["--cookies", cookies]
            dl_cmd.append(url)
            result = subprocess.run(dl_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"下载音频失败: {result.stderr}")

    # 查找下载的音频文件（优先 m4a，然后尝试其他格式）
    audio_path = None
    for ext in ["m4a", "mp3", "webm", "opus", "wav", "ogg", "mp4"]:
        candidate = os.path.join(output_dir, f"{safe_title}.{ext}")
        if os.path.exists(candidate):
            audio_path = candidate
            break

    # 如果按标题找不到，按修改时间在输出目录中找最新的音频文件
    if not audio_path:
        audio_exts = {".m4a", ".mp3", ".webm", ".opus", ".wav", ".ogg", ".mp4"}
        candidates = [
            str(f) for f in Path(output_dir).iterdir()
            if f.suffix.lower() in audio_exts
        ]
        if candidates:
            audio_path = max(candidates, key=os.path.getmtime)
            print(f"按修改时间匹配到音频文件: {audio_path}")

    if not audio_path:
        raise FileNotFoundError(f"找不到下载的音频文件，请检查 {output_dir} 目录")

    print(f"音频已保存: {audio_path}")
    return audio_path


# ── Step 2: ASR 语音识别 ──────────────────────────────────────────

def _convert_to_mp3(audio_path: str) -> str:
    """将音频文件转换为 MP3 格式（GLM-ASR 仅支持 wav/mp3）。

    优先使用 ffmpeg 转换；如无 ffmpeg，尝试用 Python 库（pydub/soundfile）。
    返回转换后的 mp3 文件路径；如果原始文件已是 mp3 则直接返回。
    """
    ext = Path(audio_path).suffix.lower()
    if ext == ".mp3":
        return audio_path

    mp3_path = str(Path(audio_path).with_suffix(".mp3"))
    if os.path.exists(mp3_path):
        print(f"已有 MP3 文件: {mp3_path}")
        return mp3_path

    print(f"将 {ext} 音频转换为 MP3 格式（ASR 仅支持 wav/mp3）...")

    # 方式1: ffmpeg
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-vn", "-ar", "16000", "-ac", "1", "-b:a", "128k", mp3_path],
            capture_output=True, check=True,
        )
        if os.path.exists(mp3_path):
            print(f"已转换: {mp3_path}")
            return mp3_path
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # 方式2: pydub
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(audio_path)
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(mp3_path, format="mp3", bitrate="128k")
        if os.path.exists(mp3_path):
            print(f"已转换（pydub）: {mp3_path}")
            return mp3_path
    except ImportError:
        pass
    except Exception as e:
        print(f"pydub 转换失败: {e}")

    # 方式3: soundfile + scipy（仅 wav 输出，然后无法转 mp3，但 ASR 也支持 wav）
    wav_path = str(Path(audio_path).with_suffix(".wav"))
    try:
        import soundfile as sf
        import numpy as np
        wav, sr = sf.read(audio_path, dtype="float32")
        if wav.ndim > 1:
            wav = np.mean(wav, axis=1)
        sf.write(wav_path, wav, sr)
        if os.path.exists(wav_path):
            print(f"已转换为 WAV: {wav_path}")
            return wav_path
    except ImportError:
        pass
    except Exception as e:
        print(f"soundfile 转换失败: {e}")

    raise RuntimeError(
        "无法将音频转换为 mp3/wav 格式。请安装以下任一工具：\n"
        "  1. ffmpeg: sudo apt install ffmpeg\n"
        "  2. pydub: pip install pydub (需要 ffmpeg)\n"
        "  3. soundfile: pip install soundfile"
    )


def _split_audio(audio_path: str, chunk_duration: int = 25) -> list:
    """将音频文件按指定时长（秒）分片，返回分片文件路径列表。

    使用 ffmpeg 进行分片；如不可用，尝试 pydub。
    """
    import soundfile as sf
    import numpy as np

    wav, sr = sf.read(audio_path, dtype="float32")
    if wav.ndim > 1:
        wav = np.mean(wav, axis=1)

    total_duration = len(wav) / sr
    print(f"音频总时长: {total_duration:.1f}s，分片大小: {chunk_duration}s")

    if total_duration <= chunk_duration:
        return [audio_path]

    chunk_paths = []
    chunk_samples = int(chunk_duration * sr)
    base = Path(audio_path).stem
    out_dir = Path(audio_path).parent

    for i, start in enumerate(range(0, len(wav), chunk_samples)):
        end = min(start + chunk_samples, len(wav))
        chunk = wav[start:end]
        offset = start / sr

        chunk_path = out_dir / f"{base}_chunk_{i:03d}.wav"
        sf.write(str(chunk_path), chunk, sr)
        chunk_paths.append((str(chunk_path), offset))

    print(f"已分为 {len(chunk_paths)} 个分片")
    return chunk_paths


def _call_asr_api(client, asr_model: str, audio_path: str, max_retries: int = 3) -> str:
    """调用智谱 ASR API 识别单个音频文件，返回转写文本。"""
    import time

    for attempt in range(1, max_retries + 1):
        try:
            with open(audio_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model=asr_model,
                    file=audio_file,
                )

            # 解析返回
            if hasattr(response, 'choices') and response.choices:
                return response.choices[0].message.content
            elif hasattr(response, 'text'):
                return response.text
            else:
                return str(response)

        except Exception as e:
            if attempt < max_retries:
                print(f"  ASR 请求失败（第 {attempt} 次）: {e}")
                print(f"  等待 {attempt * 3} 秒后重试...")
                time.sleep(attempt * 3)
            else:
                raise


def asr_transcribe(audio_path: str) -> dict:
    """使用 GLM-ASR-2512 模型进行语音识别，返回带时间戳的结果。

    GLM-ASR transcriptions API 单次请求限制 30 秒，
    长音频会被自动分片处理后合并。
    """
    try:
        from zhipuai import ZhipuAI
    except ImportError:
        print("正在安装 zhipuai 包...")
        subprocess.run([sys.executable, "-m", "pip", "install", "zhipuai"], check=True)
        from zhipuai import ZhipuAI

    api_key = os.environ.get("ZHIPU_API_KEY")
    asr_model = os.environ.get("ASR_MODEL", "glm-asr-2512")

    if not api_key:
        raise ValueError("未设置 ZHIPU_API_KEY 环境变量，请在 .env 文件中配置")

    # 确保音频格式为 wav 或 mp3
    audio_path = _convert_to_mp3(audio_path)

    client = ZhipuAI(api_key=api_key)
    print(f"使用模型 {asr_model} 进行语音识别...")

    # 分片处理
    chunks = _split_audio(audio_path, chunk_duration=25)

    if isinstance(chunks[0], str):
        # 短音频，无需分片
        result_text = _call_asr_api(client, asr_model, chunks[0])
        return parse_asr_result(result_text)

    # 长音频，逐片识别后合并
    all_segments = []
    for i, (chunk_path, offset) in enumerate(chunks):
        print(f"识别分片 {i + 1}/{len(chunks)}（偏移 {offset:.1f}s）...")
        chunk_text = _call_asr_api(client, asr_model, chunk_path)
        print(f"  结果: {chunk_text[:100]}...")

        # transcriptions API 不返回时间戳，用分片偏移估算
        # 将分片文本按句号等分段，均匀分配到分片时间范围内
        sub_segments = _split_text_to_segments(chunk_text, offset, chunk_duration=25)
        all_segments.extend(sub_segments)

        # 清理分片文件
        try:
            os.remove(chunk_path)
        except OSError:
            pass

    # 合并后的完整文本
    full_text = " ".join(seg["text"] for seg in all_segments if seg["text"])

    return {"segments": all_segments, "raw_text": full_text}


def _split_text_to_segments(text: str, offset: float, chunk_duration: int = 25) -> list:
    """将一段纯文本按句子切分为带估算时间戳的 segment 列表。

    由于 transcriptions API 不返回时间戳，
    根据文本长度均匀估算每个句子在分片内的时间分布。
    """
    # 按句号、问号、感叹号分句
    sentences = re.split(r'(?<=[。！？!?])', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return []

    # 按字符数均匀分配时间
    total_chars = sum(len(s) for s in sentences)
    segments = []
    current_time = offset

    for sent in sentences:
        char_ratio = len(sent) / total_chars if total_chars > 0 else 1 / len(sentences)
        duration = chunk_duration * char_ratio
        end_time = current_time + duration

        segments.append({
            "start": _seconds_to_time(current_time),
            "end": _seconds_to_time(end_time),
            "text": sent,
        })
        current_time = end_time

    return segments


def _time_to_seconds(time_str: str) -> float:
    """将 SRT 时间格式 (HH:MM:SS.mmm) 转为秒数。"""
    time_str = time_str.replace(",", ".")
    parts = time_str.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(time_str)


def _seconds_to_time(seconds: float) -> str:
    """将秒数转为 SRT 时间格式 (HH:MM:SS.mmm)。"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def parse_asr_result(text: str) -> dict:
    """解析 ASR 返回的结果，提取带时间戳的文本。"""
    # 尝试从返回文本中提取 JSON
    segments = []

    # 尝试解析 JSON 格式的返回
    json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if isinstance(data, list):
                segments = data
            elif isinstance(data, dict) and "segments" in data:
                segments = data["segments"]
        except json.JSONDecodeError:
            pass

    # 如果没有解析到 JSON，尝试按行解析带时间戳的文本
    if not segments:
        # 尝试匹配 "时间戳 文本" 格式
        # 例如: [00:00:01.000 -> 00:00:03.500] 你好世界
        pattern = r'\[?(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*[-—>]+\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})\]?\s*(.+)'
        for line in text.strip().split("\n"):
            m = re.match(pattern, line.strip())
            if m:
                segments.append({
                    "start": m.group(1).replace(",", "."),
                    "end": m.group(2).replace(",", "."),
                    "text": m.group(3).strip(),
                })

    # 如果还是没有解析到，尝试另一种格式
    if not segments:
        # 尝试匹配纯时间范围 + 文本
        pattern2 = r'(\d{2}:\d{2}:\d{2})\s*[-—>]+\s*(\d{2}:\d{2}:\d{2})\s*(.+)'
        for line in text.strip().split("\n"):
            m = re.match(pattern2, line.strip())
            if m:
                segments.append({
                    "start": m.group(1) + ".000",
                    "end": m.group(2) + ".000",
                    "text": m.group(3).strip(),
                })

    # 最后兜底：如果都没有解析到，将整段文本作为一个 segment
    if not segments:
        print("警告: 未能解析出带时间戳的段落，将整段文本作为一条记录")
        segments.append({
            "start": "00:00:00.000",
            "end": "99:99:99.000",
            "text": text.strip(),
        })

    return {"segments": segments, "raw_text": text}


# ── Step 3: 生成 SRT 文件 ────────────────────────────────────────

def parse_srt(srt_path: str) -> dict:
    """从 SRT 字幕文件解析出带时间戳的 segments，返回与 ASR 结果相同的格式。

    返回: {"segments": [...], "raw_text": "..."}
    """
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    segments = []
    raw_lines = []

    # SRT 格式: 序号 -> 时间轴 -> 文本 -> 空行
    blocks = re.split(r'\n\s*\n', content.strip())
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue

        # 查找时间行
        time_line_idx = None
        for i, line in enumerate(lines):
            if '-->' in line:
                time_line_idx = i
                break

        if time_line_idx is None:
            continue

        # 解析时间: HH:MM:SS,mmm --> HH:MM:SS,mmm
        time_match = re.match(
            r'(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})',
            lines[time_line_idx],
        )
        if not time_match:
            continue

        start = time_match.group(1).replace(",", ".")
        end = time_match.group(2).replace(",", ".")
        text = " ".join(lines[time_line_idx + 1:]).strip()

        if text:
            segments.append({"start": start, "end": end, "text": text})
            raw_lines.append(f"[{start}] {text}")

    raw_text = "\n".join(raw_lines)
    return {"segments": segments, "raw_text": raw_text}


def load_asr_result(output_dir: str, audio_base: str = None, asr_file: str = None) -> dict:
    """从已有的 ASR JSON 或 SRT 文件加载转写结果。

    优先级:
    1. 指定的 asr_file
    2. {audio_base}.asr.json
    3. {audio_base}.srt
    4. 在输出目录中查找最新的 .asr.json
    5. 在输出目录中查找最新的 .srt
    """
    # 尝试指定的文件
    if asr_file:
        asr_path = os.path.abspath(asr_file)
        if os.path.exists(asr_path):
            if asr_path.endswith(".json"):
                with open(asr_path, "r", encoding="utf-8") as f:
                    result = json.load(f)
                if "segments" in result:
                    print(f"从 ASR JSON 文件加载: {asr_path}")
                    return result
            elif asr_path.endswith(".srt"):
                result = parse_srt(asr_path)
                print(f"从 SRT 文件加载: {asr_path}")
                return result

    # 尝试按 audio_base 查找
    if audio_base:
        json_path = os.path.join(output_dir, f"{audio_base}.asr.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                result = json.load(f)
            if "segments" in result:
                print(f"从 ASR JSON 文件加载: {json_path}")
                return result

        srt_path = os.path.join(output_dir, f"{audio_base}.srt")
        if os.path.exists(srt_path):
            result = parse_srt(srt_path)
            print(f"从 SRT 文件加载: {srt_path}")
            return result

    # 在输出目录中查找最新的 asr.json
    json_files = list(Path(output_dir).glob("*.asr.json"))
    if json_files:
        latest = max(json_files, key=os.path.getmtime)
        with open(str(latest), "r", encoding="utf-8") as f:
            result = json.load(f)
        if "segments" in result:
            print(f"从 ASR JSON 文件加载: {latest}")
            return result

    # 在输出目录中查找最新的 srt
    srt_files = list(Path(output_dir).glob("*.srt"))
    if srt_files:
        latest = max(srt_files, key=os.path.getmtime)
        result = parse_srt(str(latest))
        print(f"从 SRT 文件加载: {latest}")
        return result

    return None

def generate_srt(asr_result: dict, output_path: str):
    """将 ASR 结果生成 SRT 字幕文件。"""
    segments = asr_result.get("segments", [])
    if not segments:
        print("警告: 没有可用的字幕段落")
        return

    srt_lines = []
    for idx, seg in enumerate(segments, 1):
        start = seg.get("start", "00:00:00.000")
        end = seg.get("end", "00:00:00.000")
        text = seg.get("text", "").strip()

        if not text:
            continue

        # SRT 时间格式: HH:MM:SS,mmm (用逗号代替点号)
        start_srt = start.replace(".", ",")
        end_srt = end.replace(".", ",")

        srt_lines.append(str(idx))
        srt_lines.append(f"{start_srt} --> {end_srt}")
        srt_lines.append(text)
        srt_lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))

    print(f"SRT 字幕已保存: {output_path}")


# ── Step 4: 总结视频内容 ──────────────────────────────────────────

def _timestamp_to_seconds(ts: str) -> int:
    """将时间戳 (HH:MM:SS.mmm / HH:MM:SS / MM:SS) 转为秒数。"""
    # 去除毫秒部分
    ts = ts.strip().split(".")[0]
    parts = ts.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0


def _add_video_links(md_content: str, video_url: str) -> str:
    """将 Markdown 中的时间戳 [HH:MM:SS] 或 [MM:SS] 转为可点击跳转的视频链接。

    支持以下格式:
    - [MM:SS] 或 [HH:MM:SS]
    - [HH:MM:SS.mmm]（带毫秒）
    - `[MM:SS]` 或 `[HH:MM:SS]`（被反引号包裹）

    已是 Markdown 链接的时间戳（如 [00:00:34](...)）不会被重复处理。
    """
    base_url = video_url.split("?")[0].split("#")[0]

    def replace_timestamp(match):
        ts = match.group(1)
        seconds = _timestamp_to_seconds(ts)
        return f"[{ts}]({base_url}?t={seconds})"

    # 先处理被反引号包裹的时间戳: `[HH:MM:SS.mmm]` -> [HH:MM:SS.mmm](url?t=X)
    result = re.sub(
        r'`\[(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?)\]`',
        replace_timestamp,
        md_content,
    )

    # 再处理未被反引号包裹且不是已有链接的时间戳
    # 使用 negative lookahead 排除 [MM:SS](...) 格式（即后面紧跟 ( 的情况）
    result = re.sub(
        r'\[(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?)\](?!\()',
        replace_timestamp,
        result,
    )

    return result


def summarize_content(asr_result: dict, video_title: str, output_path: str, video_url: str = ""):
    """使用 LLM 总结视频内容，生成 Markdown 文件。"""
    try:
        from openai import OpenAI
    except ImportError:
        from openai import OpenAI

    # LLM 使用独立的 API 配置（如未设置则回退到智谱配置）
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("ZHIPU_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL") or os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    llm_model = os.environ.get("LLM_MODEL", "glm-4-flash")

    if not api_key:
        raise ValueError("未设置 LLM_API_KEY 或 ZHIPU_API_KEY 环境变量")

    # 确保 base_url 以 /v1 结尾（OpenAI SDK 要求）
    if not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    client = OpenAI(api_key=api_key, base_url=base_url)

    # 构建带时间线的文本
    segments = asr_result.get("segments", [])
    transcript_lines = []
    for seg in segments:
        start = seg.get("start", "")
        text = seg.get("text", "").strip()
        if text:
            transcript_lines.append(f"[{start}] {text}")

    transcript = "\n".join(transcript_lines)

    prompt = f"""请根据以下视频的语音转写内容，写一篇结构化的内容总结，要求：

1. 使用 Markdown 格式
2. 标题使用视频标题: {video_title}
3. 包含以下部分：
   - **概述**: 用1-2段话总结视频的核心内容
   - **要点**: 提取3-5个关键要点，每个要点引用对应的视频时间线（格式如 `[MM:SS]`）
   - **详细内容**: 按照视频的逻辑顺序，分段总结内容，每段标注对应的时间范围
   - **结论**: 视频的最终结论或核心观点（如有）

4. 时间线引用格式: `[MM:SS]` 或 `[HH:MM:SS]`
5. 保持客观，不要添加转写中没有的内容

--- 视频转写内容 ---

{transcript}
"""

    print(f"使用模型 {llm_model} 生成内容总结...")

    response = client.chat.completions.create(
        model=llm_model,
        messages=[
            {"role": "system", "content": "你是一个专业的内容分析助手，擅长从视频转写文本中提取关键信息并生成结构化总结。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
    )

    summary = response.choices[0].message.content

    # 如果有视频链接，在开头添加链接并将时间戳转为可跳转链接
    if video_url:
        summary = _add_video_links(summary, video_url)
        # 在标题后添加视频链接
        lines = summary.split("\n")
        insert_idx = 0
        # 找到第一个标题行之后插入视频链接
        for i, line in enumerate(lines):
            if line.startswith("#"):
                insert_idx = i + 1
                break
        if insert_idx > 0:
            lines.insert(insert_idx, "")
            lines.insert(insert_idx + 1, f"> 🎬 视频链接: [{video_url}]({video_url})")
        summary = "\n".join(lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(summary)

    print(f"内容总结已保存: {output_path}")


# ── 主流程 ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Bilibili 视频音频提取 + ASR 转写 + 内容总结",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD"
  python bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD" -o ./output
  python bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD" --cookies cookies.txt
  python bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD" --skip-asr
  python bili2srt.py "https://www.bilibili.com/video/BV1xx411c7mD" --skip-asr --asr-file ./output/video.asr.json
        """,
    )
    parser.add_argument("url", help="Bilibili 视频链接")
    parser.add_argument("-o", "--output-dir", default="./output", help="输出目录（默认: ./output）")
    parser.add_argument("--cookies", help="yt-dlp cookies 文件路径（用于需要登录的视频）")
    parser.add_argument("--audio-only", action="store_true", help="仅下载音频，不进行 ASR")
    parser.add_argument("--skip-download", action="store_true", help="跳过下载，使用已有音频文件")
    parser.add_argument("--audio-file", help="指定已有的音频文件路径（与 --skip-download 配合使用）")
    parser.add_argument("--skip-asr", action="store_true", help="跳过 ASR，使用已有的字幕文件（.asr.json 或 .srt）生成总结")
    parser.add_argument("--asr-file", help="指定已有的 ASR JSON 或 SRT 文件路径（与 --skip-asr 配合使用）")
    parser.add_argument("--env-file", default=".env", help=".env 文件路径（默认: .env）")

    args = parser.parse_args()

    # 加载 .env
    load_env(args.env_file)

    # 创建输出目录
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: 下载音频
    if args.skip_download:
        if args.audio_file:
            audio_path = os.path.abspath(args.audio_file)
        else:
            # 尝试在输出目录中查找音频文件
            audio_files = list(Path(output_dir).glob("*.m4a"))
            if not audio_files:
                audio_files = list(Path(output_dir).glob("*.mp3"))
            if not audio_files:
                print("错误: 未找到音频文件，请使用 --audio-file 指定")
                sys.exit(1)
            audio_path = str(audio_files[0])
        print(f"使用已有音频文件: {audio_path}")
    else:
        cookies = args.cookies or os.environ.get("YT_DLP_COOKIES")
        audio_path = download_audio(args.url, output_dir, cookies=cookies)

    if args.audio_only:
        print("仅下载音频模式，跳过后续步骤")
        return

    # 获取视频标题（用于文件命名和总结）
    audio_base = Path(audio_path).stem

    # Step 2: ASR 语音识别 或 从已有文件加载
    if args.skip_asr:
        asr_result = load_asr_result(output_dir, audio_base=audio_base, asr_file=args.asr_file)
        if not asr_result:
            print("错误: 未找到可用的字幕文件（.asr.json 或 .srt），请使用 --asr-file 指定")
            sys.exit(1)
    else:
        # 检查 API Key
        if not os.environ.get("ZHIPU_API_KEY"):
            print("错误: 未设置 ZHIPU_API_KEY 环境变量")
            print("请在 .env 文件中添加: ZHIPU_API_KEY=your_api_key")
            sys.exit(1)

        asr_result = asr_transcribe(audio_path)

        # Step 3: 生成 SRT 文件
        srt_path = os.path.join(output_dir, f"{audio_base}.srt")
        generate_srt(asr_result, srt_path)

        # 保存原始 ASR 结果
        raw_json_path = os.path.join(output_dir, f"{audio_base}.asr.json")
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(asr_result, f, ensure_ascii=False, indent=2)

    # Step 4: 总结视频内容
    md_path = os.path.join(output_dir, f"{audio_base}.md")
    summarize_content(asr_result, video_title=audio_base, output_path=md_path, video_url=args.url)

    print("\n===== 处理完成 =====")
    print(f"  内容总结: {md_path}")


if __name__ == "__main__":
    main()
