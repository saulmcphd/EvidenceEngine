import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Local-first app: built assets are served by the FastAPI backend from any path, so use relative base.
// During dev, /api is proxied to the FastAPI backend on :8000.
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
