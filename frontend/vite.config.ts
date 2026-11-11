import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const host = process.env.TAURI_DEV_HOST

// https://vite.dev/config/ + https://v2.tauri.app/reference/config/
export default defineConfig({
  root: __dirname,
  plugins: [svelte()],
  clearScreen: false,
  envPrefix: ['VITE_', 'TAURI_'],
  server: {
    host: host || '0.0.0.0',
    port: 1420,
    strictPort: true,
    allowedHosts: true,
    hmr: host
      ? {
          port: 1421,
        }
      : undefined,
    proxy: {
      // [SMOKE 2026-11-11] `/health` kökte yaşıyor (backend/routes altında değil)
      // ama SPA `apiFetch('/health')` ile göreli çağırıyor. Proxy'de yalnız
      // `/api` ve `/ws` varken bu istek Vite'a düşüp 404 alıyordu: telemetri
      // paneli geliştirme modunda HER ZAMAN "offline" görünüyordu (gerçek
      // tarayıcıda ölçüldü). Kök sağlık ucu da backend'e taşınır.
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  },
  build: {
    target: process.env.TAURI_ENV_PLATFORM === 'windows' ? 'chrome105' : 'safari13',
    minify: !process.env.TAURI_ENV_DEBUG ? 'esbuild' : false,
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
  },
})
