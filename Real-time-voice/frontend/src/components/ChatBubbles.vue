<template>
  <div class="chat-container" ref="container">
    <div v-if="messages.length === 0" class="chat-empty">
      <div class="empty-icon">💬</div>
      <div class="empty-text">点击麦克风或输入文字<br/>和 Yuki 开始对话吧~</div>
    </div>

    <TransitionGroup name="bubble">
      <div v-for="(msg, i) in messages" :key="msg.id"
        class="chat-row" :class="msg.role">
        <div class="chat-bubble" :class="{
          'user-bubble': msg.role === 'user',
          'ai-bubble': msg.role === 'ai',
          'interrupted': msg.interrupted,
          'asr-partial': msg.asrPartial,
        }">
          <div class="bubble-label">{{ msg.role === 'user' ? '你' : 'Yuki' }}</div>
          <div class="bubble-text">{{ msg.text }}</div>
        </div>
      </div>
    </TransitionGroup>

    <div v-if="currentAsrText" class="chat-row ai">
      <div class="chat-bubble ai-bubble asr-partial">
        <div class="bubble-label">识别中...</div>
        <div class="bubble-text">{{ currentAsrText }}<span class="cursor-blink">|</span></div>
      </div>
    </div>

    <div v-if="isStreaming && streamingText" class="chat-row ai">
      <div class="chat-bubble ai-bubble streaming">
        <div class="bubble-label">Yuki</div>
        <div class="bubble-text">{{ streamingText }}<span class="cursor-blink">|</span></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  currentAsrText: { type: String, default: '' },
  isStreaming: { type: Boolean, default: false },
  streamingText: { type: String, default: '' },
})

const container = ref(null)

watch(
  () => [props.messages.length, props.streamingText, props.currentAsrText],
  () => {
    nextTick(() => {
      if (container.value) {
        container.value.scrollTop = container.value.scrollHeight
      }
    })
  },
  { deep: true }
)
</script>

<style scoped>
.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.empty-icon { font-size: 48px; opacity: 0.5; }
.empty-text {
  color: rgba(200,180,220,0.4);
  font-size: 14px;
  text-align: center;
  line-height: 1.8;
}
.chat-row {
  display: flex;
}
.chat-row.user { justify-content: flex-end; }
.chat-row.ai { justify-content: flex-start; }
.chat-bubble {
  max-width: 80%;
  padding: 12px 16px;
  border-radius: 16px;
  backdrop-filter: blur(10px);
}
.user-bubble {
  background: rgba(66,165,245,0.12);
  border: 1px solid rgba(66,165,245,0.25);
  border-bottom-right-radius: 4px;
}
.ai-bubble {
  background: rgba(236,64,122,0.08);
  border: 1px solid rgba(236,64,122,0.2);
  border-bottom-left-radius: 4px;
}
.ai-bubble.interrupted {
  opacity: 0.4;
  border-color: rgba(255,255,255,0.05);
}
.ai-bubble.asr-partial {
  border-style: dashed;
  border-color: rgba(120,160,255,0.3);
}
.ai-bubble.streaming {
  border-color: rgba(236,64,122,0.3);
}
.bubble-label {
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 4px;
  color: rgba(200,180,220,0.5);
}
.user-bubble .bubble-label { color: rgba(100,180,255,0.6); }
.bubble-text {
  font-size: 14px;
  line-height: 1.7;
  color: rgba(220,210,235,0.9);
  word-break: break-word;
}
.cursor-blink {
  animation: blink 0.8s step-end infinite;
  color: rgba(255,255,255,0.6);
}
@keyframes blink {
  50% { opacity: 0; }
}
.bubble-enter-active { animation: fadeInUp 0.3s ease; }
.bubble-leave-active { animation: fadeInUp 0.2s ease reverse; }
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
