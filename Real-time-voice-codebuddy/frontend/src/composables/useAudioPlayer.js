/**
 * Web Audio API 段落式排队播放 Float32 PCM
 *
 * - 每次 tts_start/tts_end 之间的 PCM 收集为一个"段落"
 * - 段落内所有 chunk 合并为一整段 buffer 后播放，消除 chunk 间隙
 * - 上一段播完后才播放下一段，保证严格顺序
 */
import { ref, onUnmounted } from 'vue'

export function useAudioPlayer() {
  const isPlaying = ref(false)

  let audioContext = null
  let sampleRate = 24000

  // 段落队列：每个元素是一段完整的 Float32Array
  let segmentQueue = []
  // 当前正在收集的段落 chunks
  let currentChunks = []
  let currentChunkLen = 0

  let isProcessing = false
  let currentSource = null
  let _cancelled = false

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

  /** 标记一个 TTS 段落开始 */
  function startSegment() {
    _ensureContext()
    _cancelled = false
    currentChunks = []
    currentChunkLen = 0
  }

  /** 往当前段落追加 PCM 数据 */
  function enqueue(pcmFloat32Array) {
    if (!pcmFloat32Array || pcmFloat32Array.length === 0) return
    currentChunks.push(pcmFloat32Array)
    currentChunkLen += pcmFloat32Array.length
  }

  /** 标记当前段落结束，合并并加入播放队列 */
  function endSegment() {
    if (currentChunkLen === 0) return

    // 合并所有 chunk 为一段连续 buffer
    const merged = new Float32Array(currentChunkLen)
    let offset = 0
    for (const chunk of currentChunks) {
      merged.set(chunk, offset)
      offset += chunk.length
    }

    segmentQueue.push(merged)
    currentChunks = []
    currentChunkLen = 0

    if (!isProcessing) {
      _processQueue()
    }
  }

  async function _processQueue() {
    isProcessing = true
    isPlaying.value = true

    while (segmentQueue.length > 0) {
      if (_cancelled) break

      const pcm = segmentQueue.shift()
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
    _cancelled = true
    segmentQueue = []
    currentChunks = []
    currentChunkLen = 0
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
    startSegment,
    enqueue,
    endSegment,
    clearQueue,
    stopAll,
  }
}
