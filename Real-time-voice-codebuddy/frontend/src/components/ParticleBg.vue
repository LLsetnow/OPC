<template>
  <div class="particle-bg">
    <div
      v-for="p in particles"
      :key="p.id"
      class="particle"
      :style="p.style"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const particles = ref([])

onMounted(() => {
  const count = 30
  for (let i = 0; i < count; i++) {
    const size = Math.random() * 4 + 1
    const x = Math.random() * 100
    const y = Math.random() * 100
    const duration = Math.random() * 20 + 15
    const delay = Math.random() * -20
    const opacity = Math.random() * 0.5 + 0.1

    particles.value.push({
      id: i,
      style: {
        width: `${size}px`,
        height: `${size}px`,
        left: `${x}%`,
        top: `${y}%`,
        opacity,
        animationDuration: `${duration}s`,
        animationDelay: `${delay}s`,
      },
    })
  }
})
</script>

<style scoped>
.particle-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

.particle {
  position: absolute;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(180, 160, 255, 0.8), rgba(100, 120, 255, 0.2));
  animation: float linear infinite;
}

@keyframes float {
  0% {
    transform: translateY(0) translateX(0);
    opacity: 0;
  }
  10% {
    opacity: 1;
  }
  90% {
    opacity: 1;
  }
  100% {
    transform: translateY(-100vh) translateX(30px);
    opacity: 0;
  }
}
</style>
