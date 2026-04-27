"""Bilibili 视频下载 + ASR 转写 + 内容总结"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .config import get_api_config, get_llm_config


# ── Step 1: 下载 Bilibili 音频 ────────────────────────────────────

def download_audio(url: str, output_dir: str, cookies: str = None) -> str:
    """使用 yt-dlp 从 Bilibili 下载音频，返回音频文件路径"""
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("正在安装 yt-dlp...")
        subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)

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
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
    print(f"视频标题: {title}")
    print(f"UP主: {info.get('uploader', 'unknown')}")
    print(f"时长: {info.get('duration_string', 'unknown')}")

    has_ffmpeg = False
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        has_ffmpeg = True
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("警告: 未找到 ffmpeg，将以原始格式下载音频")

    output_template = os.path.join(output_dir, f"{safe_title}.%(ext)s")

    if has_ffmpeg:
        dl_cmd = [
            "yt-dlp", "-f", "bestaudio/best", "-x",
            "--audio-format", "m4a", "--audio-quality", "0",
            "-o", output_template, "--no-playlist",
        ]
    else:
        dl_cmd = [
            "yt-dlp", "-f", "bestaudio/best",
            "-o", output_template, "--no-playlist", "--remux-video", "mp4",
        ]

    if cookies:
        dl_cmd += ["--cookies", cookies]
    dl_cmd.append(url)

    print("下载音频...")
    result = subprocess.run(dl_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if not has_ffmpeg:
            print("remux 失败，尝试直接下载原始音频流...")
            dl_cmd = ["yt-dlp", "-f", "bestaudio/best", "-o", output_template, "--no-playlist"]
            if cookies:
                dl_cmd += ["--cookies", cookies]
            dl_cmd.append(url)
            result = subprocess.run(dl_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"下载音频失败: {result.stderr}")

    audio_path = None
    for ext in ["m4a", "mp3", "webm", "opus", "wav", "ogg", "mp4"]:
        candidate = os.path.join(output_dir, f"{safe_title}.{ext}")
        if os.path.exists(candidate):
            audio_path = candidate
            break

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
    """将音频转为 MP3 格式（ASR 仅支持 wav/mp3）"""
    ext = Path(audio_path).suffix.lower()
    if ext == ".mp3":
        return audio_path

    mp3_path = str(Path(audio_path).with_suffix(".mp3"))
    if os.path.exists(mp3_path):
        return mp3_path

    print(f"将 {ext} 音频转换为 MP3 格式...")

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-vn", "-ar", "16000", "-ac", "1", "-b:a", "128k", mp3_path],
            capture_output=True, check=True,
        )
        if os.path.exists(mp3_path):
            return mp3_path
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    try:
        import soundfile as sf
        import numpy as np
        wav_path = str(Path(audio_path).with_suffix(".wav"))
        wav, sr = sf.read(audio_path, dtype="float32")
        if wav.ndim > 1:
            wav = np.mean(wav, axis=1)
        sf.write(wav_path, wav, sr)
        if os.path.exists(wav_path):
            return wav_path
    except ImportError:
        pass
    except Exception as e:
        print(f"soundfile 转换失败: {e}")

    raise RuntimeError("无法转换音频格式，请安装 ffmpeg 或 soundfile")


def _split_audio(audio_path: str, chunk_duration: int = 25) -> list:
    """将音频按指定时长分片"""
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
    """调用 ASR API"""
    for attempt in range(1, max_retries + 1):
        try:
            with open(audio_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(model=asr_model, file=audio_file)

            if hasattr(response, 'choices') and response.choices:
                return response.choices[0].message.content
            elif hasattr(response, 'text'):
                return response.text
            return str(response)
        except Exception as e:
            if attempt < max_retries:
                print(f"  ASR 请求失败（第 {attempt} 次）: {e}")
                time.sleep(attempt * 3)
            else:
                raise


def asr_transcribe(audio_path: str) -> dict:
    """使用 GLM-ASR 进行语音识别"""
    try:
        from zhipuai import ZhipuAI
    except ImportError:
        print("正在安装 zhipuai 包...")
        subprocess.run([sys.executable, "-m", "pip", "install", "zhipuai"], check=True)
        from zhipuai import ZhipuAI

    api_key = os.environ.get("ZHIPU_API_KEY")
    asr_model = os.environ.get("ASR_MODEL", "glm-asr-2512")

    if not api_key:
        raise ValueError("未设置 ZHIPU_API_KEY 环境变量")

    audio_path = _convert_to_mp3(audio_path)
    client = ZhipuAI(api_key=api_key)
    print(f"使用模型 {asr_model} 进行语音识别...")

    chunks = _split_audio(audio_path, chunk_duration=25)

    if isinstance(chunks[0], str):
        result_text = _call_asr_api(client, asr_model, chunks[0])
        return _parse_asr_result(result_text)

    all_segments = []
    for i, (chunk_path, offset) in enumerate(chunks):
        print(f"识别分片 {i + 1}/{len(chunks)}（偏移 {offset:.1f}s）...")
        chunk_text = _call_asr_api(client, asr_model, chunk_path)
        print(f"  结果: {chunk_text[:100]}...")
        sub_segments = _split_text_to_segments(chunk_text, offset, chunk_duration=25)
        all_segments.extend(sub_segments)
        try:
            os.remove(chunk_path)
        except OSError:
            pass

    full_text = " ".join(seg["text"] for seg in all_segments if seg["text"])
    return {"segments": all_segments, "raw_text": full_text}


def _split_text_to_segments(text: str, offset: float, chunk_duration: int = 25) -> list:
    """将文本按句子切分为带估算时间戳的 segment"""
    sentences = re.split(r'(?<=[。！？!?])', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return []

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


def _seconds_to_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _parse_asr_result(text: str) -> dict:
    """解析 ASR 返回结果"""
    segments = []

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

    if not segments:
        pattern = r'\[?(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*[-—>]+\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})\]?\s*(.+)'
        for line in text.strip().split("\n"):
            m = re.match(pattern, line.strip())
            if m:
                segments.append({
                    "start": m.group(1).replace(",", "."),
                    "end": m.group(2).replace(",", "."),
                    "text": m.group(3).strip(),
                })

    if not segments:
        pattern2 = r'(\d{2}:\d{2}:\d{2})\s*[-—>]+\s*(\d{2}:\d{2}:\d{2})\s*(.+)'
        for line in text.strip().split("\n"):
            m = re.match(pattern2, line.strip())
            if m:
                segments.append({
                    "start": m.group(1) + ".000",
                    "end": m.group(2) + ".000",
                    "text": m.group(3).strip(),
                })

    if not segments:
        print("警告: 未能解析出带时间戳的段落，将整段文本作为一条记录")
        segments.append({"start": "00:00:00.000", "end": "99:99:99.000", "text": text.strip()})

    return {"segments": segments, "raw_text": text}


# ── Step 3: SRT 文件 ──────────────────────────────────────────────

def parse_srt(srt_path: str) -> dict:
    """从 SRT 文件解析出 segments"""
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    segments = []
    raw_lines = []
    blocks = re.split(r'\n\s*\n', content.strip())
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue
        time_line_idx = None
        for i, line in enumerate(lines):
            if '-->' in line:
                time_line_idx = i
                break
        if time_line_idx is None:
            continue
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

    return {"segments": segments, "raw_text": "\n".join(raw_lines)}


def load_asr_result(output_dir: str, audio_base: str = None, asr_file: str = None) -> dict:
    """从已有的 ASR JSON 或 SRT 文件加载转写结果"""
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

    json_files = list(Path(output_dir).glob("*.asr.json"))
    if json_files:
        latest = max(json_files, key=os.path.getmtime)
        with open(str(latest), "r", encoding="utf-8") as f:
            result = json.load(f)
        if "segments" in result:
            print(f"从 ASR JSON 文件加载: {latest}")
            return result

    srt_files = list(Path(output_dir).glob("*.srt"))
    if srt_files:
        latest = max(srt_files, key=os.path.getmtime)
        result = parse_srt(str(latest))
        print(f"从 SRT 文件加载: {latest}")
        return result

    return None


def generate_srt(asr_result: dict, output_path: str):
    """将 ASR 结果生成 SRT 字幕文件"""
    segments = asr_result.get("segments", [])
    if not segments:
        print("警告: 没有可用的字幕段落")
        return

    srt_lines = []
    for idx, seg in enumerate(segments, 1):
        text = seg.get("text", "").strip()
        if not text:
            continue
        start_srt = seg.get("start", "00:00:00.000").replace(".", ",")
        end_srt = seg.get("end", "00:00:00.000").replace(".", ",")
        srt_lines.extend([str(idx), f"{start_srt} --> {end_srt}", text, ""])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))
    print(f"SRT 字幕已保存: {output_path}")


# ── Step 4: 内容总结 ──────────────────────────────────────────────

def _timestamp_to_seconds(ts: str) -> int:
    ts = ts.strip().split(".")[0]
    parts = ts.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0


def _add_video_links(md_content: str, video_url: str) -> str:
    base_url = video_url.split("?")[0].split("#")[0]

    def replace_timestamp(match):
        ts = match.group(1)
        seconds = _timestamp_to_seconds(ts)
        return f"[{ts}]({base_url}?t={seconds})"

    result = re.sub(r'`\[(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?)\]`', replace_timestamp, md_content)
    result = re.sub(r'\[(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?)\](?!\()', replace_timestamp, result)
    return result


def summarize_content(asr_result: dict, video_title: str, output_path: str, video_url: str = ""):
    """使用 LLM 总结视频内容，生成 Markdown 文件"""
    from openai import OpenAI

    api_key, base_url, llm_model = get_llm_config()

    if not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    client = OpenAI(api_key=api_key, base_url=base_url)

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

    if video_url:
        summary = _add_video_links(summary, video_url)
        lines = summary.split("\n")
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("#"):
                insert_idx = i + 1
                break
        if insert_idx > 0:
            lines.insert(insert_idx, "")
            lines.insert(insert_idx + 1, f"> 🎬 视频链接: [{video_url}]({video_url})")
        summary = "\n".join(lines)

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"内容总结已保存: {output_path}")


# ── 主流程入口 ────────────────────────────────────────────────────

def run_bili(
    url: str,
    output_dir: str = "./output",
    cookies: str = None,
    audio_only: bool = False,
    skip_download: bool = False,
    audio_file: str = None,
    skip_asr: bool = False,
    asr_file: str = None,
):
    """B站视频转写主流程"""
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: 下载音频
    if skip_download:
        if audio_file:
            audio_path = os.path.abspath(audio_file)
        else:
            audio_files = list(Path(output_dir).glob("*.m4a"))
            if not audio_files:
                audio_files = list(Path(output_dir).glob("*.mp3"))
            if not audio_files:
                print("错误: 未找到音频文件，请使用 --audio-file 指定")
                sys.exit(1)
            audio_path = str(audio_files[0])
        print(f"使用已有音频文件: {audio_path}")
    else:
        cookies = cookies or os.environ.get("YT_DLP_COOKIES")
        audio_path = download_audio(url, output_dir, cookies=cookies)

    if audio_only:
        print("仅下载音频模式，跳过后续步骤")
        return audio_path

    # 创建视频同名子目录，将音频移入
    audio_base = Path(audio_path).stem
    video_dir = os.path.join(output_dir, audio_base)
    os.makedirs(video_dir, exist_ok=True)

    new_audio_path = os.path.join(video_dir, Path(audio_path).name)
    if audio_path != new_audio_path and os.path.exists(audio_path):
        import shutil
        shutil.move(audio_path, new_audio_path)
        print(f"音频已移至: {new_audio_path}")
    audio_path = new_audio_path

    # Step 2: ASR 或加载已有结果
    if skip_asr:
        asr_result = load_asr_result(video_dir, audio_base=audio_base, asr_file=asr_file)
        if not asr_result:
            print("错误: 未找到可用的字幕文件，请使用 --asr-file 指定")
            sys.exit(1)
    else:
        if not os.environ.get("ZHIPU_API_KEY"):
            print("错误: 未设置 ZHIPU_API_KEY 环境变量")
            sys.exit(1)
        asr_result = asr_transcribe(audio_path)

        srt_path = os.path.join(video_dir, f"{audio_base}.srt")
        generate_srt(asr_result, srt_path)

        raw_json_path = os.path.join(video_dir, f"{audio_base}.asr.json")
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(asr_result, f, ensure_ascii=False, indent=2)

    # Step 3: 总结
    md_path = os.path.join(video_dir, f"{audio_base}.md")
    summarize_content(asr_result, video_title=audio_base, output_path=md_path, video_url=url)

    print(f"\n===== 处理完成 =====")
    print(f"  输出目录: {video_dir}")
    print(f"  内容总结: {md_path}")
    return md_path
