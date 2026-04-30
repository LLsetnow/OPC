<template>
  <div class="character-panel">
    <div class="character-avatar" :class="stateClass">
      <div class="avatar-glow" />
      <svg viewBox="0 0 200 280" class="yuki-svg" xmlns="http://www.w3.org/2000/svg">
        <!-- 头发 -->
        <ellipse cx="100" cy="90" rx="65" ry="70" fill="#2a1a4e" />
        <!-- 脸 -->
        <ellipse cx="100" cy="100" rx="48" ry="52" fill="#fde8d8" />
        <!-- 眼睛 -->
        <ellipse cx="82" cy="95" rx="8" ry="10" fill="#6a4fb8">
          <animate attributeName="ry" values="10;1;10" dur="4s" repeatCount="indefinite" begin="2s" />
        </ellipse>
        <ellipse cx="118" cy="95" rx="8" ry="10" fill="#6a4fb8">
          <animate attributeName="ry" values="10;1;10" dur="4s" repeatCount="indefinite" begin="2s" />
        </ellipse>
        <!-- 眼睛高光 -->
        <circle cx="85" cy="91" r="3" fill="white" />
        <circle cx="121" cy="91" r="3" fill="white" />
        <!-- 嘴巴 -->
        <path d="M92 115 Q100 122 108 115" stroke="#e87a90" stroke-width="2" fill="none" />
        <!-- 腮红 -->
        <ellipse cx="72" cy="110" rx="10" ry="6" fill="rgba(255,150,170,0.3)" />
        <ellipse cx="128" cy="110" rx="10" ry="6" fill="rgba(255,150,170,0.3)" />
        <!-- 身体 -->
        <path d="M60 150 Q100 140 140 150 L150 280 L50 280 Z" fill="#4a3a8a" />
        <path d="M80 150 Q100 145 120 150 L115 200 L85 200 Z" fill="#fde8d8" />
        <!-- 头发装饰 -->
        <circle cx="130" cy="60" r="6" fill="#ff7eb3" />
        <path d="M60 75 Q55 50 70 40" stroke="#2a1a4e" stroke-width="8" fill="none" />
      </svg>
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

.yuki-svg {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
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
