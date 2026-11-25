<script lang="ts">
  import { apiFetch } from '../store';
  export let clientId = 'default';

  type Mode = 'aspasia' | 'lilith' | 'hook';
  let mode: Mode = 'aspasia';
  let prompt = '';
  let target = '';
  let busy = false;
  let error = '';
  let result: any = null;
  let history: Array<{ role: string; text: string }> = [];

  const suggestions: Record<Mode, string[]> = {
    aspasia: ['Bu fikri stratejik açıdan değerlendir.', 'Varsayımları ve kanıt boşluklarını ayır.', 'Uygulanabilir bir karar planı çıkar.'],
    lilith: ['Bu fikri etik büyüme stratejisine dönüştür.', 'Hedef kitleye uygun, sahici bir iletişim yaklaşımı üret.', 'Üç farklı yaratıcı açılış öner.'],
    hook: ['Ortak ilgi alanlarına dayalı, kısa ve saygılı bir ilk temas yaz.', 'İş birliği için net ve profesyonel bir açılış hazırla.', 'Entelektüel bir konu üzerinden doğal bir soru oluştur.']
  };

  async function run() {
    const instruction = prompt.trim();
    if (!instruction || busy) return;
    busy = true;
    error = '';
    result = null;
    history = [...history, { role: 'Sen', text: instruction }];
    try {
      let response: Response;
      if (mode === 'aspasia') {
        response = await apiFetch('/api/aspasia/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ client_id: clientId || 'default', user_message: instruction })
        });
      } else if (mode === 'lilith') {
        response = await apiFetch('/api/lilith/strategy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: clientId || 'default',
            instruction,
            target_username: target.trim() || undefined,
            intent: 'authentic_connection'
          })
        });
      } else {
        response = await apiFetch('/api/hook/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: clientId || 'default',
            intent: 'authentic_connection',
            custom_goal: instruction,
            target_username: target.trim() || undefined
          })
        });
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.error?.message || data?.detail || `HTTP ${response.status}`);
      result = data;
      const reply = mode === 'aspasia'
        ? (data.message || data.reply || data.response || JSON.stringify(data, null, 2))
        : mode === 'lilith'
          ? [data.lilith?.opening_hook, data.shadow?.strategy, data.shadow?.message, data.hook_studio?.opening_message, ...(data.counter_moves || []).map((x: any) => x.our_counter_move)].filter(Boolean).join('\n\n') || JSON.stringify(data, null, 2)
          : [data.opening_message, data.rationale, ...(data.dialogue_tree || []).map((x: any) => `${x.scenario}: ${x.our_counter_move}`)].filter(Boolean).join('\n\n') || JSON.stringify(data, null, 2);
      history = [...history, { role: mode === 'aspasia' ? 'Aspasia' : mode === 'lilith' ? 'Lilith' : 'Kanca Stüdyosu', text: reply }];
      prompt = '';
    } catch (e: any) {
      error = e?.message || 'İstek tamamlanamadı.';
    } finally {
      busy = false;
    }
  }

  function copyResult() {
    const text = mode === 'aspasia'
      ? (result?.message || result?.reply || result?.response || JSON.stringify(result, null, 2))
      : JSON.stringify(result, null, 2);
    if (text && typeof navigator !== 'undefined' && navigator.clipboard) void navigator.clipboard.writeText(text);
  }
</script>

