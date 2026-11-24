<script lang="ts">
  import Icon from '../Icon.svelte';
  import { apiFetch, clientId, taskStatus } from '../../store';

  export let showHistoryModal: boolean = false;
  export let historyModalTab: 'tasks' | 'reports' = 'tasks';
  export let pastTasks: any[] = [];
  export let taskHistoryLoading: boolean = false;
  export let tasksError: string = '';
  export let reportStatusData: any = null;
  export let reportList: any[] = [];
  export let reportFormats: Record<string, boolean> = {
    markdown: true,
    pdf: true,
    diagram: true,
    video: false,
  };
  export let reportBuildBusy: boolean = false;
  export let reportBuildResult: any = null;
  export let reportBuildError: string = '';
  export let reportTitle: string = '';

  export let onClose: () => void = () => {};
  export let onRefreshTasks: () => void = () => {};
  export let onRefreshReports: () => void = () => {};
  export let onLoadPastTask: (id: string) => void = () => {};
  export let onDeletePastTask: (id: string) => void = () => {};
  export let onBuildReport: () => void = () => {};

  let downloadError = '';

  $: normalizedFormats = Array.isArray(reportStatusData?.formats)
    ? reportStatusData.formats.map((item: any) => ({
        name: item.format || item.name || '',
        available: Boolean(item.available),
        reason: item.reason || '',
      }))
    : reportStatusData?.formats && typeof reportStatusData.formats === 'object'
      ? Object.entries(reportStatusData.formats).map(([k, v]: [string, any]) => ({
          name: k,
          available: typeof v === 'object' ? Boolean(v?.available) : Boolean(v),
          reason: typeof v === 'object' ? String(v?.reason || '') : '',
        }))
      : [];

  async function downloadArtifact(urlOrFilename: string, suggestedName?: string) {
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
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = suggestedName || urlOrFilename.split('/').pop() || 'rapor';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(blobUrl);
    } catch {
      downloadError = 'İndirme sırasında bağlantı hatası oluştu.';
    }
  }
</script>

