<script lang="ts">
  import { onDestroy } from 'svelte';
  import { apiFetch } from '../store';
  export let clientId = 'default';
  let url = '';
  let typedText = '';
  let x = '640';
  let y = '360';
  let key = 'Enter';
  let busy = false;
  let message = '';
  let state: any = null;
  let screenshot = '';
  let shotUrl = '';

  onDestroy(() => { if (shotUrl) URL.revokeObjectURL(shotUrl); });

  async function request(path: string, body?: Record<string, any>) {
    const response = await apiFetch(path, body ? {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ client_id: clientId || 'default', ...body })
    } : {});
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data?.error?.message || data?.detail || `HTTP ${response.status}`);
    }
    return response;
  }

  async function run(action: () => Promise<void>) {
    if (busy) return;
    busy = true; message = '';
    try { await action(); }
    catch (e: any) { message = e?.message || 'Tarayıcı işlemi başarısız.'; }
    finally { busy = false; }
  }

  function updateState(data: any) { state = data; }
  function openPage() {
    return run(async () => { const r = await request('/api/browser/open', { url: url.trim() }); updateState(await r.json()); await fetchShotDirect(); });
  }
  function refreshState() {
    return run(async () => { const r = await request(`/api/browser/state?client_id=${encodeURIComponent(clientId || 'default')}`); updateState(await r.json()); });
  }
  async function fetchShotDirect() {
    const r = await request(`/api/browser/shot?client_id=${encodeURIComponent(clientId || 'default')}`);
    const next = URL.createObjectURL(await r.blob());
    if (shotUrl) URL.revokeObjectURL(shotUrl);
    shotUrl = next; screenshot = next;
  }
  function takeShot() { return run(fetchShotDirect); }
  function back() { return run(async () => { const r = await request('/api/browser/back', {}); updateState(await r.json()); await fetchShotDirect(); }); }
  function saveSession() {
    return run(async () => {
      const r = await request('/api/browser/save', {});
      const data = await r.json();
      message = data?.saved ? 'Instagram oturumu kasaya kaydedildi.' : (data?.hint || 'Kaydedilecek oturum bulunamadı.');
      await refreshStateDirect();
    });
  }
  async function refreshStateDirect() {
    const r = await request(`/api/browser/state?client_id=${encodeURIComponent(clientId || 'default')}`);
    updateState(await r.json());
  }
  function closeBrowser() {
    return run(async () => { const r = await request('/api/browser/close', {}); updateState(await r.json().catch(() => ({}))); if (shotUrl) URL.revokeObjectURL(shotUrl); shotUrl=''; screenshot=''; });
  }
  function typeIntoPage() {
    return run(async () => { const r = await request('/api/browser/type', { text: typedText }); updateState(await r.json()); typedText=''; });
  }
  function pressKey() { return run(async () => { const r = await request('/api/browser/press', { key }); updateState(await r.json()); await fetchShotDirect(); }); }
  function clickPoint() { return run(async () => { const r = await request('/api/browser/click', { x: Number(x), y: Number(y) }); updateState(await r.json()); await fetchShotDirect(); }); }
</script>

