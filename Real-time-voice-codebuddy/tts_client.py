"""CosyVoice TTS 流式合成 + 音色查询（独立实现）"""

import base64
import json
import struct
import time

import numpy as np
import requests

# ── 系统音色列表 ──────────────────────────────────────────────────

QWEN_TTS_VOICES_V2 = {
    "longxiaochun_v2": "龙小淳（知性积极女）",
    "longyue_v2": "龙悦（温暖磁性女）",
    "longjing_v2": "龙婧（典型播音女）",
    "longmiao_v2": "龙妙（抑扬顿挫女）",
    "longhua_v2": "龙华（元气甜美女）",
    "longxiaoxia_v2": "龙小夏（沉稳权威女）",
    "longyumi_v2": "YUMI（正经青年女）",
    "longfeifei_v2": "龙菲菲（甜美娇气女）",
    "longyan_v2": "龙颜（温暖春风女）",
    "longxing_v2": "龙星（温婉邻家女）",
    "longwan_v2": "龙婉（积极知性女）",
    "longqiang_v2": "龙嫱（浪漫风情女）",
}

QWEN_TTS_VOICES_V3 = {
    "longanhuan": "龙安欢（欢脱元气女）",
    "longhuhu_v3": "龙呼呼（天真烂漫女童）",
    "longpaopao_v3": "龙泡泡（飞天泡泡音）",
    "longxian_v3": "龙仙（豪放可爱女）",
    "longling_v3": "龙铃（稚气呆板女）",
    "longshanshan_v3": "龙闪闪（戏剧化童声）",
    "longxiaochun_v3": "龙小淳（知性积极女）",
    "longxiaoxia_v3": "龙小夏（沉稳权威女）",
    "longyumi_v3": "YUMI（正经青年女）",
    "longanwen_v3": "龙安温（优雅知性女）",
    "longanli_v3": "龙安莉（利落从容女）",
    "longyingmu_v3": "龙应沐（优雅知性女）",
    "longantai_v3": "龙安台（嗲甜台湾女）",
    "longhua_v3": "龙华（元气甜美女）",
    "longyan_v3": "龙颜（温暖春风女）",
    "longxing_v3": "龙星（温婉邻家女）",
    "longwan_v3": "龙婉（细腻柔声女）",
    "longqiang_v3": "龙嫱（浪漫风情女）",
    "longfeifei_v3": "龙菲菲（甜美娇气女）",
    "longanrou_v3": "龙安柔（温柔闺蜜女）",
    "longanling_v3": "龙安灵（思维灵动女）",
    "longanya_v3": "龙安雅（高雅气质女）",
    "longanqin_v3": "龙安亲（亲和活泼女）",
    "longmiao_v3": "龙妙（抑扬顿挫女）",
    "longyuan_v3": "龙媛（温暖治愈女）",
    "longyue_v3": "龙悦（温暖磁性女）",
    "longwanjun_v3": "龙婉君（细腻柔声女）",
    "longlaoyi_v3": "龙老姨（烟火从容阿姨）",
    "longjiaxin_v3": "龙嘉欣（优雅粤语女）",
    "longjiayi_v3": "龙嘉怡（知性粤语女）",
    "longanmin_v3": "龙安闽（清纯萝莉女）",
    "longyingxiao_v3": "龙应笑（清甜推销女）",
    "longyingjing_v3": "龙应静（低调冷静女）",
    "longyingling_v3": "龙应聆（温和共情女）",
    "longyingtao_v3": "龙应桃（温柔淡定女）",
    "loongbella_v3": "Bella3.0（精准干练女）",
    "longanran_v3": "龙安燃（活泼质感女）",
    "longanxuan_v3": "龙安宣（经典直播女）",
}

# ── 复刻音色显示名称映射（voice_id → 中文名）──────────────────────
VOICE_DISPLAY_NAMES = {
    "cosyvoice-v3.5-flash-bailian-c8b555002f404397863708adffdb6b12": "洛琪希",
    "cosyvoice-v3.5-flash-bailian-e2469654e48c44b7b5cdd9b05139e10d": "菲比",
}

QWEN_TTS_VOICES_BY_MODEL = {
    "cosyvoice-v2": QWEN_TTS_VOICES_V2,
    "cosyvoice-v3-flash": QWEN_TTS_VOICES_V3,
    "cosyvoice-v3-plus": QWEN_TTS_VOICES_V3,
    # v3.5 模型无系统音色，仅支持复刻/设计音色
    "cosyvoice-v3.5-flash": {},
    "cosyvoice-v3.5-plus": {},
}


# ── 音色查询 ──────────────────────────────────────────────────────

