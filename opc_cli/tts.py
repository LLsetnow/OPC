"""GLM-TTS 语音合成 + 音色克隆"""

import os
import re
import struct
import sys
import time
import uuid
from pathlib import Path

import requests

from .config import get_api_config, get_qwen_tts_config


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
    engine: str = "glm-tts",
) -> str:
    """文本转语音。长文本（>1024字符）自动分段合成后拼接。
    
    engine: "glm-tts" 使用智谱 API，"qwen-tts" 使用阿里云 CosyVoice API。
    """
    if engine == "qwen-tts":
        return _text_to_speech_qwen(text, voice, output_path, speed, response_format)

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


# ── Qwen TTS（阿里云 CosyVoice） ──────────────────────────────────

# CosyVoice 预设音色（按模型版本分组）
QWEN_TTS_VOICES_V2 = {
    # cosyvoice-v2 音色
    "longxiaochun_v2": "龙小淳（知性积极女）",
    "longlaotie_v2": "龙老铁（东北直率男）",
    "longshuo_v2": "龙硕（博才干练男）",
    "longyue_v2": "龙悦（温暖磁性女）",
    "longshu_v2": "龙书（沉稳青年男）",
    "longjing_v2": "龙婧（典型播音女）",
    "longmiao_v2": "龙妙（抑扬顿挫女）",
    "longfei_v2": "龙飞（热血磁性男）",
    "longhua_v2": "龙华（元气甜美女）",
    "longxiaoxia_v2": "龙小夏（沉稳权威女）",
    "longyumi_v2": "YUMI（正经青年女）",
    "longxiaocheng_v2": "龙小诚（磁性低音男）",
    "longfeifei_v2": "龙菲菲（甜美娇气女）",
    "longzhe_v2": "龙哲（呆板大暖男）",
    "longze_v2": "龙泽（温暖元气男）",
    "longyan_v2": "龙颜（温暖春风女）",
    "longtian_v2": "龙天（磁性理智男）",
    "longhao_v2": "龙浩（多情忧郁男）",
    "longxing_v2": "龙星（温婉邻家女）",
    "longwan_v2": "龙婉（积极知性女）",
    "longcheng_v2": "龙橙（智慧青年男）",
    "longqiang_v2": "龙嫱（浪漫风情女）",
    "longhan_v2": "龙寒（温暖痴情男）",
}

# cosyvoice-v3-flash / v3-plus 系统音色（每个模型仅支持自己的音色，不可混用）
QWEN_TTS_VOICES_V3 = {
    # 标杆音色（支持 Instruct）
    "longanyang": "龙安洋（阳光大男孩）",
    "longanhuan": "龙安欢（欢脱元气女）",
    # 童声
    "longhuhu_v3": "龙呼呼（天真烂漫女童）",
    "longpaopao_v3": "龙泡泡（飞天泡泡音）",
    "longjielidou_v3": "龙杰力豆（阳光顽皮男）",
    "longxian_v3": "龙仙（豪放可爱女）",
    "longling_v3": "龙铃（稚气呆板女）",
    "longshanshan_v3": "龙闪闪（戏剧化童声）",
    "longniuniu_v3": "龙牛牛（阳光男童声）",
    # 语音助手
    "longxiaochun_v3": "龙小淳（知性积极女）",
    "longxiaoxia_v3": "龙小夏（沉稳权威女）",
    "longyumi_v3": "YUMI（正经青年女）",
    "longanyun_v3": "龙安昀（居家暖男）",
    "longanwen_v3": "龙安温（优雅知性女）",
    "longanli_v3": "龙安莉（利落从容女）",
    "longanlang_v3": "龙安朗（清爽利落男）",
    "longyingmu_v3": "龙应沐（优雅知性女）",
    # 社交陪伴
    "longantai_v3": "龙安台（嗲甜台湾女）",
    "longhua_v3": "龙华（元气甜美女）",
    "longcheng_v3": "龙橙（智慧青年男）",
    "longze_v3": "龙泽（温暖元气男）",
    "longzhe_v3": "龙哲（呆板大暖男）",
    "longyan_v3": "龙颜（温暖春风女）",
    "longxing_v3": "龙星（温婉邻家女）",
    "longtian_v3": "龙天（磁性理智男）",
    "longwan_v3": "龙婉（细腻柔声女）",
    "longqiang_v3": "龙嫱（浪漫风情女）",
    "longfeifei_v3": "龙菲菲（甜美娇气女）",
    "longhao_v3": "龙浩（多情忧郁男）",
    "longanrou_v3": "龙安柔（温柔闺蜜女）",
    "longhan_v3": "龙寒（温暖痴情男）",
    "longanzhi_v3": "龙安智（睿智轻熟男）",
    "longanling_v3": "龙安灵（思维灵动女）",
    "longanya_v3": "龙安雅（高雅气质女）",
    "longanqin_v3": "龙安亲（亲和活泼女）",
    # 有声书
    "longmiao_v3": "龙妙（抑扬顿挫女）",
    "longsanshu_v3": "龙三叔（沉稳质感男）",
    "longyuan_v3": "龙媛（温暖治愈女）",
    "longyue_v3": "龙悦（温暖磁性女）",
    "longxiu_v3": "龙修（博才说书男）",
    "longnan_v3": "龙楠（睿智青年男）",
    "longwanjun_v3": "龙婉君（细腻柔声女）",
    "longyichen_v3": "龙逸尘（洒脱活力男）",
    "longlaobo_v3": "龙老伯（沧桑岁月爷）",
    "longlaoyi_v3": "龙老姨（烟火从容阿姨）",
    # 方言
    "longjiaxin_v3": "龙嘉欣（优雅粤语女）",
    "longjiayi_v3": "龙嘉怡（知性粤语女）",
    "longanyue_v3": "龙安粤（欢脱粤语男）",
    "longlaotie_v3": "龙老铁（东北直率男）",
    "longshange_v3": "龙陕哥（原味陕北男）",
    "longanmin_v3": "龙安闽（清纯萝莉女）",
    # 诗词朗诵
    "longfei_v3": "龙飞（热血磁性男）",
    # 客服
    "longyingxiao_v3": "龙应笑（清甜推销女）",
    "longyingxun_v3": "龙应询（年轻青涩男）",
    "longyingjing_v3": "龙应静（低调冷静女）",
    "longyingling_v3": "龙应聆（温和共情女）",
    "longyingtao_v3": "龙应桃（温柔淡定女）",
    # 新闻播报
    "longshuo_v3": "龙硕（博才干练男）",
    "longshu_v3": "龙书（沉稳青年男）",
    "loongbella_v3": "Bella3.0（精准干练女）",
    # 直播带货
    "longanran_v3": "龙安燃（活泼质感女）",
    "longanxuan_v3": "龙安宣（经典直播女）",
}

