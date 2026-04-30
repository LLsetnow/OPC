<template>
  <div class="particle-bg">
    <div v-for="p in particles" :key="p.id" class="particle"
      :style="{
        left: p.x + '%',
        top: p.y + '%',
        width: p.size + 'px',
        height: p.size + 'px',
        animationDelay: p.delay + 's',
        animationDuration: p.duration + 's',
        opacity: p.opacity,
      }"
    />
  </div>
</template>

<script setup>
const particles = Array.from({ length: 30 }, (_, i) => ({
  id: i,
  x: Math.random() * 100,
  y: Math.random() * 100,
  size: 1.5 + Math.random() * 3,
  delay: Math.random() * 8,
  duration: 6 + Math.random() * 12,
  opacity: 0.2 + Math.random() * 0.4,
}))
</script>

<style scoped>
.particle-bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
  background: linear-gradient(135deg, #0a0a1a 0%, #1a1040 40%, #0d1b3e 70%, #0a0a1a 100%);
}
.particle {
  position: absolute;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(180,160,255,0.8) 0%, rgba(120,100,220,0) 70%);
  animation: float-up linear infinite;
}
@keyframes float-up {
  0% { transform: translateY(0) scale(1); opacity: 0; }
  10% { opacity: var(--op, 0.4); }
  90% { opacity: var(--op, 0.4); }
  100% { transform: translateY(-120vh) scale(0.3); opacity: 0; }
}
</style>
