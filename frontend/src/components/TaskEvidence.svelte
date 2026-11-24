<script lang="ts">
  export let task: any = null;

  $: channels = Array.isArray(task?.channel_status)
    ? task.channel_status.filter((row: any) => row && typeof row === 'object' && typeof row.channel === 'string')
    : [];
  $: records = Array.isArray(task?.evidence_chain)
    ? task.evidence_chain.filter((row: any) => row?.agent === 'pillar_evidence_adapter')
    : [];
  $: record = records.length ? records[records.length - 1] : null;
  $: canonical = record?.evidence_type === 'canonical_evidence' && record?.result?.schema_version === 'evidence-item-v1' && Array.isArray(record.result.items)
    ? record.result.items.filter((item: any) => item && typeof item === 'object' && typeof item.content === 'string' && typeof item.evidence_id === 'string')
    : [];

  function channelLabel(status: unknown): string {
    switch (status) {
      case 'ok': return 'Çalıştı';
      case 'not_run': return 'Çalışmadı';
      case 'failed': return 'Başarısız';
      default: return 'Durum bilinmiyor';
    }
  }
  function typeLabel(type: unknown): string {
    switch (type) {
      case 'observation': return 'Gözlem';
      case 'absence': return 'Yokluk kaydı';
      case 'inference': return 'Çıkarım';
      case 'strategy': return 'Strateji';
      default: return 'Tür belirtilmemiş';
    }
  }
  function confidence(value: unknown): string {
    return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
      ? `${Math.round(value * 100)}%` : 'Belirtilmemiş';
  }
</script>

<section class="task-evidence" aria-label="Görev kapsamı ve kanıt kayıtları">
  <h3>Görev kapsamı ve kanıt kayıtları</h3>
  {#if !task?.task_id}
    <p>Henüz görev bilgisi yok.</p>
  {:else}
    <p>Görev: {task.task_id}</p>
    <h4>Kaynak kanalları</h4>
    {#if channels.length}
      <ul>
        {#each channels as channel}
          <li><strong>{channel.channel} — {channelLabel(channel.status)}</strong>
            {#if channel.reason}<span> · Sebep: {channel.reason}</span>{/if}
            {#if channel.detail}<span> · {channel.detail}</span>{/if}
          </li>
        {/each}
      </ul>
      <p>Çalışmadı veya başarısız, hedefte veri bulunmadığı anlamına gelmez.</p>
    {:else}
      <p>Bu görev için kanal durumu bildirilmedi.</p>
    {/if}
    <h4>Kanonik kanıt kayıtları</h4>
    <p>Bu kayıtlar görev genelindedir; yukarıdaki özet kartlarına ayrı ayrı bağlanmış değildir. Kaynak beyanı bağımsız doğrulama anlamına gelmez.</p>
    {#if record?.evidence_type === 'execution_failure' || record?.result?.build_status === 'failed'}
      <p>Kanıt kayıtları oluşturulamadı.</p>
    {:else if !record}
      <p>Bu görev için kanıt kayıtları henüz bildirilmedi.</p>
    {:else if !canonical.length}
      <p>Gösterilebilir kanıt kaydı yok.</p>
    {:else}
      <ul>
        {#each canonical as item}
          <li class="evidence-record">
            <strong>{typeLabel(item.epistemic_type)}</strong> · {item.content}
            <div>Kimlik: {item.evidence_id}</div>
            <div>Kaynak: {item.source_engine || 'Belirtilmemiş'} · Güven: {confidence(item.confidence)}</div>
            <div>Kaynak referansları: {Array.isArray(item.provenance_refs) && item.provenance_refs.length ? item.provenance_refs.join(', ') : 'Belirtilmemiş'}</div>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</section>

<style>
  .task-evidence {
    flex-shrink: 0;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    border-radius: 10px;
    padding: 12px 14px;
    color: var(--text-secondary);
    font-size: 12.5px;
    line-height: 1.5;
    overflow-wrap: anywhere;
  }
  h3 { color: var(--text-primary); font-size: 14px; font-weight: 700; }
  h4 { margin-top: 10px; color: var(--accent); font-size: 12.5px; font-weight: 600; }
  p { margin-top: 5px; }
  ul { padding-left: 18px; margin-top: 5px; }
  li { margin: 5px 0; }
  .evidence-record { border-top: 1px solid var(--border); padding-top: 6px; }
</style>
