import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/ws': {
        target: 'ws://127.0.0.1:9902',
        ws: true,
      },
      '/api': {
        target: 'http://127.0.0.1:9902',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
