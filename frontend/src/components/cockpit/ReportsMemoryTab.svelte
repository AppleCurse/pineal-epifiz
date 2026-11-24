<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '../Icon.svelte';
  import { apiFetch, clientId, taskStatus } from '../../store';

  export let pastTasks: any[] = [];
  export let taskHistoryLoading: boolean = false;
  export let reportStatusData: any = null;
  export let reportList: any[] = [];
  export let reportBuildBusy: boolean = false;
  export let reportBuildResult: any = null;
  export let reportTitle: string = '';
  export let targetUrl: string = '';
  export let onLoadTaskHistory: () => void = () => {};
  export let onLoadPastTask: (id: string) => void = () => {};
  export let onDeletePastTask: (id: string) => void = () => {};
  export let onLoadReportCenter: () => void = () => {};
  export let onBuildReport: () => void = () => {};

  let inspectedTaskId = '';
  let detailViewMode: 'graph' | 'changes' | 'memory' | null = null;
  let detailBusy = false;
  let detailData: any = null;
  let detailError = '';

  // Kalıcı Hafıza Sorgulama
  let memoryTarget = '';
  let memoryQuery = '';
  let memoryBusy = false;
  let memoryResult: any = null;
  let memoryError = '';

  // Örnek Raporlar (Kayıtsız Demolar)
  let demoReports: any[] = [];
  let demoLoading = false;
  let activeDemoReport: any = null;

  let downloadError = '';

  async function inspectTaskDetail(taskId: string, kind: 'graph' | 'changes' | 'memory') {
    inspectedTaskId = taskId;
    detailViewMode = kind;
    detailBusy = true;
    detailError = '';
    detailData = null;
    try {
      const cid = encodeURIComponent($clientId || 'default');
      const res = await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}/${kind}?client_id=${cid}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        detailError = data?.error?.message || data?.detail || `Bilgi alınamadı (${res.status}).`;
      } else {
        detailData = data;
      }
    } catch {
      detailError = 'Ayrıntılar alınırken bağlantı hatası oluştu.';
    } finally {
      detailBusy = false;
    }
  }

  $: normalizedFormats = Array.isArray(reportStatusData?.formats)
    ? reportStatusData.formats.map((item: any) => ({
        name: item.format || item.name || '',
        available: Boolean(item.available),
      }))
    : reportStatusData?.formats && typeof reportStatusData.formats === 'object'
      ? Object.entries(reportStatusData.formats).map(([k, v]: [string, any]) => ({
          name: k,
          available: typeof v === 'object' ? Boolean(v?.available) : Boolean(v),
        }))
      : [];

  async function downloadReportFile(urlOrFilename: string, suggestedName?: string) {
    downloadError = '';
    try {
      const cid = encodeURIComponent($clientId || 'default');
      const targetUrl = urlOrFilename.startsWith('/')
        ? `${urlOrFilename}${urlOrFilename.includes('?') ? '&' : '?'}client_id=${cid}`
        : `/api/report/file/${encodeURIComponent(urlOrFilename)}?client_id=${cid}`;
      const res = await apiFetch(targetUrl);
      if (!res.ok) {
        downloadError = `Dosya indirilemedi (${res.status}).`;
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = suggestedName || urlOrFilename.split('/').pop() || 'rapor';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      downloadError = 'Dosya indirilirken bağlantı kesildi.';
    }
  }

  async function queryMemorySummary() {
    const t = memoryTarget.trim();
    if (!t || memoryBusy) return;
    memoryBusy = true;
    memoryError = '';
    memoryResult = null;
    try {
      const endpoint = memoryQuery.trim()
        ? `/api/memory/${encodeURIComponent(t)}/recall?query=${encodeURIComponent(memoryQuery.trim())}&k=8`
        : `/api/memory/${encodeURIComponent(t)}`;
      const res = await apiFetch(endpoint);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        memoryError = data?.error?.message || data?.detail || `Hafıza okunamadı (${res.status}).`;
      } else {
        memoryResult = data;
      }
    } catch {
      memoryError = 'Hafıza sistemine bağlanılamadı.';
    } finally {
      memoryBusy = false;
    }
  }

  async function loadDemoReports() {
    demoLoading = true;
    try {
      const res = await apiFetch('/api/public/demo-reports');
      if (res.ok) {
        const data = await res.json();
        demoReports = Array.isArray(data) ? data : data.reports || data.items || [];
      }
    } catch {
      /* sessizce geç */
    } finally {
      demoLoading = false;
    }
  }

  async function openDemoDetail(id: string) {
    try {
      const res = await apiFetch(`/api/public/demo-reports/${encodeURIComponent(id)}`);
      if (res.ok) {
        activeDemoReport = await res.json();
      }
    } catch {
      /* sessizce geç */
    }
  }

  onMount(() => {
    if (!memoryTarget && targetUrl) {
      memoryTarget = targetUrl.replace(/^@/, '');
    }
    onLoadTaskHistory();
    onLoadReportCenter();
    loadDemoReports();
  });
</script>

