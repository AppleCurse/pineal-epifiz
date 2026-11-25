<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Icon from './Icon.svelte';
  import { apiFetch, clientId, currentApiToken, setApiToken } from '../store';

  export let open = false;
  export let initialTab: 'providers' | 'search' | 'routing' = 'providers';
  export let routingData: any = null;

  const dispatch = createEventDispatcher();
  const DIRECT_PROVIDERS = [
    { id: 'groq', label: 'Groq', placeholder: 'gsk_...' },
    { id: 'deepseek', label: 'DeepSeek', placeholder: 'sk-...' },
    { id: 'google-gemini', label: 'Google Gemini', placeholder: 'AIza...' },
    { id: 'google-gemini-backup', label: 'Google Gemini (Yedek)', placeholder: 'AIza...' },
    { id: 'mistral', label: 'Mistral AI', placeholder: '...' },
    { id: 'cerebras', label: 'Cerebras', placeholder: '...' },
    { id: 'together', label: 'Together AI', placeholder: '...' },
    { id: 'fireworks', label: 'Fireworks AI', placeholder: '...' },
    { id: 'perplexity', label: 'Perplexity', placeholder: 'pplx-...' },
    { id: 'sambanova', label: 'SambaNova', placeholder: '...' },
    { id: 'nvidia-nim', label: 'NVIDIA NIM', placeholder: 'nvapi-...' },
    { id: 'deepinfra', label: 'DeepInfra', placeholder: '...' },
    { id: 'huggingface', label: 'HuggingFace', placeholder: 'hf_...' },
    { id: 'nous-research', label: 'Nous Research', placeholder: '...' },
    { id: 'alibaba-dashscope', label: 'Alibaba DashScope', placeholder: 'sk-...' }
  ];
  const DIAGNOSTIC_PROVIDERS = [
    { id: 'anthropic', label: 'Anthropic (Tanı / OpenRouter)', placeholder: 'sk-ant-...' },
    { id: 'openai', label: 'OpenAI (Tanı / OpenRouter)', placeholder: 'sk-...' },
    { id: 'xai', label: 'xAI Grok (Tanı / OpenRouter)', placeholder: 'xai-...' },
    { id: 'cohere', label: 'Cohere (Tanı / OpenRouter)', placeholder: '...' },
    { id: 'azure-openai', label: 'Azure OpenAI (Tanı)', placeholder: '...' },
    { id: 'iflow', label: 'iFlow (Tanı)', placeholder: '...' },
    { id: 'google-gemini-vertex', label: 'Google Gemini Vertex (Tanı)', placeholder: '...' }
  ];

  let wasOpen = false;
  let settingsTab: 'providers' | 'search' | 'routing' = 'providers';
  let settingsSaving = false;
  let settingsStatusMsg = '';
  let settingsErrorMsg = '';
  let appTokenInput = currentApiToken();
  let openRouterInput = '';
  let providerInputs: Record<string, string> = Object.fromEntries(
    [...DIRECT_PROVIDERS, ...DIAGNOSTIC_PROVIDERS].map(provider => [provider.id, ''])
  );
  let localUrl = 'http://localhost:11434/v1';
  let localModel = 'dolphin-llama3:latest';
  let useLocal = false;
  let localSettingTouched = false;
  let tavilyKey = '';
  let serpapiKey = '';
  let exaKey = '';
  let xCookie = '';
  let igCookie = '';

  $: if (open && !wasOpen) {
    wasOpen = true;
    settingsTab = initialTab;
    settingsStatusMsg = '';
    settingsErrorMsg = '';
    appTokenInput = currentApiToken();
    localSettingTouched = false;
    useLocal = typeof routingData?.use_local === 'boolean' ? routingData.use_local : false;
  }
  $: if (open && !localSettingTouched && typeof routingData?.use_local === 'boolean') {
    useLocal = routingData.use_local;
  }
  $: if (!open) wasOpen = false;

  function close() {
    dispatch('close');
  }

  async function saveMultiVaultSettings() {
    if (settingsSaving) return;
    settingsSaving = true;
    settingsStatusMsg = '';
    settingsErrorMsg = '';
    try {
      if (appTokenInput !== undefined && appTokenInput.trim()) setApiToken(appTokenInput.trim());
      const cid = $clientId || 'default';
      const cleanedProviders: Record<string, string> = {};
      for (const [pid, val] of Object.entries(providerInputs)) {
        if (val && val.trim()) cleanedProviders[pid] = val.trim();
      }
      const payload: Record<string, any> = { client_id: cid, use_local: useLocal };
      if (openRouterInput.trim()) payload.api_key = openRouterInput.trim();
      if (Object.keys(cleanedProviders).length > 0) payload.provider_keys = cleanedProviders;
      if (useLocal || localUrl.trim()) payload.local_url = localUrl.trim();
      if (useLocal || localModel.trim()) payload.local_model = localModel.trim();
      if (tavilyKey.trim()) payload.tavily_key = tavilyKey.trim();
      if (serpapiKey.trim()) payload.serpapi_key = serpapiKey.trim();
      if (exaKey.trim()) payload.exa_key = exaKey.trim();
      if (xCookie.trim()) payload.x_cookie = xCookie.trim();
      if (igCookie.trim()) payload.ig_sessionid = igCookie.trim();

      const res = await apiFetch('/api/vault', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.error?.message || data?.detail || `HTTP ${res.status}`);
      settingsStatusMsg = 'Anahtarlar ve çoklu LLM yapılandırması kasaya mühürlendi.';
      openRouterInput = '';
      for (const key of Object.keys(providerInputs)) providerInputs[key] = '';
      tavilyKey = '';
      serpapiKey = '';
      exaKey = '';
      xCookie = '';
      igCookie = '';
      dispatch('saved');
    } catch (e: any) {
      settingsErrorMsg = `Kayıt hatası: ${e?.message || 'bağlantı hatası'}`;
    } finally {
      settingsSaving = false;
    }
  }

  function routeInfo(agentId: string): any {
    return routingData?.routing?.agents?.[agentId] || null;
  }
