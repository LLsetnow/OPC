"""Fun-ASR Realtime 流式语音识别（DashScope WebSocket）"""

import json
import asyncio
from logger import get_logger

logger = get_logger()


class ASRClient:
    """Fun-ASR Realtime WebSocket 客户端"""

    DASHSCOPE_WS_URL = "wss://dashscope.aliyuncs.com/api/v1/services/audio/asr/realtime"

    def __init__(self, api_key: str, model: str = "fun-asr-realtime"):
        self.api_key = api_key
        self.model = model
        self._ws = None
        self._task_id = None
        self._on_partial = None
        self._on_final = None
        self._on_error = None

    def set_callbacks(self, on_partial=None, on_final=None, on_error=None):
        self._on_partial = on_partial
        self._on_final = on_final
        self._on_error = on_error

    async def connect(self):
        """连接到 Fun-ASR WebSocket"""
        import websockets
        url = f"{self.DASHSCOPE_WS_URL}?token={self.api_key}"
        logger.info(f"[ASR] 连接到 Fun-ASR: model={self.model}")
        self._ws = await websockets.connect(url, max_size=2**24)

        task_msg = {
            "header": {
                "task_id": "asr-task-1",
                "action": "run-task",
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "asr",
                "function": "recognition",
                "model": self.model,
                "parameters": {
                    "format": "pcm",
                    "sample_rate": 16000,
                    "enable_intermediate_result": True,
                    "enable_punctuation": True,
                    "enable_semantic_sentence_detection": True,
                },
            },
        }
        await self._ws.send(json.dumps(task_msg))
        logger.info("[ASR] 已连接，等待识别结果")
        asyncio.create_task(self._recv_loop())

    async def send_audio(self, pcm_bytes: bytes):
        """发送音频数据（16kHz, 16bit, mono PCM）"""
        if self._ws and self._ws.open:
            try:
                await self._ws.send(pcm_bytes)
            except Exception as e:
                logger.error(f"[ASR] 发送音频失败: {e}")

    async def finish(self):
        """发送 finish-task 结束识别"""
        if self._ws and self._ws.open:
            finish_msg = {
                "header": {
                    "task_id": self._task_id or "asr-task-1",
                    "action": "finish-task",
                },
            }
            await self._ws.send(json.dumps(finish_msg))
            logger.info("[ASR] 已发送 finish-task")

    async def close(self):
        """关闭连接"""
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _recv_loop(self):
        """接收 ASR 结果的后台循环"""
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    continue
                try:
                    msg = json.loads(message)
                except json.JSONDecodeError:
                    continue

                header = msg.get("header", {})
                payload = msg.get("payload", {})
                event = header.get("event", "")
                self._task_id = header.get("task_id", self._task_id)

                if event == "task-failed":
                    err = header.get("status_text", "ASR task failed")
                    logger.error(f"[ASR] task-failed: {err}")
                    if self._on_error:
                        self._on_error(err)
                    break

                if event == "task-finished":
                    logger.info("[ASR] task-finished")
                    break

                result = payload.get("result", "")
                is_final = payload.get("is_final", False)

                if result:
                    if is_final:
                        logger.info(f"[ASR] final: {result}")
                        if self._on_final:
                            self._on_final(result)
                    else:
                        if self._on_partial:
                            self._on_partial(result)

        except Exception as e:
            logger.error(f"[ASR] 接收循环异常: {e}")
            if self._on_error:
                self._on_error(str(e))
