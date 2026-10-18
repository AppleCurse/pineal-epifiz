<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import {
    apiToken, currentApiToken, apiFetch, clientId, wsUrl, logs, taskStatus,
    speechState, lastSpeech, voiceEnabled,
    isProcessing, powerEngaged, recordEngaged, agentStatuses, vaultLocked,
    activeViewMode, agentStatusSource, supportRequests, supportTaskId, refreshSupport
  } from './store';
  import { uplinkState } from './lib/telemetry';
  import AtlasPinealCockpit from './components/AtlasPinealCockpit.svelte';
  import TacticalWarRoom from './components/TacticalWarRoom.svelte';
  // [P6 · CANLI PANEL] Canlı kontrol paneli: ajan hattı, anlık kanal, muhakeme,
  // kanıt akışı ve çağrı izi — hepsi MEVCUT SoT'tan (WS + /api/aspasia/state).
  import LiveControlPanel from './components/LiveControlPanel.svelte';
  import NeuralTelemetryBoard from './components/visualizers/NeuralTelemetryBoard.svelte';
  import SupportPanel from './components/SupportPanel.svelte';

  let ws: WebSocket | null = null;
  let reconnectAttempts = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;
  let lastToken = currentApiToken();
  let telemetryData: any = null;
  let telemetryPoll: any = null;
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
          taskStatus.update(s => ({ ...s, ...data }));
          // Snapshot içinde current_agent varsa onu Active yap
          if (data.current_agent) {
            handleAgentStatusUpdate({ agent_id: data.current_agent, status: 'Active' });
          }
        } else if (data.type === "result") {
          taskStatus.update(s => ({ ...s, ...data }));
          isProcessing.set(false);
          const terminal = String(data.status || "").toLowerCase();
          const okStates = ["completed", "partially_completed"];
          logLine(okStates.includes(terminal) ? "INFO" : "ERROR", "OPERASYON SONUÇLANDI: " + data.status);
          // Tüm ajanları Ready yap (iş bitti)
          agentStatuses.update(s => {
            const updated: any = { ...s };
            for (const k of Object.keys(updated)) {
              if (updated[k].status === 'Active') {
                updated[k] = { ...updated[k], status: 'Ready', updatedAt: Date.now() };
              }
            }
            return updated;
          });
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

<main class="fullscreen-cockpit-viewport">
  {#if $activeViewMode === 'warroom'}
    <TacticalWarRoom />
  {:else if $activeViewMode === 'control'}
    <LiveControlPanel />
  {:else}
    <AtlasPinealCockpit />
  {/if}

  <!-- [P6] Görünüm seçici: Muharebe Masası · Kontrol Paneli · Kokpit.
       Panel kendi içinde de bu düğmeleri taşır; buradaki seçici her görünümden
       erişilebilir olsun diye vardır. -->
  <nav class="view-switcher" aria-label="Görünüm seçici">
    <button
      class:is-active={$activeViewMode === 'warroom'}
      on:click={() => { activeViewMode.set('warroom'); localStorage.setItem('pineal_view_mode', 'warroom'); }}
    >MUHAREBE MASASI</button>
    <button
      class:is-active={$activeViewMode === 'control'}
      on:click={() => { activeViewMode.set('control'); localStorage.setItem('pineal_view_mode', 'control'); }}
    >KONTROL PANELİ</button>
    <button
      class:is-active={$activeViewMode === 'cockpit'}
      on:click={() => { activeViewMode.set('cockpit'); localStorage.setItem('pineal_view_mode', 'cockpit'); }}
    >KOKPİT</button>
  </nav>

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
    left: 14px;
    top: 46px;
    width: min(340px, 24vw);
    z-index: 45;
  }

  /* Pano kompakt yükseklikte; sohbet ve ana kontrolleri örtmez. */
  .telemetry-panel :global(.telemetry-board) {
    height: min(190px, 24vh);
  }

  .telemetry-toggle {
    position: fixed;
    left: 14px;
    top: 12px;
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
</style>
