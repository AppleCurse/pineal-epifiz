<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import {
    apiToken, currentApiToken, apiFetch, clientId, wsUrl, logs, taskStatus,
    isProcessing, powerEngaged, recordEngaged, agentStatuses, vaultLocked,
    activeViewMode, agentStatusSource
  } from './store';
  import { uplinkState } from './lib/telemetry';
  import { currentLang, t, type Language } from './i18n';
  import UnifiedCompactPanel from './components/UnifiedCompactPanel.svelte';
  import CockpitEntry from './components/CockpitEntry.svelte';
  import AtlasPinealCockpit from './components/AtlasPinealCockpit.svelte';
  import TacticalWarRoom from './components/TacticalWarRoom.svelte';
  import NeuralTelemetryBoard from './components/visualizers/NeuralTelemetryBoard.svelte';

  let ws: WebSocket | null = null;
  let reconnectAttempts = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;
  let lastToken = currentApiToken();

  // Kokpit girişi: tam ortada göz + izometrik süzülen sahne. Her açılışta
  // gösterilir; başlıktaki GÖZ düğmesiyle tekrar açılabilir.
  let showEntry = true;
  function handleCockpitEnter() {
    showEntry = false;
  }
  function reopenCockpitEntry() {
    showEntry = true;
  }

  // [BOSS-12] Ölü kod temizlendi: fetchTelemetry/fetchTasks/deleteTask ve
  // tasksData hiçbir yerden çağrılmıyordu (görev geçmişi UI'de yoktu) — ölü
  // yüzey bırakmak yerine kaldırıldı. Telemetri panosu artık CANLI beslenir.
  type TelemetryPayload = Record<string, unknown>;

  let telemetryData: TelemetryPayload | null = null;
  let telemetryPoll: ReturnType<typeof setInterval> | null = null;
  let telemetryData: any = null;
  let telemetryPoll: any = null;
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
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "log") {
          if (!recording()) return;
          logs.update(l => [...l, data].slice(-80));
        } else if (data.type === "agent_status_update") {
          handleAgentStatusUpdate(data);
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
      tauriUnlisteners.forEach(fn => { try { fn(); } catch {} });
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) {
        try { ws.close(); } catch (_e) {}
        ws = null;
      }
    };
  });
</script>

{#if showEntry}
  <CockpitEntry onEnter={handleCockpitEnter} />
{/if}

<div class="walnut-frame">
  <!-- HEADER & CONTROLS -->
  <header style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid var(--brass-border); padding-bottom: 14px;">
    <div>
      <h1 class="font-cinzel" style="font-size: 22px; font-weight: 800; color: var(--gold); letter-spacing: 0.15em; line-height: 1.2;">
        {t[$currentLang].appTitle}
      </h1>
      <p class="font-cinzel" style="font-size: 11px; color: var(--text-dim); letter-spacing: 0.25em; margin-top: 4px;">
        {t[$currentLang].appSubtitle}
      </p>
    </div>

    <!-- LANGUAGE SWITCHER & BADGE -->
    <div style="display: flex; align-items: center; gap: 12px;">
      <div class="brass-header" style="font-size: 11px; font-weight: 800; letter-spacing: 0.1em; display: flex; align-items: center; gap: 6px;">
        <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; {$uplinkState === 'ONLINE' ? 'background: #10b981; box-shadow: 0 0 6px #10b981;' : 'background: #ef4444; box-shadow: 0 0 6px #ef4444;'}"></span>
        <span>{$uplinkState === 'ONLINE' ? 'ONLINE (ÇEVRİMİÇİ)' : 'OFFLINE (ÇEVRİMDIŞI)'}</span>
      </div>

      <button
        class="btn-dark"
        style="padding: 4px 10px; font-size: 11px; font-weight: 700;"
        on:click={reopenCockpitEntry}
        title="Kokpit girişini (göz) tekrar aç"
      >
        👁 GÖZ
      </button>

      <!-- TR / EN Toggle -->
      <div style="display: flex; background: #0a0705; border: 1px solid var(--brass-border); border-radius: 6px; overflow: hidden; padding: 2px;">
        <button 
          class="btn-dark" 
          style="padding: 4px 10px; font-size: 11px; font-weight: 700; border-radius: 4px; border: none; {$currentLang === 'tr' ? 'background: var(--gold); color: #120b04;' : 'background: transparent; color: var(--text-dim);'}" 
          on:click={() => switchLang('tr')}
        >
          🇹🇷 TR
        </button>
        <button 
          class="btn-dark" 
          style="padding: 4px 10px; font-size: 11px; font-weight: 700; border-radius: 4px; border: none; {$currentLang === 'en' ? 'background: var(--gold); color: #120b04;' : 'background: transparent; color: var(--text-dim);'}" 
          on:click={() => switchLang('en')}
        >
          🇬🇧 EN
        </button>
      </div>
    </div>
  </header>

  <!-- MAIN COCKPIT BODY -->
  <main>
    <UnifiedCompactPanel />
  </main>

  <!-- [BOSS-12] NeuralTelemetryBoard import ediliyordu ama hiç basılmıyordu:
       ölü import + görünmeyen pano. Artık gerçek telemetriyle render edilir. -->
  <section class="telemetry-section">
    <NeuralTelemetryBoard telemetry={telemetryData} />
  </section>
<main class="fullscreen-cockpit-viewport">
  {#if $activeViewMode === 'warroom'}
    <TacticalWarRoom />
  {:else}
    <AtlasPinealCockpit />
  {/if}

  <!-- Adli Telemetri & Sözleşme Köprüsü -->
  <div style="display: none;" aria-hidden="true">
    <NeuralTelemetryBoard telemetry={telemetryData} />
  </div>
</main>

<style>
  .fullscreen-cockpit-viewport {
    width: 100vw;
    height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #000;
    overflow: hidden;
  }
</style>
