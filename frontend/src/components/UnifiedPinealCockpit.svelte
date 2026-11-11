<script lang="ts">
  import {
    activeViewMode, powerEngaged, armEngaged, recordEngaged,
    clientId, taskStatus, apiFetch
  } from '../store';
  import AtlasObservatory from './AtlasObservatory.svelte';
  import AtlasPinealCockpit from './AtlasPinealCockpit.svelte';
  import TacticalWarRoom from './TacticalWarRoom.svelte';
  import LiveControlPanel from './LiveControlPanel.svelte';
  import SpiderFootCockpit from './SpiderFootCockpit.svelte';

  type Surface = 'observatory' | 'command' | 'evidence' | 'live' | 'warroom';
  const surfaceByView: Record<string, Surface> = {
    observatory: 'observatory', cockpit: 'command', spiderfoot: 'evidence', control: 'live', warroom: 'warroom'
  };
  const viewBySurface: Record<Surface, string> = {
    observatory: 'observatory', command: 'cockpit', evidence: 'spiderfoot', live: 'control', warroom: 'warroom'
  };
  let surface: Surface = surfaceByView[$activeViewMode] || 'observatory';
  $: surface = surfaceByView[$activeViewMode] || surface;

  function selectSurface(next: Surface) {
    surface = next;
    activeViewMode.set(viewBySurface[next] as any);
  }

  const surfaces: Array<{ id: Surface; label: string; description: string }> = [
    { id: 'observatory', label: 'ATLAS OBSERVATORY', description: 'Göz Mabedi & Steampunk Konsol' },
    { id: 'command', label: 'KOMUTA', description: 'Ajan komuta yüzeyi' },
    { id: 'evidence', label: 'KANIT RADARI', description: 'Gerçek görev kanıtı ve OSINT grafı' },
    { id: 'live', label: 'CANLI SİSTEM', description: 'Telemetri, ses ve bağlantı durumu' },
    { id: 'warroom', label: 'MUHAREBE MASASI', description: 'İleri operasyon görünümü' },
  ];

  let stopBusy = false;
  let stopNote = '';

  async function emergencyStop() {
    if (stopBusy) return;
    stopBusy = true;
    const id = $taskStatus?.task_id;
    armEngaged.set(false);
    powerEngaged.set(false);
    if (!id) { stopNote = 'Uçuşta görev yok.'; stopBusy = false; return; }
    try {
      const res = await apiFetch(
        `/api/tasks/${encodeURIComponent(id)}/cancel?client_id=${encodeURIComponent($clientId)}&reason=emergency_stop`,
        { method: 'POST' }
      );
      stopNote = res.ok ? `İptal: ${id}` : `İptal reddedildi (HTTP ${res.status})`;
    } catch {
      stopNote = 'İptal isteği gönderilemedi.';
    } finally {
      stopBusy = false;
    }
  }
</script>

<section class="unified-shell" aria-label="Pineal birleşik görev merkezi">
  <header class="shell-header">
    <div>
      <p class="eyebrow">PINEAL // MISSION CONTROL</p>
      <h1>TEK GÖREV MERKEZİ</h1>
      <p class="shell-subtitle">Komuta, gerçek kanıt, canlı sistem ve operasyon yüzeyleri tek kabukta.</p>
    </div>

    <div class="console-controls">
      <button type="button" class:on={$powerEngaged} on:click={() => powerEngaged.update((v) => !v)} title="Uplink (WebSocket) ana şalteri">PWR</button>
      <button type="button" class:on={$armEngaged} on:click={() => armEngaged.update((v) => !v)} title="Görev başlatma kilidi">ARM</button>
      <button type="button" class:on={$recordEngaged} on:click={() => recordEngaged.update((v) => !v)} title="Log kaydı">REC</button>
      <button type="button" class="stop" on:click={emergencyStop} disabled={stopBusy}>ACİL STOP</button>
      {#if stopNote}<span class="stop-note">{stopNote}</span>{/if}
    </div>

    <div class="truth-badge">VERİ YOKSA UYDURMAZ</div>
  </header>

  <nav class="surface-tabs" aria-label="Görev merkezi yüzeyleri">
    {#each surfaces as item}
      <button type="button" class:active={surface === item.id} on:click={() => selectSurface(item.id)}>
        <span>{item.label}</span>
        <small>{item.description}</small>
      </button>
    {/each}
  </nav>

  <div class="surface-stage">
    {#if surface === 'observatory'}
      <AtlasObservatory />
    {:else if surface === 'command'}
      <AtlasPinealCockpit />
    {:else if surface === 'evidence'}
      <SpiderFootCockpit />
    {:else if surface === 'live'}
      <LiveControlPanel />
    {:else}
      <TacticalWarRoom />
    {/if}
  </div>
</section>

<style>
  .unified-shell { min-height: 100vh; background: #050914; color: #e5edf8; }
  .shell-header { display: flex; justify-content: space-between; gap: 1.5rem; align-items: center; padding: 1.25rem 1.5rem 1rem; border-bottom: 1px solid #1e293b; background: linear-gradient(120deg, #08111f, #0b1220 55%, #101827); }
  .eyebrow { margin: 0 0 .35rem; color: #67e8f9; font: 700 .7rem/1 monospace; letter-spacing: .16em; }
  h1 { margin: 0; font-size: clamp(1.25rem, 2vw, 1.8rem); letter-spacing: .06em; }
  .shell-subtitle { margin: .45rem 0 0; color: #94a3b8; font-size: .82rem; }

  .console-controls { display: flex; align-items: center; gap: .35rem; margin-left: auto; }
  .console-controls button { font: 700 .66rem monospace; letter-spacing: .1em; padding: .45rem .55rem; background: #0c1423; color: #64748b; border: 1px solid #1e293b; border-radius: .3rem; cursor: pointer; }
  .console-controls button.on { color: #052e16; background: #4ade80; border-color: #22c55e; }
  .console-controls button.stop { color: #fca5a5; background: #2a0d0d; border-color: #b91c1c; }
  .console-controls button:disabled { opacity: .5; cursor: default; }
  .stop-note { font: .62rem monospace; color: #94a3b8; }

  .truth-badge { padding: .35rem .75rem; border: 1px solid #0284c7; background: #082f49; color: #38bdf8; font: 700 .72rem/1 monospace; letter-spacing: .08em; border-radius: 999px; }
  .surface-tabs { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: .5rem; padding: .75rem 1.5rem; background: #020617; border-bottom: 1px solid #0f172a; position: sticky; top: 0; z-index: 10; }
  .surface-tabs button { display: flex; flex-direction: column; align-items: flex-start; gap: .25rem; padding: .7rem .9rem; border: 1px solid #1e293b; background: #070d1d; color: #94a3b8; border-radius: .5rem; text-align: left; cursor: pointer; }
  .surface-tabs button:hover { border-color: #38bdf8; color: #f8fafc; }
  .surface-tabs button.active { border-color: #38bdf8; background: #0c1933; color: #f8fafc; }
  .surface-tabs button span { font: 700 .84rem monospace; letter-spacing: .08em; }
  .surface-tabs button small { font-size: .72rem; color: #64748b; line-height: 1.25; }
  .surface-stage { padding: 1.25rem 1.5rem; }
</style>
