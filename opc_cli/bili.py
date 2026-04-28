"""Bilibili 视频下载 + ASR 转写 + 内容总结"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .config import get_llm_config, get_asr_config


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

def _convert_to_wav(audio_path: str) -> str:
    """将音频转为 WAV 16k 单声道格式（fun-asr-realtime 要求 16kHz 采样率）"""
    ext = Path(audio_path).suffix.lower()

    # 即使是 wav，也要检查采样率是否为 16kHz，否则时间戳会出错
    if ext == ".wav":
        try:
            import wave as _wave
            with _wave.open(audio_path, "rb") as wf:
                sr = wf.getframerate()
                ch = wf.getnchannels()
            if sr == 16000 and ch == 1:
                return audio_path
            print(f"wav 采样率={sr}Hz 声道数={ch}，需转换为 16kHz 单声道")
        except Exception:
            pass  # 读取失败则继续走转换流程

    wav_path = str(Path(audio_path).with_suffix(".wav"))
    # 如果需要转换，不使用已有缓存（可能采样率不对）
    if ext == ".wav":
        # 输入是 wav 但采样率不对，用临时路径避免覆盖原文件
        wav_path = str(Path(audio_path).with_stem(Path(audio_path).stem + "_16k")) + ".wav"
    elif os.path.exists(wav_path):
        return wav_path

    print(f"将 {ext} 音频转换为 WAV 格式...")

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-vn", "-ar", "16000", "-ac", "1", wav_path],
            capture_output=True, check=True,
        )
        if os.path.exists(wav_path):
            return wav_path
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    try:
        import soundfile as sf
        import numpy as np
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


def asr_transcribe(audio_path: str, use_words: bool = True) -> dict:
    """使用阿里云 DashScope fun-asr-realtime 进行语音识别

    基于 DashScope SDK 的 Recognition.call() 非流式接口，
    支持本地文件直接识别，返回带精确时间戳的结果。

    Args:
        use_words: 是否提取词级时间戳（asr 命令用 True，bili 命令用 False）
    """
    import dashscope
    from dashscope.audio.asr import Recognition
    from http import HTTPStatus

    api_key, asr_model = get_asr_config()
    dashscope.api_key = api_key
    dashscope.base_websocket_api_url = 'wss://dashscope.aliyuncs.com/api-ws/v1/inference'

    print(f"使用模型 {asr_model} 进行语音识别（阿里云 DashScope）...")

    # 转换为 wav 16kHz（fun-asr-realtime 要求 16kHz 采样率）
    audio_path = _convert_to_wav(audio_path)

    # 创建 Recognition 实例并调用非流式识别
    recognition = Recognition(
        model=asr_model,
        format="wav",
        sample_rate=16000,
        callback=None,
    )

    result = recognition.call(audio_path)

    if result.status_code != HTTPStatus.OK:
        raise RuntimeError(f"ASR 识别失败: {result.message}")

    # 解析结果
    return _parse_recognition_result(result, use_words=use_words)


def llm_fix_asr_text(raw_text: str) -> str:
    """使用 LLM 修复 ASR 文本中的同音字/近音字和错字错误

    只修正错字，不改变断词和文本结构，以保留精确的时间戳映射。
    """
    from openai import OpenAI

    api_key, base_url, llm_model = get_llm_config()
    if not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = f"""你是一个 ASR（语音识别）文本校对专家。以下是一段语音识别的原始输出，ASR 模型存在同音字/近音字识别错误，需要根据上下文语义纠正。

**重要约束**：
- 只修正同音字、近音字和明显的错字，不要改变断词、语序或文本结构
- 保留原有的所有标点符号（句号、逗号等），不要增删或移动标点
- 修正后文本的字符数必须与原文相同（逐字替换，不增不减）
- 如果某个字不需要修正，保持原样即可

常见同音/近音错误示例：
- "几干" → "几千"
- "5干度" → "5千度"
- "近视温度" → "近似温度"
- "密的" → "密得"

直接输出修正后的文本，不要添加任何解释。

--- 原始 ASR 文本 ---

