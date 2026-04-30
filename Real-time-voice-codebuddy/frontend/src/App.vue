<template>
  <div class="app" :class="currentState">
    <ParticleBg />

    <div class="main-container">
      <!-- Header -->
      <header class="app-header">
        <div class="header-left">
          <span class="status-dot" :class="currentState" />
          <h1 class="app-title">Yuki</h1>
        </div>
        <div class="header-right">
          <span class="conn-status" :class="{ connected: wsConnected }">
            {{ wsConnected ? '已连接' : '未连接' }}
          </span>
          <button class="icon-btn" @click="settingsVisible = true" title="设置">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
              <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.49.49 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 00-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 00-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6A3.6 3.6 0 1112 8.4a3.6 3.6 0 010 7.2z" />
            </svg>
          </button>
        </div>
      </header>

      <!-- 主内容区 -->
      <div class="content-area">
        <!-- 左侧：角色立绘 -->
        <div class="left-panel">
          <CharacterPanel
            :state="currentState"
            :affection="affection"
            :trust="trust"
          />
        </div>

        <!-- 右侧：对话气泡 -->
        <div class="right-panel">
          <ChatBubbles
            :messages="messages"
            :asrPartial="asrPartial"
            :llmPartial="llmPartial"
          />
        </div>
      </div>

      <!-- 底部控制栏 -->
      <div class="bottom-area">
        <VoiceWaveform
          :state="currentState"
          :volume="micVolume"
        />
        <ControlBar
          :isRecording="mic.isRecording.value"
          :isPlaying="player.isPlaying.value"
          :micEnabled="settings.micEnabled.value"
          :state="currentState"
          @send-text="handleSendText"
          @start-voice="handleStartVoice"
          @stop-voice="handleStopVoice"
          @open-settings="openSettings"
        />
      </div>
    </div>

    <!-- 设置面板 -->
    <SettingsPanel
      :visible="settingsVisible"
      :voices="voices"
      :currentVoice="settings.voice.value"
      :currentInstruction="settings.instruction.value"
      :currentDeviceId="mic.selectedDeviceId.value"
      :micEnabled="settings.micEnabled.value"
      :audioDevices="mic.audioDevices.value"
      :modelConfig="settings.modelConfig"
      @close="settingsVisible = false"
      @update:voice="handleVoiceUpdate"
      @update:instruction="handleInstructionUpdate"
      @update:device="handleDeviceUpdate"
      @update:mic-enabled="handleMicEnabledUpdate"
      @update:model-config="handleModelConfigUpdate"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import ParticleBg from './components/ParticleBg.vue'
import CharacterPanel from './components/CharacterPanel.vue'
import ChatBubbles from './components/ChatBubbles.vue'
import VoiceWaveform from './components/VoiceWaveform.vue'
import ControlBar from './components/ControlBar.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import { useWebSocket } from './composables/useWebSocket'
import { useMicrophone } from './composables/useMicrophone'
import { useAudioPlayer } from './composables/useAudioPlayer'
import { useSettings } from './composables/useSettings'

// ── 状态 ──────────────────────────────────────────────────
const ws = useWebSocket()
const mic = useMicrophone()
const player = useAudioPlayer()
const settings = useSettings()

const wsConnected = ref(false)
const currentState = ref('idle')
const affection = ref(0)
const trust = ref(0)
const messages = ref([])
const asrPartial = ref('')
const llmPartial = ref('')
const micVolume = ref(0)
const settingsVisible = ref(false)
const voices = ref([])

// 当前正在生成的 AI 消息（用于打断标记）
let currentAiMsgIdx = -1

// ── WebSocket 事件处理 ──────────────────────────────────
ws.on('status', (msg) => {
  currentState.value = msg.state
})

ws.on('asr_partial', (msg) => {
  asrPartial.value = msg.text
})

ws.on('asr_final', (msg) => {
  asrPartial.value = ''
  messages.value.push({ role: 'user', text: msg.text })
})

ws.on('llm_delta', (msg) => {
  if (msg.text) {
    llmPartial.value += msg.text
  }
})

ws.on('llm_done', () => {
  if (llmPartial.value) {
    messages.value.push({ role: 'assistant', text: llmPartial.value, interrupted: false })
    currentAiMsgIdx = messages.value.length - 1
  }
  llmPartial.value = ''
})

ws.on('tts_start', (msg) => {
  player.setSampleRate(msg.sample_rate || 24000)
})

ws.on('tts_audio', (pcm) => {
  player.enqueue(pcm)
})

ws.on('tts_end', () => {
  // TTS 播放结束
})

ws.on('emotion', (msg) => {
  affection.value = msg.affection
  trust.value = msg.trust
})

ws.on('error', (msg) => {
  console.error('[Error]', msg.message)
  messages.value.push({ role: 'system', text: `错误: ${msg.message}` })
})