{#if showHistoryModal}
  <div class="modal-backdrop" role="presentation" on:click|self={onClose}>
    <div class="modal-dialog" role="dialog" aria-modal="true" aria-label="Geçmiş ve Rapor Fabrikası">
      <header class="modal-header">
        <div>
          <h3>Geçmiş Çalışmalar ve Rapor Fabrikası</h3>
          <p class="modal-sub">Önceki analizleri ekrana geri alabilir veya dosya halinde paket rapor üretebilirsiniz.</p>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" on:click={onClose} aria-label="Kapat">
          <Icon name="close" size={1} />
        </button>
      </header>

      <div class="modal-tabs">
        <button
          type="button"
          class="tab-pill"
          class:active={historyModalTab === 'tasks'}
          on:click={() => { historyModalTab = 'tasks'; onRefreshTasks(); }}
        >
          Önceki Çalışmalar ({pastTasks.length})
        </button>
        <button
          type="button"
          class="tab-pill"
          class:active={historyModalTab === 'reports'}
          on:click={() => { historyModalTab = 'reports'; onRefreshReports(); }}
        >
          Rapor Fabrikası
        </button>
      </div>

      <div class="modal-body">
        {#if historyModalTab === 'tasks'}
          {#if tasksError}
            <div class="alert-banner err">{tasksError}</div>
          {/if}
          {#if taskHistoryLoading}
            <div class="empty-state">Geçmiş çalışmalar okunuyor...</div>
          {:else if pastTasks.length === 0}
            <div class="empty-state">Henüz kaydedilmiş geçmiş çalışma yok.</div>
          {:else}
            <div class="list-col">
              {#each pastTasks as t}
                <div class="item-row">
                  <div class="item-meta">
                    <strong>{t.task_id}</strong>
                    <small>
                      {t.target_url || t.url || ''} • {t.status || 'tamamlandı'} • {t.last_updated || t.created_at || t.updated_at || ''}
                    </small>
                  </div>
                  <div class="item-actions">
                    <button type="button" class="btn btn-primary btn-sm" on:click={() => onLoadPastTask(t.task_id)}>
                      YÜKLE
                    </button>
                    <button type="button" class="btn btn-danger btn-sm" on:click={() => onDeletePastTask(t.task_id)}>
                      SİL
                    </button>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        {:else}
          <div class="factory-box">
            <div class="factory-head">
              <strong>Rapor Fabrikası</strong>
              {#if normalizedFormats.length > 0}
                <div class="badges-row">
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
                placeholder="Rapor başlığı (isteğe bağlı)"
              />
              <button
                type="button"
                class="btn btn-primary"
                on:click={onBuildReport}
                disabled={reportBuildBusy || !$taskStatus}
              >
                {reportBuildBusy ? 'Hazırlanıyor...' : 'RAPOR PAKETİ ÜRET'}
              </button>
            </div>

            <div class="fmt-checks">
              <label><input type="checkbox" bind:checked={reportFormats.markdown} /> Yazılı Özet</label>
              <label><input type="checkbox" bind:checked={reportFormats.pdf} /> PDF Belgesi</label>
              <label><input type="checkbox" bind:checked={reportFormats.diagram} /> İlişki Şeması</label>
              <label><input type="checkbox" bind:checked={reportFormats.video} /> Özet Video</label>
            </div>

            {#if reportBuildError}
              <div class="alert-banner err">{reportBuildError}</div>
            {/if}

            {#if reportBuildResult}
              <div class="alert-banner ok">
                <span class="pill pill-ok">ÜRETİLDİ</span>
                <span>Rapor paketi hazırlandı ({reportBuildResult.title || 'Rapor'}).</span>
              </div>
            {/if}
            {#if downloadError}
              <div class="alert-banner err">{downloadError}</div>
            {/if}

            {#if reportList.length > 0}
              <div class="list-col">
                {#each reportList as rf}
                  {#if typeof rf === 'string'}
                    <div class="item-row">
                      <span>{rf}</span>
                      <button type="button" class="btn btn-secondary btn-sm" on:click={() => downloadArtifact(rf)}>
                        <Icon name="download" size={0.85} />
                        İndir
                      </button>
                    </div>
                  {:else}
                    <div class="report-card">
                      <div class="report-card-top">
                        <div>
                          <strong>{rf.title || rf.filename || rf.name || 'Rapor'}</strong>
                          {#if rf.subject || rf.created_at}
                            <small class="sub-line">{rf.subject || ''} {rf.created_at ? `• ${rf.created_at}` : ''}</small>
                          {/if}
                        </div>
                        {#if rf.evidence_count !== undefined}
                          <span class="pill">{rf.evidence_count} kanıt</span>
                        {/if}
                      </div>
                      {#if Array.isArray(rf.artifacts) && rf.artifacts.length > 0}
                        <div class="artifact-btns">
                          {#each rf.artifacts as art}
                            <button
                              type="button"
                              class="btn btn-secondary btn-sm"
                              on:click={() => downloadArtifact(art.download_url || art.name, art.name)}
                            >
                              <Icon name="download" size={0.85} />
                              {art.name}
                            </button>
                          {/each}
                        </div>
                      {/if}
                    </div>
                  {/if}
                {/each}
              </div>
            {:else}
              <div class="empty-state">Henüz üretilmiş dosya raporu yok.</div>
            {/if}
          </div>
        {/if}
      </div>

      <footer class="modal-footer">
        <button type="button" class="btn btn-ghost" on:click={onClose}>Kapat</button>
      </footer>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(2, 6, 23, 0.72);
    backdrop-filter: blur(4px);
    z-index: 60;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
  }

  .modal-dialog {
    width: 100%;
    max-width: 780px;
    max-height: 88vh;
    background: var(--bg-surface);
    border: 1px solid var(--border-strong);
    border-radius: 14px;
    box-shadow: var(--shadow-md);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .modal-header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
  }

  .modal-header h3 {
    font-size: 16px;
    font-weight: 700;
  }

  .modal-sub {
    margin-top: 4px;
    font-size: 12.5px;
    color: var(--text-muted);
  }

  .modal-tabs {
    display: flex;
    gap: 8px;
    padding: 10px 20px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-elevated);
    flex-wrap: wrap;
  }

  .tab-pill {
    padding: 6px 12px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--bg-surface);
    color: var(--text-secondary);
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
  }

  .tab-pill.active {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-contrast);
  }

  .modal-body {
    padding: 18px 20px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .factory-box,
  .list-col {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .factory-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    flex-wrap: wrap;
  }

  .badges-row,
  .fmt-checks,
  .artifact-btns {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .fmt-checks label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12.5px;
    color: var(--text-secondary);
    cursor: pointer;
  }

  .build-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }

  .build-row .field-input {
    flex: 1 1 220px;
  }

  .item-row,
  .report-card {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 11px 13px;
    border-radius: 9px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
  }

  .item-row {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
  }

  .report-card-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
  }

  .item-meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .item-meta small,
  .sub-line {
    display: block;
    font-size: 11.5px;
    color: var(--text-muted);
  }

  .item-actions {
    display: flex;
    gap: 6px;
  }

  .modal-footer {
    padding: 14px 20px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: flex-end;
    background: var(--bg-elevated);
  }
</style>
