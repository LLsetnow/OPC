import { ref } from 'vue'

export function useMicrophone() {
  const isRecording = ref(false)
  const devices = ref([])
  const volume = ref(0)
  let stream = null
  let audioContext = null
  let workletNode = null
  let analyser = null
  let animationId = null
  let onAudioCallback = null

  async function enumerateDevices() {
    try {
      const all = await navigator.mediaDevices.enumerateDevices()
      devices.value = all
        .filter(d => d.kind === 'audioinput')
        .map(d => ({ deviceId: d.deviceId, label: d.label || `麦克风 ${d.deviceId.slice(0, 8)}` }))
    } catch {
      devices.value = []
    }
  }

  function start(deviceId = '') {
    return new Promise(async (resolve, reject) => {
      try {
        const constraints = {
          audio: {
            sampleRate: 16000,
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
          },
        }
        stream = await navigator.mediaDevices.getUserMedia(constraints)
        audioContext = new AudioContext({ sampleRate: 16000 })
        const source = audioContext.createMediaStreamSource(stream)

        analyser = audioContext.createAnalyser()
        analyser.fftSize = 256
        source.connect(analyser)

        await audioContext.audioWorklet.addModule('/worklet/recorder.js').catch(async () => {
          // Fallback: create inline worklet via blob URL
          const code = `
            class RecorderProcessor extends AudioWorkletProcessor {
              process(inputs) {
                const input = inputs[0];
                if (input && input[0]) {
                  const pcm16 = new Int16Array(input[0].length);
                  for (let i = 0; i < input[0].length; i++) {
                    pcm16[i] = Math.max(-32768, Math.min(32767, Math.round(input[0][i] * 32767)));
                  }
                  this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
                }
                return true;
              }
            }
            registerProcessor('recorder-processor', RecorderProcessor);
          `
          const blob = new Blob([code], { type: 'application/javascript' })
          const url = URL.createObjectURL(blob)
          await audioContext.audioWorklet.addModule(url)
          URL.revokeObjectURL(url)
        })

        workletNode = new AudioWorkletNode(audioContext, 'recorder-processor')
        workletNode.port.onmessage = (e) => {
          if (onAudioCallback && isRecording.value) {
            onAudioCallback(new Int16Array(e.data))
          }
        }
        source.connect(workletNode)

        isRecording.value = true
        _startVolumeMeter()
        resolve()
      } catch (err) {
        reject(err)
      }
    })
  }

  function stop() {
    isRecording.value = false
    _stopVolumeMeter()
    if (workletNode) { workletNode.disconnect(); workletNode = null }
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
    if (audioContext) { audioContext.close(); audioContext = null }
  }

  function onAudio(callback) {
    onAudioCallback = callback
  }

  function _startVolumeMeter() {
    function update() {
      if (!analyser || !isRecording.value) return
      const data = new Uint8Array(analyser.frequencyBinCount)
      analyser.getByteFrequencyData(data)
      const avg = data.reduce((a, b) => a + b, 0) / data.length
      volume.value = Math.min(1, avg / 128)
      animationId = requestAnimationFrame(update)
    }
    update()
  }

  function _stopVolumeMeter() {
    if (animationId) { cancelAnimationFrame(animationId); animationId = null }
    volume.value = 0
  }

  return { isRecording, devices, volume, enumerateDevices, start, stop, onAudio }
}
