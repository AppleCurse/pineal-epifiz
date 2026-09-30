import { writable, get } from 'svelte/store';

// API adresi tek yerden yönetilir:
//  - Üretimde (FastAPI aynı origin'de servis eder): window.location.origin kullanılır.
//  - Geliştirmede (vite:5173 -> backend:8000): frontend/.env içinde VITE_API_BASE=http://127.0.0.1:8000 tanımlanır.
const envBase = (import.meta.env && (import.meta.env as any).VITE_API_BASE) as string | undefined;
const origin = typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000';

export const API_BASE = (envBase && envBase.trim()) || origin;
export const WS_BASE = API_BASE.replace(/^http/, 'ws');

// FAZ 3: PINEAL_TOKEN kipinde UI da kimligini tasir.
// [AUDIT 2026-09-11 P0] Token kaynağı TEK: çalışma zamanı. Kullanıcı arayüzden
// (Kasa -> "API ERİŞİM ANAHTARI") girdiği token localStorage'da kalıcı.
// Derleme zamanı gömme (eski VITE_PINEAL_TOKEN) KALDIRILDI: Vite VITE_*
// değerlerini bundle'a plaintext derlediği için server secret'ı statik
// asset'e dönüşüyordu — secret olmaktan çıkıyordu. Token girilmezse
// arayüz 401'de dürüst hata gösterir (bkz. App.svelte onclose +
// UnifiedCompactPanel hata yolları); "ağ hatası" maskesi yok.
const TOKEN_STORAGE_KEY = 'pineal_api_token';

function readStoredToken(): string {
  if (typeof window === 'undefined') return '';
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

export const apiToken = writable<string>(readStoredToken());

export function currentApiToken(): string {
  return get(apiToken).trim();
}

export function setApiToken(value: string): void {
  const v = (value || '').trim();
  apiToken.set(v);
  try {
    if (v) localStorage.setItem(TOKEN_STORAGE_KEY, v);
    else localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    /* localStorage erişilemiyorsa sessizce geç; token oturum boyunca bellekte kalır */
  }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const token = currentApiToken();
  if (token) headers.set('X-API-Key', token);
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

// 401/403 yanıtını ağ hatasından ayırır; arayüzün dürüst mesaj basması için tek yardımcı.
export function isAuthFailure(res: Response): boolean {
  return res.status === 401 || res.status === 403;
}

export function wsUrl(clientId: string): string {
  // Secrets never enter URLs or proxy/access logs. The socket authenticates
  // with its first message instead.
  return `${WS_BASE}/ws/${clientId}`;
}

// Benzersiz bir istemci kimliği (session/tarayıcı boyunca sabit kalır)
function getOrCreateClientId(): string {
  try {
    if (typeof localStorage !== 'undefined') {
      let stored = localStorage.getItem('pineal_client_id');
      if (!stored) {
        stored = `client_${Math.random().toString(36).substring(2, 9)}`;
        localStorage.setItem('pineal_client_id', stored);
      }
      return stored;
    }
  } catch (_e) {}
  return `client_${Math.random().toString(36).substring(2, 9)}`;
}
export const clientId = writable(getOrCreateClientId());

// Global state
export const logs = writable<Array<{ts: string, level: string, msg: string}>>([]);
export const taskStatus = writable<any>(null);
export const isProcessing = writable(false);
export const telemetryEvents = writable<any[]>([]);
export const agentStatuses = writable<Record<string, { status: string; updatedAt: number; metadata?: any }>>({});
// [RÖNTGEN 2026-09-23] Ajan durumlarının GERÇEK kaynağı (backend beyanı):
//   'redis_bus'  -> Redis Pub/Sub canlı
//   'fallback'   -> Redis yok, süreç-içi bellek
//   'error'      -> tracker okunamadı
//   'unreachable'-> API'ye hiç ulaşılamadı
//   'none'       -> henüz hiçbir yanıt yok
// UI bu etiketi basar; "REDIS PUB/SUB" yazısı artık varsayılan SÜS değil.
export const agentStatusSource = writable<'redis_bus' | 'in_memory' | 'fallback' | 'error' | 'unreachable' | 'none'>('none');
export const vaultLocked = writable<boolean>(true);
export const activeViewMode = writable<'warroom' | 'cockpit'>(
  (typeof localStorage !== 'undefined' && (localStorage.getItem('pineal_view_mode') as 'warroom' | 'cockpit')) || 'warroom'
);
export const inspectedAgentId = writable<string | null>(null);

// Scraper vb. state'ler
export const scrapedUsername = writable('');
export const scrapedBio = writable('');
export const scrapedPosts = writable<string[]>([]);
export const isScraping = writable(false);
export const autoTriggerLLM = writable(false);

// ==========================================
// ANALOG KONSOL KONTROLLERİ (POWER · SIGINT)
// ==========================================
export const armEngaged = writable<boolean>(false);
export const sigintEngaged = writable<boolean>(false);
export const recordEngaged = writable<boolean>(true);
export const keyUnlocked = writable<boolean>(false);
// POWER: uplink (WebSocket) ana şalteri. Kapalıysa soket kapatılır ve
// otomatik yeniden bağlanma durur (App.svelte abonesi yönetir).
export const powerEngaged = writable<boolean>(true);

// Merkez göz: giriş perdesinde yüklenen özel göz fotoğrafı, kokpit
// ortasındaki gözle aynı kaynaktan beslenir (localStorage destekli).
const EYE_STORAGE_KEY = 'pineal_custom_eye';

function readStoredEye(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(EYE_STORAGE_KEY);
  } catch {
    return null;
  }
}

export const eyeImage = writable<string | null>(readStoredEye());

// i18n köprüsü
export { currentLang, type Language } from './i18n';