def list_voices(api_key: str, model: str = "") -> list[dict]:
    """获取可用音色列表（系统音色 + API 查询的复刻音色）"""
    voices = []
    seen = set()

    # 系统音色（严格按模型过滤）
    if model:
        sys_voices = QWEN_TTS_VOICES_BY_MODEL.get(model, {})
    else:
        sys_voices = {**QWEN_TTS_VOICES_V2, **QWEN_TTS_VOICES_V3}

    for vid, label in sys_voices.items():
        if vid not in seen:
            seen.add(vid)
            voices.append({"value": vid, "label": label, "type": "system"})

    # API 查询复刻音色（按 target_model 过滤）
    clone_voices = _query_clone_from_api(api_key)
    for v in clone_voices:
        target = v.get("target_model", "")
        vid = v.get("value", "")
        # 只包含匹配当前模型的克隆音色
        if not model or target == model:
            if vid not in seen:
                seen.add(vid)
                voices.append(v)

    return voices


def _query_clone_from_api(api_key: str) -> list[dict]:
    """从阿里云百炼 API 查询已创建的复刻/设计音色"""
    try:
        url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        all_voices = []
        page_index = 0
        while True:
            body = {
                "model": "voice-enrollment",
                "input": {
                    "action": "list_voice",
                    "page_size": 100,
                    "page_index": page_index,
                },
            }
            resp = requests.post(url, headers=headers, json=body, timeout=30)
            if resp.status_code != 200:
                break
            data = resp.json()
            voice_list = data.get("output", {}).get("voice_list", [])
            if not voice_list:
                break
            for v in voice_list:
                vid = v.get("voice_id", "")
                target = v.get("target_model", "")
                voice_name = v.get("voice_name", "")
                if v.get("status") != "OK" or not vid:
                    continue
                # 优先使用自定义映射名称，其次 voice_name，最后截取 id
                display_name = VOICE_DISPLAY_NAMES.get(vid) or (voice_name if voice_name else vid[:16])
                label = f"{display_name}（复刻-{target}）"
                all_voices.append({
                    "value": vid,
                    "label": label,
                    "target_model": target,
                    "type": "clone",
                })
            if len(voice_list) < 100:
                break
            page_index += 1
        return all_voices
    except Exception:
        return []


# ── 流式 TTS 合成 ──────────────────────────────────────────────────

def generate_tts_stream(
    text: str,
    voice: str,
    model: str,
    api_key: str,
    instruction: str = "",
    speed: float = 1.0,
):
    """
    CosyVoice SSE 流式合成生成器。
    Yields: (pcm_bytes: bytes, sample_rate: int, is_final: bool)
    """
    url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-SSE": "enable",
    }
    input_obj = {
        "text": text,
        "voice": voice,
        "format": "pcm",
        "sample_rate": 24000,
        "rate": speed,
    }
    if instruction:
        input_obj["instruction"] = instruction

    body = {"model": model, "input": input_obj}

    t0 = time.time()
    resp = requests.post(url, headers=headers, json=body, stream=True, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"TTS HTTP {resp.status_code}: {resp.text[:300]}")

    collected = bytearray()
    sample_rate = 24000

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data_str = line[5:].strip()
        if not data_str:
            continue
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        output = chunk.get("output", {})
        audio_info = output.get("audio", {})
        audio_b64 = audio_info.get("data", "")

        if audio_b64:
            audio_bytes = base64.b64decode(audio_b64)
            collected.extend(audio_bytes)
            # PCM int16 → float32
            pcm = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            yield (pcm.tobytes(), sample_rate, False)

        err_code = chunk.get("code", "")
        if err_code and err_code not in ("Success", ""):
            err_msg = chunk.get("message", "")
            raise RuntimeError(f"TTS error: {err_code} {err_msg}")

    if not collected:
        raise RuntimeError("TTS 未返回音频数据")

    yield (b"", sample_rate, True)


def _wav_chunk_to_pcm(wav_data: bytes):
    """将 WAV 字节转换为 float32 PCM 数组"""
    if wav_data[:4] != b"RIFF" or len(wav_data) <= 44:
        sr = 24000
        pcm = np.frombuffer(wav_data, dtype=np.int16).astype(np.float32) / 32768.0
        return pcm, sr

    sr = struct.unpack_from("<I", wav_data, 24)[0]
    bits = struct.unpack_from("<H", wav_data, 34)[0]
    channels = struct.unpack_from("<H", wav_data, 22)[0]
    data_pos = wav_data.find(b"data")
    if data_pos < 0:
        return np.array([], dtype=np.float32), sr

    audio_raw = wav_data[data_pos + 8:]

    if bits == 16:
        pcm = np.frombuffer(audio_raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif bits == 32:
        pcm = np.frombuffer(audio_raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        pcm = np.frombuffer(audio_raw, dtype=np.float32)

    if channels > 1:
        pcm = pcm[::channels]

    return pcm, sr


def _wav_to_pcm(wav_data: bytes):
    """完整 WAV 文件转 PCM"""
    return _wav_chunk_to_pcm(wav_data)
