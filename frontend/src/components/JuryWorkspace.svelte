<script lang="ts">
  import { taskStatus } from '../store';

  $: report = ($taskStatus as any)?.output_summary ?? null;
  $: verifications = Array.isArray(report?.verifications) ? report.verifications : [];
  $: canonicalChecks = Array.isArray(report?.canonical_observation_checks) ? report.canonical_observation_checks : [];
  $: jurors = Array.isArray(report?.jurors) ? report.jurors : [];
  $: dropped = Array.isArray(report?.dropped_juror) ? report.dropped_juror : [];
  $: consensus = report?.consensus && typeof report.consensus === 'object' ? report.consensus : null;
  $: accounting = report?.vote_accounting && typeof report.vote_accounting === 'object' ? report.vote_accounting : null;

  function pct(value: unknown): string {
    return typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value * 100)}%` : 'ölçülmedi';
  }

  function pretty(value: unknown): string {
    if (value === null || value === undefined || value === '') return 'veri yok';
    if (typeof value === 'string') return value;
    try { return JSON.stringify(value, null, 2); } catch { return String(value); }
  }
</script>

<section id="jury" class="jury-workspace">
  <header class="jury-head">
    <div>
      <p class="eyebrow">INDEPENDENT VERIFICATION</p>
      <h2>Bağımsız Jüri &amp; Konsensüs</h2>
      <p>Panelin oyları, bağımsız yeniden sayım ve kanıt kapısı kayıtları. Yalnızca aktif görevin gerçek <code>output_summary</code> verisi gösterilir.</p>
    </div>
    <span class="live-indicator" class:available={!!report}> {report ? 'GÖREV VERİSİ VAR' : 'VERİ BEKLENİYOR'} </span>
  </header>

  {#if !report}
    <div class="empty-state">
      <strong>Henüz jüri raporu yayınlanmadı.</strong>
      <span>Bir görevde <code>autonomous_verifier</code> sonucu oluştuğunda jüri koltukları, oylar ve konsensüs burada görünür. Varsayılan jüri sayısı veya karar üretilmez.</span>
    </div>
  {:else}
    <div class="summary-grid">
      <article class="metric"><span>Hüküm</span><strong>{report.status || 'BİLİNMİYOR'}</strong></article>
      <article class="metric"><span>Güven</span><strong>{pct(report.confidence)}</strong></article>
      <article class="metric"><span>Veri güveni</span><strong>{typeof report.data_confidence === 'boolean' ? (report.data_confidence ? 'VAR' : 'YOK') : 'BELİRSİZ'}</strong></article>
      <article class="metric"><span>Belirsiz iddia</span><strong>{Number.isFinite(report.unknown_claims) ? report.unknown_claims : '—'}</strong></article>
    </div>

    <div class="two-col">
      <article class="panel">
        <h3>Jüri koltukları</h3>
        {#if jurors.length}
          <div class="chips">{#each jurors as seat}<span class="chip">{seat}</span>{/each}</div>
        {:else}
          <p class="muted">Aktif jüri koltuğu bildirilmedi.</p>
        {/if}
        <h4>Düşürülen koltuklar</h4>
        {#if dropped.length}
          <div class="chips dropped">{#each dropped as seat}<span class="chip">{seat}</span>{/each}</div>
        {:else}
          <p class="muted">Düşürülen koltuk bildirilmedi.</p>
        {/if}
      </article>

      <article class="panel">
        <h3>Bağımsız konsensüs denetimi</h3>
        {#if consensus}
          <div class="consensus-grid">
            <div><span>Denetlenen iddia</span><strong>{consensus.claims_audited ?? '—'}</strong></div>
            <div><span>Uyuşmazlık</span><strong>{consensus.mismatches ?? '—'}</strong></div>
            <div><span>Yeter sayı sağlandı</span><strong>{consensus.quorum_met_claims ?? '—'}</strong></div>
            <div><span>Gerekli koltuk</span><strong>{consensus.quorum_required ?? '—'}</strong></div>
            <div><span>Ortalama uzlaşma</span><strong>{pct(consensus.mean_strength)}</strong></div>
            <div><span>Bağlayıcı kip</span><strong>{typeof consensus.binding === 'boolean' ? (consensus.binding ? 'AÇIK' : 'KAPALI') : 'BELİRSİZ'}</strong></div>
          </div>
          {#if consensus.machine_note}<p class="machine-note">{consensus.machine_note}</p>{/if}
        {:else}
          <p class="muted">Bağımsız konsensüs özeti bu görevde bulunmuyor.</p>
        {/if}
      </article>
    </div>

    {#if report.decision_rule}
      <article class="panel">
        <h3>Karar kuralı / denetim izi</h3>
        <p class="decision-rule">{report.decision_rule}</p>
      </article>
    {/if}

    {#if accounting}
      <article class="panel">
        <h3>Oy muhasebesi</h3>
        <div class="chips">{#each Object.entries(accounting) as [key, value]}<span class="chip">{key}: <strong>{value}</strong></span>{/each}</div>
      </article>
    {/if}

    <article class="panel">
      <div class="panel-title"><h3>İddia bazlı doğrulamalar</h3><span>{verifications.length} kayıt</span></div>
      {#if verifications.length}
        <div class="verification-list">
          {#each verifications as item, index}
            <details class="verification">
              <summary>
                <span class="claim-number">{index + 1}</span>
                <span class="claim-text">{item.claim_text || item.claim_id || 'İsimsiz iddia'}</span>
                <span class="verdict">{item.truth_status || 'BİLİNMİYOR'}</span>
              </summary>
              <div class="verification-body">
                {#if item.evidence_quote}<blockquote>{item.evidence_quote}</blockquote>{/if}
                {#if item.evidence_url}<p><a href={item.evidence_url} target="_blank" rel="noopener">{item.evidence_url}</a></p>{/if}
                {#if item.contradiction_detail}<p><strong>Çelişki:</strong> {item.contradiction_detail}</p>{/if}
                <div class="audit-columns">
                  {#each [['Jüri oyları', item.juror_votes], ['Oy kapısı', item.vote_audit], ['Geçersiz oylar', item.invalid_votes], ['Koltuk hataları', item.seat_errors]] as pair}
                    {#if pair[1] && Object.keys(pair[1]).length}
                      <div><h4>{pair[0]}</h4><pre>{pretty(pair[1])}</pre></div>
                    {/if}
                  {/each}
                </div>
                {#if item.decision_rule}<p class="decision-rule">{item.decision_rule}</p>{/if}
                {#if item.claim_source_refs?.length}<p class="muted">Kaynak referansları: {item.claim_source_refs.join(' · ')}</p>{/if}
              </div>
            </details>
          {/each}
        </div>
      {:else}
        <p class="muted">Bu görevde doğrulanacak iddia kaydı bulunmuyor.</p>
      {/if}
    </article>

    {#if canonicalChecks.length}
      <article class="panel">
        <h3>Kanonik gözlem bütünlüğü kontrolleri ({canonicalChecks.length})</h3>
        {#each canonicalChecks as check}
          <details class="verification">
            <summary><span class="claim-text">{check.claim_text || check.claim_id}</span><span class="verdict">{check.downstream_decision_state || 'NO_FACTUAL_VERDICT'}</span></summary>
            <div class="verification-body">
              <p>{check.decision_note}</p>
              <div class="chips">
                <span class="chip">Provenance: {check.provenance_integrity}</span>
                <span class="chip">Kaynak tutarlılığı: {check.source_consistency}</span>
                <span class="chip">Tekrarlanabilirlik: {check.reproducibility}</span>
                <span class="chip">Gerçek hüküm: {check.factual_truth_status || 'BİLİNMİYOR'}</span>
              </div>
            </div>
          </details>
        {/each}
      </article>
    {/if}

    {#if report.fallback_reason}
      <p class="fallback-note">Veri güveni uyarısı: {report.fallback_reason}</p>
    {/if}
  {/if}
</section>

<style>
  .jury-workspace{margin:1.1rem auto;padding:clamp(1rem,2vw,1.5rem);width:min(1440px,96%);color:#e7e2d8;background:linear-gradient(145deg,#101216,#080a0d);border:1px solid rgba(190,157,93,.24);border-radius:14px;scroll-margin-top:72px}
  .jury-head{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;margin-bottom:1rem}
  .eyebrow{margin:0 0 .35rem;color:#b79a63;font-size:.62rem;letter-spacing:.18em;font-weight:800}
  .jury-head h2{margin:0;color:#e3d0a7;font-size:1.1rem}
  .jury-head p:not(.eyebrow){max-width:760px;margin:.35rem 0 0;color:#9b9a95;font-size:.75rem}
  .live-indicator{flex:0 0 auto;padding:.35rem .6rem;border:1px solid #51483a;border-radius:999px;color:#aaa398;font-size:.58rem;letter-spacing:.08em}
  .live-indicator.available{color:#a7d9b8;border-color:#37624b;background:rgba(36,110,68,.12)}
  .empty-state{display:flex;flex-direction:column;gap:.4rem;padding:1.1rem;background:#11161c;border:1px dashed #45413a;border-radius:9px;color:#d6c9aa}
  .empty-state span,.muted{color:#999a9c;font-size:.72rem}
  .summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem;margin-bottom:.75rem}
  .metric{padding:.75rem;background:#151a20;border:1px solid #2d333b;border-radius:8px}
  .metric span,.consensus-grid span{display:block;color:#9c9b96;font-size:.62rem}
  .metric strong{display:block;margin-top:.3rem;color:#e1c995;font-size:.95rem;overflow-wrap:anywhere}
  .two-col{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.75rem}
  .panel{margin:.7rem 0;padding:.85rem;background:#11161c;border:1px solid #2b323b;border-radius:9px;min-width:0}
  .panel h3{margin:0 0 .65rem;color:#d9c28f;font-size:.76rem}
  .panel h4{margin:.7rem 0 .4rem;color:#aab6bd;font-size:.66rem}
  .panel-title{display:flex;justify-content:space-between;align-items:center;gap:.7rem}
  .panel-title span{color:#a29c8e;font-size:.65rem}
  .chips{display:flex;flex-wrap:wrap;gap:.4rem}
  .chip{display:inline-flex;gap:.3rem;padding:.28rem .5rem;color:#c5c0b6;background:#1a2027;border:1px solid #343c45;border-radius:5px;font-size:.62rem;overflow-wrap:anywhere}
  .dropped .chip{color:#f0b7aa;border-color:#66403a;background:#261718}
  .consensus-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.6rem}
  .consensus-grid>div{padding:.45rem;background:#0c1116;border-radius:5px}
  .consensus-grid strong{display:block;margin-top:.15rem;color:#e1d2ae;font-size:.82rem}
  .machine-note,.decision-rule{color:#a9a59c;font-size:.68rem;overflow-wrap:anywhere}
  .decision-rule{padding:.55rem;background:#0a0e13;border-left:2px solid #9d8150;font-family:ui-monospace,monospace}
  .verification-list{display:flex;flex-direction:column;gap:.45rem}
  .verification{border:1px solid #303741;border-radius:6px;background:#0c1117}
  .verification summary{display:flex;align-items:center;gap:.6rem;padding:.55rem;cursor:pointer;list-style:none}
  .verification summary::-webkit-details-marker{display:none}
  .claim-number{display:grid;place-items:center;flex:0 0 1.4rem;height:1.4rem;color:#e0c88f;background:#282319;border-radius:4px;font-size:.65rem}
  .claim-text{flex:1;min-width:0;color:#d5d1c8;font-size:.7rem;overflow-wrap:anywhere}
  .verdict{flex:0 0 auto;padding:.22rem .4rem;color:#c9bd9f;background:#25231e;border:1px solid #4c4434;border-radius:4px;font-size:.58rem}
  .verification-body{padding:.6rem .8rem;border-top:1px solid #29313a;color:#b9b6ae;font-size:.68rem;overflow-wrap:anywhere}
  .verification-body a{color:#9bd4e2}
  .verification-body blockquote{margin:.4rem 0;padding:.5rem .65rem;border-left:2px solid #8b744b;background:#141820;color:#e2d9c5}
  .audit-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.55rem}
  .audit-columns pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;padding:.5rem;background:#080b10;border-radius:5px;color:#b9c4c8;font-size:.6rem}
  .fallback-note{padding:.6rem .75rem;color:#f0d49a;background:rgba(115,76,16,.15);border:1px solid rgba(190,145,55,.35);border-radius:6px;font-size:.68rem}
  @media(max-width:760px){.summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.two-col{grid-template-columns:1fr}.jury-head{flex-direction:column}.audit-columns{grid-template-columns:1fr}}
</style>
