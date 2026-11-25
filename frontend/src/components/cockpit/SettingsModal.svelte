<script lang="ts">
  import Icon from '../Icon.svelte';

  export let showSettingsModal: boolean = false;
  export let routingData: any = null;
  export let DIRECT_PROVIDERS: Array<{ id: string; label: string; placeholder?: string; hint?: string }> = [];
  export let DIAGNOSTIC_PROVIDERS: Array<{ id: string; label: string; placeholder?: string; hint?: string }> = [];
  export let SOVEREIGNS: Array<{ id: string; name: string; role?: string; desc?: string }> = [];
  export let FIELD_AGENTS: Array<{ id: string; name: string; role?: string; desc?: string }> = [];

  export let appTokenInput: string = '';
  export let openRouterInput: string = '';
  export let providerKeys: Record<string, string> = {};
  export let tavilyKey: string = '';
  export let serpapiKey: string = '';
  export let exaKey: string = '';
  export let xCookie: string = '';
  export let igCookie: string = '';
  export let useLocal: boolean = false;
  export let localUrl: string = 'http://localhost:11434/v1';
  export let localModel: string = 'dolphin-llama3:latest';

  export let settingsSaving: boolean = false;
  export let settingsError: string = '';
  export let settingsNotice: string = '';

  export let routeChain: (id: string) => string = () => '—';
  export let routeTier: (id: string) => string = () => '—';
  export let routeSource: (id: string) => string = () => '—';
  export let onSave: () => void = () => {};
  export let onClose: () => void = () => {};

  let activeTab: 'providers' | 'routing' = 'providers';

  $: configuredSet = new Set<string>(
    Array.isArray(routingData?.provider_keys_set) ? routingData.provider_keys_set : []
  );
</script>

