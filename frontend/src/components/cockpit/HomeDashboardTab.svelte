<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '../Icon.svelte';
  import TaskEvidence from '../TaskEvidence.svelte';
  import {
    isProcessing,
    taskStatus,
    agentStatuses,
    agentStatusSource,
    speechState,
    logs,
    vaultLocked,
  } from '../../store';
  import { taskRuns, taskRunLabel, rackAvailability } from '../../lib/taskRunStatus';
  import { channelStatusText } from '../../lib/channelStatus';
  import { activeTab } from '../../lib/theme';

  export let SOVEREIGNS: any[] = [];
  export let FIELD_AGENTS: any[] = [];
  export let PILLARS: any[] = [];

  export let targetUrl: string = '';
  export let isAdultDeclared: boolean = false;
  export let showContextInputs: boolean = false;
  export let contextRituals: string = '';
  export let contextPlaylist: string = '';
  export let contextEnvies: string = '';
  export let userRituals: string = '';
  export let userPlaylist: string = '';
  export let userEnvies: string = '';

  export let phoneConsentGiven: boolean = false;
  export let isProbingPhone: boolean = false;
  export let phoneProbeResult: any = null;

  export let launchNotice: { tone: 'err' | 'warn' | 'ok'; text: string } | null = null;
  export let platformWarning: string | null = null;
  export let legalNotice: any = null;

  export let selectedAgentId: string | null = 'aspasia';
  export let chatMessages: Array<{ ts: string; sender: string; text: string }> = [];
  export let inputMessage: string = '';
  export let isSending: boolean = false;

  export let injectType: string = 'twin_url';
  export let injectValue: string = '';
  export let injectTargetAgent: string = 'all';
  export let injectNote: string = '';
  export let isInjecting: boolean = false;
  export let injectHistory: Array<{ type: string; value: string; target: string; note: string; ts: string }> = [];

  export let overrideFact: string = '';
  export let overrideTag: string = 'operator_note';
  export let overrideBusy: boolean = false;
  export let overrideNotice: string = '';

  export let routingData: any = null;
  export let statusSourceText: string = 'none';
  export let sourceDescriptions: Record<string, string> = {};
  export let jurors: any = null;

  export let isPhoneInput: (val: string) => boolean = () => false;
  export let getPillarHasData: (id: string) => boolean = () => false;
  export let pillarSummaries: Record<string, any> = {};
  export let launchAnalysis: () => void = () => {};
  export let probePhoneAction: () => void = () => {};
  export let selectAgent: (id: string) => void = () => {};
  export let formatPresetWithTarget: (p: string) => string = (p) => p;
  export let sendAspasiaMessage: () => void = () => {};
  export let injectCommanderEvidence: () => void = () => {};
  export let submitOperatorOverride: () => void = () => {};
  export let openHistoryModal: (tab: 'tasks' | 'reports') => void = () => {};
  export let openTermsModal: () => void = () => {};
  export let openSettingsModal: () => void = () => {};
  export let routeChain: (id: string) => string = () => '';
  export let routeTier: (id: string) => string = () => '';
  export let routeSource: (id: string) => string = () => '';

  let guideOpen = true;
  let logsOpen = false;
  let manualOpen = false;

  onMount(() => {
    try {
      if (localStorage.getItem('pineal_guide_dismissed') === '1') {
        guideOpen = false;
      }
    } catch {
      /* sessizce geç */
    }
  });

  function toggleGuide() {
    guideOpen = !guideOpen;
    try {
      localStorage.setItem('pineal_guide_dismissed', guideOpen ? '0' : '1');
    } catch {
      /* sessizce geç */
    }
  }

  $: scopedRuns = taskRuns($taskStatus);
  $: liveRunModels = Object.entries(scopedRuns)
    .filter(([, run]) => (run as any)?.model)
    .map(([agent, run]) => ({ agent, model: (run as any).model }));

  $: activeTaskAgentIds = (() => {
    const ids = new Set<string>(Object.keys(scopedRuns));
    for (const a of $taskStatus?.planned_agents || []) if (a) ids.add(String(a));
    for (const a of $taskStatus?.completed_agents || []) if (a) ids.add(String(a));
    if ($taskStatus?.current_agent) ids.add(String($taskStatus.current_agent));
    return Array.from(ids);
  })();

  $: followerAudit = $taskStatus?.follower_audit || null;
  $: timingForensics = $taskStatus?.timing_forensics || null;
  $: depthReport = $taskStatus?.depth_report || null;
  $: visualEvidence = $taskStatus?.visual_evidence || null;
  $: shadowProfile = $taskStatus?.shadow_profile || null;
  $: osintFootprint = $taskStatus?.osint_footprint || null;
  $: resonanceCalc = $taskStatus?.resonance_calc || $taskStatus?.reso || null;
  $: evidenceChain = Array.isArray($taskStatus?.evidence_chain) ? $taskStatus.evidence_chain : [];
  $: channelStatusList = Array.isArray($taskStatus?.channel_status) ? $taskStatus.channel_status : [];

  $: rackSlotSummary = (() => {
    const values = Object.values($agentStatuses || {});
    const labels = values.map((v: any) => rackAvailability(v?.status));
    return {
      total: labels.length,
      active: labels.filter((l) => l === 'ACTIVE').length,
      ready: labels.filter((l) => l === 'READY').length,
    };
  })();

  const PILLAR_TITLES_TR: Record<string, string> = {
    follower: 'Takipçi Kalitesi',
    timing: 'Zamanlama Düzeni',
    depth: 'İçerik Derinliği',
    visual: 'Görsel Tutarlılık',
    shadow: 'Gölge & Koordinasyon',
    osint: 'Açık Kaynak (OSINT)',
    resonance: 'Uyum & Rezonans',
  };
