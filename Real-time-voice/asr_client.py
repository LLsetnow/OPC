"""Fun-ASR Realtime 流式语音识别（DashScope WebSocket 官方协议）"""

import json
import asyncio
import time
from logger import get_logger

logger = get_logger()


class ASRClient:
    """Fun-ASR Realtime WebSocket 客户端"""

    DASHSCOPE_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"

    def __init__(self, api_key: str, model: str = "fun-asr-realtime"):
        self.api_key = api_key
        self.model = model
        self._ws = None
        self._task_id = None
        self._on_partial = None  # callback(text: str)
        self._on_final = None    # callback(text: str)
        self._on_error = None    # callback(error: str)
        self._ready = asyncio.Event()

    def set_callbacks(self, on_partial=None, on_final=None, on_error=None):
        self._on_partial = on_partial
        self._on_final = on_final
        self._on_error = on_error

    async def connect(self):
        """连接到 Fun-ASR WebSocket"""
        import websockets

        logger.info(f"[ASR] 连接到 Fun-ASR: model={self.model}")
        t0 = time.time()
        self._ws = await websockets.connect(
            self.DASHSCOPE_WS_URL,
            additional_headers={"Authorization": f"Bearer {self.api_key}"},
            max_size=2**24,
        )

        import uuid
        self._task_id = uuid.uuid4().hex

        # 发送 run-task
        task_msg = {
            "header": {
                "task_id": self._task_id,
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
                "input": {},
            },
        }
        await self._ws.send(json.dumps(task_msg))
        logger.info(f"[ASR] run-task 已发送，耗时 {(time.time() - t0):.1f}s")

        # 启动后台接收任务
        asyncio.create_task(self._recv_loop())

    async def send_audio(self, pcm_bytes: bytes):
        """发送音频数据（16kHz, 16bit, mono PCM）"""
        if self._ready.is_set() and self._ws and self._ws.state.name == "OPEN":
            try:
                await self._ws.send(pcm_bytes)
            except Exception as e:
                logger.error(f"[ASR] 发送音频失败: {e}")

    async def finish(self):
        """发送 finish-task 结束识别"""
        if self._ws and self._ws.state.name == "OPEN":
            finish_msg = {
                "header": {
                    "task_id": self._task_id or "",
                    "action": "finish-task",
                },
                "payload": {"input": {}},
            }
            await self._ws.send(json.dumps(finish_msg))
            logger.info("[ASR] 已发送 finish-task")

    async def close(self):
        """关闭连接"""
        self._ready.clear()
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
                event = header.get("event", "")
                self._task_id = header.get("task_id", self._task_id)

                if event == "task-started":
                    self._ready.set()
                    logger.info(f"[ASR] task-started, ready to send audio")

                elif event == "task-failed":
                    err_msg = header.get("error_message", header.get("status_text", "ASR task failed"))
                    logger.error(f"[ASR] task-failed: {err_msg}")
                    if self._on_error:
                        self._on_error(err_msg)
                    break

                elif event == "task-finished":
                    logger.info("[ASR] task-finished")
                    break

                elif event == "result-generated":
                    payload = msg.get("payload", {})
                    output = payload.get("output", {})
                    sentence = output.get("sentence", {})
                    text = sentence.get("text", "")

                    if not text:
                        continue

                    # is_final: sentence 有 end_time 且不为 None
                    is_final = (
                        "end_time" in sentence
                        and sentence["end_time"] is not None
                    )

                    if is_final:
                        logger.info(f"[ASR] final: {text}")
                        if self._on_final:
                            self._on_final(text)
                    else:
                        if self._on_partial:
                            self._on_partial(text)

        except Exception as e:
            logger.error(f"[ASR] 接收循环异常: {e}")
            if self._on_error:
                self._on_error(str(e))