{#if showSettingsModal}
  <div class="modal-backdrop" role="presentation" on:click|self={onClose}>
    <div class="modal-dialog" role="dialog" aria-modal="true" aria-label="Sistem ve Anahtar Ayarları">
      <header class="modal-header">
        <div>
          <h3>Sistem ve Yapay Zekâ Anahtar Ayarları</h3>
          <p class="modal-sub">
            Yapay zekâ ve arama anahtarlarını buradan girebilirsiniz. Boş bıraktığınız alanlara dokunulmaz; anahtar olmadan da yerel ücretsiz araçlar çalışır.
          </p>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" on:click={onClose} aria-label="Kapat">
          <Icon name="close" size={1} />
        </button>
      </header>

      <div class="modal-tabs">
        <button
          type="button"
          class="tab-pill"
          class:active={activeTab === 'providers'}
          on:click={() => { activeTab = 'providers'; }}
        >
          Anahtarlar &amp; Sağlayıcılar
        </button>
        <button
          type="button"
          class="tab-pill"
          class:active={activeTab === 'routing'}
          on:click={() => { activeTab = 'routing'; }}
        >
          Ajan &gt; Model Haritası
        </button>
      </div>

      <div class="modal-body">
        {#if activeTab === 'providers'}
          <!-- Uygulama Giriş ve Ana Sağlayıcı -->
          <div class="section-box">
            <strong>Erişim ve Ana Sağlayıcı</strong>
            <div class="keys-grid">
              <label class="field-label key-card">
                <div class="key-title-row">
                  <span>Uygulama Erişim Anahtarı</span>
                  {#if appTokenInput}
                    <span class="pill pill-ok">Girili</span>
                  {/if}
                </div>
                <small class="key-hint">Sunucu erişim kilidi aktifse burada saklanır.</small>
                <input
                  type="password"
                  class="field-input"
                  bind:value={appTokenInput}
                  placeholder="Erişim anahtarı..."
                  autocomplete="off"
                />
              </label>

              <label class="field-label key-card">
                <div class="key-title-row">
                  <span>9Router / OpenRouter Ana Anahtarı</span>
                  {#if routingData?.has_openrouter}
                    <span class="pill pill-ok">Kayıtlı</span>
                  {/if}
                </div>
                <small class="key-hint">Yerel 9Router (localhost:20128) veya OpenRouter anahtarınızı buraya girin; tüm uzman birimler buradan beslenir.</small>
                <input
                  type="password"
                  class="field-input"
                  bind:value={openRouterInput}
                  placeholder="sk-..."
                  autocomplete="off"
                />
              </label>
            </div>
          </div>

          <!-- Doğrudan Aktif Rota Sağlayıcıları -->
          <div class="section-box">
            <div class="section-label-row">
              <strong>Doğrudan Aktif Rota Sağlayıcıları</strong>
              <span class="pill">
                {configuredSet.size > 0
                  ? `${configuredSet.size} sağlayıcı kayıtlı`
                  : routingData?.has_openrouter
                    ? 'OpenRouter üzerinden aktif'
                    : 'Henüz anahtar girilmedi'}
              </span>
            </div>
            <p class="help-text">
              Sohbet, özetleme ve yorumlama için doğrudan kullandığınız sağlayıcı anahtarlarını aşağıya yazabilirsiniz.
            </p>

            <div class="keys-grid">
              {#each DIRECT_PROVIDERS as p}
                <label class="field-label key-card">
                  <div class="key-title-row">
                    <span>{p.label}</span>
                    {#if configuredSet.has(p.id)}
                      <span class="pill pill-ok">Kayıtlı</span>
                    {/if}
                  </div>
                  {#if p.hint}
                    <small class="key-hint">{p.hint}</small>
                  {/if}
                  <input
                    type="password"
                    class="field-input"
                    bind:value={providerKeys[p.id]}
                    placeholder={p.placeholder || 'Anahtar girin (isteğe bağlı)'}
                    autocomplete="off"
                  />
                </label>
              {/each}
            </div>
          </div>

          <!-- Web Arama & Sosyal Oturum -->
          <div class="section-box">
            <strong>Arama Motorları ve Sosyal Oturum Bilgileri</strong>
            <p class="help-text">İnternet taraması ve açık hesap incelemeleri için isteğe bağlı bağlantılar.</p>
            <div class="keys-grid">
              <label class="field-label key-card">
                <div class="key-title-row">
                  <span>Tavily Arama Anahtarı</span>
                  {#if routingData?.has_tavily}
                    <span class="pill pill-ok">Kayıtlı</span>
                  {/if}
                </div>
                <input type="password" class="field-input" bind:value={tavilyKey} placeholder="tvly-..." autocomplete="off" />
              </label>

              <label class="field-label key-card">
                <div class="key-title-row">
                  <span>SerpAPI Arama Anahtarı</span>
                  {#if routingData?.has_serpapi}
                    <span class="pill pill-ok">Kayıtlı</span>
                  {/if}
                </div>
                <input type="password" class="field-input" bind:value={serpapiKey} placeholder="Anahtar..." autocomplete="off" />
              </label>

              <label class="field-label key-card">
                <div class="key-title-row">
                  <span>Exa Arama Anahtarı</span>
                  {#if routingData?.has_exa}
                    <span class="pill pill-ok">Kayıtlı</span>
                  {/if}
                </div>
                <input type="password" class="field-input" bind:value={exaKey} placeholder="Anahtar..." autocomplete="off" />
              </label>

              <label class="field-label key-card">
                <span>Instagram Oturum Kimliği (sessionid)</span>
                <input type="password" class="field-input" bind:value={igCookie} placeholder="Oturum çerezi..." autocomplete="off" />
              </label>

              <label class="field-label key-card">
                <span>X (Twitter) Çerez Bilgisi</span>
                <input type="password" class="field-input" bind:value={xCookie} placeholder="Çerez dizesi..." autocomplete="off" />
              </label>
            </div>
          </div>

          <!-- Yerel Kısıtlamasız Yapay Zekâ -->
          <div class="section-box local-box">
            <div class="section-label-row">
              <strong>Bilgisayardaki Yerel Yapay Zekâ (İsteğe Bağlı)</strong>
              <label class="toggle-inline">
                <input type="checkbox" bind:checked={useLocal} />
                <span>Yerel modeli kullan</span>
              </label>
            </div>
            <div class="keys-grid">
              <label class="field-label">
                <span>Yerel Sunucu Adresi</span>
                <input type="text" class="field-input" bind:value={localUrl} placeholder="http://localhost:11434/v1" />
              </label>
              <label class="field-label">
                <span>Model Adı</span>
                <input type="text" class="field-input" bind:value={localModel} placeholder="dolphin-llama3:latest" />
              </label>
            </div>
          </div>

          <!-- Tanı Amaçlı Ek Sağlayıcılar -->
          {#if DIAGNOSTIC_PROVIDERS.length > 0}
            <details class="section-box fold-box">
              <summary>Diğer Sağlayıcılar (Tanı ve OpenRouter Köprüsü)</summary>
              <div class="keys-grid" style="margin-top: 10px;">
                {#each DIAGNOSTIC_PROVIDERS as dp}
                  <label class="field-label key-card">
                    <span>{dp.label}</span>
                    <input
                      type="password"
                      class="field-input"
                      bind:value={providerKeys[dp.id]}
                      placeholder={dp.placeholder || 'Anahtar girin (isteğe bağlı)'}
                      autocomplete="off"
                    />
                  </label>
                {/each}
              </div>
            </details>
          {/if}
        {:else}
          <div class="section-box">
            <strong>Ajan &gt; Model Haritası</strong>
            <p class="help-text">Her uzman birimin şu anda hangi akıllı model hattını kullandığını buradan şeffaf biçimde görebilirsiniz.</p>

            <div class="map-table">
              {#each [...SOVEREIGNS, ...FIELD_AGENTS] as agent}
                <div class="map-row">
                  <div class="map-agent">
                    <strong>{agent.name}</strong>
                    <small>{agent.role || agent.desc || agent.id}</small>
                  </div>
                  <div class="map-route">
                    <span class="pill">{routeTier(agent.id)}</span>
                    <span class="route-text">{routeChain(agent.id)}</span>
                    <small class="route-src">{routeSource(agent.id)}</small>
                  </div>
                </div>
              {/each}
            </div>
          </div>
        {/if}

        {#if settingsError}
          <div class="alert-banner err">{settingsError}</div>
        {/if}
        {#if settingsNotice}
          <div class="alert-banner ok">{settingsNotice}</div>
        {/if}
      </div>

      <footer class="modal-footer">
        <button type="button" class="btn btn-ghost" on:click={onClose}>Kapat</button>
        <button
          type="button"
          class="btn btn-primary"
          on:click={onSave}
          disabled={settingsSaving}
        >
          <Icon name="check" size={0.95} />
          {settingsSaving ? 'Kaydediliyor...' : 'KAYDET VE UYGULA'}
        </button>
      </footer>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(2, 6, 23, 0.72);
    backdrop-filter: blur(4px);
    z-index: 60;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
  }

  .modal-dialog {
    width: 100%;
    max-width: 820px;
    max-height: 88vh;
    background: var(--bg-surface);
    backdrop-filter: blur(18px);
    border: 1px solid var(--border-strong);
    border-radius: 14px;
    box-shadow: var(--shadow-md);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  :global([data-theme='dark']) .modal-dialog {
    background: rgba(30, 14, 11, 0.92);
  }

  .modal-header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
  }

  .modal-header h3 {
    font-size: 16px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .modal-sub {
    margin-top: 4px;
    font-size: 12.5px;
    color: var(--text-muted);
  }

  .modal-tabs {
    display: flex;
    gap: 8px;
    padding: 10px 20px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-elevated);
    flex-wrap: wrap;
  }

  .tab-pill {
    padding: 6px 12px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--bg-surface);
    color: var(--text-secondary);
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
  }

  .tab-pill.active {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-contrast);
  }

  .modal-body {
    padding: 18px 20px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .section-box {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .local-box {
    padding: 12px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
  }

  .fold-box {
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid var(--border);
  }

  .fold-box summary {
    cursor: pointer;
    font-weight: 600;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .toggle-inline {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
  }

  .section-label-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    flex-wrap: wrap;
  }

  .help-text {
    font-size: 12.5px;
    color: var(--text-muted);
  }

  .keys-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 10px;
  }

  .key-card {
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
  }

  .key-title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
  }

  .key-hint {
    font-size: 11px;
    font-weight: 400;
    color: var(--text-muted);
  }

  .map-table {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .map-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    padding: 10px 12px;
    border-radius: 9px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
  }

  .map-agent {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .map-agent small,
  .route-src {
    font-size: 11.5px;
    color: var(--text-muted);
  }

  .map-route {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .route-text {
    font-size: 12.5px;
    color: var(--text-primary);
  }

  .modal-footer {
    padding: 14px 20px;
    border-top: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    background: var(--bg-elevated);
  }
</style>
