<script lang="ts">
  import { apiFetch } from '../store';
  export let clientId = 'default';
  let text = '';
  let target = 'en';
  let busy = false;
  let error = '';
  let detected: any = null;
  let translated: any = null;
  let speech: any = null;
  let voiceText = '';
  async function readJson(path: string, init?: RequestInit) {
    const r = await apiFetch(path, init);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data?.error?.message || data?.detail || 'HTTP ' + r.status);
    return data;
  }
  async function detect() {
    if (busy || !text.trim()) return;
    busy=true;error='';detected=null;
    try { detected=await readJson('/api/language/detect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text.trim(),client_id:clientId||'default'})}); }
    catch(e:any){error=e?.message||'Dil ölçülemedi.';} finally{busy=false;}
  }
  async function translate() {
    if (busy || !text.trim()) return;
    busy=true;error='';translated=null;
    try { translated=await readJson('/api/language/translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text.trim(),target,client_id:clientId||'default'})}); }
    catch(e:any){error=e?.message||'Çeviri üretilemedi.';} finally{busy=false;}
  }
  async function loadStatus() {
    busy=true;error='';
    try { const [language,speechState]=await Promise.all([readJson('/api/language/status?client_id='+encodeURIComponent(clientId||'default')),readJson('/api/speech/status')]); speech=speechState; detected=language; }
    catch(e:any){error=e?.message||'Durum okunamadı.';} finally{busy=false;}
  }
  async function speak() {
    if(busy || !voiceText.trim()) return;
    busy=true;error='';
    try { speech=await readJson('/api/speech/say',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:voiceText.trim(),client_id:clientId||'default'})}); }
    catch(e:any){error=e?.message||'Seslendirme başlatılamadı.';} finally{busy=false;}
  }
  async function stopSpeech() {
    busy=true;error='';
    try { speech=await readJson('/api/speech/stop?client_id='+encodeURIComponent(clientId||'default'),{method:'POST'}); }
    catch(e:any){error=e?.message||'Ses durdurulamadı.';} finally{busy=false;}
  }
</script>
<section class="language-voice" aria-label="Dil ve ses çalışma alanı">
  <header><div><span class="kicker">PINEAL · DİL VE SES</span><h2>Dil & Ses İstasyonu</h2><p>Dil tespiti, yerel çeviri ve sunucunun gerçek ses motoru.</p></div><button on:click={loadStatus} disabled={busy}>MOTOR DURUMU</button></header>
  <div class="language-grid">
    <article><h3>Dil ölçümü</h3><textarea bind:value={text} rows="5" placeholder="Dilini ölçmek veya çevirmek istediğin metni yaz..."></textarea><button on:click={detect} disabled={busy || !text.trim()}>DİLİ TESPİT ET</button>
      {#if detected}<div class="output"><strong>{detected.detect?.method || detected.language || detected.detect?.available ? (detected.language || 'Dil durumu alındı') : 'Ölçüm yok'}</strong><small>{detected.available === false ? (detected.reason || detected.denied_by || 'Dil ölçümü yapılamadı') : 'Güven: ' + (typeof detected.confidence === 'number' ? Math.round(detected.confidence*100)+'%' : 'belirtilmedi')}</small></div>{/if}
    </article>
    <article><h3>Yerel çeviri</h3><label>HEDEF DİL<select bind:value={target}><option value="en">İngilizce</option><option value="tr">Türkçe</option><option value="de">Almanca</option><option value="fr">Fransızca</option><option value="es">İspanyolca</option><option value="ar">Arapça</option></select></label><button on:click={translate} disabled={busy || !text.trim()}>ÇEVİRİ ÜRET</button>
      {#if translated}<div class="output"><strong>{translated.available ? 'ÇEVİRİ HAZIR' : 'ÇEVİRİ ÜRETİLEMEDİ'}</strong><p>{translated.text || translated.reason || translated.denied_by || 'Motor metin döndürmedi.'}</p><small>{translated.engine || translated.reason || ''}</small></div>{/if}
    </article>
    <article><h3>Ses motoru</h3><textarea bind:value={voiceText} rows="3" placeholder="Seslendirilecek metin..."></textarea><div class="actions"><button on:click={speak} disabled={busy || !voiceText.trim()}>SESLENDİR</button><button on:click={stopSpeech} disabled={busy}>DURDUR</button></div>
      {#if speech}<div class="output"><strong>{speech.available === true ? 'MOTOR HAZIR' : speech.available === false ? 'KULLANILAMIYOR' : speech.state || speech.status || 'DURUM ALINDI'}</strong><small>{speech.reason || speech.engine || speech.machine_note || ''}</small></div>{/if}
    </article>
  </div>
  {#if error}<p class="error" role="alert">{error}</p>{/if}
  <footer>Çeviri ucu yerel motor şartına bağlıdır; uzak çeviri servisine sessizce yönlendirme yapılmaz. Ses çalma, uygulamanın sesli yanıt anahtarı ve WebSocket bildirimi üzerinden yürür.</footer>
</section>
<style>
  .language-voice{width:min(1500px,calc(100% - 28px));margin:0 auto 28px;padding:20px;color:#e9e3d7;background:linear-gradient(145deg,#151719,#090a0c);border:1px solid rgba(190,164,111,.2);border-radius:15px;box-shadow:0 20px 55px rgba(0,0,0,.22);font-family:inherit}
  header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.kicker{font-size:9px;letter-spacing:.2em;color:#bda36e;font-weight:800}h2{font-size:19px;margin:5px 0}header p{font-size:10px;color:#89857c;margin:0}button{padding:9px 11px;border:1px solid rgba(201,177,127,.4);border-radius:6px;background:rgba(185,157,104,.1);color:#d8c49a;font-size:9px;font-weight:800;cursor:pointer}button:disabled{opacity:.4}
  .language-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:14px}.language-grid article{display:flex;flex-direction:column;gap:8px;min-width:0;padding:12px;border:1px solid rgba(190,164,111,.13);border-radius:8px;background:rgba(255,255,255,.018)}h3{font-size:11px;color:#d7c7a5;margin:0}
  textarea,select{box-sizing:border-box;width:100%;padding:9px;border:1px solid rgba(190,164,111,.18);border-radius:6px;background:#08090b;color:#eee8dc;font:inherit;font-size:10px;resize:vertical}label{font-size:8px;color:#bca575;letter-spacing:.1em}.actions{display:flex;gap:6px}.actions button{flex:1}
  .output{padding:9px;border:1px solid rgba(190,164,111,.12);border-radius:6px;background:rgba(0,0,0,.17)}.output strong{display:block;font-size:9px;color:#c7b68f}.output p{font-size:10px;line-height:1.5;color:#c7c0b4;white-space:pre-wrap;overflow-wrap:anywhere}.output small{display:block;margin-top:5px;color:#827c72;font-size:8px;line-height:1.4}.error{color:#e19a8b;font-size:10px}.language-voice footer{margin-top:12px;color:#77736b;font-size:9px;line-height:1.5}
  @media(max-width:800px){.language-voice{width:calc(100% - 16px);padding:12px}.language-grid{grid-template-columns:1fr}header{flex-direction:column}}
</style>