</script>

<div class="home-wrap">
  <!-- 1. BAŞLANGIÇ REHBERİ (İlk defa kullanan biri için 3 net adım) -->
  <section class="card guide-card" aria-label="Başlangıç rehberi">
    <div class="guide-head">
      <div class="guide-title-row">
        <span class="pill pill-ok"><Icon name="help" size={0.85} /> Hızlı Başlangıç</span>
        <span class="guide-sub">İlk kez kullanıyorsanız sadece şu 3 adımı izleyin:</span>
      </div>
      <button type="button" class="btn btn-ghost btn-sm" on:click={toggleGuide}>
        {guideOpen ? 'Rehberi Gizle' : 'Rehberi Göster'}
      </button>
    </div>

    {#if guideOpen}
      <div class="guide-steps">
        <div class="guide-step">
          <span class="step-num">1</span>
          <div>
            <strong>Anahtarı ve Kasayı Açın</strong>
            <p>
              Sağ üstteki <button type="button" class="inline-link" on:click={openSettingsModal}>Ayarlar</button>
              düğmesinden yapay zekâ anahtarınızı kaydedin. Şu an kasa:
              <strong>{$vaultLocked ? 'Kilitli' : 'Açık'}</strong>.
            </p>
          </div>
        </div>
        <div class="guide-step">
          <span class="step-num">2</span>
          <div>
            <strong>Hedefi Yazıp Onay Verin</strong>
            <p>Aşağıdaki kutuya incelemek istediğiniz profil adresini, kullanıcı adını veya telefonu yazın; 18+ ve KVKK kutusunu işaretleyin.</p>
          </div>
        </div>
        <div class="guide-step">
          <span class="step-num">3</span>
          <div>
            <strong>Analizi Başlatın</strong>
            <p><strong>ANALİZİ BAŞLAT</strong>'a basın. Sonuçlar sağdaki kartlara ve Aspasia sohbetine canlı akar; soldaki menüden tüm araçlara ulaşabilirsiniz.</p>
          </div>
        </div>
      </div>
    {/if}

    {#if legalNotice?.headline}
      <div class="legal-strip">
        <Icon name="shield" size={0.9} />
        <span>{legalNotice.headline}</span>
        <button type="button" class="inline-link" on:click={openTermsModal}>Detayları Gör</button>
      </div>
    {/if}
  </section>

  <!-- 2. ANA HEDEF ANALİZ KARTI -->
  <section class="card hero-card">
    <div class="hero-top">
      <div>
        <h2 class="hero-title">Kimi veya hangi hesabı araştırmak istiyorsunuz?</h2>
        <p class="section-intro">
          Sosyal medya adresi, <span class="code-mono">@kullanıcı</span> veya telefon numarası yazın — sistem ne girdiğinizi otomatik tanır.
        </p>
      </div>
      {#if $taskStatus?.task_id}
        <span class="pill pill-indigo code-mono">Görev: {$taskStatus.task_id}</span>
      {/if}
    </div>

    <div class="target-input-row">
      <div class="target-input-box">
        <span class="input-prefix"><Icon name="target" size={1.05} /></span>
        <input
          type="text"
          class="target-main-input"
          bind:value={targetUrl}
          placeholder="Hedef Profil URL, @kullanıcı veya Telefon (örn: (552) 956-87-63)..."
          disabled={$isProcessing || isProbingPhone}
          on:keydown={(e) => {
            if (e.key === 'Enter') {
              if (isPhoneInput(targetUrl)) probePhoneAction();
              else launchAnalysis();
            }
          }}
        />
      </div>
    </div>

    <div class="launch-controls-row">
      <label class="adult-consent-badge" title="Hedef kişinin 18 yaşından büyük (reşit) ve KVKK kapsamında işlenebilir olduğu beyanı">
        <input type="checkbox" bind:checked={isAdultDeclared} />
        <span>18+ Reşit &amp; KVKK Açık Rıza Beyanı</span>
      </label>

      <button
        type="button"
        class="btn btn-primary launch-main-btn"
        on:click={launchAnalysis}
        disabled={$isProcessing || !targetUrl.trim() || !isAdultDeclared}
      >
        <Icon name={$isProcessing ? 'refresh' : 'play'} size={0.9} />
        <span>{$isProcessing ? 'ANALİZ EDİLİYOR...' : 'ANALİZİ BAŞLAT'}</span>
      </button>

      <button
        type="button"
        class="btn btn-secondary"
        on:click={() => (showContextInputs = !showContextInputs)}
      >
        <Icon name={showContextInputs ? 'chevron-down' : 'sparkle'} size={0.9} />
        <span>{showContextInputs ? 'Ek Bilgileri Gizle' : 'Ek Bilgi Ekle (İsteğe Bağlı)'}</span>
      </button>

      <button
        type="button"
        class="btn btn-ghost"
        on:click={() => activeTab.set('cross')}
      >
        <Icon name="search" size={0.9} />
        <span>Çapraz Taramaya Git</span>
      </button>
    </div>

    {#if showContextInputs}
      <div class="context-drawer">
        <div class="context-col">
          <div class="context-heading">Hedef Hakkında Bilinenler (İsteğe Bağlı)</div>
          <div class="context-grid">
            <label class="field-label">
              <span>Alışkanlıklar / İlgi Alanları</span>
              <input type="text" class="field-input" bind:value={contextRituals} placeholder="Örn: Gece okumaları, felsefe, kahve..." />
            </label>
            <label class="field-label">
              <span>Müzik / Çalma Listesi</span>
              <input type="text" class="field-input" bind:value={contextPlaylist} placeholder="Örn: Klasik müzik, caz, rock..." />
            </label>
            <label class="field-label">
              <span>Amaç / Odak Notu</span>
              <input type="text" class="field-input" bind:value={contextEnvies} placeholder="Örn: İş birliği kurmak, ortak zemin bulmak..." />
            </label>
          </div>
        </div>

        <div class="context-col">
          <div class="context-heading">OPERATÖR VERİSİ (Kendi Profiliniz — İsteğe Bağlı)</div>
          <div class="context-grid">
            <label class="field-label">
              <span>Kendi Alışkanlıklarınız</span>
              <input type="text" class="field-input" bind:value={userRituals} placeholder="Kendi ilgi alanlarınız..." />
            </label>
            <label class="field-label">
              <span>Müzik Tarzınız</span>
              <input type="text" class="field-input" bind:value={userPlaylist} placeholder="Sevdiğiniz müzikler..." />
            </label>
            <label class="field-label">
              <span>Hedefiniz</span>
              <input type="text" class="field-input" bind:value={userEnvies} placeholder="Yaklaşım amacınız..." />
            </label>
          </div>
        </div>
      </div>
    {/if}

    {#if isPhoneInput(targetUrl)}
      <div class="phone-action-strip">
        <label class="consent-check-label">
          <input type="checkbox" bind:checked={phoneConsentGiven} />
          <span>AÇIK RIZA ALINDI — Bu telefon numarasının sahibinden KVKK kapsamında açık rıza alındığını beyan ederim</span>
        </label>
        <button
          type="button"
          class="btn btn-secondary"
          on:click={probePhoneAction}
          disabled={isProbingPhone || !phoneConsentGiven}
        >
          <Icon name="phone" size={0.9} />
          <span>{isProbingPhone ? 'TARANIYOR...' : 'NUMARAYI SORGULA'}</span>
        </button>
      </div>
    {/if}

    {#if platformWarning}
      <div class="alert-banner warn" style="margin-top: 10px;" role="status">
        <Icon name="warning" size={0.95} />
        <span>{platformWarning}</span>
      </div>
    {/if}

    {#if launchNotice}
      <div class="alert-banner {launchNotice.tone}" style="margin-top: 10px;" role="alert">
        <Icon name={launchNotice.tone === 'ok' ? 'check' : 'warning'} size={0.95} />
        <span>{launchNotice.text}</span>
      </div>
    {/if}
  </section>

  <!-- TELEFON SONUÇ KARTI -->
  {#if phoneProbeResult}
    <section class="card phone-result-card">
      <div class="section-head">
        <div>
          <h3>TELEFON OSINT İSTİHBARATI — {phoneProbeResult.metadata?.e164 || phoneProbeResult.phone_input}</h3>
          <p class="section-intro">Numaranın operatör, bölge ve açık mesajlaşma kanalı bilgileri</p>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" on:click={() => (phoneProbeResult = null)} aria-label="Telefon kartını kapat">
          <Icon name="close" size={0.9} />
        </button>
      </div>

      <div class="phone-meta-grid">
        <div class="card-elevated">
          <span class="meta-lbl">Operatör / Şebeke</span>
          <strong>{phoneProbeResult.metadata?.carrier_name || 'Bilinmiyor'}</strong>
        </div>
        <div class="card-elevated">
          <span class="meta-lbl">Ülke &amp; Bölge</span>
          <strong>{phoneProbeResult.metadata?.country_name || 'Bilinmiyor'}</strong>
        </div>
        <div class="card-elevated">
          <span class="meta-lbl">Hat Türü</span>
          <strong>{phoneProbeResult.metadata?.line_type || 'Bilinmiyor'}</strong>
        </div>
        <div class="card-elevated">
          <span class="meta-lbl">Geçerlilik</span>
          <strong>{phoneProbeResult.metadata?.is_valid ? 'Geçerli numara formatı' : 'Doğrulanamadı'}</strong>
        </div>
      </div>

      {#if (phoneProbeResult.messaging_probes || []).length > 0}
        <div class="phone-links-row">
          {#each phoneProbeResult.messaging_probes as mp}
            <a href={mp.url} target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm">
              <Icon name="arrow-right" size={0.8} />
              <span>{mp.platform} Profilini Aç</span>
            </a>
          {/each}
        </div>
      {/if}

      {#if (phoneProbeResult.associated_handles || []).length > 0}
        <div class="phone-links-row">
          <span class="meta-lbl">Aday kullanıcı adları:</span>
          {#each phoneProbeResult.associated_handles as handle}
            <button
              type="button"
              class="btn btn-ghost btn-sm"
              on:click={() => {
                targetUrl = handle;
                launchAnalysis();
              }}
            >
              @{handle} Analize Al
            </button>
          {/each}
        </div>
      {/if}

      <div style="margin-top: 10px;">
        <button
          type="button"
          class="btn btn-primary btn-sm"
          on:click={() => {
            injectType = 'phone';
            injectValue = `${phoneProbeResult.metadata?.e164 || phoneProbeResult.phone_input} (${phoneProbeResult.metadata?.carrier_name || 'Bilinmiyor'})`;
            injectCommanderEvidence();
          }}
        >
          <Icon name="check" size={0.85} />
          <span>Bu Numarayı Kanıt Olarak Kaydet</span>
        </button>
      </div>
    </section>
  {/if}

  <!-- 3. ANA 2 SÜTUNLU ÇALIŞMA ALANI -->
  <div class="main-two-col">
    <!-- SOL SÜTUN: DANIŞMANLAR + SOHBET + AJANLAR + MANUEL KANIT -->
    <div class="col-stack">
      <!-- Danışman Seçimi & Hızlı Sohbet -->
      <section class="card">
        <div class="section-head">
          <div>
            <h3 class="block-title">Danışmanlar &amp; Canlı Sohbet</h3>
            <p class="section-intro">Sorularınızı Aspasia'ya sorun veya ilk temas/büyüme için Lilith'i seçin.</p>
          </div>
          <span class="pill" class:pill-ok={$speechState === 'speaking'}>
            {$speechState === 'speaking'
              ? 'Konuşuyor'
              : $speechState === 'listening'
                ? 'Dinliyor'
                : $speechState === 'denied'
                  ? 'Ses Motoru Yok'
                  : 'Sohbet Hazır'}
          </span>
        </div>

        <div class="advisors-row">
          <div
            class="advisor-card aspasia-station"
            class:selected={selectedAgentId === 'aspasia'}
            role="button"
            tabindex="0"
            aria-pressed={selectedAgentId === 'aspasia'}
            on:click={() => selectAgent('aspasia')}
            on:keydown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                selectAgent('aspasia');
              }
            }}
          >
            <div class="adv-head">
              <span class="pill pill-ok"><Icon name="diamond" size={0.85} /> ASPASIA</span>
              <button type="button" class="inline-link" on:click|stopPropagation={() => activeTab.set('aspasia')}>
                Tam Ekran Aç →
              </button>
            </div>
            <p class="adv-desc">Baş strateji danışmanı: hedefi özetler, sorularınızı yanıtlar, yaklaşım kurar.</p>
          </div>

          <div
            class="advisor-card lilith-station"
            class:selected={selectedAgentId === 'lilith'}
            role="button"
            tabindex="0"
            aria-pressed={selectedAgentId === 'lilith'}
            on:click={() => selectAgent('lilith')}
            on:keydown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                selectAgent('lilith');
              }
            }}
          >
            <div class="adv-head">
              <span class="pill pill-pink"><Icon name="sparkle" size={0.85} /> LILITH</span>
              <button type="button" class="inline-link" on:click|stopPropagation={() => activeTab.set('lilith')}>
                Stüdyoyu Aç →
              </button>
            </div>
            <p class="adv-desc">Büyüme ve ilk mesaj uzmanı: dikkat çekici açılış mesajı ve karşı hamle üretir.</p>
          </div>
        </div>

        <div class="preset-chips">
          {#each (selectedAgentId === 'lilith' ? SOVEREIGNS[1]?.presets : SOVEREIGNS[0]?.presets) || [] as preset}
            <button
              type="button"
              class="chip-btn"
              on:click={() => {
                inputMessage = formatPresetWithTarget(preset);
              }}
            >
              {preset}
            </button>
          {/each}
        </div>

        <div class="chat-feed">
          {#each chatMessages.slice(-40) as msg}
            <div class="chat-bubble" class:user={msg.sender === 'SÖZ'} class:lilith={msg.sender === 'Lilith'}>
              <div class="bubble-meta">
                <strong>{msg.sender === 'SÖZ' ? 'Siz' : msg.sender}</strong>
                <span>{msg.ts}</span>
              </div>
              <div class="bubble-text">{msg.text}</div>
            </div>
          {/each}
        </div>

        <div class="chat-input-area">
          <input
            type="text"
            class="field-input"
            bind:value={inputMessage}
            placeholder="Aspasia veya Lilith'e mesaj yazın, soru sorun..."
            disabled={isSending}
            on:keydown={(e) => {
              if (e.key === 'Enter') sendAspasiaMessage();
            }}
          />
          <button
            type="button"
            class="btn btn-primary"
            on:click={sendAspasiaMessage}
            disabled={isSending || !inputMessage.trim()}
          >
            <Icon name={isSending ? 'refresh' : 'send'} size={0.9} />
            <span>Gönder</span>
          </button>
        </div>
      </section>

      <!-- 12 Saha Ajanı & Model Kaynağı -->
      <section class="card">
        <div class="section-head">
          <div>
            <h3 class="block-title">Analiz Ajanları ({activeTaskAgentIds.length || FIELD_AGENTS.length})</h3>
            <p class="section-intro">Görev sırasında hangi uzmanın hangi modelle çalıştığını gerçek zamanlı izleyin.</p>
          </div>
          <span class="pill" title="Sunucudaki ajan durum kaynağı">
            KAYNAK: {sourceDescriptions[statusSourceText] || statusSourceText}
            {#if rackSlotSummary.total > 0}
              · {rackSlotSummary.active} aktif / {rackSlotSummary.ready} hazır
            {/if}
          </span>
        </div>

        {#if liveRunModels.length > 0}
          <div class="live-models-strip">
            <span class="meta-lbl">ÇALIŞMA MODELİ:</span>
            {#each liveRunModels as lm}
              <span class="pill pill-indigo code-mono">{lm.agent}: {lm.model}</span>
            {/each}
          </div>
        {/if}

        {#if activeTaskAgentIds.length > 0}
          <div class="agents-grid">
            {#each activeTaskAgentIds as agId}
              {@const agMeta = FIELD_AGENTS.find((a) => a.id === agId)}
              {@const run = scopedRuns[agId]}
              {@const rStatus = run ? taskRunLabel(run) : $taskStatus?.current_agent === agId ? 'RUNNING' : 'PLANNED'}
              <button
                type="button"
                class="agent-card"
                class:selected={selectedAgentId === agId}
                on:click={() => selectAgent(agId)}
              >
                <div class="ag-top">
                  <strong>{agMeta?.name || agId}</strong>
                  <span class="pill" class:pill-ok={rStatus === 'DONE' || rStatus === 'READY'} class:pill-warn={rStatus === 'ACTIVE' || rStatus === 'RUNNING'}>
                    {rStatus}
                  </span>
                </div>
                <div class="ag-meta code-mono">{run?.model || 'model bekleniyor'}</div>
                <div class="ag-meta">
                  {#if Array.isArray(run?.call_ids) && run.call_ids.length > 0}
                    Çağrı: {run.call_ids.slice(0, 2).join(', ')}
                  {:else}
                    {routeChain(agId)}
                  {/if}
                </div>
                <div class="ag-tier">{routeTier(agId)} · {routeSource(agId)}</div>
              </button>
            {/each}
          </div>
        {:else}
          <div class="empty-state">
            Bu görevde henüz çalışmış ajan yok. Yukarıdan hedef girip <strong>ANALİZİ BAŞLAT</strong>'a bastığınızda çalışan ajanlar burada canlı görünür.
          </div>
        {/if}

        <details class="catalog-fold">
          <summary>Sistemdeki Tüm Uzman Ajanlar ({FIELD_AGENTS.length} ajan)</summary>
          <div class="agents-grid" style="margin-top: 10px;">
            {#each FIELD_AGENTS as ag}
              <button
                type="button"
                class="agent-card"
                class:selected={selectedAgentId === ag.id}
                on:click={() => selectAgent(ag.id)}
              >
                <div class="ag-top">
                  <strong>{ag.name}</strong>
                  <span class="pill">{routeTier(ag.id)}</span>
                </div>
                <div class="ag-desc">{ag.desc}</div>
                <div class="ag-meta code-mono" title={routeChain(ag.id)}>{routeChain(ag.id)}</div>
              </button>
            {/each}
          </div>
        </details>

        {#if channelStatusList.length > 0}
          <div class="channels-block">
            <div class="context-heading">Veri Kanalları ({channelStatusList.length})</div>
            <div class="channels-list">
              {#each channelStatusList as ch}
                <div class="channel-row" class:ok={ch?.status === 'ok'}>
                  <span>{channelStatusText(ch)}</span>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </section>

      <!-- Manuel Kanıt Ekle & Not Mühürle -->
      <section class="card">
        <div class="guide-head">
          <div>
            <h3 class="block-title">Manuel Kanıt &amp; Operatör Notu</h3>
            <p class="section-intro">Kendi bulduğunuz ek bilgiyi veya hesabı doğrudan ajan hafızasına kaydedin.</p>
          </div>
          <button type="button" class="btn btn-ghost btn-sm" on:click={() => (manualOpen = !manualOpen)}>
            {manualOpen ? 'Daralt' : 'Aç'}
          </button>
        </div>

        {#if manualOpen}
          <div class="manual-grid">
            <div class="manual-pair">
              <label class="field-label">
                <span>Bilgi Türü</span>
                <select class="field-select" bind:value={injectType}>
                  <option value="twin_url">Eş Profil URL</option>
                  <option value="phone">Telefon Numarası</option>
                  <option value="bio_fact">Biyografi / Meslek Bilgisi</option>
                  <option value="ground_truth">Doğrulanmış Bilgi</option>
                  <option value="note">Önemli Not</option>
                </select>
              </label>
              <label class="field-label">
                <span>İlgili Ajan</span>
                <select class="field-select" bind:value={injectTargetAgent}>
                  <option value="all">Tüm Ajanlar</option>
                  <option value="lilith">Lilith</option>
                  <option value="osint_investigator">OSINT Uzmanı</option>
                  <option value="depth_analyst">Derinlik Uzmanı</option>
                </select>
              </label>
            </div>
            <input
              type="text"
              class="field-input"
              bind:value={injectValue}
              placeholder="Bulduğunuz kanıtı yazın (örn: https://x.com/hesap veya 'Mimar')..."
            />
            <input
              type="text"
              class="field-input"
              bind:value={injectNote}
              placeholder="Kısa açıklama (isteğe bağlı)..."
            />
            <button
              type="button"
              class="btn btn-secondary"
              on:click={injectCommanderEvidence}
              disabled={isInjecting || !injectValue.trim()}
            >
              <Icon name="check" size={0.9} />
              <span>{isInjecting ? 'Kaydediliyor...' : 'Kanıtı Ajan Hafızasına Kaydet'}</span>
            </button>

            {#if injectHistory.length > 0}
              <div class="inject-list">
                {#each injectHistory.slice(0, 3) as h}
                  <div class="inject-item">
                    <span class="pill">{h.type}</span>
                    <span>{h.value}</span>
                  </div>
                {/each}
              </div>
            {/if}

            <div class="override-divider">
              <div class="context-heading">Doğrulanmış Operatör Notu Mühürle</div>
              <div class="manual-pair">
                <input
                  type="text"
                  class="field-input"
                  bind:value={overrideFact}
                  placeholder="Kesin bilgi ekle (örn: Hedef İstanbul'da yaşıyor)"
                />
                <button
                  type="button"
                  class="btn btn-ghost"
                  on:click={submitOperatorOverride}
                  disabled={overrideBusy || !overrideFact.trim()}
                >
                  {overrideBusy ? 'Mühürleniyor...' : 'Notu Mühürle'}
                </button>
              </div>
              {#if overrideNotice}
                <div class="ag-meta">{overrideNotice}</div>
              {/if}
            </div>
          </div>
        {/if}
      </section>
    </div>

    <!-- SAĞ SÜTUN: 7 ANALİZ SÜTUNU + CANLI KANIT ZİNCİRİ -->
    <div class="col-stack">
      <section class="card">
        <div class="section-head">
          <div>
            <h3 class="block-title">7 Analiz Kategorisi</h3>
            <p class="section-intro">Bu özetler ön göstergedir; tek başına doğrulanmış kanıt değildir.</p>
          </div>
          {#if jurors !== null}
            <span class="pill pill-indigo">Jüri Koltuğu: {jurors}</span>
          {/if}
        </div>

        <div class="pillars-grid">
          {#each PILLARS as p}
            {@const summary = pillarSummaries[p.id]}
            {@const hasData = getPillarHasData(p.id) || Boolean(summary?.hasData)}
            <article class="pillar-column {p.id}-pillar" class:has-data={hasData}>
              <div class="pillar-head">
                <span class="pillar-name">
                  <Icon name={p.icon} size={0.95} />
                  <span>{PILLAR_TITLES_TR[p.id] || p.tr}</span>
                </span>
                <span class="pill" class:pill-ok={hasData}>
                  {hasData ? (summary?.evidenceCount ? `${summary.evidenceCount} Kayıt` : 'Ölçüldü') : 'VERİ YOK'}
                </span>
              </div>

              <div class="pillar-meta-row">
                <span>Güven: <strong>{summary?.confidence !== null && summary?.confidence !== undefined ? summary.confidence + '%' : 'ölçülmedi'}</strong></span>
                <span>Kaynak: <strong>{summary?.sources?.length ? summary.sources.slice(0, 2).join(', ') : 'yok'}</strong></span>
              </div>

              {#if hasData}
                <div class="pillar-body">
                  {#if p.id === 'follower' && followerAudit}
                    <div><strong>Ortalama:</strong> {followerAudit.avg_followers ?? '—'}</div>
                    <div><strong>Gerçeklik:</strong> {followerAudit.authenticity_score !== undefined ? followerAudit.authenticity_score + '%' : '—'}</div>
                    <div><strong>Bot Riski:</strong> {followerAudit.bot_risk !== undefined ? followerAudit.bot_risk + '%' : '—'}</div>
                  {:else if p.id === 'timing' && timingForensics}
                    <div><strong>Saat Dağılımı:</strong> {timingForensics.hour_distribution ? 'Mevcut' : '—'}</div>
                    <div><strong>Otomatik Skor:</strong> {timingForensics.automation_score !== undefined ? timingForensics.automation_score + '%' : '—'}</div>
                    <div><strong>Zaman Dilimi:</strong> {timingForensics.timezone_inferred || '—'}</div>
                  {:else if p.id === 'depth' && depthReport}
                    <div><strong>Gerçeklik Endeksi:</strong> {typeof depthReport.reality_index === 'number' ? depthReport.reality_index.toFixed(2) : '—'}</div>
                    <div><strong>Özet:</strong> {depthReport.essence_one_liner || '—'}</div>
                    <div><strong>Bulgu / Çelişki:</strong> {(depthReport.reality_findings?.length || 0) + ' / ' + (depthReport.contradictions?.length || 0)}</div>
                  {:else if p.id === 'visual' && visualEvidence}
                    <div><strong>Tutarlılık:</strong> {visualEvidence.consistency_score !== undefined ? visualEvidence.consistency_score + '%' : '—'}</div>
                    <div><strong>Deepfake Riski:</strong> {visualEvidence.deepfake_risk !== undefined ? visualEvidence.deepfake_risk + '%' : '—'}</div>
                    <div><strong>Estetik:</strong> {visualEvidence.aesthetic_signature || '—'}</div>
                  {:else if p.id === 'shadow' && shadowProfile}
                    <div><strong>Gölge Hesap:</strong> {shadowProfile.shadow_accounts?.length || 0}</div>
                    <div><strong>Bağlantı Ağırlığı:</strong> {shadowProfile.link_weight !== undefined ? shadowProfile.link_weight : '—'}</div>
                    <div><strong>Koordinasyon:</strong> {shadowProfile.coordination_score !== undefined ? shadowProfile.coordination_score + '%' : '—'}</div>
                  {:else if p.id === 'osint' && osintFootprint}
                    <div><strong>Kullanıcı Adları:</strong> {osintFootprint.usernames?.length || 0}</div>
                    <div><strong>E-posta Sızıntıları:</strong> {osintFootprint.email_leaks?.length || 0}</div>
                    <div><strong>Telefon:</strong> {osintFootprint.phone_exposed == null ? 'Bilinmiyor' : osintFootprint.phone_exposed ? 'Açık' : 'Kapalı'}</div>
                  {:else if p.id === 'resonance' && resonanceCalc}
                    <div><strong>Rezonans Açısı:</strong> {resonanceCalc.resonance_angle !== undefined ? resonanceCalc.resonance_angle + '°' : '—'}</div>
                    <div><strong>Uyum Skoru:</strong> {(resonanceCalc.alignment_score ?? resonanceCalc.compatibility_score) !== undefined ? (resonanceCalc.alignment_score ?? resonanceCalc.compatibility_score) + '%' : '—'}</div>
                    <div><strong>Vektör:</strong> {resonanceCalc.vector_dimensions || '—'} boyut</div>
                  {:else if summary?.chainEntries?.length}
                    <div>{JSON.stringify(summary.chainEntries[0]?.result ?? summary.chainEntries[0]).slice(0, 140)}</div>
                  {:else}
                    <div class="ag-meta">Yapılandırılmış özet bekleniyor...</div>
                  {/if}
                </div>
              {:else}
                <div class="pillar-empty">
                  Henüz veri yok. Analiz başladığında burası dolar.
                </div>
              {/if}
            </article>
          {/each}
        </div>
      </section>

      <!-- Canlı Kanıt Zinciri -->
      <section class="card">
        <div class="section-head">
          <div>
            <h3 class="block-title">CANLI KANIT ZİNCİRİ (evidence_chain — {evidenceChain.length})</h3>
            <p class="section-intro">Ajanların doğruladığı kanıt kayıtları burada sıralanır.</p>
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <span class="pill pill-ok">KANIT ({evidenceChain.length})</span>
            <button type="button" class="btn btn-secondary btn-sm" on:click={() => openHistoryModal('reports')}>
              <Icon name="file" size={0.85} />
              <span>Rapor Üret</span>
            </button>
          </div>
        </div>

        {#if evidenceChain.length > 0}
          <div class="chain-list">
            {#each evidenceChain.slice(0, 12) as item, i}
              {@const ep = item?.epistemic_type || item?.evidence_type || 'kayıt'}
              {@const src = item?.provenance?.engine || item?.source_agent || item?.agent || 'bilinmiyor'}
              {@const conf = item?.uncertainty?.confidence ?? item?.result?.confidence ?? item?.confidence}
              <div class="chain-row">
                <span class="chain-idx">{i + 1}</span>
                <div class="chain-txt">
                  <strong>{item?.agent || 'sistem'}</strong> · [{ep}] · kaynak: {src}
                  {#if typeof conf === 'number'} · güven: {conf <= 1 ? Math.round(conf * 100) : Math.round(conf)}%{/if}
                </div>
              </div>
            {/each}
          </div>
        {:else}
          <div class="empty-state">
            Henüz kaydedilmiş kanıt yok. Bir analiz başlatın veya <strong>Geçmiş &amp; Raporlar</strong>'dan eski bir görevi yükleyin.
          </div>
        {/if}

        <div style="margin-top: 14px;">
          <TaskEvidence task={$taskStatus} />
        </div>
      </section>
    </div>
  </div>

  <!-- 4. AÇILIR KAPANIR CANLI VERİ AKIŞI -->
  <section class="card logs-drawer">
    <button type="button" class="logs-toggle" on:click={() => (logsOpen = !logsOpen)}>
      <span style="display: inline-flex; align-items: center; gap: 8px;">
        <Icon name={logsOpen ? 'chevron-down' : 'chevron-up'} size={0.95} />
        <strong>Canlı Veri Akışı</strong>
        <span class="pill">{$logs.length} kayıt</span>
      </span>
      <span class="ag-meta">{logsOpen ? 'Gizle' : 'Son kayıtları görmek için tıklayın'}</span>
    </button>

    {#if logsOpen}
      <div class="logs-list">
        {#each $logs.slice(-40).reverse() as log}
          <div class="log-line">
            <span class="code-mono ag-meta">{log.ts}</span>
            <span class="pill" class:pill-danger={log.level === 'ERROR'} class:pill-warn={log.level === 'WARNING'}>{log.level}</span>
            <span>{log.msg}</span>
          </div>
        {:else}
          <div class="empty-state">Henüz canlı akış kaydı yok.</div>
        {/each}
      </div>
    {/if}
  </section>
</div>

<style>
  .home-wrap {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .guide-card {
    background: linear-gradient(135deg, var(--bg-surface), var(--bg-elevated));
  }

  .guide-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
  }

  .guide-title-row {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .guide-sub {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .guide-steps {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-top: 12px;
  }

  @media (max-width: 900px) {
    .guide-steps {
      grid-template-columns: 1fr;
    }
  }

  .guide-step {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 10px 12px;
    border-radius: 10px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
  }

  .step-num {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: var(--accent);
    color: var(--accent-contrast);
    font-weight: 700;
    font-size: 12px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .guide-step strong {
    display: block;
    font-size: 13px;
    margin-bottom: 2px;
    color: var(--text-primary);
  }

  .guide-step p {
    font-size: 12px;
    color: var(--text-secondary);
    line-height: 1.45;
  }

  .legal-strip {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 12px;
    color: var(--text-muted);
  }

  .inline-link {
    background: none;
    border: none;
    padding: 0;
    color: var(--accent);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
    text-decoration: underline;
  }

  .hero-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }

  .hero-title {
    font-size: 18px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .target-input-row {
    display: flex;
    gap: 10px;
  }

  .target-input-box {
    position: relative;
    flex: 1;
    display: flex;
    align-items: center;
  }

  .input-prefix {
    position: absolute;
    left: 13px;
    color: var(--text-muted);
    display: inline-flex;
    pointer-events: none;
  }

  .target-main-input {
    width: 100%;
    padding: 12px 14px 12px 38px;
    font-family: inherit;
    font-size: 14px;
    color: var(--text-primary);
    background: var(--bg-input);
    border: 1.5px solid var(--border-strong);
    border-radius: 10px;
    outline: none;
  }

  .target-main-input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .launch-controls-row {
    margin-top: 12px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
  }

  .adult-consent-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 7px 12px;
    border-radius: 8px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-strong);
    font-size: 12.5px;
    font-weight: 600;
    color: var(--text-primary);
    cursor: pointer;
  }

  .adult-consent-badge input {
    accent-color: var(--accent);
    width: 15px;
    height: 15px;
  }

  .launch-main-btn {
    padding: 9px 18px;
  }

  .context-drawer {
    margin-top: 14px;
    padding-top: 14px;
    border-top: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .context-heading {
    font-size: 12px;
    font-weight: 700;
    color: var(--text-secondary);
    margin-bottom: 6px;
  }

  .context-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
  }

  @media (max-width: 900px) {
    .context-grid {
      grid-template-columns: 1fr;
    }
  }

  .phone-action-strip {
    margin-top: 12px;
    padding: 10px 12px;
    border-radius: 9px;
    background: var(--accent-2-soft);
    border: 1px solid rgba(99, 102, 241, 0.35);
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  .consent-check-label {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--text-primary);
    cursor: pointer;
  }

  .phone-meta-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
  }

  @media (max-width: 900px) {
    .phone-meta-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  .meta-lbl {
    display: block;
    font-size: 11px;
    color: var(--text-muted);
    margin-bottom: 2px;
  }

  .phone-links-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: 10px;
  }

  .main-two-col {
    display: grid;
    grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
    gap: 16px;
    align-items: start;
  }

  @media (max-width: 1120px) {
    .main-two-col {
      grid-template-columns: 1fr;
    }
  }

  .col-stack {
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-width: 0;
  }

  .block-title {
    font-size: 15px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .advisors-row {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin-bottom: 10px;
  }

  @media (max-width: 640px) {
    .advisors-row {
      grid-template-columns: 1fr;
    }
  }

  .advisor-card {
    padding: 11px 12px;
    border-radius: 10px;
    border: 1.5px solid var(--border);
    background: var(--bg-elevated);
    cursor: pointer;
    transition: border-color 0.15s ease, background-color 0.15s ease;
  }

  .advisor-card.selected {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .lilith-station.selected {
    border-color: var(--pink);
    background: var(--pink-soft);
  }

  .adv-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 6px;
  }

  .adv-desc {
    font-size: 12px;
    color: var(--text-secondary);
    line-height: 1.4;
  }

  .preset-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;
  }

  .chip-btn {
    padding: 5px 10px;
    border-radius: 999px;
    border: 1px solid var(--border-strong);
    background: var(--bg-elevated);
    color: var(--text-secondary);
    font-family: inherit;
    font-size: 11.5px;
    cursor: pointer;
    text-align: left;
  }

  .chip-btn:hover {
    border-color: var(--accent);
    color: var(--text-primary);
  }

  .chat-feed {
    max-height: 260px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 10px;
    border-radius: 10px;
    background: var(--bg-input);
    border: 1px solid var(--border);
    margin-bottom: 10px;
  }

  .chat-bubble {
    padding: 8px 11px;
    border-radius: 9px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    font-size: 13px;
  }

  .chat-bubble.user {
    background: var(--accent-soft);
    border-color: rgba(16, 185, 129, 0.35);
    align-self: flex-end;
    max-width: 92%;
  }

  .chat-bubble.lilith {
    background: var(--pink-soft);
    border-color: rgba(236, 72, 153, 0.35);
  }

  .bubble-meta {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    font-size: 11px;
    color: var(--text-muted);
    margin-bottom: 3px;
  }

  .bubble-text {
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--text-primary);
  }

  .chat-input-area {
    display: flex;
    gap: 8px;
  }

  .live-models-strip {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    margin-bottom: 10px;
  }

  .agents-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  @media (max-width: 680px) {
    .agents-grid {
      grid-template-columns: 1fr;
    }
  }

  .agent-card {
    text-align: left;
    padding: 9px 11px;
    border-radius: 9px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    color: var(--text-primary);
    font-family: inherit;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .agent-card.selected {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .ag-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 6px;
    font-size: 12px;
  }

  .ag-desc,
  .ag-meta,
  .ag-tier {
    font-size: 11.5px;
    color: var(--text-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .catalog-fold {
    margin-top: 10px;
    font-size: 12.5px;
    color: var(--text-secondary);
  }

  .catalog-fold summary {
    cursor: pointer;
    font-weight: 600;
  }

  .channels-block {
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
  }

  .channels-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .channel-row {
    font-size: 12px;
    padding: 5px 8px;
    border-radius: 6px;
    background: var(--bg-elevated);
    border-left: 3px solid var(--warning);
  }

  .channel-row.ok {
    border-left-color: var(--accent);
  }

  .manual-grid {
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .manual-pair {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  @media (max-width: 640px) {
    .manual-pair {
      grid-template-columns: 1fr;
    }
  }

  .inject-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .inject-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .override-divider {
    margin-top: 8px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
  }

  .pillars-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  @media (max-width: 640px) {
    .pillars-grid {
      grid-template-columns: 1fr;
    }
  }

  .pillar-column {
    padding: 11px 12px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .pillar-column.has-data {
    border-color: rgba(16, 185, 129, 0.45);
    background: var(--accent-soft);
  }

  .pillar-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
  }

  .pillar-name {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 700;
    color: var(--text-primary);
  }

  .pillar-meta-row {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    font-size: 11px;
    color: var(--text-muted);
  }

  .pillar-body {
    font-size: 12px;
    color: var(--text-secondary);
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .pillar-empty {
    font-size: 12px;
    color: var(--text-muted);
  }

  .chain-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .chain-row {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 7px 9px;
    border-radius: 8px;
    background: var(--bg-elevated);
    font-size: 12.5px;
  }

  .chain-idx {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 11px;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .logs-drawer {
    padding: 8px 14px;
  }

  .logs-toggle {
    width: 100%;
    background: transparent;
    border: none;
    color: var(--text-primary);
    font-family: inherit;
    font-size: 13px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    padding: 4px 0;
  }

  .logs-list {
    margin-top: 10px;
    max-height: 210px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 5px;
    border-top: 1px solid var(--border);
    padding-top: 8px;
  }

  .log-line {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--text-secondary);
  }
</style>
