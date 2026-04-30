/**
 * AudioWorklet 麦克风采集 + 设备枚举 + PCM 数据发送
 */
import { ref, onUnmounted } from 'vue'

export function useMicrophone() {
  const isRecording = ref(false)
  const audioDevices = ref([])
  const selectedDeviceId = ref('')
  const volume = ref(0)

  let audioContext = null
  let mediaStream = null
  let workletNode = null
  let analyser = null
  let volumeInterval = null

  async function enumerateDevices() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices()
      audioDevices.value = devices
        .filter((d) => d.kind === 'audioinput')
        .map((d) => ({
          deviceId: d.deviceId,
          label: d.label || `麦克风 ${d.deviceId.slice(0, 8)}`,
        }))
      if (!selectedDeviceId.value && audioDevices.value.length > 0) {
        selectedDeviceId.value = audioDevices.value[0].deviceId
      }
    } catch (e) {
      console.error('[Mic] 枚举设备失败', e)
    }
  }

  async function start(sendBinaryFn) {
    if (isRecording.value) return

    try {
      const constraints = {
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      }
      if (selectedDeviceId.value) {
        constraints.audio.deviceId = { exact: selectedDeviceId.value }
      }

      mediaStream = await navigator.mediaDevices.getUserMedia(constraints)
      audioContext = new AudioContext({ sampleRate: 16000 })

      // AudioWorklet
      const workletCode = `
        class PCMProcessor extends AudioWorkletProcessor {
          process(inputs) {
            const input = inputs[0]
            if (input && input[0]) {
              const float32 = input[0]
              const int16 = new Int16Array(float32.length)
              for (let i = 0; i < float32.length; i++) {
                const s = Math.max(-1, Math.min(1, float32[i]))
                int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
              }
              this.port.postMessage(int16.buffer, [int16.buffer])
            }
            return true
          }
        }
        registerProcessor('pcm-processor', PCMProcessor)
      `
      const blob = new Blob([workletCode], { type: 'application/javascript' })
      const url = URL.createObjectURL(blob)
      await audioContext.audioWorklet.addModule(url)
      URL.revokeObjectURL(url)

      const source = audioContext.createMediaStreamSource(mediaStream)
      workletNode = new AudioWorkletNode(audioContext, 'pcm-processor')

      workletNode.port.onmessage = (event) => {
        const pcm16Buffer = event.data
        // 上行音频帧: [0x01] + PCM16
        const header = new Uint8Array([0x01])
        const combined = new Uint8Array(1 + pcm16Buffer.byteLength)
        combined.set(header, 0)
        combined.set(new Uint8Array(pcm16Buffer), 1)
        sendBinaryFn(combined.buffer)
      }

      source.connect(workletNode)
      workletNode.connect(audioContext.destination)

      // 音量分析
      analyser = audioContext.createAnalyser()
      analyser.fftSize = 256
      source.connect(analyser)
      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      volumeInterval = setInterval(() => {
        if (!analyser) return
        analyser.getByteFrequencyData(dataArray)
        let sum = 0
        for (let i = 0; i < dataArray.length; i++) sum += dataArray[i]
        volume.value = sum / dataArray.length / 255
      }, 50)

      isRecording.value = true
    } catch (e) {
      console.error('[Mic] 启动失败', e)
      stop()
    }
  }

  function stop() {
    isRecording.value = false
    volume.value = 0

    if (volumeInterval) {
      clearInterval(volumeInterval)
      volumeInterval = null
    }
    if (workletNode) {
      workletNode.disconnect()
      workletNode = null
    }
    if (audioContext) {
      audioContext.close().catch(() => {})
      audioContext = null
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop())
      mediaStream = null
    }
  }

  onUnmounted(() => {
    stop()
  })

  return {
    isRecording,
    audioDevices,
    selectedDeviceId,
    volume,
    enumerateDevices,
    start,
    stop,
  }
}
