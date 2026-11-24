<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '../Icon.svelte';
  import { apiFetch, clientId } from '../../store';
  import { reasonLabel } from '../../lib/channelStatus';

  export let targetUrl: string = '';

  let statusLoading = false;
  let capabilitiesData: any = null;
  let stealthData: any = null;

  // 1. Maigret (Kullanıcı Adı Çapraz Taraması)
  let maigretUsername = '';
  let maigretLimit = 50;
  let maigretBusy = false;
  let maigretResult: any = null;
  let maigretError = '';

  // 2. Holehe (E-posta Kayıt Taraması)
  let holeheEmail = '';
  let holeheLimit = 50;
  let holeheBusy = false;
  let holeheResult: any = null;
  let holeheError = '';

  // 3. Socid (Profil Kimlik Çıkarıcı)
  let socidUrl = '';
  let socidBusy = false;
  let socidResult: any = null;
  let socidError = '';

  // 4. Telefon Numarası & Sosyal Köprü (KVKK Rızalı)
  let phoneInput = '';
  let phoneConsent = false;
  let phoneAutoBridge = true;
  let phoneBusy = false;
  let phoneResult: any = null;
  let phoneError = '';

  // 5. Web Sayfası Okuyucu (Crawl4AI / Scrapling)
  let crawlUrl = '';
  let crawlBusy = false;
  let crawlResult: any = null;
  let crawlError = '';

  function prefillFromTarget() {
    const t = (targetUrl || '').trim();
    if (!t) return;
    if (!maigretUsername && !t.includes('@') && !t.includes('://')) {
      maigretUsername = t.replace(/^@/, '');
    }
    if (!holeheEmail && t.includes('@') && t.includes('.')) {
      holeheEmail = t;
    }
    if (!socidUrl && t.startsWith('http')) {
      socidUrl = t;
    }
    if (!crawlUrl && t.startsWith('http')) {
      crawlUrl = t;
    }
  }

  async function loadCrossStatus() {
    statusLoading = true;
    try {
      const cid = encodeURIComponent($clientId || 'default');
      const [capRes, stRes] = await Promise.all([
        apiFetch(`/api/brain/capabilities?client_id=${cid}`),
        apiFetch('/api/experimental/stealth'),
      ]);
      if (capRes.ok) capabilitiesData = await capRes.json();
      if (stRes.ok) stealthData = await stRes.json();
    } catch {
      /* sessizce geç */
    } finally {
      statusLoading = false;
    }
  }

  onMount(() => {
    prefillFromTarget();
    void loadCrossStatus();
  });

  function readFlag(name: string): boolean {
    const p = capabilitiesData?.profiles;
    if (!p) return false;
    return Boolean(
      p?.local_core?.flags?.[name] ??
        p?.external_keyed?.flags?.[name] ??
        p?.consent_only?.flags?.[name]
    );
  }

  async function parseResponse(res: Response) {
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data?.error?.message || data?.detail || `HTTP ${res.status}`);
    }
    return data;
  }

  async function runMaigret() {
    const u = maigretUsername.trim().replace(/^@/, '');
    if (!u || maigretBusy) return;
    maigretBusy = true;
    maigretError = '';
    maigretResult = null;
    try {
      const res = await apiFetch('/api/experimental/maigret/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: u,
          limit: Number(maigretLimit) || 50,
          timeout: 20,
          client_id: $clientId || 'default',
        }),
      });
      maigretResult = await parseResponse(res);
    } catch (e: any) {
      maigretError = e?.message || 'Tarama başlatılamadı';
    } finally {
      maigretBusy = false;
    }
  }

  async function runHolehe() {
    const email = holeheEmail.trim();
    if (!email || holeheBusy) return;
    holeheBusy = true;
    holeheError = '';
    holeheResult = null;
    try {
      const res = await apiFetch('/api/experimental/holehe/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          limit: Number(holeheLimit) || 50,
          timeout: 20,
          client_id: $clientId || 'default',
        }),
      });
      holeheResult = await parseResponse(res);
    } catch (e: any) {
      holeheError = e?.message || 'E-posta taraması başlatılamadı';
    } finally {
      holeheBusy = false;
    }
  }

  async function runSocid() {
    const url = socidUrl.trim();
    if (!url || socidBusy) return;
    socidBusy = true;
    socidError = '';
    socidResult = null;
    try {
      const res = await apiFetch('/api/experimental/socid/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url,
          client_id: $clientId || 'default',
        }),
      });
      socidResult = await parseResponse(res);
    } catch (e: any) {
      socidError = e?.message || 'Profil kimlik çıkarımı başarısız';
    } finally {
      socidBusy = false;
    }
  }

  async function runPhoneProbe() {
    const phone = phoneInput.trim();
    if (!phone || phoneBusy || !phoneConsent) return;
    phoneBusy = true;
    phoneError = '';
    phoneResult = null;
    try {
      const res = await apiFetch('/api/commander/phone-probe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phone,
          auto_bridge_social: phoneAutoBridge,
          subject_consent: phoneConsent,
          client_id: $clientId || 'default',
        }),
      });
      phoneResult = await parseResponse(res);
    } catch (e: any) {
      phoneError = e?.message || 'Telefon sorgulaması başarısız';
    } finally {
      phoneBusy = false;
    }
  }

  async function runCrawl() {
    const url = crawlUrl.trim();
    if (!url || crawlBusy) return;
    crawlBusy = true;
    crawlError = '';
    crawlResult = null;
    try {
      const res = await apiFetch('/api/experimental/crawl/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url,
          client_id: $clientId || 'default',
        }),
      });
      crawlResult = await parseResponse(res);
    } catch (e: any) {
      crawlError = e?.message || 'Sayfa okunamadı';
    } finally {
      crawlBusy = false;
    }
  }
