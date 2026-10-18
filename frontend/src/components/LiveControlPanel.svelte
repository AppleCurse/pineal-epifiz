<script lang="ts">
  /**
   * CANLI KONTROL PANELİ — "hangi modül çalışıyor, nerede çalışıyor, sırada kim var,
   * kimi kazıyor, muhakemesi ne, toplanan bilgi ne, çağrı izi nerede".
   *
   * VERİ KAYNAKLARI (ikisi de MEVCUT SoT; paralel telemetri deposu YOK):
   *   1) WS `snapshot_update` → `$taskStatus`  → ajan koşuları, kuyruk,
   *      kanal durumu, hedef URL'leri (ANLIK).
   *   2) `GET /api/aspasia/state` → registry / run / budget / quota / anomalies
   *      / **calls** (gateway `call_log` → çağrı izi).
   *
   * DÜRÜSTLÜK KURALLARI (depo sözleşmesi):
   *   · Ölçüm yoksa "—" + SEBEP yazılır; asla "hazır/başarılı" denmez.
   *   · Sayı uydurulmaz: süre gerçek zaman damgalarından, maliyet çağrı
   *     kaydından gelir.
   *   · Boş bölüm "veri yok" diye SESSİZCE boş kalmaz; nedeni yazılır.
   */
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import { apiFetch, clientId, taskStatus, activeViewMode, isProcessing } from '../store';

  type RunEntry = {
    status?: string | null;
    confidence?: number | null;
    error_code?: string | null;
    error_message?: string | null;
    call_ids?: string[];
    input_summary?: Record<string, any>;
    evidence_ids?: string[];
    decision_grade?: boolean;
    responsibility?: Record<string, any> | null;
    warnings?: string[];
    output_summary?: Record<string, any>;
    provenance?: Record<string, any> | null;
    started_at?: string | null;
    completed_at?: string | null;
    model?: string | null;
    via?: string | null;
    run_source?: string | null;
  };

  type CallRow = {
    call_id?: string;
    agent_id?: string;
    bound_agents?: string[];
    model?: string;
    provider?: string;
    route_key?: string;
    fallback_reason?: string;
    chain_source?: string;
    quota_status?: string;
    error?: string;
    duration_ms?: number;
    cost_usd?: number;
    requested_model?: string;
    actual_model?: string;
  };

  type ChannelRow = {
    channel?: string;
    status?: string;
    reason?: string | null;
    detail?: string | null;
  };

  // Repo kanonik ölçüm-yok işareti (bkz. test_ui_honesty_contract.py).
  const INSUFFICIENT = 'YETERSİZ KANIT';

  let state: Record<string, any> = {};
  let stateError: string | null = null;
  let poller: ReturnType<typeof setInterval> | null = null;

  $: runs = ($taskStatus?.runs || {}) as Record<string, RunEntry>;
  $: planned = ($taskStatus?.planned_agents || []) as string[];
  $: currentAgent = ($taskStatus?.current_agent || null) as string | null;
  $: channels = ($taskStatus?.channel_status || []) as ChannelRow[];
  $: targetUrls = [
    ...(($taskStatus?.target_profile?.detected_urls || []) as string[]),
    ...(($taskStatus?.target_profile?.scanned_urls || []) as string[]),
  ];
  $: calls = (state.calls || []) as CallRow[];
  // [P6] Çağrı kimliği bağlayıcısı: `run.call_ids` (koşu) ↔ gateway call_log.
  $: callBinding = (state.call_binding || {}) as Record<string, any>;
  $: visibleCallIds = new Set(calls.map((c) => String(c.call_id || '')));
  $: registry = (state.registry || []) as string[];
  $: budget = (state.budget || {}) as Record<string, any>;
  $: anomalies = (state.anomalies || {}) as Record<string, any[]>;
  $: quota = (state.quota || {}) as Record<string, any>;

  /** Kuyruk + durum: planlanan her ajan için ANLIK gerçek durum. */
  $: agentLane = planned.map((name, index) => {
    const run = runs[name] as RunEntry | undefined;
    const status = run?.status || 'pending';
    return {
      name,
      queue: index,
      status,
      running: status === 'running',
      done: status === 'completed' || status === 'completed_no_decision',
      failed: status === 'failed' || status === 'halted' || status === 'timed_out'
        || status === 'unavailable',
      confidence: run?.confidence ?? null,
      decisionGrade: run?.decision_grade ?? null,
      evidenceCount: (run?.evidence_ids || []).length,
      callCount: (run?.call_ids || []).length,
      urls: (run?.input_summary?.urls || []) as string[],
      errorCode: run?.error_code || null,
      errorMessage: run?.error_message || null,
      warnings: run?.warnings || [],
      responsibility: (run?.responsibility || {}) as Record<string, any>,
      model: run?.model || null,
      via: run?.via || null,
      runSource: run?.run_source || null,
      startedAt: run?.started_at || null,
      completedAt: run?.completed_at || null,
    };
  });

  /** Planlanmamış ama koşmuş ajanlar (7-sütun/gölge/OSINT gibi kanallar). */
  $: extraRuns = Object.keys(runs)
    .filter((name) => !planned.includes(name))
    .map((name) => {
      const run = runs[name] as RunEntry;
      return {
        name,
        status: run.status || 'unknown',
        evidenceCount: (run.evidence_ids || []).length,
        callCount: (run.call_ids || []).length,
        model: run.model || null,
        via: run.via || null,
        startedAt: run.started_at || null,
        completedAt: run.completed_at || null,
      };
    });

  $: totalEvidence = Object.values(runs).reduce(
    (acc, run) => acc + ((run as RunEntry)?.evidence_ids || []).length,
    0,
  );

  function elapsedMs(start?: string | null, end?: string | null): number | null {
    if (!start) return null;
    const t0 = Date.parse(start);
    if (Number.isNaN(t0)) return null;
    const t1 = end ? Date.parse(end) : Date.now();
    if (Number.isNaN(t1)) return null;
    return Math.max(0, t1 - t0);
  }

  function fmtDuration(ms: number | null): string {
    if (ms === null) return INSUFFICIENT;
    if (ms < 1000) return `${ms} ms`;
    const s = ms / 1000;
    if (s < 60) return `${s.toFixed(1)} sn`;
    const m = Math.floor(s / 60);
    return `${m} dk ${Math.round(s - m * 60)} sn`;
  }

  /** Anomali sayacı — alan yoksa 0 DEĞİL, ölçülemiyor olarak işaretlenir. */
  function fallbacks(anomalies: Record<string, any[]>): string {
    if (!anomalies) return INSUFFICIENT;
    const fb = (anomalies.fallbacks || []).length;
    const sd = (anomalies.substitution_denials || []).length;
    const mm = (anomalies.model_mismatches || []).length;
    if (!fb && !sd && !mm) return '0 (düzensizlik yok)';
    return `fallback ${fb} · model-ikamesi-reddi ${sd} · model-uyumsuzluğu ${mm}`;
  }

  function fmtCost(value?: number | null): string {
    if (typeof value !== 'number') return INSUFFICIENT;
    return `$${value.toFixed(6)}`;
  }

  function statusLabel(run: { status: string; failed: boolean; done: boolean; running: boolean }): string {
    if (run.running) return 'ÇALIŞIYOR';
    if (run.done) return 'TAMAM';
    if (run.failed) return 'DURDU';
    if (run.status === 'pending') return 'SIRADA';
    return (run.status || 'bilinmiyor').toUpperCase();
  }

  async function refreshState(): Promise<void> {
    try {
      const res = await apiFetch(`/api/aspasia/state?client_id=${encodeURIComponent(get(clientId) || 'default')}`);
      if (!res.ok) {
        stateError = `HTTP ${res.status}`;
        return;
      }
      const data = await res.json();
      state = data || {};
      stateError = null;
    } catch (err: any) {
      stateError = err?.message || 'ağ hatası';
    }
  }

  onMount(() => {
    void refreshState();
    poller = setInterval(() => void refreshState(), 4000);
  });

  onDestroy(() => {
    if (poller) clearInterval(poller);
    poller = null;
  });
