import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      // /api/* → http://localhost:8002 (same-origin화 — cross-origin download 문제 해결)
      // EventSource(SSE)는 브라우저가 직접 연결하므로 proxy 경유 가능
      '/api': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
    },
  },
})
