import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'
import { enableGPUAcceleration } from './lib/tauriBridge'

// PINEAL-HERETIC v5.0 - Tauri native GPU + Redis Agent Rack live bridge
// Bu sabit build icinde korunur, CI grep ile dogrular
const PINEAL_HERETIC_SIGNATURE = 'PINEAL-HERETIC v5.0 - ATLAS PINEAL OBSERVATORY - Tauri Native GPU'
if (typeof window !== 'undefined') {
  (window as any).__PINEAL_HERETIC__ = PINEAL_HERETIC_SIGNATURE
  console.info(`%c${PINEAL_HERETIC_SIGNATURE}`, 'color:#d4af37;font-weight:800;')
}

// Tauri native GPU hızlandırma - tarayıcı sınırlarından kurtul
enableGPUAcceleration()

const app = mount(App, {
  target: document.getElementById('app')!,
})

export default app