<section class="browser-workspace" aria-label="Canlı tarayıcı çalışma alanı">
  <header><div><span class="kicker">PINEAL · ETKİLEŞİMLİ OTURUM</span><h2>Canlı Tarayıcı</h2><p>Instagram ve Google giriş alanında sunucu tarayıcısını aç, görüntüle ve kontrollü biçimde kullan.</p></div><span class="lock-note">KASA + ÇOCUK KİLİDİNE TABİ</span></header>
  <div class="browser-toolbar">
    <input bind:value={url} placeholder="https://www.instagram.com/accounts/login/" aria-label="Açılacak adres" />
    <button class="primary" on:click={openPage} disabled={busy || !url.trim()}>AÇ</button>
    <button on:click={refreshState} disabled={busy}>DURUM</button><button on:click={saveSession} disabled={busy}>OTURUMU KASAYA KAYDET</button><button on:click={takeShot} disabled={busy}>GÖRÜNTÜ</button><button on:click={back} disabled={busy}>GERİ</button><button class="close" on:click={closeBrowser} disabled={busy}>KAPAT</button>
  </div>
  {#if message}<p class="notice" role="alert">{message}</p>{/if}
  <div class="browser-grid">
    <div class="screen">
      {#if screenshot}<img src={screenshot} alt="Sunucu tarayıcısının anlık ekran görüntüsü" />
      {:else}<div class="screen-empty"><span>⌘</span><strong>Tarayıcı görüntüsü henüz alınmadı</strong><small>Adres açıldığında veya Görüntü düğmesine basıldığında sunucu ekranı burada görünür.</small></div>{/if}
      <div class="screen-foot">{state?.url || state?.current_url || 'Oturum adresi henüz bilinmiyor'} {#if state?.title} · {state.title}{/if}</div>
    </div>
    <aside class="browser-controls">
      <div class="state-card"><small>OTURUM DURUMU</small><strong>{state ? (state.live === true ? 'AÇIK' : state.live === false ? 'KAPALI' : 'YANIT ALINDI') : 'SORGULANMADI'}</strong><span>{state?.saved_session === true ? 'Kayıtlı oturum mevcut' : state?.saved_session === false ? 'Kayıtlı oturum yok' : 'Durum verisi bekleniyor'}</span></div>
      <label>Sayfaya metin yaz<input bind:value={typedText} maxlength="500" placeholder="Metin..." /></label><button on:click={typeIntoPage} disabled={busy || !typedText.trim()}>METNİ YAZ</button>
      <label>Tuş gönder<select bind:value={key}><option value="Enter">Enter</option><option value="Tab">Tab</option><option value="Escape">Escape</option><option value="Backspace">Backspace</option><option value="ArrowDown">ArrowDown</option><option value="ArrowUp">ArrowUp</option></select></label><button on:click={pressKey} disabled={busy}>TUŞA BAS</button>
      <div class="coords"><label>X<input bind:value={x} inputmode="numeric" /></label><label>Y<input bind:value={y} inputmode="numeric" /></label></div><button on:click={clickPoint} disabled={busy || !Number.isFinite(Number(x)) || !Number.isFinite(Number(y))}>KOORDİNATA TIKLA</button>
    </aside>
  </div>
  {#if busy}<p class="working">İstek sunucuya gönderiliyor…</p>{/if}
  <footer>Bu bir web sayfası gömülü önizlemesi değildir. Görüntü, backend tarayıcısından alınan gerçek ekran karesidir. Kasa kilitli veya çocuk koruması etkinse sunucu işlemi reddeder.</footer>
</section>

<style>
  .browser-workspace{width:min(1500px,calc(100% - 28px));margin:0 auto 28px;padding:20px;color:#e9e3d7;background:linear-gradient(145deg,#121416,#090a0c);border:1px solid rgba(190,164,111,.2);border-radius:15px;box-shadow:0 20px 55px rgba(0,0,0,.25);font-family:inherit}
  header{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:14px}.kicker{font-size:9px;letter-spacing:.2em;color:#bda36e;font-weight:800}h2{font-size:19px;margin:5px 0}.browser-workspace header p{font-size:10px;color:#89857c;margin:0}.lock-note{font-size:8px;color:#c6a975;border:1px solid rgba(190,164,111,.25);border-radius:5px;padding:6px 8px;white-space:nowrap}
  .browser-toolbar{display:flex;gap:6px;flex-wrap:wrap}.browser-toolbar input{flex:1;min-width:190px}.browser-workspace input,.browser-workspace select{box-sizing:border-box;padding:9px 10px;border:1px solid rgba(190,164,111,.18);border-radius:6px;background:#08090b;color:#e8e2d5;font:inherit;font-size:10px;min-width:0}
  button{padding:9px 11px;border:1px solid rgba(190,164,111,.2);border-radius:6px;background:#171819;color:#c8bdab;font:inherit;font-size:9px;font-weight:800;letter-spacing:.06em;cursor:pointer}button.primary{background:#b99d68;color:#15120c;border-color:#b99d68}button.close{color:#d58f80;border-color:rgba(190,120,100,.35)}button:disabled{opacity:.4;cursor:not-allowed}
  .browser-grid{display:grid;grid-template-columns:minmax(0,1.8fr) minmax(220px,.7fr);gap:10px;margin-top:12px}.screen{position:relative;min-height:300px;border:1px solid rgba(190,164,111,.16);border-radius:8px;background:#050607;overflow:hidden;display:flex;flex-direction:column}.screen img{display:block;width:100%;height:auto;max-height:600px;object-fit:contain}.screen-empty{flex:1;min-height:270px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;text-align:center;color:#77736b;padding:20px}.screen-empty span{font-size:28px;color:#b99d68}.screen-empty strong{font-size:12px;color:#c8bdab}.screen-empty small{max-width:340px;font-size:10px;line-height:1.5}.screen-foot{padding:7px 9px;border-top:1px solid rgba(190,164,111,.12);font-size:9px;color:#817c72;overflow-wrap:anywhere}
  .browser-controls{display:flex;flex-direction:column;gap:7px;padding:10px;border:1px solid rgba(190,164,111,.14);border-radius:8px;background:rgba(255,255,255,.015)}.browser-controls label{display:grid;gap:4px;color:#b5a47f;font-size:9px}.browser-controls label input,.browser-controls label select{width:100%;margin:0}.state-card{display:grid;gap:4px;padding:9px;border:1px solid rgba(190,164,111,.13);border-radius:6px}.state-card small{font-size:8px;color:#827d73;letter-spacing:.12em}.state-card strong{font-size:14px;color:#d5c39e}.state-card span{font-size:9px;color:#89857c}.coords{display:grid;grid-template-columns:1fr 1fr;gap:7px}.notice{margin:9px 0;color:#e0a092;font-size:10px}.working{font-size:9px;color:#b99d68}.browser-workspace footer{margin-top:12px;color:#77736b;font-size:9px;line-height:1.5}
  @media(max-width:760px){.browser-workspace{width:calc(100% - 16px);padding:12px}.browser-grid{grid-template-columns:1fr}.screen{min-height:220px}.screen-empty{min-height:200px}header{flex-direction:column}.lock-note{white-space:normal}}
</style>
