<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '../Icon.svelte';
  import { apiFetch, clientId, formatApiError, taskStatus, vaultLocked } from '../../store';

  export let targetUrl: string = '';

  // Sol Panel: İlk Mesaj / Kanca Stüdyosu (Hook Studio)
  let archetypes: Array<{ id: string; title: string; icon?: string; description: string }> = [];
  let selectedIntent = 'authentic_connection';
  let hookUsername = '';
  let customGoal = '';
  let hookBusy = false;
  let hookError = '';
  let hookResult: any = null;
  let copiedHook = false;

  // Sağ Panel: Lilith Büyüme & Strateji Motoru
  let lilithPlatform = 'instagram';
  let lilithUsername = '';
  let lilithInstruction = '';
  let lilithBusy = false;
  let lilithError = '';
  let lilithResult: any = null;
  let copiedLilith = false;

  const LILITH_PRESETS = [
    'Karşı tarafın ilgisini hemen çekecek, doğal ama ezber bozan bir ilk mesaj yaz',
    'Profil duruşuna göre dikkat çekme ve büyüme stratejisi çıkar',
    'Olası savunmacı veya mesafeli tepkilere karşı hazır cevap planı kur',
  ];

  function prefillNames() {
    const clean = (targetUrl || '')
      .trim()
      .replace(/^https?:\/\/(?:www\.)?(?:instagram\.com|x\.com|twitter\.com)\//i, '')
      .replace(/\/.*$/, '')
      .replace(/^@/, '');
    if (clean) {
      if (!hookUsername) hookUsername = clean;
      if (!lilithUsername) lilithUsername = clean;
    }
  }

  async function loadArchetypes() {
    try {
      const res = await apiFetch('/api/hook/archetypes');
      if (res.ok) {
        const data = await res.json();
        archetypes = Array.isArray(data) ? data : data.archetypes || [];
      }
    } catch {
      /* sessizce geç */
    }
  }

  async function generateOpeningHook() {
    if (hookBusy) return;
    hookBusy = true;
    hookError = '';
    hookResult = null;
    copiedHook = false;
    try {
      const res = await apiFetch('/api/hook/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          task_id: $taskStatus?.task_id || undefined,
          intent: selectedIntent,
          custom_goal: customGoal.trim() || undefined,
          target_username: hookUsername.trim().replace(/^@/, '') || undefined,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(formatApiError(data, `HTTP ${res.status}`));
      }
      hookResult = data;
    } catch (e: any) {
      hookError = e?.message || 'İlk mesaj üretilemedi';
    } finally {
      hookBusy = false;
    }
  }

  async function generateLilithStrategy() {
    if (lilithBusy) return;
    lilithBusy = true;
    lilithError = '';
    lilithResult = null;
    copiedLilith = false;
    try {
      const res = await apiFetch('/api/lilith/strategy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          task_id: $taskStatus?.task_id || undefined,
          instruction: lilithInstruction.trim() || LILITH_PRESETS[0],
          intent: selectedIntent,
          platform: lilithPlatform,
          target_username: lilithUsername.trim().replace(/^@/, '') || undefined,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(formatApiError(data, `HTTP ${res.status}`));
      }
      lilithResult = data;
    } catch (e: any) {
      lilithError = e?.message || 'Strateji üretilemedi';
    } finally {
      lilithBusy = false;
    }
  }

  async function copyText(text: string, which: 'hook' | 'lilith') {
    if (!text) return;
    try {
      await navigator.clipboard?.writeText(text);
      if (which === 'hook') copiedHook = true;
      else copiedLilith = true;
    } catch {
      /* pano izni yoksa sessiz geç */
    }
  }

  onMount(() => {
    prefillNames();
    void loadArchetypes();
  });
</script>

<div class="lilith-page">
  <div class="section-head">
    <div>
      <h2 class="section-title">Lilith &amp; İlk Mesaj Stüdyosu</h2>
      <p class="section-intro">
        Hedefe özel açılış mesajı, 3 farklı tepkiye karşı hazır cevaplar ve büyüme stratejisi üretin.
      </p>
    </div>
    {#if $taskStatus?.task_id}
      <span class="pill pill-pink code-mono">Bağlı Analiz: {$taskStatus.task_id}</span>
    {:else}
      <span class="pill">Doğrudan mesaj da üretebilirsiniz</span>
    {/if}
  </div>

  {#if $vaultLocked}
    <div class="alert-banner warn">
      <Icon name="lock" size={0.95} />
      <span>Kasa kilitliyken yapay zekâ mesaj üretemez. Önce sağ üstten kasayı açın (veya Ayarlardan anahtar ekleyin).</span>
    </div>
  {/if}

  <div class="studio-grid">
    <!-- SOL PANEL: İLK MESAJ / KANCA ÜRETİCİ -->
    <section class="card studio-panel">
      <div class="panel-head">
        <h3><Icon name="send" size={1} /> İlk Mesaj Üretici</h3>
        <span class="pill pill-indigo">3 Dallı Cevap Planı</span>
      </div>
      <p class="section-intro">Yaklaşım tarzını seçin, isterseniz özel amacınızı yazın ve tek tıkla kopyalanabilir ilk mesaj alın.</p>

      {#if archetypes.length > 0}
        <div class="archetypes-grid">
          {#each archetypes as arc}
            <button
              type="button"
              class="arc-card"
              class:active={selectedIntent === arc.id}
              on:click={() => (selectedIntent = arc.id)}
            >
              <strong>{arc.title}</strong>
              <span>{arc.description}</span>
            </button>
          {/each}
        </div>
      {/if}

      <div class="form-grid">
        <label class="field-label">
          <span>Hedef Kullanıcı Adı (isteğe bağlı)</span>
          <input type="text" class="field-input" bind:value={hookUsername} placeholder="@kullanici" />
        </label>
        <label class="field-label">
          <span>Özel Amacınız / Notunuz</span>
          <textarea class="field-textarea" bind:value={customGoal} placeholder="Örn: Ortak ilgi alanımız üzerinden samimi bir sohbet başlatmak istiyorum..."></textarea>
        </label>
      </div>

      <button type="button" class="btn btn-primary" on:click={generateOpeningHook} disabled={hookBusy}>
        <Icon name={hookBusy ? 'refresh' : 'sparkle'} size={0.9} />
        <span>{hookBusy ? 'Üretiliyor...' : 'İLK MESAJ ÜRET'}</span>
      </button>

      {#if hookError}
        <div class="alert-banner err">{hookError}</div>
      {/if}

      {#if hookResult}
        <div class="output-hero">
          <div class="out-head">
            <span class="pill pill-ok">Önerilen İlk Mesaj</span>
            <button
              type="button"
              class="btn btn-secondary btn-sm"
              on:click={() => copyText(hookResult.opening_message || '', 'hook')}
            >
              <Icon name={copiedHook ? 'check' : 'copy'} size={0.85} />
              <span>{copiedHook ? 'Kopyalandı' : 'Kopyala'}</span>
            </button>
          </div>
          <p class="opening-msg">{hookResult.opening_message || 'Mesaj üretilemedi.'}</p>
          {#if hookResult.rationale}
            <p class="rationale-txt"><strong>Neden bu mesaj?</strong> {hookResult.rationale}</p>
          {/if}
          {#if hookResult.evidence_verification_status}
            <div class="meta-line">
              Kanıt durumu: <strong>{hookResult.evidence_verification_status}</strong>
              {#if hookResult.fallback_reason} · {hookResult.fallback_reason}{/if}
            </div>
          {/if}
        </div>

        {#if (hookResult.dialogue_tree || []).length > 0}
          <div class="branches-wrap">
            <div class="sub-lbl">Karşı Tarafın Olası Tepkilerine Hazır Yanıtlar:</div>
            {#each hookResult.dialogue_tree as branch}
              <div class="branch-card">
                <span class="pill pill-pink">{branch.scenario}</span>
                {#if branch.target_reaction}
                  <div class="br-line"><strong>Tepkisi:</strong> {branch.target_reaction}</div>
                {/if}
                <div class="br-line"><strong>Sizin Yanıtınız:</strong> {branch.our_counter_move}</div>
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    </section>

    <!-- SAĞ PANEL: LILITH BÜYÜME & STRATEJİ -->
    <section class="card studio-panel">
      <div class="panel-head">
        <h3><Icon name="sparkle" size={1} /> Lilith Büyüme &amp; Strateji Motoru</h3>
        <span class="pill pill-pink">Lilith</span>
      </div>
      <p class="section-intro">Profil için dikkat çekme kancası, psikolojik yaklaşım açısı ve adım adım strateji üretir.</p>

      <div class="preset-col">
        {#each LILITH_PRESETS as p}
          <button type="button" class="chip-btn" on:click={() => (lilithInstruction = p)}>{p}</button>
        {/each}
      </div>

      <div class="dual-row">
        <label class="field-label">
          <span>Platform</span>
          <select class="field-select" bind:value={lilithPlatform}>
            <option value="instagram">Instagram</option>
            <option value="x">X (Twitter)</option>
            <option value="general">Genel</option>
          </select>
        </label>
        <label class="field-label">
          <span>Hedef Kullanıcı Adı</span>
          <input type="text" class="field-input" bind:value={lilithUsername} placeholder="@kullanici" />
        </label>
      </div>

      <label class="field-label">
        <span>İsteğiniz / Strateji Hedefi</span>
        <textarea class="field-textarea" bind:value={lilithInstruction} placeholder="Ne tür bir ilk mesaj veya büyüme planı istersiniz?"></textarea>
      </label>

      <button type="button" class="btn btn-pink" on:click={generateLilithStrategy} disabled={lilithBusy}>
        <Icon name={lilithBusy ? 'refresh' : 'flame'} size={0.9} />
        <span>{lilithBusy ? 'Hazırlanıyor...' : 'STRATEJİ ÜRET'}</span>
      </button>

      {#if lilithError}
        <div class="alert-banner err">{lilithError}</div>
      {/if}

      {#if lilithResult}
        <div class="output-hero">
          <div class="out-head">
            <span class="pill pill-pink">Lilith Çıktısı</span>
            {#if lilithResult.lilith?.hook}
              <button
                type="button"
                class="btn btn-secondary btn-sm"
                on:click={() => copyText(lilithResult.lilith.hook, 'lilith')}
              >
                <Icon name={copiedLilith ? 'check' : 'copy'} size={0.85} />
                <span>{copiedLilith ? 'Kopyalandı' : 'Kancayı Kopyala'}</span>
              </button>
            {/if}
          </div>

          {#if lilithResult.lilith?.hook}
            <p class="opening-msg">{lilithResult.lilith.hook}</p>
          {/if}
          {#if lilithResult.lilith?.psychological_angle}
            <p class="rationale-txt"><strong>Yaklaşım Açısı:</strong> {lilithResult.lilith.psychological_angle}</p>
          {/if}
          {#if lilithResult.neuro_metrics}
            <div class="meta-line">
              Etki Skoru: <strong>{lilithResult.neuro_metrics.viral_coefficient_score ?? '—'}/10</strong> ·
              Baskın Tetik: <strong>{lilithResult.neuro_metrics.dominant_neurotransmitter ?? '—'}</strong>
            </div>
          {/if}
          {#if lilithResult.shadow?.strategy}
            <p class="rationale-txt"><strong>Gölge Stratejisi:</strong> {lilithResult.shadow.strategy}</p>
          {/if}
          {#if lilithResult.fallback_reason}
            <div class="meta-line">Not: {lilithResult.fallback_reason}</div>
          {/if}
        </div>

        {#if (lilithResult.counter_moves || []).length > 0}
          <div class="branches-wrap">
            <div class="sub-lbl">Karşı Hamleler:</div>
            {#each lilithResult.counter_moves as cm}
              <div class="branch-card">
                <span class="pill pill-pink">{cm.scenario}</span>
                <div class="br-line">{cm.our_counter_move}</div>
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    </section>
  </div>
</div>

<style>
  .lilith-page {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .studio-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    align-items: start;
  }

  @media (max-width: 1024px) {
    .studio-grid {
      grid-template-columns: 1fr;
    }
  }

  .studio-panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .panel-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }

  .panel-head h3 {
    font-size: 15px;
    font-weight: 700;
    color: var(--text-primary);
    display: inline-flex;
    align-items: center;
    gap: 7px;
  }

  .archetypes-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  @media (max-width: 600px) {
    .archetypes-grid {
      grid-template-columns: 1fr;
    }
  }

  .arc-card {
    text-align: left;
    padding: 9px 10px;
    border-radius: 9px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    color: var(--text-secondary);
    font-family: inherit;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .arc-card.active {
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--text-primary);
  }

  .arc-card strong {
    font-size: 12.5px;
    color: var(--text-primary);
  }

  .arc-card span {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.35;
  }

  .form-grid,
  .preset-col {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .dual-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .chip-btn {
    padding: 7px 10px;
    border-radius: 8px;
    border: 1px solid var(--border-strong);
    background: var(--bg-elevated);
    color: var(--text-secondary);
    font-family: inherit;
    font-size: 12px;
    text-align: left;
    cursor: pointer;
  }

  .chip-btn:hover {
    border-color: var(--pink);
    color: var(--text-primary);
  }

  .output-hero {
    padding: 13px 14px;
    border-radius: 10px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-strong);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .out-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }

  .opening-msg {
    font-size: 14.5px;
    font-weight: 500;
    color: var(--text-primary);
    line-height: 1.55;
    white-space: pre-wrap;
  }

  .rationale-txt {
    font-size: 12.5px;
    color: var(--text-secondary);
    line-height: 1.45;
  }

  .meta-line {
    font-size: 11.5px;
    color: var(--text-muted);
  }

  .branches-wrap {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .sub-lbl {
    font-size: 12px;
    font-weight: 700;
    color: var(--text-secondary);
  }

  .branch-card {
    padding: 9px 11px;
    border-radius: 8px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12.5px;
  }

  .br-line {
    color: var(--text-secondary);
    line-height: 1.45;
  }
</style>
