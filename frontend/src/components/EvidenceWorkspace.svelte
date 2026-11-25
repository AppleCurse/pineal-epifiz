<script lang="ts">
  import { taskStatus } from '../store';
  import { buildPillarSummaries, evidenceChainToReportItems } from '../lib/evidence';
  import TaskEvidence from './TaskEvidence.svelte';
  const labels: Record<string, string> = { follower: 'Takipçi', timing: 'Zaman', depth: 'Derinlik', visual: 'Görsel', shadow: 'Gölge', osint: 'Açık kaynak', resonance: 'Rezonans' };
  $: task = $taskStatus;
  $: summaries = buildPillarSummaries(task);
  $: chain = Array.isArray(task?.evidence_chain) ? task.evidence_chain : [];
  $: reportable = evidenceChainToReportItems(task);
  $: hasTask = Boolean(task?.task_id);
</script>
<section id="evidence" class="evidence-workspace" aria-label="Kanıt ve kaynak merkezi">
  <header><div><span class="kicker">PINEAL · KAYNAK VE İZLENEBİLİRLİK</span><h2>Kanıt Merkezi</h2><p>Yedi sütun, görev kanıt zinciri ve rapora aktarılabilir kayıtlar.</p></div><div class="task-ref">{hasTask ? task.task_id : 'AKTİF GÖREV YOK'}</div></header>
  {#if !hasTask}
    <div class="empty">Henüz aktif görev bulunmuyor. Yeni bir analiz başlatıldığında görev kanıtları burada görünür.</div>
  {:else}
    <div class="pillar-grid">
      {#each Object.values(summaries) as item}
        <article class:has-data={item.hasData}>
          <span>{labels[item.id] || item.id}</span><strong>{item.hasData ? 'KAYIT VAR' : 'VERİ YOK'}</strong>
          <small>{item.evidenceCount} kanıt · {item.confidence === null ? 'Güven belirtilmedi' : 'Güven ' + item.confidence + '%'}</small>
          <small>{item.sufficiency}</small>
          {#if item.sources.length}<small>Kaynak: {item.sources.join(', ')}</small>{/if}
        </article>
      {/each}
    </div>
    <div class="chain-head"><h3>Kanıt zinciri</h3><span>{chain.length} ham kayıt · {reportable.length} rapora aktarılabilir kayıt</span></div>
    {#if chain.length}
      <div class="chain-list">
        {#each chain as entry, i}
          <article><div><strong>{entry.agent || entry.source_agent || entry.source_engine || 'Kaynak belirtilmedi'}</strong><span>{entry.epistemic_type || entry.evidence_type || 'Tür belirtilmedi'}</span></div>
            <p>{typeof entry.content === 'string' ? entry.content : JSON.stringify(entry.result ?? entry.content ?? entry).slice(0, 900)}</p>
            {#if entry.timestamp}<small>{entry.timestamp}</small>{/if}
          </article>
        {/each}
      </div>
    {:else}
      <div class="empty">Görev var, ancak henüz kanıt zinciri kaydı bildirilmedi.</div>
    {/if}
    <TaskEvidence task={task} />
  {/if}
  <footer>“Veri yok” ifadesi hedefte bulgu olmadığı anlamına gelmez. Kaynak beyanı tek başına doğrulama değildir; güven puanı yalnızca kaynakta sayısal olarak varsa gösterilir.</footer>
</section>
<style>
  .evidence-workspace{width:min(1500px,calc(100% - 28px));margin:0 auto 28px;padding:20px;color:#e9e3d7;background:linear-gradient(145deg,#141618,#090a0c);border:1px solid rgba(190,164,111,.2);border-radius:15px;box-shadow:0 20px 55px rgba(0,0,0,.22);font-family:inherit}
  header{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:15px}.kicker{font-size:9px;letter-spacing:.2em;color:#bda36e;font-weight:800}h2{font-size:19px;margin:5px 0}header p{font-size:10px;color:#89857c;margin:0}.task-ref{font-size:9px;color:#bba77b;border:1px solid rgba(190,164,111,.2);padding:7px 9px;border-radius:5px;overflow-wrap:anywhere}
  .pillar-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:7px;margin:12px 0 18px}.pillar-grid article{display:flex;flex-direction:column;gap:6px;min-width:0;padding:10px 9px;border:1px solid rgba(190,164,111,.13);border-radius:8px;background:rgba(255,255,255,.018)}.pillar-grid article.has-data{border-color:rgba(131,159,135,.45);background:rgba(131,159,135,.045)}.pillar-grid article span{font-size:10px;color:#d8c8a7;font-weight:750}.pillar-grid article strong{font-size:8px;letter-spacing:.1em;color:#c28b7b}.pillar-grid article.has-data strong{color:#9bb39a}.pillar-grid article small{font-size:8px;line-height:1.4;color:#858078;overflow-wrap:anywhere}
  .chain-head{display:flex;justify-content:space-between;gap:8px;align-items:baseline;margin:10px 0}.chain-head h3{font-size:12px;margin:0;color:#d8c8a7}.chain-head span{font-size:9px;color:#817c72}.chain-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;max-height:430px;overflow:auto;margin-bottom:12px}
  .chain-list article{padding:10px;border:1px solid rgba(190,164,111,.12);border-radius:7px;background:rgba(0,0,0,.18);min-width:0}.chain-list article>div{display:flex;justify-content:space-between;gap:8px}.chain-list strong{font-size:9px;color:#c9b17f;overflow-wrap:anywhere}.chain-list article span,.chain-list article small{font-size:8px;color:#817c72}.chain-list p{font-size:9px;color:#c0baaf;line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere;margin:7px 0 0}
  .empty{padding:16px;border:1px dashed rgba(190,164,111,.18);border-radius:8px;color:#89857c;font-size:10px}.evidence-workspace footer{margin-top:12px;font-size:9px;color:#77736b;line-height:1.5}
  :global(.task-evidence){margin-top:12px;background:rgba(0,0,0,.16);border-color:rgba(190,164,111,.15);color:#c9c1b4}:global(.task-evidence h3){color:#d8c8a7}:global(.task-evidence h4){color:#b99d68}
  @media(max-width:1000px){.pillar-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}@media(max-width:620px){.evidence-workspace{width:calc(100% - 16px);padding:12px}.pillar-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.chain-list{grid-template-columns:1fr}header{flex-direction:column}}
</style>