</script>

{#if open}
  <div class="sw-backdrop" role="presentation" on:click|self={close}>
    <section class="sw-card" role="dialog" aria-modal="true" aria-label="Ayarlar ve çoklu LLM kasası">
      <header class="sw-head">
        <div>
          <h3><Icon name="gear" size={0.95} /> AYARLAR, ÇOKLU LLM KASASI &amp; AJAN MODEL HARİTASI</h3>
          <p>Her sağlayıcıya doğrudan anahtar girin; sistemdeki her ajan/özellik kendi uzman modelini kullanır.</p>
        </div>
        <button class="sw-close" on:click={close} aria-label="Kapat"><Icon name="close" size={0.9} /></button>
      </header>
      <nav class="sw-tabs" aria-label="Ayar sekmeleri">
        <button class:active={settingsTab === 'providers'} on:click={() => settingsTab = 'providers'}>Çoklu LLM Anahtarları</button>
        <button class:active={settingsTab === 'search'} on:click={() => settingsTab = 'search'}>Arama &amp; Oturum (OSINT)</button>
        <button class:active={settingsTab === 'routing'} on:click={() => settingsTab = 'routing'}>Ajan &gt; Model Haritası ({routingData?.routing?.agents ? Object.keys(routingData.routing.agents).length : 21})</button>
      </nav>
      <div class="sw-body">
        {#if settingsTab === 'providers'}
          <section class="sw-panel">
            <h4>Doğrudan Aktif Rota Sağlayıcıları (llm_gateway)</h4>
            <div class="sw-grid">
              {#each DIRECT_PROVIDERS as prov}
                {@const isSet = (routingData?.provider_keys_set || []).includes(prov.id)}
                <label>
                  <span>{prov.label}<small class:active={isSet}>{isSet ? 'AKTİF' : 'BOŞ'}</small></span>
                  <input type="password" aria-label={prov.label} placeholder={prov.placeholder} bind:value={providerInputs[prov.id]} />
                </label>
              {/each}
            </div>
          </section>
          <section class="sw-panel">
            <h4>Tanı / Envanter Sağlayıcıları (Doğrudan Taşıyıcı Yok — Claude/GPT/Grok OpenRouter Üzerinden Çalışır)</h4>
            <div class="sw-grid">
              {#each DIAGNOSTIC_PROVIDERS as prov}
                {@const isSet = (routingData?.provider_keys_set || []).includes(prov.id)}
                <label>
                  <span>{prov.label}<small class:active={isSet}>{isSet ? 'KAYITLI (TANI)' : 'BOŞ'}</small></span>
                  <input type="password" aria-label={prov.label} placeholder={prov.placeholder} bind:value={providerInputs[prov.id]} />
                </label>
              {/each}
            </div>
          </section>
          <section class="sw-panel">
            <h4>OpenRouter Yedek Anahtarı &amp; Yetki Tokenı</h4>
            <div class="sw-grid">
              <label><span>OpenRouter (Yedek / Çoklu Model Ağ Geçidi)<small class:active={routingData?.has_openrouter}>{routingData?.has_openrouter ? 'AKTİF' : 'BOŞ'}</small></span><input type="password" aria-label="OpenRouter" placeholder="sk-or-v1-..." bind:value={openRouterInput} /></label>
              <label><span>PINEAL_TOKEN (Sunucu Yetki Anahtarı)</span><input type="password" aria-label="PINEAL_TOKEN" placeholder="Opsiyonel (üretim modu için)" bind:value={appTokenInput} /></label>
            </div>
          </section>
          <section class="sw-panel">
            <h4>Yerel LLM (Ollama / LM Studio)</h4>
            <label class="sw-toggle"><input type="checkbox" bind:checked={useLocal} on:change={() => localSettingTouched = true} /> Yerel LLM Kullan (Bulut yerine yerel model)</label>
            <div class="sw-grid">
              <label><span>Base URL</span><input type="text" bind:value={localUrl} placeholder="http://localhost:11434/v1" /></label>
              <label><span>Model Adı</span><input type="text" bind:value={localModel} placeholder="dolphin-llama3:latest" /></label>
            </div>
          </section>
        {:else if settingsTab === 'search'}
          <section class="sw-panel">
            <h4>OSINT Arama Motoru Anahtarları &amp; Sosyal Oturum</h4>
            <div class="sw-grid">
              <label><span>Tavily API Key<small class:active={routingData?.has_tavily}>{routingData?.has_tavily ? 'AKTİF' : 'BOŞ'}</small></span><input type="password" placeholder="tvly-..." bind:value={tavilyKey} /></label>
              <label><span>SerpAPI Key<small class:active={routingData?.has_serpapi}>{routingData?.has_serpapi ? 'AKTİF' : 'BOŞ'}</small></span><input type="password" placeholder="..." bind:value={serpapiKey} /></label>
              <label><span>Exa API Key<small class:active={routingData?.has_exa}>{routingData?.has_exa ? 'AKTİF' : 'BOŞ'}</small></span><input type="password" placeholder="..." bind:value={exaKey} /></label>
              <label><span>Instagram Session / Cookie (sessionid)</span><input type="password" placeholder="sessionid=... veya doğrudan sessionid" bind:value={igCookie} /></label>
              <label><span>X / Twitter Cookie (auth_token / ct0)</span><input type="password" placeholder="auth_token=...; ct0=..." bind:value={xCookie} /></label>
            </div>
          </section>
        {:else}
          <section class="sw-panel">
            <h4>Gerçek Ajan &amp; Özellik / Uzman Model Zinciri (llm_gateway)</h4>
            <p class="sw-note">Bu tablo OpenRouter tekilleştirmesi değildir: her ajan kendi tier ve uzman zinciriyle çalışır. Kaynak <strong>9router_canonical</strong> görünüyorsa aktif 9Router overlay zinciri üstüne yazmaktadır.</p>
            {#if routingData?.routing?.tier_violations && Object.keys(routingData.routing.tier_violations).length > 0}
              <div class="sw-warning">Tier uyarıları: {Object.entries(routingData.routing.tier_violations).map(([name, reason]) => `${name}: ${reason}`).join(' · ')}</div>
            {/if}
            {#if routingData?.routing?.agents}
              <div class="sw-table-wrap">
                <table><thead><tr><th>Ajan / Özellik</th><th>Tier</th><th>Uzman Model Zinciri (Sırayla)</th><th>Kaynak / Durum</th></tr></thead>
                  <tbody>
                    {#each Object.entries(routingData.routing.agents as Record<string, any>) as [agentName, info]}
                      <tr><td class="sw-agent">{agentName}</td><td>{info?.tier || routingData?.routing?.tiers?.[agentName] || '—'}</td><td class="sw-chain">{Array.isArray(info?.chain) ? info.chain.join(' > ') : '—'}</td><td>{info?.source || '—'}{routingData?.routing?.tier_violations?.[agentName] ? ` · ! ${routingData.routing.tier_violations[agentName]}` : ''}</td></tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {:else}
              <p class="sw-note">Model yönlendirme verisi alınamadı.</p>
            {/if}
          </section>
        {/if}
        {#if settingsStatusMsg}<div class="sw-success">{settingsStatusMsg}</div>{/if}
        {#if settingsErrorMsg}<div class="sw-error" role="alert">{settingsErrorMsg}</div>{/if}
      </div>
      <footer class="sw-foot">
        <button class="sw-secondary" on:click={close}>Kapat</button>
        {#if settingsTab !== 'routing'}<button class="sw-primary" on:click={saveMultiVaultSettings} disabled={settingsSaving}>{settingsSaving ? 'KAYDEDİLİYOR...' : 'KAYDET VE UYGULA'}</button>{/if}
      </footer>
    </section>
  </div>
{/if}

<style>
  .sw-backdrop{position:fixed;inset:0;z-index:9998;background:rgba(2,4,10,.87);backdrop-filter:blur(9px);display:flex;align-items:center;justify-content:center;padding:1rem}
  .sw-card{width:min(940px,96vw);max-height:90vh;display:flex;flex-direction:column;overflow:hidden;background:#0b0e13;color:#e8e5dc;border:1px solid rgba(190,157,93,.42);border-radius:12px;box-shadow:0 24px 70px rgba(0,0,0,.78)}
  .sw-head{display:flex;justify-content:space-between;gap:1rem;padding:1rem 1.25rem;border-bottom:1px solid #30343b}
  .sw-head h3{margin:0 0 .25rem;color:#d6bd86;font-size:.9rem}
  .sw-head p,.sw-note{margin:0;color:#9d9a91;font-size:.7rem}
  .sw-close{width:2rem;height:2rem;background:transparent;border:1px solid #41434a;color:#b8b2a6;border-radius:5px;cursor:pointer}
  .sw-tabs{display:flex;flex-wrap:wrap;gap:.45rem;padding:.65rem 1.25rem;background:#0c1016;border-bottom:1px solid #292d34}
  .sw-tabs button,.sw-secondary{padding:.42rem .75rem;background:#151a21;color:#a9a59b;border:1px solid #343a43;border-radius:5px;font-size:.7rem;font-weight:700;cursor:pointer}
  .sw-tabs button.active{background:rgba(190,157,93,.18);color:#f0dba9;border-color:#9b8051}
  .sw-body{flex:1;min-height:0;overflow:auto;padding:1rem 1.25rem;display:flex;flex-direction:column;gap:.8rem}
  .sw-panel{padding:.85rem;background:#11161d;border:1px solid #2d333c;border-radius:8px}
  .sw-panel h4{margin:0 0 .65rem;color:#d7bd82;font-size:.72rem;text-transform:uppercase}
  .sw-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.65rem}
  .sw-grid label{display:flex;flex-direction:column;gap:.3rem;color:#aaa69c;font-size:.68rem}
  .sw-grid label>span{display:flex;justify-content:space-between;gap:.4rem}
  .sw-grid small{color:#99978f;font-size:.58rem}
  .sw-grid small.active{color:#8bd5a9}
  .sw-grid input{padding:.5rem .6rem;color:#e8e5dc;background:#080b10;border:1px solid #3b414a;border-radius:5px;font-family:ui-monospace,monospace;font-size:.68rem}
  .sw-toggle{display:flex;align-items:center;gap:.5rem;margin-bottom:.65rem;color:#c7c1b4;font-size:.7rem}
  .sw-table-wrap{max-height:360px;overflow:auto}
  .sw-table-wrap table{width:100%;border-collapse:collapse;font-size:.66rem}
  .sw-table-wrap th,.sw-table-wrap td{padding:.42rem .5rem;text-align:left;border-bottom:1px solid #30343b}
  .sw-table-wrap th{color:#d6bd86}
  .sw-agent{color:#8dd9e3;font-family:ui-monospace,monospace;font-weight:700}
  .sw-chain{color:#e8e5dc;font-family:ui-monospace,monospace}
  .sw-warning{margin:.5rem 0;padding:.5rem;color:#f6d58c;background:rgba(120,70,0,.2);border:1px solid rgba(251,191,36,.35);font-size:.68rem}
  .sw-success,.sw-error{padding:.6rem .75rem;border-radius:5px;font-size:.7rem}
  .sw-success{color:#b8ebcf;background:rgba(16,100,65,.15);border:1px solid rgba(60,170,115,.35)}
  .sw-error{color:#ffc4c4;background:rgba(150,30,30,.16);border:1px solid rgba(220,80,80,.35)}
  .sw-foot{display:flex;justify-content:flex-end;gap:.6rem;padding:.8rem 1.25rem;border-top:1px solid #292d34}
  .sw-primary{padding:.48rem .9rem;color:#17140d;background:linear-gradient(135deg,#d5b779,#a8874e);border:0;border-radius:5px;font-size:.7rem;font-weight:800;cursor:pointer}
  .sw-primary:disabled{opacity:.55;cursor:wait}
  @media(max-width:680px){.sw-backdrop{padding:.35rem}.sw-card{width:100%;max-height:96vh}.sw-head,.sw-body{padding:.8rem}.sw-tabs{padding:.55rem .8rem}}
</style>
