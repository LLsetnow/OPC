"""CosyVoice TTS 流式合成 + 音色查询（独立实现，不复用 tts_server.py）"""

import base64
import io
import json
import struct
import time

import numpy as np
import requests

# ── 系统音色列表 ──────────────────────────────────────────────────

QWEN_TTS_VOICES_V2 = {
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

QWEN_TTS_VOICES_V3 = {
    "longanyang": "龙安洋（阳光大男孩）",
    "longanhuan": "龙安欢（欢脱元气女）",
    "longhuhu_v3": "龙呼呼（天真烂漫女童）",
    "longpaopao_v3": "龙泡泡（飞天泡泡音）",
    "longjielidou_v3": "龙杰力豆（阳光顽皮男）",
    "longxian_v3": "龙仙（豪放可爱女）",
    "longling_v3": "龙铃（稚气呆板女）",
    "longshanshan_v3": "龙闪闪（戏剧化童声）",
    "longniuniu_v3": "龙牛牛（阳光男童声）",
    "longxiaochun_v3": "龙小淳（知性积极女）",
    "longxiaoxia_v3": "龙小夏（沉稳权威女）",
    "longyumi_v3": "YUMI（正经青年女）",
    "longanyun_v3": "龙安昀（居家暖男）",
    "longanwen_v3": "龙安温（优雅知性女）",
    "longanli_v3": "龙安莉（利落从容女）",
    "longanlang_v3": "龙安朗（清爽利落男）",
    "longyingmu_v3": "龙应沐（优雅知性女）",
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
    "longjiaxin_v3": "龙嘉欣（优雅粤语女）",
    "longjiayi_v3": "龙嘉怡（知性粤语女）",
    "longanyue_v3": "龙安粤（欢脱粤语男）",
    "longlaotie_v3": "龙老铁（东北直率男）",
    "longshange_v3": "龙陕哥（原味陕北男）",
    "longanmin_v3": "龙安闽（清纯萝莉女）",
    "longfei_v3": "龙飞（热血磁性男）",
    "longyingxiao_v3": "龙应笑（清甜推销女）",
    "longyingxun_v3": "龙应询（年轻青涩男）",
    "longyingjing_v3": "龙应静（低调冷静女）",
    "longyingling_v3": "龙应聆（温和共情女）",
    "longyingtao_v3": "龙应桃（温柔淡定女）",
    "longshuo_v3": "龙硕（博才干练男）",
    "longshu_v3": "龙书（沉稳青年男）",
    "loongbella_v3": "Bella3.0（精准干练女）",
    "longanran_v3": "龙安燃（活泼质感女）",
    "longanxuan_v3": "龙安宣（经典直播女）",
}

QWEN_TTS_VOICES_BY_MODEL = {
    "cosyvoice-v2": QWEN_TTS_VOICES_V2,
    "cosyvoice-v3-flash": QWEN_TTS_VOICES_V3,
    "cosyvoice-v3-plus": QWEN_TTS_VOICES_V3,
    "cosyvoice-v3.5-flash": {},
    "cosyvoice-v3.5-plus": {},
}

# ── 音色查询 ──────────────────────────────────────────────────────

def list_voices(api_key: str, model: str = "") -> list[dict]:
    """获取可用音色列表（系统音色 + API 查询的复刻音色）"""
    voices = []

    # 系统音色
    sys_voices = QWEN_TTS_VOICES_BY_MODEL.get(model, {})
    if not sys_voices:
        sys_voices = {**QWEN_TTS_VOICES_V2, **QWEN_TTS_VOICES_V3}
    for vid, label in sys_voices.items():
        voices.append({"value": vid, "label": label, "type": "system"})

    # API 查询复刻音色
    clone_voices = _query_clone_from_api(api_key)
    voices.extend(clone_voices)

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
                if v.get("status") != "OK" or not vid:
                    continue
                label = f"{vid[:16]}...（{target}）" if len(vid) > 20 else f"{vid}（{target}）"
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
        "format": "wav",
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
    first_chunk = True

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
            pcm, sr = _wav_chunk_to_pcm(bytes(audio_bytes))
            if first_chunk:
                first_chunk = False
                yield (pcm.tobytes(), sr, False)
            else:
                yield (pcm.tobytes(), sr, False)

        err_code = chunk.get("code", "")
        if err_code and err_code not in ("Success", ""):
            err_msg = chunk.get("message", "")
            raise RuntimeError(f"TTS error: {err_code} {err_msg}")

    gen_time = time.time() - t0
    if not collected:
        raise RuntimeError("TTS 未返回音频数据")

    # Yield the final accumulated WAV for duration calculation
    full_pcm, full_sr = _wav_to_pcm(bytes(collected))
    duration = len(full_pcm) / full_sr if full_sr > 0 else 0
    yield (b"", full_sr, True)  # Signal end, with full duration info


def _wav_chunk_to_pcm(wav_data: bytes):
    """将 WAV 字节转换为 float32 PCM 数组"""
    if wav_data[:4] != b"RIFF" or len(wav_data) <= 44:
        # 可能是裸 PCM，按 16bit 处理
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
