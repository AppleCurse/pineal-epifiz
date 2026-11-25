<script lang="ts">
  import { apiFetch } from '../store';
  export let clientId = 'default';
  let agents: any[] = [];
  let source = 'none';
  let routing: any = null;
  let busy = false;
  let error = '';
  let updatedAt = '';
  let query = '';
  $: visible = agents.filter((agent: any) => String(agent?.agent_id || agent?.name || '').toLocaleLowerCase('tr').includes(query.toLocaleLowerCase('tr')));
  async function refresh() {
    if (busy) return;
    busy = true; error = '';
    try {
      const [a, r] = await Promise.all([
        apiFetch('/api/agents/status'),
        apiFetch('/api/llm/routing?client_id=' + encodeURIComponent(clientId || 'default'))
      ]);
      if (!a.ok) { const d = await a.json().catch(() => ({})); throw new Error(d?.error?.message || 'Ajan durumu HTTP ' + a.status); }
      const ad = await a.json();
      agents = Array.isArray(ad.agents) ? ad.agents : [];
      source = typeof ad.source === 'string' ? ad.source : 'unreachable';
      if (r.ok) routing = await r.json();
      else routing = null;
      updatedAt = new Date().toLocaleTimeString('tr-TR');
    } catch (e: any) { error = e?.message || 'Ajan envanteri okunamadı.'; agents = []; source = 'unreachable'; }
    finally { busy = false; }
  }
  function modelChain(id: string) {
    const info = routing?.routing?.agents?.[id];
    return Array.isArray(info?.chain) && info.chain.length ? info.chain.join(' → ') : 'Model rotası bildirilmedi';
  }
  function sourceLabel(value: string) {
    return ({ redis_bus: 'Redis olay akışı', in_memory: 'Bellek içi olay akışı', fallback: 'Yedek kaynak', error: 'Kaynak hatası', unreachable: 'Erişilemiyor', none: 'Henüz okunmadı' } as Record<string,string>)[value] || value;
  }
</script>
<section id="agents" class="agent-lab" aria-label="Ajan laboratuvarı">
  <header><div><span class="kicker">PINEAL · AJAN GÖZLEMLENEBİLİRLİĞİ</span><h2>Ajan Laboratuvarı</h2><p>Ajan durumu ve uzman model rotaları ayrı kaynaklardan okunur.</p></div><button on:click={refresh} disabled={busy}>{busy ? 'OKUNUYOR…' : 'ENVANTERİ YENİLE'}</button></header>
  <div class="source-row"><span>Durum kaynağı: <strong>{sourceLabel(source)}</strong></span><span>{updatedAt ? 'Son okuma: ' + updatedAt : 'Henüz okunmadı'}</span><span>{agents.length} ajan</span></div>
  <input class="search" bind:value={query} placeholder="Ajan ara..." aria-label="Ajan ara" />
  {#if error}<p class="error" role="alert">{error}</p>{/if}
  {#if !agents.length && !error}<div class="empty">Ajan envanteri henüz okunmadı. Yenile düğmesi gerçek sunucu durumunu getirir.</div>{/if}
  <div class="agent-grid">
    {#each visible as agent, i (agent.agent_id || i)}
      <article>
        <div class="agent-top"><strong>{agent.agent_id || agent.name || 'Kimliksiz ajan'}</strong><span class:active={String(agent.status).toLowerCase() === 'active'} class:ready={String(agent.status).toLowerCase() === 'ready'}>{agent.status || 'Durum bildirilmedi'}</span></div>
        <p>{modelChain(agent.agent_id || agent.name || '')}</p>
        {#if agent.metadata && Object.keys(agent.metadata).length}<small>{Object.entries(agent.metadata).slice(0,3).map(([k,v]) => k + ': ' + String(v)).join(' · ')}</small>{/if}
      </article>
    {/each}
  </div>
  <footer>Bu ekran ajan başlatmaz veya durum uydurmaz. Model zinciri sunucudan gelmiyorsa “bildirilmedi” olarak kalır.</footer>
</section>
<style>
  .agent-lab{width:min(1500px,calc(100% - 28px));margin:0 auto 28px;padding:20px;color:#e9e3d7;background:linear-gradient(145deg,#151719,#090a0c);border:1px solid rgba(190,164,111,.2);border-radius:15px;box-shadow:0 20px 55px rgba(0,0,0,.22);font-family:inherit}
  header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}h2{font-size:19px;margin:5px 0}.kicker{font-size:9px;letter-spacing:.2em;color:#bda36e;font-weight:800}header p{margin:0;color:#89857c;font-size:10px}
  button{padding:9px 12px;border:1px solid rgba(201,177,127,.42);border-radius:6px;background:rgba(185,157,104,.1);color:#d8c49a;font-size:9px;font-weight:800;letter-spacing:.08em;cursor:pointer}button:disabled{opacity:.45}
  .source-row{display:flex;flex-wrap:wrap;gap:8px 18px;padding:10px 0;margin:10px 0;border-top:1px solid rgba(190,164,111,.1);border-bottom:1px solid rgba(190,164,111,.1);font-size:9px;color:#858078}.source-row strong{color:#c7b68f}
  .search{box-sizing:border-box;width:100%;padding:9px 10px;margin-bottom:10px;border:1px solid rgba(190,164,111,.17);border-radius:6px;background:#08090b;color:#eee8dc;font:inherit;font-size:10px}
  .agent-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.agent-grid article{min-width:0;padding:11px;border:1px solid rgba(190,164,111,.13);border-radius:8px;background:rgba(255,255,255,.018)}
  .agent-top{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.agent-top strong{font-size:10px;color:#ddd2bd;overflow-wrap:anywhere}.agent-top span{font-size:8px;color:#a49b89;white-space:nowrap}.agent-top span.active{color:#d9b16e}.agent-top span.ready{color:#9bb39a}
  .agent-grid p{font-size:9px;color:#b99d68;line-height:1.4;overflow-wrap:anywhere;margin:9px 0 4px}.agent-grid small{font-size:8px;color:#7f7a70;overflow-wrap:anywhere}
  .empty{padding:15px;border:1px dashed rgba(190,164,111,.17);border-radius:7px;color:#89857c;font-size:10px}.error{font-size:10px;color:#e29a8b}.agent-lab footer{margin-top:12px;font-size:9px;color:#77736b;line-height:1.5}
  @media(max-width:900px){.agent-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.agent-lab{width:calc(100% - 16px);padding:12px}.agent-grid{grid-template-columns:1fr}header{flex-direction:column}}
</style>
