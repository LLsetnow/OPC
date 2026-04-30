<template>
  <div class="character-panel">
    <div class="character-avatar" :class="stateClass">
      <div class="avatar-glow" />
      <img src="/img/gpt_img_20260430_210021.png" alt="Yuki" class="avatar-img" />
    </div>

    <div class="affection-bar">
      <div class="bar-label">好感度</div>
      <div class="bar-track">
        <div class="bar-fill affection" :style="{ width: affectionPct + '%' }" />
      </div>
      <div class="bar-value">{{ affection }}</div>
    </div>
    <div class="affection-bar">
      <div class="bar-label">信任度</div>
      <div class="bar-track">
        <div class="bar-fill trust" :style="{ width: trustPct + '%' }" />
      </div>
      <div class="bar-value">{{ trust }}</div>
    </div>

    <div class="status-indicator">
      <span class="status-dot" :class="stateClass" />
      <span class="status-text">{{ stateText }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  state: { type: String, default: 'idle' },
  affection: { type: Number, default: 0 },
  trust: { type: Number, default: 0 },
})

const stateClass = computed(() => props.state)

const stateText = computed(() => {
  const map = { idle: '待机中', listening: '聆听中...', thinking: '思考中...', speaking: '说话中...' }
  return map[props.state] || '待机中'
})

const affectionPct = computed(() => Math.min(100, Math.max(0, props.affection * 2)))
const trustPct = computed(() => Math.min(100, Math.max(0, props.trust * 2)))
</script>

<style scoped>
.character-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px;
}

.character-avatar {
  position: relative;
  width: 180px;
  height: 260px;
  border-radius: 16px;
  overflow: hidden;
  transition: transform 0.3s ease;
}

.character-avatar.speaking {
  transform: scale(1.03);
}

.avatar-glow {
  position: absolute;
  inset: -20px;
  border-radius: 50%;
  z-index: 0;
  transition: all 0.5s ease;
}

.character-avatar.idle .avatar-glow {
  box-shadow: 0 0 30px rgba(100, 200, 100, 0.3);
}
.character-avatar.listening .avatar-glow {
  box-shadow: 0 0 40px rgba(80, 150, 255, 0.5);
  animation: pulse 1.5s ease-in-out infinite;
}
.character-avatar.thinking .avatar-glow {
  box-shadow: 0 0 40px rgba(255, 180, 60, 0.5);
  animation: pulse 1.2s ease-in-out infinite;
}
.character-avatar.speaking .avatar-glow {
  box-shadow: 0 0 50px rgba(255, 120, 180, 0.6);
  animation: pulse 1s ease-in-out infinite;
}

.avatar-img {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.affection-bar {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
}

.bar-label {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  white-space: nowrap;
  width: 48px;
}

.bar-track {
  flex: 1;
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s ease;
}

.bar-fill.affection {
  background: linear-gradient(90deg, #ff7eb3, #ff5f9e);
}

.bar-fill.trust {
  background: linear-gradient(90deg, #7eb3ff, #5f9eff);
}

.bar-value {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
  width: 28px;
  text-align: right;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  transition: all 0.3s;
}

.status-dot.idle {
  background: #5eff7e;
  box-shadow: 0 0 8px rgba(94, 255, 126, 0.6);
}

.status-dot.listening {
  background: #5e9eff;
  box-shadow: 0 0 8px rgba(94, 158, 255, 0.6);
  animation: pulse 1.5s ease-in-out infinite;
}

.status-dot.thinking {
  background: #ffb85e;
  box-shadow: 0 0 8px rgba(255, 184, 94, 0.6);
  animation: pulse 1.2s ease-in-out infinite;
}

.status-dot.speaking {
  background: #ff5ea0;
  box-shadow: 0 0 8px rgba(255, 94, 160, 0.6);
  animation: pulse 1s ease-in-out infinite;
}

.status-text {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.7);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
