<script lang="ts">
  // Backend'den gelen canlı telemetri nesnesi (App.svelte üzerinden beslenir)
  export let telemetry: any = null;
  // [P0 · DENETİM 2026-10-16] Yetenek tablosu: kapalı yetenek + SEBEP.
  import { channelLabel, reasonLabel, type CapabilityRow } from '../../lib/channelStatus';
  $: capabilityRows = ((telemetry?.capabilities || []) as CapabilityRow[]);
  $: unavailableCapabilities = capabilityRows.filter((c) => c && !c.available);

  // Gerçek telemetri durumu — ASLA SİMÜLASYON YOK
  $: isOnline = !!(
    telemetry &&
    typeof telemetry === 'object' &&
    Object.keys(telemetry).length > 0 &&
    telemetry.core !== undefined
  );

  // Aktif düğümler kümesi — YALNIZCA BACKEND VERİSİNDEN BESLENİR
  let activeNodes = new Set<string>();
  let flowSpeed = 0; // 0 = akış durdu
  let systemStatusText = 'TELEMETRY OFFLINE';
  let systemStatusColor = '#ef4444'; // Sinyal yoksa daima KIRMIZI
  let activeAgentsCount = 0;
  let readyAgentsCount = 0;

  // Gerçek telemetri verisini ayrıştırma
  $: {
    activeNodes.clear();

    if (!isOnline) {
      systemStatusText = 'TELEMETRY OFFLINE';
      systemStatusColor = '#ef4444';
      flowSpeed = 0;
      activeAgentsCount = 0;
      readyAgentsCount = 0;
    } else {
      // Backend servis bayrakları
      if (telemetry.gateway) activeNodes.add('gateway');
      if (telemetry.core) activeNodes.add('router');
      if (telemetry.vault) activeNodes.add('memory');

      // Ajan durumlarını gerçek veriden say
      const agentList = Object.values(telemetry.agent_statuses || {}) as any[];
      activeAgentsCount = agentList.filter(
        (a) => a.status?.toLowerCase() === 'active' || a.status?.toLowerCase() === 'running'
      ).length;
      readyAgentsCount = agentList.filter(
        (a) => a.status?.toLowerCase() === 'ready' || a.status?.toLowerCase() === 'done'
      ).length;

      // LLM borusu yalnız gerçekten çalışan ajan varsa aktifleşir
      if (activeAgentsCount > 0) {
        activeNodes.add('llm');
        systemStatusText = `PROCESSING (${activeAgentsCount} AJAN)`;
        systemStatusColor = '#d4af37'; // Altın sarısı
        flowSpeed = 0.8;
      } else {
        systemStatusText = 'STANDBY / READY';
        systemStatusColor = '#10b981'; // Zümrüt yeşili
        flowSpeed = 3.5;
      }
    }
    activeNodes = activeNodes;
  }

  // Parçacık efekti için (yalnızca arka plan estetiği, telemetri durumuyla ilgisi yok)
  const particles = Array(16)
    .fill(0)
    .map((_, i) => ({
      x: (i * 6.25 + 2) % 100,
      y: (i * 12.5 + 5) % 100,
      size: (i % 3) + 1,
      speed: 1 + (i % 2) * 0.5,
      delay: -(i * 0.7),
    }));
</script>

