import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

function getBackendPort() {
  try {
    const portFile = path.resolve(__dirname, '../backend/.active_port')
    if (fs.existsSync(portFile)) {
      const p = fs.readFileSync(portFile, 'utf8').trim()
      if (p && !isNaN(p)) return parseInt(p, 10)
    }
  } catch {}
  return process.env.VITE_BACKEND_PORT ? parseInt(process.env.VITE_BACKEND_PORT, 10) : 8000
}

const backendPort = getBackendPort()
const backendTarget = `http://127.0.0.1:${backendPort}`

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/static': {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
})