<section id="strategy" class="sovereign-studio" aria-label="Strateji çalışma alanları">
  <header class="studio-head">
    <div><span class="kicker">PINEAL · ÇALIŞMA ALANLARI</span><h2>Strateji Stüdyosu</h2><p>Mevcut API uçlarına bağlı üç ayrı çalışma masası. Yanıtlar sunucudan gelir.</p></div>
    <span class="studio-mark">01 / 03</span>
  </header>
  <nav class="mode-tabs" aria-label="Çalışma alanı seçimi">
    <button class:active={mode === 'aspasia'} on:click={() => { mode = 'aspasia'; result = null; }}> <b>01</b><span>Aspasia</span><small>Strateji ve muhakeme</small></button>
    <button class:active={mode === 'lilith'} on:click={() => { mode = 'lilith'; result = null; }}> <b>02</b><span>Lilith</span><small>Büyüme ve karşı-hamle</small></button>
    <button class:active={mode === 'hook'} on:click={() => { mode = 'hook'; result = null; }}> <b>03</b><span>İlk Temas</span><small>Üç dallı diyalog taslağı</small></button>
  </nav>
  <div class="studio-body">
    <div class="studio-context">
      <label>HEDEF / KULLANICI ADI <input bind:value={target} placeholder="İsteğe bağlı kullanıcı adı" /></label>
      <div class="privacy-note">Yalnızca gerekli bilgiyi gir. Başka bir kişinin özel veya hassas verilerini izinsiz ekleme. İlk temas taslakları saygılı iletişim amacıyla üretilir.</div>
      <div class="suggestions"><span>HIZLI BAŞLANGIÇ</span>{#each suggestions[mode] as item}<button on:click={() => prompt = item}>{item}</button>{/each}</div>
    </div>
    <div class="studio-conversation">
      <div class="history">
        {#if history.length === 0}<div class="empty-state"><span>◇</span><strong>Çalışma alanı hazır</strong><small>Bir talimat gir veya hızlı başlangıçlardan birini seç.</small></div>{/if}
        {#each history.slice(-8) as item, i}
          <article class:answer={item.role !== 'Sen'}><small>{item.role}</small><p>{item.text}</p></article>
        {/each}
      </div>
      <form on:submit|preventDefault={run}>
        <textarea bind:value={prompt} rows="3" placeholder={mode === 'aspasia' ? 'Sorunu, fikrini veya kararını yaz...' : 'İstenen stratejiyi açıkça tarif et...'}></textarea>
        <button type="submit" disabled={busy || !prompt.trim()}>{busy ? 'İŞLENİYOR…' : 'ÇALIŞTIR  ↗'}</button>
      </form>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      {#if result}
        <details class="raw-result"><summary>Sunucudan gelen ham yanıtı görüntüle</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>
      {/if}
    </div>
  </div>
  <footer>Bu alan öneri ve taslak üretir. Çıktılar doğrulanmış olgu veya karşı tarafın niyetine dair kanıt sayılmaz.</footer>
</section>

<style>
  .sovereign-studio{margin:18px auto 26px;width:min(1500px,calc(100% - 28px));color:#e9e3d7;background:radial-gradient(ellipse at 85% 0%,rgba(150,119,65,.12),transparent 38%),linear-gradient(145deg,#151618,#090a0c 72%);border:1px solid rgba(190,164,111,.22);border-radius:16px;overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,.28);font-family:inherit}
  .studio-head{display:flex;justify-content:space-between;align-items:flex-start;padding:22px 24px 16px;border-bottom:1px solid rgba(190,164,111,.13)}.kicker{font-size:9px;letter-spacing:.2em;color:#bda36e;font-weight:800}
  h2{font-size:22px;margin:6px 0 4px;letter-spacing:-.02em}.studio-head p{font-size:11px;color:#8f8b82;margin:0}.studio-mark{font-size:10px;color:#7c7465;letter-spacing:.14em}
  .mode-tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:12px 18px;border-bottom:1px solid rgba(190,164,111,.12)}
  .mode-tabs button{display:grid;grid-template-columns:28px 1fr;grid-template-rows:auto auto;gap:3px 8px;text-align:left;padding:11px 12px;border:1px solid rgba(190,164,111,.14);border-radius:9px;background:rgba(255,255,255,.02);color:#a9a397;cursor:pointer}
  .mode-tabs b{grid-row:1/3;align-self:center;color:#a58c5d;font-size:11px}.mode-tabs span{font-size:12px;font-weight:750;color:#ddd4c2}.mode-tabs small{font-size:9px;color:#77756e}
  .mode-tabs button.active{background:rgba(185,157,104,.1);border-color:rgba(201,177,127,.52);box-shadow:inset 0 0 20px rgba(185,157,104,.04)}.mode-tabs button.active span{color:#e7d3a7}
  .studio-body{display:grid;grid-template-columns:minmax(210px,.7fr) minmax(0,1.7fr);gap:16px;padding:18px}
  .studio-context{display:flex;flex-direction:column;gap:12px}.studio-context label{font-size:9px;letter-spacing:.1em;color:#bca575;font-weight:800}
  input,textarea{box-sizing:border-box;width:100%;margin-top:7px;padding:10px 11px;border:1px solid rgba(190,164,111,.2);border-radius:7px;background:#08090b;color:#eee8dc;font:inherit;font-size:11px;outline:none}
  input:focus,textarea:focus{border-color:#b99d68;box-shadow:0 0 0 2px rgba(185,157,104,.1)}
  .privacy-note{font-size:10px;line-height:1.5;color:#89857c;padding:10px;border-left:2px solid #9e8556;background:rgba(185,157,104,.05)}
  .suggestions{display:grid;gap:6px}.suggestions>span{font-size:8px;letter-spacing:.16em;color:#77756e;font-weight:800}
  .suggestions button{padding:8px 9px;text-align:left;border:1px solid rgba(190,164,111,.12);border-radius:6px;background:transparent;color:#aaa397;font:inherit;font-size:10px;cursor:pointer}.suggestions button:hover{border-color:#9f8659;color:#e1d4b9}
  .studio-conversation{min-width:0;border:1px solid rgba(190,164,111,.14);border-radius:10px;background:rgba(0,0,0,.2);padding:12px}
  .history{display:flex;flex-direction:column;gap:8px;min-height:180px;max-height:380px;overflow:auto}
  .history article{padding:9px 11px;border-radius:7px;background:rgba(255,255,255,.025);border-left:2px solid #9a8357}.history article.answer{border-left-color:#7d9b89;background:rgba(125,155,137,.045)}
  .history article small{font-size:8px;letter-spacing:.12em;text-transform:uppercase;color:#b99d68}.history article p{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;line-height:1.55;color:#d5d0c6;margin:5px 0 0}
  .empty-state{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:180px;color:#77756e;gap:7px}.empty-state span{font-size:27px;color:#a88e5b}.empty-state strong{font-size:12px;color:#c9c0af}.empty-state small{font-size:10px}
  form{display:grid;grid-template-columns:1fr auto;align-items:end;gap:8px;margin-top:12px}form textarea{resize:vertical;min-height:74px;margin:0}form>button{height:42px;padding:0 17px;border:1px solid rgba(201,177,127,.55);border-radius:7px;background:linear-gradient(135deg,#c1a36b,#8d7042);color:#17130c;font-size:10px;font-weight:900;letter-spacing:.1em;cursor:pointer}form>button:disabled{opacity:.45;cursor:not-allowed}
  .error{color:#e29a8b;font-size:10px;margin:8px 0 0}.raw-result{margin-top:10px;color:#b9a77e;font-size:10px}.raw-result pre{max-height:220px;overflow:auto;padding:10px;background:#08090b;color:#c8c2b5;font-size:9px;white-space:pre-wrap;overflow-wrap:anywhere}
  footer{padding:10px 20px;border-top:1px solid rgba(190,164,111,.1);font-size:9px;color:#77736b}
  @media(max-width:760px){.sovereign-studio{width:calc(100% - 16px);margin:12px auto 20px}.studio-head{padding:16px}.studio-body{grid-template-columns:1fr;padding:12px}.mode-tabs{padding:9px;gap:5px}.mode-tabs button{padding:9px 7px;grid-template-columns:1fr}.mode-tabs b{display:none}.mode-tabs span{font-size:10px}.mode-tabs small{font-size:8px}form{grid-template-columns:1fr}form>button{height:40px}}
</style>
