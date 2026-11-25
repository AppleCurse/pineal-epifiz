<script lang="ts">
  import { apiFetch } from '../store';
  export let clientId = 'default';
  let domain = '';
  let modes = ['harvester', 'seo', 'people'];
  let limit = 200;
  let status: any = null;
  let result: any = null;
  let busy = false;
  let error = '';
  const modeLabels: Record<string,string> = { harvester: 'Açık kaynak varlıkları', seo: 'SEO ve web görünürlüğü', people: 'Kişi / ekip sinyalleri' };
  async function loadStatus() {
    try { const r = await apiFetch('/api/company/status'); if (!r.ok) throw new Error('HTTP ' + r.status); status = await r.json(); }
    catch (e: any) { status = null; error = e?.message || 'Kurum yetenek durumu okunamadı.'; }
  }
  async function scan() {
    if (busy || !domain.trim() || !modes.length) return;
    busy = true; error = ''; result = null;
    try {
      const r = await apiFetch('/api/company/scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ domain: domain.trim(), client_id: clientId || 'default', modes, limit }) });
      const data = await r.json().catch(() => ({})); result = data;
      if (!r.ok) throw new Error(data?.error?.message || data?.detail || 'HTTP ' + r.status);
    } catch (e: any) { error = e?.message || 'Kurum taraması tamamlanamadı.'; }
    finally { busy = false; }
  }
</script>
<section class="company-workspace" aria-label="Kurum ve şirket taraması">
  <header><div><span class="kicker">PINEAL · KURUMSAL İSTİHBARAT</span><h2>Şirket / Domain İnceleme</h2><p>Alan adı üzerinden üç yetenek hattını ayrı ayrı çalıştır.</p></div><button on:click={loadStatus}>YETENEK DURUMU</button></header>
  {#if status}
    <div class="cap-status"><span>Kapı: {status.gate}</span><span>{status.any_available ? 'En az bir mod kullanılabilir görünüyor' : 'Kullanılabilir mod bildirilmedi'}</span></div>
    <div class="mode-status">{#each status.modes || [] as item}<div><strong>{modeLabels[item.mode] || item.mode}</strong><span class:yes={item.available}>{item.available ? 'KULLANILABİLİR' : 'KAPALI'}</span><small>{item.reason || 'Sunucu gerekçe bildirmedi'}</small></div>{/each}</div>
  {/if}
  <div class="scan-form"><label>ALAN ADI<input bind:value={domain} placeholder="ornek.com" /></label><label>KANIT SINIRI<input type="number" min="1" max="1000" bind:value={limit} /></label></div>
  <div class="mode-picks">{#each Object.entries(modeLabels) as [id,label]}<label><input type="checkbox" checked={modes.includes(id)} on:change={(e) => modes = e.currentTarget.checked ? [...modes,id] : modes.filter(x => x !== id)} />{label}</label>{/each}</div>
  <button class="run" on:click={scan} disabled={busy || !domain.trim() || !modes.length}>{busy ? 'TARAMA SÜRÜYOR…' : 'KURUM TARAMASINI BAŞLAT'}</button>
  {#if error}<p class="error" role="alert">{error}</p>{/if}
  {#if result}
    <div class="result-head"><strong>{result.domain || domain}</strong><span>{result.evidence_total ?? 0} kayıt döndü</span></div>
    <div class="results">{#each Object.entries(result.modes || {}) as [id, data]}<article><strong>{modeLabels[id] || id}</strong><span>{data.available ? 'KULLANILABİLİR' : 'KULLANILAMADI'}</span><small>{data.reason || data.denied_by || (data.available ? 'Motor yanıt verdi' : 'Gerekçe bildirilmedi')}</small><small>{data.counts?.evidence ?? 0} kanıt</small>{#if data.evidence?.length}<pre>{data.evidence.map((x: any) => x.content).join('\n\n')}</pre>{/if}</article>{/each}</div>
  {/if}
  <footer>Sunucunun kapı ve yetenek kararları esas alınır. Boş sonuç, taranan kurumda bilgi bulunmadığının kesin kanıtı değildir.</footer>
</section>
<style>
  .company-workspace{width:min(1500px,calc(100% - 28px));margin:0 auto 28px;padding:20px;color:#e9e3d7;background:linear-gradient(145deg,#151719,#090a0c);border:1px solid rgba(190,164,111,.2);border-radius:15px;box-shadow:0 20px 55px rgba(0,0,0,.22);font-family:inherit}
  header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.kicker{font-size:9px;letter-spacing:.2em;color:#bda36e;font-weight:800}h2{font-size:19px;margin:5px 0}header p{font-size:10px;color:#89857c;margin:0}
  button{padding:9px 12px;border:1px solid rgba(201,177,127,.4);border-radius:6px;background:rgba(185,157,104,.1);color:#d8c49a;font-size:9px;font-weight:800;cursor:pointer}.cap-status{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;margin:12px 0;padding:9px;border:1px solid rgba(190,164,111,.12);border-radius:6px;color:#9c927f;font-size:9px}
  .mode-status{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.mode-status div,.results article{display:flex;flex-direction:column;gap:5px;padding:10px;border:1px solid rgba(190,164,111,.12);border-radius:7px;background:rgba(255,255,255,.018);min-width:0}
  .mode-status strong,.results strong{font-size:10px;color:#d5c6a5}.mode-status span,.results span{font-size:8px;color:#c58b7d}.mode-status span.yes{color:#9db49b}.mode-status small,.results small{font-size:8px;color:#817c72;overflow-wrap:anywhere}
  .scan-form{display:grid;grid-template-columns:1fr 130px;gap:8px;margin-top:14px}.scan-form label{font-size:9px;color:#bca575;letter-spacing:.1em}.scan-form input{box-sizing:border-box;width:100%;margin-top:5px;padding:9px;border:1px solid rgba(190,164,111,.18);border-radius:6px;background:#08090b;color:#eee8dc;font:inherit;font-size:10px}
  .mode-picks{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0}.mode-picks label{display:flex;align-items:center;gap:5px;color:#a9a194;font-size:9px}.run{width:100%;margin-top:5px;background:#b99d68;color:#15120c}.run:disabled{opacity:.45}
  .error{color:#e19a8b;font-size:10px}.result-head{display:flex;justify-content:space-between;gap:8px;margin:14px 0 7px;color:#c8b68e;font-size:10px}.results{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.results pre{max-height:190px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:8px;color:#bcb4a7}.company-workspace footer{margin-top:12px;color:#77736b;font-size:9px;line-height:1.5}
  @media(max-width:760px){.company-workspace{width:calc(100% - 16px);padding:12px}.mode-status,.results{grid-template-columns:1fr}.scan-form{grid-template-columns:1fr}header{flex-direction:column}}
</style>
