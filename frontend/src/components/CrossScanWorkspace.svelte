<script lang="ts">
  import { apiFetch } from '../store';
  export let clientId = 'default';
  let username = '';
  let email = '';
  let profileUrl = '';
  let busy: string | null = null;
  let results: Record<string, any> = {};
  let errors: Record<string, string> = {};

  async function scan(kind: 'maigret' | 'holehe' | 'socid') {
    if (busy) return;
    const value = kind === 'maigret' ? username.trim() : kind === 'holehe' ? email.trim() : profileUrl.trim();
    if (!value) return;
    busy = kind; errors = { ...errors, [kind]: '' };
    try {
      const path = kind === 'maigret' ? '/api/experimental/maigret/scan' : kind === 'holehe' ? '/api/experimental/holehe/scan' : '/api/experimental/socid/extract';
      const body = kind === 'maigret' ? { username: value, client_id: clientId || 'default' } : kind === 'holehe' ? { email: value, client_id: clientId || 'default' } : { url: value, client_id: clientId || 'default' };
      const response = await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await response.json().catch(() => ({}));
      results = { ...results, [kind]: data };
      if (!response.ok) errors = { ...errors, [kind]: data?.error?.message || data?.detail || 'HTTP ' + response.status + ' · İstek işlenmedi.' };
    } catch (e: any) { errors = { ...errors, [kind]: e?.message || 'Bağlantı hatası' }; }
    finally { busy = null; }
  }

  function statusText(data: any) {
    if (!data) return 'Henüz çalıştırılmadı';
    if (data.available === true) return 'Motor yanıt verdi';
    if (data.available === false) return 'Kullanılamıyor / sonuç yok';
    return data.status || data.error?.code || 'Yanıt alındı, durum alanı yok';
  }
</script>
<section id="cross-scan" class="cross-scan" aria-label="Çapraz kaynak tarama">
  <header><div><span class="kicker">PINEAL · ÇAPRAZ KAYNAK</span><h2>Çapraz Tarama Masası</h2><p>Kullanıcı adı, e-posta ve profil adresi için ayrı motorlar.</p></div><span class="gate">KASA AÇIK OLMALI</span></header>
  <div class="scan-grid">
    <article><span class="number">01</span><h3>Kullanıcı adı · Maigret</h3><p>Herkese açık platformlardaki kullanıcı adı eşleşmelerini arar.</p><input bind:value={username} placeholder="kullanici_adi" aria-label="Kullanıcı adı" /><button on:click={() => scan('maigret')} disabled={!!busy || !username.trim()}>{busy === 'maigret' ? 'TARANIYOR…' : 'KULLANICI ADINI TARA'}</button><div class="result"><strong>{statusText(results.maigret)}</strong>{#if errors.maigret}<small class="error">{errors.maigret}</small>{:else if results.maigret}<pre>{JSON.stringify(results.maigret, null, 2)}</pre>{/if}</div></article>
    <article><span class="number">02</span><h3>E-posta · Holehe</h3><p>E-posta adresinin desteklenen servislerde kayıt sinyalini sorgular.</p><input type="email" bind:value={email} placeholder="ornek@eposta.com" aria-label="E-posta adresi" /><button on:click={() => scan('holehe')} disabled={!!busy || !email.trim()}>{busy === 'holehe' ? 'SORGULANIYOR…' : 'E-POSTAYI SORGULA'}</button><div class="result"><strong>{statusText(results.holehe)}</strong>{#if errors.holehe}<small class="error">{errors.holehe}</small>{:else if results.holehe}<pre>{JSON.stringify(results.holehe, null, 2)}</pre>{/if}</div></article>
    <article><span class="number">03</span><h3>Profil adresi · Socid</h3><p>Verilen profil adresinden yapılandırılmış kayıt çıkarmayı dener.</p><input type="url" bind:value={profileUrl} placeholder="https://www.instagram.com/..." aria-label="Profil adresi" /><button on:click={() => scan('socid')} disabled={!!busy || !profileUrl.trim()}>{busy === 'socid' ? 'ÇIKARILIYOR…' : 'PROFİLİ ÇÖZÜMLE'}</button><div class="result"><strong>{statusText(results.socid)}</strong>{#if errors.socid}<small class="error">{errors.socid}</small>{:else if results.socid}<pre>{JSON.stringify(results.socid, null, 2)}</pre>{/if}</div></article>
  </div>
  <footer>Motor kapalıysa istek başarısız olarak gösterilir. “Kayıt bulunamadı” sonucu, yalnızca motor gerçekten çalışıp bu sonucu bildirdiğinde anlamlıdır. Kasa kilidi ve reşitlik koruması sunucuda uygulanır.</footer>
</section>
<style>
  .cross-scan{width:min(1500px,calc(100% - 28px));margin:0 auto 28px;padding:20px;color:#e9e3d7;background:linear-gradient(145deg,#151719,#090a0c);border:1px solid rgba(190,164,111,.2);border-radius:15px;box-shadow:0 20px 55px rgba(0,0,0,.22);font-family:inherit}
  header{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:14px}.kicker{font-size:9px;letter-spacing:.2em;color:#bda36e;font-weight:800}h2{font-size:19px;margin:5px 0}header p{font-size:10px;color:#89857c;margin:0}.gate{font-size:8px;color:#c9b17f;border:1px solid rgba(190,164,111,.2);padding:6px 8px;border-radius:5px}
  .scan-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.scan-grid article{display:flex;flex-direction:column;min-width:0;padding:13px;border:1px solid rgba(190,164,111,.14);border-radius:9px;background:rgba(255,255,255,.018)}
  .number{font-size:9px;color:#8d7650;letter-spacing:.15em}.scan-grid h3{font-size:12px;color:#d9c9a8;margin:7px 0 4px}.scan-grid p{font-size:9px;line-height:1.5;color:#858078;min-height:28px;margin:0 0 8px}
  input{box-sizing:border-box;width:100%;padding:9px 10px;border:1px solid rgba(190,164,111,.18);border-radius:6px;background:#08090b;color:#eee8dc;font:inherit;font-size:10px;margin-bottom:7px}
  button{padding:9px 10px;border:1px solid rgba(201,177,127,.36);border-radius:6px;background:rgba(185,157,104,.1);color:#d8c49a;font-size:9px;font-weight:800;letter-spacing:.06em;cursor:pointer}button:disabled{opacity:.4;cursor:not-allowed}
  .result{margin-top:10px;padding:9px;border:1px solid rgba(190,164,111,.1);border-radius:6px;background:rgba(0,0,0,.16);min-height:60px}.result strong{font-size:9px;color:#b99d68}.result pre{max-height:190px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:8px;line-height:1.45;color:#bdb6aa;margin:7px 0 0}.error{display:block;margin-top:6px;color:#e19a8b;font-size:9px;line-height:1.4}
  .cross-scan footer{margin-top:12px;font-size:9px;color:#77736b;line-height:1.5}@media(max-width:850px){.scan-grid{grid-template-columns:1fr}}@media(max-width:600px){.cross-scan{width:calc(100% - 16px);padding:12px}header{flex-direction:column}}
</style>