# cosyvoice-v3.5-flash / v3.5-plus 无系统音色，仅支持复刻/设计音色

# 兼容旧代码：按模型版本分组
QWEN_TTS_VOICES = {**QWEN_TTS_VOICES_V2, **QWEN_TTS_VOICES_V3}

# 模型→系统音色映射（每个模型只能用自己的音色）
QWEN_TTS_VOICES_BY_MODEL = {
    "cosyvoice-v2": QWEN_TTS_VOICES_V2,
    "cosyvoice-v3-flash": QWEN_TTS_VOICES_V3,
    "cosyvoice-v3-plus": QWEN_TTS_VOICES_V3,
    "cosyvoice-v3.5-flash": {},  # 无系统音色
    "cosyvoice-v3.5-plus": {},   # 无系统音色
}


def _text_to_speech_qwen(
    text: str,
    voice: str = "longhuhu_v3",
    output_path: str = "output.wav",
    speed: float = 1.0,
    response_format: str = "wav",
) -> str:
    """使用阿里云 CosyVoice（HTTP REST API）进行语音合成"""
    MAX_LEN = 20000  # DashScope 支持最长 20000 字符
    if len(text) <= MAX_LEN:
        return _tts_single_qwen_http(text, voice, output_path, speed, response_format)

    # 超长文本分段
    segments = _split_text(text, max_len=MAX_LEN)
    print(f"文本较长({len(text)}字)，分为 {len(segments)} 段合成 (Qwen TTS)")

    segment_files = []
    for i, seg in enumerate(segments):
        ext = os.path.splitext(output_path)[1] or ".wav"
        seg_path = output_path.replace(ext, f"_part{i}{ext}")
        print(f"  合成第 {i+1}/{len(segments)} 段: {seg[:30]}...")
        _tts_single_qwen_http(seg, voice, seg_path, speed, response_format)
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


def _tts_single_qwen_http(
    text: str, voice: str, output_path: str,
    speed: float, response_format: str,
) -> str:
    """单次 Qwen TTS 请求（HTTP REST API，非流式）"""
    import requests as _requests
    import base64

    api_key, model = get_qwen_tts_config()

    print(f"正在生成语音 (Qwen TTS): voice={voice}, model={model}, text={text[:50]}...")
    t0 = time.time()

    url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "input": {
            "text": text,
            "voice": voice,
            "format": response_format,
            "sample_rate": 24000,
            "rate": speed,
        },
    }

    resp = _requests.post(url, headers=headers, json=body, timeout=120)
    if resp.status_code != 200:
        print(f"错误: Qwen TTS HTTP {resp.status_code}: {resp.text[:200]}")
        sys.exit(1)

    result = resp.json()

    # 检查错误
    err_code = result.get("code", "")
    err_msg = result.get("message", "")
    if err_code and err_code != "Success":
        print(f"错误: Qwen TTS {err_code}: {err_msg}")
        sys.exit(1)

    # 非流式返回 URL
    audio_info = result.get("output", {}).get("audio", {})
    audio_url = audio_info.get("url", "")

    if audio_url:
        audio_resp = _requests.get(audio_url, timeout=120)
        audio_data = audio_resp.content
    else:
        # 尝试从 data 字段获取 base64
        audio_b64 = audio_info.get("data", "")
        if audio_b64:
            audio_data = base64.b64decode(audio_b64)
        else:
            print("错误: Qwen TTS 未返回音频数据")
            sys.exit(1)

    gen_time = time.time() - t0

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "wb") as f:
        f.write(audio_data)

    # 计算 RTF
    duration = _get_wav_duration(audio_data)
    rtf = gen_time / duration if duration > 0 else 0
    file_size = os.path.getsize(output_path)
    print(f"语音生成完成: {output_path} ({file_size / 1024:.1f} KB, 音频时长: {duration:.1f}s, 生成耗时: {gen_time:.1f}s, RTF: {rtf:.2f})")
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


