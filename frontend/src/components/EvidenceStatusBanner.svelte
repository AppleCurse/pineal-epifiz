<script lang="ts">
  export let evidenceStatus: {
    code?: string;
    label?: string;
    severity?: string;
    reason?: string;
  } | null = null;

  $: insufficient = evidenceStatus?.code === 'insufficient_evidence';
  $: label = evidenceStatus?.label || 'YETERSİZ KANIT';
  $: reason = evidenceStatus?.reason || 'Karar üretmek için doğrulanabilir kanıt bulunamadı.';
</script>

{#if insufficient}
  <aside class="evidence-warning" role="alert" aria-live="assertive" data-evidence-status="insufficient_evidence">
    <div class="warning-heading">
      <span class="warning-icon" aria-hidden="true">⚠</span>
      <strong>{label}</strong>
    </div>
    <span class="warning-reason">{reason}</span>
    <span class="warning-note">Bu sonuç karar değildir; sistem kanıt uydurmadı.</span>
  </aside>
{/if}

<style>
  .evidence-warning {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.45rem 0.8rem;
    margin: 0.6rem 0;
    padding: 0.7rem 0.9rem;
    border: 1px solid rgba(239, 68, 68, 0.85);
    border-left: 4px solid #ef4444;
    background: rgba(80, 8, 8, 0.72);
    color: #fee2e2;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.02em;
  }

  .warning-heading {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    color: #fca5a5;
    font-size: 0.82rem;
  }

  .warning-icon {
    color: #f87171;
    font-size: 1.1rem;
  }

  .warning-reason {
    flex: 1 1 16rem;
    color: #fecaca;
    font-size: 0.74rem;
  }

  .warning-note {
    flex-basis: 100%;
    color: #fca5a5;
    font-size: 0.68rem;
    opacity: 0.9;
  }
</style>
