<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Icon from './Icon.svelte';
  import { apiFetch, clientId, taskStatus, activeTargetUrl } from '../store';
  import { evidenceChainToReportItems } from '../lib/evidence';

  export let open = false;
  export let targetUrl = '';

  const dispatch = createEventDispatcher();
  let wasOpen = false;
  let historyTab: 'tasks' | 'reports' = 'tasks';
  let tasksLoading = false;
  let tasksError = '';
  let taskHistoryList: any[] = [];
  let reportStatusLoading = false;
  let reportStatusData: any = null;
  let reportListData: any[] = [];
  let reportTitle = 'Pineal Adli Analiz Raporu';
  let reportSubject = '';
  let reportFormats: Record<string, boolean> = { markdown: true, pdf: true, diagram: true, video: false };
  let reportBuilding = false;
  let reportBuildResult: any = null;
  let reportBuildError = '';
  let reportCenterError = '';

  $: if (open && !wasOpen) {
    wasOpen = true;
    reportSubject = reportSubject || targetUrl || $activeTargetUrl || $taskStatus?.target_profile?.url || '';
    void loadTaskHistory();
    void loadReportCenter();
  }
  $: if (!open) wasOpen = false;

  function close() {
    dispatch('close');
  }

  async function loadTaskHistory() {
    tasksLoading = true;
    tasksError = '';
    try {
      const cid = $clientId || 'default';
      const res = await apiFetch(`/api/tasks?client_id=${encodeURIComponent(cid)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      taskHistoryList = Array.isArray(data.tasks) ? data.tasks : [];
    } catch (e: any) {
      tasksError = e?.message || 'Görev geçmişi alınamadı';
    } finally {
      tasksLoading = false;
    }
  }

  async function loadPastTaskIntoCockpit(taskId: string) {
    tasksError = '';
    try {
      const cid = $clientId || 'default';
      const res = await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}?client_id=${encodeURIComponent(cid)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const detail = await res.json();
      taskStatus.set({
        task_id: detail.task_id,
        status: detail.status || 'completed',
        confidence: detail.confidence,
        target_profile: detail.target_profile || null,
        evidence_chain: Array.isArray(detail.evidence_chain) ? detail.evidence_chain : [],
        runs: {},
      });
      reportSubject = detail.target_profile?.url || (detail.target_profile?.username ? `@${detail.target_profile.username}` : '');
      reportTitle = `Pineal Rapor — ${detail.task_id}`;
      dispatch('taskloaded', detail);
      close();
    } catch (e: any) {
      tasksError = e?.message || 'Görev detayı yüklenemedi';
    }
  }

  async function deletePastTask(taskId: string) {
    tasksError = '';
    try {
      const cid = $clientId || 'default';
      const res = await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}?client_id=${encodeURIComponent(cid)}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadTaskHistory();
    } catch (e: any) {
      tasksError = e?.message || 'Görev silinemedi';
    }
  }

  async function loadReportCenter() {
    reportStatusLoading = true;
    reportCenterError = '';
    try {
      const cid = $clientId || 'default';
      const [sRes, lRes] = await Promise.all([
        apiFetch('/api/report/status'),
        apiFetch(`/api/report/list?client_id=${encodeURIComponent(cid)}`),
      ]);
      if (!sRes.ok) throw new Error(`Rapor durumu HTTP ${sRes.status}`);
      if (!lRes.ok) throw new Error(`Rapor listesi HTTP ${lRes.status}`);
      reportStatusData = await sRes.json();
      const lJson = await lRes.json();
      reportListData = Array.isArray(lJson.reports) ? lJson.reports : [];
    } catch (e: any) {
      reportCenterError = e?.message || 'Rapor merkezi yüklenemedi';
    } finally {
      reportStatusLoading = false;
    }
  }

  async function buildReportFromCockpit() {
    if (reportBuilding) return;
    reportBuilding = true;
    reportBuildError = '';
    reportBuildResult = null;
    const selectedFormats = Object.entries(reportFormats)
      .filter(([, on]) => on)
      .map(([fmt]) => fmt);
    if (selectedFormats.length === 0) {
      reportBuildError = 'En az bir çıktı formatı seçin.';
      reportBuilding = false;
      return;
    }
    const evidenceItems = evidenceChainToReportItems($taskStatus);
    try {
      const res = await apiFetch('/api/report/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          title: (reportTitle || 'Pineal Adli Analiz Raporu').trim(),
          subject: (reportSubject || targetUrl || $activeTargetUrl || '').trim(),
          evidence: evidenceItems,
          formats: selectedFormats,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.error?.message || `HTTP ${res.status}`);
      reportBuildResult = data;
      await loadReportCenter();
    } catch (e: any) {
      reportBuildError = e?.message || 'Rapor üretilemedi';
    } finally {
      reportBuilding = false;
    }
  }
</script>

{#if open}
  <div class="rf-backdrop" role="presentation" on:click|self={close}>
    <section class="rf-card" role="dialog" aria-modal="true" aria-label="Görev geçmişi ve rapor fabrikası">
      <header class="rf-head">
        <div>
          <h3><Icon name="scroll" size={0.95} /> GÖREV GEÇMİŞİ &amp; RAPOR FABRİKASI</h3>
          <p>Görev kayıtlarını yükleyin, kanıt zincirinden rapor paketi üretin ve önceki çıktıları indirin.</p>
        </div>
        <button class="rf-close" on:click={close} aria-label="Kapat"><Icon name="close" size={0.9} /></button>
      </header>

      <nav class="rf-tabs" aria-label="Rapor merkezi sekmeleri">
        <button class:active={historyTab === 'tasks'} on:click={() => historyTab = 'tasks'}>Görev Geçmişi ({taskHistoryList.length})</button>
        <button class:active={historyTab === 'reports'} on:click={() => historyTab = 'reports'}>Rapor Fabrikası &amp; Geçmiş Raporlar ({reportListData.length})</button>
      </nav>

      <div class="rf-body">
        {#if historyTab === 'tasks'}
          <section class="rf-panel">
            <div class="rf-toolbar">
              <h4>Kayıtlı Görevler <code>GET /api/tasks</code></h4>
              <button class="rf-secondary" on:click={loadTaskHistory} disabled={tasksLoading}>{tasksLoading ? 'Yükleniyor...' : 'Yenile'}</button>
            </div>
            {#if tasksError}<div class="rf-error" role="alert">{tasksError}</div>{/if}
            {#if tasksLoading && taskHistoryList.length === 0}
              <p class="rf-muted">Görev geçmişi yükleniyor...</p>
            {:else if taskHistoryList.length === 0}
              <p class="rf-muted">Bu oda için henüz kayıtlı görev yok.</p>
            {:else}
              <div class="rf-table-wrap">
                <table>
                  <thead><tr><th>Görev ID</th><th>Durum</th><th>Kanıt</th><th>Güven</th><th>Tarih</th><th>İşlem</th></tr></thead>
                  <tbody>
                    {#each taskHistoryList as t}
                      <tr>
                        <td class="rf-mono">{t.task_id}</td>
                        <td>{t.status || t.memory_state || '-'}</td>
                        <td>{t.evidence_count ?? 0}</td>
                        <td>{typeof t.confidence === 'number' ? Math.round(t.confidence * 100) + '%' : '-'}</td>
                        <td>{t.last_updated || '-'}</td>
                        <td class="rf-actions">
                          <button class="rf-action" on:click={() => loadPastTaskIntoCockpit(t.task_id)}>YÜKLE</button>
                          <button class="rf-action danger" on:click={() => deletePastTask(t.task_id)}>SİL</button>
                        </td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {/if}
          </section>
        {:else}
          <section class="rf-panel">
            <h4>Kanıttan Rapor Üret <code>POST /api/report/build</code></h4>
            {#if reportStatusData}
              <p class="rf-muted">Kapı: <code>{reportStatusData.gate}</code> · Dizin: <code>{reportStatusData.report_dir}</code></p>
              <div class="rf-formats">
                {#each reportStatusData.formats || [] as fmt}
                  <label class:unavailable={!fmt.available}>
                    <input type="checkbox" bind:checked={reportFormats[fmt.format]} disabled={!fmt.available} />
                    <span>{fmt.format.toUpperCase()}</span>
                    <small>{fmt.available ? 'hazır' : fmt.reason || 'kullanılamıyor'}</small>
                  </label>
                {/each}
              </div>
            {:else if reportStatusLoading}
              <p class="rf-muted">Rapor fabrikası durumu kontrol ediliyor...</p>
            {/if}
            {#if reportCenterError}<div class="rf-error" role="alert">{reportCenterError}</div>{/if}
            <div class="rf-fields">
              <label>Rapor başlığı<input bind:value={reportTitle} placeholder="Pineal Adli Analiz Raporu" /></label>
              <label>Konu / hedef<input bind:value={reportSubject} placeholder="https://instagram.com/..." /></label>
            </div>
            <p class="rf-muted">Aktif kanıt zincirinden aktarılacak kayıt: <strong>{evidenceChainToReportItems($taskStatus).length}</strong></p>
            <button class="rf-primary" on:click={buildReportFromCockpit} disabled={reportBuilding}>{reportBuilding ? 'ÜRETİLİYOR...' : 'RAPOR PAKETİ ÜRET'}</button>
            {#if reportBuildError}<div class="rf-error">{reportBuildError}</div>{/if}
            {#if reportBuildResult}
              <div class="rf-success">
                <strong>Rapor sonucu: {reportBuildResult.title}</strong>
                {#each Object.entries(reportBuildResult.formats || {}) as [fmtName, fmtRes]}
                  {@const result = fmtRes as any}
                  <div><code>{fmtName}</code>: {result.available ? 'ÜRETİLDİ' : `ENGELLENDİ / YOK (${result.denied_by || result.reason || 'bilinmiyor'})`}{#if result.manifest_sha256} · SHA-256 <code>{result.manifest_sha256.slice(0, 12)}…</code>{/if}</div>
                {/each}
              </div>
            {/if}
          </section>

          <section class="rf-panel">
            <div class="rf-toolbar">
              <h4>Geçmiş Raporlar <code>GET /api/report/list</code></h4>
              <button class="rf-secondary" on:click={loadReportCenter} disabled={reportStatusLoading}><Icon name="refresh" size={0.85} /> Yenile</button>
            </div>
            {#if reportListData.length === 0}
              <p class="rf-muted">Henüz üretilmiş rapor paketi bulunamadı.</p>
            {:else}
              <div class="rf-report-list">
                {#each reportListData as rep}
                  <article class="rf-report">
                    <div class="rf-report-head"><strong>{rep.title}</strong><span>{rep.created_at || '-'}</span></div>
                    <p>Hedef: {rep.subject || '-'} · Kanıt: {rep.evidence_count ?? 0} · Manifest: <code>{(rep.manifest_sha256 || '').slice(0, 12)}…</code></p>
                    <div class="rf-links">
                      {#each rep.artifacts || [] as art}
                        {#if art.download_url}
                          <a href={`${art.download_url}?client_id=${encodeURIComponent($clientId || 'default')}`} target="_blank" rel="noopener"><Icon name="download" size={0.85} /> {art.kind} ({art.bytes} B)</a>
                        {/if}
                      {/each}
                      {#if rep.manifest_url}
                        <a href={`${rep.manifest_url}?client_id=${encodeURIComponent($clientId || 'default')}`} target="_blank" rel="noopener"><Icon name="download" size={0.85} /> manifest.json</a>
                      {/if}
                    </div>
                  </article>
                {/each}
              </div>
            {/if}
          </section>
        {/if}
      </div>
      <footer class="rf-foot"><button class="rf-secondary" on:click={close}>Kapat</button></footer>
    </section>
  </div>
{/if}

<style>
  .rf-backdrop{position:fixed;inset:0;z-index:9999;background:rgba(2,4,10,.86);backdrop-filter:blur(9px);display:flex;align-items:center;justify-content:center;padding:1rem}
  .rf-card{width:min(920px,96vw);max-height:90vh;display:flex;flex-direction:column;overflow:hidden;background:#0b0e13;color:var(--text-primary,#e8e5dc);border:1px solid rgba(190,157,93,.42);border-radius:12px;box-shadow:0 24px 70px rgba(0,0,0,.75)}
  .rf-head{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;padding:1rem 1.25rem;border-bottom:1px solid rgba(190,157,93,.2)}
  .rf-head h3{margin:0 0 .25rem;color:#d6bd86;font-size:.9rem;letter-spacing:.06em}
  .rf-head p{margin:0;color:#9d9a91;font-size:.7rem}
  .rf-close{display:grid;place-items:center;width:2rem;height:2rem;background:transparent;border:1px solid #41434a;color:#b8b2a6;border-radius:5px;cursor:pointer}
  .rf-tabs{display:flex;gap:.5rem;flex-wrap:wrap;padding:.65rem 1.25rem;background:#0c1016;border-bottom:1px solid #292d34}
  .rf-tabs button,.rf-secondary{padding:.42rem .75rem;background:#151a21;color:#a9a59b;border:1px solid #343a43;border-radius:5px;font-size:.7rem;font-weight:700;cursor:pointer}
  .rf-tabs button.active{background:rgba(190,157,93,.18);color:#f0dba9;border-color:#9b8051}
  .rf-body{flex:1 1 auto;min-height:0;overflow:auto;padding:1rem 1.25rem;display:flex;flex-direction:column;gap:.85rem}
  .rf-panel{padding:.85rem;background:#11161d;border:1px solid #2d333c;border-radius:8px}
  .rf-panel h4{margin:0 0 .65rem;color:#d7bd82;font-size:.74rem;text-transform:uppercase}
  .rf-panel h4 code{margin-left:.35rem;color:#99978f;font-size:.65rem;text-transform:none}
  .rf-muted{color:#9c9a93;font-size:.7rem}
  .rf-toolbar{display:flex;align-items:center;justify-content:space-between;gap:.7rem;margin-bottom:.55rem}
  .rf-toolbar h4{margin:0}
  .rf-table-wrap{max-height:340px;overflow:auto}
  .rf-table-wrap table{width:100%;border-collapse:collapse;font-size:.68rem}
  .rf-table-wrap th,.rf-table-wrap td{text-align:left;padding:.45rem;border-bottom:1px solid #2b3038}
  .rf-table-wrap th{color:#d6bd86}
  .rf-mono,.rf-table-wrap code{font-family:ui-monospace,monospace}
  .rf-actions,.rf-links,.rf-formats{display:flex;flex-wrap:wrap;gap:.4rem}
  .rf-action{padding:.25rem .45rem;color:#b9dce2;background:#14232a;border:1px solid #31515a;border-radius:4px;font-size:.6rem;cursor:pointer}
  .rf-action.danger{color:#f1aaaa;background:#29191b;border-color:#63383c}
  .rf-formats label{display:flex;align-items:center;gap:.35rem;padding:.3rem .5rem;border:1px solid #353a42;border-radius:5px;font-size:.66rem}
  .rf-formats label.unavailable{opacity:.55}
  .rf-formats small{color:#99978f}
  .rf-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.7rem;margin:.75rem 0}
  .rf-fields label{display:flex;flex-direction:column;gap:.3rem;color:#aaa69c;font-size:.68rem}
  .rf-fields input{padding:.55rem .65rem;color:#e8e5dc;background:#080b10;border:1px solid #3b414a;border-radius:5px}
  .rf-primary{padding:.55rem .9rem;color:#17140d;background:linear-gradient(135deg,#d5b779,#a8874e);border:0;border-radius:5px;font-size:.7rem;font-weight:800;cursor:pointer}
  .rf-primary:disabled,.rf-secondary:disabled{opacity:.55;cursor:wait}
  .rf-error{margin:.45rem 0;padding:.55rem .7rem;color:#ffc4c4;background:rgba(150,30,30,.16);border:1px solid rgba(220,80,80,.35);border-radius:5px;font-size:.7rem}
  .rf-success{margin-top:.65rem;padding:.65rem;color:#b8ebcf;background:rgba(16,100,65,.15);border:1px solid rgba(60,170,115,.35);border-radius:5px;font-size:.7rem}
  .rf-success div{margin-top:.3rem}
  .rf-report-list{display:flex;flex-direction:column;gap:.5rem;max-height:260px;overflow:auto}
  .rf-report{padding:.6rem;background:#0b1016;border:1px solid #303741;border-radius:5px}
  .rf-report-head{display:flex;justify-content:space-between;gap:.7rem;color:#e3ded2;font-size:.7rem}
  .rf-report-head span,.rf-report p{color:#9d9a91;font-size:.62rem}
  .rf-report p{margin:.35rem 0}
  .rf-links a{display:inline-flex;align-items:center;gap:.25rem;padding:.25rem .45rem;color:#a8dce5;border:1px solid #31515a;border-radius:4px;text-decoration:none;font-size:.62rem}
  .rf-foot{display:flex;justify-content:flex-end;padding:.75rem 1.25rem;border-top:1px solid #292d34}
  @media(max-width:680px){.rf-backdrop{padding:.35rem}.rf-card{width:100%;max-height:96vh}.rf-head,.rf-body{padding:.8rem}.rf-tabs{padding:.55rem .8rem}.rf-report-head{flex-direction:column}}
</style>
