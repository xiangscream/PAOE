import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

const apiTarget = process.env.POE_API_TARGET || 'http://127.0.0.1:8780'

export default defineConfig({
  plugins: [vue()],
  base: './',
  server: {
    port: 5173,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: false },
    },
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.ts'],
  },
})
