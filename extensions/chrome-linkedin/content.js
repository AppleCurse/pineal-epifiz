// Atlas Epifiz — LinkedIn Content Script
// Sözleşme: POST /api/initiate (X-API-Key) -> GET /api/tasks/{id}/graph.
// Kanıt yoksa panel DOLDURULMAZ; sunucu hatası AYNEN gösterilir.
(function () {
  if (window.__ATLAS_EPIFIZ_LOADED__) return;
  window.__ATLAS_EPIFIZ_LOADED__ = true;

  const BACKEND_URL = 'http://127.0.0.1:8000';
  const POLL_MS = 3000;
  const MAX_EMPTY = 12;
  const REASON = {
    no_evidence: 'Görev belleğinde kanıt yok — graf üretilmedi.',
    no_nodes: 'Kanıttan düğüm çıkarılamadı.',
  };

  let isPanelOpen = false;
  let isAnalyzing = false;
  let pollTimer = null;
  let emptyPolls = 0;
  let currentTask = '';
  let currentClient = '';

  // ── yardımcılar ────────────────────────────────────────────────
  async function settings() {
    const s = await chrome.storage.local.get(['pineal_token', 'atlas_client_id']);
    let cid = s.atlas_client_id;
    if (!cid) {
      cid = 'ext_' + Math.random().toString(36).slice(2, 9);
      await chrome.storage.local.set({ atlas_client_id: cid });
    }
    return { token: (s.pineal_token || '').trim(), clientId: cid };
  }

  function headers(token) {
    const h = { 'Content-Type': 'application/json' };
    if (token) h['X-API-Key'] = token;
    return h;
  }

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

  async function call(path, init) {
    const { token } = await settings();
    const res = await fetch(BACKEND_URL + path, {
      ...init,
      headers: { ...headers(token), ...(init?.headers || {}) },
    });
    let body = null;
    try { body = await res.json(); } catch { body = null; }
    if (!res.ok) throw new Error(serverError(res.status, body));
    return body;
  }

  function extractProfileData() {
    const nameEl = document.querySelector('h1.text-heading-xlarge') || document.querySelector('h1');
    const titleEl = document.querySelector('div.text-body-medium') || document.querySelector('.pv-text-details__left-panel h2');
    const canonical = document.querySelector('link[rel="canonical"]')?.href || window.location.href;
    return {
      name: nameEl ? nameEl.innerText.trim() : 'LinkedIn Profili',
      title: titleEl ? titleEl.innerText.trim() : '',
      url: canonical.split('?')[0],
    };
  }

  // ── DOM ────────────────────────────────────────────────────────
  function createFloatingButton() {
    if (document.getElementById('atlas-epifiz-floating-btn')) return;
    const btn = document.createElement('button');
    btn.id = 'atlas-epifiz-floating-btn';
    btn.innerHTML = '<span class="atlas-eye-icon">👁️</span><span class="atlas-btn-text">ATLAS RADARI</span>';
    btn.title = 'Atlas Epifiz: bu profilin kanıt grafını çıkar';
    btn.addEventListener('click', () => toggleSidebar());
    document.body.appendChild(btn);
  }

  function createSidebar() {
    if (document.getElementById('atlas-epifiz-sidebar')) return;
    const sidebar = document.createElement('div');
    sidebar.id = 'atlas-epifiz-sidebar';
    sidebar.innerHTML = `
      <div class="atlas-sidebar-header">
        <div class="atlas-brand">
          <span class="atlas-logo">👁️</span>
          <div><strong>ATLAS EPİFİZ</strong><small>PINEAL OBSERVATORY</small></div>
        </div>
        <button id="atlas-sidebar-close" class="atlas-close-btn">&times;</button>
      </div>
      <div class="atlas-target-badge">
        <span class="atlas-badge-label">HEDEF:</span>
        <span id="atlas-target-name" class="atlas-badge-val">Tespit ediliyor...</span>
      </div>
      <div class="atlas-sidebar-content">
        <button id="atlas-run-analyze-btn" class="atlas-primary-btn">⚡ DERİN İSTİHBARAT BAŞLAT</button>
        <button id="atlas-stop-btn" class="atlas-secondary-btn" hidden>■ ACİL STOP</button>
        <div id="atlas-status" class="atlas-status" role="status"></div>
        <div id="atlas-results-container" class="atlas-results-hidden">
          <div class="atlas-section">
            <div class="atlas-sec-title">🎯 GRAF (GERÇEK KANIT)</div>
            <div id="atlas-note" class="atlas-data-box"></div>
            <div id="atlas-nodes" class="atlas-matrix-pills"></div>
          </div>
          <a id="atlas-open-console-link" href="http://127.0.0.1:8000" target="_blank" class="atlas-secondary-btn">🏛️ TAM KONSOLDA AÇ</a>
        </div>
      </div>`;
    document.body.appendChild(sidebar);
    document.getElementById('atlas-sidebar-close').addEventListener('click', () => toggleSidebar(false));
    document.getElementById('atlas-run-analyze-btn').addEventListener('click', runProfileAnalysis);
    document.getElementById('atlas-stop-btn').addEventListener('click', stopAnalysis);
  }

  function toggleSidebar(force) {
    const sidebar = document.getElementById('atlas-epifiz-sidebar');
    if (!sidebar) return;
    isPanelOpen = typeof force === 'boolean' ? force : !isPanelOpen;
    sidebar.classList.toggle('active', isPanelOpen);
    if (isPanelOpen) {
      const t = extractProfileData();
      document.getElementById('atlas-target-name').innerText = `${t.name} (${t.title || 'LinkedIn'})`;
    }
  }

  function setStatus(text, kind) {
    const el = document.getElementById('atlas-status');
    if (!el) return;
    el.innerText = text;
    el.dataset.kind = kind || '';
  }

  // ── iş ─────────────────────────────────────────────────────────
  async function runProfileAnalysis() {
    if (isAnalyzing) return;
    const target = extractProfileData();
    const { clientId } = await settings();
    currentClient = clientId;

    isAnalyzing = true;
    emptyPolls = 0;
    const btn = document.getElementById('atlas-run-analyze-btn');
    const stop = document.getElementById('atlas-stop-btn');
    btn.disabled = true;
    btn.innerText = '⏳ GÖREV AÇILIYOR...';
    document.getElementById('atlas-results-container').classList.add('atlas-results-hidden');
    setStatus('Görev açılıyor…');

    try {
      const started = await call('/api/initiate', {
        method: 'POST',
        body: JSON.stringify({
          client_id: clientId,
          url: target.url,
          rituals: '',
          playlist: '',
          envies: '',
          scraper_type: 'cross',
        }),
      });
      currentTask = started.task_id;
      stop.hidden = false;
      btn.innerText = '⚡ YENİDEN TARA & ANALİZ ET';
      btn.disabled = false;
      setStatus(`Görev ${currentTask} — kanıt bekleniyor…`);
      pollTimer = setInterval(() => pollGraph(currentTask, currentClient), POLL_MS);
      pollGraph(currentTask, currentClient);
    } catch (err) {
      setStatus(err.message, 'err');
      btn.innerText = '⚡ YENİDEN TARA & ANALİZ ET';
      btn.disabled = false;
      isAnalyzing = false;
    }
  }

  async function pollGraph(taskId, clientId) {
    try {
      const g = await call(`/api/tasks/${encodeURIComponent(taskId)}/graph?client_id=${encodeURIComponent(clientId)}`);
      if (g.available && g.nodes?.length) {
        emptyPolls = 0;
        renderGraph(g);
        setStatus(g.machine_note || `${g.node_count} düğüm / ${g.edge_count} kenar`, 'ok');
        return;
      }
      emptyPolls += 1;
      renderEmpty(g);
      setStatus(REASON[g.reason] || g.reason || 'Kanıt henüz yok…', 'wait');
      if (emptyPolls === 6) offerAuthorization();
      if (emptyPolls >= MAX_EMPTY) {
        setStatus('Süre doldu, kanıt gelmedi. Görev arka planda sürüyor olabilir.', 'warn');
        clearInterval(pollTimer);
        pollTimer = null;
        isAnalyzing = false;
      }
    } catch (err) {
      setStatus(err.message, 'err');
      clearInterval(pollTimer);
      pollTimer = null;
      isAnalyzing = false;
    }
  }

  function renderEmpty(g) {
    const box = document.getElementById('atlas-results-container');
    const note = document.getElementById('atlas-note');
    const nodes = document.getElementById('atlas-nodes');
    box.classList.remove('atlas-results-hidden');
    note.innerHTML = `<div><strong>Durum:</strong> ${g.available ? 'graf boş' : 'kanıt yok'}</div>
      <div><strong>Sebep:</strong> ${g.reason || '—'}</div>`;
    nodes.innerHTML = '';
  }

  function renderGraph(g) {
    const box = document.getElementById('atlas-results-container');
    const note = document.getElementById('atlas-note');
    const nodes = document.getElementById('atlas-nodes');
    box.classList.remove('atlas-results-hidden');
    note.innerHTML = `<div><strong>${g.node_count}</strong> düğüm · <strong>${g.edge_count}</strong> kenar</div>
      <div class="atlas-muted">${g.machine_note || ''}</div>`;
    nodes.innerHTML = '';
    for (const n of g.nodes) {
      const pill = document.createElement('span');
      pill.className = 'atlas-pill' + (n.kind === 'target' ? ' active' : '');
      pill.innerText = `${n.kind} · ${n.label} (${n.evidence_count})`;
      nodes.appendChild(pill);
    }
  }

  async function offerAuthorization() {
    if (document.getElementById('atlas-authz-btn')) return;
    const btn = document.createElement('button');
    btn.id = 'atlas-authz-btn';
    btn.className = 'atlas-primary-btn';
    btn.innerText = '🔓 WEB ARAMASINA ONAY VER';
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        const r = await call('/api/scraper/authorize-alternative', {
          method: 'POST',
          body: JSON.stringify({ client_id: currentClient, alternative: 'public_web_search', approved: true }),
        });
        setStatus(`Onay: ${r.status}`, r.status === 'no_pending_authorization' ? 'warn' : 'ok');
        if (r.status === 'no_pending_authorization') setStatus('Bekleyen onay yok — görev zaten ilerliyor olabilir.', 'warn');
      } catch (err) {
        setStatus(err.message, 'err');
      } finally {
        btn.disabled = false;
        btn.remove();
      }
    });
    document.getElementById('atlas-status').after(btn);
  }

  async function stopAnalysis() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    isAnalyzing = false;
    if (!currentTask) return setStatus('Durduruldu.', 'warn');
    try {
      await call(`/api/tasks/${encodeURIComponent(currentTask)}/cancel?client_id=${encodeURIComponent(currentClient)}&reason=extension_stop`, { method: 'POST' });
      setStatus('Görev iptal edildi.', 'warn');
    } catch (err) {
      setStatus(`İzleme durdu; iptal başarısız: ${err.message}`, 'err');
    }
    document.getElementById('atlas-stop-btn').hidden = true;
  }

  createFloatingButton();
  createSidebar();

  let lastUrl = location.href;
  new MutationObserver(() => {
    if (location.href === lastUrl) return;
    lastUrl = location.href;
    if (location.pathname.startsWith('/in/')) createFloatingButton();
  }).observe(document, { subtree: true, childList: true });
})();
