<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import {
    apiFetch, clientId, isAuthFailure, logs, taskStatus, isProcessing,
    apiToken, agentStatuses, vaultLocked, activeViewMode, inspectedAgentId,
    speechState, lastSpeech, voiceEnabled, activeTargetUrl, missionElapsed
  } from '../store';
  import { playClick, playHalt, playRunning } from '../lib/consoleAudio';

  export let telemetryData: any = null;

  // --- 1. HÜKÜMDARLAR KONSEYİ (ASPASIA & LILITH) ---
  const SOVEREIGNS = [
    {
      id: 'aspasia',
      name: 'ASPASIA PRIME',
      short: 'ASPASIA',
      role: 'Bilinç & Baş Stratejist',
      title: 'Sokratik Retorik, Hakikat Aynası ve Empatik Strateji',
      glyph: '👑',
      accent: '#10b981',
      badge: 'BİLİNÇ',
      presets: [
        'Hedefle olan uyumu ve rezonansı stratejik olarak özetle',
        'Hedefin kalkanını kırmadan sahici bir temas stratejisi kur',
        'Kullanıcının frekansına ayna tutarak zayıf/güçlü yönleri değerlendir'
      ]
    },
    {
      id: 'lilith',
      name: 'LILITH GROWTH',
      short: 'LILITH',
      role: 'Bilinçdışı Gölge & Nörobiliş',
      title: 'Dopamin Kancası, Amigdala Uyarımı, Maske Yırtıcı ve Viralite',
      glyph: '🔥',
      accent: '#ec4899',
      badge: 'GÖLGE',
      presets: [
        'Dopaminerjik ödül tahmin hatasıyla beklenti kırıcı viral kanca kurgula',
        'Hedefin vitrindeki duruşu ile bastırılmış narsistik dürtülerini analiz et',
        'Amigdala uyarımı ve kayıptan kaçınma açısıyla hipnotik bir ilk temas yaz'
      ]
    }
  ];

  // --- 2. 12 SAHA AJANI ---
  const FIELD_AGENTS = [
    { id: 'osint_investigator', name: 'OSINT INVESTIGATOR', short: 'OSINT', glyph: '🌐', color: '#8b5cf6', desc: 'Açık kaynak, web ve dijital ayak izi taraması', preset: 'Tüm web platformlarında çapraz kullanıcı adı ve dijital parmak izi tara' },
    { id: 'depth_analyst', name: 'DEPTH ANALYST', short: 'DEPTH', glyph: '🔍', color: '#eab308', desc: 'Gerçeklik endeksi ve kişilik derinliği analizi', preset: 'Kişilik özünü ve sosyal medyadaki yapay maskeyi derinlemesine incele' },
    { id: 'human_behavior', name: 'HUMAN BEHAVIOR', short: 'BEHAVIOR', glyph: '🧬', color: '#f59e0b', desc: 'Dijital cold reading ve aşil tendonu analizi', preset: 'Hedefin alışkanlıklarını, çelişkilerini ve zayıf hassasiyet noktasını çıkar' },
    { id: 'friction_detector', name: 'FRICTION & BOUNDS', short: 'FRICTION', glyph: '⚠️', color: '#ef4444', desc: 'Sınırlar, hassasiyet ve sürtünme dedektörü', preset: 'Konuşulmaması gereken kırmızı çizgileri ve sürtünme tetikleyicilerini belirle' },
    { id: 'pattern_interrupt', name: 'PATTERN INTERRUPT', short: 'PATTERN', glyph: '⚡', color: '#dc2626', desc: 'Beklenti kırma ve temas stratejisi', preset: 'Sıradan mesajların ötesinde ezber bozan bir kalıp kırıcı ilk cümle kur' },
    { id: 'passion_mapper', name: 'PASSION MAPPER', short: 'PASSION', glyph: '✨', color: '#eab308', desc: 'Tutku, neşe ve akış tetikleyicileri haritası', preset: 'Hedefin gözlerini parlatan, gerçek tutkularını ve akış alanlarını haritala' },
    { id: 'cognitive_profiler', name: 'COGNITIVE PROFILER', short: 'COGNITIVE', glyph: '🧠', color: '#06b6d4', desc: 'Bilişsel dil, üslup ve tonlama profili', preset: 'Hedefin kelime dağarcığını, resmiyet derecesini ve iletişim ritmini modelle' },
    { id: 'mirror_truth', name: 'MIRROR TRUTH', short: 'MIRROR', glyph: '🪞', color: '#10b981', desc: 'Öz-frekans yansıtma ve kullanıcı uyumu', preset: 'Kullanıcının ritüelleri ile hedefin profili arasındaki doğal frekans bağını test et' },
    { id: 'autonomous_verifier', name: 'AUTONOMOUS VERIFIER', short: 'VERIFIER', glyph: '🛡️', color: '#a855f7', desc: 'Otonom çapraz doğrulama ve hakem paneli', preset: 'Takipçi/beğeni oranlarındaki bot veya manipülasyon şüphesini denetle' },
    { id: 'resonance_calc', name: 'RESONANCE CALC', short: 'CALC', glyph: '📐', color: '#3b82f6', desc: 'Numpy vektörel rezonans ve açı hesaplaması', preset: 'Çok boyutlu semantik uzayda rezonans ve uyum açısını matematiksel hesapla' },
    { id: 'authenticity_auditor', name: 'AUTHENTICITY AUDITOR', short: 'AUTH', glyph: '👁️', color: '#14b8a6', desc: 'Orijinallik ve güvenilirlik denetimi', preset: 'Gönderilerin doğallığı ile alıntı/kurgu oranını ölçerek maske puanı çıkar' },
    { id: 'resonance_synthesizer', name: 'RESONANCE SYNTH', short: 'SYNTH', glyph: '🌉', color: '#ec4899', desc: 'Sahici köprü sentezi ve önerilen ilk mesaj', preset: 'Tüm bulguları sentezleyerek hedefe ulaşacak en etkili ve zarif köprüyü inşa et' },
  ];

  // --- STATE ---
  let targetUrl = '';
  let selectedAgentId = 'lilith';
  let commandInstruction = '';
  let commandTwinUrl = '';
  let isDispatching = false;
  let dispatchResult: any = null;

  // Komutan Müdahalesi State
  let injectType = 'twin_url';
  let injectValue = '';
  let injectTargetAgent = 'all';
  let injectNote = '';
  let isInjecting = false;
  let injectHistory: Array<{ type: string; value: string; target: string; note: string; ts: string }> = [];

  // Telefon OSINT State
  let isProbingPhone = false;
  let phoneProbeResult: any = null;

  // Sohbet & CRT State
  let chatMessages: Array<{ ts: string; sender: string; text: string }> = [
    { ts: nowTime(), sender: 'Aspasia', text: 'Sistem çevrimiçi Mösyö. 12 saha ajanı ve Lilith konseyde hazır. Hedef profil girin veya dilediğiniz ajana doğrudan emir verin.' }
  ];
  let inputMessage = '';
  let isSending = false;
  let activePillarModal: string | null = null;
  let missionStartTime: number | null = null;
  let missionTimer: any = null;
  let missionElapsedStr = '00:00';

  // 7 Adli Sütun Listesi
  const pillarsList = [
    { id: 'follower',  label: 'FOLLOWER',  tr: 'TAKİPÇİ',  icon: '👥' },
    { id: 'timing',    label: 'TIMING',    tr: 'ZAMAN',    icon: '⏳' },
    { id: 'depth',     label: 'DEPTH',     tr: 'DERİNLİK', icon: '🔍' },
    { id: 'visual',    label: 'VISUAL',    tr: 'GÖRSEL',   icon: '🎨' },
    { id: 'shadow',    label: 'SHADOW',    tr: 'GÖLGE',    icon: '🌑' },
    { id: 'osint',     label: 'OSINT',     tr: 'OSINT',    icon: '🌐' },
    { id: 'resonance', label: 'RESONANCE', tr: 'REZONANS', icon: '⚡' },
  ];

  $: followerAudit = $taskStatus?.follower_audit || null;
  $: timingForensics = $taskStatus?.timing_forensics || null;
  $: depthReport = $taskStatus?.depth_report || null;
  $: visualEvidence = $taskStatus?.visual_evidence || null;
  $: shadowProfile = $taskStatus?.shadow_profile || null;
  $: osintFootprint = $taskStatus?.osint_footprint || null;
  $: resonanceCalc = $taskStatus?.resonance_calc || null;

  const INSUFFICIENT_EVIDENCE = 'YETERSİZ KANIT';

  function hasEvidence(val: any): boolean {
    if (val === null || val === undefined) return false;
    if (typeof val === 'number') return Number.isFinite(val);
    if (typeof val === 'string') return val.trim().length > 0;
    if (Array.isArray(val)) return val.length > 0;
    return true;
  }

  function getPillarHasData(pillarId: string): boolean {
    if (pillarId === 'follower') return hasEvidence(followerAudit);
    if (pillarId === 'timing') return hasEvidence(timingForensics);
    if (pillarId === 'depth') return hasEvidence(depthReport);
    if (pillarId === 'visual') return hasEvidence(visualEvidence);
    if (pillarId === 'shadow') return hasEvidence(shadowProfile);
    if (pillarId === 'osint') return hasEvidence(osintFootprint);
    if (pillarId === 'resonance') return hasEvidence(resonanceCalc);
    return false;
  }

  // Aktif Ajan Algılama
  $: anyActiveAgent = Object.entries($agentStatuses || {}).find(([k, v]) => (v as any)?.status?.toLowerCase() === 'active');
  $: anyActiveAgentKey = anyActiveAgent ? anyActiveAgent[0] : null;

  $: plainLiveStatus = (() => {
    const st = String($taskStatus?.status || '');
    const cur = $taskStatus?.current_agent ? ($taskStatus.current_agent.toUpperCase()) : null;
    const activeLabel = anyActiveAgentKey ? anyActiveAgentKey.toUpperCase() : null;
    const doneCount = $taskStatus?.completed_agents?.length || 0;
    const planCount = $taskStatus?.planned_agents?.length || 12;
    const tName = $taskStatus?.target_profile?.name || $taskStatus?.target_profile?.username || targetUrl || $activeTargetUrl || '';

    if ($isProcessing || st === 'running' || st === 'processing' || anyActiveAgentKey) {
      const step = cur || activeLabel || 'Kazı & Analiz Sürüyor';
      return `⚡ ŞU AN ÇALIŞIYOR: ${tName ? `[${tName}] · ` : ''}${step} (${doneCount}/${planCount} tamamlandı)`;
    }
    if (st && (st === 'completed' || st === 'partially_completed')) {
      return `SON İŞLEM TAMAMLANDI ${tName ? `(${tName})` : ''} — İstihbarat raporları hazır.`;
    }
    return 'HAZIR — Hedef girin, ajana görev verin veya komutan yetkisiyle kanıt mühürleyin.';
  })();

  // Kazıcı Canlı Logları
  $: scraperLogs = ($logs || []).filter(l => {
    const m = (l.msg || '').toUpperCase();
    return m.includes('UPLINK') || m.includes('TELEMETRİ') || m.includes('KAZI') || m.includes('SCRAPE') || m.includes('SENSÖR') || m.includes('INSTAGRAM') || m.includes('X ·');
  }).slice(-30);

  function nowTime() {
    return new Date().toLocaleTimeString('tr-TR', { hour12: false });
  }

  onMount(() => {
    missionTimer = setInterval(() => {
      if (missionStartTime) {
        const diff = Math.floor((Date.now() - missionStartTime) / 1000);
        const m = Math.floor(diff / 60).toString().padStart(2, '0');
        const s = (diff % 60).toString().padStart(2, '0');
        missionElapsedStr = `${m}:${s}`;
        missionElapsed.set(missionElapsedStr);
      }
    }, 1000);

    return () => {
      if (missionTimer) clearInterval(missionTimer);
    };
  });

  function selectAgent(agentId: string) {
    selectedAgentId = agentId;
    playClick(400, 30);
    const sov = SOVEREIGNS.find(s => s.id === agentId);
    if (sov && sov.presets.length > 0) {
      commandInstruction = sov.presets[0];
    } else {
      const fa = FIELD_AGENTS.find(a => a.id === agentId);
      if (fa && fa.preset) commandInstruction = fa.preset;
    }
  }

  // --- ACTIONS ---
  async function launchAnalysis() {
    const url = targetUrl.trim();
    if (!url || $isProcessing) return;
    isProcessing.set(true);
    activeTargetUrl.set(url);
    missionStartTime = Date.now();
    playRunning();

    chatMessages = [...chatMessages, {
      ts: nowTime(),
      sender: 'Aspasia',
      text: `Hedef profil kilitlendi Mösyö: [${url}]. 12 kişilik ajan timi ve kazıcı sensörler sahada.`
    }];

    try {
      const res = await apiFetch('/api/initiate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId,
          url,
          rituals: '',
          playlist: '',
          envies: '',
          scraper_type: 'cross',
        })
      });
      if (!res.ok) {
        if (isAuthFailure(res)) throw new Error('PINEAL_TOKEN yetki hatası');
        if (res.status === 423) throw new Error('KASA KİLİTLİ (423): Lütfen üst paneldeki Kasa mandalını açın.');
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson?.error?.message || errJson?.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      if (data.task_id) {
        taskStatus.update(s => ({ ...(s || {}), task_id: data.task_id, status: 'processing' }));
      }
    } catch (e: any) {
      isProcessing.set(false);
      playHalt();
      chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: `Görev başlatılamadı: ${e?.message || e}` }];
    }
  }

  function isPhoneInput(val: string): boolean {
    if (!val) return false;
    const clean = val.trim();
    if (clean.startsWith('http://') || clean.startsWith('https://')) return false;
    const digits = clean.replace(/[^\d]/g, '');
    return digits.length >= 7 && (clean.includes('(') || clean.includes('-') || clean.startsWith('+') || clean.startsWith('0') || digits.length >= 10);
  }

  async function probePhoneAction() {
    const phone = targetUrl.trim();
    if (!phone || isProbingPhone) return;
    isProbingPhone = true;
    playClick(480, 50);

    chatMessages = [...chatMessages, {
      ts: nowTime(),
      sender: 'OSINT İSTİHBARAT',
      text: `📱 Telefon numarası analiz ediliyor: [${phone}] (Operatör, şebeke ve mesajlaşma protokolleri taranıyor...)`
    }];

    try {
      const res = await apiFetch('/api/commander/phone-probe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          phone,
          auto_bridge_social: true
        })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      phoneProbeResult = await res.json();
      playClick(700, 60);

      const m = phoneProbeResult.metadata;
      chatMessages = [...chatMessages, {
        ts: nowTime(),
        sender: 'OSINT İSTİHBARAT',
        text: `📱 [${m.e164 || phone}] Şebeke: ${m.carrier_name || 'Bilinmiyor'} | Bölge: ${m.country_name} | Tür: ${m.line_type}. WhatsApp ve Telegram doğrudan linkleri hazırlandı.`
      }];
    } catch (e: any) {
      playHalt();
      chatMessages = [...chatMessages, {
        ts: nowTime(),
        sender: 'OSINT İSTİHBARAT',
        text: `Telefon sorgulaması başarısız: ${e?.message || e}`
      }];
    } finally {
      isProbingPhone = false;
    }
  }

  async function dispatchAgentTask() {
    if (!commandInstruction.trim() || isDispatching) return;
    isDispatching = true;
    playClick(500, 40);

    const payload = {
      client_id: $clientId || 'default',
      agent_id: selectedAgentId,
      instruction: commandInstruction.trim(),
      target_url: targetUrl || $activeTargetUrl || '',
      twin_url: commandTwinUrl.trim(),
      context: {
        bio: $taskStatus?.target_profile?.bio || '',
        posts: $taskStatus?.target_profile?.posts || [],
      }
    };

    try {
      const res = await apiFetch('/api/commander/dispatch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      dispatchResult = await res.json();
      playClick(600, 50);

      const agentName = SOVEREIGNS.find(s => s.id === selectedAgentId)?.name || FIELD_AGENTS.find(a => a.id === selectedAgentId)?.name || selectedAgentId.toUpperCase();
      chatMessages = [...chatMessages, {
        ts: nowTime(),
        sender: agentName,
        text: dispatchResult.output_text || 'Görev sonuçlandırıldı.'
      }];
    } catch (e: any) {
      playHalt();
      dispatchResult = {
        status: 'error',
        agent_id: selectedAgentId,
        thought_chain: ['Aksaklık oluştu: ' + (e?.message || e)],
        output_text: 'Ajana görev iletilirken bir hata yaşandı.',
      };
    } finally {
      isDispatching = false;
    }
  }

  async function injectCommanderEvidence() {
    if (!injectValue.trim() || isInjecting) return;
    isInjecting = true;
    playClick(450, 40);

    try {
      const res = await apiFetch('/api/commander/inject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          evidence_type: injectType,
          evidence_value: injectValue.trim(),
          target_agent: injectTargetAgent,
          note: injectNote.trim()
        })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      playClick(700, 60);

      injectHistory = [{
        type: injectType,
        value: injectValue.trim(),
        target: injectTargetAgent,
        note: injectNote.trim(),
        ts: nowTime()
      }, ...injectHistory];

      chatMessages = [...chatMessages, {
        ts: nowTime(),
        sender: 'KOMUTAN MÜDAHALESİ',
        text: `Gerçeklik Enjekte Edildi [${injectType.toUpperCase()}]: "${injectValue.trim()}" -> ${injectTargetAgent.toUpperCase()} ajanına mühürlendi.`
      }];
      injectValue = '';
      injectNote = '';
    } catch (e: any) {
      playHalt();
      alert('Enjeksiyon başarısız: ' + (e?.message || e));
    } finally {
      isInjecting = false;
    }
  }

  async function sendAspasiaMessage() {
    const text = inputMessage.trim();
    if (!text || isSending) return;
    inputMessage = '';
    isSending = true;
    chatMessages = [...chatMessages, { ts: nowTime(), sender: 'SİZ', text }];

    try {
      const res = await apiFetch('/api/aspasia/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: $clientId, message: text })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const reply = data.reply || data.response || 'Mesajınız alındı Mösyö.';
      chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: reply }];
    } catch (e: any) {
      chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: `Bağlantı kesintisi: ${e?.message || e}` }];
    } finally {
      isSending = false;
    }
  }

  function toggleVaultLock() {
    vaultLocked.update(v => !v);
    playClick(400, 30);
  }

  function togglePillar(id: string) {
    activePillarModal = activePillarModal === id ? null : id;
    playClick(300, 20);
  }