def _trim_wav_prefix(wav_data: bytes, trim_seconds: float = 2.0) -> bytes:
    """去除 WAV 数据前 trim_seconds 秒的音频（水印），返回新 WAV 字节"""
    if wav_data[:4] != b"RIFF" or len(wav_data) <= 44:
        return wav_data

    channels = struct.unpack_from("<H", wav_data, 22)[0]
    sample_rate = struct.unpack_from("<I", wav_data, 24)[0]
    bits_per_sample = struct.unpack_from("<H", wav_data, 34)[0]
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8

    # 找到 data chunk
    data_pos = wav_data.find(b"data")
    if data_pos < 0:
        return wav_data
    data_size = struct.unpack_from("<I", wav_data, data_pos + 4)[0]
    audio_start = data_pos + 8
    audio_end = audio_start + data_size

    # 计算要跳过的字节数
    trim_bytes = int(byte_rate * trim_seconds)
    if trim_bytes >= data_size:
        return wav_data  # 全部裁掉则保留原样

    new_audio = wav_data[audio_start + trim_bytes:audio_end]
    new_data_size = len(new_audio)

    # 重建 WAV
    header = bytearray(wav_data[:audio_start])
    # 修正 data size
    struct.pack_into("<I", header, data_pos + 4, new_data_size)
    # 修正 RIFF size
    struct.pack_into("<I", header, 4, 36 + new_data_size)

    return bytes(header) + new_audio


def _get_wav_duration(wav_data: bytes) -> float:
    """从 WAV 字节中获取音频时长（秒）。
    优先用实际数据长度计算，因为流式 WAV 的 header data_size 可能是预估值（不准确）。
    """
    if wav_data[:4] != b"RIFF" or len(wav_data) <= 44:
        return 0.0
    sample_rate = struct.unpack_from("<I", wav_data, 24)[0]
    bits_per_sample = struct.unpack_from("<H", wav_data, 34)[0]
    channels = struct.unpack_from("<H", wav_data, 22)[0]
    byte_rate = sample_rate * channels * bits_per_sample // 8
    if byte_rate == 0:
        return 0.0
    data_pos = wav_data.find(b"data")
    if data_pos < 0:
        return 0.0
    # 用实际数据长度而非 header 中的 data_size（流式 WAV 的 data_size 可能是占位值）
    actual_data_len = len(wav_data) - (data_pos + 8)
    header_data_size = struct.unpack_from("<I", wav_data, data_pos + 4)[0]
    # 取较小值：header 声明的大小 vs 实际数据大小
    data_size = min(actual_data_len, header_data_size) if header_data_size > 0 else actual_data_len
    return data_size / byte_rate
    if byte_rate == 0:
        return 0.0
    data_pos = wav_data.find(b"data")
    if data_pos < 0:
        return 0.0
    data_size = struct.unpack_from("<I", wav_data, data_pos + 4)[0]
    return data_size / byte_rate


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
    t0 = time.time()
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    gen_time = time.time() - t0

    if resp.status_code != 200:
        try:
            error = resp.json()
            err_msg = error.get("message", "") or error.get("error", {}).get("message", resp.text[:200])
            print(f"错误: {err_msg}")
        except Exception:
            print(f"错误: HTTP {resp.status_code} - {resp.text[:200]}")
        sys.exit(1)

    audio_data = resp.content

    # 去除前 2 秒水印（仅 WAV 格式）
    if response_format == "wav" and len(audio_data) > 44:
        audio_data = _trim_wav_prefix(audio_data, trim_seconds=2.0)

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "wb") as f:
        f.write(audio_data)

    # 计算 RTF
    duration = _get_wav_duration(audio_data)
    rtf = gen_time / duration if duration > 0 else 0
    file_size = os.path.getsize(output_path)
    print(f"语音生成完成: {output_path} ({file_size / 1024:.1f} KB, 音频时长: {duration:.1f}s, 生成耗时: {gen_time:.1f}s, RTF: {rtf:.2f})")
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
