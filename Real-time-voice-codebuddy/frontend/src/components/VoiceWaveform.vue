<template>
  <div class="voice-waveform">
    <div
      v-for="(bar, i) in bars"
      :key="i"
      class="wave-bar"
      :class="barClass"
      :style="{ height: bar.height + '%' }"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'

const props = defineProps({
  state: { type: String, default: 'idle' },
  volume: { type: Number, default: 0 },
  barCount: { type: Number, default: 24 },
})

const bars = ref(Array.from({ length: props.barCount }, () => ({ height: 8 })))
let animFrame = null

const barClass = computed(() => props.state)

watch(() => props.volume, (vol) => {
  const newBars = bars.value.map(() => {
    const base = props.state === 'idle' ? 6 : 12
    const randomFactor = Math.random() * 0.6 + 0.4
    const h = base + vol * 80 * randomFactor
    return { height: Math.min(95, h) }
  })
  bars.value = newBars
})

// idle 状态下微弱动画
function idleAnimation() {
  if (props.state === 'idle' && props.volume === 0) {
    const newBars = bars.value.map(() => {
      const h = 4 + Math.random() * 8
      return { height: h }
    })
    bars.value = newBars
  }
  animFrame = requestAnimationFrame(idleAnimation)
}
idleAnimation()

onUnmounted(() => {
  if (animFrame) cancelAnimationFrame(animFrame)
})
</script>

<style scoped>
.voice-waveform {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 3px;
  height: 40px;
  padding: 4px 0;
}

.wave-bar {
  width: 4px;
  min-height: 3px;
  border-radius: 2px;
  transition: height 0.08s ease;
  background: rgba(255, 255, 255, 0.15);
}

.wave-bar.idle {
  background: rgba(255, 255, 255, 0.15);
}

.wave-bar.listening {
  background: rgba(80, 150, 255, 0.7);
  box-shadow: 0 0 4px rgba(80, 150, 255, 0.4);
}

.wave-bar.thinking {
  background: rgba(255, 180, 60, 0.7);
  box-shadow: 0 0 4px rgba(255, 180, 60, 0.4);
}

.wave-bar.speaking {
  background: rgba(255, 120, 180, 0.8);
  box-shadow: 0 0 6px rgba(255, 120, 180, 0.5);
}
</style>
