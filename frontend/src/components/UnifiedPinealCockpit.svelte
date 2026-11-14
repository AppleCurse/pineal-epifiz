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
  .unified-shell { position: relative; min-height: 100vh; background: radial-gradient(circle at 50% 0%, #241a08 0, #090b10 32%, #030407 100%); color: #efe7d0; overflow: hidden; }
  .shell-header { position: relative; z-index: 1; display: flex; justify-content: space-between; gap: 1.5rem; align-items: center; padding: 1.25rem 1.5rem 1rem; border-bottom: 1px solid #1e293b; background: linear-gradient(120deg, #08111f, #0b1220 55%, #101827); }
  .eyebrow { margin: 0 0 .35rem; color: #d7a83f; font: 700 .7rem/1 monospace; letter-spacing: .16em; }
  h1 { margin: 0; font-size: clamp(1.25rem, 2vw, 1.8rem); letter-spacing: .06em; color: #f5eedc; }
  .shell-subtitle { margin: .45rem 0 0; color: #94a3b8; font-size: .82rem; }

  .console-controls { display: flex; align-items: center; gap: .4rem; margin-left: auto; }
  .console-controls button { font: 700 .68rem monospace; letter-spacing: .1em; padding: .45rem .65rem; background: #0c1423; color: #94a3b8; border: 1px solid #334155; border-radius: .3rem; cursor: pointer; transition: all .2s; }
  .console-controls button:hover { border-color: #d7a83f; color: #fef08a; }
  .console-controls button.on { color: #052e16; background: #4ade80; border-color: #22c55e; font-weight: 800; box-shadow: 0 0 10px rgba(74, 222, 128, 0.35); }
  .console-controls button.stop { color: #fee2e2; background: #7f1d1d; border-color: #ef4444; font-weight: 800; box-shadow: 0 0 10px rgba(239, 68, 68, 0.35); }
  .console-controls button:disabled { opacity: .5; cursor: default; }
  .stop-note { font: .65rem monospace; color: #cbd5e1; }

  .truth-badge { border: 1px solid #0e7490; color: #d7a83f; background: rgba(14, 116, 144, 0.15); padding: .55rem .75rem; border-radius: .35rem; font: 700 .68rem monospace; white-space: nowrap; }
  
  .surface-tabs { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: .5rem; padding: .75rem 1.5rem; background: #080e1a; border-bottom: 1px solid #1e293b; position: sticky; top: 0; z-index: 10; }
  .surface-tabs button { min-height: 3.25rem; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: .25rem; text-align: left; padding: .6rem .8rem; color: #94a3b8; background: #0c1423; border: 1px solid #1e293b; border-radius: .35rem; cursor: pointer; transition: all .2s; }
  .surface-tabs button:hover, .surface-tabs button.active { color: #fef08a; border-color: #b88a35; background: #4b310e; }
  .surface-tabs span { display: block; font: 700 .74rem monospace; letter-spacing: .08em; }
  .surface-tabs small { display: block; font-size: .68rem; color: #64748b; line-height: 1.25; }
  .surface-tabs .active small { color: #fde047; }
  
  .surface-stage { min-height: calc(100vh - 9rem); }
  @media (max-width: 800px) {
    .shell-header { align-items: flex-start; flex-direction: column; }
    .surface-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); padding: .65rem; }
  }
</style>
