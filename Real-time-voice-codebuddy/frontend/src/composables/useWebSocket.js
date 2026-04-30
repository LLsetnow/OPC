/**
 * WebSocket 连接管理：消息收发、自动重连
 */
import { ref, onUnmounted } from 'vue'

// 开发模式走 Vite 代理，生产模式直连后端
const WS_URL = import.meta.env.DEV
  ? `ws://${location.host}/ws/voice-chat`
  : `ws://${location.hostname}:9902/ws/voice-chat`

export function useWebSocket() {
  const ws = ref(null)
  const connected = ref(false)
  const connecting = ref(false)
  const reconnectTimer = ref(null)

  const handlers = {
    status: null,
    config: null,
    asr_partial: null,
    asr_final: null,
    llm_delta: null,
    llm_done: null,
    tts_start: null,
    tts_audio: null,
    tts_end: null,
    emotion: null,
    error: null,
  }

  function on(event, handler) {
    handlers[event] = handler
  }

  function connect(url = WS_URL) {
    if (ws.value && (ws.value.readyState === WebSocket.OPEN || ws.value.readyState === WebSocket.CONNECTING)) {
      return
    }

    connecting.value = true
    ws.value = new WebSocket(url)

    ws.value.onopen = () => {
      connected.value = true
      connecting.value = false
      console.log('[WS] 已连接')
    }

    ws.value.onclose = () => {
      connected.value = false
      connecting.value = false
      console.log('[WS] 已断开')
      scheduleReconnect(url)
    }

    ws.value.onerror = (err) => {
      console.error('[WS] 错误', err)
      connecting.value = false
    }

    ws.value.onmessage = (event) => {
      if (event.data instanceof Blob) {
        // 二进制音频帧: [0x02] + Float32 PCM
        event.data.arrayBuffer().then((buf) => {
          if (buf.byteLength < 5) return
          const view = new Uint8Array(buf)
          if (view[0] === 0x02) {
            // 跳过 1 字节前缀，拷贝到 4 字节对齐的新 buffer
            const pcmBuf = buf.slice(1)
            const pcm = new Float32Array(pcmBuf)
            handlers.tts_audio?.(pcm)
          }
        })
        return
      }

      try {
        const msg = JSON.parse(event.data)
        const type = msg.type
        if (handlers[type]) {
          handlers[type](msg)
        }
      } catch (e) {
        console.error('[WS] 解析消息失败', e)
      }
    }
  }

  function scheduleReconnect(url) {
    if (reconnectTimer.value) return
    reconnectTimer.value = setTimeout(() => {
      reconnectTimer.value = null
      connect(url)
    }, 3000)
  }

  function send(obj) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify(obj))
    }
  }

  function sendBinary(data) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(data)
    }
  }

  function disconnect() {
    if (reconnectTimer.value) {
      clearTimeout(reconnectTimer.value)
      reconnectTimer.value = null
    }
    if (ws.value) {
      ws.value.onclose = null
      ws.value.close()
      ws.value = null
    }
    connected.value = false
  }

  onUnmounted(() => {
    // 只在组件真正卸载时断开，避免 composable 初始化时误触发
  })

  return {
    connected,
    connecting,
    connect,
    disconnect,
    send,
    sendBinary,
    on,
  }
}
