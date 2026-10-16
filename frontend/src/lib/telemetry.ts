import { writable, get } from 'svelte/store';
import { apiFetch, clientId, vaultLocked } from '../store';

// ============================================================
// CANLI SİSTEM TELEMETRİSİ — göstergelerin DÜRÜST veri kaynağı.
//
// İlke: ibreler yalnızca gerçekten ölçülen değerleri gösterir.
// Backend'e ulaşılamazsa ok=false olur, ibreler park konumuna
// çekilir ve okuma "—" basar. ASLA sentetik/uydurma değer yok.
// ============================================================

export type UplinkState = 'ONLINE' | 'OFFLINE';
export const uplinkState = writable<UplinkState>('OFFLINE');

export interface HealthSnapshot {
  ok: boolean;
  status: string; // ready | degraded | failed | unreachable
  ready: number;
  total: number;
  integrityPct: number; // 0..100
  latencyMs: number | null; // son /health ping süresi
  updatedAt: number;
}

export const health = writable<HealthSnapshot>({
  ok: false,
  status: 'unknown',
  ready: 0,
  total: 0,
  integrityPct: 0,
  latencyMs: null,
  updatedAt: 0,
});

export interface SysTelemetry {
  ok: boolean;
  gateway: boolean; // LLM geçidi canlı mı
  scraper: boolean; // kazıyıcı yeteneği
  browser: boolean; // chromium kurulu mu
  vault: boolean; // kasada çerez/anahtar var mı
  instagramSession: boolean; // canlı IG oturumu mühürlü mü
  spendUsd: number;
  spendCapUsd: number;
  activeReservations: number;
  taskRuns: number;
  // [P0 · DENETİM 2026-10-16] X sensörü + sebebi. "Kapalı" demek yetmez;
  // NEDEN kapalı olduğu da bilinir.
  xSensorReady: boolean;
  xSensorReason: string | null;
}

export const sysTelemetry = writable<SysTelemetry>({
  ok: false,
  gateway: false,
  scraper: false,
  browser: false,
  vault: false,
  instagramSession: false,
  spendUsd: 0,
  spendCapUsd: 0,
  activeReservations: 0,
  taskRuns: 0,
  xSensorReady: false,
  xSensorReason: null,
});

// THROTTLE düğmesi: ping aralığı (saniye) detentleri.
export const THROTTLE_DETENTS = [5, 10, 30];
export const throttleIdx = writable(1); // varsayılan 10 sn

// MIXTURE düğmesi: Aspasia TTS konuşma hızı detentleri.
export const TTS_DETENTS = [0.8, 1.0, 1.25];
export const ttsRate = writable(1.0);

let timer: ReturnType<typeof setInterval> | null = null;
let lastTick = 0;
let ticking = false;

async function pollOnce() {
  if (ticking) return;
  ticking = true;
  try {
    // 1) /health — bütünlük + gecikme ölçümü
    const t0 = performance.now();
    try {
      const res = await apiFetch('/health');
      const ms = Math.round(performance.now() - t0);
      if (!res.ok) throw new Error('http ' + res.status);
      const data = await res.json();
      const deps: Array<{ status?: string }> = Array.isArray(data.dependencies) ? data.dependencies : [];
      const ready = deps.filter((d) => d && d.status === 'ready').length;
      const total = deps.length;
      health.set({
        ok: true,
        status: String(data.status || 'unknown'),
        ready,
        total,
        integrityPct: total > 0 ? Math.round((ready / total) * 100) : 0,
        latencyMs: ms,
        updatedAt: Date.now(),
      });
    } catch {
      // Başarısız ping: son iyi değerler korunur ama ok=false → ibreler park eder.
      health.update((h) => ({ ...h, ok: false, status: 'unreachable', latencyMs: null }));
    }

    // 2) /api/telemetry — geçit/kazıyıcı/harcama bayrakları
    try {
      const res = await apiFetch(`/api/telemetry?client_id=${get(clientId)}`);
      if (!res.ok) throw new Error('http ' + res.status);
      const t = await res.json();
      sysTelemetry.set({
        ok: true,
        gateway: !!t.gateway,
        scraper: !!(t.scraper || t.instagram_scraper),
        browser: !!t.browser_installed,
        vault: !!t.vault,
        instagramSession: !!t.instagram_session,
        spendUsd: Number(t.llm_spend_usd || 0),
        spendCapUsd: Number(t.llm_spend_cap_usd || 0),
        activeReservations: Number(t.llm_active_reservations || 0),
        taskRuns: Number((t.task_lifecycle || {}).runs || 0),
        // [P0] X sensörü: hazır mı + NEDEN değil.
        xSensorReady: !!t.x_scraper,
        xSensorReason: t.x_scraper_reason ? String(t.x_scraper_reason) : null,
      });
      if (t.vault_locked !== undefined) {
        vaultLocked.set(!!t.vault_locked);
      }
    } catch {
      sysTelemetry.update((s) => ({ ...s, ok: false }));
    }
  } finally {
    ticking = false;
  }
}

export function startHealthPoll() {
  stopHealthPoll();
  lastTick = 0;
  // 1 sn çözünürlüklü zamanlayıcı; detent değişince aralığı kendisi uyarlar.
  timer = setInterval(() => {
    const intervalMs = THROTTLE_DETENTS[get(throttleIdx)] * 1000;
    if (Date.now() - lastTick >= intervalMs) {
      lastTick = Date.now();
      void pollOnce();
    }
  }, 1000);
  void pollOnce();
}

export function stopHealthPoll() {
  if (timer) clearInterval(timer);
  timer = null;
}
