<script lang="ts">
  import Icon from '../Icon.svelte';
  import { taskStatus } from '../../store';

  $: report = ($taskStatus as any)?.output_summary ?? null;
  $: verifications = Array.isArray(report?.verifications) ? report.verifications : [];
  $: canonicalChecks = Array.isArray(report?.canonical_observation_checks)
    ? report.canonical_observation_checks
    : [];
  $: jurors = Array.isArray(report?.jurors) ? report.jurors : [];
  $: dropped = Array.isArray(report?.dropped_juror) ? report.dropped_juror : [];
  $: consensus =
    report?.consensus && typeof report.consensus === 'object' ? report.consensus : null;
  $: accounting =
    report?.vote_accounting && typeof report.vote_accounting === 'object'
      ? report.vote_accounting
      : null;

  function pct(value: unknown): string {
    return typeof value === 'number' && Number.isFinite(value)
      ? `${Math.round(value * 100)}%`
      : 'ölçülmedi';
  }

  function statusLabel(raw: unknown): string {
    const val = String(raw || '').trim().toLowerCase();
    if (!val) return 'Bilinmiyor';
    if (val === 'verified' || val === 'passed' || val === 'ok' || val === 'confirmed') {
      return 'Doğrulandı';
    }
    if (val === 'rejected' || val === 'failed') return 'Reddedildi';
    if (val === 'inconclusive' || val === 'uncertain') return 'Belirsiz';
    return String(raw);
  }

  function pretty(value: unknown): string {
    if (value === null || value === undefined || value === '') return 'veri yok';
    if (typeof value === 'string') return value;
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
</script>

<section class="card jury-panel" aria-label="Bağımsız Jüri ve Uzlaşma">
  <div class="jury-head">
    <div>
      <p class="atelier-kicker">BAĞIMSIZ DOĞRULAMA</p>
      <h3><Icon name="scale" size={1.05} /> Jüri Koltukları &amp; Uzlaşma Özeti</h3>
      <p class="jury-sub">
        Aktif incelemede jüri üyelerinin verdiği oylar, elenen koltuklar ve kanıt kapısı denetimi burada görünür. Veri yoksa sonuç uydurulmaz.
      </p>
    </div>
    <span class="pill" class:pill-ok={Boolean(report)} class:pill-warn={!report}>
      {report ? 'Görev Verisi Var' : 'Veri Bekleniyor'}
    </span>
  </div>

  {#if !report}
    <div class="empty-state">
      <strong>Henüz jüri raporu yayınlanmadı.</strong>
      <p class="empty-sub">
        Ana Ekrandan bir analiz tamamlandığında doğrulama koltukları, oylar ve uzlaşma kuralları burada yer alır.
      </p>
    </div>
  {:else}
    <div class="summary-grid">
      <div class="metric-card">
        <span>Genel Hüküm</span>
        <strong>{statusLabel(report.status)}</strong>
      </div>
      <div class="metric-card">
        <span>Güven Oranı</span>
        <strong>{pct(report.confidence)}</strong>
      </div>
      <div class="metric-card">
        <span>Veri Yeterliliği</span>
        <strong>
          {typeof report.data_confidence === 'boolean'
            ? report.data_confidence
              ? 'Yeterli'
              : 'Yetersiz'
            : 'Belirsiz'}
        </strong>
      </div>
      <div class="metric-card">
        <span>Belirsiz İddia</span>
        <strong>{Number.isFinite(report.unknown_claims) ? report.unknown_claims : '—'}</strong>
      </div>
    </div>

    <div class="two-col">
      <div class="sub-box">
        <h4>Aktif Jüri Koltukları</h4>
        {#if jurors.length > 0}
          <div class="chip-row">
            {#each jurors as seat}
              <span class="pill pill-ok">{seat}</span>
            {/each}
          </div>
        {:else}
          <p class="muted-note">Aktif jüri koltuğu bildirilmedi.</p>
        {/if}

        <h4 class="spaced-title">Düşürülen / Katılmayan Koltuklar</h4>
        {#if dropped.length > 0}
          <div class="chip-row">
            {#each dropped as seat}
              <span class="pill pill-warn">{seat}</span>
            {/each}
          </div>
        {:else}
          <p class="muted-note">Düşürülen koltuk yok.</p>
        {/if}
      </div>

      <div class="sub-box">
        <h4>Bağımsız Uzlaşma Denetimi</h4>
        {#if consensus}
          <div class="kv-grid">
            <div><span>Denetlenen İddia:</span><strong>{consensus.claims_audited ?? '—'}</strong></div>
            <div><span>Uyuşmazlık:</span><strong>{consensus.mismatches ?? '—'}</strong></div>
            <div><span>Yeter Sayı Sağlanan:</span><strong>{consensus.quorum_met_claims ?? '—'}</strong></div>
            <div><span>Gerekli Koltuk:</span><strong>{consensus.quorum_required ?? '—'}</strong></div>
            <div><span>Ortalama Uzlaşma:</span><strong>{pct(consensus.mean_strength)}</strong></div>
            <div>
              <span>Bağlayıcı Kural:</span>
              <strong>
                {typeof consensus.binding === 'boolean'
                  ? consensus.binding
                    ? 'Açık'
                    : 'Kapalı'
                  : 'Belirsiz'}
              </strong>
            </div>
          </div>
          {#if consensus.machine_note}
            <p class="machine-note">{consensus.machine_note}</p>
          {/if}
        {:else}
          <p class="muted-note">Bu çalışmada bağımsız uzlaşma özeti bulunmuyor.</p>
        {/if}
      </div>
    </div>

    {#if report.decision_rule}
      <div class="sub-box">
        <h4>Karar Kuralı</h4>
        <p class="rule-txt">{report.decision_rule}</p>
      </div>
    {/if}

    {#if accounting && Object.keys(accounting).length > 0}
      <div class="sub-box">
        <h4>Oy Dağılımı</h4>
        <div class="chip-row">
          {#each Object.entries(accounting) as [key, val]}
            <span class="pill">{key}: <strong>{val}</strong></span>
          {/each}
        </div>
      </div>
    {/if}

    {#if verifications.length > 0}
      <div class="sub-box">
        <h4>İddia Bazlı Doğrulamalar ({verifications.length})</h4>
        <div class="verify-list">
          {#each verifications.slice(0, 12) as v}
            <div class="verify-item">
              <div class="verify-top">
                <strong>{v.claim || v.statement || 'İddia'}</strong>
                <span class="pill">{statusLabel(v.verdict || v.status)}</span>
              </div>
              {#if v.note || v.reason}
                <p class="muted-note">{v.note || v.reason}</p>
              {/if}
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if canonicalChecks.length > 0}
      <details class="sub-box fold">
        <summary>Ham Kanıt Kapısı Kontrolleri ({canonicalChecks.length})</summary>
        <pre class="json-pre">{pretty(canonicalChecks)}</pre>
      </details>
    {/if}
  {/if}
</section>

<style>
  .jury-panel {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .jury-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }

  .jury-head h3 {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 16px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .jury-sub {
    margin-top: 4px;
    font-size: 12.5px;
    color: var(--text-muted);
    max-width: 72ch;
  }

  .empty-sub {
    margin-top: 6px;
    font-size: 12px;
    color: var(--text-muted);
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(155px, 1fr));
    gap: 10px;
  }

  .metric-card {
    padding: 10px 12px;
    border-radius: 9px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .metric-card span {
    font-size: 11.5px;
    color: var(--text-muted);
  }

  .metric-card strong {
    font-size: 15px;
    color: var(--text-primary);
  }

  .two-col {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
    gap: 12px;
  }

  .sub-box {
    padding: 12px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .sub-box h4 {
    font-size: 13px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .spaced-title {
    margin-top: 6px;
  }

  .chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .muted-note,
  .machine-note,
  .rule-txt {
    font-size: 12px;
    color: var(--text-secondary);
    line-height: 1.45;
  }

  .kv-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 6px 10px;
    font-size: 12px;
  }

  .kv-grid div {
    display: flex;
    justify-content: space-between;
    gap: 6px;
    padding: 5px 8px;
    border-radius: 6px;
    background: var(--bg-input);
  }

  .kv-grid span {
    color: var(--text-muted);
  }

  .verify-list {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }

  .verify-item {
    padding: 8px 10px;
    border-radius: 8px;
    background: var(--bg-input);
    border: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .verify-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 12.5px;
  }

  .fold summary {
    cursor: pointer;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .json-pre {
    margin-top: 6px;
    padding: 10px;
    border-radius: 8px;
    background: var(--bg-input);
    border: 1px solid var(--border);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    max-height: 200px;
    overflow: auto;
    white-space: pre-wrap;
    color: var(--text-secondary);
  }
</style>
