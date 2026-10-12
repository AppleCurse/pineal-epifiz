<!-- CANLI TARAYICI LCD'si: içinde gerçek Instagram açılır.
     Kullanıcı fareyle tıklar, klavyeyle yazar (şifre/Google/2FA serbest —
     tuşlar doğrudan Instagram'a gider, arka-uç parolayı asla görmez).
     Giriş bitince OTURUMU KAYDET yalnızca sessionid'yi kasaya mühürler.
     Chromium yoksa dürüst "TARAYICI YOK" + manuel çerez yedeği. -->
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import { clientId, apiFetch, logs } from '../../store';
  import { sysTelemetry } from '../../lib/telemetry';
  import { playClick } from '../../lib/consoleAudio';

  const VW = 800;
  const VH = 600;

  let live = false;
  let pageUrl = '';
  let pageTitle = '';
  let savedSession = false;
  let browserMissing = false;
  let shotUrl = '';
  let busy = false;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let shotEl: HTMLImageElement | null = null;

  // yazı kutusu + manuel çerez yedeği
  let typeText = '';
  let cookie = '';
  let sealing = false;
  const SEAL_KEY = 'pineal_vault_cookie_sealed';
  let sealedAt = '';
  try { sealedAt = localStorage.getItem(SEAL_KEY) || ''; } catch { /* ignore */ }

  function log(level: string, msg: string) {
    logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level, msg }]);
  }

  async function refreshState(): Promise<boolean> {
    try {
      const res = await apiFetch(`/api/browser/state?client_id=${get(clientId)}`);
      if (res.status === 503) { browserMissing = true; live = false; return false; }
      if (!res.ok) return false;
      const st = await res.json();
      live = !!st.live;
      pageUrl = st.url || '';
      pageTitle = st.title || '';
      savedSession = !!st.saved_session;
      return live;
    } catch {
      return false;
    }
  }

  async function refreshShot() {
    if (!live) return;
    try {
      const res = await apiFetch(`/api/browser/shot?client_id=${get(clientId)}&k=${Date.now()}`);
      if (res.status === 503) { browserMissing = true; live = false; return; }
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      if (shotUrl) URL.revokeObjectURL(shotUrl);
      shotUrl = url;
    } catch { /* ağ hatası: eski kare kalır */ }
  }

  async function poll() {
    if (busy) return;
    if (await refreshState()) await refreshShot();
  }

  async function act(label: string, fn: () => Promise<Response | null>) {
    if (busy) return;
    busy = true;
    playClick(280, 40);
    try {
      const res = await fn();
      if (!res) return;
      if (res.status === 503) {
        browserMissing = true; live = false;
        log('ERROR', 'TARAYICI YOK: bu makinede Chromium kurulu değil');
        return;
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        log('ERROR', `TARAYICI: ${data?.error?.message || label + ' Tarayıcıyı başlatırken bir sorun oluştu'}`);
        return;
      }
      if (data?.url) pageUrl = data.url;
      setTimeout(() => { void refreshState(); void refreshShot(); }, 700);
    } catch (e: any) {
      log('ERROR', `TARAYICI: ${e?.message || e}`);
    } finally {
      busy = false;
    }
  }

  const post = (path: string, body: any) =>
    apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

  function openBrowser() {
    browserMissing = false;
    void act('aç', () => post('/api/browser/open', { client_id: get(clientId) }));
  }
  function goBack() { void act('geri', () => post('/api/browser/back', { client_id: get(clientId) })); }
  function sendPress(key: string) {
    void act(key, () => post('/api/browser/press', { client_id: get(clientId), key }));
  }
  function sendType() {
    const text = typeText;
    if (!text) return;
    typeText = '';
    void act('yaz', () => post('/api/browser/type', { client_id: get(clientId), text }));
  }
  function handleShotClick(e: MouseEvent) {
    if (!live || !shotEl) return;
    const r = shotEl.getBoundingClientRect();
    const x = Math.round(((e.clientX - r.left) / r.width) * VW);
    const y = Math.round(((e.clientY - r.top) / r.height) * VH);
    void act('tık', () => post('/api/browser/click', { client_id: get(clientId), x, y }));
  }
  function handleTypeKey(e: KeyboardEvent) { if (e.key === 'Enter') sendType(); }
  function handleViewportKey(e: KeyboardEvent) {
    // Uzak viewport klavye kontrolü: oklar/Enter/Tab/Escape tarayıcıya gider.
    const map: Record<string, string> = {
      Enter: 'Enter', Tab: 'Tab', Escape: 'Escape',
      ArrowLeft: 'ArrowLeft', ArrowRight: 'ArrowRight',
      ArrowUp: 'ArrowUp', ArrowDown: 'ArrowDown',
    };
    const key = map[e.key];
    if (key && live && !busy) {
      e.preventDefault();
      sendPress(key);
    }
  }

  async function saveSession() {
    if (busy) return;
    busy = true;
    playClick(320, 50);
    try {
      const res = await post('/api/browser/save', { client_id: get(clientId) });
      const data = await res.json().catch(() => ({}));
      if (data?.saved) {
        savedSession = true;
        playClick(420, 60);
        log('INFO', 'KASA: Canlı IG oturumu mühürlendi (sessionid)');
      } else {
        log('WARNING', `OTURUM YOK: ${data?.hint || 'giriş tamamlanmamış'}`);
      }
      void refreshState();
    } catch (e: any) {
      log('ERROR', `KASA: ${e?.message || e}`);
    } finally {
      busy = false;
    }
  }

  function closeBrowser() {
    void act('kapat', () => post('/api/browser/close', { client_id: get(clientId) }));
    setTimeout(() => { live = false; shotUrl = ''; }, 800);
  }

  async function sealCookie() {
    if (!cookie.trim() || sealing) return;
    sealing = true;
    playClick(280, 50);
    try {
      const res = await post('/api/vault', { client_id: get(clientId), x_cookie: cookie.trim() });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const now = new Date().toLocaleString();
      try { localStorage.setItem(SEAL_KEY, now); } catch { /* ignore */ }
      sealedAt = now;
      cookie = '';
      playClick(420, 60);
      log('INFO', 'KASA: IG çerez havuzu mühürlendi (rotasyon hazır)');
    } catch (e: any) {
      log('ERROR', `KASA HATASI: ${e?.message || e}`);
    } finally {
      sealing = false;
    }
  }

  onMount(() => {
    void poll();
    pollTimer = setInterval(() => void poll(), 2000);
  });
  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (shotUrl) URL.revokeObjectURL(shotUrl);
  });
