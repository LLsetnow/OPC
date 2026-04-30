<template>
  <ParticleBg />
  <div class="app-layout">
    <div class="app-container">
      <!-- Header -->
      <header class="app-header">
        <div class="header-left">
          <div class="status-indicator" :class="statusClass" />
          <span class="app-title">Yuki</span>
          <span class="app-subtitle">语音对话</span>
        </div>
        <div class="header-right">
          <span class="state-label">{{ stateLabel }}</span>
          <button class="btn-icon" @click="showSettings = true" title="设置">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>
        </div>
      </header>

      <!-- Main -->
      <div class="app-main">
        <aside class="left-panel">
          <CharacterPanel
            :state="appState"
            :affection="affection"
            :trust="trust"
          />
        </aside>
        <section class="center-panel">
          <ChatBubbles
            :messages="messages"
            :currentAsrText="currentAsrText"
            :isStreaming="isStreaming"
            :streamingText="streamingText"
          />
          <VoiceWaveform
            :volume="micVolume"
            :isActive="appState === 'listening'"
            :isAi="appState === 'speaking' || appState === 'thinking'"
          />
          <ControlBar
            :isRecording="appState === 'listening'"
            :micEnabled="settings.micEnabled"
            :disabled="appState === 'thinking' || appState === 'speaking'"
            @start-voice="startVoice"
            @stop-voice="stopVoice"
            @send-text="handleTextInput"
            @open-settings="showSettings = true"
          />
        </section>
      </div>
    </div>
  </div>

  <!-- Settings Panel -->
  <SettingsPanel
    :visible="showSettings"
    :voices="voices"
    :currentVoice="settings.voice"
    :currentInstruction="settings.instruction"
    :currentDeviceId="settings.deviceId"
    :micEnabled="settings.micEnabled"
    :audioDevices="audioDevices"
    :modelConfig="modelConfig"
    @close="showSettings = false"
    @update:voice="updateSetting('voice', $event)"
    @update:instruction="updateSetting('instruction', $event)"
    @update:device="updateSetting('deviceId', $event)"
    @update:mic-enabled="updateSetting('micEnabled', $event)"
    @update:model-config="handleModelConfigUpdate"
  />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import ParticleBg from './components/ParticleBg.vue'
import CharacterPanel from './components/CharacterPanel.vue'
import ChatBubbles from './components/ChatBubbles.vue'
import VoiceWaveform from './components/VoiceWaveform.vue'
import ControlBar from './components/ControlBar.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import { useWebSocket } from './composables/useWebSocket.js'
import { useMicrophone } from './composables/useMicrophone.js'
import { useAudioPlayer } from './composables/useAudioPlayer.js'
import { useSettings } from './composables/useSettings.js'

// ── Composables ──
const { settings, updateSetting, getWebSocketConfig } = useSettings()
const { connected, connect, send, sendAudio, on, off, close } = useWebSocket()
const { isRecording, devices: audioDevices, volume: micVolume, enumerateDevices, start: startMic, stop: stopMic, onAudio } = useMicrophone()
const { isPlaying, playPCM, clear: clearAudio } = useAudioPlayer()

// ── State ──
const appState = ref('idle')  // idle | listening | thinking | speaking
const showSettings = ref(false)
const messages = ref([])
const currentAsrText = ref('')
const streamingText = ref('')
const isStreaming = ref(false)
const affection = ref(0)
const trust = ref(0)
const voices = ref([])
let msgIdCounter = 0

const modelConfig = computed(() => ({
  asr_model: settings.asr_model,
  asr_api_key: settings.asr_api_key,
  llm_model: settings.llm_model,
  llm_api_key: settings.llm_api_key,
  llm_base_url: settings.llm_base_url,
  tts_model: settings.tts_model,
  tts_api_key: settings.tts_api_key,
}))

const statusClass = computed(() => `state-${appState.value}`)
const stateLabel = computed(() => {
  const map = { idle: '待机', listening: '聆听中...', thinking: '思考中...', speaking: '说话中...' }
  return map[appState.value] || '待机'
})

// ── WebSocket message handlers ──

function setupWS() {
  on('open', () => {
    console.log('[WS] Connected')
    send(getWebSocketConfig())
  })

  on('close', () => {
    console.log('[WS] Disconnected')
    appState.value = 'idle'
  })

  on('status', (data) => {
    if (data.state === 'speaking') {
      appState.value = 'speaking'
    } else if (data.state === 'thinking') {
      appState.value = 'thinking'
    } else if (data.state === 'listening') {
      appState.value = 'listening'
    } else {
      appState.value = 'idle'
      isStreaming.value = false
    }
  })

  on('asr_partial', (data) => {
    currentAsrText.value = data.text
  })

  on('asr_final', (data) => {
    currentAsrText.value = ''
    messages.value.push({ id: ++msgIdCounter, role: 'user', text: data.text })
    appState.value = 'thinking'
    isStreaming.value = true
    streamingText.value = ''
  })

  on('llm_delta', (data) => {
    streamingText.value += data.text
  })

  on('llm_done', () => {
    if (streamingText.value) {
      messages.value.push({ id: ++msgIdCounter, role: 'ai', text: streamingText.value })
      streamingText.value = ''
    }
    isStreaming.value = false
  })

  on('emotion', (data) => {
    if (data.affection !== undefined) affection.value = data.affection
    if (data.trust !== undefined) trust.value = data.trust
  })

  on('audio', (pcm) => {
    playPCM(pcm, 24000)
    appState.value = 'speaking'
  })

  on('tts_end', () => {
    if (appState.value === 'speaking') {
      appState.value = 'idle'
    }
  })

  on('error', (data) => {
    console.error('[WS] Error:', data.message)
    appState.value = 'idle'
    isStreaming.value = false
  })
}

