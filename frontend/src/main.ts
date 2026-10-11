import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'
import { enableGPUAcceleration } from './lib/tauriBridge'
import { APP_SIGNATURE } from './lib/version'

// Sürüm artık kopyalanmiyor: `lib/version.ts` üzerinden kök VERSION dosyasiyla
// senkron tutulur. Bu sabit build icinde korunur, CI grep ile dogrular.
const PINEAL_HERETIC_SIGNATURE = APP_SIGNATURE
if (typeof window !== 'undefined') {
  (window as any).__PINEAL_HERETIC__ = PINEAL_HERETIC_SIGNATURE
  console.info(`%c${PINEAL_HERETIC_SIGNATURE}`, 'color:#d4af37;font-weight:800;')
}

// Tauri katmaninda GPU hizlandirma: yalnizca CSS ipucu; gercek GPU durumu
// `get_system_info` tarafindan OLÇÜLEREK bildirilir, burada iddia edilmez.
enableGPUAcceleration()

const app = mount(App, {
  target: document.getElementById('app')!,
})

export default app
