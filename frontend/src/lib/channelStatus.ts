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

// ============================================================
// [P1 · DENETİM 2026-10-16] PROFİL DERİN TARAMA DEFTERİ
//
// Bulunan profil URL'leri artık GERÇEKTEN taranır. Her URL için backend
// bir defter satırı yazar: {url, platform, handle, capability_id, status,
// reason, post_count}. UI bu satırı olduğu gibi gösterir — "bağlandı"
// gibi ölçülmemiş bir dil KULLANILMAZ.
// ============================================================

export interface ScannedUrl {
  url: string;
  platform?: string;
  handle?: string;
  capability_id?: string | null;
  status: ChannelState;
  reason?: string | null;
  detail?: string | null;
  post_count?: number;
}

/** Taranmış profil URL'si için tek satırlık dürüst özet. */
export function scannedUrlText(row: ScannedUrl): string {
  const name = row.handle || row.url;
  if (row.status === 'ok') {
    const count = row.post_count ?? 0;
    return `${name}: kazandı (${count} gönderi)`;
  }
  if (row.status === 'failed') {
    return `${name}: ÇALIŞMADI — hata: ${reasonLabel(row.reason)}`;
  }
  return `${name}: ÇALIŞMADI — ${reasonLabel(row.reason)}`;
}

/** Derin tarama defterinin özeti (kaç kazandı / kaçı koşmadı). */
export function scannedSummary(rows: ScannedUrl[] | null | undefined): {
  total: number;
  ok: number;
  not_run: number;
  failed: number;
  posts: number;
} {
  const list = Array.isArray(rows) ? rows : [];
  return {
    total: list.length,
    ok: list.filter((r) => r && r.status === 'ok').length,
    not_run: list.filter((r) => r && r.status === 'not_run').length,
    failed: list.filter((r) => r && r.status === 'failed').length,
    posts: list.reduce((sum, r) => sum + (r?.post_count ?? 0), 0),
  };
}

/** [P2 · DENETİM 2026-10-16] Çapraz profil eşleşmesi (deterministik sinyaller). */
export interface CrossProfileMatch {
  source_platform: string;
  source_handle: string;
  source_url?: string;
  target_platform: string;
  target_handle: string;
  target_url?: string;
  match_method: string;
  /** KAPSAM skoru — olasılık DEĞİLDİR. */
  coverage: number;
  confidence_label: string;
  epistemic_type: string;
  signals?: string[];
}

/** Sinyal adını insan diline çevirir (kanıt izi, iddia değil). */
export function crossProfileSignalText(signal: string): string {
  switch (signal) {
    case 'self_declared_link':
      return 'biyografideki bağlantı';
    case 'exact_handle':
      return 'birebir aynı kullanıcı adı';
    case 'normalized_handle':
      return 'kullanıcı adı varyantı';
    case 'shared_platform_id':
      return 'ortak platform kimliği';
    default:
      return signal;
  }
}

/** Eşleşmeyi "kapsam" etiketiyle özetler — olasılık dili kullanılmaz. */
export function crossProfileText(row: CrossProfileMatch): string {
  const signals = (row.signals || []).map(crossProfileSignalText).join(' + ');
  const scope = row.confidence_label || 'kapsam';
  return `${row.source_platform}/@${row.source_handle} ↔ ${row.target_platform}/@${row.target_handle} · ${signals || 'eşleşme'} · ${scope} ${row.coverage.toFixed(2)}`;
}