</script>

<div class="tab-page">
  <div class="section-head">
    <div>
      <h2 class="section-title">Çapraz Tarama &amp; Kimlik İz Sürme</h2>
      <p class="section-intro">
        Tek bir kullanıcı adı, e-posta, telefon numarası veya web adresiyle tüm açık platformlarda çapraz iz sürün.
      </p>
    </div>
    <button type="button" class="btn btn-secondary btn-sm" on:click={loadCrossStatus} disabled={statusLoading}>
      <Icon name="refresh" size={0.85} />
      <span>{statusLoading ? 'Kontrol Ediliyor...' : 'Durumu Yenile'}</span>
    </button>
  </div>

  <!-- Durum Şeridi -->
  <div class="status-strip card">
    <span class="pill" class:pill-ok={readFlag('ENABLE_CROSS_PLATFORM')}>
      Çapraz Platform: {readFlag('ENABLE_CROSS_PLATFORM') ? 'Açık' : 'Kapalı / Görev Onaylı'}
    </span>
    <span class="pill" class:pill-ok={readFlag('ENABLE_MAIGRET')}>
      Maigret (Kullanıcı Adı): {readFlag('ENABLE_MAIGRET') ? 'Açık' : 'Kapalı'}
    </span>
    <span class="pill" class:pill-ok={readFlag('ENABLE_HOLEHE')}>
      Holehe (E-posta): {readFlag('ENABLE_HOLEHE') ? 'Açık' : 'Kapalı'}
    </span>
    <span class="pill" class:pill-ok={readFlag('ENABLE_CRAWL4AI')}>
      Web Okuyucu: {readFlag('ENABLE_CRAWL4AI') ? 'Açık' : 'Kapalı'}
    </span>
    <span class="pill" class:pill-ok={stealthData?.available}>
      Gizli Tarayıcı: {stealthData?.available ? stealthData.provider || 'Hazır' : reasonLabel(stealthData?.reason || 'bilinmiyor')}
    </span>
  </div>

  <div class="cross-grid">
    <!-- 1. Maigret -->
    <section class="card tool-card">
      <div class="tool-head">
        <h3><Icon name="users" size={1} /> Kullanıcı Adı Çapraz Taraması (Maigret)</h3>
        <span class="pill">Binlerce site</span>
      </div>
      <p class="section-intro">Bir kullanıcı adının başka hangi sosyal ağlarda ve sitelerde kayıtlı olduğunu tarar.</p>

      <div class="form-row">
        <label class="field-label" style="flex: 2;">
          <span>Kullanıcı Adı</span>
          <input type="text" class="field-input" bind:value={maigretUsername} placeholder="Örn: ornek_kullanici" />
        </label>
        <label class="field-label" style="flex: 1;">
          <span>Site Sınırı</span>
          <input type="number" min="5" max="500" class="field-input" bind:value={maigretLimit} />
        </label>
      </div>

      <button type="button" class="btn btn-primary" on:click={runMaigret} disabled={maigretBusy || !maigretUsername.trim()}>
        <Icon name="search" size={0.9} />
        <span>{maigretBusy ? 'Taranıyor...' : 'Kullanıcı Adını Tara'}</span>
      </button>

      {#if maigretError}
        <div class="alert-banner err">{maigretError}</div>
      {/if}
      {#if maigretResult}
        <div class="result-box">
          <div class="res-head">
            <strong>Sonuç: {maigretResult.available ? `${(maigretResult.hits || maigretResult.found || []).length} eşleşme` : 'Sonuç alınamadı'}</strong>
            {#if maigretResult.reason}<span class="pill pill-warn">{reasonLabel(maigretResult.reason)}</span>{/if}
          </div>
          {#if (maigretResult.hits || maigretResult.found || []).length > 0}
            <ul class="hit-list">
              {#each (maigretResult.hits || maigretResult.found || []).slice(0, 30) as hit}
                <li>
                  <strong>{hit.site || hit.name || 'Site'}</strong>
                  {#if hit.url || hit.url_user}
                    <a href={hit.url || hit.url_user} target="_blank" rel="noopener noreferrer">{hit.url || hit.url_user}</a>
                  {/if}
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      {/if}
    </section>

    <!-- 2. Holehe -->
    <section class="card tool-card">
      <div class="tool-head">
        <h3><Icon name="search" size={1} /> E-posta Kayıt Taraması (Holehe)</h3>
        <span class="pill">Platform hesabı</span>
      </div>
      <p class="section-intro">Girilen e-posta adresinin hangi platformlarda üyeliği bulunduğunu kontrol eder.</p>

      <div class="form-row">
        <label class="field-label" style="flex: 2;">
          <span>E-posta Adresi</span>
          <input type="email" class="field-input" bind:value={holeheEmail} placeholder="ornek@alanadi.com" />
        </label>
        <label class="field-label" style="flex: 1;">
          <span>Site Sınırı</span>
          <input type="number" min="5" max="200" class="field-input" bind:value={holeheLimit} />
        </label>
      </div>

      <button type="button" class="btn btn-primary" on:click={runHolehe} disabled={holeheBusy || !holeheEmail.trim()}>
        <Icon name="search" size={0.9} />
        <span>{holeheBusy ? 'Kontrol Ediliyor...' : 'E-postayı Tara'}</span>
      </button>

      {#if holeheError}
        <div class="alert-banner err">{holeheError}</div>
      {/if}
      {#if holeheResult}
        <div class="result-box">
          <div class="res-head">
            <strong>Kayıtlı Siteler: {(holeheResult.registered || holeheResult.hits || []).length}</strong>
            {#if holeheResult.reason}<span class="pill pill-warn">{reasonLabel(holeheResult.reason)}</span>{/if}
          </div>
          {#if (holeheResult.registered || holeheResult.hits || []).length > 0}
            <div class="tag-cloud">
              {#each (holeheResult.registered || holeheResult.hits || []) as site}
                <span class="pill pill-ok">{typeof site === 'string' ? site : site.domain || site.name || JSON.stringify(site)}</span>
              {/each}
            </div>
          {/if}
        </div>
      {/if}
    </section>

    <!-- 3. Telefon + Sosyal Köprü -->
    <section class="card tool-card">
      <div class="tool-head">
        <h3><Icon name="phone" size={1} /> Telefon Numarası &amp; Sosyal Köprü</h3>
        <span class="pill pill-indigo">KVKK Rızalı</span>
      </div>
      <p class="section-intro">Operatör, ülke, WhatsApp/Telegram bağlantıları ve varsa sosyal medya köprüsünü çıkarır.</p>

      <label class="field-label">
        <span>Telefon Numarası</span>
        <input type="text" class="field-input" bind:value={phoneInput} placeholder="Örn: +90 555 123 45 67" />
      </label>

      <label class="check-row">
        <input type="checkbox" bind:checked={phoneConsent} />
        <span>Hedef kişiden KVKK kapsamında açık rıza alındı</span>
      </label>

      <label class="check-row">
        <input type="checkbox" bind:checked={phoneAutoBridge} />
        <span>Aday kullanıcı adlarını otomatik sosyal platformlarda yokla</span>
      </label>

      <button type="button" class="btn btn-primary" on:click={runPhoneProbe} disabled={phoneBusy || !phoneInput.trim() || !phoneConsent}>
        <Icon name="phone" size={0.9} />
        <span>{phoneBusy ? 'Sorgulanıyor...' : 'Telefonu Sorgula'}</span>
      </button>

      {#if phoneError}
        <div class="alert-banner err">{phoneError}</div>
      {/if}
      {#if phoneResult}
        <div class="result-box">
          <div><strong>Operatör:</strong> {phoneResult.metadata?.carrier_name || 'Bilinmiyor'} · {phoneResult.metadata?.country_name || '—'}</div>
          {#if (phoneResult.messaging_probes || []).length > 0}
            <div class="tag-cloud" style="margin-top: 6px;">
              {#each phoneResult.messaging_probes as mp}
                <a href={mp.url} target="_blank" rel="noopener noreferrer" class="btn btn-ghost btn-sm">{mp.platform}</a>
              {/each}
            </div>
          {/if}
          {#if (phoneResult.social_probes || []).length > 0}
            <div class="tag-cloud" style="margin-top: 6px;">
              {#each phoneResult.social_probes as sp}
                <a href={sp.url} target="_blank" rel="noopener noreferrer" class="pill pill-ok">{sp.platform}: @{sp.handle}</a>
              {/each}
            </div>
          {/if}
        </div>
      {/if}
    </section>

    <!-- 4. Socid Profil Çıkarıcı -->
    <section class="card tool-card">
      <div class="tool-head">
        <h3><Icon name="target" size={1} /> Profil Kimlik Çıkarıcı (Socid)</h3>
        <span class="pill">Profil adresi</span>
      </div>
      <p class="section-intro">Verilen açık profil sayfasından kimlik bilgilerini ve bağlantılı hesapları çıkarır.</p>

      <label class="field-label">
        <span>Profil Adresi (URL)</span>
        <input type="url" class="field-input" bind:value={socidUrl} placeholder="https://..." />
      </label>

      <button type="button" class="btn btn-primary" on:click={runSocid} disabled={socidBusy || !socidUrl.trim()}>
        <Icon name="search" size={0.9} />
        <span>{socidBusy ? 'Çıkarılıyor...' : 'Kimlik Bilgisi Çıkar'}</span>
      </button>

      {#if socidError}
        <div class="alert-banner err">{socidError}</div>
      {/if}
      {#if socidResult}
        <div class="result-box">
          {#if socidResult.reason}<span class="pill pill-warn">{reasonLabel(socidResult.reason)}</span>{/if}
          <pre class="json-preview code-mono">{JSON.stringify(socidResult.fields || socidResult, null, 2).slice(0, 800)}</pre>
        </div>
      {/if}
    </section>

    <!-- 5. Web Sayfası Derin Okuyucu -->
    <section class="card tool-card" style="grid-column: 1 / -1;">
      <div class="tool-head">
        <h3><Icon name="globe" size={1} /> Web Sayfası Derin Okuyucu (Crawl4AI)</h3>
        <span class="pill">Temiz metin</span>
      </div>
      <p class="section-intro">Herhangi bir açık web sayfasının içeriğini temiz metin hâline getirip özetler.</p>

      <div class="form-row">
        <input type="url" class="field-input" style="flex: 1;" bind:value={crawlUrl} placeholder="https://ornek.com/sayfa" />
        <button type="button" class="btn btn-primary" on:click={runCrawl} disabled={crawlBusy || !crawlUrl.trim()}>
          <Icon name="globe" size={0.9} />
          <span>{crawlBusy ? 'Okunuyor...' : 'Sayfayı Oku'}</span>
        </button>
      </div>

      {#if crawlError}
        <div class="alert-banner err">{crawlError}</div>
      {/if}
      {#if crawlResult}
        <div class="result-box">
          {#if crawlResult.reason}<span class="pill pill-warn">{reasonLabel(crawlResult.reason)}</span>{/if}
          <pre class="json-preview code-mono">{(crawlResult.markdown || crawlResult.text || JSON.stringify(crawlResult, null, 2)).slice(0, 1200)}</pre>
        </div>
      {/if}
    </section>
  </div>
</div>

<style>
  .tab-page {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .status-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 12px 14px;
  }

  .cross-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
  }

  @media (max-width: 900px) {
    .cross-grid {
      grid-template-columns: 1fr;
    }
  }

  .tool-card {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .tool-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }

  .tool-head h3 {
    font-size: 14.5px;
    font-weight: 700;
    color: var(--text-primary);
    display: inline-flex;
    align-items: center;
    gap: 7px;
  }

  .form-row {
    display: flex;
    gap: 10px;
    align-items: flex-end;
    flex-wrap: wrap;
  }

  .check-row {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 12.5px;
    color: var(--text-secondary);
    cursor: pointer;
  }

  .result-box {
    padding: 10px 12px;
    border-radius: 9px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    font-size: 12.5px;
  }

  .res-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }

  .hit-list {
    padding-left: 16px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 200px;
    overflow-y: auto;
  }

  .hit-list a {
    color: var(--accent);
    margin-left: 6px;
    word-break: break-all;
  }

  .tag-cloud {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .json-preview {
    margin-top: 6px;
    max-height: 220px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    font-size: 11.5px;
    color: var(--text-secondary);
  }
</style>
