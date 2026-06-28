import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  server: {
    // allow access over the LAN via mDNS hostnames (e.g. my-server.local)
    allowedHosts: ['.local'],
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
