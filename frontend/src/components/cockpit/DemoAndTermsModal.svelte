<script lang="ts">
  import Icon from '../Icon.svelte';

  export let showDemoModal: boolean = false;
  export let demoLoading: boolean = false;
  export let demoData: any = null;
  export let selectedDemoReport: any = null;
  export let showTermsModal: boolean = false;
  export let legalNotice: any = null;

  export let onCloseDemo: () => void = () => {};
  export let onSelectDemoReport: (id: string) => void = () => {};
  export let onCloseTerms: () => void = () => {};
</script>

{#if showDemoModal}
  <div class="modal-backdrop" role="presentation" on:click|self={onCloseDemo}>
    <div class="modal-dialog" role="dialog" aria-modal="true" aria-label="Örnek Raporlar ve Vitrin">
      <header class="modal-header">
        <div>
          <h3>Örnek Çalışmalar (Demo Vitrini)</h3>
          <p class="modal-sub">Herhangi bir anahtar veya kurulum gerektirmeden sistemin nasıl sonuç çıkardığını görebilirsiniz.</p>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" on:click={onCloseDemo} aria-label="Kapat">
          <Icon name="close" size={1} />
        </button>
      </header>

      <div class="modal-body">
        {#if demoLoading}
          <div class="empty-state">Örnek vitrin yükleniyor...</div>
        {:else if demoData}
          {#if demoData.headline || demoData.summary}
            <div class="alert-banner ok">
              <div>
                {#if demoData.headline}<strong>{demoData.headline}</strong>{/if}
                {#if demoData.summary}<p>{demoData.summary}</p>{/if}
              </div>
            </div>
          {/if}

          {#if Array.isArray(demoData.reports) && demoData.reports.length > 0}
            <div class="demo-list">
              {#each demoData.reports as rep}
                <button
                  type="button"
                  class="demo-card"
                  on:click={() => onSelectDemoReport(rep.id || rep.report_id)}
                >
                  <strong>{rep.title || rep.name || rep.id}</strong>
                  <span>{rep.summary || 'İçeriği açmak için tıklayın'}</span>
                </button>
              {/each}
            </div>
          {/if}

          {#if selectedDemoReport}
            <div class="detail-box">
              <strong>{selectedDemoReport.title || 'Örnek Rapor İçeriği'}</strong>
              <pre class="json-pre">{JSON.stringify(selectedDemoReport, null, 2)}</pre>
            </div>
          {/if}
        {:else}
          <div class="empty-state">Gösterilecek örnek kayıt bulunamadı.</div>
        {/if}
      </div>

      <footer class="modal-footer">
        <button type="button" class="btn btn-ghost" on:click={onCloseDemo}>Kapat</button>
      </footer>
    </div>
  </div>
{/if}

{#if showTermsModal}
  <div class="modal-backdrop" role="presentation" on:click|self={onCloseTerms}>
    <div class="modal-dialog" role="dialog" aria-modal="true" aria-label="Kullanım Kuralları ve Yasal Uyarı">
      <header class="modal-header">
        <div>
          <h3>Kullanım Kuralları ve Sorumluluk Beyanı</h3>
          <p class="modal-sub">Bu sistemi kullanırken uyulması gereken temel gizlilik ve güvenlik ilkeleri.</p>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" on:click={onCloseTerms} aria-label="Kapat">
          <Icon name="close" size={1} />
        </button>
      </header>

      <div class="modal-body">
        {#if legalNotice}
          <div class="terms-stack">
            {#if legalNotice.headline}
              <div class="alert-banner warn"><strong>{legalNotice.headline}</strong></div>
            {/if}
            {#if legalNotice.consent_declaration}
              <div class="term-item">
                <strong>Açık Rıza İlkesi</strong>
                <p>{legalNotice.consent_declaration}</p>
              </div>
            {/if}
            {#if legalNotice.minor_protection}
              <div class="term-item">
                <strong>18 Yaş Altı Koruması</strong>
                <p>{legalNotice.minor_protection}</p>
              </div>
            {/if}
            {#if legalNotice.usage_terms}
              <div class="term-item">
                <strong>Kullanım Şartları</strong>
                <p>{legalNotice.usage_terms}</p>
              </div>
            {/if}
            {#if legalNotice.disclaimer}
              <div class="term-item">
                <strong>Sorumluluk Bildirimi</strong>
                <p>{legalNotice.disclaimer}</p>
              </div>
            {/if}
          </div>
        {:else}
          <div class="empty-state">Yasal bildirim metni sunucudan alınamadı; yine de analiz için açık rıza ve 18+ beyanı gereklidir.</div>
        {/if}
      </div>

      <footer class="modal-footer">
        <button type="button" class="btn btn-primary" on:click={onCloseTerms}>Okudum, Anladım</button>
      </footer>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(2, 6, 23, 0.7);
    backdrop-filter: blur(4px);
    z-index: 65;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
  }

  .modal-dialog {
    width: 100%;
    max-width: 700px;
    max-height: 86vh;
    background: var(--bg-surface);
    backdrop-filter: blur(18px);
    border: 1px solid var(--border-strong);
    border-radius: 14px;
    box-shadow: var(--shadow-md);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  :global([data-theme='dark']) .modal-dialog {
    background: rgba(30, 14, 11, 0.92);
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

  .modal-body {
    padding: 18px 20px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .demo-list,
  .terms-stack {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .demo-card,
  .term-item {
    text-align: left;
    padding: 12px 14px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    color: var(--text-primary);
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .demo-card {
    cursor: pointer;
  }

  .demo-card:hover {
    border-color: var(--accent);
    background: var(--bg-hover);
  }

  .demo-card span,
  .term-item p {
    font-size: 12.5px;
    color: var(--text-secondary);
    line-height: 1.5;
  }

  .detail-box {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .json-pre {
    padding: 10px;
    border-radius: 8px;
    background: var(--bg-input);
    border: 1px solid var(--border);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px;
    max-height: 260px;
    overflow: auto;
    white-space: pre-wrap;
    color: var(--text-secondary);
  }

  .modal-footer {
    padding: 14px 20px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: flex-end;
    background: var(--bg-elevated);
  }
</style>
