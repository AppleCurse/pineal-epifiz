<script lang="ts">
  import { activeViewMode } from '../store';
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
</script>

<section class="unified-shell" aria-label="Pineal birleşik görev merkezi">
  <header class="shell-header">
    <div>
      <p class="eyebrow">PINEAL // MISSION CONTROL</p>
      <h1>TEK GÖREV MERKEZİ</h1>
      <p class="shell-subtitle">Komuta, gerçek kanıt, canlı sistem ve operasyon yüzeyleri tek kabukta.</p>
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
  h1 { margin: 0; font-size: clamp(1.25rem, 2vw, 1.8rem); letter-spacing: .06em; }
  .shell-subtitle { margin: .45rem 0 0; color: #94a3b8; font-size: .82rem; }
  .truth-badge { border: 1px solid #0e7490; color: #d7a83f; padding: .55rem .75rem; border-radius: .35rem; font: 700 .68rem monospace; white-space: nowrap; }
  .surface-tabs { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: .5rem; padding: .75rem 1.5rem; background: #080e1a; border-bottom: 1px solid #1e293b; }
  .surface-tabs button { min-height: 3.25rem; text-align: left; padding: .6rem .7rem; color: #94a3b8; background: #0c1423; border: 1px solid #1e293b; border-radius: .35rem; cursor: pointer; }
  .surface-tabs button:hover, .surface-tabs button.active { color: #e0f2fe; border-color: #b88a35; background: #4b310e; }
  .surface-tabs span { display: block; font: 700 .72rem monospace; letter-spacing: .08em; }
  .surface-tabs small { display: block; margin-top: .3rem; font-size: .68rem; color: #64748b; }
  .surface-tabs .active small { color: #7dd3fc; }
  .surface-stage { min-height: calc(100vh - 9rem); }
  @media (max-width: 800px) { .shell-header { align-items: flex-start; flex-direction: column; } .surface-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); padding: .65rem; } }
</style>

