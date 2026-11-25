<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Icon from './Icon.svelte';

  export let showDemo = false;
  export let showTerms = false;
  export let demoReports: any[] = [];
  export let demoSelected: any = null;
  export let demoLoading = false;
  export let demoError = '';
  export let legalNotice: any = null;

  const dispatch = createEventDispatcher();
</script>


  {#if showDemo}
    <div class="cockpit-modal-backdrop" role="dialog" aria-modal="true" aria-label="Örnek analiz raporları">
      <div class="cockpit-modal-card demo-modal-card">
        <div class="cockpit-modal-head">
          <h3><Icon name="file" size={0.95} /> ÖRNEK ANALİZ RAPORLARI</h3>
          <p class="cockpit-modal-sub">
            Ürünün çıktı biçimini gösteren 2 SENTEİTİK örnek. Gerçek kişi/kurum taranmadı — token gerekmez.
          </p>
          <button class="modal-close-btn" on:click={() => dispatch('close-demo')} aria-label="Kapat">
            <Icon name="close" size={0.9} />
          </button>
        </div>
        <div class="cockpit-modal-body demo-body">
          {#if demoError}
            <div class="modal-alert err" role="alert">{demoError}</div>
          {/if}
          {#if demoLoading && !demoReports.length}
            <div class="demo-loading">Yükleniyor...</div>
          {/if}
          <div class="demo-layout">
            <div class="demo-index" role="tablist" aria-label="Örnek raporlar">
              {#each demoReports as r (r.id)}
                <button
                  class="demo-index-item"
                  class:active={demoSelected?.id === r.id}
                  role="tab"
                  aria-selected={demoSelected?.id === r.id}
                  on:click={() => dispatch('select-demo', { id: r.id })}
                >
                  <span class="demo-index-title">{r.title}</span>
                  <span class="demo-index-sub">{r.scenario}</span>
                  <span class="demo-index-meta">{r.finding_count} bulgu · {r.evidence_count} kanıt</span>
                </button>
              {/each}
            </div>

            <div class="demo-report" role="tabpanel">
              {#if demoSelected}
                <div class="demo-report-head">
                  <h4>{demoSelected.title}</h4>
                  <div class="demo-subject">{demoSelected.subject_label}</div>
                  <div class="demo-tags">
                    <span class="demo-tag">SENTEİTİK</span>
                    <span class="demo-tag">{demoSelected.engine}</span>
                    <span class="demo-tag">{demoSelected.duration_seconds} sn</span>
                  </div>
                </div>

                <div class="demo-confidence">
                  <strong>{demoSelected.confidence?.label}</strong>
                  <span>{demoSelected.confidence?.caveat}</span>
                </div>

                <h5>Bulgular</h5>
                {#each demoSelected.findings as f (f.id)}
                  <div class="demo-finding">
                    <div class="demo-finding-head">
                      <span class="demo-sev sev-{(f.severity || '').toLowerCase()}">{f.severity}</span>
                      <strong>{f.title}</strong>
                    </div>
                    <blockquote>{f.quote}</blockquote>
                    <div class="demo-finding-meta">
                      Kanıt: {(f.evidence || []).join(', ')} · Güven: {f.confidence}
                    </div>
                  </div>
                {/each}

                <h5>Kanıt Zinciri</h5>
                <ul class="demo-evidence">
                  {#each demoSelected.evidence_chain as e, i (i)}
                    <li>
                      <strong>{e.agent}</strong> — {e.result?.claim}
                      <span class="demo-ev-status">[{e.result?.verification || 'BİLİNMİYOR'}]</span>
                    </li>
                  {/each}
                </ul>

                <h5>Sütun Durumları</h5>
                <div class="demo-pillars">
                  {#each demoSelected.pillars as pl (pl.id)}
                    <div class="demo-pillar st-{(pl.status || '').toLowerCase()}">
                      <span class="demo-pillar-label">{pl.label}</span>
                      <span class="demo-pillar-status">{pl.status}</span>
                      <span class="demo-pillar-summary">{pl.summary}</span>
                    </div>
                  {/each}
                </div>

                <h5>Sınırlar</h5>
                <ul class="demo-limits">
                  {#each demoSelected.limitations as lim, i (i)}
                    <li>{lim}</li>
                  {/each}
                </ul>

                <p class="demo-note">{demoSelected.notice}</p>
              {:else}
                <div class="demo-loading">Soldan bir örnek seçin.</div>
              {/if}
            </div>
          </div>
        </div>
      </div>
    </div>
  {/if}

  
  {#if showTerms}
    <div class="cockpit-modal-backdrop" role="dialog" aria-modal="true" aria-label="Sorumluluk reddi ve kullanım koşulları">
      <div class="cockpit-modal-card demo-modal-card">
        <div class="cockpit-modal-head">
          <h3><Icon name="warning" size={0.95} /> SORUMLULUK REDDİ VE KULLANIM KOŞULLARI</h3>
          <button class="modal-close-btn" on:click={() => dispatch('close-terms')} aria-label="Kapat">
            <Icon name="close" size={0.9} />
          </button>
        </div>
        <div class="cockpit-modal-body demo-body">
          {#if legalNotice}
            <div class="terms-headline">{legalNotice.headline}</div>
            <p class="terms-par">{legalNotice.disclaimer}</p>
            <h4>Açık Rıza Beyanı</h4>
            <p class="terms-par">{legalNotice.consent_declaration}</p>
            <h4>Kullanım Koşulları</h4>
            <ul class="terms-list">
              {#each legalNotice.usage_terms as t, i (i)}
                <li>{t}</li>
              {/each}
            </ul>
            <p class="terms-par terms-muted">{legalNotice.not_legal_advice}</p>
            <p class="terms-par terms-muted">Yargı çevresi: {legalNotice.jurisdiction} · Dil: {legalNotice.language}</p>
          {:else}
            <div class="demo-loading">Metin yüklenemedi — sunucuya erişilemiyor.</div>
          {/if}
        </div>
      </div>
    </div>
  {/if}

<style>
  .cockpit-modal-backdrop {
    position: fixed; inset: 0; z-index: 9999;
    background: rgba(2, 4, 10, 0.85);
    backdrop-filter: blur(8px);
    display: flex; align-items: center; justify-content: center; padding: 1rem;
  }
  .cockpit-modal-card {
    width: min(880px, 96vw); max-height: 90vh;
    background: #0a0e17; border: 1px solid rgba(6, 182, 212, 0.45);
    border-radius: 10px; display: flex; flex-direction: column; overflow: hidden;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.8);
  }
  .cockpit-modal-head {
    display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;
    padding: 1rem 1.25rem; border-bottom: 1px solid var(--border-dim);
  }
  .cockpit-modal-head h3 { font-size: 0.9rem; color: var(--gold); margin: 0 0 0.25rem; }
  .cockpit-modal-sub { font-size: 0.7rem; color: var(--text-dim); margin: 0; }
  .modal-x-btn {
    background: transparent; border: 1px solid var(--border-dim); color: var(--text-dim);
    border-radius: 4px; padding: 0.25rem 0.55rem; cursor: pointer;
  }
  .cockpit-modal-tabs {
    display: flex; gap: 0.5rem; padding: 0.65rem 1.25rem;
    background: rgba(5, 7, 12, 0.8); border-bottom: 1px solid var(--border-dim);
    flex-wrap: wrap;
  }
  .cockpit-modal-tabs button {
    padding: 0.4rem 0.8rem; font-family: inherit; font-size: 0.7rem; font-weight: 700;
    color: var(--text-dim); background: rgba(255,255,255,0.03);
    border: 1px solid var(--border-dim); border-radius: 5px; cursor: pointer;
  }
  .cockpit-modal-tabs button.active {
    color: #02140a; background: var(--cyan); border-color: var(--cyan);
  }
  .cockpit-modal-body {
    padding: 1rem 1.25rem;
    






    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto; display: flex; flex-direction: column; gap: 1rem;
  }
  .modal-section-box {
    background: rgba(15, 20, 32, 0.7); border: 1px solid var(--border-dim);
    border-radius: 8px; padding: 0.85rem;
  }
  .modal-section-box h4 { font-size: 0.72rem; color: var(--cyan); margin: 0 0 0.65rem; text-transform: uppercase; }
  



  .endpoint-path {
    text-transform: none;
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-size: 0.68rem;
    font-weight: 500;
    letter-spacing: 0;
    color: var(--text-dim);
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-dim);
    border-radius: 4px;
    padding: 0.05rem 0.35rem;
    margin-left: 0.4rem;
    vertical-align: 0.05em;
    white-space: nowrap;
  }
  


  .modal-close-btn {
    flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    width: 1.85rem; height: 1.85rem;
    background: transparent;
    border: 1px solid var(--border-dim);
    border-radius: 4px;
    color: var(--text-dim);
    cursor: pointer;
    transition: color 0.15s, border-color 0.15s, background 0.15s;
  }
  .modal-close-btn:hover,
  .modal-close-btn:focus-visible {
    color: var(--gold);
    border-color: var(--gold);
    background: rgba(212, 175, 55, 0.08);
  }
  .provider-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.65rem; }
  .provider-field { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.68rem; color: var(--text-dim); }
  .pf-top { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }
  .pf-badge { font-size: 0.58rem; padding: 0.1rem 0.35rem; border-radius: 3px; background: rgba(255,255,255,0.08); color: var(--text-muted); }
  .pf-badge.active { background: rgba(16, 185, 129, 0.2); color: var(--emerald); border: 1px solid rgba(16, 185, 129, 0.4); }
  .provider-field input {
    padding: 0.45rem 0.6rem; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
    color: var(--text-primary); background: #05080f; border: 1px solid var(--border-dim); border-radius: 4px;
  }
  .local-toggle-row { display: flex; align-items: center; gap: 0.5rem; font-size: 0.7rem; color: var(--text-primary); margin-bottom: 0.6rem; }
  .routing-table-wrap { max-height: 360px; overflow: auto; }
  .routing-table { width: 100%; border-collapse: collapse; font-size: 0.66rem; }
  .routing-table th, .routing-table td { text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border-dim); }
  .routing-table th { color: var(--gold); font-weight: 800; }
  .rt-agent { color: var(--cyan); font-weight: 700; font-family: 'JetBrains Mono', monospace; }
  .rt-tier { color: var(--gold); font-weight: 700; }
  .rt-chain { color: var(--text-primary); font-family: 'JetBrains Mono', monospace; }
  .rt-src { color: var(--text-muted); }
  .routing-warning { margin: .5rem 0; padding: .5rem; color: #fbbf24; background: rgba(120, 70, 0, .2); border: 1px solid rgba(251, 191, 36, .35); font-size: .68rem; }
  .routing-note { font-size: 0.7rem; color: var(--text-dim); }
  .modal-alert { padding: 0.55rem 0.75rem; border-radius: 5px; font-size: 0.72rem; }
  .modal-alert.ok { background: rgba(16, 185, 129, 0.15); border: 1px solid var(--emerald); color: var(--emerald); }
  .modal-alert.err { background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #fca5a5; }
  .cockpit-modal-foot {
    display: flex; justify-content: flex-end; gap: 0.65rem;
    padding: 0.85rem 1.25rem; border-top: 1px solid var(--border-dim);
  }
  .modal-cancel-btn {
    padding: 0.45rem 0.9rem; font-family: inherit; font-size: 0.7rem;
    background: transparent; color: var(--text-dim); border: 1px solid var(--border-dim); border-radius: 5px; cursor: pointer;
  }
  .modal-save-btn {
    padding: 0.45rem 1rem; font-family: inherit; font-size: 0.7rem; font-weight: 800;
    background: linear-gradient(135deg, var(--emerald), #059669); color: #02140a; border: none; border-radius: 5px; cursor: pointer;
  }
  
  .demo-modal-card { width: min(1080px, 96vw); }
  .demo-body { gap: 0.75rem; }
  .demo-loading { color: var(--text-dim); font-size: 0.78rem; padding: 1rem 0; }

  .demo-layout { display: grid; grid-template-columns: 260px 1fr; gap: 1rem; min-height: 0; }
  .demo-index { display: flex; flex-direction: column; gap: 0.5rem; }
  .demo-index-item {
    display: flex; flex-direction: column; gap: 0.25rem; text-align: left;
    padding: 0.65rem 0.75rem; cursor: pointer; font-family: inherit;
    background: rgba(15, 20, 32, 0.6); border: 1px solid var(--border-dim);
    border-radius: 6px; color: var(--text-dim); transition: all 0.15s;
  }
  .demo-index-item:hover { border-color: var(--cyan); color: var(--text-primary); }
  .demo-index-item.active { border-color: var(--emerald); background: rgba(16, 185, 129, 0.08); color: var(--text-primary); }
  .demo-index-title { font-size: 0.78rem; font-weight: 800; letter-spacing: 0.02em; }
  .demo-index-sub { font-size: 0.62rem; color: var(--text-muted); }
  .demo-index-meta { font-size: 0.6rem; color: var(--cyan); }

  .demo-report { min-width: 0; padding-right: 0.25rem; }
  .demo-report-head h4 { font-size: 0.95rem; color: var(--gold); margin: 0 0 0.2rem; }
  .demo-subject { font-size: 0.68rem; color: var(--cyan); margin-bottom: 0.4rem; }
  .demo-tags { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 0.6rem; }
  .demo-tag {
    font-size: 0.58rem; font-weight: 700; letter-spacing: 0.06em;
    padding: 0.1rem 0.4rem; border-radius: 3px;
    background: rgba(255, 255, 255, 0.06); border: 1px solid var(--border-dim);
    color: var(--text-dim); text-transform: uppercase;
  }
  .demo-confidence {
    display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: baseline;
    padding: 0.5rem 0.65rem; margin-bottom: 0.6rem; border-radius: 5px;
    background: rgba(6, 182, 212, 0.08); border: 1px solid rgba(6, 182, 212, 0.3);
    font-size: 0.68rem;
  }
  .demo-confidence strong { color: var(--cyan); }
  .demo-confidence span { color: var(--text-dim); }

  .demo-report h5 {
    font-size: 0.62rem; letter-spacing: 0.12em; text-transform: uppercase;
    color: var(--text-muted); margin: 0.75rem 0 0.35rem;
  }
  .demo-finding {
    padding: 0.5rem 0.65rem; margin-bottom: 0.4rem; border-radius: 5px;
    background: rgba(15, 20, 32, 0.65); border-left: 2px solid var(--border-dim);
  }
  .demo-finding-head { display: flex; align-items: center; gap: 0.5rem; font-size: 0.74rem; }
  .demo-finding blockquote {
    margin: 0.3rem 0; padding-left: 0.6rem; border-left: 1px solid var(--border-dim);
    font-size: 0.7rem; font-style: italic; color: var(--text-dim);
  }
  .demo-finding-meta { font-size: 0.6rem; color: var(--text-muted); }
  .demo-sev { font-size: 0.58rem; font-weight: 800; padding: 0.08rem 0.35rem; border-radius: 3px; }
  .demo-sev.sev-high { background: rgba(239, 68, 68, 0.18); color: #fca5a5; }
  .demo-sev.sev-medium { background: rgba(251, 191, 36, 0.16); color: #fbbf24; }
  .demo-sev.sev-low { background: rgba(16, 185, 129, 0.14); color: var(--emerald); }

  .demo-evidence, .demo-limits, .terms-list {
    margin: 0; padding-left: 1.1rem; font-size: 0.68rem; color: var(--text-dim);
    display: flex; flex-direction: column; gap: 0.25rem;
  }
  .demo-evidence strong { color: var(--cyan); }
  .demo-ev-status { color: var(--text-muted); margin-left: 0.25rem; }

  .demo-pillars { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.4rem; }
  .demo-pillar {
    display: flex; flex-direction: column; gap: 0.15rem;
    padding: 0.4rem 0.5rem; border-radius: 4px; font-size: 0.62rem;
    background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-dim);
  }
  .demo-pillar-label { font-weight: 800; color: var(--text-primary); letter-spacing: 0.06em; }
  .demo-pillar-status { font-size: 0.58rem; font-weight: 700; }
  .demo-pillar.st-observed .demo-pillar-status { color: var(--emerald); }
  .demo-pillar.st-partial .demo-pillar-status { color: var(--amber); }
  .demo-pillar.st-no_data .demo-pillar-status { color: var(--text-muted); }
  .demo-pillar-summary { color: var(--text-muted); line-height: 1.35; }

  .demo-note {
    margin-top: 0.6rem; padding: 0.5rem 0.65rem; border-radius: 5px;
    font-size: 0.66rem; color: #fbbf24;
    background: rgba(120, 70, 0, 0.18); border: 1px solid rgba(251, 191, 36, 0.3);
  }

  
  .terms-headline {
    font-size: 0.82rem; font-weight: 800; color: var(--gold);
    padding: 0.65rem 0.8rem; border-radius: 5px;
    background: rgba(212, 175, 55, 0.08); border: 1px solid rgba(212, 175, 55, 0.3);
  }
  .terms-par { font-size: 0.75rem; line-height: 1.6; color: var(--text-dim); margin: 0; }
  .terms-muted { color: var(--text-muted); font-size: 0.68rem; }
  .terms-list li { line-height: 1.5; }

</style>
