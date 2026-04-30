import { ref } from 'vue'

export function useAudioPlayer() {
  const isPlaying = ref(false)
  let audioCtx = null
  let nextPlayTime = 0

  function ensureContext(sampleRate = 24000) {
    if (!audioCtx || audioCtx.state === 'closed') {
      audioCtx = new AudioContext({ sampleRate })
      nextPlayTime = audioCtx.currentTime
    }
    return audioCtx
  }

  function playPCM(float32Array, sampleRate = 24000) {
    const ctx = ensureContext(sampleRate)
    if (ctx.sampleRate !== sampleRate) {
      ctx.close()
      audioCtx = new AudioContext({ sampleRate })
      nextPlayTime = audioCtx.currentTime
    }

    const buffer = audioCtx.createBuffer(1, float32Array.length, sampleRate)
    buffer.getChannelData(0).set(float32Array)
    const source = audioCtx.createBufferSource()
    source.buffer = buffer
    source.connect(audioCtx.destination)

    const now = audioCtx.currentTime
    if (now > nextPlayTime) nextPlayTime = now
    source.start(nextPlayTime)
    nextPlayTime += buffer.duration

    isPlaying.value = true
    source.onended = () => {
      if (audioCtx && audioCtx.currentTime >= nextPlayTime - 0.05) {
        isPlaying.value = false
        nextPlayTime = 0
      }
    }
  }

  function clear() {
    if (audioCtx && audioCtx.state !== 'closed') {
      audioCtx.close()
    }
    audioCtx = null
    nextPlayTime = 0
    isPlaying.value = false
  }

  function suspend() {
    if (audioCtx && audioCtx.state === 'running') {
      audioCtx.suspend()
    }
  }

  return { isPlaying, playPCM, clear, suspend }
}
