/**
 * Web Audio API 排队播放 Float32 PCM、清空队列（打断用）
 */
import { ref, onUnmounted } from 'vue'

export function useAudioPlayer() {
  const isPlaying = ref(false)

  let audioContext = null
  let sampleRate = 24000
  let playQueue = []
  let isProcessing = false
  let currentSource = null

  function _ensureContext() {
    if (!audioContext || audioContext.state === 'closed') {
      audioContext = new AudioContext({ sampleRate })
    }
    if (audioContext.state === 'suspended') {
      audioContext.resume()
    }
  }

  function setSampleRate(sr) {
    if (sr && sr !== sampleRate) {
      sampleRate = sr
      if (audioContext) {
        audioContext.close().catch(() => {})
        audioContext = null
      }
    }
  }

  function enqueue(pcmFloat32Array) {
    _ensureContext()
    playQueue.push(pcmFloat32Array)
    if (!isProcessing) {
      _processQueue()
    }
  }

  async function _processQueue() {
    isProcessing = true
    isPlaying.value = true

    while (playQueue.length > 0) {
      const pcm = playQueue.shift()
      if (!pcm || pcm.length === 0) continue

      try {
        _ensureContext()
        const buffer = audioContext.createBuffer(1, pcm.length, audioContext.sampleRate)
        buffer.getChannelData(0).set(pcm)

        const source = audioContext.createBufferSource()
        source.buffer = buffer
        source.connect(audioContext.destination)

        currentSource = source

        await new Promise((resolve) => {
          source.onended = resolve
          source.start(0)
        })

        currentSource = null
      } catch (e) {
        console.error('[Player] 播放错误', e)
        currentSource = null
      }
    }

    isProcessing = false
    isPlaying.value = false
  }

  function clearQueue() {
    playQueue = []
    if (currentSource) {
      try {
        currentSource.stop()
      } catch (e) {
        // ignore
      }
      currentSource = null
    }
    isProcessing = false
    isPlaying.value = false
  }

  function stopAll() {
    clearQueue()
    if (audioContext) {
      audioContext.close().catch(() => {})
      audioContext = null
    }
  }

  onUnmounted(() => {
    stopAll()
  })

  return {
    isPlaying,
    setSampleRate,
    enqueue,
    clearQueue,
    stopAll,
  }
}
