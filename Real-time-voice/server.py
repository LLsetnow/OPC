"""Real-time-voice 主服务：WebSocket + HTTP API + 静态文件"""

import asyncio
import json
import os
import struct
import sys
import time
from pathlib import Path

import websockets
from websockets.asyncio.server import serve

from logger import setup_logger, get_logger

# 加载 .env（项目根目录）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=False)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9902

# ── 状态常量 ────────────────────────────────────────────────────────

STATE_IDLE = "idle"
STATE_LISTENING = "listening"
STATE_THINKING = "thinking"
STATE_SPEAKING = "speaking"

# ── 消息工具 ────────────────────────────────────────────────────────


def _mkmsg(**kwargs) -> str:
    return json.dumps(kwargs, ensure_ascii=False)


async def _send_json(ws, **kwargs):
    await ws.send(_mkmsg(**kwargs))


async def _send_audio(ws, pcm_bytes: bytes):
    """发送音频二进制帧：[0x02] + PCM float32"""
    await ws.send(b"\x02" + pcm_bytes)


# ── 主逻辑 ──────────────────────────────────────────────────────────


class VoiceChatSession:
    """管理单次 WebSocket 连接的完整会话状态"""

    def __init__(self, ws, logger):
        self.ws = ws
        self.logger = logger
        self.state = STATE_IDLE

        # 配置
        self.asr_model = os.environ.get("ASR_MODEL", "fun-asr-realtime")
        self.asr_api_key = os.environ.get("ASR_API_KEY", "")
        self.llm_model = os.environ.get("LLM_MODEL", "deepseek-v4-flash")
        self.llm_api_key = os.environ.get("LLM_API_KEY", "")
        self.llm_base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
        self.tts_model = os.environ.get("QWEN_TTS_MODEL", "cosyvoice-v3.5-flash")
        self.tts_api_key = os.environ.get("QWEN_TTS_API_KEY", "")
        self.tts_voice = os.environ.get("VOICE_ID1", "").split("#")[0].strip() or "longxiaochun_v3"
        self.tts_instruction = ""

        # 打断控制
        self._cancel_event = asyncio.Event()
        self._current_asr = None
        self._current_llm_task = None
        self._tts_queue = asyncio.Queue()

        # 好感度
        self.affection = 0
        self.trust = 0

    async def handle_message(self, raw):
        """消息路由"""
        if isinstance(raw, bytes):
            if raw[0:1] == b"\x01":
                # 音频数据
                if self.state == STATE_LISTENING and self._current_asr:
                    await self._current_asr.send_audio(raw[1:])
            return

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type", "")
        self.logger.debug(f"[WS] 收到: {msg_type}")

        if msg_type == "start_voice":
            await self._handle_start_voice(msg)
        elif msg_type == "stop_voice":
            await self._handle_stop_voice()
        elif msg_type == "text_input":
            await self._handle_text_input(msg.get("text", ""))
        elif msg_type == "interrupt":
            await self._handle_interrupt()
        elif msg_type == "update_config":
            await self._handle_update_config(msg)

    # ── 语音输入 ──────────────────────────────────────────────────

    async def _handle_start_voice(self, msg):
        if self.state == STATE_THINKING or self.state == STATE_SPEAKING:
            await self._handle_interrupt()

        from asr_client import ASRClient

        self.state = STATE_LISTENING
        await _send_json(self.ws, type="status", state=STATE_LISTENING)

        asr = ASRClient(self.asr_api_key, self.asr_model)
        self._current_asr = asr

        asr.set_callbacks(
            on_partial=lambda t: asyncio.create_task(
                _send_json(self.ws, type="asr_partial", text=t)
            ),
            on_final=lambda t: asyncio.create_task(self._on_asr_final(t)),
            on_error=lambda e: asyncio.create_task(
                _send_json(self.ws, type="error", message=str(e))
            ),
        )

        try:
            await asr.connect()
        except Exception as e:
            self.logger.error(f"[ASR] 连接失败: {e}")
            await _send_json(self.ws, type="error", message=f"ASR连接失败: {e}")
            self.state = STATE_IDLE

    async def _on_asr_final(self, text: str):
        """ASR 识别到最终结果 → 触发 LLM 流程"""
        if self.state != STATE_LISTENING:
            return
        self.logger.info(f"[会话] ASR final: {text}")
        await _send_json(self.ws, type="asr_final", text=text)
        await self._start_llm_tts_pipeline(text)

    async def _handle_stop_voice(self):
        if self._current_asr:
            await self._current_asr.finish()
            await self._current_asr.close()
            self._current_asr = None

    # ── 文字输入 ──────────────────────────────────────────────────

    async def _handle_text_input(self, text: str):
        if not text.strip():
            return
        if self.state == STATE_THINKING or self.state == STATE_SPEAKING:
            await self._handle_interrupt()
        self.logger.info(f"[会话] 文字输入: {text}")
        await self._start_llm_tts_pipeline(text)

    # ── LLM + TTS 流水线 ──────────────────────────────────────────

    async def _start_llm_tts_pipeline(self, user_text: str):
        self.state = STATE_THINKING
        self._cancel_event.clear()
        await _send_json(self.ws, type="status", state=STATE_THINKING)

        try:
            import httpx
            from llm_client import generate_llm_stream, should_trigger_tts, prepare_tts_text, extract_emotion_tags

            text_buffer = ""
            tts_tasks = []
            full_text = ""  # 初始化，防止 async for 未执行

            async for token, full_text, is_done in generate_llm_stream(
                user_text=user_text,
                session_id="default",
                api_key=self.llm_api_key,
                base_url=self.llm_base_url,
                model=self.llm_model,
            ):
                if self._cancel_event.is_set():
                    self.logger.info("[会话] LLM 生成被取消")
                    return

                if token:
                    await _send_json(self.ws, type="llm_delta", text=token)
                    text_buffer += token

                    if should_trigger_tts(text_buffer):
                        tts_text = prepare_tts_text(text_buffer)
                        if tts_text.strip():
                            t = asyncio.create_task(self._tts_synthesize(tts_text))
                            tts_tasks.append(t)
                        text_buffer = ""

                if is_done and text_buffer.strip():
                    tts_text = prepare_tts_text(text_buffer)
                    if tts_text.strip():
                        t = asyncio.create_task(self._tts_synthesize(tts_text))
                        tts_tasks.append(t)
                    text_buffer = ""

            await _send_json(self.ws, type="llm_done")

            # 提取好感/信任变化
            clean_text, aff, tru = extract_emotion_tags(full_text)
            if aff != 0 or tru != 0:
                self.affection += aff
                self.trust += tru
                await _send_json(self.ws, type="emotion",
                                 affection=self.affection, trust=self.trust)

            # 等待所有 TTS 任务完成
            if tts_tasks:
                await asyncio.gather(*tts_tasks, return_exceptions=True)

            self.state = STATE_IDLE
            await _send_json(self.ws, type="status", state=STATE_IDLE)
            await _send_json(self.ws, type="tts_end")

        except Exception as e:
            self.logger.error(f"[会话] LLM/TTS 管道异常: {e}")
            await _send_json(self.ws, type="error", message=str(e))
            self.state = STATE_IDLE
            await _send_json(self.ws, type="status", state=STATE_IDLE)

    async def _tts_synthesize(self, text: str):
        """执行单次 TTS 合成并发送音频"""
        from tts_client import generate_tts_stream

        if self._cancel_event.is_set():
            return

        self.state = STATE_SPEAKING
        await _send_json(self.ws, type="status", state=STATE_SPEAKING)

        try:
            first_audio = True
            for pcm_bytes, sr, is_final in generate_tts_stream(
                text=text,
                voice=self.tts_voice,
                model=self.tts_model,
                api_key=self.tts_api_key,
                instruction=self.tts_instruction,
            ):
                if self._cancel_event.is_set():
                    return

                if first_audio and not is_final:
                    await _send_json(self.ws, type="tts_start", sample_rate=sr)
                    first_audio = False

                if pcm_bytes and not is_final:
                    await _send_audio(self.ws, pcm_bytes)

            self.logger.debug(f"[TTS] 块合成完成: {text[:30]}...")

        except Exception as e:
            if not self._cancel_event.is_set():
                self.logger.error(f"[TTS] 合成失败: {e}")

    # ── 打断 ──────────────────────────────────────────────────────

    async def _handle_interrupt(self):
        self.logger.info("[会话] 收到打断请求")
        self._cancel_event.set()

        # 取消 ASR
        if self._current_asr:
            try:
                await self._current_asr.close()
            except Exception:
                pass
            self._current_asr = None

        self.state = STATE_IDLE
        await _send_json(self.ws, type="status", state=STATE_IDLE)

    # ── 配置更新 ──────────────────────────────────────────────────

    async def _handle_update_config(self, msg):
        if "voice" in msg:
            self.tts_voice = msg["voice"]
        if "instruction" in msg:
            self.tts_instruction = msg.get("instruction", "")
        if "asr_model" in msg:
            self.asr_model = msg["asr_model"]
        if "asr_api_key" in msg and msg["asr_api_key"]:
            self.asr_api_key = msg["asr_api_key"]
        if "llm_model" in msg:
            self.llm_model = msg["llm_model"]
        if "llm_api_key" in msg and msg["llm_api_key"]:
            self.llm_api_key = msg["llm_api_key"]
        if "llm_base_url" in msg:
            self.llm_base_url = msg["llm_base_url"]
        if "tts_model" in msg:
            self.tts_model = msg["tts_model"]
        if "tts_api_key" in msg and msg["tts_api_key"]:
            self.tts_api_key = msg["tts_api_key"]
        self.logger.info(f"[会话] 配置已更新: voice={self.tts_voice}")