{raw_text}"""

    response = client.chat.completions.create(
        model=llm_model,
        messages=[
            {"role": "system", "content": "你是一个 ASR 文本校对专家，只修正同音字/近音字和错字，不改变断词、标点和文本结构。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=4096,
    )

    corrected = response.choices[0].message.content
    if not corrected:
        print("警告: LLM 修复返回为空，使用原始文本")
        return raw_text

    corrected = corrected.strip()
    print(f"LLM 文本修复完成: 原始 {len(raw_text)} 字 → 修正 {len(corrected)} 字")
    return corrected


def resegment_asr(asr_result: dict, llm_fix: bool = False) -> dict:
    """后处理：将 ASR 片段按自然语句重新切分

    优先使用词级时间戳（words）进行精确映射，退回到段落级线性插值。
    如果使用 LLM 修正了文本，则按总时长比例估算时间。
    """
    segments = asr_result.get("segments", [])
    if not segments:
        return asr_result

    # 1. 合并所有片段文本，构建词级时间线（比段落级更精确）
    full_text = ""
    # word_boundaries: [(char_start, char_end, start_sec, end_sec), ...]
    word_boundaries = []
    has_words = False

    for seg in segments:
        start_idx = len(full_text)
        text = seg.get("text", "").strip()
        if not text:
            continue
        full_text += text

        seg_start_sec = _time_to_seconds(seg.get("start", "00:00:00.000"))
        seg_end_sec = _time_to_seconds(seg.get("end", "00:00:00.000"))

        words = seg.get("words", [])
        if words:
            has_words = True
            # 检查词文本拼接是否与段文本一致
            concatenated = "".join(w.get("text", "") for w in words)

            if concatenated == text:
                # 完美匹配：精确词级字符偏移
                w_offset = 0
                for w in words:
                    w_text = w.get("text", "")
                    w_len = len(w_text)
                    word_boundaries.append((
                        start_idx + w_offset,
                        start_idx + w_offset + w_len,
                        w["start_sec"],
                        w["end_sec"],
                    ))
                    w_offset += w_len
            else:
                # 词文本与段文本不完全匹配（可能含标点差异）
                # 按词字符数比例分配段内字符位置
                total_word_chars = sum(len(w.get("text", "")) for w in words)
                if total_word_chars > 0:
                    w_offset = 0
                    for w in words:
                        w_text = w.get("text", "")
                        w_len = len(w_text)
                        char_start = start_idx + int(w_offset / total_word_chars * len(text))
                        char_end = start_idx + int((w_offset + w_len) / total_word_chars * len(text))
                        # 确保最后一个词覆盖到段末尾
                        if w == words[-1]:
                            char_end = start_idx + len(text)
                        word_boundaries.append((char_start, char_end, w["start_sec"], w["end_sec"]))
                        w_offset += w_len
                else:
                    word_boundaries.append((start_idx, start_idx + len(text), seg_start_sec, seg_end_sec))
        else:
            # 无词级数据：退回到段落级边界
            word_boundaries.append((start_idx, start_idx + len(text), seg_start_sec, seg_end_sec))

    if not word_boundaries:
        return asr_result

    # 2. 可选：LLM 修复合并后的文本（修复断词、误加标点等）
    if llm_fix:
        print("使用 LLM 修复 ASR 文本...")
        corrected_text = llm_fix_asr_text(full_text)
    else:
        corrected_text = full_text

    # 3. 按逗号逐句切分，每小句独立成段
    SENTENCE_END = r'[。！？!?]'
    COMMA = r'[，,；;：:]'

    # 先按句号切分出完整句子
    raw_sentences = re.split(f'(?<={SENTENCE_END})', corrected_text)
    raw_sentences = [s.strip() for s in raw_sentences if s.strip()]

    # 再按逗号切分，每小句独立成段
    sentences = []
    for sent in raw_sentences:
        parts = re.split(f'(?<={COMMA})', sent)
        parts = [p.strip() for p in parts if p.strip()]
        for part in parts:
            # 去掉末尾的逗号/分号等
            part = re.sub(r'[，,；;：:]+$', '', part.strip())
            if not part:
                continue
            # 确保每小句以句号结尾
            if not re.search(r'[。！？!?]$', part):
                part += '。'
            sentences.append(part)

    if not sentences:
        return asr_result

    # 4. 根据字符位置映射时间戳（使用词级时间线，比段落级更精确）
    if has_words:
        print(f"使用词级时间戳映射（{len(word_boundaries)} 个词）")

    # 如果 LLM 修正了文本，建立 corrected→original 字符位置对齐
    char_map = None  # char_map[i] = corrected_text[i] 对应的 full_text 字符位置
    if llm_fix and corrected_text != full_text:
        from difflib import SequenceMatcher
        sm = SequenceMatcher(None, full_text, corrected_text, autojunk=False)
        char_map = {}
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                for k in range(j2 - j1):
                    char_map[j1 + k] = i1 + k
            elif tag == 'replace':
                # 替换：按顺序对齐，多余字符映射到最近的原始位置
                src_len = i2 - i1
                dst_len = j2 - j1
                for k in range(dst_len):
                    char_map[j1 + k] = i1 + min(k, src_len - 1)
            # delete: 原文有而修正文没有，跳过
            # insert: 修正文多出的字符，映射到前一个原始位置
            elif tag == 'insert':
                prev_orig = char_map.get(j1 - 1, i1)
                for k in range(j2 - j1):
                    char_map[j1 + k] = prev_orig
        print(f"LLM 修正后字符对齐: {len(char_map)} 个字符映射到原文")

    new_segments = []
    char_pos = 0

    for sent in sentences:
        sent_chars = len(sent)

        # 统一使用词级时间线映射，不再对 llm_fix 做比例估算
        if char_map is not None:
            # LLM 修正后：通过字符对齐映射回原文位置
            orig_start = char_map.get(char_pos, 0)
            orig_end = char_map.get(char_pos + sent_chars - 1, len(full_text) - 1)
            start_sec = _map_char_to_time(orig_start, word_boundaries)
            end_sec = _map_char_to_time(orig_end + 1, word_boundaries)
        else:
            # 使用词级时间线映射字符位置到时间
            start_sec = _map_char_to_time(char_pos, word_boundaries)
            end_sec = _map_char_to_time(char_pos + sent_chars, word_boundaries)

        # 确保结束时间 > 开始时间
        if end_sec <= start_sec:
            end_sec = start_sec + max(1.0, sent_chars * 0.15)

        new_segments.append({
            "start": _seconds_to_time(start_sec),
            "end": _seconds_to_time(end_sec),
            "text": sent,
        })
        char_pos += sent_chars

    return {
        "segments": new_segments,
        "raw_text": "".join(s["text"] for s in new_segments),
    }


def _map_char_to_time(char_idx: int, boundaries: list) -> float:
    """将字符位置映射到时间（线性插值）"""
    for start_char, end_char, start_sec, end_sec in boundaries:
        if start_char <= char_idx <= end_char:
            if end_char == start_char:
                return start_sec
            ratio = (char_idx - start_char) / (end_char - start_char)
            return start_sec + ratio * (end_sec - start_sec)
    # 超出范围，返回最后一个时间
    if boundaries:
        return boundaries[-1][3]
    return 0.0


def _time_to_seconds(ts: str) -> float:
    """将时间戳字符串转为秒数"""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return 0.0


def _seconds_to_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _parse_recognition_result(result, use_words: bool = True) -> dict:
    """解析 DashScope Recognition.call() 返回的结果

    RecognitionResult.get_sentence() 返回 dict:
    {"begin_time": ms, "end_time": ms, "text": "...", "words": [...]}
    非流式调用返回的是所有句子的 list。

    words 中每个词的格式:
    {"text": "词", "begin_time": ms, "end_time": ms}

    Args:
        use_words: 是否提取词级时间戳，False 则只保留段落级
    """
    sentence = result.get_sentence()
    segments = []

    # 非流式 call() 返回 list[sentence]
    if isinstance(sentence, list):
        sentences = sentence
    elif isinstance(sentence, dict) and "text" in sentence:
        sentences = [sentence]
    else:
        sentences = []

    for sent in sentences:
        begin_ms = sent.get("begin_time", 0)
        end_ms = sent.get("end_time", 0)
        text = sent.get("text", "").strip()
        if not text:
            continue

        start_sec = begin_ms / 1000.0
        end_sec = end_ms / 1000.0

        # 确保结束时间 > 开始时间
        if end_sec <= start_sec:
            end_sec = start_sec + max(1.0, len(text) * 0.15)

        # 提取词级时间戳（仅 asr 命令需要）
        words_data = []
        if use_words:
            for w in sent.get("words", []):
                w_text = w.get("text", "")
                w_begin_ms = w.get("begin_time", 0)
                w_end_ms = w.get("end_time", 0)
                if w_text:
                    w_start_sec = w_begin_ms / 1000.0
                    w_end_sec = w_end_ms / 1000.0
                    if w_end_sec <= w_start_sec:
                        w_end_sec = w_start_sec + max(0.1, len(w_text) * 0.1)
                    words_data.append({
                        "text": w_text,
                        "start_sec": w_start_sec,
                        "end_sec": w_end_sec,
                    })

        seg_dict = {
            "start": _seconds_to_time(start_sec),
            "end": _seconds_to_time(end_sec),
            "text": text,
        }
        if use_words:
            seg_dict["words"] = words_data
        segments.append(seg_dict)

    if not segments:
        print("警告: 未能解析出带时间戳的段落")
        return {"segments": [], "raw_text": ""}

    raw_text = "".join(s["text"] for s in segments)
    return {"segments": segments, "raw_text": raw_text}


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

    # 在 output_dir 及其子目录中搜索（优先取最新修改的文件）
    json_files = list(Path(output_dir).rglob("*.asr.json"))
    if json_files:
        latest = max(json_files, key=os.path.getmtime)
        with open(str(latest), "r", encoding="utf-8") as f:
            result = json.load(f)
        if "segments" in result:
            print(f"从 ASR JSON 文件加载: {latest}")
            return result

    srt_files = list(Path(output_dir).rglob("*.srt"))
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

    # 匹配被反引号包裹的时间戳范围，如 `[00:01:35]-[00:06:20]` 或 `[00:01:35]`
    # 先处理反引号内的范围
    def replace_backtick_range(match):
        inner = match.group(1)
        # 逐个替换内部的时间戳
        return re.sub(r'\[(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?)\]', replace_timestamp, inner)

    result = re.sub(r'`(\[[\d:.\-\]]+\])`', replace_backtick_range, md_content)
    # 再处理未被反引号包裹的裸时间戳
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
    llm_fix: bool = False,
):
    """B站视频转写主流程

    自动检测：确定了视频目录后，若该目录下已有字幕文件则自动跳过 ASR。
    """
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    audio_exts = {".m4a", ".mp3", ".wav", ".ogg", ".opus", ".webm", ".mp4"}

    # Step 1: 下载音频
    if skip_download:
        if audio_file:
            audio_path = os.path.abspath(audio_file)
        else:
            # 在 output_dir 中搜索音频文件
            audio_files = []
            for ext in audio_exts:
                audio_files.extend(Path(output_dir).glob(f"*{ext}"))
                if not audio_files:
                    audio_files.extend(Path(output_dir).rglob(f"*{ext}"))
            if not audio_files:
                print(f"错误: 未找到音频文件，请在 --output-dir ({output_dir}) 中放入音频文件，或使用 --audio-file 指定")
                sys.exit(1)
            # 选最新修改的文件
            audio_path = str(max(audio_files, key=os.path.getmtime))
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

    # ── 自动检测：该视频目录下是否已有字幕文件 ──
    if not skip_asr and not asr_file:
        json_path = os.path.join(video_dir, f"{audio_base}.asr.json")
        srt_path = os.path.join(video_dir, f"{audio_base}.srt")
        if os.path.exists(json_path):
            print(f"检测到已有字幕文件: {json_path}")
            print("自动跳过 ASR（如需重新识别请删除该文件）")
            skip_asr = True
            asr_file = json_path
        elif os.path.exists(srt_path):
            print(f"检测到已有字幕文件: {srt_path}")
            print("自动跳过 ASR（如需重新识别请删除该文件）")
            skip_asr = True
            asr_file = srt_path

    # Step 2: ASR 或加载已有结果
    if skip_asr:
        asr_result = load_asr_result(video_dir, audio_base=audio_base, asr_file=asr_file)
        if not asr_result:
            print("错误: 未找到可用的字幕文件，请使用 --asr-file 指定")
            sys.exit(1)
    else:
        asr_result = asr_transcribe(audio_path, use_words=False)

        # 自动重断句
        asr_result = resegment_asr(asr_result, llm_fix=llm_fix)

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
