<template>
  <div class="waveform-container">
    <div class="waveform">
      <div v-for="i in barCount" :key="i" class="bar"
        :class="{ active: isActive, ai: isAi }"
        :style="{
          height: barHeight(i) + '%',
          animationDelay: (i * 0.08) + 's',
        }"
      />
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  volume: { type: Number, default: 0 },
  isActive: { type: Boolean, default: false },
  isAi: { type: Boolean, default: false },
})

const barCount = 32

function barHeight(i) {
  if (!props.isActive && !props.isAi) return 3
  const t = Date.now() / 200
  const seed = Math.sin(i * 0.7 + t) * 0.5 + 0.5
  const vol = props.isAi ? 0.6 : Math.max(0.08, props.volume)
  return Math.max(3, seed * vol * 100)
}
</script>

<style scoped>
.waveform-container {
  width: 100%;
  padding: 0 8px;
}
.waveform {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 3px;
  height: 48px;
}
.bar {
  flex: 1;
  border-radius: 2px;
  background: rgba(255,255,255,0.06);
  transition: height 0.1s ease;
}
.bar.active {
  background: linear-gradient(180deg, #42a5f5 0%, rgba(66,165,245,0.3) 100%);
}
.bar.ai {
  background: linear-gradient(180deg, #ec407a 0%, rgba(236,64,122,0.3) 100%);
}
</style>