# ── HTTP 请求处理 ──────────────────────────────────────────────────


async def _http_handler(connection, request):
    """HTTP 请求处理（用于 /api/voices 和静态文件）

    websockets 16.0: process_request(connection, request)
    - connection: ServerConnection
    - request: Request with .path, .headers
    返回 (status, headers, body) 元组或 None
    """
    from tts_client import list_voices

    path = request.path

    if path == "/api/voices":
        api_key = os.environ.get("QWEN_TTS_API_KEY", "")
        voices = list_voices(api_key)
        body = json.dumps(voices, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
        }
        return 200, headers, body

    # 静态文件服务（Vue build 产物）
    static_dir = Path(__file__).resolve().parent / "frontend" / "dist"
    if not static_dir.exists():
        static_dir = Path(__file__).resolve().parent / "frontend"

    if path == "/" or path == "":
        path = "/index.html"

    file_path = static_dir / path.lstrip("/")
    if file_path.exists() and file_path.is_file():
        content_type = _guess_mime(file_path)
        body = file_path.read_bytes()
        return 200, {"Content-Type": content_type}, body

    # SPA fallback
    index_path = static_dir / "index.html"
    if index_path.exists():
        body = index_path.read_bytes()
        return 200, {"Content-Type": "text/html"}, body

    return 404, {"Content-Type": "text/plain"}, b"Not Found"


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    mime_map = {
        ".html": "text/html; charset=utf-8",
        ".js": "application/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
        ".woff2": "font/woff2",
    }
    return mime_map.get(ext, "application/octet-stream")