</script>

<div class="master-cockpit-layout">
  <!-- ==================== 1. ÜST COMMAND HUD ==================== -->
  <header class="master-hud-header">
    <div class="hud-brand">
      <span class="pulse-beacon" class:active={$isProcessing}></span>
      <div class="brand-titles">
        <h1 class="brand-title">PINEAL HERETIC // MASTER MISSION COCKPIT</h1>
        <span class="live-status-badge">{plainLiveStatus}</span>
      </div>
    </div>

    <!-- HEDEF KASETİ -->
    <div class="target-cassette-bar">
      <div class="cassette-input-wrap">
        <span class="cassette-icon">🎯</span>
        <input
          type="text"
          class="cassette-text-input"
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
      {#if isPhoneInput(targetUrl)}
        <button
          class="phone-launch-btn"
          class:is-running={isProbingPhone}
          on:click={probePhoneAction}
          disabled={isProbingPhone}
          title="Numarayı OSINT Sensörleriyle Tara"
        >
          {isProbingPhone ? '📱 TARANIYOR...' : '📱 NUMARAYI SORGULA'}
        </button>
      {/if}
      <button
        class="cassette-launch-btn"
        class:is-running={$isProcessing}
        on:click={launchAnalysis}
        disabled={$isProcessing || !targetUrl.trim()}
      >
        {$isProcessing ? '⚡ KAZILIYOR...' : '▶ KAZIYI BAŞLAT'}
      </button>
    </div>

    <!-- SAĞ SİSTEM METRİKLERİ -->
    <div class="hud-meters">
      <div class="hud-meter-box" title="Geçen Görev Süresi">
        <span class="hm-icon">⏱️</span>
        <span class="hm-val">{missionElapsedStr}</span>
      </div>
      <button
        class="vault-lock-btn"
        class:locked={$vaultLocked}
        on:click={toggleVaultLock}
        title={$vaultLocked ? 'Kasa Kilitli (OSINT korumalı) — Tıkla ve Aç' : 'Kasa Açık — Tıkla ve Kilitle'}
      >
        <span class="vault-dot"></span>
        <span class="vault-label">{$vaultLocked ? 'KASA KİLİTLİ' : 'KASA AÇIK'}</span>
      </button>
    </div>
  </header>

  <!-- ==================== 2. ANA 3 SÜTUNLU GÖVDE ==================== -->
  <main class="master-grid-container">

    <!-- SÜTUN 1: HÜKÜMDARLAR KONSEYİ & KOMUTAN MÜDAHALESİ (Sol - 28%) -->
    <section class="column-deck col-left">
      <div class="deck-title-ribbon">
        <span class="ribbon-icon">👑</span>
        <h2>HÜKÜMDARLAR & KOMUTA</h2>
      </div>

      <!-- ASPASIA PRIME -->
      <div
        class="sovereign-station aspasia-station {selectedAgentId === 'aspasia' ? 'selected' : ''}"
        on:click={() => selectAgent('aspasia')}
      >
        <div class="station-header">
          <span class="station-glyph">👑</span>
          <div>
            <h3 class="station-name">ASPASIA PRIME</h3>
            <span class="station-role">Bilinç & Baş Stratejist</span>
          </div>
          <span class="station-badge badge-green">BİLİNÇ</span>
        </div>
        <p class="station-desc">Sokratik Retorik, Hakikat Aynası, Taktiksel Sentez ve Empatik Strateji</p>
        <div class="station-presets">
          {#each SOVEREIGNS[0].presets as p}
            <button class="preset-btn" on:click|stopPropagation={() => { selectAgent('aspasia'); commandInstruction = p; }}>
              ⚡ {p.slice(0, 36)}...
            </button>
          {/each}
        </div>
      </div>

      <!-- LILITH GROWTH -->
      <div
        class="sovereign-station lilith-station {selectedAgentId === 'lilith' ? 'selected' : ''}"
        on:click={() => selectAgent('lilith')}
      >
        <div class="station-header">
          <span class="station-glyph">🔥</span>
          <div>
            <h3 class="station-name">LILITH GROWTH</h3>
            <span class="station-role">Bilinçdışı Gölge & Nörobiliş</span>
          </div>
          <span class="station-badge badge-pink">GÖLGE</span>
        </div>
        <p class="station-desc">Dopamin Kancası, Amigdala Uyarımı, Maske Yırtıcı ve Viralite</p>

        <!-- CANLI NÖROKİMYA FORMÜL METRİKLERİ -->
        <div class="lilith-neuro-meters">
          <div class="nm-row">
            <span class="nm-name">DOPAMİN (Ödül):</span>
            <div class="nm-bar-track"><div class="nm-fill fill-dopamine" style="width: 85%;"></div></div>
            <span class="nm-score">85%</span>
          </div>
          <div class="nm-row">
            <span class="nm-name">SEROTONİN (Statü):</span>
            <div class="nm-bar-track"><div class="nm-fill fill-serotonin" style="width: 72%;"></div></div>
            <span class="nm-score">72%</span>
          </div>
          <div class="nm-row">
            <span class="nm-name">KORTİZOL (Aciliyet):</span>
            <div class="nm-bar-track"><div class="nm-fill fill-cortisol" style="width: 40%;"></div></div>
            <span class="nm-score">40%</span>
          </div>
          <div class="nm-viral-chip">
            <span>VİRAL KATSAYI (Vc):</span>
            <strong class="highlight-green">2.84</strong>
          </div>
        </div>

        <div class="station-presets">
          {#each SOVEREIGNS[1].presets as p}
            <button class="preset-btn btn-pink" on:click|stopPropagation={() => { selectAgent('lilith'); commandInstruction = p; }}>
              🔥 {p.slice(0, 36)}...
            </button>
          {/each}
        </div>
      </div>

      <!-- KOMUTAN MÜDAHALESİ ("İşte bu da onun!") -->
      <div class="commander-override-box">
        <div class="box-header">
          <span class="box-icon">🛡️</span>
          <h3>KOMUTAN MÜDAHALESİ ("İşte bu da onun!")</h3>
        </div>
        <p class="box-sub">Ajanlar kazarken benzerini veya ikizini bulamazsa, limitsiz komutan yetkinizle doğrudan sisteme zorla enjekte edin.</p>

        <div class="override-form">
          <div class="form-dual-fields">
            <select bind:value={injectType} class="select-field">
              <option value="twin_url">İkiz Profil URL (Twin URL)</option>
              <option value="phone">📱 Telefon Numarası / GSM</option>
              <option value="bio_fact">Gerçek Biyo / Meslek Bilgisi</option>
              <option value="ground_truth">Kesin Gerçeklik (Ground Truth)</option>
              <option value="note">Kritik Taktik Not</option>
            </select>
            <select bind:value={injectTargetAgent} class="select-field">
              <option value="all">Tüm Ajanlar (Genel Hafıza)</option>
              <option value="lilith">Lilith (Gölge & Kanca)</option>
              <option value="osint_investigator">OSINT Investigator</option>
              <option value="depth_analyst">Depth Analyst</option>
            </select>
          </div>
          <input
            type="text"
            class="input-field"
            bind:value={injectValue}
            placeholder="Kanıtı girin (Örn: https://x.com/gercek_hesap veya 'Mesleği Mimar')..."
          />
          <button
            class="override-submit-btn"
            class:injecting={isInjecting}
            on:click={injectCommanderEvidence}
            disabled={isInjecting || !injectValue.trim()}
          >
            {isInjecting ? '⚡ ENJEKTE EDİLİYOR...' : '🔥 KANITI ZORLA ENJEKTE ET & KAZIYI GÜNCELLE'}
          </button>
        </div>

        {#if injectHistory.length > 0}
          <div class="inject-history-ticker">
            <span class="ticker-title">MÜHÜRLENEN KANITLAR:</span>
            {#each injectHistory.slice(0, 2) as h}
              <div class="ticker-row">
                <span class="t-type">[{h.type.toUpperCase()}]</span>
                <span class="t-val">{h.value}</span>
                <span class="t-agent">→ {h.target}</span>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </section>

    <!-- SÜTUN 2: CANLI SAHA BORU HATTI, DİREKT GÖREV & MUHAKEME (Orta - 44%) -->
    <section class="column-deck col-center">
      <div class="deck-title-ribbon">
        <span class="ribbon-icon">⚡</span>
        <h2>12 SAHA AJANI & CANLI MUHAKEME (CHAIN-OF-THOUGHT)</h2>
      </div>

      <!-- 12 SAHA AJANI MATRİSİ -->
      <div class="field-matrix-grid">
        {#each FIELD_AGENTS as ag}
          {@const rStatus = $agentStatuses?.[ag.id]?.status || $taskStatus?.runs?.[ag.id]?.status || 'Wait'}
          <div
            class="agent-matrix-chip {selectedAgentId === ag.id ? 'is-selected' : ''} {rStatus.toLowerCase()}"
            on:click={() => selectAgent(ag.id)}
            title="{ag.name}: {ag.desc}"
          >
            <span class="agent-pulse-lamp"></span>
            <span class="agent-glyph">{ag.glyph}</span>
            <span class="agent-code">{ag.short}</span>
            <span class="agent-status-tag">{rStatus.toUpperCase()}</span>
          </div>
        {/each}
      </div>

      <!-- SEÇİLİ AJANA DİREKT EMİR & CANLI MUHAKEME TERMİNALİ -->
      <div class="direct-dispatch-console">
        <div class="console-header-bar">
          <div class="console-agent-identity">
            <span class="ca-tag">DİREKT MUHATAP:</span>
            <strong class="ca-name">{selectedAgentId.toUpperCase()}</strong>
          </div>
          <span class="ca-hint">İstediğin ajana istediğin görevi ver; düşünce aşamalarını canlı izle.</span>
        </div>

        <div class="console-input-row">
          <input
            type="text"
            class="console-text-input"
            bind:value={commandInstruction}
            placeholder="> {selectedAgentId.toUpperCase()} için özel emir veya soru..."
            disabled={isDispatching}
            on:keydown={(e) => { if (e.key === 'Enter') dispatchAgentTask(); }}
          />
          <input
            type="text"
            class="console-twin-input"
            bind:value={commandTwinUrl}
            placeholder="İkiz URL (Opsiyonel)..."
            disabled={isDispatching}
          />
          <button
            class="console-dispatch-btn"
            class:running={isDispatching}
            on:click={dispatchAgentTask}
            disabled={isDispatching || !commandInstruction.trim()}
          >
            {isDispatching ? '⚡ ÇALIŞIYOR...' : '🔥 GÖREVİ VER'}
          </button>
        </div>

        <!-- CANLI DÜŞÜNCE ZİNCİRİ (CHAIN-OF-THOUGHT) -->
        <div class="cot-reasoning-stream">
          <div class="stream-header">
            <span>🧠 CANLI DÜŞÜNCE ADIMLARI (CHAIN-OF-THOUGHT):</span>
            {#if isDispatching}<span class="thinking-glow">● DÜŞÜNÜYOR</span>{/if}
          </div>
          {#if dispatchResult}
            <div class="cot-steps-list">
              {#each dispatchResult.thought_chain || [] as step, idx}
                <div class="cot-step-item">
                  <span class="cot-num">#{idx + 1}</span>
                  <span class="cot-msg">{step}</span>
                </div>
              {/each}
            </div>
            <div class="cot-final-result">
              <span class="cfr-label">AJANIN NİHAİ RAPORU:</span>
              <p class="cfr-text">{dispatchResult.output_text}</p>
            </div>
          {:else}
            <div class="cot-idle-placeholder">
              <p>Herhangi bir ajanı seçip görev verdiğinizde, arka planda yürüttüğü içsel muhakeme, hipotez testleri ve nihai çıkarımları burada anlık olarak akacaktır.</p>
            </div>
          {/if}
        </div>
      </div>

      <!-- CANLI KAZICI RADARI (RAW SCRAPER FEED) -->
      <div class="raw-scraper-radar">
        <div class="radar-hud-bar">
          <div class="rh-target">
            <span>📡 KAZICI SENSÖR AKIŞI:</span>
            <strong>{targetUrl || $activeTargetUrl || 'Hedef Bekleniyor'}</strong>
          </div>
          <div class="rh-metrics">
            <span>Gönderiler: <strong>{($taskStatus?.target_profile?.posts || []).length}</strong></span>
            <span>Linkler: <strong>{($taskStatus?.target_profile?.detected_urls || []).length}</strong></span>
          </div>
        </div>

        <div class="radar-packet-terminal">
          {#each scraperLogs as l}
            <div class="packet-line">
              <span class="p-ts">[{l.ts}]</span>
              <span class="p-level {l.level.toLowerCase()}">[{l.level}]</span>
              <span class="p-text">{l.msg}</span>
            </div>
          {/each}
          {#if scraperLogs.length === 0}
            <p class="p-empty">Kazıcı sensörler beklemede. Hedef kasetine profil girip "KAZIYI BAŞLAT" butonuna basın.</p>
          {/if}
        </div>
      </div>
    </section>

    <!-- SÜTUN 3: İSTİHBARAT & 7 SÜTUN (Sağ - 28%) -->
    <section class="column-deck col-right">
      <div class="deck-title-ribbon">
        <span class="ribbon-icon">🎯</span>
        <h2>İSTİHBARAT & 7 SÜTUN</h2>
      </div>

      <!-- 7 ADLİ SÜTUN MATRİSİ -->
      <div class="pillars-tactical-grid">
        {#each pillarsList as p}
          {@const hasData = getPillarHasData(p.id)}
          <button
            class="pillar-tactical-card {hasData ? 'has-data' : ''} {activePillarModal === p.id ? 'active' : ''}"
            on:click={() => togglePillar(p.id)}
          >
            <div class="ptc-top">
              <span class="ptc-icon">{p.icon}</span>
              <span class="ptc-name">{p.label}</span>
            </div>
            <span class="ptc-tr">{p.tr}</span>
            <span class="ptc-status-pill">{hasData ? '✓ VERİ VAR' : '○ BEKLEMEDE'}</span>
          </button>
        {/each}
      </div>

      <!-- HEDEF PROFİL DOSYASI ÖZETİ -->
      <div class="target-dossier-card">
        <div class="td-header">
          <span>📋 HEDEF DOSYASI RAPORU</span>
          <span class="td-user">{$taskStatus?.target_profile?.username || $taskStatus?.target_profile?.name || 'Hedef'}</span>
        </div>
        <div class="td-body">
          <div class="td-row">
            <span class="td-lbl">Biyografi:</span>
            <p class="td-val">{$taskStatus?.target_profile?.bio || 'Henüz biyografi çekilmedi.'}</p>
          </div>
          <div class="td-row-dual">
            <div class="td-chip">
              <span class="td-lbl">Gerçeklik Endeksi:</span>
              <strong class="td-highlight">{hasEvidence(depthReport?.reality_index) ? `%${(depthReport.reality_index * 100).toFixed(0)}` : 'Ölçülmedi'}</strong>
            </div>
            <div class="td-chip">
              <span class="td-lbl">Uyum Skoru:</span>
              <strong class="td-highlight">{hasEvidence(resonanceCalc?.compatibility_score) ? `%${(resonanceCalc.compatibility_score * 100).toFixed(0)}` : 'Ölçülmedi'}</strong>
            </div>
          </div>

          <!-- TESPİT EDİLEN BAĞLANTILAR -->
          <div class="td-detected-links">
            <span class="td-lbl">Tespit Edilen Çapraz Ağlar:</span>
            <div class="td-link-pills">
              {#each ($taskStatus?.target_profile?.detected_urls || []) as link}
                <a href={link} target="_blank" rel="noopener noreferrer" class="link-pill">{link.replace(/https?:\/\/(www\.)?/, '').slice(0, 24)}...</a>
              {/each}
              {#if ($taskStatus?.target_profile?.detected_urls || []).length === 0}
                <span class="td-muted">Çapraz bağlantı henüz taranmadı.</span>
              {/if}
            </div>
          </div>
        </div>
      </div>

      <!-- 📱 TELEFON OSINT İSTİHBARAT KARTI -->
      {#if phoneProbeResult}
        <div class="phone-osint-dossier-card">
          <div class="pod-header">
            <span class="pod-icon">📱</span>
            <div class="pod-title-block">
              <span class="pod-title">TELEFON OSINT İSTİHBARATI</span>
              <strong class="pod-num">{phoneProbeResult.metadata?.e164 || phoneProbeResult.phone_input}</strong>
            </div>
            <button class="pod-close-btn" on:click={() => { phoneProbeResult = null; }}>✕</button>
          </div>

          <div class="pod-grid">
            <div class="pod-chip">
              <span class="pod-lbl">Operatör / Şebeke:</span>
              <strong class="pod-val highlight-gold">{phoneProbeResult.metadata?.carrier_name || 'Bilinmiyor'}</strong>
            </div>
            <div class="pod-chip">
              <span class="pod-lbl">Ülke & Bölge:</span>
              <span class="pod-val">{phoneProbeResult.metadata?.country_name || 'Türkiye'}</span>
            </div>
            <div class="pod-chip">
              <span class="pod-lbl">Hat Türü:</span>
              <span class="pod-val">{phoneProbeResult.metadata?.line_type || 'MOBILE'}</span>
            </div>
            <div class="pod-chip">
              <span class="pod-lbl">Doğruluk:</span>
              <span class="pod-val highlight-green">{phoneProbeResult.metadata?.is_valid ? '✓ Geçerli GSM' : 'Doğrulanamadı'}</span>
            </div>
          </div>

          <!-- MESAJLAŞMA PROTOKOLLERİ -->
          <div class="pod-messaging-strip">
            <span class="pod-sub-title">Açık Profil / Doğrudan Kanallar:</span>
            <div class="pod-actions-row">
              {#each phoneProbeResult.messaging_probes || [] as mp}
                <a
                  href={mp.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  class="pod-action-pill {mp.platform.toLowerCase()}"
                  title={mp.note}
                >
                  <span class="pill-dot"></span>
                  <strong>{mp.platform}</strong> Profilini Aç
                </a>
              {/each}
            </div>
          </div>

          <!-- TESPİT EDİLEN KULLANICI ADLARI / AĞLAR -->
          {#if (phoneProbeResult.associated_handles || []).length > 0}
            <div class="pod-handles-strip">
              <span class="pod-sub-title">İlişkili Kullanıcı Adları (@):</span>
              <div class="pod-handle-pills">
                {#each phoneProbeResult.associated_handles as handle}
                  <button
                    class="pod-handle-btn"
                    on:click={() => { targetUrl = handle; launchAnalysis(); }}
                    title="Bu kullanıcı adını doğrudan kazıya al"
                  >
                    @{handle} ➔ [KAZIYA AL]
                  </button>
                {/each}
              </div>
            </div>
          {/if}

          <!-- BULUNAN SOSYAL AĞLAR -->
          {#if (phoneProbeResult.social_probes || []).length > 0}
            <div class="pod-social-strip">
              <span class="pod-sub-title">Tespit Edilen Sosyal Profiller:</span>
              <div class="pod-social-pills">
                {#each phoneProbeResult.social_probes as sp}
                  <a href={sp.url} target="_blank" rel="noopener noreferrer" class="pod-social-pill">
                    {sp.platform.toUpperCase()}: @{sp.handle}
                  </a>
                {/each}
              </div>
            </div>
          {/if}

          <!-- KOMUTAN KANITI ENJEKTE ET -->
          <button
            class="pod-inject-btn"
            on:click={() => {
              injectType = 'phone';
              injectValue = `${phoneProbeResult.metadata?.e164 || phoneProbeResult.phone_input} (${phoneProbeResult.metadata?.carrier_name || 'Bilinmiyor'})`;
              injectCommanderEvidence();
            }}
          >
            🔥 Bu Numarayı Komutan Kanıtı Olarak Mühürle
          </button>
        </div>
      {/if}

      <!-- SİSTEM TELEMETRİSİ -->
      <div class="system-health-card">
        <div class="sh-header">
          <span>📊 SİSTEM NÖRAL TELEMETRİSİ</span>
          <span class="sh-beacon">CANLI UPLINK</span>
        </div>
        <div class="sh-grid">
          <div class="sh-item">
            <span class="sh-label">Sensör Motoru:</span>
            <span class="sh-val highlight-green">Twscrape & Playwright</span>
          </div>
          <div class="sh-item">
            <span class="sh-label">LLM Gateway:</span>
            <span class="sh-val highlight-green">Aktif / Router OK</span>
          </div>
          <div class="sh-item">
            <span class="sh-label">Bellek Mührü:</span>
            <span class="sh-val">{injectHistory.length} Kanıt Kayıtlı</span>
          </div>
          <div class="sh-item">
            <span class="sh-label">Protokol:</span>
            <span class="sh-val">WSS Çift Yönlü</span>
          </div>
        </div>
      </div>
    </section>
  </main>

  <!-- ==================== 3. ALT DİYALOG & KOMUT SATIRI ==================== -->
  <footer class="master-bottom-dock">
    <div class="bottom-chat-terminal">
      <div class="bct-stream">
        {#each chatMessages as msg}
          <div class="bct-line {msg.sender === 'SİZ' ? 'user-line' : 'aspasia-line'}">
            <span class="bct-ts">[{msg.ts}]</span>
            <span class="bct-sender">{msg.sender}</span>
            <span class="bct-sep">&gt;</span>
            <span class="bct-text">{msg.text}</span>
          </div>
        {/each}
        {#if isSending}
          <div class="bct-line typing-line">
            <span class="bct-ts">[{nowTime()}]</span>
            <span class="bct-sender">Aspasia</span>
            <span class="bct-sep">&gt;</span>
            <span class="bct-text typing-glow">Sokratik muhakeme yapılıyor, rezonans hesaplanıyor...</span>
          </div>
        {/if}
      </div>

      <div class="bct-input-bar">
        <input
          type="text"
          class="bct-input"
          bind:value={inputMessage}
          placeholder="> Aspasia ile konuşun veya sisteme doğrudan komut verin (Enter)..."
          disabled={isSending}
          on:keydown={(e) => { if (e.key === 'Enter') sendAspasiaMessage(); }}
        />
        <button class="bct-send-btn" on:click={sendAspasiaMessage} disabled={isSending || !inputMessage.trim()}>
          GÖNDER
        </button>
      </div>
    </div>
  </footer>

  <!-- ==================== 4. ADLİ RAPOR MODALI ==================== -->
  {#if activePillarModal}
    <div class="forensic-backdrop" role="presentation" on:click={() => activePillarModal = null} on:keydown={(e) => { if (e.key === 'Escape') activePillarModal = null; }}>
      <div class="forensic-card" role="dialog" aria-modal="true" tabindex="-1" on:click|stopPropagation on:keydown|stopPropagation>
        <div class="forensic-card-header">
          <span class="card-title">ADLİ SÜTUN RAPORU: {activePillarModal.toUpperCase()}</span>
          <button class="close-x" on:click={() => activePillarModal = null}>✕</button>
        </div>
        <div class="forensic-card-body">
          {#if activePillarModal === 'follower' && followerAudit}
            <div class="report-block">
              <h4>Takipçi & Kitle Bütünlüğü</h4>
              <p>Hüküm: <strong>{followerAudit.verdict || 'BİLİNMİYOR'}</strong> ({followerAudit.verdict_code || 'nominal'})</p>
              <p>
                Takipçi Sayısı:
                {#if hasEvidence(followerAudit.follower_count)}{followerAudit.follower_count}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}
                · Takip: {#if hasEvidence(followerAudit.following_count)}{followerAudit.following_count}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}
              </p>
              <p>Etkileşim Katsayısı: {#if hasEvidence(followerAudit.engagement_rate)}{followerAudit.engagement_rate}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Veri Tamlığı: {#if hasEvidence(followerAudit.data_completeness)}%{(followerAudit.data_completeness * 100).toFixed(0)}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
            </div>
          {:else if activePillarModal === 'timing' && timingForensics}
            <div class="report-block">
              <h4>Zaman & Sirkadiyen Forensik</h4>
              <p>Gece Payı: {#if hasEvidence(timingForensics.night_share)}%{(timingForensics.night_share * 100).toFixed(0)}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Tepe Saati: {#if hasEvidence(timingForensics.peak_hour)}{timingForensics.peak_hour}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Medyan Kayma: {#if hasEvidence(timingForensics.median_drift_hours)}{timingForensics.median_drift_hours}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if} saat</p>
            </div>
          {:else if activePillarModal === 'depth' && depthReport}
            <div class="report-block">
              <h4>Derinlik & Alıntı Kalkanı</h4>
              <p>Gerçeklik İndeksi: {#if hasEvidence(depthReport.reality_index)}%{(depthReport.reality_index * 100).toFixed(0)}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Öz Çıkarım: {#if hasEvidence(depthReport.essence_one_liner)}{depthReport.essence_one_liner}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
            </div>
          {:else if activePillarModal === 'visual' && visualEvidence}
            <div class="report-block">
              <h4>Görsel & Estetik Forensik</h4>
              <p>Estetik Stil: {#if hasEvidence(visualEvidence.aesthetic_style)}{visualEvidence.aesthetic_style}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Özet: {#if hasEvidence(visualEvidence.visual_evidence_summary)}{visualEvidence.visual_evidence_summary}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
            </div>
          {:else if activePillarModal === 'shadow' && shadowProfile}
            <div class="report-block">
              <h4>Gölge Profili (Karanlık Üçlü)</h4>
              <p>Narsisizm Skoru: {#if shadowProfile.trait_scores_measured === true && hasEvidence(shadowProfile.dark_profile?.narcissism)}{shadowProfile.dark_profile?.narcissism}{:else}<span class="evidence-insufficient" title="Trait skoru üretilmedi — derinlik stratejisi ayrı bir metriktir">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Tespit Edilen Strateji: {#if hasEvidence(shadowProfile.strategy)}{shadowProfile.strategy}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
            </div>
          {:else if activePillarModal === 'osint' && osintFootprint}
            <div class="report-block">
              <h4>OSINT Dijital Ayak İzi</h4>
              <p>İlişkili Platformlar: {#if hasEvidence(osintFootprint.associated_platforms)}{osintFootprint.associated_platforms.join(', ')}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
            </div>
          {:else if activePillarModal === 'resonance' && resonanceCalc}
            <div class="report-block">
              <h4>Rezonans & Uyum</h4>
              <p>Uyum Skoru: {#if hasEvidence(resonanceCalc.compatibility_score)}%{(resonanceCalc.compatibility_score * 100).toFixed(0)}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Yaklaşım Protokolü: {#if hasEvidence(resonanceCalc.recommended_approach)}{resonanceCalc.recommended_approach}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
            </div>
          {:else}
            <div class="report-block">
              <h4>{activePillarModal.toUpperCase()} Sinyali</h4>
              <p>Bu sütun için henüz aktif analiz verisi işlenmedi veya ÜRETİLEMEDİ. Hedef kasetine profil girip CAPTURE tuşuna basın.</p>
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  /* =========================================================
     MASTER COCKPIT FULLSCREEN TITANIUM & DARK GLASS THEME
     ========================================================= */
  :global(body) {
    margin: 0;
    padding: 0;
    background: #02060f;
    color: #e2e8f0;
    font-family: 'JetBrains Mono', 'Segoe UI', monospace;
    overflow: hidden;
  }

  .master-cockpit-layout {
    width: 100vw;
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: radial-gradient(circle at 50% 15%, #081124 0%, #030712 65%, #01040a 100%);
    box-sizing: border-box;
    overflow: hidden;
  }

  /* 1. ÜST COMMAND HUD */
  .master-hud-header {
    height: 52px;
    background: rgba(8, 14, 28, 0.95);
    border-bottom: 1px solid rgba(212, 175, 55, 0.35);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
    gap: 16px;
    z-index: 100;
    backdrop-filter: blur(12px);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.8);
  }

  .hud-brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .pulse-beacon {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 10px #10b981;
  }

  .pulse-beacon.active {
    background: #f59e0b;
    box-shadow: 0 0 14px #f59e0b;
    animation: beaconPulse 1s infinite alternate;
  }

  @keyframes beaconPulse {
    from { transform: scale(0.9); opacity: 0.7; }
    to { transform: scale(1.2); opacity: 1; }
  }

  .brand-titles {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .brand-title {
    margin: 0;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0.1em;
    color: #d4af37;
    text-shadow: 0 0 10px rgba(212, 175, 55, 0.4);
  }

  .live-status-badge {
    font-size: 10px;
    color: #94a3b8;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 480px;
  }

  .target-cassette-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    max-width: 640px;
  }

  .cassette-input-wrap {
    flex: 1;
    display: flex;
    align-items: center;
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid rgba(212, 175, 55, 0.4);
    border-radius: 4px;
    padding: 0 10px;
    gap: 8px;
  }

  .cassette-icon { font-size: 14px; }

  .cassette-text-input {
    flex: 1;
    height: 32px;
    background: transparent;
    border: none;
    outline: none;
    color: #fde68a;
    font-family: inherit;
    font-size: 11px;
    font-weight: 600;
  }

  .cassette-launch-btn {
    height: 34px;
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    border: 1px solid #34d399;
    border-radius: 4px;
    color: #fff;
    font-family: inherit;
    font-size: 11px;
    font-weight: 700;
    padding: 0 16px;
    cursor: pointer;
    white-space: nowrap;
    box-shadow: 0 0 12px rgba(16, 185, 129, 0.4);
    transition: all 0.2s ease;
  }

  .cassette-launch-btn:hover {
    box-shadow: 0 0 20px rgba(16, 185, 129, 0.7);
  }

  .cassette-launch-btn.is-running {
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    border-color: #fbbf24;
    box-shadow: 0 0 14px rgba(245, 158, 11, 0.5);
  }

  .hud-meters {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .hud-meter-box {
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid rgba(100, 116, 139, 0.3);
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 700;
    color: #fde68a;
  }

  .vault-lock-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid #10b981;
    color: #34d399;
    padding: 5px 12px;
    border-radius: 4px;
    font-family: inherit;
    font-size: 10px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .vault-lock-btn.locked {
    background: rgba(239, 68, 68, 0.15);
    border-color: #ef4444;
    color: #ef4444;
  }

  .vault-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 8px currentColor;
  }

  /* 2. ANA 3 SÜTUNLU GÖVDE */
  .master-grid-container {
    flex: 1;
    display: grid;
    grid-template-columns: 28% 44% 28%;
    gap: 12px;
    padding: 12px;
    box-sizing: border-box;
    overflow: hidden;
  }

  .column-deck {
    background: rgba(6, 12, 24, 0.75);
    border: 1px solid rgba(212, 175, 55, 0.22);
    border-radius: 6px;
    padding: 10px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    overflow-y: auto;
    box-shadow: inset 0 0 15px rgba(0, 0, 0, 0.8);
  }

  .deck-title-ribbon {
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid rgba(212, 175, 55, 0.25);
    padding-bottom: 6px;
  }

  .deck-title-ribbon h2 {
    margin: 0;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.08em;
    color: #d4af37;
  }

  /* SÜTUN 1: HÜKÜMDARLAR */
  .sovereign-station {
    background: rgba(11, 18, 33, 0.85);
    border-radius: 6px;
    padding: 10px;
    border: 1px solid rgba(100, 116, 139, 0.3);
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .aspasia-station { border-color: rgba(16, 185, 129, 0.4); }
  .aspasia-station.selected {
    border-color: #10b981;
    background: rgba(16, 185, 129, 0.12);
    box-shadow: 0 0 16px rgba(16, 185, 129, 0.35);
  }

  .lilith-station { border-color: rgba(236, 72, 153, 0.4); }
  .lilith-station.selected {
    border-color: #ec4899;
    background: rgba(236, 72, 153, 0.12);
    box-shadow: 0 0 16px rgba(236, 72, 153, 0.35);
  }

  .station-header {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .station-glyph { font-size: 20px; }
  .station-name { margin: 0; font-size: 12px; font-weight: 800; color: #fde68a; }
  .station-role { font-size: 9px; color: #94a3b8; }

  .station-badge {
    margin-left: auto;
    font-size: 8px;
    font-weight: 800;
    padding: 2px 6px;
    border-radius: 3px;
  }
  .badge-green { background: #10b981; color: #000; }
  .badge-pink { background: #ec4899; color: #000; }

  .station-desc {
    font-size: 9px;
    color: #cbd5e1;
    margin: 6px 0;
    line-height: 1.35;
  }

  .station-presets {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 6px;
  }

  .preset-btn {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 3px;
    color: #cbd5e1;
    font-family: inherit;
    font-size: 9px;
    padding: 4px 8px;
    text-align: left;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .preset-btn:hover {
    background: rgba(16, 185, 129, 0.2);
    border-color: #10b981;
    color: #38ef7d;
  }

  .btn-pink:hover {
    background: rgba(236, 72, 153, 0.2);
    border-color: #ec4899;
    color: #f472b6;
  }

  /* LILITH NÖROKİMYA */
  .lilith-neuro-meters {
    background: rgba(5, 8, 16, 0.9);
    border: 1px solid rgba(236, 72, 153, 0.3);
    border-radius: 4px;
    padding: 6px 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin: 6px 0;
  }

  .nm-row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 8px;
  }

  .nm-name { width: 95px; color: #94a3b8; }

  .nm-bar-track {
    flex: 1;
    height: 5px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 3px;
    overflow: hidden;
  }

  .nm-fill { height: 100%; border-radius: 3px; }
  .fill-dopamine { background: linear-gradient(90deg, #ec4899, #f43f5e); }
  .fill-serotonin { background: linear-gradient(90deg, #38bdf8, #818cf8); }
  .fill-cortisol { background: linear-gradient(90deg, #eab308, #f97316); }

  .nm-score { font-weight: 700; color: #fde68a; width: 28px; text-align: right; }

  .nm-viral-chip {
    display: flex;
    justify-content: space-between;
    font-size: 9px;
    border-top: 1px solid rgba(236, 72, 153, 0.2);
    padding-top: 4px;
    color: #fde68a;
  }

  /* KOMUTAN MÜDAHALESİ */
  .commander-override-box {
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid rgba(245, 158, 11, 0.4);
    border-radius: 6px;
    padding: 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .box-header { display: flex; align-items: center; gap: 6px; }
  .box-header h3 { margin: 0; font-size: 11px; font-weight: 800; color: #f59e0b; }
  .box-sub { margin: 0; font-size: 9px; color: #94a3b8; line-height: 1.35; }

  .override-form {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .form-dual-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }

  .select-field, .input-field {
    background: #030712;
    border: 1px solid rgba(212, 175, 55, 0.35);
    border-radius: 4px;
    color: #fde68a;
    font-family: inherit;
    font-size: 9px;
    padding: 6px 8px;
    outline: none;
  }

  .override-submit-btn {
    background: linear-gradient(135deg, #f59e0b 0%, #b45309 100%);
    border: 1px solid #fbbf24;
    border-radius: 4px;
    color: #000;
    font-family: inherit;
    font-size: 10px;
    font-weight: 800;
    padding: 7px;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .inject-history-ticker {
    border-top: 1px solid rgba(245, 158, 11, 0.25);
    padding-top: 4px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .ticker-title { font-size: 8px; font-weight: 700; color: #10b981; }
  .ticker-row { font-size: 8px; color: #cbd5e1; display: flex; gap: 4px; }
  .t-type { color: #f59e0b; }
  .t-val { color: #38bdf8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 130px; }
  .t-agent { color: #ec4899; }

  /* SÜTUN 2: 12 AJAN & MUHAKEME */
  .field-matrix-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
  }

  .agent-matrix-chip {
    background: rgba(11, 19, 36, 0.85);
    border: 1px solid rgba(100, 116, 139, 0.3);
    border-radius: 4px;
    padding: 6px 4px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    cursor: pointer;
    transition: all 0.15s ease;
    position: relative;
  }

  .agent-matrix-chip.is-selected {
    border-color: #38ef7d;
    background: rgba(16, 185, 129, 0.15);
    box-shadow: 0 0 10px rgba(56, 239, 125, 0.3);
  }

  .agent-matrix-chip.active {
    border-color: #f59e0b;
    box-shadow: 0 0 12px #f59e0b;
  }

  .agent-pulse-lamp {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: #64748b;
  }

  .agent-matrix-chip.active .agent-pulse-lamp {
    background: #f59e0b;
    box-shadow: 0 0 6px #f59e0b;
    animation: beaconPulse 1s infinite alternate;
  }

  .agent-matrix-chip.done .agent-pulse-lamp {
    background: #10b981;
    box-shadow: 0 0 4px #10b981;
  }

  .agent-glyph { font-size: 14px; }
  .agent-code { font-size: 9px; font-weight: 700; color: #fde68a; }
  .agent-status-tag { font-size: 7px; color: #94a3b8; }

  /* DİREKT GÖREV & MUHAKEME */
  .direct-dispatch-console {
    background: rgba(3, 7, 16, 0.92);
    border: 1px solid rgba(212, 175, 55, 0.35);
    border-radius: 6px;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .console-header-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 9px;
  }

  .ca-tag { color: #94a3b8; }
  .ca-name { color: #f59e0b; margin-left: 4px; }
  .ca-hint { color: #64748b; font-size: 8px; }

  .console-input-row {
    display: flex;
    gap: 6px;
  }

  .console-text-input {
    flex: 2;
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid rgba(212, 175, 55, 0.4);
    border-radius: 4px;
    color: #fde68a;
    font-family: inherit;
    font-size: 10px;
    padding: 6px 8px;
    outline: none;
  }

  .console-twin-input {
    flex: 1;
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid rgba(56, 189, 248, 0.4);
    border-radius: 4px;
    color: #38bdf8;
    font-family: inherit;
    font-size: 10px;
    padding: 6px 8px;
    outline: none;
  }

  .console-dispatch-btn {
    background: linear-gradient(135deg, #ec4899 0%, #be185d 100%);
    border: 1px solid #f472b6;
    border-radius: 4px;
    color: #fff;
    font-family: inherit;
    font-size: 10px;
    font-weight: 700;
    padding: 0 14px;
    cursor: pointer;
    white-space: nowrap;
    box-shadow: 0 0 10px rgba(236, 72, 153, 0.4);
  }

  .console-dispatch-btn.running {
    background: #f59e0b;
    border-color: #fbbf24;
  }

  .cot-reasoning-stream {
    background: #02050c;
    border: 1px solid rgba(56, 189, 248, 0.25);
    border-radius: 4px;
    padding: 8px;
    max-height: 140px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .stream-header {
    display: flex;
    justify-content: space-between;
    font-size: 9px;
    font-weight: 700;
    color: #38bdf8;
  }

  .thinking-glow { color: #f59e0b; animation: beaconPulse 1s infinite alternate; }

  .cot-steps-list {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .cot-step-item {
    font-size: 9px;
    color: #cbd5e1;
    display: flex;
    gap: 6px;
    line-height: 1.35;
  }

  .cot-num { color: #f59e0b; font-weight: 700; }

  .cot-final-result {
    border-top: 1px solid rgba(56, 189, 248, 0.2);
    padding-top: 4px;
    margin-top: 4px;
  }

  .cfr-label { font-size: 8px; color: #fde68a; font-weight: 700; }
  .cfr-text { margin: 2px 0 0; font-size: 10px; color: #38ef7d; line-height: 1.4; }
  .cot-idle-placeholder p { margin: 0; font-size: 9px; color: #64748b; font-style: italic; }

  /* KAZICI RADARI */
  .raw-scraper-radar {
    background: #02050c;
    border: 1px solid rgba(16, 185, 129, 0.3);
    border-radius: 6px;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
    min-height: 100px;
  }

  .radar-hud-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 9px;
    border-bottom: 1px solid rgba(16, 185, 129, 0.2);
    padding-bottom: 4px;
  }

  .rh-target { color: #34d399; font-weight: 700; }
  .rh-metrics { display: flex; gap: 8px; color: #fde68a; }

  .radar-packet-terminal {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 9px;
  }

  .packet-line { display: flex; gap: 6px; }
  .p-ts { color: #64748b; }
  .p-level.info { color: #38bdf8; }
  .p-level.warning { color: #f59e0b; }
  .p-level.error { color: #ef4444; }
  .p-text { color: #cbd5e1; }
  .p-empty { color: #64748b; font-size: 9px; margin: 4px 0; }

  /* SÜTUN 3: İSTİHBARAT & 7 SÜTUN */
  .pillars-tactical-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 4px;
  }

  .pillar-tactical-card {
    background: rgba(11, 19, 36, 0.85);
    border: 1px solid rgba(100, 116, 139, 0.3);
    border-radius: 4px;
    padding: 6px 4px;
    cursor: pointer;
    font-family: inherit;
    text-align: left;
    transition: all 0.15s ease;
  }

  .pillar-tactical-card.has-data {
    border-color: #10b981;
    background: rgba(16, 185, 129, 0.15);
  }

  .pillar-tactical-card.active {
    border-color: #f59e0b;
    box-shadow: 0 0 10px #f59e0b;
  }

  .ptc-top { display: flex; align-items: center; gap: 4px; }
  .ptc-icon { font-size: 11px; }
  .ptc-name { font-size: 9px; font-weight: 700; color: #fde68a; }
  .ptc-tr { font-size: 7px; color: #94a3b8; display: block; }
  .ptc-status-pill { font-size: 7px; color: #64748b; margin-top: 2px; display: block; }
  .pillar-tactical-card.has-data .ptc-status-pill { color: #38ef7d; font-weight: 700; }

  /* HEDEF DOSYASI */
  .target-dossier-card {
    background: rgba(11, 19, 36, 0.85);
    border: 1px solid rgba(212, 175, 55, 0.3);
    border-radius: 6px;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .td-header { display: flex; justify-content: space-between; font-size: 9px; font-weight: 700; color: #d4af37; border-bottom: 1px solid rgba(212, 175, 55, 0.2); padding-bottom: 4px; }
  .td-user { color: #38bdf8; }
  .td-body { display: flex; flex-direction: column; gap: 4px; }
  .td-row { font-size: 9px; }
  .td-lbl { color: #94a3b8; font-size: 8px; }
  .td-val { margin: 2px 0 0; color: #e2e8f0; line-height: 1.35; font-size: 9px; }

  .td-row-dual { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
  .td-chip { background: rgba(3, 7, 18, 0.8); border: 1px solid rgba(100, 116, 139, 0.25); border-radius: 4px; padding: 4px 6px; font-size: 9px; }
  .td-highlight { color: #38ef7d; display: block; font-size: 11px; }

  .td-link-pills { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 2px; }
  .link-pill { background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 3px; color: #38bdf8; font-size: 8px; padding: 2px 5px; text-decoration: none; }
  .td-muted { color: #64748b; font-size: 8px; font-style: italic; }

  /* SİSTEM SAĞLIĞI */
  .system-health-card {
    background: rgba(11, 19, 36, 0.85);
    border: 1px solid rgba(56, 189, 248, 0.25);
    border-radius: 6px;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .sh-header { display: flex; justify-content: space-between; font-size: 9px; font-weight: 700; color: #38bdf8; border-bottom: 1px solid rgba(56, 189, 248, 0.2); padding-bottom: 4px; }
  .sh-beacon { color: #10b981; font-size: 8px; }
  .sh-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
  .sh-item { background: rgba(3, 7, 18, 0.7); border-radius: 3px; padding: 3px 6px; font-size: 8px; display: flex; flex-direction: column; gap: 2px; }
  .sh-label { color: #64748b; }
  .sh-val { color: #e2e8f0; font-weight: 700; }
  .highlight-green { color: #10b981; }

  /* 3. ALT DİYALOG & SOHBET MERKEZİ */
  .master-bottom-dock {
    height: 110px;
    background: rgba(3, 7, 16, 0.96);
    border-top: 1px solid rgba(16, 185, 129, 0.35);
    display: flex;
    flex-direction: column;
    padding: 6px 12px;
    box-sizing: border-box;
    z-index: 100;
  }

  .bottom-chat-terminal {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 4px;
    overflow: hidden;
  }

  .bct-stream {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 10px;
  }

  .bct-line { display: flex; gap: 6px; line-height: 1.3; }
  .bct-ts { color: #64748b; }
  .bct-sender { font-weight: 700; color: #d4af37; }
  .user-line .bct-sender { color: #38bdf8; }
  .bct-sep { color: #10b981; }
  .bct-text { color: #e2e8f0; }

  .bct-input-bar {
    display: flex;
    gap: 6px;
    height: 30px;
  }

  .bct-input {
    flex: 1;
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid rgba(16, 185, 129, 0.4);
    border-radius: 4px;
    color: #38ef7d;
    font-family: inherit;
    font-size: 10px;
    padding: 0 10px;
    outline: none;
  }

  .bct-send-btn {
    background: #10b981;
    border: none;
    border-radius: 4px;
    color: #000;
    font-family: inherit;
    font-size: 10px;
    font-weight: 700;
    padding: 0 16px;
    cursor: pointer;
  }

  /* 4. ADLİ RAPOR MODALI */
  .forensic-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.85);
    z-index: 99999;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .forensic-card {
    background: #050b14;
    border: 1px solid #d4af37;
    border-radius: 6px;
    padding: 14px;
    max-width: 520px;
    width: 90%;
    color: #e2e8f0;
  }

  .forensic-card-header {
    display: flex;
    justify-content: space-between;
    font-weight: 700;
    color: #d4af37;
    border-bottom: 1px solid rgba(212, 175, 55, 0.3);
    padding-bottom: 6px;
  }

  .close-x {
    background: none;
    border: none;
    color: #cbd5e1;
    font-size: 14px;
    cursor: pointer;
  }

  /* PHONE PROBE STYLES */
  .phone-launch-btn {
    background: linear-gradient(135deg, #0284c7, #0369a1);
    color: #ffffff;
    border: 1px solid #38bdf8;
    padding: 7px 14px;
    border-radius: 4px;
    font-family: inherit;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.05em;
    cursor: pointer;
    box-shadow: 0 0 12px rgba(56, 189, 248, 0.4);
    transition: all 0.2s ease;
  }
  .phone-launch-btn:hover:not(:disabled) {
    background: linear-gradient(135deg, #38bdf8, #0284c7);
    box-shadow: 0 0 18px rgba(56, 189, 248, 0.6);
  }
  .phone-launch-btn.is-running {
    animation: pulse 1.2s infinite;
  }

  .phone-osint-dossier-card {
    background: rgba(3, 15, 28, 0.92);
    border: 1px solid #0284c7;
    border-radius: 6px;
    padding: 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    box-shadow: 0 0 16px rgba(2, 132, 199, 0.25);
  }
  .pod-header {
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid rgba(2, 132, 199, 0.3);
    padding-bottom: 6px;
  }
  .pod-icon {
    font-size: 16px;
  }
  .pod-title-block {
    flex: 1;
    display: flex;
    flex-direction: column;
  }
  .pod-title {
    font-size: 9px;
    color: #38bdf8;
    letter-spacing: 0.08em;
    font-weight: 700;
  }
  .pod-num {
    font-size: 13px;
    color: #f8fafc;
    font-family: monospace;
    letter-spacing: 0.05em;
  }
  .pod-close-btn {
    background: none;
    border: none;
    color: #94a3b8;
    cursor: pointer;
    font-size: 14px;
  }
  .pod-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;
  }
  .pod-chip {
    background: rgba(15, 23, 42, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 4px;
    padding: 5px 7px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .pod-lbl {
    font-size: 8.5px;
    color: #94a3b8;
    text-transform: uppercase;
  }
  .pod-val {
    font-size: 11px;
    color: #e2e8f0;
    font-weight: 600;
  }
  .pod-messaging-strip, .pod-handles-strip, .pod-social-strip {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 2px;
  }
  .pod-sub-title {
    font-size: 9px;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .pod-actions-row, .pod-handle-pills, .pod-social-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .pod-action-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 10px;
    padding: 4px 8px;
    border-radius: 3px;
    text-decoration: none;
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid #334155;
    color: #f1f5f9;
    transition: all 0.15s ease;
  }
  .pod-action-pill.whatsapp {
    border-color: #22c55e;
    color: #4ade80;
  }
  .pod-action-pill.whatsapp:hover {
    background: rgba(34, 197, 94, 0.2);
  }
  .pod-action-pill.telegram {
    border-color: #0ea5e9;
    color: #38bdf8;
  }
  .pod-action-pill.telegram:hover {
    background: rgba(14, 165, 233, 0.2);
  }
  .pill-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
  }
  .pod-handle-btn {
    background: rgba(168, 85, 247, 0.15);
    border: 1px solid #a855f7;
    color: #c084fc;
    font-size: 10px;
    font-weight: 700;
    padding: 3px 6px;
    border-radius: 3px;
    cursor: pointer;
  }
  .pod-handle-btn:hover {
    background: rgba(168, 85, 247, 0.35);
  }
  .pod-social-pill {
    background: rgba(244, 63, 94, 0.15);
    border: 1px solid #f43f5e;
    color: #fb7185;
    font-size: 9.5px;
    padding: 3px 6px;
    border-radius: 3px;
    text-decoration: none;
  }
  .pod-inject-btn {
    margin-top: 4px;
    background: rgba(212, 175, 55, 0.12);
    border: 1px solid #d4af37;
    color: #d4af37;
    font-family: inherit;
    font-size: 10px;
    font-weight: 700;
    padding: 6px 10px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  .pod-inject-btn:hover {
    background: #d4af37;
    color: #000;
  }

  .evidence-insufficient {
    color: #ef4444;
    border-bottom: 1px dashed rgba(239, 68, 68, 0.6);
    font-size: 0.85em;
    padding: 0 2px;
  }
</style>
