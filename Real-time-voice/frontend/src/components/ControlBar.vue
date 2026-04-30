<template>
  <div class="control-bar">
    <div class="input-row">
      <input
        ref="textInput"
        v-model="text"
        class="text-input"
        type="text"
        placeholder="输入消息，按 Enter 发送..."
        :disabled="disabled || isRecording"
        @keydown.enter="sendText"
      />
      <button v-if="!isRecording" class="btn btn-mic" :class="{ disabled: !micEnabled }"
        :disabled="!micEnabled || disabled" @click="$emit('start-voice')" title="语音输入">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
          <line x1="12" y1="19" x2="12" y2="23"/>
          <line x1="8" y1="23" x2="16" y2="23"/>
        </svg>
      </button>
      <button v-else class="btn btn-mic recording" @click="$emit('stop-voice')" title="停止录音">
        <div class="rec-dot" />
      </button>
      <button v-if="!isRecording" class="btn btn-send" :disabled="!text.trim() || disabled"
        @click="sendText" title="发送">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="22" y1="2" x2="11" y2="13"/>
          <polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>
      </button>
      <button class="btn btn-settings" @click="$emit('open-settings')" title="设置">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  isRecording: { type: Boolean, default: false },
  micEnabled: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['send-text', 'start-voice', 'stop-voice', 'open-settings'])

const text = ref('')

function sendText() {
  if (text.value.trim() && !props.disabled) {
    emit('send-text', text.value.trim())
    text.value = ''
  }
}
</script>

<style scoped>
.control-bar {
  padding: 12px 16px;
  border-top: 1px solid rgba(255,255,255,0.06);
  background: rgba(10,10,26,0.6);
  backdrop-filter: blur(10px);
}
.input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.text-input {
  flex: 1;
  padding: 10px 16px;
  border-radius: 24px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.04);
  color: #e0d0f0;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
  font-family: inherit;
}
.text-input:focus {
  border-color: rgba(160,120,220,0.4);
}
.text-input:disabled {
  opacity: 0.4;
}
.text-input::placeholder {
  color: rgba(200,180,220,0.25);
}
.btn {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.04);
  color: rgba(200,180,220,0.7);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}
.btn:hover { background: rgba(255,255,255,0.08); color: #e0d0f0; }
.btn:active { transform: scale(0.95); }
.btn:disabled { opacity: 0.3; cursor: not-allowed; }
.btn-mic.disabled { opacity: 0.3; }
.btn-mic.recording {
  background: rgba(236,64,122,0.2);
  border-color: rgba(236,64,122,0.4);
  animation: mic-pulse 1.5s ease-in-out infinite;
}
.rec-dot {
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #ec407a;
}
@keyframes mic-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(236,64,122,0.4); }
  50% { box-shadow: 0 0 0 12px rgba(236,64,122,0); }
}
.btn-send { color: rgba(120,200,255,0.7); }
.btn-send:hover { color: #80d8ff; }
.btn-settings { color: rgba(200,180,220,0.5); }
.btn-settings:hover { color: rgba(200,180,220,0.8); }
</style>
