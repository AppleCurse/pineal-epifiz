<script lang="ts">
  /**
   * CANLI KONTROL PANELİ — "hangi modül çalışıyor, nerede çalışıyor, sırada kim var,
   * kimi kazıyor, muhakemesi ne, toplanan bilgi ne, çağrı izi nerede".
   *
   * VERİ KAYNAKLARI (ikisi de MEVCUT SoT; paralel telemetri deposu YOK):
   *   1) WS `snapshot_update` → `$taskStatus`  → ajan koşuları, kuyruk,
   *      kanal durumu, hedef URL'leri, ajan çıktıları (ANLIK).
   *      WS `result` → `$taskStatus.evidence_chain` → kanıt zinciri (görev sonu).
   *   2) `GET /api/aspasia/state` → registry / run / budget / quota / anomalies
   *      / **calls** (gateway `call_log` → çağrı izi, sayfalı).
   *
   * DÜRÜSTLÜK KURALLARI (depo sözleşmesi):
   *   · Ölçüm yoksa "YETERSİZ KANIT" + SEBEP yazılır; asla "hazır/başarılı" denmez.
   *   · Sayı uydurulmaz: süre gerçek zaman damgalarından, maliyet çağrı
   *     kaydından gelir.
   *   · Boş bölüm "veri yok" diye SESSİZCE boş kalmaz; nedeni yazılır.
   *   · Uzun metin kırpılır ama kırpıldığı SAYILIR ("… +N karakter").
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

  /** Görev sonu kanıt zinciri satırı (result payload → `evidence_chain`). */
  type EvidenceRow = {
    agent?: string;
    evidence_type?: string;
    provenance?: any;
    result?: any;
    timestamp?: string;
  };

  // Repo kanonik ölçüm-yok işareti (bkz. test_ui_honesty_contract.py).
  const INSUFFICIENT = 'YETERSİZ KANIT';
  /** Uzun metin kırpma sınırı (kırpıldığı sayıyla birlikte yazılır). */
  const TEXT_LIMIT = 320;
  /** Bir sayfada gösterilen çağrı sayısı. */
  const CALL_PAGE = 40;

  let state: Record<string, any> = {};
  let stateError: string | null = null;
  let poller: ReturnType<typeof setInterval> | null = null;

  // [P8-C] Seçim + filtre durumu (panel deneyimi).
  let selectedAgent: string | null = null;
  let filterText = '';
  let statusFilter: 'all' | 'running' | 'done' | 'failed' | 'queued' = 'all';
  // [P8-D] Çağrı izi sayfalama (0 = en yeniler).
  let callOffset = 0;

  $: runs = ($taskStatus?.runs || {}) as Record<string, RunEntry>;
  $: planned = ($taskStatus?.planned_agents || []) as string[];
  $: currentAgent = ($taskStatus?.current_agent || null) as string | null;
  $: channels = ($taskStatus?.channel_status || []) as ChannelRow[];
  $: evidenceChain = ($taskStatus?.evidence_chain || []) as EvidenceRow[];
  $: targetUrls = [
    ...(($taskStatus?.target_profile?.detected_urls || []) as string[]),
    ...(($taskStatus?.target_profile?.scanned_urls || []) as string[]),
  ];
  $: calls = (state.calls || []) as CallRow[];
  $: registry = (state.registry || []) as string[];
  $: budget = (state.budget || {}) as Record<string, any>;
  $: anomalies = (state.anomalies || {}) as Record<string, any[]>;
  $: quota = (state.quota || {}) as Record<string, any>;
  // [P6] Çağrı kimliği bağlayıcısı: `run.call_ids` (koşu) ↔ gateway call_log.
  $: callBinding = (state.call_binding || {}) as Record<string, any>;
  $: callWindow = (state.call_window || {}) as Record<string, any>;
  $: visibleCallIds = new Set(calls.map((c) => String(c.call_id || '')));
  $: logTotal = Number(callWindow.total ?? callBinding.log_total ?? calls.length);

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

  /** [P8-C] Filtre uygulanmış ajan hattı (metin + durum). */
  $: filteredLane = agentLane.filter((run) => {
    if (statusFilter === 'running' && !run.running) return false;
    if (statusFilter === 'done' && !run.done) return false;
    if (statusFilter === 'failed' && !run.failed) return false;
    if (statusFilter === 'queued' && !(run.status === 'pending')) return false;
    const needle = filterText.trim().toLowerCase();
    if (!needle) return true;
    const haystack = [
      run.name,
      run.model || '',
      run.via || '',
      run.runSource || '',
      run.errorCode || '',
      ...run.urls,
      ...run.warnings
    ].join(' ').toLowerCase();
    return haystack.includes(needle);
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
    0
  );

  /** [P8] Seçili ajan: varsayılan CANLI ajan, yoksa kuyruğun ilki koşanı. */
  $: activeAgent = selectedAgent || currentAgent || (agentLane[0]?.name ?? null);
  $: activeRun = activeAgent ? (runs[activeAgent] as RunEntry | undefined) : undefined;
  /** [P8] Sıradaki ajan: canlı ajanın hemen ardından gelen plan ajanı. */
  $: nextAgent = (() => {
    const idx = currentAgent ? planned.indexOf(currentAgent) : -1;
    if (idx < 0) return planned[0] || null;
    return planned[idx + 1] || null;
  })();
  /** [P8-A] Kanıt zinciri ajan bazında gruplanır (toplanma yapısı). */
  $: evidenceByAgent = evidenceChain.reduce((acc: Record<string, EvidenceRow[]>, row) => {
    const key = row?.agent || 'bilinmiyor';
    acc[key] = acc[key] || [];
    acc[key].push(row);
    return acc;
  }, {} as Record<string, EvidenceRow[]>);

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

  /** [P8-A] Metni kırp; kırpıldığı miktarı YAZ (sessiz kesme yok). */
  function truncate(text: string, limit: number = TEXT_LIMIT): string {
    if (text.length <= limit) return text;
    return `${text.slice(0, limit)}… (+${text.length - limit} karakter)`;
  }

  /** [P8-A] Her türlü çıktıyı insan-okunur tek satıra çevirir. */
  function humanize(value: any, limit: number = TEXT_LIMIT): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'string') return truncate(value, limit);
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    if (Array.isArray(value)) {
      if (value.length === 0) return '[] (boş liste)';
      const head = value.slice(0, 3).map((item) => humanize(item, 120)).join(' · ');
      return truncate(`${value.length} öğe: ${head}`, limit);
    }
    if (typeof value === 'object') {
      const keys = Object.keys(value);
      if (keys.length === 0) return '{} (boş)';
      const head = keys.slice(0, 4)
        .map((k) => `${k}: ${humanize(value[k], 120)}`)
        .join(' · ');
      return truncate(`${keys.length} alan — ${head}`, limit);
    }
    return truncate(String(value), limit);
  }

  /** [P8-A] Bir ajanın çıktısını satır satır (anahtar → değer) listeler. */
  function outputRows(summary?: Record<string, any> | null): { key: string; value: string }[] {
    const src = summary || {};
    return Object.keys(src)
      .filter((k) => k !== '_provenance')
      .sort()
      .map((k) => ({ key: k, value: humanize(src[k]) }));
  }

  function hasEvidenceFor(name?: string | null): number {
    if (!name) return 0;
    return (evidenceByAgent[name] || []).length;
  }

  async function refreshState(): Promise<void> {
    try {
      const url = `/api/aspasia/state?client_id=${encodeURIComponent(get(clientId) || 'default')}`
        + `&offset=${callOffset}&limit=${CALL_PAGE}`;
      const res = await apiFetch(url);
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

  /** [P8-D] Çağrı izinde sayfalar (pencere kaydırılır; kayıt uydurulmaz). */
  async function pageCalls(delta: number): Promise<void> {
    callOffset = Math.max(0, callOffset + delta);
    await refreshState();
  }

  function selectAgent(name: string): void {
    selectedAgent = selectedAgent === name ? null : name;
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
      <span class="cp-badge" title="Çağrı izi (gateway call_log)">
        ÇAĞRI: {calls.length}/{logTotal}
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

  <!-- [P8-C] Filtre çubuğu -->
  <div class="cp-toolbar">
    <input
      class="cp-input"
      type="search"
      placeholder="AJAN / MODEL / URL / UYARI ara…"
      bind:value={filterText}
      aria-label="Ajan filtrele"
    />
    <select class="cp-input" bind:value={statusFilter} aria-label="Durum filtrele">
      <option value="all">TÜMÜ</option>
      <option value="running">ÇALIŞIYOR</option>
      <option value="queued">SIRADA</option>
      <option value="done">TAMAM</option>
      <option value="failed">DURDU</option>
    </select>
    <span class="cp-sub">
      {filteredLane.length}/{agentLane.length} ajan gösteriliyor
      {#if filterText.trim()}· filtre: “{truncate(filterText, 40)}”{/if}
    </span>
    {#if filterText.trim() || statusFilter !== 'all'}
      <button class="cp-btn" on:click={() => { filterText = ''; statusFilter = 'all'; }}>TEMİZLE</button>
    {/if}
  </div>

  <div class="cp-grid">
    <!-- 1) AJAN HATTI: kuyruk + canlı ajan -->
    <section class="cp-card">
      <h3>1 · AJAN HATTI (kuyruk + anlık)</h3>
      {#if agentLane.length === 0}
        <p class="cp-empty">
          {INSUFFICIENT} — görev henüz rota çizmedi. Neden: WS'te <code>planned_agents</code> boş.
        </p>
      {:else if filteredLane.length === 0}
        <p class="cp-empty">
          {INSUFFICIENT} — filtreye uyan ajan yok. Neden: “{truncate(filterText, 40)}” + durum
          “{statusFilter}” filtresi {agentLane.length} ajanın hiçbirine uymuyor.
        </p>
      {:else}
        <ul class="cp-list">
          {#each filteredLane as run (run.name)}
            <li
              class="cp-item cp-clickable"
              class:is-running={run.running}
              class:is-failed={run.failed}
              class:is-selected={activeAgent === run.name}
            >
              <button
                class="cp-agentbtn"
                on:click={() => selectAgent(run.name)}
                title="Ajan detayını aç"
              >
                <span class="cp-queue">#{run.queue + 1}</span>
                <span class="cp-name">{run.name}</span>
                <span class="cp-state">{statusLabel(run)}</span>
              </button>
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
      <h4>SIRADAKİ AJAN</h4>
      <p class="cp-sub">
        {#if nextAgent}
          <span class="cp-chip">{nextAgent}</span>
          {#if currentAgent}
            (canlı ajan: {currentAgent} → sıradaki: {nextAgent})
          {/if}
        {:else}
          {INSUFFICIENT} — sırada ajan yok. Neden: rota tamamlandı veya plan boş.
        {/if}
      </p>
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

    <!-- 3) MUHAKEME: karar var mı, gerekçe ne, çıktı ne -->
    <section class="cp-card">
      <h3>3 · MUHAKEME (karar + gerekçe + çıktı)</h3>
      {#if activeAgent && activeRun}
        {@const r = activeRun}
        <ul class="cp-list">
          <li class="cp-item">
            <span class="cp-name">AJAN</span>
            <span class="cp-state">{activeAgent}</span>
            {#if activeAgent !== currentAgent}
              <span class="cp-meta">(seçili ajan; canlı ajan: {currentAgent || '—'})</span>
            {/if}
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
        <h4>ÇIKTI (output_summary)</h4>
        {#if outputRows(r.output_summary).length === 0}
          <p class="cp-empty">
            {INSUFFICIENT} — ajan çıktı üretmedi. Neden: <code>output_summary</code> boş
            (ajan koşmadı ya da karar üretmedi).
          </p>
        {:else}
          <ul class="cp-list cp-kv">
            {#each outputRows(r.output_summary) as row (row.key)}
              <li class="cp-item">
                <span class="cp-name mono">{row.key}</span>
                <span class="cp-meta">{row.value}</span>
              </li>
            {/each}
          </ul>
        {/if}
      {:else}
        <p class="cp-empty">
          {INSUFFICIENT} — canlı ajan çalışmıyor. Neden: {currentAgent ? 'kayıt yok' : 'görev yok/idle'}.
        </p>
      {/if}
    </section>

    <!-- 4) TOPLANAN BİLGİ: kanıt akışı + zincir -->
    <section class="cp-card">
      <h3>4 · TOPLANAN BİLGİ (kanıt akışı)</h3>
      <p class="cp-sub">
        TOPLAM KANIT KİMLİĞİ: {totalEvidence} · KANAL: {channels.length} ·
        ZİNCİR SATIRI: {evidenceChain.length}
      </p>
      {#if totalEvidence === 0 && evidenceChain.length === 0}
        <p class="cp-empty">
          {INSUFFICIENT} — kanıt kaydı yok. Neden: henüz kanıt üretilmemiş
          (<code>agent_runs[*].evidence_ids</code> boş) ve kanıt zinciri görev
          bitince gelir.
        </p>
      {:else}
        <ul class="cp-list">
          {#each agentLane.filter((a) => a.evidenceCount > 0) as run (run.name)}
            <li class="cp-item">
              <span class="cp-name">{run.name}</span>
              <span class="cp-meta">{run.evidenceCount} kanıt</span>
              {#if hasEvidenceFor(run.name) > 0}
                <span class="cp-chip">zincir: {hasEvidenceFor(run.name)} satır</span>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
      <h4>KANIT ZİNCİRİ (görev sonu — ajan → kanıt)</h4>
      {#if evidenceChain.length === 0}
        <p class="cp-empty">
          {INSUFFICIENT} — kanıt zinciri yok. Neden: görev sonucu yayınlanmadı
          ya da zincir boş döndü.
        </p>
      {:else}
        {#each Object.keys(evidenceByAgent) as agentName (agentName)}
          <p class="cp-sub">AJAN: {agentName}</p>
          <ul class="cp-list">
            {#each evidenceByAgent[agentName] as row, i (agentName + '-' + i)}
              <li class="cp-item">
                <details>
                  <summary>
                    <span class="cp-name">{row.evidence_type || 'kanıt'}</span>
                    <span class="cp-meta">
                      {row.timestamp || 'zaman damgası yok'} · {humanize(row.result, 120)}
                    </span>
                  </summary>
                  <pre class="cp-pre">{humanize(row.result, 2000)}</pre>
                  {#if row.provenance}
                    <p class="cp-sub">PROVENANCE: {humanize(row.provenance, 400)}</p>
                  {/if}
                </details>
              </li>
            {/each}
          </ul>
        {/each}
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

    <!-- 5) ÇAĞRI İZİ: call_id → model → süre → maliyet (sayfalı) -->
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
        günlükte yok {Array.isArray(callBinding.missing_call_ids) ? callBinding.missing_call_ids.length : INSUFFICIENT}
        {#if callBinding.missing_reason}· sebep: {callBinding.missing_reason}{/if}
        · bu sayfada {callBinding.page_call_count ?? calls.length}
        {#if Array.isArray(callBinding.page_missing_call_ids) && callBinding.page_missing_call_ids.length > 0}
          · başka sayfada {callBinding.page_missing_call_ids.length}
        {/if}
        · günlük toplamı {logTotal}
      </p>
      <div class="cp-pager">
        <button class="cp-btn" on:click={() => pageCalls(CALL_PAGE)} disabled={callOffset === 0}>
          ← DAHA ESKİ
        </button>
        <span class="cp-sub">
          sayfa: {calls.length ? calls.length : 0} kayıt
          {#if callOffset > 0}· {callOffset} kayıt atl{/if}
        </span>
        <button class="cp-btn" on:click={() => pageCalls(-CALL_PAGE)} disabled={callOffset === 0}>
          DAHA YENİ →
        </button>
        {#if callOffset > 0}
          <button class="cp-btn" on:click={() => { callOffset = 0; void refreshState(); }}>
            CANLIYA DÖN
          </button>
        {/if}
      </div>
      {#if calls.length === 0}
        <p class="cp-empty">
          {INSUFFICIENT} — çağrı kaydı yok. Neden: gateway <code>call_log</code> boş (LLM çağrısı yapılmadı)
          {callOffset > 0 ? ` veya ${callOffset} kayıt geride` : ''}.
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

    <!-- 6) AJAN DETAYI (seçili ajanın tam dökümü) -->
    <section class="cp-card cp-wide">
      <h3>6 · AJAN DETAYI (seçili ajan)</h3>
      {#if !activeAgent}
        <p class="cp-empty">
          {INSUFFICIENT} — seçili ajan yok. Neden: görev yok/idle ya da ajan hattı boş.
        </p>
      {:else if !activeRun}
        <p class="cp-empty">
          {INSUFFICIENT} — “{activeAgent}” için koşu kaydı yok. Neden: ajan henüz
          başlamadı (kuyrukta) ya da kayıt bu görevde üretilmedi.
        </p>
      {:else}
        {@const d = activeRun}
        <ul class="cp-list cp-kv">
          <li class="cp-item">
            <span class="cp-name">AJAN</span>
            <span class="cp-meta">{activeAgent} · durum {d.status || 'bilinmiyor'}</span>
          </li>
          <li class="cp-item">
            <span class="cp-name">SÜRE</span>
            <span class="cp-meta">
              {fmtDuration(elapsedMs(d.started_at, d.completed_at))}
              · başlangıç {d.started_at || '—'} · bitiş {d.completed_at || '—'}
            </span>
          </li>
          <li class="cp-item">
            <span class="cp-name">GİRDİ</span>
            <span class="cp-meta">{humanize(d.input_summary, 400)}</span>
          </li>
          <li class="cp-item">
            <span class="cp-name">KANIT KİMLİKLERİ</span>
            <span class="cp-meta mono">
              {#if (d.evidence_ids || []).length > 0}
                {(d.evidence_ids || []).join(' · ')}
              {:else}
                {INSUFFICIENT} — kanıt kimliği yok
              {/if}
            </span>
          </li>
          <li class="cp-item">
            <span class="cp-name">ÇAĞRI KİMLİKLERİ</span>
            <span class="cp-meta mono">
              {#if (d.call_ids || []).length > 0}
                {(d.call_ids || []).join(' · ')}
              {:else}
                {INSUFFICIENT} — çağrı kimliği yok
              {/if}
            </span>
          </li>
          <li class="cp-item">
            <span class="cp-name">SORUMLULUK</span>
            <span class="cp-meta">{humanize(d.responsibility, 600)}</span>
          </li>
          <li class="cp-item">
            <span class="cp-name">UYARILAR</span>
            <span class="cp-meta">
              {#if (d.warnings || []).length > 0}
                {(d.warnings || []).join(' · ')}
              {:else}
                {INSUFFICIENT} — uyarı yok
              {/if}
            </span>
          </li>
          <li class="cp-item">
            <span class="cp-name">HATA</span>
            <span class="cp-meta">
              {d.error_code || d.error_message || 'yok'}
            </span>
          </li>
        </ul>
      {/if}
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
    font-size: 10px;
    letter-spacing: 1px;
    padding: 3px 8px;
    cursor: pointer;
  }
  .cp-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .cp-toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }
  .cp-input {
    background: rgba(0, 0, 0, 0.5);
    border: 1px solid rgba(212, 175, 55, 0.4);
    color: var(--text-phosphor, #38ef7d);
    font-family: inherit;
    font-size: 11px;
    padding: 4px 6px;
  }
  .cp-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
    gap: 14px;
  }
  .cp-card {
    border: 1px solid rgba(212, 175, 55, 0.28);
    background: rgba(0, 0, 0, 0.35);
    padding: 12px;
  }
  .cp-wide { grid-column: 1 / -1; }
  .cp-card h3 {
    margin: 0 0 10px;
    font-size: 13px;
    letter-spacing: 1.5px;
    color: var(--gold, #d4af37);
  }
  .cp-card h4 {
    margin: 12px 0 6px;
    font-size: 11px;
    letter-spacing: 1px;
    color: rgba(212, 175, 55, 0.85);
  }
  .cp-list { list-style: none; margin: 0; padding: 0; }
  .cp-item {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
    border-bottom: 1px dashed rgba(212, 175, 55, 0.14);
    padding: 4px 0;
  }
  .cp-kv .cp-item { align-items: flex-start; }
  .cp-clickable:hover { background: rgba(212, 175, 55, 0.06); }
  .cp-item.is-running { color: #ffe27a; }
  .cp-item.is-failed { color: #ff8f6b; }
  .cp-item.is-selected { background: rgba(212, 175, 55, 0.12); }
  .cp-agentbtn {
    background: none;
    border: none;
    color: inherit;
    font-family: inherit;
    font-size: inherit;
    display: inline-flex;
    gap: 8px;
    align-items: baseline;
    cursor: pointer;
    padding: 0;
  }
  .cp-queue { color: var(--gold, #d4af37); font-size: 11px; }
  .cp-name { color: var(--gold, #d4af37); font-size: 12px; }
  .cp-state { font-size: 11px; letter-spacing: 1px; }
  .cp-meta { font-size: 11px; opacity: 0.85; }
  .cp-sub { font-size: 11px; opacity: 0.8; margin: 6px 0; }
  .cp-empty {
    font-size: 11px;
    opacity: 0.85;
    border-left: 2px solid rgba(212, 175, 55, 0.5);
    padding-left: 8px;
  }
  .cp-warn { color: #ff8f6b; font-size: 12px; }
  .cp-warn-inline { color: #ff8f6b; font-size: 10px; }
  .cp-chip {
    display: inline-block;
    border: 1px solid rgba(212, 175, 55, 0.35);
    padding: 1px 5px;
    margin: 1px 3px 1px 0;
    font-size: 10px;
  }
  .cp-table { width: 100%; border-collapse: collapse; font-size: 11px; }
  .cp-table th, .cp-table td {
    border: 1px solid rgba(212, 175, 55, 0.18);
    padding: 3px 5px;
    text-align: left;
    vertical-align: top;
  }
  .cp-table th { color: var(--gold, #d4af37); font-weight: normal; }
  .cp-pager { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
  .cp-pre {
    white-space: pre-wrap;
    word-break: break-word;
    font-size: 10px;
    border: 1px solid rgba(212, 175, 55, 0.2);
    padding: 6px;
    margin: 4px 0;
  }
  .mono { font-family: 'JetBrains Mono', 'Courier New', monospace; }
  details summary { cursor: pointer; display: flex; gap: 8px; flex-wrap: wrap; align-items: baseline; }
</style>
