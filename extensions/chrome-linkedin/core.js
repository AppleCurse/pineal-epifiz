// Atlas Epifiz — LinkedIn içerik betiği (SAF çekirdek)
//
// Bu dosya tarayıcıdan BAĞIMSIZDIR: `document`, `chrome`, `fetch` gibi
// global'lere dokunmaz. Bu yüzden Node ile (eklenti yüklemeden) ölçülebilir:
// tests/edge/linkedin_extension.mjs. `content.js` bu çekirdeği kullanır.
//
// [2026-11-11 · SAHTE SONUÇ TEMİZLİĞİ] Ölçülen üç kusur:
//   1. Panel, hedef adı DOM'dan bulamazsa "LinkedIn Profili" UYDURUYORDU ve
//      bunu gerçek hedef gibi gösteriyordu. Artık ad yoksa `name: ''` döner ve
//      panel "HEDEF TESPİT EDİLEMEDİ" der; analiz butonu KAPALI kalır (URL'siz
//      görev açmak, sunucudan uydurma sonuç istemekle aynı şeydir).
//   2. URL yoksa/geçersizse yine istek atılıyordu. Artık `planAnalysis()`
//      isteği HİÇ kurmaz ve nedenini söyler.
//   3. Boş graf "boş" gibi değil, sebebiyle gösterilir; `reason` bilinmiyorsa
//      uydurma metin değil ham sebep yazılır.
'use strict';

const BACKEND_URL = 'http://127.0.0.1:8000';

//: Sunucunun `reason` kodları → operatör metni. Listede OLMAYAN sebep
//: uydurulmaz, HAM gösterilir (bilinmeyen sebebi "kanıt yok" diye yazmak,
//: olmayan bir teşhis koymaktır).
const REASON_TEXT = {
  no_evidence: 'Görev belleğinde kanıt yok — graf üretilmedi.',
  no_nodes: 'Kanıttan düğüm çıkarılamadı.',
};

const TARGET_MISSING_TEXT = 'HEDEF TESPİT EDİLEMEDİ';

/** Sunucu hatasını operatör diline çevirir (davranış korunur). */
function serverError(status, body) {
  const code = body?.error?.code || '';
  const msg = body?.error?.message || body?.detail || '';
  if (status === 423) return `KASA KİLİTLİ (423). ${msg || 'Konsoldan kasayı aç, sonra tekrar dene.'}`;
  if (status === 451) return `ÇOCUK KİLİDİ (451). ${msg || 'Operatör beyanı gerekiyor.'}`;
  if (status === 429) return `HIZ LİMİTİ (429). ${msg || 'Dakikada 5 görev; biraz bekle.'}`;
  if (status === 401) return `KİMLİK REDDEDİLDİ (401). Token gir (eklenti simgesi). ${msg}`;
  if (status === 403) return `ODA REDDEDİLDİ (403). ${msg || 'Bu oda başka operatöre kayıtlı.'}`;
  return `HTTP ${status}${code ? ' · ' + code : ''} ${msg}`.trim();
}

/** Hedef URL gerçekten bir LinkedIn profil adresi mi? (uydurma yok) */
function isLinkedInProfileUrl(url) {
  if (typeof url !== 'string') return false;
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return false;
  const host = parsed.hostname.toLowerCase().replace(/\.$/, '');
  if (host !== 'linkedin.com' && !host.endsWith('.linkedin.com')) return false;
  return /^\/in\/[A-Za-z0-9\-_%.]+\/?$/.test(parsed.pathname);
}

/**
 * Panel hedefini, DOM'dan okunan ham alanlardan üretir.
 * @param {{name?: string, title?: string, url?: string, canonical?: string}} raw
 */
function extractProfileData(raw = {}) {
  const name = String(raw.name || '').trim();
  const title = String(raw.title || '').trim();
  const url = String(raw.canonical || raw.url || '').split('?')[0].trim();
  return {
    name,
    title,
    url,
    // Ad ve geçerli URL YOKSA hedef yoktur; panel bunu açıkça söyler.
    hasTarget: Boolean(name) && isLinkedInProfileUrl(url),
    display: name ? `${name} (${title || 'LinkedIn'})` : TARGET_MISSING_TEXT,
  };
}

/**
 * Analiz isteğini kurar — kurulamıyorsa isteği ÜRETMEZ ve nedenini döner.
 * @returns {{ok: true, body: object} | {ok: false, reason: string}}
 */
function planAnalysis(profile, clientId) {
  const target = profile || extractProfileData({});
  if (!String(clientId || '').trim()) {
    return { ok: false, reason: 'İstemci kimliği yok (eklenti ayarları okunamadı).' };
  }
  if (!target.hasTarget) {
    return {
      ok: false,
      reason: `${TARGET_MISSING_TEXT} — bu sayfada profil adı/URL'si okunamadı; istek GÖNDERİLMEDİ.`,
    };
  }
  return {
    ok: true,
    body: {
      client_id: clientId,
      url: target.url,
      rituals: '',
      playlist: '',
      envies: '',
      scraper_type: 'cross',
    },
  };
}

/**
 * Graf yanıtını paneller için normalize eder. İçerik UYDURULMAZ:
 * sayılar sunucudan geldiği gibi, sebep bilinmiyorsa ham hâliyle.
 * @returns {{state: 'graph'|'empty'|'error', note: string, nodes: Array<{kind:string,label:string,evidence:number}>}}
 */
function normalizeGraph(payload) {
  const g = payload || {};
  if (g.available && Array.isArray(g.nodes) && g.nodes.length > 0) {
    const nodes = g.nodes.map((n) => ({
      kind: String(n?.kind || 'unknown'),
      label: String(n?.label || '—'),
      evidence: Number.isFinite(n?.evidence_count) ? n.evidence_count : 0,
    }));
    return {
      state: 'graph',
      note: `${g.node_count ?? nodes.length} düğüm · ${g.edge_count ?? 0} kenar${g.machine_note ? ` · ${g.machine_note}` : ''}`,
      nodes,
    };
  }
  const reason = String(g.reason || '').trim();
  return {
    state: 'empty',
    note: reason ? REASON_TEXT[reason] || `Sebep: ${reason}` : 'Sebep bildirilmedi (sunucu gerekçe döndürmedi).',
    nodes: [],
  };
}

/** Hata gövdesini panel durumuna çevirir (dürüst: sunucu metni aynen). */
function normalizeError(status, body) {
  return { state: 'error', note: serverError(status, body), nodes: [] };
}

const AtlasLinkedInCore = {
  BACKEND_URL,
  REASON_TEXT,
  TARGET_MISSING_TEXT,
  serverError,
  isLinkedInProfileUrl,
  extractProfileData,
  planAnalysis,
  normalizeGraph,
  normalizeError,
};

// Klasik content-script dünyası: core.js manifest sırasıyla ÖNCE yüklenir ve
// çekirdeğini açıkça paylaşır (content.js bunu window.AtlasLinkedInCore'dan
// okur). Node testleri için CommonJS dışa aktarım korunur.
if (typeof window !== 'undefined') {
  window.AtlasLinkedInCore = AtlasLinkedInCore;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = AtlasLinkedInCore;
}
