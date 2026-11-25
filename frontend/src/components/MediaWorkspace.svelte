<script lang="ts">
  import { apiFetch } from '../store';
  export let clientId = 'default';
  let source = '';
  let modes = ['fetch', 'frames', 'transcript'];
  let sampleEvery = 5;
  let topK = 3;
  let status: any = null;
  let result: any = null;
  let busy = false;
  let error = '';
  const labels: Record<string,string> = { fetch: 'Kaynağı getir', frames: 'Kareleri incele', transcript: 'Konuşmayı yazıya dök', similarity: 'Benzerlik analizi' };
  async function loadStatus() {
    try { const r = await apiFetch('/api/media/status'); if (!r.ok) throw new Error('HTTP ' + r.status); status = await r.json(); }
    catch (e: any) { status = null; error = e?.message || 'Medya motoru durumu okunamadı.'; }
  }
  async function analyze() {
    if (busy || !source.trim() || !modes.length) return;
    busy = true; error = ''; result = null;
    try {
      const r = await apiFetch('/api/media/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source: source.trim(), client_id: clientId || 'default', modes, sample_every: sampleEvery, top_k: topK }) });
      const data = await r.json().catch(() => ({})); result = data;
      if (!r.ok) throw new Error(data?.error?.message || data?.detail || 'HTTP ' + r.status);
    } catch (e: any) { error = e?.message || 'Medya analizi tamamlanamadı.'; }
    finally { busy = false; }
  }
</script>
<section class="media-workspace" aria-label="Medya ve konuşma analizi">
  <header><div><span class="kicker">PINEAL · MEDYA ADLİ HATTI</span><h2>Medya Laboratuvarı</h2><p>Kaynak, kare, konuşma ve benzerlik modlarını ayrı ayrı çalıştır.</p></div><button on:click={loadStatus}>MOTOR DURUMU</button></header>
  {#if status}
    <div class="status-strip"><span>{status.gate}</span><span>{status.any_available ? 'En az bir mod hazır' : 'Hazır mod bildirilmedi'}</span><span>FFmpeg: {status.tools?.ffmpeg ? 'Var' : 'Yok'}</span><span>yt-dlp: {status.tools?.['yt-dlp'] ? 'Var' : 'Yok'}</span><span>OpenCV: {status.tools?.opencv ? 'Var' : 'Yok'}</span></div>
    <div class="mode-status">{#each status.modes || [] as item}<div><strong>{labels[item.mode] || item.mode}</strong><span class:yes={item.available}>{item.available ? 'HAZIR' : 'KAPALI'}</span><small>{item.reason || 'Gerekçe bildirilmedi'}</small></div>{/each}</div>
  {/if}
  <label class="source-label">MEDYA KAYNAĞI<input bind:value={source} placeholder="https://... veya sunucunun erişebildiği dosya yolu" /></label>
  <div class="mode-picks">{#each Object.entries(labels) as [id,label]}<label><input type="checkbox" checked={modes.includes(id)} on:change={(e) => modes = e.currentTarget.checked ? [...modes,id] : modes.filter(x => x !== id)} />{label}</label>{/each}</div>
  <div class="params"><label>Kare aralığı (saniye)<input type="number" min="1" max="120" bind:value={sampleEvery} /></label><label>En yakın eşleşme sayısı<input type="number" min="1" max="20" bind:value={topK} /></label></div>
  <button class="run" on:click={analyze} disabled={busy || !source.trim() || !modes.length}>{busy ? 'ANALİZ SÜRÜYOR…' : 'MEDYA ANALİZİNİ BAŞLAT'}</button>
  {#if error}<p class="error" role="alert">{error}</p>{/if}
  {#if result?.modes}
    <div class="results">{#each Object.entries(result.modes as Record<string, any>) as [id, data]}<article><strong>{labels[id] || id}</strong><span class:yes={data.available}>{data.available ? 'KULLANILABİLİR' : 'KULLANILAMADI'}</span><small>{data.reason || data.denied_by || 'Gerekçe bildirilmedi'}</small>{#each data.evidence || [] as ev}<p><b>{ev.epistemic_type || 'Kayıt'}</b> · {ev.content}</p>{/each}</article>{/each}</div>
  {/if}
  {#if result}<div class="result-total">{result.evidence_total ?? 0} kanıt satırı döndü</div>{/if}\n  <footer>Motor ve politika kapıları sunucuda uygulanır. Bir mod kapalıysa sonuç varmış gibi gösterilmez; boş çıktı, kaynağın içeriği hakkında kesin hüküm değildir.</footer>
</section>
<style>
  .media-workspace{width:min(1500px,calc(100% - 28px));margin:0 auto 28px;padding:20px;color:#e9e3d7;background:linear-gradient(145deg,#151719,#090a0c);border:1px solid rgba(190,164,111,.2);border-radius:15px;box-shadow:0 20px 55px rgba(0,0,0,.22);font-family:inherit}
  header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.kicker{font-size:9px;letter-spacing:.2em;color:#bda36e;font-weight:800}h2{font-size:19px;margin:5px 0}header p{font-size:10px;color:#89857c;margin:0}button{padding:9px 12px;border:1px solid rgba(201,177,127,.4);border-radius:6px;background:rgba(185,157,104,.1);color:#d8c49a;font-size:9px;font-weight:800;cursor:pointer}
  .status-strip{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0;padding:9px;border:1px solid rgba(190,164,111,.12);border-radius:6px;color:#a99d87;font-size:8px}.mode-status{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin-bottom:12px}.mode-status div,.results article{display:flex;flex-direction:column;gap:5px;padding:9px;border:1px solid rgba(190,164,111,.12);border-radius:7px;background:rgba(255,255,255,.018);min-width:0}.mode-status strong,.results strong{font-size:9px;color:#d5c6a5}.mode-status span,.results span{font-size:8px;color:#c58b7d}.mode-status span.yes,.results span.yes{color:#9db49b}.mode-status small,.results small{font-size:8px;color:#817c72;overflow-wrap:anywhere}
  .source-label{display:block;color:#bca575;font-size:9px;letter-spacing:.1em}.source-label input,.params input{box-sizing:border-box;width:100%;margin-top:5px;padding:9px;border:1px solid rgba(190,164,111,.18);border-radius:6px;background:#08090b;color:#eee8dc;font:inherit;font-size:10px}.mode-picks{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0}.mode-picks label{display:flex;align-items:center;gap:5px;color:#aaa194;font-size:9px}
  .params{display:grid;grid-template-columns:1fr 1fr;gap:8px}.params label{font-size:9px;color:#bca575}.run{width:100%;margin-top:12px;background:#b99d68;color:#15120c}.run:disabled{opacity:.45}.error{font-size:10px;color:#e19a8b}.results{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px}.results p{font-size:9px;color:#bdb6aa;line-height:1.5;margin:3px 0;overflow-wrap:anywhere}.media-workspace footer{margin-top:12px;color:#77736b;font-size:9px;line-height:1.5}
  @media(max-width:800px){.media-workspace{width:calc(100% - 16px);padding:12px}.mode-status,.results{grid-template-columns:1fr}header{flex-direction:column}.params{grid-template-columns:1fr}}
</style>
