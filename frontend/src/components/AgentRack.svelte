<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { agentStatuses, agentStatusSource, isProcessing } from '../store';

  const dispatch = createEventDispatcher();

  // 12 ajan tanımı - sağdaki Agent Rack slotları
  const AGENT_DEFINITIONS = [
    { id: 'mirror_truth', name: 'MIRROR TRUTH', short: 'MIRROR', color: '#10b981', glyph: '🪞', desc: 'Öz-frekans yansıtma' },
    { id: 'autonomous_verifier', name: 'AUTONOMOUS VERIFIER', short: 'VERIFIER', color: '#a855f7', glyph: '⚖️', desc: 'Otonom doğrulama paneli' },
    { id: 'human_behavior', name: 'HUMAN BEHAVIOR', short: 'HUMAN', color: '#f59e0b', glyph: '👤', desc: 'Dijital cold reading' },
    { id: 'passion_mapper', name: 'PASSION MAPPER', short: 'PASSION', color: '#f59e0b', glyph: '✨', desc: 'Tutku & neşe haritası' },
    { id: 'friction_detector', name: 'FRICTION & BOUNDS', short: 'FRICTION', color: '#ef4444', glyph: '🛡️', desc: 'Sınır & hassasiyet' },
    { id: 'cognitive_profiler', name: 'COGNITIVE PROFILER', short: 'COGNITIVE', color: '#06b6d4', glyph: '🧠', desc: 'Dil & üslup profili' },
    { id: 'resonance_calculator', name: 'RESONANCE CALC', short: 'RESONANCE', color: '#3b82f6', glyph: '📐', desc: 'Numpy rezonans' },
    { id: 'pattern_interrupt', name: 'PATTERN INTERRUPT', short: 'PATTERN', color: '#dc2626', glyph: '💥', desc: 'Beklenti kırma' },
    { id: 'osint_investigator', name: 'OSINT INVESTIGATOR', short: 'OSINT', color: '#8b5cf6', glyph: '🔍', desc: 'Dijital ayak izi' },
    { id: 'authenticity_auditor', name: 'AUTHENTICITY AUDITOR', short: 'AUTH', color: '#14b8a6', glyph: '🔎', desc: 'Orijinallik denetimi' },
    { id: 'depth_analyst', name: 'DEPTH ANALYST', short: 'DEPTH', color: '#eab308', glyph: '🕳️', desc: 'Gerçeklik endeksi' },
    { id: 'resonance_synthesizer', name: 'RESONANCE SYNTH', short: 'SYNTH', color: '#ec4899', glyph: '🎼', desc: 'Sahici köprü sentezi' },
  ];

  export let compact: boolean = false;

  function statusColor(status: string): string {
    switch (status?.toLowerCase()) {
      case 'active':
      case 'processing':
      case 'running': return '#facc15'; // sarı
      case 'ready':
      case 'idle':
      case 'done':
      case 'completed': return '#10b981'; // yeşil
      case 'wait':
      case 'waiting':
      case 'queued': return '#6b7280'; // gri
      case 'error':
      case 'failed':
      case 'halted': return '#ef4444'; // kırmızı
      default: return '#6b7280';
    }
  }

  function statusLabel(status: string): string {
    switch (status?.toLowerCase()) {
      case 'active': return 'ACTIVE';
      case 'processing': return 'ACTIVE';
      case 'ready': return 'READY';
      // [RÖNTGEN 2026-09-23] 'idle' eskiden READY'ye çevriliyordu: boşta
      // duran ajan "hazır/kanıt üretti" gibi görünüyordu. Boşta = bekliyor.
      case 'idle': return 'WAIT';
      case 'wait': return 'WAIT';
      case 'waiting': return 'WAIT';
      case 'queued': return 'WAIT';
      case 'done': return 'DONE';
      case 'completed': return 'DONE';
      case 'error': return 'ERROR';
      case 'failed': return 'ERROR';
      default: return status?.toUpperCase() || 'WAIT';
    }
  }

  export let selectedAgentId: string | null = null;

  function selectAgent(id: string) {
    dispatch('select', { agentId: id });
  }

  $: statuses = $agentStatuses || {};

  // [RÖNTGEN 2026-09-23] Sayaçlar slotlarla AYNI kaynaktan sayılır.
  // Eski kod: `READY = gerçek_ready || 12` — hiç ajan READY değilken (hatta
  // backend'den tek kayıt gelmemişken) ekrana "READY 12" basıyordu; yani
  // ölçülmeyen bir durum uydurma sayıyla gösteriliyordu.
  $: slotLabels = AGENT_DEFINITIONS.map((a) => statusLabel((statuses[a.id] || { status: 'Wait' }).status));
  $: readyCount = slotLabels.filter((l) => l === 'READY').length;
  $: activeCount = slotLabels.filter((l) => l === 'ACTIVE').length;
  $: waitCount = slotLabels.filter((l) => l === 'WAIT').length;
  $: errorCount = slotLabels.filter((l) => l === 'ERROR').length;
  $: hasBackendStatus = Object.keys(statuses).length > 0;

  // Durum kaynağı backend beyanından gelir; süs etiketi basılmaz.
  // Etiketler backend'in `/api/agents/status` → `source` alanının birebir
  // karşılığıdır (redis_bus.connection_state() dahil): her satır gerçek bir
  // taşıyıcı durumuna izlenebilir, süs etiketi yok.
  const SOURCE_LABELS: Record<string, string> = {
    redis_bus: 'REDIS PUB/SUB',
    in_memory: 'YEREL BELLEK (REDIS YOK)',
    fallback: 'TRACKER YÜKLÜ DEĞİL',
    error: 'TRACKER HATASI',
    unreachable: 'API ERİŞİLEMEDİ',
    none: 'KAYNAK YOK',
  };
  $: busLabel = SOURCE_LABELS[$agentStatusSource] || 'KAYNAK YOK';
