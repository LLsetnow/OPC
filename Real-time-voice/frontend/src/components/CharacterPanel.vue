<template>
  <div class="character-panel">
    <div class="character-avatar" :class="statusClass">
      <div class="avatar-circle">
        <svg viewBox="0 0 120 120" class="avatar-svg">
          <!-- Simple anime-style face SVG -->
          <defs>
            <radialGradient id="hairGrad" cx="50%" cy="30%">
              <stop offset="0%" stop-color="#6b4c8a"/>
              <stop offset="100%" stop-color="#3a2050"/>
            </radialGradient>
            <radialGradient id="skinGrad" cx="50%" cy="50%">
              <stop offset="0%" stop-color="#ffe4c4"/>
              <stop offset="100%" stop-color="#f5c6a0"/>
            </radialGradient>
          </defs>
          <!-- Hair back -->
          <ellipse cx="60" cy="30" rx="44" ry="40" fill="url(#hairGrad)"/>
          <!-- Face -->
          <ellipse cx="60" cy="55" rx="32" ry="35" fill="url(#skinGrad)"/>
          <!-- Hair bangs -->
          <path d="M28 35 Q60 10 92 35 Q88 50 85 42 Q75 30 60 28 Q45 30 35 42 Q32 50 28 35Z" fill="url(#hairGrad)"/>
          <!-- Side hair -->
          <path d="M28 35 Q25 60 30 85 Q32 90 36 85 Q34 60 32 40Z" fill="url(#hairGrad)"/>
          <path d="M92 35 Q95 60 90 85 Q88 90 84 85 Q86 60 88 40Z" fill="url(#hairGrad)"/>
          <!-- Eyes -->
          <ellipse cx="50" cy="52" rx="7" ry="8" fill="white"/>
          <ellipse cx="70" cy="52" rx="7" ry="8" fill="white"/>
          <ellipse cx="51" cy="53" rx="4.5" ry="5.5" fill="#5a3a7a"/>
          <ellipse cx="71" cy="53" rx="4.5" ry="5.5" fill="#5a3a7a"/>
          <circle cx="52.5" cy="51" r="1.8" fill="white"/>
          <circle cx="72.5" cy="51" r="1.8" fill="white"/>
          <!-- Eyebrows -->
          <path d="M42 44 Q50 41 57 44" fill="none" stroke="#4a3060" stroke-width="1.5" stroke-linecap="round"/>
          <path d="M63 44 Q70 41 78 44" fill="none" stroke="#4a3060" stroke-width="1.5" stroke-linecap="round"/>
          <!-- Blush -->
          <ellipse cx="43" cy="60" rx="6" ry="3.5" fill="#ffb3b3" opacity="0.35"/>
          <ellipse cx="77" cy="60" rx="6" ry="3.5" fill="#ffb3b3" opacity="0.35"/>
          <!-- Nose -->
          <path d="M58 57 L60 61 L62 57" fill="none" stroke="#d4a882" stroke-width="1"/>
          <!-- Mouth -->
          <path d="M53 67 Q60 72 67 67" fill="none" stroke="#d49090" stroke-width="2" stroke-linecap="round"/>
          <!-- Hair ornament -->
          <circle cx="85" cy="38" r="5" fill="#ff6b9d" opacity="0.8"/>
        </svg>
      </div>
      <div class="status-dot" :class="statusClass" />
    </div>

    <div class="character-name">Yuki</div>
    <div class="character-desc">妹妹 · 恋人</div>

    <div class="stats">
      <div class="stat-row">
        <span class="stat-label">好感度</span>
        <div class="stat-bar">
          <div class="stat-fill affection" :style="{ width: affectionPercent + '%' }" />
        </div>
        <span class="stat-value">{{ affection }}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">信任度</span>
        <div class="stat-bar">
          <div class="stat-fill trust" :style="{ width: trustPercent + '%' }" />
        </div>
        <span class="stat-value">{{ trust }}</span>
      </div>
    </div>

    <div class="tags">
      <span class="tag">热情主动</span>
      <span class="tag">大胆表达</span>
      <span class="tag">撒娇依恋</span>
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

const statusClass = computed(() => `state-${props.state}`)

const affectionPercent = computed(() => Math.min(100, Math.max(0, 50 + props.affection * 5)))
const trustPercent = computed(() => Math.min(100, Math.max(0, 50 + props.trust * 5)))
</script>

<style scoped>
.character-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 16px;
}
.character-avatar {
  position: relative;
  width: 140px;
  height: 140px;
  border-radius: 50%;
  background: rgba(255,255,255,0.04);
  backdrop-filter: blur(10px);
  border: 2px solid rgba(255,255,255,0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.4s ease;
  box-shadow: 0 0 30px rgba(160,120,220,0.15);
}
.character-avatar.state-speaking {
  box-shadow: 0 0 50px rgba(255,120,180,0.3), 0 0 30px rgba(160,120,220,0.2);
  transform: scale(1.02);
}
.character-avatar.state-listening {
  box-shadow: 0 0 50px rgba(120,160,255,0.3), 0 0 30px rgba(120,160,220,0.2);
}
.character-avatar.state-thinking {
  box-shadow: 0 0 50px rgba(255,160,80,0.3), 0 0 30px rgba(220,160,80,0.2);
}
.avatar-circle {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  overflow: hidden;
  background: radial-gradient(circle, rgba(200,180,220,0.2) 0%, rgba(100,80,140,0.1) 100%);
}
.avatar-svg {
  width: 100%;
  height: 100%;
}
.status-dot {
  position: absolute;
  bottom: 10px;
  right: 10px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(0,0,0,0.4);
  transition: all 0.4s ease;
}
.status-dot.state-idle { background: #66bb6a; box-shadow: 0 0 8px rgba(102,187,106,0.5); }
.status-dot.state-listening { background: #42a5f5; box-shadow: 0 0 12px rgba(66,165,245,0.6); animation: pulse-dot 1s ease-in-out infinite; }
.status-dot.state-thinking { background: #ffa726; box-shadow: 0 0 12px rgba(255,167,38,0.6); animation: pulse-dot 1s ease-in-out infinite; }
.status-dot.state-speaking { background: #ec407a; box-shadow: 0 0 12px rgba(236,64,122,0.6); animation: pulse-dot 0.6s ease-in-out infinite; }
@keyframes pulse-dot {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.4); }
}
.character-name {
  font-size: 22px;
  font-weight: 700;
  color: #e0d0f0;
  letter-spacing: 2px;
}
.character-desc {
  font-size: 13px;
  color: rgba(200,180,220,0.6);
  margin-top: -4px;
}
.stats {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}
.stat-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.stat-label {
  font-size: 12px;
  color: rgba(200,180,220,0.6);
  width: 42px;
  text-align: right;
}
.stat-bar {
  flex: 1;
  height: 6px;
  background: rgba(255,255,255,0.06);
  border-radius: 3px;
  overflow: hidden;
}
.stat-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s ease;
}
.stat-fill.affection { background: linear-gradient(90deg, #ec407a, #f06292); }
.stat-fill.trust { background: linear-gradient(90deg, #42a5f5, #64b5f6); }
.stat-value {
  font-size: 12px;
  color: rgba(200,180,220,0.8);
  width: 24px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
  margin-top: 8px;
}
.tag {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 12px;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.08);
  color: rgba(200,180,220,0.7);
}
</style>