# ── WebSocket 主循环 ───────────────────────────────────────────────


async def _ws_handler(websocket):
    """WebSocket 连接处理入口"""
    logger = get_logger()
    session = VoiceChatSession(websocket, logger)
    client_addr = websocket.remote_address
    logger.info(f"[连接] 新客户端: {client_addr}")

    await _send_json(websocket, type="status", state=STATE_IDLE)

    try:
        async for message in websocket:
            await session.handle_message(message)
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"[连接] 客户端断开: {client_addr}")
    except Exception as e:
        logger.error(f"[连接] 异常: {e}")
    finally:
        session._cancel_event.set()
        if session._current_asr:
            try:
                await session._current_asr.close()
            except Exception:
                pass


# ── 启动服务 ───────────────────────────────────────────────────────


def main(host=DEFAULT_HOST, port=DEFAULT_PORT):
    logger = setup_logger("voice-chat")
    logger.info(f"=== Real-time-voice 服务启动 ===")
    logger.info(f"HTTP + WS 地址: http://{host}:{port}")
    logger.info(f"API: GET /api/voices")

    # 检查 API 配置
    asr_key = os.environ.get("ASR_API_KEY") or os.environ.get("IMAGE_API_KEY", "")
    llm_key = os.environ.get("LLM_API_KEY", "")
    tts_key = os.environ.get("QWEN_TTS_API_KEY") or os.environ.get("IMAGE_API_KEY", "")

    if not asr_key:
        logger.warning("[配置] ASR_API_KEY 未设置，语音识别不可用")
    if not llm_key:
        logger.warning("[配置] LLM_API_KEY 未设置，对话不可用")
    if not tts_key:
        logger.warning("[配置] QWEN_TTS_API_KEY 未设置，语音合成不可用")

    logger.info(f"[配置] ASR: fun-asr-realtime")
    logger.info(f"[配置] LLM: {os.environ.get('LLM_MODEL', 'deepseek-v4-flash')} @ {os.environ.get('LLM_BASE_URL', 'https://api.deepseek.com')}")
    logger.info(f"[配置] TTS: {os.environ.get('QWEN_TTS_MODEL', 'cosyvoice-v3.5-flash')}")

    async def _serve(websocket):
        path = websocket.request.path if hasattr(websocket, 'request') else ""
        if path == "/ws/voice-chat":
            await _ws_handler(websocket)
        else:
            await _ws_handler(websocket)

    async def _run():
        async with serve(_serve, host, port, process_request=_http_handler):
            logger.info(f"服务就绪 → ws://{host}:{port}/ws/voice-chat")
            logger.info(f"按 Ctrl+C 停止服务")
            await asyncio.Future()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("服务已停止")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Real-time-voice 服务")
    parser.add_argument("--host", default=DEFAULT_HOST, help="绑定地址")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="绑定端口")
    args = parser.parse_args()
    main(args.host, args.port)
