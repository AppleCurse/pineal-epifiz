<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import {
    apiToken, currentApiToken, apiFetch, clientId, wsUrl, logs, taskStatus,
    speechState, lastSpeech, voiceEnabled,
    isProcessing, powerEngaged, recordEngaged, agentStatuses, vaultLocked,
    activeViewMode, agentStatusSource, supportRequests, supportTaskId, refreshSupport, mergeTaskSnapshot
  } from './store';
  import { uplinkState } from './lib/telemetry';
  import AtlasPinealCockpit from './components/AtlasPinealCockpit.svelte';
  import TacticalWarRoom from './components/TacticalWarRoom.svelte';
  // [P6 · CANLI PANEL] Canlı kontrol paneli: ajan hattı, anlık kanal, muhakeme,
  // kanıt akışı ve çağrı izi — hepsi MEVCUT SoT'tan (WS + /api/aspasia/state).
  import LiveControlPanel from './components/LiveControlPanel.svelte';
  import AgentRack from './components/AgentRack.svelte';
  import HolographicResonanceMesh from './components/HolographicResonanceMesh.svelte';
  import SpiderFootCockpit from './components/SpiderFootCockpit.svelte';
  import NeuralTelemetryBoard from './components/visualizers/NeuralTelemetryBoard.svelte';
  import SupportPanel from './components/SupportPanel.svelte';

  let ws: WebSocket | null = null;
  let reconnectAttempts = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;
  let lastToken = currentApiToken();
  let telemetryData: any = null;
  let telemetryPoll: any = null;
  let evidenceGraph: any = null;
  let graphMessage = 'Görev seçilmedi';
  let graphGeneration = 0;
  $: graphTaskId = $taskStatus?.task_id || '';
  $: graphRoom = $clientId;
  $: if ($activeViewMode === 'control') loadEvidenceGraph(graphTaskId, graphRoom);

  async function loadEvidenceGraph(taskId: string, roomId: string) {
    const generation = ++graphGeneration;
    evidenceGraph = null;
    if (!taskId) { graphMessage = 'Görev seçilmedi'; return; }
    graphMessage = 'Kanıt grafı yükleniyor';
    try {
      const res = await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}/graph?client_id=${encodeURIComponent(roomId)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const graph = await res.json();
      if (generation !== graphGeneration) return;
      evidenceGraph = graph;
      graphMessage = graph.available ? 'Kanıt grafı' : `Kanıt grafı kullanılamıyor: ${graph.reason || 'veri yok'}`;
    } catch (error: any) {
      if (generation !== graphGeneration) return;
      graphMessage = `Kanıt grafı yüklenemedi: ${error?.message || 'hata'}`;
    }
  }

  let activeSpeechAudio: HTMLAudioElement | null = null;
  let activeSpeechObjectUrl: string | null = null;
  let speechPlaybackRequest: AbortController | null = null;
  let speechPlaybackGeneration = 0;

  function stopActiveSpeechAudio() {
    speechPlaybackGeneration += 1;
    speechPlaybackRequest?.abort();
    speechPlaybackRequest = null;
    const audio = activeSpeechAudio;
    activeSpeechAudio = null;
    if (audio) {
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      try { audio.currentTime = 0; } catch {}
    }
    if (activeSpeechObjectUrl) {
      URL.revokeObjectURL(activeSpeechObjectUrl);
      activeSpeechObjectUrl = null;
    }
  }

  function reportSpeechPlaybackFinished(playbackId: string) {
    if (!/^[0-9a-f]{32}$/.test(playbackId)) return;
    void apiFetch('/api/speech/finished', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: get(clientId) || 'default', playback_id: playbackId }),
    }).catch(() => {});
  }

  async function playSpeechUrl(path: string, playbackId: string) {
    stopActiveSpeechAudio();
    const generation = speechPlaybackGeneration;
    const controller = new AbortController();
    speechPlaybackRequest = controller;
    try {
      // Use apiFetch so protected deployments send X-API-Key without putting
      // credentials in the audio URL (HTMLAudioElement cannot set that header).
      const response = await apiFetch(path, { signal: controller.signal });
      if (!response.ok) throw new Error(`speech_audio_http_${response.status}`);
      const blob = await response.blob();
      if (generation !== speechPlaybackGeneration || !get(voiceEnabled)) return;

      const objectUrl = URL.createObjectURL(blob);
      activeSpeechObjectUrl = objectUrl;
      const audio = new Audio(objectUrl);
      activeSpeechAudio = audio;
      speechPlaybackRequest = null;
      const finish = () => {
        if (activeSpeechAudio !== audio) return;
        stopActiveSpeechAudio();
        speechState.set("idle");
        reportSpeechPlaybackFinished(playbackId);
      };
      audio.onended = finish;
      audio.onerror = finish;
      await audio.play();
    } catch (_error) {
      if (generation === speechPlaybackGeneration) {
        stopActiveSpeechAudio();
        speechState.set("idle");
        reportSpeechPlaybackFinished(playbackId);
      }
    }
  }

  // [AUDIT 2026-10-07 · Madde 6] Telemetri panosu GÖRÜNÜR olsun.
  // Eskiden bileşen `display: none` içinde basılıyordu: DOM'da vardı
  // ama kullanıcı HİÇ göremiyordu (gözlemlenebilirlik fiilen sıfır).
  // Varsayılan AÇIK; isteyen kullanıcı bilinçli olarak kapatabilir.
  let telemetryVisible = true;
  let tauriUnlisteners: (() => void)[] = [];

  // [ATLAS EPIFIZ 2026-11-09] Intro / Karşılama katmanı + ambient fon
  // İlk açılışta gösterilir (localStorage ile hatırlanır), içeride ambient olarak kalır.
  let showIntro = true;
  function enterAtlas() {
    showIntro = false;
    try { localStorage.setItem('pineal_atlas_intro_seen', '1'); } catch {}
  }
  function reopenIntro() {
    showIntro = true;
  }

  async function fetchTelemetry() {
    // [RÖNTGEN 2026-09-23] Başarısız okumada telemetryData ESKİ değeriyle
    // kalıyordu: pano "canlı" görünen BAYAT veriyi basmaya devam ediyordu.
    // Sözleşme: okuma yoksa veri de yok (null) → pano OFFLINE basar.
    try {
      const res = await apiFetch('/api/telemetry');
      if (!res.ok) throw new Error('http ' + res.status);
      {
        telemetryData = await res.json();
        // Vault kilit durumu
        if (telemetryData.vault_locked !== undefined) {
          vaultLocked.set(telemetryData.vault_locked);
        }
        // Agent statuses - backend'den gelen toplu durum
        if (telemetryData.agent_statuses && Object.keys(telemetryData.agent_statuses).length > 0) {
          const mapped: Record<string, any> = {};
          for (const [k, v] of Object.entries(telemetryData.agent_statuses)) {
            const val: any = v;
            mapped[k] = {
              status: val.status || 'Wait',
              updatedAt: Date.now(),
              metadata: val.metadata || {}
            };
          }
          // Sadece gerçek veri varsa güncelle
          if (Object.keys(mapped).length > 0) {
            agentStatuses.update(s => ({ ...s, ...mapped }));
          }
        }
      }
    } catch (_e) {
      telemetryData = null;
    }
  }

  function recording(): boolean {
    return get(recordEngaged);
  }

  function logLine(level: string, msg: string) {
    if (!recording()) return;
    logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level, msg }]);
  }

  function handleAgentStatusUpdate(payload: any) {
    // payload: { agent_id, status, timestamp, metadata } veya JSON string
    let data = payload;
    if (typeof payload === 'string') {
      try { data = JSON.parse(payload); } catch { return; }
    }
    // Tauri event: { payload: {...} } veya direkt
    if (data.payload) data = data.payload;
    // Bazı Tauri emit'leri { event_type, data } şeklinde
    if (data.data && typeof data.data === 'string') {
      try { data = JSON.parse(data.data); } catch { /* keep */ }
    }

    const agentId = data.agent_id || data.agent_name;
    const status = data.status || data.step_name;
    if (!agentId || !status) return;

    agentStatuses.update(s => ({
      ...s,
      [agentId]: {
        status,
        updatedAt: Date.now(),
        metadata: data.metadata || {}
      }
    }));

    // Log da bas
    if (status.toLowerCase() === 'active') {
      logLine('INFO', `AGENT RACK: ${agentId} -> ACTIVE`);
    }
  }

  function connect() {
    if (disposed) return;
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
    try {
      ws = new WebSocket(wsUrl($clientId));
    } catch (_e) {
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      reconnectAttempts = 0;
      uplinkState.set('ONLINE');
      const token = currentApiToken();
      if (token && ws) ws.send(JSON.stringify({ type: 'auth', token }));
      logLine("INFO", "UPLINK KURULDU (FastAPI WebSocket + Agent Rack)");
      // [B0] Kopma → yeniden bağlanma: açık destek talepleri kalıcı
      // checkpoint'ten GERİ YÜKLENİR (süreç/kayıp yaşamaz).
      refreshSupport(get(supportTaskId));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "speech") {
          // [FAZ C · C2] Konuşma durumu TEK kaynaktan (backend) gelir:
          // arayüz kendi kendine "konuşuyorum" uydurmaz.
          lastSpeech.set(data);
          if (data.state === "speaking") {
            stopActiveSpeechAudio();
            speechState.set("speaking");
            if (get(voiceEnabled) && data.url) {
              void playSpeechUrl(data.url, String(data.playback_id || ''));
            }
          } else {
            stopActiveSpeechAudio();
            if (data.state === "denied") {
              speechState.set("denied");
            } else if (data.state === "interrupted") {
              speechState.set("interrupted");
            } else if (data.state === "listening") {
              speechState.set("listening");
            } else {
              speechState.set("idle");
            }
          }
        } else if (data.type === "log") {
          if (!recording()) return;
          logs.update(l => [...l, data].slice(-80));
        } else if (data.type === "agent_status_update") {
          handleAgentStatusUpdate(data);
        } else if (data.event && data.event_type === 'AwaitingHuman') {
          // [B0] Destek talebi GÖRÜNÜR: kayıt + panel + log. Detay/kimlik
          // alanları kalıcı checkpoint'ten REST ile tazelenir.
          const humanEvent = data.event;
          supportTaskId.set(humanEvent.task_id || null);
          refreshSupport(humanEvent.task_id);
          logLine('WARNING', `DESTEK TALEBİ: ${humanEvent.agent_name || ''} — ${String(humanEvent.reason || '').slice(0, 180)}`);
        } else if (data.event && data.event.event_type) {
          if (recording()) {
            const evt = data.event;
            const msg = `[${evt.event_type}] ${evt.agent_name || ''} - ${evt.input_summary || evt.step_name || evt.error_message || ''}`;
            logs.update(l => [...l, { ts: new Date(data.timestamp).toLocaleTimeString(), level: evt.severity || "INFO", msg }].slice(-80));
          }
          // EventBus fallback -> Agent Rack
          if (data.event.agent_name) {
            const agentName = data.event.agent_name;
            let rackStatus = 'Wait';
            if (data.event.event_type === 'TaskStarted') rackStatus = 'Active';
            if (data.event.event_type === 'StepCompleted') rackStatus = 'Ready';
            if (data.event.event_type === 'ErrorHalt') rackStatus = 'Wait';
            handleAgentStatusUpdate({ agent_id: agentName, status: rackStatus });
          }
        } else if (data.type === "snapshot_update") {
          if (!data.task_id) return;
          taskStatus.update(s => mergeTaskSnapshot(s, data));
          // Snapshot içinde current_agent varsa onu Active yap
          if (data.current_agent) {
            handleAgentStatusUpdate({ agent_id: data.current_agent, status: 'Active' });
          }
        } else if (data.type === "result") {
          if (!data.task_id) return;
          taskStatus.update(s => mergeTaskSnapshot(s, data));
          isProcessing.set(false);
          const terminal = String(data.status || "").toLowerCase();
          const okStates = ["completed", "partially_completed"];
          logLine(okStates.includes(terminal) ? "INFO" : "ERROR", "OPERASYON SONUÇLANDI: " + data.status);
          // Rack states describe availability; a task result must not rewrite
          // other agents (or other concurrent tasks) as Ready.
        }
      } catch(e) {
        console.error("WS parse error", e);
      }
    };

    ws.onclose = (event) => {
      if (disposed) return;
      uplinkState.set('OFFLINE');
      if (!get(powerEngaged)) return;
      scheduleReconnect();
    };

    ws.onerror = () => {};
  }

  function scheduleReconnect() {
    if (disposed) return;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 15000);
    reconnectAttempts += 1;
    reconnectTimer = setTimeout(connect, delay);
  }

  async function setupTauriListeners() {
    try {
      // Dinamik import - sadece Tauri ortamında var
      const { listen } = await import('@tauri-apps/api/event');

      const unlistenTelemetry = await listen('pineal-telemetry', (event: any) => {
        // Telemetri event'i geldi
        try {
          let payload = event.payload;
          if (typeof payload === 'string') {
            try { payload = JSON.parse(payload); } catch {}
          }
          if (payload?.data) {
            let inner = payload.data;
            if (typeof inner === 'string') {
              try { inner = JSON.parse(inner); } catch {}
            }
            // Agent fallback
            if (inner?.event?.agent_name) {
              const agentName = inner.event.agent_name;
              let rackStatus = 'Wait';
              if (inner.event.event_type === 'TaskStarted') rackStatus = 'Active';
              if (inner.event.event_type === 'StepCompleted') rackStatus = 'Ready';
              handleAgentStatusUpdate({ agent_id: agentName, status: rackStatus });
            }
          }
        } catch (e) {
          console.debug('Tauri telemetry parse', e);
        }
      });

      const unlistenAgent = await listen('pineal-agent-status', (event: any) => {
        handleAgentStatusUpdate(event.payload || event);
      });

      tauriUnlisteners.push(unlistenTelemetry, unlistenAgent);
      console.log('[Tauri] Agent Rack + Telemetry listener aktif');
      logLine('INFO', 'TAURI NATIVE: GPU hızlandırmalı köprü aktif + Agent Rack canlı');
    } catch (e) {
      // Tarayıcı ortamı - Tauri API yok, sorun değil
      console.debug('Tauri API yok (browser mod)', e);
    }
  }

  onMount(() => {
    try {
      if (localStorage.getItem('pineal_atlas_intro_seen') === '1') showIntro = false;
    } catch {}
    telemetryVisible = false;
    connect();
    setupTauriListeners();
    const unsubVoice = voiceEnabled.subscribe((enabled) => {
      if (!enabled) {
        stopActiveSpeechAudio();
        if (get(speechState) === "speaking") {
          void apiFetch(`/api/speech/stop?client_id=${encodeURIComponent(get(clientId))}`, {
            method: "POST",
          }).catch(() => {});
        }
      }
    });

    // Telemetri panosu canlı beslenir
    fetchTelemetry();
    telemetryPoll = setInterval(fetchTelemetry, 4000);

    // Agent status polling fallback - WS yoksa bile REST'ten besle
    const agentPoll = setInterval(async () => {
      try {
        const res = await apiFetch('/api/agents/status');
        if (res.ok) {
          const data = await res.json();
          // Backend kaynağı beyan eder (redis_bus / in_memory / fallback /
          // error): UI bunu basar, süs etiketi basmaz. Tanımadığı bir kaynak
          // adı 'unreachable' olarak düşer (sessizce "gerçek" sayılmaz).
          agentStatusSource.set(
            data.source === 'redis_bus' || data.source === 'in_memory'
              || data.source === 'fallback' || data.source === 'error'
              ? data.source
              : 'unreachable'
          );
          if (data.agents && data.agents.length > 0) {
            const mapped: Record<string, any> = {};
            for (const agent of data.agents) {
              mapped[agent.agent_id] = {
                status: agent.status,
                updatedAt: Date.now(),
                metadata: agent.metadata || {}
              };
            }
            agentStatuses.set(mapped);
          }
        } else {
          agentStatusSource.set('unreachable');
        }
      } catch {
        agentStatusSource.set('unreachable');
      }
    }, 3000);

    const unsubPower = powerEngaged.subscribe((on) => {
      if (disposed) return;
      if (!on) {
        if (reconnectTimer) clearTimeout(reconnectTimer);
        if (ws) {
          try { ws.close(); } catch (_e) {}
          ws = null;
        }
        uplinkState.set('OFFLINE');
      } else {
        reconnectAttempts = 0;
        connect();
      }
    });

    const unsubToken = apiToken.subscribe((value) => {
      if (value === lastToken) return;
      lastToken = value;
      reconnectAttempts = 0;
      if (ws) {
        try { ws.close(); } catch (_e) {}
        ws = null;
      }
      connect();
    });

    return () => {
      disposed = true;
      if (telemetryPoll) clearInterval(telemetryPoll);
      clearInterval(agentPoll);
      unsubToken();
      unsubPower();
      unsubVoice();
      stopActiveSpeechAudio();
      tauriUnlisteners.forEach(fn => { try { fn(); } catch {} });
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) {
        try { ws.close(); } catch (_e) {}
        ws = null;
      }
    };
  });
