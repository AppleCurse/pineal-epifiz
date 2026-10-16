// ============================================================
// KANAL DURUMU — "ÇALIŞMADI: sebep" ETİKETLERİ
//
// [P0 · DENETİM 2026-10-16] Backend artık her sensör/araştırma için
// "koştu (ok) / ÇALIŞMADI (not_run) / hata (failed)" + MAKİNE-OKUNUR sebep
// gönderiyor. Bu dosya o sebebi operatörün okuyacağı Türkçe metne çevirir.
//
// İlke: bilinmeyen sebep ASLA "başarılı" gibi gösterilmez; ham token
// parantez içinde aynen bırakılır (yanlış çeviri, yanlış güven üretir).
// ============================================================

export type ChannelState = 'ok' | 'not_run' | 'failed';

export interface ChannelRun {
  channel: string;
  status: ChannelState;
  reason?: string | null;
  detail?: string | null;
}

export interface CapabilityRow {
  id: string;
  kind: string;
  license: string;
  available: boolean;
  reason: string | null;
  gates: string[];
  policy_allowed: boolean | null;
  policy_reason: string | null;
  policy_gate: string | null;
}

// Makine-okunur sebep → okunur Türkçe etiket.
const REASON_LABELS: Record<string, string> = {
  vault_locked: 'kasa kilitli',
  no_session_pool: 'oturum hesabı yok (hesap havuzu boş)',
  no_session_pool_detail: 'oturum hesabı yok',
  user_not_found: 'kullanıcı bulunamadı',
  dependency_missing: 'bağımlılık kurulu değil',
  timeout: 'zaman aşımı',
  scrape_error: 'kazıma hatası',
  network_error: 'ağ hatası',
  provider_errors: 'sağlayıcı hataları',
  config_missing: 'yapılandırma eksik',
  library_missing: 'kütüphane kurulu değil',
  disabled: 'kapı kapalı',
  not_attempted: ' denenmedi',
  unknown: 'bilinmeyen sebep',
  extract_unavailable: 'çıkarım yapılamadı',
  scan_unavailable: 'tarama yapılamadı',
  invalid_username: 'geçersiz kullanıcı adı',
  unavailable: 'kullanılamıyor',
};

const CHANNEL_LABELS: Record<string, string> = {
  'sensor.x.twscrape': 'X sensörü',
  'sensor.ig.primary': 'Instagram kazıma',
  'sensor.ig.instagrapi': 'Instagram ikinci kaynak',
  'sensor.identity.maigret': 'Maigret kimlik taraması',
  'sensor.identity.holehe': 'Holehe e-posta taraması',
  'sensor.web.agent_reach': 'Agent-Reach okuma',
  'sensor.search.searxng': 'SearXNG arama',
  'search.web': 'Açık kaynak araması',
  'profile.deep_scan': 'Derin profil taraması',
  'extractor.identity.socid': 'SOCID kimlik çıkarımı',
  'extractor.web.trafilatura': 'Sayfa metni çıkarımı',
};

/** Makine-okunur sebebi okunur metne çevirir (bilinmeyen token aynen kalır). */
export function reasonLabel(reason?: string | null): string {
  if (!reason) return 'sebep yok';
  const raw = String(reason);
  if (REASON_LABELS[raw]) return REASON_LABELS[raw];
  // "gate_disabled:ENABLE_X_SENSOR" / "dependency_missing:twscrape" gibi
  // "a:b" biçimini bileşenlerine ayır.
  const idx = raw.indexOf(':');
  if (idx > 0) {
    const head = raw.slice(0, idx);
    const tail = raw.slice(idx + 1);
    const headLabel = REASON_LABELS[head];
    if (headLabel) return `${headLabel} (${tail})`;
    if (head === 'gate_disabled') return `bayrak kapalı: ${tail}`;
    if (head === 'dependency_missing') return `bağımlılık yok: ${tail}`;
    if (head === 'config_missing') return `yapılandırma eksik: ${tail}`;
    if (head === 'search_unavailable') return `arama motoru yok: ${tail}`;
  }
  return raw;
}

/** Kanal kimliğini okunur ada çevirir. */
export function channelLabel(channel?: string | null): string {
  if (!channel) return 'kanal';
  return CHANNEL_LABELS[channel] || channel;
}

/** Bir kanal kaydını "ÇALIŞMADI: sebep" biçiminde döndürür. */
export function channelStatusText(run: ChannelRun): string {
  const name = channelLabel(run.channel);
  if (run.status === 'ok') {
    return run.detail ? `${name}: çalıştı (${run.detail})` : `${name}: çalıştı`;
  }
  if (run.status === 'failed') {
    return `${name}: ÇALIŞMADI — hata: ${reasonLabel(run.reason)}`;
  }
  return `${name}: ÇALIŞMADI — ${reasonLabel(run.reason)}`;
}

/** "ÇALIŞMADI" olan kanalları süzer. */
export function blockedChannels(runs: ChannelRun[] | null | undefined): ChannelRun[] {
  if (!Array.isArray(runs)) return [];
  return runs.filter((r) => r && (r.status === 'not_run' || r.status === 'failed'));
}
