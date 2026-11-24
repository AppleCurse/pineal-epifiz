<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '../Icon.svelte';
  import { apiFetch, clientId } from '../../store';
  import { reasonLabel } from '../../lib/channelStatus';

  export let targetUrl: string = '';

  let statusLoading = false;
  let companyStatus: any = null;

  let domainInput = '';
  let limitCount = 15;
  let selectedModes: Record<'harvester' | 'seo' | 'people', boolean> = {
    harvester: true,
    seo: true,
    people: true,
  };

  let scanBusy = false;
  let scanError = '';
  let scanResult: any = null;

  const MODE_META: Record<string, { title: string; hint: string }> = {
    harvester: {
      title: 'E-posta ve Alt Alan Adı Toplayıcı',
      hint: 'Şirketin açık internette görünen kurumsal e-posta adreslerini ve alt sitelerini listeler.',
    },
    seo: {
      title: 'Site Yapısı ve Arama Görünürlüğü',
      hint: 'Sayfa başlıklarını, arama motoru etiketlerini ve teknik site sağlığını okur.',
    },
    people: {
      title: 'Çalışan ve Ekip İzi',
      hint: 'Şirket adına bağlı herkese açık ekip ve uzman profillerini tarar.',
    },
  };

  function prefillDomain() {
    if (domainInput.trim()) return;
    const raw = (targetUrl || '').trim();
    if (!raw) return;
    try {
      if (raw.startsWith('http://') || raw.startsWith('https://')) {
        domainInput = new URL(raw).hostname.replace(/^www\./, '');
      } else if (raw.includes('.') && !raw.includes(' ') && !raw.includes('@')) {
        domainInput = raw.replace(/^www\./, '').split('/')[0];
      }
    } catch {
      /* geçersiz adres olursa dokunma */
    }
  }

  async function loadCompanyStatus() {
    statusLoading = true;
    try {
      const res = await apiFetch('/api/company/status');
      if (res.ok) {
        companyStatus = await res.json();
      }
    } catch {
      /* sessizce geç */
    } finally {
      statusLoading = false;
    }
  }

  async function runCompanyScan() {
    const cleanDomain = domainInput
      .trim()
      .replace(/^https?:\/\//i, '')
      .replace(/^www\./i, '')
      .split('/')[0];
    if (!cleanDomain || scanBusy) return;

    const modes = (Object.keys(selectedModes) as Array<'harvester' | 'seo' | 'people'>).filter(
      (m) => selectedModes[m]
    );
    if (modes.length === 0) {
      scanError = 'Lütfen en az bir tarama başlığı işaretleyin.';
      return;
    }

    scanBusy = true;
    scanError = '';
    scanResult = null;
    try {
      const res = await apiFetch('/api/company/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          domain: cleanDomain,
          client_id: $clientId || 'default',
          modes,
          limit: Number(limitCount) || 15,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        scanError = data?.error?.message || data?.detail || `İşlem tamamlanamadı (${res.status}).`;
      } else {
        scanResult = data;
      }
    } catch {
      scanError = 'Sunucuyla bağlantı kurulamadı. Lütfen bağlantıyı kontrol edin.';
    } finally {
      scanBusy = false;
    }
  }

  onMount(() => {
    prefillDomain();
    loadCompanyStatus();
  });
</script>

<div class="tab-wrap">
  <div class="section-head">
    <div>
      <h2 class="section-title">Şirket &amp; İnternet Sitesi Taraması</h2>
      <p class="section-intro">
        Bir firmanın internet sitesini yazarak kurumsal e-postalarını, site yapısını ve açık ekip profillerini tek ekranda toplayın.
      </p>
    </div>
    <button
      type="button"
      class="btn btn-secondary btn-sm"
      on:click={loadCompanyStatus}
      disabled={statusLoading}
    >
      <Icon name="refresh" size={0.9} />
      {statusLoading ? 'Kontrol ediliyor...' : 'Araç Durumunu Yenile'}
    </button>
  </div>

  {#if companyStatus}
    <div class="card status-strip">
      <div class="strip-head">
        <span class="strip-title">Kullanılabilir Araçlar</span>
        <span class="pill" class:pill-ok={companyStatus.any_available} class:pill-warn={!companyStatus.any_available}>
          {companyStatus.any_available ? 'En az bir araç hazır' : 'Ek kurulum gerekiyor'}
        </span>
      </div>
      <div class="mode-badges">
        {#each companyStatus.modes || [] as m}
          <div class="mode-badge-card">
            <div class="mode-badge-top">
              <strong>{MODE_META[m.mode]?.title || m.mode}</strong>
              <span class="pill" class:pill-ok={m.available} class:pill-warn={!m.available}>
                {m.available ? 'Hazır' : reasonLabel(m.reason || 'blocked')}
              </span>
            </div>
            <p class="mode-hint">{MODE_META[m.mode]?.hint || ''}</p>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <div class="card form-card">
    <div class="form-grid">
      <label class="field-label domain-field">
        <span>Şirket İnternet Sitesi (Alan Adı)</span>
        <input
          type="text"
          class="field-input"
          bind:value={domainInput}
          placeholder="Örn: ornekfirma.com"
          on:keydown={(e) => e.key === 'Enter' && runCompanyScan()}
        />
      </label>

      <label class="field-label limit-field">
        <span>En Fazla Kayıt Sayısı</span>
        <input type="number" class="field-input" min="1" max="100" bind:value={limitCount} />
      </label>
    </div>

    <div class="checks-row">
      <span class="checks-label">Hangi bilgiler taransın?</span>
      <div class="check-pills">
        <label class="check-chip" class:active={selectedModes.harvester}>
          <input type="checkbox" bind:checked={selectedModes.harvester} />
          <span>E-posta ve Alt Siteler</span>
        </label>
        <label class="check-chip" class:active={selectedModes.seo}>
          <input type="checkbox" bind:checked={selectedModes.seo} />
          <span>Site Yapısı ve Arama</span>
        </label>
        <label class="check-chip" class:active={selectedModes.people}>
          <input type="checkbox" bind:checked={selectedModes.people} />
          <span>Çalışan İzleri</span>
        </label>
      </div>
    </div>

    <div class="actions-row">
      <button
        type="button"
        class="btn btn-primary"
        on:click={runCompanyScan}
        disabled={scanBusy || !domainInput.trim()}
      >
        <Icon name="building" size={1} />
        {scanBusy ? 'Şirket taranıyor...' : 'Şirket Taramasını Başlat'}
      </button>
    </div>

    {#if scanError}
      <div class="alert-banner err">{scanError}</div>
    {/if}
  </div>

  {#if scanResult}
    {@const entries = Object.entries(scanResult.results || {})}
    {#if entries.length === 0}
      <div class="empty-state">Tarama tamamlandı ancak gösterilecek sonuç dönmedi.</div>
    {:else}
      <div class="results-grid">
        {#each entries as [modeKey, item]}
          {@const entry = item as any}
          <section class="card result-card">
            <div class="result-head">
              <div>
                <h3>{MODE_META[modeKey]?.title || modeKey}</h3>
                {#if entry.notes}
                  <p class="result-note">{entry.notes}</p>
                {/if}
              </div>
              <span class="pill" class:pill-ok={entry.available} class:pill-warn={!entry.available}>
                {entry.available ? 'Tamamlandı' : reasonLabel(entry.denied_by || entry.reason || 'blocked')}
              </span>
            </div>

            {#if entry.counts && Object.keys(entry.counts).length > 0}
              <div class="counts-row">
                {#each Object.entries(entry.counts) as [k, v]}
                  <span class="pill">{k}: <strong>{v}</strong></span>
                {/each}
              </div>
            {/if}

            {#if Array.isArray(entry.evidence) && entry.evidence.length > 0}
              <ul class="evidence-list">
                {#each entry.evidence.slice(0, 25) as ev}
                  <li>
                    {#if typeof ev === 'string'}
                      <span>{ev}</span>
                    {:else}
                      <strong>{ev.title || ev.kind || ev.type || ev.label || 'Bulgu'}:</strong>
                      <span>{ev.value || ev.url || ev.email || ev.summary || JSON.stringify(ev)}</span>
                    {/if}
                  </li>
                {/each}
              </ul>
            {:else if !entry.available && entry.reason}
              <div class="alert-banner warn">
                Bu bölüm şu an çalıştırılamadı: {reasonLabel(entry.reason)} ({entry.reason})
              </div>
            {:else}
              <p class="empty-note">Bu başlık altında yeni kayıt bulunamadı.</p>
            {/if}
          </section>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .tab-wrap {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .status-strip,
  .form-card {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .strip-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  .strip-title {
    font-weight: 700;
    font-size: 13px;
    color: var(--text-primary);
  }

  .mode-badges {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 10px;
  }

  .mode-badge-card {
    padding: 11px 12px;
    border: 1px solid var(--border);
    border-radius: 9px;
    background: var(--bg-elevated);
  }

  .mode-badge-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 12.5px;
  }

  .mode-hint {
    margin-top: 5px;
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.4;
  }

  .form-grid {
    display: grid;
    grid-template-columns: 1fr 160px;
    gap: 12px;
  }

  @media (max-width: 640px) {
    .form-grid {
      grid-template-columns: 1fr;
    }
  }

  .checks-row {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .checks-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .check-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .check-chip {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 7px 12px;
    border-radius: 8px;
    border: 1px solid var(--border-strong);
    background: var(--bg-input);
    font-size: 12.5px;
    cursor: pointer;
    user-select: none;
  }

  .check-chip.active {
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--text-primary);
  }

  .actions-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }

  .results-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 14px;
  }

  .result-card {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .result-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
  }

  .result-head h3 {
    font-size: 14px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .result-note {
    margin-top: 3px;
    font-size: 12px;
    color: var(--text-muted);
  }

  .counts-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .evidence-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 280px;
    overflow-y: auto;
  }

  .evidence-list li {
    padding: 8px 10px;
    border-radius: 7px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    font-size: 12.5px;
    color: var(--text-secondary);
    word-break: break-word;
  }

  .empty-note {
    font-size: 12.5px;
    color: var(--text-muted);
  }
</style>