</script>

{#if showIntro}
  <!-- ATLAS EPIFIZ INTRO — ilk açılışta şık karşılama -->
  <div class="atlas-intro-overlay" role="dialog" aria-modal="true" aria-label="Atlas Epifiz Karşılama">
    <div class="atlas-intro-bg" style="background-image: url('/atlas_epifiz_observatory.jpg')"></div>
    <div class="atlas-intro-veil"></div>
    <div class="atlas-intro-vignette"></div>
    <div class="atlas-intro-content">
      <div class="atlas-intro-kicker">PINEAL CORE • OBSERVE — ANALYZE — CORRELATE</div>
      <div class="atlas-intro-badge">PINEAL OBSERVATORY</div>
      <h1 class="atlas-intro-title">ATLAS<br/><span>EPİFİZ</span></h1>
      <div class="atlas-intro-divider"></div>
      <p class="atlas-intro-quote">“Göz görür. Pineal ayırır.<br/>Atlas ilişkilendirir.” <em>— SG</em></p>
      <div class="atlas-intro-meta">
        <span>Salim Gümüş • Operator PINEAL</span>
        <span class="dot">●</span>
        <span>14/14 Aktif Ajan</span>
        <span class="dot">●</span>
        <span>KAYNAK — BAĞLAM — KORELASYON — ANALİZ — DOĞRULAMA</span>
      </div>
      <button class="atlas-intro-enter" on:click={enterAtlas}>
        <span class="enter-glow"></span>
        <span class="enter-label">◉ GÖZLEME BAŞLA</span>
        <span class="enter-sub">Atlas Epifiz Kokpitine Gir</span>
      </button>
      <div class="atlas-intro-hint">GETA Güvenli Erişim Terminali • Pineal Token Authorized</div>
    </div>
  </div>
{/if}

<main class="fullscreen-cockpit-viewport">
  <!-- Ambient / silik fon — uygulama içinde hafif arka plan -->
  <div class="atlas-ambient-bg" aria-hidden="true"></div>
  <div class="atlas-ambient-veil" aria-hidden="true"></div>

  <nav class="view-switcher" aria-label="Görünüm seçimi">
    <div class="view-switcher-label">
      <button class="view-switcher-atlas" on:click={reopenIntro} title="Atlas Epifiz karşılama ekranını tekrar göster" aria-label="Atlas Intro">
        <span class="atlas-eye">◉</span> ATLAS
      </button>
    </div>
    <button class:is-active={$activeViewMode === 'cockpit'} on:click={() => activeViewMode.set('cockpit')} class="primary-tab">ATLAS EPİFİZ</button>
    <button class:is-active={$activeViewMode === 'warroom'} on:click={() => activeViewMode.set('warroom')}>Muharebe</button>
    <button class:is-active={$activeViewMode === 'control'} on:click={() => activeViewMode.set('control')}>Canlı kontrol</button>
    <button class:is-active={$activeViewMode === 'spiderfoot'} on:click={() => activeViewMode.set('spiderfoot')}>Araştırma</button>
  </nav>
  {#if $activeViewMode === 'cockpit'}
    <AtlasPinealCockpit />
  {:else if $activeViewMode === 'warroom'}
    <TacticalWarRoom />
  {:else if $activeViewMode === 'control'}
    <LiveControlPanel />
    <section aria-label="Ajan durumu ve kanıt grafı">
      <AgentRack compact={true} />
      <p>{graphMessage}</p>
      {#if graphTaskId}<button on:click={() => loadEvidenceGraph(graphTaskId, graphRoom)}>Kanıt grafını yenile</button>{/if}
      <HolographicResonanceMesh graph={evidenceGraph} size={360} />
    </section>
  {:else if $activeViewMode === 'spiderfoot'}
    <SpiderFootCockpit />
  {:else}
    <AtlasPinealCockpit />
  {/if}

  <!--
    Adli Telemetri & Sözleşme Köprüsü — ARTIK GERÇEKTEN GÖRÜNÜR.
    [AUDIT 2026-10-07 · Madde 6] Bu katman eskiden
    `<div style="display: none;" aria-hidden="true">` içindeydi: bileşen
    DOM'a basılıyor ama KULLANICI HİÇ GÖREMİYORDU; yani telemetri
    gözlemlenebilirliği fiilen yoktu ve "TELEMETRY OFFLINE" uyarısı bile
    hiçbir zaman ekrana ulaşmıyordu. Pano artık görünür bir panel;
    kapamak kullanıcının BİLİNÇLİ seçimiyle olur (aşağıdaki düğme).
  -->
  <button
    class="telemetry-toggle"
    on:click={() => (telemetryVisible = !telemetryVisible)}
    aria-expanded={telemetryVisible}
    aria-controls="neural-telemetry-panel"
    title="Nöral telemetri panosunu göster / gizle"
  >
    {telemetryVisible ? '▼ TELEMETRİYİ GİZLE' : '▲ TELEMETRİYİ GÖSTER'}
  </button>

  {#if telemetryVisible}
    <div class="telemetry-panel" id="neural-telemetry-panel">
      <NeuralTelemetryBoard telemetry={telemetryData} />
    </div>
  {/if}

  <!-- [B0] Destek & güvenli devam kokpiti — açık talepler görünür ve yanıtlanabilir -->
  <SupportPanel />
</main>

<style>
  .view-switcher {
    position: fixed;
    right: 14px;
    bottom: 14px;
    display: flex;
    gap: 6px;
    z-index: 40;
  }
  .view-switcher button {
    background: rgba(2, 6, 3, 0.85);
    border: 1px solid rgba(212, 175, 55, 0.5);
    color: var(--gold, #d4af37);
    font-family: 'JetBrains Mono', 'Courier New', monospace;
    font-size: 10px;
    letter-spacing: 1px;
    padding: 4px 8px;
    cursor: pointer;
  }
  .view-switcher button.is-active {
    background: rgba(212, 175, 55, 0.18);
    color: var(--text-phosphor, #38ef7d);
  }

  .fullscreen-cockpit-viewport {
    width: 100vw;
    height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #000;
    overflow: hidden;
  }

  /* [AUDIT 2026-10-07 · Madde 6] Telemetri panosu ve açma/kapama düğmesi.
     Sol üst köşede kompakt konumlandırıldı — alttaki Aspasia sohbet ekranını ASLA kapatmaz. */
  .telemetry-panel {
    position: fixed;
    right: 14px;
    bottom: 46px;
    width: min(380px, 30vw);
    z-index: 45;
  }

  /* Pano kompakt yükseklikte; sohbet ve ana kontrolleri örtmez. */
  .telemetry-panel :global(.telemetry-board) {
    height: min(220px, 28vh);
  }

  .telemetry-toggle {
    position: fixed;
    right: 420px;
    bottom: 14px;
    z-index: 46;
    padding: 5px 10px;
    font-family: 'JetBrains Mono', 'Courier New', monospace;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: #d4af37;
    background: rgba(3, 5, 10, 0.88);
    border: 1px solid rgba(212, 175, 55, 0.35);
    border-radius: 6px;
    cursor: pointer;
  }

  .telemetry-toggle:hover {
    border-color: rgba(212, 175, 55, 0.75);
  }

  /* =========================================================
     ATLAS EPIFIZ — Ambient (dimmed) + Intro
     ========================================================= */
  .atlas-ambient-bg {
    position: fixed;
    inset: 0;
    background-image: url('/atlas_epifiz_observatory.jpg');
    background-size: cover;
    background-position: center 35%;
    opacity: 0.09;
    filter: brightness(0.55) saturate(0.85) blur(0.8px);
    pointer-events: none;
    z-index: 0;
  }
  .atlas-ambient-veil {
    position: fixed;
    inset: 0;
    background:
      radial-gradient(ellipse at 50% 18%, rgba(8, 17, 36, 0.55) 0%, transparent 58%),
      linear-gradient(to bottom, rgba(2, 6, 15, 0.25) 0%, rgba(2, 6, 15, 0.78) 100%);
    pointer-events: none;
    z-index: 1;
  }
  .fullscreen-cockpit-viewport > :not(.atlas-ambient-bg):not(.atlas-ambient-veil) {
    position: relative;
    z-index: 2;
  }

  /* View switcher — Atlas primary */
  .view-switcher {
    align-items: center;
  }
  .view-switcher-label {
    display: flex;
    align-items: center;
    margin-right: 4px;
  }
  .view-switcher-atlas {
    background: rgba(212, 175, 55, 0.12) !important;
    border-color: rgba(212, 175, 55, 0.65) !important;
    color: #fde68a !important;
    font-weight: 800 !important;
    font-size: 9px !important;
    padding: 4px 7px !important;
    letter-spacing: 1.2px !important;
  }
  .atlas-eye {
    color: #38ef7d;
    text-shadow: 0 0 8px rgba(56, 239, 125, 0.85);
    margin-right: 2px;
  }
  .primary-tab.is-active {
    background: rgba(212, 175, 55, 0.22) !important;
    border-color: #d4af37 !important;
    color: #fde68a !important;
    box-shadow: 0 0 10px rgba(212, 175, 55, 0.28);
  }

  /* ── INTRO OVERLAY ── */
  .atlas-intro-overlay {
    position: fixed;
    inset: 0;
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    background: #02060f;
  }
  .atlas-intro-bg {
    position: absolute;
    inset: 0;
    background-size: cover;
    background-position: center 32%;
    filter: brightness(0.72) saturate(1.05) contrast(1.06);
    transform: scale(1.02);
  }
  .atlas-intro-veil {
    position: absolute;
    inset: 0;
    background:
      radial-gradient(ellipse at 50% 44% , transparent 42%, rgba(2, 6, 15, 0.55) 78%, rgba(2, 6, 15, 0.88) 100%),
      linear-gradient(to bottom, rgba(2, 6, 15, 0.18) 0%, rgba(2, 6, 15, 0.45) 55%, rgba(2, 6, 15, 0.86) 100%);
  }
  .atlas-intro-vignette {
    position: absolute;
    inset: 0;
    box-shadow: inset 0 0 140px rgba(0,0,0,0.85), inset 0 0 35px rgba(0,0,0,0.7);
    pointer-events: none;
  }
  .atlas-intro-content {
    position: relative;
    z-index: 2;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 10px;
    padding: 32px 24px;
    max-width: 680px;
    width: 92%;
    background: rgba(3, 7, 18, 0.58);
    border: 1px solid rgba(212, 175, 55, 0.38);
    border-radius: 10px;
    backdrop-filter: blur(10px) saturate(1.1);
    box-shadow:
      0 16px 48px rgba(0,0,0,0.7),
      0 0 0 1px rgba(212,175,55,0.12) inset,
      0 0 28px rgba(212,175,55,0.10);
  }
  .atlas-intro-kicker {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.18em;
    color: #38ef7d;
    opacity: 0.95;
    text-shadow: 0 0 10px rgba(56,239,125,0.5);
  }
  .atlas-intro-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.32em;
    color: #d4af37;
    border: 1px solid rgba(212,175,55,0.4);
    padding: 4px 12px;
    border-radius: 999px;
    background: rgba(212,175,55,0.08);
  }
  .atlas-intro-title {
    margin: 6px 0 0;
    font-family: 'Cinzel', 'Trajan Pro', 'Times New Roman', serif;
    font-weight: 800;
    font-size: clamp(38px, 7vw, 56px);
    line-height: 0.95;
    letter-spacing: 0.14em;
    color: #fde68a;
    text-shadow:
      0 2px 0 rgba(120,90,12,0.45),
      0 0 18px rgba(212,175,55,0.35),
      0 0 36px rgba(212,175,55,0.16);
  }
  .atlas-intro-title span {
    display: block;
    font-size: 0.92em;
    letter-spacing: 0.18em;
    color: #e8d9a3;
    margin-top: 2px;
  }
  .atlas-intro-divider {
    width: 120px;
    height: 1px;
    background: linear-gradient(90deg, transparent, #d4af37 50%, transparent);
    margin: 4px 0;
    opacity: 0.9;
  }
  .atlas-intro-quote {
    margin: 0;
    font-family: 'Georgia', serif;
    font-size: 15px;
    font-style: italic;
    color: #cbd5e1;
    line-height: 1.45;
  }
  .atlas-intro-quote em {
    font-style: normal;
    color: #d4af37;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.08em;
  }
  .atlas-intro-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
    align-items: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.08em;
    color: #94a3b8;
    margin-top: 2px;
  }
  .atlas-intro-meta .dot { color: #d4af37; opacity: 0.9; }
  .atlas-intro-enter {
    position: relative;
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 12px 28px;
    background: linear-gradient(135deg, #d4af37 0%, #b8931f 100%);
    border: 1px solid #fde68a;
    border-radius: 999px;
    cursor: pointer;
    color: #0b0f14;
    box-shadow: 0 0 18px rgba(212,175,55,0.45), 0 6px 18px rgba(0,0,0,0.5);
    transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
    overflow: hidden;
  }
  .atlas-intro-enter:hover {
    transform: translateY(-1px) scale(1.015);
    box-shadow: 0 0 26px rgba(212,175,55,0.62), 0 10px 22px rgba(0,0,0,0.55);
    filter: brightness(1.06);
  }
  .atlas-intro-enter:active { transform: scale(0.99); }
  .enter-glow {
    position: absolute;
    inset: -40%;
    background: radial-gradient(ellipse at 50% 30%, rgba(255,255,255,0.22), transparent 60%);
    pointer-events: none;
  }
  .enter-label {
    position: relative;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    font-weight: 900;
    letter-spacing: 0.14em;
  }
  .enter-sub {
    position: relative;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.1em;
    opacity: 0.82;
    font-weight: 600;
  }
  .atlas-intro-hint {
    font-family: 'JetBrains Mono', monospace;
    font-size: 8px;
    letter-spacing: 0.1em;
    color: #64748b;
    margin-top: 4px;
  }
</style>
