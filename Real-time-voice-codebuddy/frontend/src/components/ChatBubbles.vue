<template>
  <div class="chat-bubbles" ref="container">
    <div
      v-for="(msg, idx) in messages"
      :key="idx"
      class="bubble-wrapper"
      :class="msg.role"
    >
      <div class="bubble" :class="[msg.role, { interrupted: msg.interrupted }]">
        <span class="bubble-text">{{ msg.text }}</span>
        <span v-if="msg.interrupted" class="interrupted-mark">（被打断）</span>
      </div>
    </div>
    <div v-if="asrPartial" class="bubble-wrapper user">
      <div class="bubble user asr-partial">
        <span class="bubble-text">{{ asrPartial }}...</span>
      </div>
    </div>
    <div v-if="llmPartial" class="bubble-wrapper assistant">
      <div class="bubble assistant llm-partial">
        <span class="bubble-text">{{ llmPartial }}<span class="cursor">|</span></span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  asrPartial: { type: String, default: '' },
  llmPartial: { type: String, default: '' },
})

const container = ref(null)

watch(
  () => [props.messages.length, props.asrPartial, props.llmPartial],
  () => {
    nextTick(() => {
      if (container.value) {
        container.value.scrollTop = container.value.scrollHeight
      }
    })
  }
)
</script>

<style scoped>
.chat-bubbles {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  overflow-y: auto;
  height: 100%;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.15) transparent;
}

.bubble-wrapper {
  display: flex;
  animation: fadeInUp 0.3s ease;
}

.bubble-wrapper.user {
  justify-content: flex-end;
}

.bubble-wrapper.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.5;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  word-break: break-word;
}

.bubble.assistant {
  background: rgba(255, 120, 180, 0.12);
  border: 1px solid rgba(255, 120, 180, 0.25);
  color: rgba(255, 220, 240, 0.95);
  border-bottom-left-radius: 4px;
}

.bubble.user {
  background: rgba(80, 150, 255, 0.12);
  border: 1px solid rgba(80, 150, 255, 0.25);
  color: rgba(200, 220, 255, 0.95);
  border-bottom-right-radius: 4px;
}

.bubble.interrupted {
  opacity: 0.5;
  border-style: dashed;
}

.bubble.asr-partial {
  opacity: 0.6;
  font-style: italic;
}

.bubble.llm-partial .cursor {
  animation: blink 0.8s step-end infinite;
  color: rgba(255, 120, 180, 0.8);
}

.interrupted-mark {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
  margin-left: 6px;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
