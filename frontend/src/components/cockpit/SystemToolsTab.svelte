<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '../Icon.svelte';
  import JuryConsensusPanel from './JuryConsensusPanel.svelte';
  import { apiFetch, clientId, formatApiError } from '../../store';
  import { channelLabel, reasonLabel, type CapabilityRow } from '../../lib/channelStatus';

  export let routingData: any = null;
  export let onLoadRoutingSnapshot: () => void = () => {};
  export let onOpenSettings: () => void = () => {};
  export let onOpenTerms: () => void = () => {};

  let loadingOverview = false;
  let capabilitiesList: CapabilityRow[] = [];
  let healthDetail: any = null;
  let mcpStatus: any = null;
  let juryStatus: any = null;
  let minorState: any = null;
  let calibrationData: any = null;

  // Dil Çevirici
  let langText = '';
  let langTarget = 'tr';
  let langBusy = false;
  let langResult: any = null;
  let langError = '';

  // Gölge Karakter Analizi / Mesaj Denemesi
  let shadowMode: 'analyze' | 'generate' = 'analyze';
  let shadowUsername = '';
  let shadowInput = '';
  let shadowGoal = '';
  let shadowBusy = false;
  let shadowResult: any = null;
  let shadowError = '';

  // Jüri Doğrulama
  let juryClaim = '';
  let juryEvidence = '';
  let juryBusy = false;
  let juryResult: any = null;
  let juryError = '';

  // Güven Kalibrasyonu (Gözlem Ekle / Doğrula)
  let calScore = 0.75;
  let calScope = 'general';
  let calNote = '';
  let calBusy = false;
  let calNotice = '';

  // Kod / Komut Asistanı
  let interpPrompt = '';
  let interpBusy = false;
  let interpResult: any = null;
  let interpError = '';

  // Küçükler İçin Ekstra Koruma Kalkanı
  let minorSubjectIsMinor = false;
  let minorCaseType = 'safety_review';
  let minorFamilyNotified = false;
  let minorReason = '';
  let minorBusy = false;
  let minorNotice = '';

  async function refreshAllTools() {
    loadingOverview = true;
    const cid = encodeURIComponent($clientId || 'default');
    try {
      const [telRes, capRes, healthRes, mcpRes, juryRes, minorRes, calRes] = await Promise.all([
        apiFetch(`/api/telemetry?client_id=${cid}`),
        apiFetch(`/api/brain/capabilities?client_id=${cid}`),
        apiFetch('/api/health/detail'),
        apiFetch(`/api/mcp/status?client_id=${cid}`),
        apiFetch('/api/jury/status'),
        apiFetch(`/api/minor/state?client_id=${cid}`),
        apiFetch('/api/calibration?scope=general'),
      ]);
      const telData = telRes.ok ? await telRes.json().catch(() => null) : null;
      const capData = capRes.ok ? await capRes.json().catch(() => null) : null;
      const telCaps = Array.isArray(telData?.capabilities) ? telData.capabilities : [];
      const fallbackCaps = Array.isArray(capData)
        ? capData
        : Array.isArray(capData?.capabilities)
          ? capData.capabilities
          : [];
      capabilitiesList = telCaps.length ? telCaps : fallbackCaps;
      if (healthRes.ok) healthDetail = await healthRes.json();
      if (mcpRes.ok) mcpStatus = await mcpRes.json();
      if (juryRes.ok) juryStatus = await juryRes.json();
      if (minorRes.ok) minorState = await minorRes.json();
      if (calRes.ok) calibrationData = await calRes.json();
      onLoadRoutingSnapshot();
    } catch {
      /* sessizce geç */
    } finally {
      loadingOverview = false;
    }
  }

  async function detectAndTranslate(kind: 'detect' | 'translate') {
    const txt = langText.trim();
    if (!txt || langBusy) return;
    langBusy = true;
    langError = '';
    langResult = null;
    try {
      const endpoint = kind === 'detect' ? '/api/language/detect' : '/api/language/translate';
      const body =
        kind === 'detect'
          ? { text: txt, client_id: $clientId || 'default' }
          : { text: txt, target: langTarget, client_id: $clientId || 'default' };
      const res = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) langError = formatApiError(data, `İşlem yapılamadı (${res.status}).`);
      else langResult = data;
    } catch {
      langError = 'Dil aracına ulaşılamadı.';
    } finally {
      langBusy = false;
    }
  }

  async function runShadow() {
    const rawText = shadowInput.trim();
    const posts = rawText ? rawText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean) : [];
    const username = shadowUsername.trim();
    if ((!rawText && !username) || shadowBusy) return;
    shadowBusy = true;
    shadowError = '';
    shadowResult = null;
    try {
      const endpoint =
        shadowMode === 'analyze'
          ? '/api/experimental/shadow/analyze'
          : '/api/experimental/shadow/generate';
      const payload =
        shadowMode === 'analyze'
          ? {
              client_id: $clientId || 'default',
              username: username || undefined,
              bio: rawText,
              posts,
            }
          : {
              client_id: $clientId || 'default',
              target_profile: {
                username: username || undefined,
                bio: rawText,
                posts,
              },
              goal: shadowGoal.trim(),
              context: username,
            };
      const res = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) shadowError = formatApiError(data, `İşlem başarısız (${res.status}).`);
      else shadowResult = data;
    } catch {
      shadowError = 'Sunucuya ulaşılamadı.';
    } finally {
      shadowBusy = false;
    }
  }

  async function runJuryVote() {
    const claim = juryClaim.trim();
    const evidence = juryEvidence.trim();
    if (!claim || !evidence || juryBusy) return;
    juryBusy = true;
    juryError = '';
    juryResult = null;
    try {
      const res = await apiFetch('/api/jury/vote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          claim,
          evidence,
          client_id: $clientId || 'default',
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) juryError = formatApiError(data, `Jüri kontrolü başarısız (${res.status}).`);
      else juryResult = data;
    } catch {
      juryError = 'Jüri servisine bağlanılamadı.';
    } finally {
      juryBusy = false;
    }
  }

  async function addCalibrationObs() {
    if (calBusy) return;
    calBusy = true;
    calNotice = '';
    try {
      const res = await apiFetch('/api/calibration/observations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          score: Number(calScore) || 0.5,
          scope: calScope.trim() || 'general',
          note: calNote.trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        calNotice = `Ölçüm kaydedildi (${data.observation_id || data.id || 'ok'}).`;
        calNote = '';
        await refreshAllTools();
      } else {
        calNotice = formatApiError(data, 'Kayıt eklenemedi.');
      }
    } catch {
      calNotice = 'Kayıt gönderilemedi.';
    } finally {
      calBusy = false;
    }
  }

  async function runInterpreterPlan() {
    const prompt = interpPrompt.trim();
    if (!prompt || interpBusy) return;
    interpBusy = true;
    interpError = '';
    interpResult = null;
    try {
      const res = await apiFetch('/api/experimental/interpreter/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          prompt,
          auto_run: false,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) interpError = formatApiError(data, `Asistan çalıştırılamadı (${res.status}).`);
      else interpResult = data;
    } catch {
      interpError = 'Bağlantı sağlanamadı.';
    } finally {
      interpBusy = false;
    }
  }

  async function updateMinorGuard(action: 'set' | 'clear') {
    if (minorBusy) return;
    minorBusy = true;
    minorNotice = '';
    try {
      const res =
        action === 'set'
          ? await apiFetch('/api/minor/case', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                client_id: $clientId || 'default',
                subject_is_minor: minorSubjectIsMinor,
                case_type: minorCaseType,
                family_notified: minorFamilyNotified,
                reason: minorReason.trim() || 'Aile güvenliği kontrolü',
                council_approvals: [],
              }),
            })
          : await apiFetch('/api/minor/clear', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ client_id: $clientId || 'default' }),
            });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        minorState = data;
        minorNotice = action === 'set' ? 'Çocuk koruma kilidi güncellendi.' : 'Koruma kilidi temizlendi.';
      } else {
        minorNotice = formatApiError(data, 'İşlem uygulanamadı.');
      }
    } catch {
      minorNotice = 'Bağlantı hatası.';
    } finally {
      minorBusy = false;
    }
  }

  onMount(() => {
    refreshAllTools();
  });

  let capQuery = '';
  let capFilter: 'all' | 'ready' | 'missing' = 'all';

  $: readyCount = capabilitiesList.filter((c) => c.available).length;
  $: missingCount = capabilitiesList.length - readyCount;
  $: filteredCapabilities = capabilitiesList.filter((c) => {
    if (capFilter === 'ready' && !c.available) return false;
    if (capFilter === 'missing' && c.available) return false;
    const q = capQuery.trim().toLocaleLowerCase('tr');
    if (!q) return true;
    const haystack = [
      channelLabel(c.id),
      c.id,
      c.reason ? reasonLabel(c.reason) : '',
      c.reason || '',
    ]
      .join(' ')
      .toLocaleLowerCase('tr');
    return haystack.includes(q);
  });