// ── Voice input ──

async function startVoice() {
  if (appState.value === 'thinking' || appState.value === 'speaking') {
    // Interrupt
    send({ type: 'interrupt' })
    clearAudio()
    // Mark current AI message as interrupted
    const lastAi = [...messages.value].reverse().find(m => m.role === 'ai')
    if (lastAi && !lastAi.interrupted) {
      lastAi.interrupted = true
    }
    isStreaming.value = false
    streamingText.value = ''
    await new Promise(r => setTimeout(r, 100))
  }

  try {
    await startMic(settings.deviceId)
    appState.value = 'listening'
    currentAsrText.value = ''
    send({ type: 'start_voice', sample_rate: 16000 })
  } catch (err) {
    console.error('[Mic] Failed to start:', err)
  }
}

function stopVoice() {
  stopMic()
  send({ type: 'stop_voice' })
  if (currentAsrText.value) {
    // Use the partial result as final if user manually stops
  }
  if (appState.value === 'listening') {
    appState.value = 'idle'
  }
}

// ── Text input ──

function handleTextInput(text) {
  if (appState.value === 'thinking' || appState.value === 'speaking') {
    send({ type: 'interrupt' })
    clearAudio()
    const lastAi = [...messages.value].reverse().find(m => m.role === 'ai')
    if (lastAi && !lastAi.interrupted) {
      lastAi.interrupted = true
    }
    isStreaming.value = false
    streamingText.value = ''
  }

  messages.value.push({ id: ++msgIdCounter, role: 'user', text })
  appState.value = 'thinking'
  isStreaming.value = true
  streamingText.value = ''
  send({ type: 'text_input', text })
}

// ── Settings ──

function handleModelConfigUpdate({ key, value }) {
  updateSetting(key, value)
  send(getWebSocketConfig())
}

// ── Init ──

onMounted(async () => {
  await enumerateDevices()

  onAudio((pcmData) => {
    sendAudio(pcmData)
  })

  // WebSocket URL
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = location.hostname
  const wsPort = 9902
  const wsUrl = `${proto}//${host}:${wsPort}/ws/voice-chat`
  connect(wsUrl)
  setupWS()

  // Fetch voices
  try {
    const resp = await fetch('/api/voices')
    if (resp.ok) {
      voices.value = await resp.json()
    }
  } catch {}
})
</script>

<style>
/* ── Global Reset ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: #0a0a1a;
  color: #e0d0f0;
  overflow: hidden;
  height: 100vh;
}
#app { height: 100vh; }
</style>

<style scoped>
.app-layout {
  position: relative;
  z-index: 1;
  height: 100vh;
  display: flex;
  align-items: stretch;
  justify-content: center;
}
.app-container {
  width: 100%;
  max-width: 1000px;
  display: flex;
  flex-direction: column;
}

/* Header */
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  background: rgba(10,10,26,0.4);
  backdrop-filter: blur(10px);
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.status-indicator {
  width: 10px; height: 10px;
  border-radius: 50%;
  transition: all 0.4s ease;
}
.status-indicator.state-idle { background: #66bb6a; box-shadow: 0 0 6px rgba(102,187,106,0.4); }
.status-indicator.state-listening { background: #42a5f5; box-shadow: 0 0 10px rgba(66,165,245,0.5); animation: pulse-dot 1s ease-in-out infinite; }
.status-indicator.state-thinking { background: #ffa726; box-shadow: 0 0 10px rgba(255,167,38,0.5); animation: pulse-dot 1s ease-in-out infinite; }
.status-indicator.state-speaking { background: #ec407a; box-shadow: 0 0 10px rgba(236,64,122,0.5); animation: pulse-dot 0.6s ease-in-out infinite; }
@keyframes pulse-dot {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.5); }
}
.app-title {
  font-size: 18px;
  font-weight: 700;
  color: #e0d0f0;
  letter-spacing: 2px;
}
.app-subtitle {
  font-size: 12px;
  color: rgba(200,180,220,0.4);
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.state-label {
  font-size: 13px;
  color: rgba(200,180,220,0.5);
}
.btn-icon {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  color: rgba(200,180,220,0.5);
  width: 36px; height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-icon:hover { color: rgba(200,180,220,0.8); background: rgba(255,255,255,0.06); }

/* Main */
.app-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.left-panel {
  width: 240px;
  flex-shrink: 0;
  border-right: 1px solid rgba(255,255,255,0.05);
  background: rgba(10,10,26,0.2);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.center-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
</style>