// ── 连接状态 ──────────────────────────────────────────────
import { watch } from 'vue'
watch(() => ws.connected.value, (val) => {
  wsConnected.value = val
})

// ── 麦克风音量 ──────────────────────────────────────────
watch(() => mic.volume.value, (val) => {
  micVolume.value = val
})

// ── 用户操作处理 ──────────────────────────────────────────

function handleSendText({ text }) {
  // 打断当前播放
  if (currentState.value === 'thinking' || currentState.value === 'speaking') {
    doInterrupt()
  }

  messages.value.push({ role: 'user', text })
  ws.send({ type: 'text_input', text })
}

function handleStartVoice() {
  if (currentState.value === 'thinking' || currentState.value === 'speaking') {
    doInterrupt()
  }

  ws.send({ type: 'start_voice', sample_rate: 16000 })
  mic.start((binaryData) => ws.sendBinary(binaryData))
}

function handleStopVoice() {
  mic.stop()
  ws.send({ type: 'stop_voice' })
}

function doInterrupt() {
  ws.send({ type: 'interrupt' })
  player.clearQueue()
  mic.stop()

  // 标记当前 AI 消息为被打断
  if (currentAiMsgIdx >= 0 && currentAiMsgIdx < messages.value.length) {
    messages.value[currentAiMsgIdx].interrupted = true
  }
  currentAiMsgIdx = -1
  llmPartial.value = ''
  asrPartial.value = ''
}

function openSettings() {
  loadVoices()
  settingsVisible.value = true
}

async function loadVoices() {
  try {
    const resp = await fetch('/api/voices')
    if (resp.ok) {
      voices.value = await resp.json()
    }
  } catch (e) {
    console.error('加载音色列表失败', e)
  }
}

// ── 设置变更同步 ──────────────────────────────────────────

function handleVoiceUpdate(val) {
  settings.voice.value = val
  syncConfig()
}

function handleInstructionUpdate(val) {
  settings.instruction.value = val
  syncConfig()
}

function handleDeviceUpdate(val) {
  mic.selectedDeviceId.value = val
  settings.selectedDeviceId.value = val
}

function handleMicEnabledUpdate(val) {
  settings.micEnabled.value = val
  if (!val && mic.isRecording.value) {
    mic.stop()
    ws.send({ type: 'stop_voice' })
  }
}

function handleModelConfigUpdate({ key, value }) {
  settings.modelConfig[key] = value
  syncConfig()
}

function syncConfig() {
  ws.send(settings.getUpdateConfigMsg())
}

// ── 初始化 ──────────────────────────────────────────────

onMounted(async () => {
  ws.connect()
  await mic.enumerateDevices()

  // 设置麦克风设备
  if (settings.selectedDeviceId.value) {
    mic.selectedDeviceId.value = settings.selectedDeviceId.value
  }

  // 同步初始配置
  setTimeout(() => {
    syncConfig()
  }, 1000)
})
</script>

<style>
/* 全局样式 */
:root {
  --bg-primary: #0a0a1a;
  --bg-secondary: #1a1040;
  --bg-tertiary: #0d1b3e;
}

html, body, #app {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
</style>

<style scoped>
.app {
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-secondary) 50%, var(--bg-tertiary) 100%);
  color: rgba(255, 255, 255, 0.9);
  display: flex;
  flex-direction: column;
}

.main-container {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}

/* Header */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.app-title {
  font-size: 20px;
  font-weight: 600;
  background: linear-gradient(90deg, #ff7eb3, #7eb3ff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.conn-status {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.3);
}

.conn-status.connected {
  color: rgba(100, 255, 150, 0.7);
}

.icon-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.icon-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: white;
  transform: scale(1.08);
}

/* 状态指示灯 */
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #5eff7e;
  box-shadow: 0 0 6px rgba(94, 255, 126, 0.5);
}

.status-dot.listening {
  background: #5e9eff;
  box-shadow: 0 0 6px rgba(94, 158, 255, 0.5);
  animation: pulse 1.5s ease-in-out infinite;
}

.status-dot.thinking {
  background: #ffb85e;
  box-shadow: 0 0 6px rgba(255, 184, 94, 0.5);
  animation: pulse 1.2s ease-in-out infinite;
}

.status-dot.speaking {
  background: #ff5ea0;
  box-shadow: 0 0 6px rgba(255, 94, 160, 0.5);
  animation: pulse 1s ease-in-out infinite;
}

/* 内容区 */
.content-area {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.left-panel {
  width: 240px;
  flex-shrink: 0;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  overflow-y: auto;
}

.right-panel {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

/* 底部 */
.bottom-area {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* 响应式 */
@media (max-width: 768px) {
  .left-panel {
    display: none;
  }
}
</style>