<div class="tab-wrap">
  <div class="section-head">
    <div>
      <h2 class="section-title">Raporlar, Geçmiş ve Hafıza Arşivi</h2>
      <p class="section-intro">
        Yaptığınız eski analizlere dönün, kalıcı dosyalar (PDF, şema, özet) üretin veya hedeflerin geçmiş hafızasını sorgulayın.
      </p>
    </div>
    <div class="head-actions">
      <button type="button" class="btn btn-secondary btn-sm" on:click={onLoadTaskHistory} disabled={taskHistoryLoading}>
        <Icon name="refresh" size={0.9} />
        Geçmişi Yenile
      </button>
      <button type="button" class="btn btn-secondary btn-sm" on:click={onLoadReportCenter}>
        <Icon name="file" size={0.9} />
        Raporları Yenile
      </button>
    </div>
  </div>

  <!-- ÜST BÖLÜM: Rapor Oluşturucu -->
  <section class="card block-card">
    <div class="block-head">
      <div>
        <h3>Dosya Halinde Rapor Üret</h3>
        <p class="sub-text">
          Aktif çalışmanızdan bilgisayarınıza indirebileceğiniz düzenli bir rapor paketi (yazılı özet, PDF, ilişki şeması ve video) çıkarır.
        </p>
      </div>
      {#if normalizedFormats.length > 0}
        <div class="format-badges">
          {#each normalizedFormats as fmt}
            <span class="pill" class:pill-ok={fmt.available} class:pill-warn={!fmt.available}>
              {fmt.name}: {fmt.available ? 'Hazır' : 'Eksik'}
            </span>
          {/each}
        </div>
      {/if}
    </div>

    <div class="build-row">
      <input
        type="text"
        class="field-input"
        bind:value={reportTitle}
        placeholder="Rapor başlığı (boş bırakırsanız otomatik verilir)"
      />
      <button
        type="button"
        class="btn btn-primary"
        on:click={onBuildReport}
        disabled={reportBuildBusy || !$taskStatus}
      >
        <Icon name="file" size={0.95} />
        {reportBuildBusy ? 'Hazırlanıyor...' : 'Rapor Paketini Oluştur'}
      </button>
    </div>

    {#if !$taskStatus}
      <p class="sub-text">Not: Önce Ana Ekran'dan bir analiz başlatmalı ya da aşağıdan eski bir işi yüklemelisiniz.</p>
    {/if}

    {#if reportBuildResult}
      <div class="alert-banner ok">
        Rapor paketi hazırlandı. Aşağıdaki listeden dosyaları bilgisayarınıza indirebilirsiniz.
      </div>
    {/if}
    {#if downloadError}
      <div class="alert-banner err">{downloadError}</div>
    {/if}

    {#if reportList.length > 0}
      <div class="file-list">
        {#each reportList as rf}
          {#if typeof rf === 'string'}
            <div class="file-row">
              <div class="file-info">
                <Icon name="file" size={0.95} />
                <span>{rf}</span>
              </div>
              <button type="button" class="btn btn-secondary btn-sm" on:click={() => downloadReportFile(rf)}>
                <Icon name="download" size={0.9} />
                İndir
              </button>
            </div>
          {:else}
            <div class="file-row">
              <div class="file-info">
                <Icon name="file" size={0.95} />
                <div>
                  <strong>{rf.title || rf.filename || rf.name || 'Rapor'}</strong>
                  {#if rf.created_at}<small class="small-meta">{rf.created_at}</small>{/if}
                </div>
              </div>
              <div class="task-actions">
                {#each rf.artifacts || [] as art}
                  <button
                    type="button"
                    class="btn btn-secondary btn-sm"
                    on:click={() => downloadReportFile(art.download_url || art.name, art.name)}
                  >
                    <Icon name="download" size={0.9} />
                    {art.name}
                  </button>
                {/each}
              </div>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  </section>

  <!-- ORTA BÖLÜM: Geçmiş Görevler -->
  <section class="card block-card">
    <div class="block-head">
      <div>
        <h3>Önceki Çalışmalar</h3>
        <p class="sub-text">Kayıtlı eski bir çalışmayı ana ekrana geri getirebilir, ilişki haritasına ve değişimlere bakabilirsiniz.</p>
      </div>
      <span class="pill">{pastTasks.length} kayıt</span>
    </div>

    {#if taskHistoryLoading}
      <div class="empty-state">Geçmiş çalışmalar yükleniyor...</div>
    {:else if pastTasks.length === 0}
      <div class="empty-state">Henüz kaydedilmiş bir geçmiş çalışma yok.</div>
    {:else}
      <div class="task-list">
        {#each pastTasks as t}
          <div class="task-row">
            <div class="task-meta">
              <strong>{t.task_id}</strong>
              <span class="small-meta">{t.target_url || t.url || ''} • {t.status || 'tamamlandı'} • {t.last_updated || t.created_at || t.updated_at || ''}</span>
            </div>
            <div class="task-actions">
              <button type="button" class="btn btn-primary btn-sm" on:click={() => onLoadPastTask(t.task_id)}>
                Ekrana Yükle
              </button>
              <button type="button" class="btn btn-ghost btn-sm" on:click={() => inspectTaskDetail(t.task_id, 'graph')}>
                İlişki Ağı
              </button>
              <button type="button" class="btn btn-ghost btn-sm" on:click={() => inspectTaskDetail(t.task_id, 'changes')}>
                Değişimler
              </button>
              <button type="button" class="btn btn-ghost btn-sm" on:click={() => inspectTaskDetail(t.task_id, 'memory')}>
                Hafıza
              </button>
              <button type="button" class="btn btn-danger btn-sm" on:click={() => onDeletePastTask(t.task_id)}>
                <Icon name="trash" size={0.85} />
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}

    {#if inspectedTaskId && detailViewMode}
      <div class="detail-box">
        <div class="detail-head">
          <strong>Seçili Çalışma Ayrıntısı ({inspectedTaskId})</strong>
          <button type="button" class="btn btn-ghost btn-sm" on:click={() => { detailViewMode = null; }}>
            Kapat
          </button>
        </div>
        {#if detailBusy}
          <p class="sub-text">Ayrıntılar okunuyor...</p>
        {:else if detailError}
          <div class="alert-banner err">{detailError}</div>
        {:else if detailData}
          <pre class="json-pre">{JSON.stringify(detailData, null, 2)}</pre>
        {/if}
      </div>
    {/if}
  </section>

  <!-- ALT İKİLİ: Hafıza Arama + Hazır Örnek Raporlar -->
  <div class="bottom-grid">
    <section class="card block-card">
      <h3>Hedef Hafızasında Ara</h3>
      <p class="sub-text">Daha önce incelenen bir kişi veya kurum hakkında sistemin aklında ne kaldığını kontrol edin.</p>
      <label class="field-label">
        <span>Hedef Adı veya Bağlantı</span>
        <input type="text" class="field-input" bind:value={memoryTarget} placeholder="Örn: @kullanici veya firma.com" />
      </label>
      <label class="field-label">
        <span>Aranacak Konu (İsteğe Bağlı)</span>
        <input type="text" class="field-input" bind:value={memoryQuery} placeholder="Örn: müzik zevki, e-posta, iş..." />
      </label>
      <button type="button" class="btn btn-secondary" on:click={queryMemorySummary} disabled={memoryBusy || !memoryTarget.trim()}>
        <Icon name="search" size={0.95} />
        {memoryBusy ? 'Aranıyor...' : 'Hafızada Ara'}
      </button>
      {#if memoryError}
        <div class="alert-banner err">{memoryError}</div>
      {/if}
      {#if memoryResult}
        <pre class="json-pre">{JSON.stringify(memoryResult, null, 2)}</pre>
      {/if}
    </section>

    <section class="card block-card">
      <div class="block-head">
        <div>
          <h3>Hazır Örnek Raporlar</h3>
          <p class="sub-text">Sistemi tanımak için hiçbir kurulum gerektirmeyen örnek analiz dosyalarını inceleyin.</p>
        </div>
        {#if demoLoading}
          <span class="pill">Yükleniyor...</span>
        {/if}
      </div>
      {#if demoReports.length === 0}
        <div class="empty-state">Gösterilecek örnek rapor bulunamadı.</div>
      {:else}
        <div class="demo-list">
          {#each demoReports as d}
            <button type="button" class="demo-item" on:click={() => openDemoDetail(d.id || d.report_id)}>
              <strong>{d.title || d.name || d.id}</strong>
              <span>{d.summary || 'Örnek raporu görmek için tıklayın'}</span>
            </button>
          {/each}
        </div>
      {/if}
      {#if activeDemoReport}
        <pre class="json-pre">{JSON.stringify(activeDemoReport, null, 2)}</pre>
      {/if}
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
    gap: 8px;
    flex-wrap: wrap;
  }

  .block-card {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
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

  .sub-text {
    font-size: 12.5px;
    color: var(--text-muted);
    margin-top: 3px;
  }

  .format-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .build-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }

  .build-row .field-input {
    flex: 1 1 240px;
  }

  .file-list,
  .task-list,
  .demo-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .file-row,
  .task-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
    padding: 10px 12px;
    border-radius: 9px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
  }

  .file-info {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 500;
  }

  .task-meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .small-meta {
    font-size: 11.5px;
    color: var(--text-muted);
  }

  .task-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .detail-box {
    padding: 12px;
    border-radius: 10px;
    border: 1px solid var(--border-strong);
    background: var(--bg-input);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .detail-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .bottom-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 16px;
  }

  .demo-item {
    text-align: left;
    padding: 10px 12px;
    border-radius: 9px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    color: var(--text-primary);
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .demo-item:hover {
    background: var(--bg-hover);
    border-color: var(--accent);
  }

  .demo-item span {
    font-size: 12px;
    color: var(--text-muted);
  }

  .json-pre {
    padding: 10px;
    border-radius: 8px;
    background: var(--bg-input);
    border: 1px solid var(--border);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px;
    max-height: 240px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--text-secondary);
  }
</style>
