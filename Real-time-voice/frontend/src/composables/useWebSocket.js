import { ref, onUnmounted } from 'vue'

export function useWebSocket() {
  const ws = ref(null)
  const connected = ref(false)
  const messageHandlers = new Map()
  let reconnectTimer = null

  function connect(url) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) return

    const socket = new WebSocket(url)
    socket.binaryType = 'arraybuffer'
    ws.value = socket

    socket.onopen = () => {
      connected.value = true
      emit('open')
    }

    socket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        if (event.data.byteLength > 0) {
          const prefix = new Uint8Array(event.data, 0, 1)[0]
          if (prefix === 0x02) {
            const pcm = new Float32Array(event.data.slice(1))
            emit('audio', pcm)
          }
        }
      } else {
        try {
          const data = JSON.parse(event.data)
          emit(data.type, data)
        } catch {}
      }
    }

    socket.onclose = () => {
      connected.value = false
      emit('close')
    }

    socket.onerror = () => {
      emit('error')
    }
  }

  function send(data) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      if (data instanceof ArrayBuffer || data instanceof Uint8Array) {
        ws.value.send(data)
      } else {
        ws.value.send(JSON.stringify(data))
      }
    }
  }

  function sendAudio(pcmData) {
    const prefix = new Uint8Array([0x01])
    const combined = new Uint8Array(prefix.length + pcmData.length)
    combined.set(prefix, 0)
    combined.set(new Uint8Array(pcmData.buffer, pcmData.byteOffset, pcmData.byteLength), prefix.length)
    send(combined.buffer)
  }

  function on(type, handler) {
    if (!messageHandlers.has(type)) {
      messageHandlers.set(type, new Set())
    }
    messageHandlers.get(type).add(handler)
  }

  function off(type, handler) {
    const handlers = messageHandlers.get(type)
    if (handlers) handlers.delete(handler)
  }

  function emit(type, data) {
    const handlers = messageHandlers.get(type)
    if (handlers) handlers.forEach(h => h(data))
  }

  function close() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    connected.value = false
  }

  onUnmounted(() => {
    close()
    if (reconnectTimer) clearTimeout(reconnectTimer)
  })

  return { ws, connected, connect, send, sendAudio, on, off, close }
}