</script>

<div class="tab-wrap">
  <div class="section-head">
    <div>
      <p class="atelier-kicker">ATÖLYE · YETENEKLER VE DOĞRULAMA</p>
      <h2 class="section-title">Tüm Yetenekler &amp; Araç Kutusu</h2>
      <p class="section-intro">
        Sistemdeki 28 yeteneğin hangilerinin kullanıma hazır olduğunu görün; jüri doğrulaması, çeviri ve diğer yardımcı araçları buradan kullanın.
      </p>
    </div>
    <div class="head-actions">
      <button type="button" class="btn btn-secondary btn-sm" on:click={onOpenSettings}>
        <Icon name="gear" size={0.9} />
        Anahtar Ayarları
      </button>
      <button type="button" class="btn btn-secondary btn-sm" on:click={onOpenTerms}>
        <Icon name="scale" size={0.9} />
        Kurallar
      </button>
      <button type="button" class="btn btn-primary btn-sm" on:click={refreshAllTools} disabled={loadingOverview}>
        <Icon name="refresh" size={0.9} />
        {loadingOverview ? 'Kontrol ediliyor...' : 'Tümünü Yenile'}
      </button>
    </div>
  </div>

  <!-- BAĞIMSIZ JÜRİ & UZLAŞMA PANELİ -->
  <JuryConsensusPanel />

  <!-- 28 YETENEK TABLOSU -->
  <section class="card block-card">
    <div class="block-head">
      <div>
        <h3>28 Yetenek Durum Tablosu</h3>
        <p class="sub-text">
          Her özelliğin neden açık veya neden eksik olduğunu sade dille gösterir. Eksik anahtarları sağ üstten ekleyebilirsiniz.
        </p>
      </div>
      <span class="pill" class:pill-ok={readyCount > 0} class:pill-warn={readyCount === 0}>
        {readyCount} / {capabilitiesList.length} Hazır
      </span>
    </div>

    {#if capabilitiesList.length > 0}
      <div class="cap-toolbar">
        <div class="search-box">
          <Icon name="search" size={0.9} />
          <input
            type="search"
            class="field-input"
            bind:value={capQuery}
            placeholder="Yetenek veya eksik nedeni ara..."
            aria-label="Yetenek ara"
          />
        </div>
        <div class="filter-pills" role="group" aria-label="Yetenek filtresi">
          <button
            type="button"
            class="filter-pill"
            class:active={capFilter === 'all'}
            on:click={() => { capFilter = 'all'; }}
          >
            Tümü ({capabilitiesList.length})
          </button>
          <button
            type="button"
            class="filter-pill"
            class:active={capFilter === 'ready'}
            on:click={() => { capFilter = 'ready'; }}
          >
            Hazır ({readyCount})
          </button>
          <button
            type="button"
            class="filter-pill"
            class:active={capFilter === 'missing'}
            on:click={() => { capFilter = 'missing'; }}
          >
            Eksik ({missingCount})
          </button>
        </div>
      </div>
    {/if}

    {#if capabilitiesList.length === 0}
      <div class="empty-state">Yetenek listesi henüz yüklenemedi. "Tümünü Yenile" düğmesine basın.</div>
    {:else if filteredCapabilities.length === 0}
      <div class="empty-state">Aramanızla veya seçili filtreyle eşleşen yetenek yok.</div>
    {:else}
      <div class="cap-grid">
        {#each filteredCapabilities as row}
          <div class="cap-card" class:cap-ready={row.available}>
            <div class="cap-top">
              <strong>{channelLabel(row.id)}</strong>
              <span class="pill" class:pill-ok={row.available} class:pill-warn={!row.available}>
                {row.available ? 'Hazır' : reasonLabel(row.reason || 'blocked')}
              </span>
            </div>
            {#if !row.available && row.reason}
              <p class="cap-reason">{reasonLabel(row.reason)} ({row.reason})</p>
            {:else if row.available}
              <p class="cap-reason ok-text">Kullanıma hazır</p>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <!-- YARDIMCI ARAÇLAR IZGARASI -->
  <div class="tools-grid">
    <!-- 1. Dil Çevirici -->
    <section class="card block-card">
      <div class="title-with-icon">
        <Icon name="globe" size={1.05} />
        <h3>Dil Tanıma ve Çeviri</h3>
      </div>
      <p class="sub-text">Yabancı dildeki yazışmaları veya profilleri kolayca anlayın ya da çevirin.</p>
      <textarea class="field-textarea" bind:value={langText} placeholder="Çevirmek veya dilini bulmak istediğiniz metni yapıştırın..."></textarea>
      <div class="inline-controls">
        <select class="field-select" bind:value={langTarget}>
          <option value="tr">Türkçeye Çevir</option>
          <option value="en">İngilizceye Çevir</option>
          <option value="de">Almancaya Çevir</option>
          <option value="fr">Fransızcaya Çevir</option>
          <option value="es">İspanyolcaya Çevir</option>
        </select>
        <button type="button" class="btn btn-secondary btn-sm" on:click={() => detectAndTranslate('detect')} disabled={langBusy || !langText.trim()}>
          Dilini Bul
        </button>
        <button type="button" class="btn btn-primary btn-sm" on:click={() => detectAndTranslate('translate')} disabled={langBusy || !langText.trim()}>
          Çevir
        </button>
      </div>
      {#if langError}<div class="alert-banner err">{langError}</div>{/if}
      {#if langResult}<pre class="json-pre">{JSON.stringify(langResult, null, 2)}</pre>{/if}
    </section>

    <!-- 2. Doğrulama Jürisi -->
    <section class="card block-card">
      <div class="title-with-icon">
        <Icon name="scale" size={1.05} />
        <h3>Çoklu Doğrulama Jürisi</h3>
      </div>
      <p class="sub-text">Önemli bir iddiayı birden fazla yapay zekâ modeline kontrol ettirip ortak karara varın.</p>
      {#if juryStatus}
        <span class="pill">{juryStatus.available ? 'Jüri aktif' : 'Ek anahtar gerekli'}</span>
      {/if}
      <input type="text" class="field-input" bind:value={juryClaim} placeholder="Doğrulanacak iddia..." />
      <input type="text" class="field-input" bind:value={juryEvidence} placeholder="Dayanak kanıt metni (zorunlu)..." />
      <button type="button" class="btn btn-primary btn-sm" on:click={runJuryVote} disabled={juryBusy || !juryClaim.trim() || !juryEvidence.trim()}>
        {juryBusy ? 'Jüri inceliyor...' : 'Jüriye Sor'}
      </button>
      {#if juryError}<div class="alert-banner err">{juryError}</div>{/if}
      {#if juryResult}<pre class="json-pre">{JSON.stringify(juryResult, null, 2)}</pre>{/if}
    </section>

    <!-- 3. Gölge / Üslup Çalışması -->
    <section class="card block-card">
      <div class="title-with-icon">
        <Icon name="sparkle" size={1.05} />
        <h3>Üslup İnceleme ve Yazım Denemesi</h3>
      </div>
      <p class="sub-text">Bir yazının tonunu çözümleyin veya aynı sıcak tonda örnek bir metin hazırlayın.</p>
      <div class="inline-controls">
        <select class="field-select" bind:value={shadowMode}>
          <option value="analyze">Yazı Tonunu Çözümle</option>
          <option value="generate">Benzer Tonda Metin Üret</option>
        </select>
        <input type="text" class="field-input" bind:value={shadowUsername} placeholder="Kişi / konu" />
      </div>
      <textarea class="field-textarea" bind:value={shadowInput} placeholder="Örnek yazılar veya üslup notu..."></textarea>
      {#if shadowMode === 'generate'}
        <input type="text" class="field-input" bind:value={shadowGoal} placeholder="Bu mesajda amacınız nedir?" />
      {/if}
      <button type="button" class="btn btn-secondary btn-sm" on:click={runShadow} disabled={shadowBusy || (!shadowInput.trim() && !shadowUsername.trim())}>
        {shadowBusy ? 'Çalışılıyor...' : 'Çalıştır'}
      </button>
      {#if shadowError}<div class="alert-banner err">{shadowError}</div>{/if}
      {#if shadowResult}<pre class="json-pre">{JSON.stringify(shadowResult, null, 2)}</pre>{/if}
    </section>

    <!-- 4. Güven Kalibrasyonu & Kod Asistanı -->
    <section class="card block-card">
      <div class="title-with-icon">
        <Icon name="terminal" size={1.05} />
        <h3>Güven Ölçümü ve Masaüstü Yardımcı</h3>
      </div>
      <p class="sub-text">Tahmin tutarlılığını kaydedin veya kontrollü görev planı hazırlayın.</p>
      <div class="inline-controls">
        <input type="number" min="0" max="1" step="0.05" class="field-input" bind:value={calScore} />
        <input type="text" class="field-input" bind:value={calNote} placeholder="Ölçüm notu..." />
        <button type="button" class="btn btn-secondary btn-sm" on:click={addCalibrationObs} disabled={calBusy}>
          Kaydet
        </button>
      </div>
      {#if calNotice}<div class="alert-banner ok">{calNotice}</div>{/if}
      {#if calibrationData}
        <p class="small-note">Kayıtlı ölçüm sayısı: {calibrationData.count ?? calibrationData.observations?.length ?? 0}</p>
      {/if}
      <div class="divider"></div>
      <input type="text" class="field-input" bind:value={interpPrompt} placeholder="Yardımcı asistan ne yapsın? (önce plan gösterir)" />
      <button type="button" class="btn btn-secondary btn-sm" on:click={runInterpreterPlan} disabled={interpBusy || !interpPrompt.trim()}>
        {interpBusy ? 'Hazırlanıyor...' : 'Plan Hazırla'}
      </button>
      {#if interpError}<div class="alert-banner err">{interpError}</div>{/if}
      {#if interpResult}<pre class="json-pre">{JSON.stringify(interpResult, null, 2)}</pre>{/if}
    </section>
  </div>

  <!-- ALT KISIM: Güvenlik Kalkanı + Sistem Özeti -->
  <div class="tools-grid">
    <section class="card block-card">
      <div class="title-with-icon">
        <Icon name="shield" size={1.05} />
        <h3>18 Yaş Altı Koruma Kilidi</h3>
      </div>
      <p class="sub-text">
        İncelenen hesap 18 yaşından küçük birine aitse yalnızca aile güvenliği kapsamında sıkı denetim açılır; aksi halde analiz engellenir.
      </p>
      <div class="inline-checks">
        <label><input type="checkbox" bind:checked={minorSubjectIsMinor} /> Hesap sahibi 18 yaş altında</label>
        <label><input type="checkbox" bind:checked={minorFamilyNotified} /> Aile onayı / bildirimi var</label>
      </div>
      <div class="inline-controls">
        <input type="text" class="field-input" bind:value={minorReason} placeholder="Koruma gerekçesi" />
        <button type="button" class="btn btn-secondary btn-sm" on:click={() => updateMinorGuard('set')} disabled={minorBusy}>
          Durumu Uygula
        </button>
        <button type="button" class="btn btn-ghost btn-sm" on:click={() => updateMinorGuard('clear')} disabled={minorBusy}>
          Kilidi Temizle
        </button>
      </div>
      {#if minorNotice}<div class="alert-banner ok">{minorNotice}</div>{/if}
      {#if minorState}
        <p class="small-note">Güncel koruma durumu: {minorState.subject_is_minor ? '18 Yaş Altı Kalkanı Açık' : 'Standart Yetişkin Modu'}</p>
      {/if}
    </section>

    <section class="card block-card">
      <div class="title-with-icon">
        <Icon name="sliders" size={1.05} />
        <h3>Sistem ve Dış Bağlantı Özeti</h3>
      </div>
      <div class="summary-kv">
        <div><span>Sistem Durumu:</span><strong>{healthDetail?.status || 'Bilinmiyor'}</strong></div>
        <div><span>Dış Araç Köprüsü (MCP):</span><strong>{mcpStatus?.connected_count ?? mcpStatus?.servers?.length ?? 0}</strong></div>
        <div>
          <span>Aktif Model Sağlayıcıları:</span>
          <strong>
            {Array.isArray(routingData?.provider_keys_set) && routingData.provider_keys_set.length > 0
              ? routingData.provider_keys_set.join(', ')
              : routingData?.has_openrouter
                ? '9Router / OpenRouter'
                : routingData?.use_local
                  ? 'Yerel Model'
                  : 'Seçilmedi'}
          </strong>
        </div>
      </div>
    </section>
  </div>
</div>

<style>
  .tab-wrap {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .head-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .block-card {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 11px;
  }

  .block-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }

  .block-card h3 {
    font-size: 15px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .title-with-icon {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .sub-text,
  .small-note {
    font-size: 12.5px;
    color: var(--text-muted);
    line-height: 1.45;
  }

  .cap-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    justify-content: space-between;
  }

  .search-box {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1 1 240px;
    color: var(--text-muted);
  }

  .filter-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .filter-pill {
    padding: 6px 12px;
    border-radius: 999px;
    border: 1px solid var(--border-strong);
    background: var(--bg-input);
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.14s ease;
  }

  .filter-pill:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .filter-pill.active {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-contrast);
  }

  .cap-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(235px, 1fr));
    gap: 10px;
  }

  .cap-card {
    padding: 11px 12px;
    border-radius: 9px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .cap-card.cap-ready {
    border-color: rgba(138, 170, 114, 0.42);
  }

  .cap-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    font-size: 12.5px;
  }

  .cap-reason {
    font-size: 11.5px;
    color: var(--text-muted);
  }

  .cap-reason.ok-text {
    color: var(--accent-2);
  }

  .tools-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 16px;
  }

  .inline-controls {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }

  .inline-controls .field-input,
  .inline-controls .field-select {
    flex: 1 1 130px;
  }

  .inline-checks {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    font-size: 12.5px;
    color: var(--text-secondary);
  }

  .inline-checks label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
  }

  .divider {
    height: 1px;
    background: var(--border);
    margin: 4px 0;
  }

  .summary-kv {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .summary-kv div {
    display: flex;
    justify-content: space-between;
    padding: 8px 10px;
    border-radius: 8px;
    background: var(--bg-elevated);
    font-size: 13px;
  }

  .summary-kv span {
    color: var(--text-muted);
  }

  .json-pre {
    padding: 10px;
    border-radius: 8px;
    background: var(--bg-input);
    border: 1px solid var(--border);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px;
    max-height: 200px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--text-secondary);
  }
</style>