</script>

<section class="control-panel" aria-label="Canlı kontrol paneli">
  <header class="cp-head">
    <h2>LIVE CONTROL PANEL</h2>
    <div class="cp-head-right">
      <span class="cp-badge" title="Görev durumu (WS)">
        GÖREV: {$taskStatus?.status || (isProcessing ? 'RUNNING' : 'IDLE')}
      </span>
      <span class="cp-badge" title="Canlı ajan (WS)">
        CANLI AJAN: {currentAgent || '—'}
      </span>
      <span class="cp-badge" title="Çağrı kaydı (gateway call_log)">
        ÇAĞRI: {calls.length}
      </span>
      <button class="cp-btn" on:click={() => activeViewMode.set('warroom')}>MUHAREBE MASASI</button>
      <button class="cp-btn" on:click={() => activeViewMode.set('cockpit')}>KOKPİT</button>
    </div>
  </header>

  {#if stateError}
    <p class="cp-warn">
      DENETİM GÖRÜNÜMÜ ALINAMADI: {stateError} — çağrı izi ve bütçe satırları ölçülemiyor.
    </p>
  {/if}

  <div class="cp-grid">
    <!-- 1) AJAN HATTI: kuyruk + canlı ajan -->
    <section class="cp-card">
      <h3>1 · AJAN HATTI (kuyruk + anlık)</h3>
      {#if agentLane.length === 0}
        <p class="cp-empty">
          {INSUFFICIENT} — görev henüz rota çizmedi. Neden: WS'te <code>planned_agents</code> boş.
        </p>
      {:else}
        <ul class="cp-list">
          {#each agentLane as run (run.name)}
            <li class="cp-item" class:is-running={run.running} class:is-failed={run.failed}>
              <span class="cp-queue">#{run.queue + 1}</span>
              <span class="cp-name">{run.name}</span>
              <span class="cp-state">{statusLabel(run)}</span>
              <span class="cp-meta">
                süre {fmtDuration(elapsedMs(run.startedAt, run.completedAt))}
                · kanıt {run.evidenceCount}
                · çağrı {run.callCount}
              </span>
              {#if run.decisionGrade === false}
                <span class="cp-warn-inline" title="Ajan koştu ama karar üretmedi (data_confidence=False)">
                  KAR YOK
                </span>
              {/if}
              {#if run.errorCode || run.errorMessage}
                <span class="cp-warn-inline">{run.errorCode || 'hata'}: {run.errorMessage || ''}</span>
              {/if}
              {#each run.warnings as w (w)}
                <span class="cp-warn-inline">{w}</span>
              {/each}
            </li>
          {/each}
        </ul>
        {#if extraRuns.length > 0}
          <p class="cp-sub">
            ROTA DIŞI KANALLAR (yürütücü dışı):
            {#each extraRuns as extra (extra.name)}
              <span class="cp-chip">
                {extra.name} · {extra.status} · kanıt {extra.evidenceCount} · çağrı {extra.callCount}
              </span>
            {/each}
          </p>
        {/if}
      {/if}
    </section>

    <!-- 2) ANLIK KANAL: hangi modül nerede çalışıyor -->
    <section class="cp-card">
      <h3>2 · ANLIK KANAL (hangi modül nerede)</h3>
      {#if channels.length === 0}
        <p class="cp-empty">
          {INSUFFICIENT} — kanal kaydı yok. Neden: görev başlamadı ya da kanal üretmedi.
        </p>
      {:else}
        <ul class="cp-list">
          {#each channels as ch (ch.channel)}
            <li class="cp-item" class:is-failed={ch.status !== 'ok'}>
              <span class="cp-name">{ch.channel || 'kanal'}</span>
              <span class="cp-state">{ch.status || 'bilinmiyor'}</span>
              <span class="cp-meta">{ch.detail || ch.reason || 'açıklama yok'}</span>
            </li>
          {/each}
        </ul>
      {/if}
      <h4>NE KAZILIYOR (canlı ajanın girdisi)</h4>
      {#if currentAgent && runs[currentAgent]?.input_summary?.urls?.length}
        <ul class="cp-list">
          {#each (runs[currentAgent]?.input_summary?.urls || []) as url (url)}
            <li class="cp-item"><span class="cp-name">{url}</span></li>
          {/each}
        </ul>
      {:else}
        <p class="cp-empty">
          {INSUFFICIENT} — canlı ajanın URL girdisi yok
          {currentAgent ? `(ajan: ${currentAgent})` : '(canlı ajan yok)'}.
        </p>
      {/if}
      {#if targetUrls.length > 0}
        <p class="cp-sub">HEDEF URL'LERİ: {#each targetUrls as u (u)}<span class="cp-chip">{u}</span>{/each}</p>
      {/if}
    </section>

    <!-- 3) MUHAKEME: karar var mı, gerekçe ne -->
    <section class="cp-card">
      <h3>3 · MUHAKEME (karar + gerekçe)</h3>
      {#if currentAgent && runs[currentAgent]}
        {@const r = runs[currentAgent]}
        <ul class="cp-list">
          <li class="cp-item">
            <span class="cp-name">AJAN</span><span class="cp-state">{currentAgent}</span>
          </li>
          <li class="cp-item">
            <span class="cp-name">KARAR</span>
            <span class="cp-state">
              {r.decision_grade === false ? 'KAR YOK (ölçülemedi)' : (r.decision_grade ? 'VAR' : INSUFFICIENT)}
            </span>
            <span class="cp-meta">
              güven {typeof r.confidence === 'number' ? `${(r.confidence * 100).toFixed(1)}%` : INSUFFICIENT}
            </span>
          </li>
          <li class="cp-item">
            <span class="cp-name">MODEL</span>
            <span class="cp-state">{r.model || (r.run_source === 'deterministic' ? 'deterministik motor' : INSUFFICIENT)}</span>
            <span class="cp-meta">kaynak: {r.run_source || INSUFFICIENT} · via: {r.via || INSUFFICIENT}</span>
          </li>
          {#if r.responsibility && Object.keys(r.responsibility).length > 0}
            <li class="cp-item">
              <span class="cp-name">SORUMLULUK</span>
              <span class="cp-meta">
                attempted: {JSON.stringify(r.responsibility.attempted ?? null)} ·
                blockers: {JSON.stringify(r.responsibility.blockers ?? null)} ·
                next: {JSON.stringify(r.responsibility.next_action ?? r.responsibility.next ?? null)}
              </span>
            </li>
          {/if}
          {#if (r.call_ids || []).length > 0}
            <li class="cp-item">
              <span class="cp-name">ÇAĞRI KİMLİĞİ</span>
              <span class="cp-meta mono">
                {#each (r.call_ids || []) as cid (cid)}
                  <span class="cp-chip">
                    {cid}{visibleCallIds.has(String(cid)) ? '' : ' · İZ PENCERESİ DIŞINDA'}
                  </span>
                {/each}
              </span>
            </li>
          {/if}
        </ul>
      {:else}
        <p class="cp-empty">
          {INSUFFICIENT} — canlı ajan çalışmıyor. Neden: {currentAgent ? 'kayıt yok' : 'görev yok/idle'}.
        </p>
      {/if}
    </section>

    <!-- 4) KANIT AKIŞI: toplanan bilgi -->
    <section class="cp-card">
      <h3>4 · TOPLANAN BİLGİ (kanıt akışı)</h3>
      <p class="cp-sub">TOPLAM KANIT: {totalEvidence} · KANAL: {channels.length}</p>
      {#if totalEvidence === 0}
        <p class="cp-empty">
          {INSUFFICIENT} — kanıt kaydı yok. Neden: henüz kanıt üretilmemiş (dosya:satır:
          <code>agent_runs[*].evidence_ids</code> boş).
        </p>
      {:else}
        <ul class="cp-list">
          {#each agentLane.filter((a) => a.evidenceCount > 0) as run (run.name)}
            <li class="cp-item">
              <span class="cp-name">{run.name}</span>
              <span class="cp-meta">{run.evidenceCount} kanıt</span>
            </li>
          {/each}
        </ul>
      {/if}
      <h4>KANAL YAPISI (hangi modül ne üretti)</h4>
      {#if channels.length === 0}
        <p class="cp-empty">{INSUFFICIENT} — kanal satırı yok.</p>
      {:else}
        <ul class="cp-list">
          {#each channels.filter((c) => c.status === 'ok') as ch (ch.channel)}
            <li class="cp-item"><span class="cp-name">{ch.channel}</span><span class="cp-meta">{ch.detail || '—'}</span></li>
          {/each}
        </ul>
      {/if}
    </section>

    <!-- 5) ÇAĞRI İZİ: call_id → model → süre → maliyet -->
    <section class="cp-card cp-wide">
      <h3>5 · ÇAĞRI İZİ (call_id → model → süre → maliyet)</h3>
      <p class="cp-sub">
        BÜTÇE: harcanan {fmtCost(budget.spend_usd)} / tavan {fmtCost(budget.cap_usd)} ·
        KOTA: {Object.keys(quota).length ? Object.entries(quota).map(([k, v]) => `${k}: ${(v as any)?.status ?? INSUFFICIENT}`).join(' · ') : INSUFFICIENT}
        · ANOMALİ: {fallbacks(anomalies)}
      </p>
      <p class="cp-sub">
        İZLENEBİLİRLİK (çağrı kimliği bağı):
        koşu çağrısı {callBinding.run_call_count ?? INSUFFICIENT} ·
        bağlı {callBinding.bound_call_count ?? INSUFFICIENT} ·
        pencere dışı {Array.isArray(callBinding.missing_call_ids) ? callBinding.missing_call_ids.length : INSUFFICIENT}
        {#if callBinding.missing_reason}· sebep: {callBinding.missing_reason}{/if}
      </p>
      {#if calls.length === 0}
        <p class="cp-empty">
          {INSUFFICIENT} — çağrı kaydı yok. Neden: gateway <code>call_log</code> boş (LLM çağrısı yapılmadı).
        </p>
      {:else}
        <table class="cp-table">
          <thead>
            <tr>
              <th>CALL_ID</th><th>AJAN</th><th>KOŞUYA BAĞLI</th><th>MODEL</th><th>SAĞLAYICI</th>
              <th>SÜRE</th><th>MALİYET</th><th>NOT</th>
            </tr>
          </thead>
          <tbody>
            {#each calls.slice().reverse() as call, i (call.call_id || i)}
              <tr>
                <td class="mono">{call.call_id || '—'}</td>
                <td>{call.agent_id || '—'}</td>
                <td>
                  {#if (call.bound_agents || []).length > 0}
                    {(call.bound_agents || []).join(' · ')}
                  {:else}
                    <span class="cp-warn-inline">koşuya bağlı değil</span>
                  {/if}
                </td>
                <td>{call.model || call.requested_model || INSUFFICIENT}</td>
                <td>{call.provider || INSUFFICIENT}</td>
                <td>{typeof call.duration_ms === 'number' ? `${call.duration_ms} ms` : INSUFFICIENT}</td>
                <td>{fmtCost(call.cost_usd)}</td>
                <td class="cp-warn-inline">
                  {call.fallback_reason ? `fallback: ${call.fallback_reason}` : ''}
                  {call.error ? ` hata: ${String(call.error).slice(0, 60)}` : ''}
                  {call.quota_status ? ` kota: ${call.quota_status}` : ''}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
      <p class="cp-sub">KAYITLI AJANLAR ({registry.length}): {registry.join(', ') || '—'}</p>
    </section>
  </div>
</section>

<style>
  .control-panel {
    position: fixed;
    inset: 0;
    overflow-y: auto;
    background: var(--bg-main, #020101);
    color: var(--text-phosphor, #38ef7d);
    font-family: 'JetBrains Mono', 'Courier New', monospace;
    padding: 18px 20px 40px;
    box-sizing: border-box;
  }
  .cp-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    border-bottom: 1px solid rgba(212, 175, 55, 0.35);
    padding-bottom: 10px;
    margin-bottom: 14px;
    flex-wrap: wrap;
  }
  .cp-head h2 { margin: 0; font-size: 18px; letter-spacing: 2px; color: var(--gold, #d4af37); }
  .cp-head-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .cp-badge {
    border: 1px solid rgba(212, 175, 55, 0.4);
    padding: 3px 8px;
    font-size: 11px;
    letter-spacing: 1px;
  }
  .cp-btn {
    background: transparent;
    border: 1px solid var(--gold, #d4af37);
    color: var(--gold, #d4af37);
    font-family: inherit;
    font-size: 11px;
    letter-spacing: 1px;
    padding: 4px 10px;
    cursor: pointer;
  }
  .cp-btn:hover { background: rgba(212, 175, 55, 0.15); }
  .cp-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
    gap: 14px;
  }
  .cp-card {
    border: 1px solid rgba(56, 239, 125, 0.25);
    background: rgba(2, 6, 3, 0.72);
    padding: 12px 14px;
  }
  .cp-wide { grid-column: 1 / -1; }
  .cp-card h3 {
    margin: 0 0 10px;
    font-size: 13px;
    letter-spacing: 1.5px;
    color: var(--gold, #d4af37);
  }
  .cp-card h4 { margin: 12px 0 6px; font-size: 11px; letter-spacing: 1px; opacity: 0.8; }
  .cp-list { list-style: none; margin: 0; padding: 0; }
  .cp-item {
    border-left: 2px solid rgba(56, 239, 125, 0.35);
    padding: 4px 8px;
    margin-bottom: 4px;
    font-size: 12px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: baseline;
  }
  .cp-item.is-running { border-left-color: var(--gold, #d4af37); background: rgba(212, 175, 55, 0.08); }
  .cp-item.is-failed { border-left-color: var(--accent-red, #ef4444); }
  .cp-queue { color: var(--gold, #d4af37); }
  .cp-name { color: var(--text-phosphor, #38ef7d); }
  .cp-state { color: var(--gold, #d4af37); letter-spacing: 1px; font-size: 11px; }
  .cp-meta { opacity: 0.75; font-size: 11px; }
  .cp-empty { color: #fbbf24; font-size: 11px; line-height: 1.5; margin: 4px 0; }
  .cp-warn { color: var(--accent-red, #ef4444); font-size: 12px; }
  .cp-warn-inline { color: #fbbf24; font-size: 11px; }
  .cp-sub { font-size: 11px; opacity: 0.75; line-height: 1.6; }
  .cp-chip {
    display: inline-block;
    border: 1px solid rgba(56, 239, 125, 0.3);
    padding: 1px 6px;
    margin: 2px 4px 2px 0;
    font-size: 10px;
  }
  .cp-table { width: 100%; border-collapse: collapse; font-size: 11px; }
  .cp-table th, .cp-table td {
    border: 1px solid rgba(56, 239, 125, 0.2);
    padding: 3px 6px;
    text-align: left;
  }
  .cp-table th { color: var(--gold, #d4af37); font-weight: 400; letter-spacing: 1px; }
  .mono { font-family: 'JetBrains Mono', 'Courier New', monospace; }
</style>