</script>

<div class="lcd-bezel">
  <div class="lcd-scan"></div>
  <div class="lcd-head">
    <span class="lcd-title">CANLI TARAYICI</span>
    <span class="lcd-title-tr">LIVE BROWSER · SCRAPER NODE</span>
  </div>

  {#if browserMissing}
    <div class="lcd-nobrowser">
      <div class="lcd-off">TARAYICI YOK (NO BROWSER)</div>
      <div class="lcd-note">Bu makinede Chromium kurulu değil. Ajan fare-klavyesi burada çalışamaz; manuel çerez yedeğini kullanın.</div>
    </div>
  {:else if !live}
    <button class="lcd-open" on:click={openBrowser} disabled={busy}>
      {busy ? 'AÇILIYOR…' : 'INSTAGRAM’I AÇ (OPEN)'}
    </button>
    <div class="lcd-note">Gerçek Chromium açılır; girişini bildiğin gibi yap (şifre / Google / 2FA).</div>
  {:else}
    <!-- svelte-ignore a11y-no-noninteractive-tabindex a11y-no-noninteractive-element-interactions --
        Uzak masaüstü viewport'u: role=application + tam klavye kontrolü (oklar/Enter/Tab/Escape) bilinçli seçimdir. -->
    <div
      class="lcd-viewport"
      role="application"
      tabindex="0"
      aria-label="Canlı tarayıcı görünümü. Fareyle tıklayın, ok tuşları ve Enter klavyeden çalışır."
      on:click={handleShotClick}
      on:keydown={handleViewportKey}
    >
      {#if shotUrl}
        <img
          bind:this={shotEl}
          src={shotUrl}
          alt="Canlı tarayıcı"
          class="lcd-shot"
          draggable={false}
        />
      {:else}
        <div class="lcd-loading">GÖRÜNTÜ ALINIYOR…</div>
      {/if}
    </div>
    <div class="lcd-url" title={pageTitle || pageUrl}>{pageUrl ? pageUrl.slice(0, 52) : '—'}</div>
    <div class="lcd-controls">
      <button class="lcd-btn" on:click={goBack} disabled={busy} title="Geri">◀ GERİ</button>
      <button class="lcd-btn" on:click={() => sendPress('Enter')} disabled={busy} title="Enter">ENTER ⏎</button>
      <button class="lcd-btn" on:click={closeBrowser} disabled={busy} title="Kapat">KAPAT ✕</button>
    </div>
    <div class="lcd-typerow">
      <input
        class="lcd-type"
        bind:value={typeText}
        on:keydown={handleTypeKey}
        placeholder="Yaz · Type…"
        disabled={busy || !live}
        autocomplete="off"
      />
      <button class="lcd-btn" on:click={sendType} disabled={busy || !typeText}>YAZ</button>
    </div>
    <button class="lcd-save {savedSession ? 'saved' : ''}" on:click={saveSession} disabled={busy}>
      {savedSession ? '✓ OTURUM MÜHÜRLÜ (SAVED)' : 'OTURUMU KAYDET (SAVE)'}
    </button>
  {/if}

  <!-- X satırı: B4 ile devre dışı -->
  <div class="lcd-row lcd-x">
    <div class="lcd-line">
      <span class="lcd-net">X (TWITTER)</span>
      <span class="lcd-led off-red"></span>
    </div>
    <div class="lcd-off">DEVRE DIŞI · B4 (DISABLED)</div>
  </div>

  <!-- Manuel çerez yedeği (tarayıcısız makine için) -->
  <details class="lcd-fallback">
    <summary class="lcd-summary">MANUEL ÇEREZ · MANUAL COOKIE</summary>
    <textarea
      class="lcd-input"
      rows="2"
      bind:value={cookie}
      placeholder="sessionid çerezi · cookie"
      spellcheck={false}
      disabled={sealing}
    ></textarea>
    <button class="lcd-btn lcd-seal" on:click={sealCookie} disabled={sealing || !cookie.trim()}>
      {sealing ? 'MÜHÜRLENİYOR…' : 'MÜHÜRLE (SEAL)'}
    </button>
    <div class="lcd-note">{sealedAt ? `Mühürlü: ${sealedAt}` : 'Havuzu değiştirir · Replaces pool'}</div>
  </details>

  <div class="lcd-foot">
    <span>OTURUM: {savedSession || $sysTelemetry.instagramSession ? 'KAYITLI' : 'YOK'}</span>
    <span>KASA: {$sysTelemetry.ok ? ($sysTelemetry.vault ? 'DOLU' : 'BOŞ') : '—'}</span>
  </div>
</div>

<style>
  .lcd-bezel {
    position: relative;
    width: 330px;
    background: linear-gradient(180deg, #1c1408 0%, #0d0903 100%);
    border: 2px solid #8a6332;
    border-radius: 6px;
    padding: 8px 10px;
    box-shadow: inset 0 0 22px rgba(0, 0, 0, 0.9), 0 4px 10px rgba(0, 0, 0, 0.7);
    overflow: hidden;
  }
  .lcd-scan {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: repeating-linear-gradient(180deg, rgba(255, 255, 255, 0.025) 0 1px, transparent 1px 3px);
    z-index: 5;
  }
  .lcd-head {
    display: flex;
    flex-direction: column;
    align-items: center;
    border-bottom: 1px solid #3d2b17;
    padding-bottom: 5px;
    margin-bottom: 6px;
  }
  .lcd-title {
    font-family: 'Cinzel', serif;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1.5px;
    color: #ffb000;
    text-shadow: 0 0 8px rgba(255, 176, 0, 0.6);
  }
  .lcd-title-tr {
    font-family: 'JetBrains Mono', monospace;
    font-size: 7px;
    letter-spacing: 1px;
    color: #8a6a2a;
  }
  .lcd-open {
    width: 100%;
    background: linear-gradient(180deg, #d4af37, #8a6332);
    border: 1px solid #ffe89e;
    color: #120904;
    font-family: 'Cinzel', serif;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.8px;
    border-radius: 3px;
    padding: 8px;
    cursor: pointer;
    margin: 4px 0;
  }
  .lcd-open:disabled { opacity: 0.5; cursor: wait; }
  .lcd-viewport {
    background: #000;
    border: 1px solid #5a3d1c;
    border-radius: 3px;
    overflow: hidden;
    min-height: 120px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .lcd-shot {
    width: 100%;
    display: block;
    cursor: crosshair;
    user-select: none;
  }
  .lcd-loading {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    color: #8a6a2a;
    padding: 20px;
  }
  .lcd-url {
    font-family: 'JetBrains Mono', monospace;
    font-size: 7px;
    color: #8a6a2a;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-top: 3px;
  }
  .lcd-controls {
    display: flex;
    gap: 4px;
    margin-top: 5px;
  }
  .lcd-typerow {
    display: flex;
    gap: 4px;
    margin-top: 4px;
  }
  .lcd-type {
    flex: 1;
    background: #050302;
    border: 1px solid #5a3d1c;
    color: #ffb000;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    border-radius: 3px;
    padding: 4px 6px;
    outline: none;
    min-width: 0;
  }
  .lcd-type:focus { border-color: #ffb000; }
  .lcd-type::placeholder { color: #6b4e1e; }
  .lcd-btn {
    background: linear-gradient(180deg, #d4af37, #8a6332);
    border: 1px solid #ffe89e;
    color: #120904;
    font-family: 'Cinzel', serif;
    font-size: 8px;
    font-weight: 800;
    letter-spacing: 0.5px;
    border-radius: 3px;
    padding: 4px 8px;
    cursor: pointer;
    white-space: nowrap;
  }
  .lcd-btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .lcd-save {
    width: 100%;
    margin-top: 5px;
    background: linear-gradient(180deg, #10b981, #065f46);
    border: 1px solid #7dfcd0;
    color: #fff;
    font-family: 'Cinzel', serif;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 0.8px;
    border-radius: 3px;
    padding: 5px;
    cursor: pointer;
  }
  .lcd-save.saved { filter: saturate(0.6); }
  .lcd-save:disabled { opacity: 0.5; cursor: wait; }
  .lcd-row { padding: 5px 0 0; }
  .lcd-x {
    border-top: 1px dashed #3d2b17;
    margin-top: 6px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .lcd-line {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .lcd-net {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 1px;
    color: #ffcf6e;
  }
  .lcd-led { width: 8px; height: 8px; border-radius: 50%; border: 1px solid #000; }
  .lcd-led.off-red { background: #3a1512; box-shadow: inset 0 1px 2px #000; }
  .lcd-off {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
    color: #5a3a30;
  }
  .lcd-nobrowser { padding: 6px 0; display: flex; flex-direction: column; gap: 4px; }
  .lcd-note {
    font-family: 'JetBrains Mono', monospace;
    font-size: 6.5px;
    color: #8a6a2a;
    line-height: 1.4;
  }
  .lcd-fallback { margin-top: 6px; border-top: 1px dashed #3d2b17; padding-top: 4px; }
  .lcd-summary {
    font-family: 'JetBrains Mono', monospace;
    font-size: 7px;
    font-weight: 700;
    color: #8a6a2a;
    cursor: pointer;
    letter-spacing: 0.6px;
  }
  .lcd-input {
    background: #050302;
    border: 1px solid #5a3d1c;
    color: #ffb000;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    border-radius: 3px;
    padding: 4px 6px;
    width: 100%;
    resize: none;
    outline: none;
    margin-top: 4px;
  }
  .lcd-input:focus { border-color: #ffb000; }
  .lcd-input::placeholder { color: #6b4e1e; }
  .lcd-seal { width: 100%; margin-top: 4px; }
  .lcd-foot {
    display: flex;
    justify-content: space-between;
    border-top: 1px solid #3d2b17;
    margin-top: 6px;
    padding-top: 5px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 7.5px;
    font-weight: 700;
    letter-spacing: 0.6px;
    color: #ffcf6e;
  }
</style>
