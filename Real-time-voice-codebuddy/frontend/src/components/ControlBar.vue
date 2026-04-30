<template>
  <div class="control-bar">
    <div class="input-row">
      <input
        v-model="textInput"
        type="text"
        class="text-input"
        :placeholder="inputPlaceholder"
        :disabled="isInputDisabled"
        @keydown.enter="handleSendText"
      />
      <button
        v-if="micEnabled"
        class="btn mic-btn"
        :class="{ active: isRecording, disabled: isMicDisabled }"
        :disabled="isMicDisabled"
        @click="handleMicClick"
        :title="isRecording ? '停止录音' : '开始录音'"
      >
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
          <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
          <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
        </svg>
      </button>
      <button
        class="btn send-btn"
        :disabled="isInputDisabled || !textInput.trim()"
        @click="handleSendText"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
        </svg>
      </button>
      <button class="btn settings-btn" @click="$emit('open-settings')" title="设置">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
          <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.49.49 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 00-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 00-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6A3.6 3.6 0 1112 8.4a3.6 3.6 0 010 7.2z" />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  isRecording: { type: Boolean, default: false },
  isPlaying: { type: Boolean, default: false },
  micEnabled: { type: Boolean, default: true },
  state: { type: String, default: 'idle' },
})

const emit = defineEmits(['send-text', 'start-voice', 'stop-voice', 'open-settings'])

const textInput = ref('')

const isInputDisabled = computed(() => props.isRecording || props.state === 'thinking' || props.state === 'speaking')
const isMicDisabled = computed(() => props.state === 'thinking' || props.state === 'speaking')

const inputPlaceholder = computed(() => {
  if (props.isRecording) return '录音中...'
  if (props.state === 'thinking') return 'AI 思考中...'
  if (props.state === 'speaking') return 'AI 说话中...'
  return '输入消息...'
})

function handleSendText() {
  const text = textInput.value.trim()
  if (!text || isInputDisabled.value) return
  emit('send-text', { text })
  textInput.value = ''
}

function handleMicClick() {
  if (props.isRecording) {
    emit('stop-voice')
  } else {
    emit('start-voice')
  }
}
</script>

<style scoped>
.control-bar {
  padding: 12px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.input-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.text-input {
  flex: 1;
  height: 40px;
  padding: 0 14px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.06);
  color: #e0e0f0;
  font-size: 14px;
  outline: none;
  transition: all 0.2s;
}

.text-input:focus {
  border-color: rgba(255, 120, 180, 0.4);
  background: rgba(255, 255, 255, 0.08);
}

.text-input:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.text-input::placeholder {
  color: rgba(255, 255, 255, 0.3);
}

.btn {
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  color: rgba(255, 255, 255, 0.7);
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.btn:hover:not(:disabled) {
  transform: scale(1.08);
  background: rgba(255, 255, 255, 0.14);
}

.btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.mic-btn.active {
  background: rgba(255, 60, 100, 0.3);
  border-color: rgba(255, 60, 100, 0.5);
  color: #ff5e8a;
  animation: micPulse 1.5s ease-in-out infinite;
}

.send-btn {
  background: rgba(255, 120, 180, 0.15);
  border-color: rgba(255, 120, 180, 0.3);
  color: #ff7eb3;
}

.settings-btn {
  background: rgba(255, 255, 255, 0.05);
}

@keyframes micPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255, 60, 100, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(255, 60, 100, 0); }
}
</style>