</script>

<div class="agent-rack {compact ? 'compact' : ''}" role="region" aria-label="Agent Rack">
  <div class="rack-header">
    <div class="rack-title">AGENT RACK</div>
    <!--
      [AUDIT 2026-10-07 · Madde 3] Etiket "12 AUTONOMOUS NODES" idi: bu
      slotların her birinin BAĞIMSIZ/OTONOM bir işlemci olduğu iddiasını
      taşıyordu. Gerçek: bunlar orkestratörün (PinealExecutor) süreç içinde
      sırayla yürüttüğü 12 analiz ROLÜDÜR. Docker'daki 12 `beacon-*`
      servisi ise analiz yürütmez; yalnızca "yuva ayakta ve boşta" canlılık
      sinyali yayınlar. Etiket + ipucu (title) dürüst hâle getirildi.
    -->
    <div
      class="rack-subtitle"
      title="12 analiz rolü — çekirdek orkestratör tarafından süreç içinde yürütülür. Docker'daki beacon-* servisleri analiz yürütmez; yalnızca canlılık sinyali yayınlar."
    >
      12 ANALYSIS ROLES · {busLabel}
    </div>
    <div class="rack-live-dot" class:live={$isProcessing}></div>
  </div>

  <div class="rack-slots">
    {#each AGENT_DEFINITIONS as agent (agent.id)}
      {@const st = statuses[agent.id] || { status: 'Wait' }}
      {@const label = statusLabel(st.status)}
      {@const color = statusColor(st.status)}
      <div 
        class="rack-slot" 
        class:active={label === 'ACTIVE'} 
        class:ready={label === 'READY'} 
        class:wait={label === 'WAIT'} 
        class:error={label === 'ERROR'}
        class:selected={selectedAgentId === agent.id}
        style="--agent-color:{agent.color}; --status-color:{color}; cursor: pointer;"
        on:click={() => selectAgent(agent.id)}
        role="button"
        tabindex="0"
        on:keydown={(e) => e.key === 'Enter' && selectAgent(agent.id)}
      >
        <div class="slot-glyph">{agent.glyph}</div>
        <div class="slot-info">
          <div class="slot-name">{compact ? agent.short : agent.name}</div>
          {#if !compact}
            <div class="slot-desc">{agent.desc}</div>
          {/if}
        </div>
        <div class="slot-status">
          <span class="status-dot" style="background:{color}; box-shadow: 0 0 8px {color};"></span>
          <span class="status-text" style="color:{color};">{label}</span>
        </div>
        {#if label === 'ACTIVE'}
          <div class="slot-activity-bar">
            <div class="activity-fill"></div>
          </div>
        {/if}
      </div>
    {/each}
  </div>

  <div class="rack-footer">
    <div class="footer-stat">
      <span class="stat-label">READY</span>
      <span class="stat-value">{readyCount}</span>
    </div>
    <div class="footer-stat">
      <span class="stat-label">ACTIVE</span>
      <span class="stat-value active">{activeCount}</span>
    </div>
    <div class="footer-stat">
      <span class="stat-label">WAIT</span>
      <span class="stat-value wait">{waitCount}</span>
    </div>
    <div class="footer-stat">
      <span class="stat-label">ERROR</span>
      <span class="stat-value error">{errorCount}</span>
    </div>
    <div class="footer-source" title="Durum kaynağı backend beyanıdır">
      {hasBackendStatus ? `KAYNAK: ${busLabel}` : 'KAYNAK YOK — HİÇBİR AJAN DURUMU OKUNMADI'}
    </div>
  </div>
</div>

<style>
  .agent-rack {
    background: linear-gradient(180deg, #0a0e1a 0%, #05070d 100%);
    border: 1px solid rgba(212, 175, 55, 0.15);
    border-radius: 8px;
    padding: 12px;
    font-family: 'JetBrains Mono', monospace;
    width: 100%;
    max-width: 380px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.05);
  }

  .rack-header {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(212, 175, 55, 0.15);
    position: relative;
  }

  .stat-value.error {
    color: #ef4444;
  }

  .footer-source {
    width: 100%;
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid rgba(212, 175, 55, 0.1);
    font-size: 7px;
    letter-spacing: 0.08em;
    color: #64748b;
    text-align: center;
  }

  .rack-title {
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.18em;
    color: #d4af37;
    text-shadow: 0 0 8px rgba(212, 175, 55, 0.5);
  }

  .rack-subtitle {
    font-size: 8px;
    letter-spacing: 0.12em;
    color: #6b7280;
  }

  .rack-live-dot {
    position: absolute;
    right: 0;
    top: 2px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #6b7280;
    transition: all 0.3s;
  }

  .rack-live-dot.live {
    background: #10b981;
    box-shadow: 0 0 10px #10b981;
    animation: livePulse 1s ease-in-out infinite;
  }

  @keyframes livePulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.6; transform: scale(1.2); }
  }

  .rack-slots {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 520px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: rgba(212, 175, 55, 0.2) transparent;
  }

  .rack-slot {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-left: 2px solid var(--status-color);
    border-radius: 4px;
    transition: all 0.2s ease;
  }

  .rack-slot:hover {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.1);
    border-left-color: var(--status-color);
    transform: translateX(2px);
  }

  .rack-slot.active {
    background: rgba(250, 204, 21, 0.08);
    border-left-width: 3px;
    box-shadow: 0 0 12px rgba(250, 204, 21, 0.15), inset 0 0 8px rgba(250, 204, 21, 0.05);
  }

  .rack-slot.ready {
    background: rgba(16, 185, 129, 0.05);
  }

  .rack-slot.error {
    background: rgba(239, 68, 68, 0.08);
    border-left-color: #ef4444;
  }

  .slot-glyph {
    font-size: 14px;
    width: 20px;
    text-align: center;
    flex-shrink: 0;
  }

  .slot-info {
    flex: 1;
    min-width: 0;
  }

  .slot-name {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #e5e7eb;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .slot-desc {
    font-size: 7px;
    color: #6b7280;
    letter-spacing: 0.04em;
    margin-top: 1px;
  }

  .slot-status {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-shrink: 0;
  }

  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
  }

  .slot-status .status-dot {
    animation: statusBlink 2s ease-in-out infinite;
  }

  .rack-slot.active .status-dot {
    animation: statusActive 0.8s ease-in-out infinite;
  }

  @keyframes statusBlink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  @keyframes statusActive {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.7; transform: scale(1.3); }
  }

  .status-text {
    font-size: 8px;
    font-weight: 800;
    letter-spacing: 0.1em;
  }

  .slot-activity-bar {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: rgba(0, 0, 0, 0.5);
    overflow: hidden;
    border-radius: 0 0 4px 4px;
  }

  .activity-fill {
    height: 100%;
    width: 40%;
    background: linear-gradient(90deg, transparent, var(--status-color), transparent);
    animation: activitySlide 1.2s ease-in-out infinite;
  }

  @keyframes activitySlide {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(300%); }
  }

  .rack-footer {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    justify-content: space-between;
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
  }

  .footer-stat {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1px;
  }

  .stat-label {
    font-size: 7px;
    letter-spacing: 0.1em;
    color: #6b7280;
  }

  .stat-value {
    font-size: 12px;
    font-weight: 800;
    color: #10b981;
  }

  .stat-value.active {
    color: #facc15;
  }

  .stat-value.wait {
    color: #6b7280;
  }

  .compact {
    max-width: 280px;
  }

  .compact .rack-slots {
    max-height: 360px;
  }

  .compact .slot-desc {
    display: none;
  }
</style>