<div class="telemetry-board" class:offline={!isOnline}>
  <!-- OFFLINE UYARI KATMANI — TELEMETRİ YOKSA GİZLEME VE SİMÜLASYON KESİNLİKLE YASAKTIR -->
  {#if !isOnline}
    <div class="offline-overlay" role="alert">
      <div class="offline-card">
        <span class="offline-icon">⚠️</span>
        <div class="offline-text-group">
          <div class="offline-headline">TELEMETRY OFFLINE // SİNYAL YOK</div>
          <div class="offline-subtext">
            Backend API veya WebSocket telemetri akışı alınamadı. Sahte veri üretimi engellendi.
          </div>
        </div>
      </div>
    </div>
  {/if}

  <!-- Arka plan ortam parçacıkları (sadece estetik) -->
  {#each particles as p}
    <div
      class="ambient-particle"
      style="left: {p.x}%; top: {p.y}%; width: {p.size}px; height: {p.size}px; 
             animation-duration: {10 / p.speed}s; animation-delay: {p.delay}s; opacity: {isOnline ? 0.3 : 0.08};"
    ></div>
  {/each}

  <div class="board-header">
    <div class="title-container">
      <div class="status-dot" class:pulsing={isOnline && activeAgentsCount > 0} class:offline-dot={!isOnline}></div>
      <h2 class="board-title">CANLI ANALİZ VE İZLEME AKIŞI</h2>
    </div>
    <div class="metrics">
      <div class="metric-box">
        <span class="metric-lbl">SYSTEM STATUS</span>
        <span class="metric-val" style="color: {systemStatusColor}">
          {systemStatusText}
        </span>
      </div>
      <div class="metric-box">
        <span class="metric-lbl">ACTIVE TUBES</span>
        <span class="metric-val" style="color: {isOnline ? '#fff' : '#64748b'}">
          {isOnline ? activeNodes.size : 0}
        </span>
      </div>
    </div>
  </div>

  <div class="pipeline-canvas">
    <!-- SVG Boru Hatları -->
    <svg width="100%" height="100%" preserveAspectRatio="none" viewBox="0 0 1000 400" class="pipes-svg">
      <defs>
        <!-- Akışkan filtre efekti (Neon Glow) -->
        <filter id="neon-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        <!-- Boş Hortum Doku (Cam hissi) -->
        <linearGradient id="glass-pipe" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stop-color="rgba(255,255,255,0.1)" />
          <stop offset="50%" stop-color="rgba(255,255,255,0.02)" />
          <stop offset="100%" stop-color="rgba(255,255,255,0.1)" />
        </linearGradient>

        <linearGradient id="fluid-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#d4af37" />
          <stop offset="50%" stop-color="#b8860b" />
          <stop offset="100%" stop-color="#8b4513" />
        </linearGradient>
      </defs>

      <!-- Dış Cam Borular (Zemin) -->
      <path d="M 100,200 L 300,200" class="glass-path" />
      <path d="M 300,200 L 500,100 L 700,100" class="glass-path" />
      <path d="M 300,200 L 500,300 L 700,300" class="glass-path" />
      <path d="M 700,100 L 900,200" class="glass-path" />
      <path d="M 700,300 L 900,200" class="glass-path" />

      <!-- İçerideki Akışkan Sıvı (Fluid) — YALNIZCA GERÇEK TELEMETRİYLE AKAR -->
      <!-- Gateway -> Router -->
      <path
        d="M 100,200 L 300,200"
        class="fluid-path"
        class:stalled={!isOnline || flowSpeed === 0}
        filter="url(#neon-glow)"
        style="animation-duration: {flowSpeed || 999}s; opacity: {isOnline && activeNodes.has('gateway') ? 1 : 0.06};"
      />

      <!-- Router -> Memory/OSINT (Üst Kol) -->
      <path
        d="M 300,200 L 500,100 L 700,100"
        class="fluid-path"
        class:stalled={!isOnline || flowSpeed === 0}
        filter="url(#neon-glow)"
        style="animation-duration: {flowSpeed || 999}s; opacity: {isOnline && activeNodes.has('memory') ? 1 : 0.06};"
      />

      <!-- Router -> LLM Engine (Alt Kol) -->
      <path
        d="M 300,200 L 500,300 L 700,300"
        class="fluid-path alt-fluid"
        class:stalled={!isOnline || flowSpeed === 0}
        filter="url(#neon-glow)"
        style="animation-duration: {flowSpeed || 999}s; opacity: {isOnline && activeNodes.has('llm') ? 1 : 0.06};"
      />

      <!-- Merge -> Output -->
      <path
        d="M 700,100 L 900,200"
        class="fluid-path"
        class:stalled={!isOnline || flowSpeed === 0}
        filter="url(#neon-glow)"
        style="animation-duration: {flowSpeed || 999}s; opacity: {isOnline && activeNodes.has('memory') ? 1 : 0.06};"
      />
      <path
        d="M 700,300 L 900,200"
        class="fluid-path alt-fluid"
        class:stalled={!isOnline || flowSpeed === 0}
        filter="url(#neon-glow)"
        style="animation-duration: {flowSpeed || 999}s; opacity: {isOnline && activeNodes.has('llm') ? 1 : 0.06};"
      />
    </svg>

    <!-- Node UI'ları (Cam Kartlar) -->
    <!-- Gateway -->
    <div class="cyber-node" style="left: 10%; top: 50%;">
      <div class="node-icon" class:active={isOnline && activeNodes.has('gateway')}>⛩️</div>
      <div class="node-label">API GATEWAY</div>
    </div>

    <!-- Unified Router -->
    <div class="cyber-node" style="left: 30%; top: 50%;">
      <div class="node-icon" class:active={isOnline && activeNodes.has('router')}>🚦</div>
      <div class="node-label">UNIFIED ROUTER</div>
      <div class="node-pulse" class:pulsing={isOnline && activeNodes.has('router')}></div>
    </div>

    <!-- OSINT / Memory -->
    <div class="cyber-node" style="left: 60%; top: 25%;">
      <div class="node-icon" class:active={isOnline && activeNodes.has('memory')}>🧠</div>
      <div class="node-label">OSINT & MEMORY</div>
      {#if isOnline && activeNodes.has('memory')}
        <div class="mini-hud">VAULT ONLINE</div>
      {/if}
    </div>

    <!-- LLM Engine -->
    <div class="cyber-node" style="left: 60%; top: 75%;">
      <div class="node-icon" class:active={isOnline && activeNodes.has('llm')}>🔥</div>
      <div class="node-label">LLM ENGINE</div>
      {#if isOnline && activeNodes.has('llm')}
        <div class="mini-hud stream-text">SYNTHESIZING...</div>
      {/if}
    </div>

    <!-- Output -->
    <div class="cyber-node" style="left: 90%; top: 50%;">
      <div class="node-icon" class:active={isOnline && activeNodes.has('gateway')}>✅</div>
      <div class="node-label">CLIENT RESPONSE</div>
    </div>

    <!-- [P0 · DENETİM 2026-10-16] ÇALIŞMAYAN YETENEKLER + sebep.
         "Kapalı" demek yetmez; operatör NEDENini de görmelidir. -->
    {#if isOnline && unavailableCapabilities.length > 0}
      <div class="cap-panel">
        <div class="cap-title">ÇALIŞMAYAN YETENEKLER ({unavailableCapabilities.length})</div>
        {#each unavailableCapabilities as cap}
          <div class="cap-line">
            <span class="cap-mark">⛔</span>
            <span class="cap-name">{channelLabel(cap.id)}</span>
            <span class="cap-reason">{reasonLabel(cap.reason || cap.policy_reason)}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  /* [P0 · DENETİM 2026-10-16] Kapalı yetenek paneli (sebepli). */
  .cap-panel {
    position: absolute;
    top: 10px;
    left: 10px;
    z-index: 20;
    max-width: 340px;
    max-height: 120px;
    overflow-y: auto;
    padding: 6px 8px;
    background: rgba(15, 23, 42, 0.88);
    border: 1px solid rgba(239, 68, 68, 0.35);
    border-radius: 6px;
    font-size: 10px;
    line-height: 1.35;
    color: #fca5a5;
  }

  .cap-title {
    font-size: 9px;
    letter-spacing: 1px;
    font-weight: 700;
    color: #94a3b8;
    margin-bottom: 3px;
  }

  .cap-line {
    display: flex;
    gap: 5px;
    align-items: baseline;
  }

  .cap-mark {
    flex: 0 0 auto;
  }

  .cap-name {
    color: #e2e8f0;
    font-weight: 700;
  }

  .cap-reason {
    color: #fca5a5;
    word-break: break-word;
  }

  .telemetry-board {
    position: relative;
    width: 100%;
    height: 450px;
    background: radial-gradient(circle at center, #0a0f1d 0%, #03050a 100%);
    border: 1px solid rgba(212, 175, 55, 0.15);
    border-radius: 16px;
    overflow: hidden;
    font-family: 'JetBrains Mono', 'Courier New', monospace;
    box-shadow: inset 0 0 50px rgba(0, 0, 0, 0.8), 0 10px 30px rgba(0, 0, 0, 0.5);
  }

  .telemetry-board.offline {
    border-color: rgba(239, 68, 68, 0.35);
    background: radial-gradient(circle at center, #180808 0%, #080303 100%);
  }

  /* OFFLINE UYARI ŞERİDİ */
  .offline-overlay {
    position: absolute;
    top: 60px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 25;
    pointer-events: none;
  }

  .offline-card {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 20px;
    background: rgba(15, 23, 42, 0.92);
    border: 1px solid rgba(239, 68, 68, 0.65);
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(239, 68, 68, 0.25), inset 0 0 12px rgba(239, 68, 68, 0.15);
    backdrop-filter: blur(8px);
  }

  .offline-icon {
    font-size: 20px;
    animation: alertPulse 1.6s ease-in-out infinite;
  }

  .offline-headline {
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.14em;
    color: #fca5a5;
  }

  .offline-subtext {
    font-size: 10px;
    color: #94a3b8;
    margin-top: 2px;
  }

  @keyframes alertPulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.9); }
  }

  .ambient-particle {
    position: absolute;
    background: #b8860b;
    border-radius: 50%;
    animation: floatUp linear infinite;
    pointer-events: none;
  }

  .board-header {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    padding: 15px 25px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    z-index: 10;
    background: linear-gradient(180deg, rgba(3, 5, 10, 0.9) 0%, rgba(3, 5, 10, 0) 100%);
  }

  .title-container {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 6px #10b981;
  }

  .status-dot.pulsing {
    background: #d4af37;
    animation: redAlert 1.5s infinite;
  }

  .status-dot.offline-dot {
    background: #ef4444;
    box-shadow: 0 0 8px #ef4444;
    animation: alertPulse 1.2s infinite;
  }

  .board-title {
    margin: 0;
    color: #fff;
    font-size: 16px;
    letter-spacing: 3px;
    font-weight: 600;
    text-shadow: 0 0 10px rgba(255, 255, 255, 0.3);
  }

  .metrics {
    display: flex;
    gap: 20px;
  }

  .metric-box {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
  }

  .metric-lbl {
    font-size: 10px;
    color: #a0aec0;
    letter-spacing: 1px;
  }

  .metric-val {
    font-size: 15px;
    font-weight: bold;
    color: #fff;
    letter-spacing: 0.05em;
  }

  .pipeline-canvas {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
  }

  .pipes-svg {
    position: absolute;
    top: 0;
    left: 0;
    z-index: 1;
    pointer-events: none;
  }

  .glass-path {
    fill: none;
    stroke: url(#glass-pipe);
    stroke-width: 24;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .fluid-path {
    fill: none;
    stroke: url(#fluid-gradient);
    stroke-width: 12;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-dasharray: 40 60;
    animation: flowData linear infinite;
    transition: opacity 0.4s ease;
  }

  .fluid-path.stalled {
    animation: none !important;
  }

  .alt-fluid {
    stroke: #ff4500;
    stroke-dasharray: 15 30;
  }

  .cyber-node {
    position: absolute;
    transform: translate(-50%, -50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    z-index: 5;
  }

  .node-icon {
    width: 50px;
    height: 50px;
    background: rgba(10, 15, 30, 0.85);
    border: 1px solid #2d3748;
    border-radius: 12px;
    display: flex;
    justify-content: center;
    align-items: center;
    font-size: 20px;
    backdrop-filter: blur(4px);
    transition: all 0.3s ease;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.5);
    position: relative;
    opacity: 0.5;
  }

  .node-icon.active {
    opacity: 1;
    border-color: #d4af37;
    box-shadow: 0 0 20px rgba(212, 175, 55, 0.4), inset 0 0 10px rgba(212, 175, 55, 0.2);
    transform: scale(1.08);
  }

  .node-label {
    margin-top: 10px;
    color: #94a3b8;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.8);
  }

  .node-pulse {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 50px;
    height: 50px;
    transform: translate(-50%, -50%);
    border-radius: 12px;
    border: 2px solid #b8860b;
    opacity: 0;
    pointer-events: none;
  }

  .node-pulse.pulsing {
    animation: pulseRing 1.5s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
  }

  .mini-hud {
    position: absolute;
    top: -25px;
    background: rgba(212, 175, 55, 0.1);
    border: 1px solid #d4af37;
    color: #d4af37;
    padding: 2px 6px;
    font-size: 9px;
    border-radius: 4px;
    white-space: nowrap;
  }

  .stream-text {
    color: #ff4500;
    border-color: #ff4500;
    background: rgba(255, 0, 85, 0.1);
  }

  @keyframes flowData {
    to { stroke-dashoffset: -120; }
  }

  @keyframes pulseRing {
    0% { transform: translate(-50%, -50%) scale(1); opacity: 0.8; }
    100% { transform: translate(-50%, -50%) scale(1.8); opacity: 0; }
  }

  @keyframes redAlert {
    0% { box-shadow: 0 0 0 0 rgba(212, 175, 55, 0.7); }
    70% { box-shadow: 0 0 0 10px rgba(212, 175, 55, 0); }
    100% { box-shadow: 0 0 0 0 rgba(212, 175, 55, 0); }
  }

  @keyframes floatUp {
    0% { transform: translateY(0); opacity: 0; }
    10% { opacity: 0.3; }
    90% { opacity: 0.3; }
    100% { transform: translateY(-100px); opacity: 0; }
  }
</style>
