<script lang="ts">
  export let telemetry: any = null;
  let query = '';
  let filter: 'all' | 'ready' | 'blocked' = 'all';
  $: capabilities = Array.isArray(telemetry?.capabilities) ? telemetry.capabilities : [];
  $: readyCount = capabilities.filter((item: any) => item?.available === true).length;
  $: blockedCount = capabilities.filter((item: any) => item?.available === false).length;
  $: visibleCapabilities = capabilities.filter((item: any) => {
    const matchesFilter = filter === 'all' || (filter === 'ready' && item?.available === true) || (filter === 'blocked' && item?.available === false);
    const haystack = [item?.id, item?.kind, item?.reason, item?.policy_reason].filter(Boolean).join(' ').toLocaleLowerCase('tr');
    return matchesFilter && haystack.includes(query.trim().toLocaleLowerCase('tr'));
  });
  function labelFor(item: any): string {
    return String(item?.id || 'kimliksiz-yetenek').replace(/^(sensor|tool|agent|capability)\./, '').replace(/[._-]+/g, ' ');
  }
</script>
<section class="atlas" aria-label="Yetenek envanteri">
  <header class="atlas-head">
    <div><p class="eyebrow">CANLI KAYIT DEFTERİ</p><h2>Yetenek Atlası</h2><p class="sub">Durumlar doğrudan sunucunun /api/telemetry yanıtından gelir.</p></div>
    <div class="total"><strong>{capabilities.length}</strong><span>kayıt</span></div>
  </header>
  {#if !telemetry}
    <div class="empty"><span class="pulse"></span> Telemetri bekleniyor. Sunucu yanıtı alınamadığında eski durum gösterilmez.</div>
  {:else if capabilities.length === 0}
    <div class="empty">Sunucu yetenek tablosu döndürmedi. Bu, tüm yeteneklerin kapalı olduğu anlamına gelmez; kayıt verisi şu anda mevcut değil.</div>
  {:else}
    <div class="metrics">
      <div class="metric"><strong>{readyCount}</strong><span>Hazır</span></div>
      <div class="metric blocked"><strong>{blockedCount}</strong><span>Kapalı</span></div>
      <div class="metric"><strong>{capabilities.length - readyCount - blockedCount}</strong><span>Belirsiz</span></div>
    </div>
    <div class="tools">
      <input aria-label="Yetenek ara" bind:value={query} placeholder="Yetenek veya neden ara..." />
      <div class="filters" role="group" aria-label="Yetenek durumu">
        <button class:chosen={filter === 'all'} on:click={() => filter = 'all'}>Tümü</button>
        <button class:chosen={filter === 'ready'} on:click={() => filter = 'ready'}>Hazır</button>
        <button class:chosen={filter === 'blocked'} on:click={() => filter = 'blocked'}>Kapalı</button>
      </div>
    </div>
    <div class="cap-list">
      {#each visibleCapabilities as item, index (index)}
        <article class:off={item?.available === false} class="cap-row">
          <div class="cap-main">
            <span class:good={item?.available === true} class:bad={item?.available === false} class="state-dot"></span>
            <div class="cap-name"><strong>{labelFor(item)}</strong><small>{item?.id || 'Kimlik sunulmadı'}{#if item?.kind} · {item.kind}{/if}</small></div>
            <span class="state-label">{item?.available === true ? 'HAZIR' : item?.available === false ? 'KAPALI' : 'BİLİNMİYOR'}</span>
          </div>
          {#if item?.available === false}
            <p class="reason">{item?.reason || item?.policy_reason || 'Sunucu kapalı olma nedenini bildirmedi.'}</p>
          {:else if item?.available !== true}
            <p class="reason">Sunucu bu kayıt için kesin bir kullanılabilirlik durumu bildirmedi.</p>
          {:else if item?.policy_reason}
            <p class="reason">{item.policy_reason}</p>
          {/if}
        </article>
      {/each}
      {#if visibleCapabilities.length === 0}<div class="empty">Bu aramayla eşleşen kayıt yok.</div>{/if}
    </div>
    <footer class="atlas-foot">Son alınan sunucu verisi gösteriliyor. Arayüz kendi başına yetenek etkinleştirmez.</footer>
  {/if}
</section>
<style>
  .atlas{margin-top:12px;padding:15px;border:1px solid rgba(190,164,111,.2);border-radius:13px;background:linear-gradient(145deg,rgba(24,25,27,.96),rgba(10,11,13,.98));color:#e8e2d5;font-family:inherit;box-shadow:0 12px 34px rgba(0,0,0,.2)}
  .atlas-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.eyebrow{margin:0 0 5px;color:#b99d68;font-size:9px;letter-spacing:.18em;font-weight:800}
  h2{margin:0;font-size:17px;letter-spacing:.02em;font-weight:650}.sub{margin:5px 0 0;color:#8e8b83;font-size:10px;line-height:1.45}
  .total{display:flex;align-items:baseline;gap:5px;color:#aaa18f}.total strong{font-size:25px;color:#d8c49a}.total span{font-size:10px}
  .metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:13px 0}.metric{padding:9px 10px;border:1px solid rgba(190,164,111,.14);border-radius:8px;background:rgba(255,255,255,.025)}
  .metric strong{display:block;color:#c9b17f;font-size:18px;font-variant-numeric:tabular-nums}.metric span{font-size:9px;color:#8d8b85;text-transform:uppercase;letter-spacing:.1em}.metric.blocked strong{color:#d38b79}
  .tools{display:grid;gap:8px;margin:12px 0}input{width:100%;box-sizing:border-box;padding:9px 11px;border:1px solid rgba(190,164,111,.2);border-radius:7px;background:#0b0c0e;color:#eee7d9;font:inherit;font-size:11px;outline:none}
  input:focus{border-color:#b99d68;box-shadow:0 0 0 2px rgba(185,157,104,.12)}.filters{display:flex;gap:5px}
  button{padding:6px 10px;border:1px solid rgba(190,164,111,.18);border-radius:6px;background:#111214;color:#aaa18f;font:inherit;font-size:9px;cursor:pointer}
  button.chosen{border-color:rgba(201,177,127,.55);background:rgba(185,157,104,.12);color:#e0cca1}
  .cap-list{display:grid;gap:6px;max-height:340px;overflow:auto;padding-right:2px}.cap-row{padding:9px 10px;border:1px solid rgba(190,164,111,.12);border-radius:8px;background:rgba(255,255,255,.018)}
  .cap-row.off{border-color:rgba(190,120,100,.16)}.cap-main{display:flex;align-items:center;gap:8px;min-width:0}
  .state-dot{width:7px;height:7px;flex:0 0 7px;border-radius:50%;background:#777}.state-dot.good{background:#8eaa8b;box-shadow:0 0 9px rgba(142,170,139,.45)}.state-dot.bad{background:#bd7768}
  .cap-name{display:grid;gap:2px;min-width:0;flex:1}.cap-name strong{font-size:11px;text-transform:capitalize;color:#ddd4c2;font-weight:650}.cap-name small{font-size:9px;color:#77766f;overflow-wrap:anywhere}
  .state-label{font-size:8px;letter-spacing:.1em;color:#a69b84;white-space:nowrap}.off .state-label{color:#c48677}
  .reason{margin:7px 0 0 15px;color:#a49b8d;font-size:10px;line-height:1.45}.empty{padding:14px 10px;border:1px dashed rgba(190,164,111,.2);border-radius:8px;color:#9c9589;font-size:10px;line-height:1.5}
  .pulse{display:inline-block;width:6px;height:6px;margin-right:7px;border-radius:50%;background:#b99d68}.atlas-foot{margin-top:10px;color:#77756e;font-size:9px;line-height:1.4}
  @media(max-width:420px){.atlas{padding:11px}.sub{max-width:230px}.cap-list{max-height:280px}}
</style>
