<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { isProcessing, speechState } from '../store';
  import { IrisRenderer } from '../lib/irisRenderer';
  import eyeSrc from '../assets/eye.jpg';
  import livingDisk from '../assets/living_pineal_disk.png';

  export let size: number = 420;
  export let irisSrc: string | null = null;
  export let scanning: boolean = false;

  let canvasEl: HTMLCanvasElement | null = null;
  let renderer: IrisRenderer | null = null;
  let containerEl: HTMLDivElement | null = null;

  // Mouse tracking - mikro düzey
  function handleMouseMove(e: MouseEvent) {
    if (!renderer) return;
    renderer.setMousePosition(e.clientX, e.clientY);
  }

  function handleTouchMove(e: TouchEvent) {
    if (!renderer || e.touches.length === 0) return;
    renderer.setMousePosition(e.touches[0].clientX, e.touches[0].clientY);
  }

  $: if (renderer) {
    renderer.setProcessing($isProcessing || scanning, $isProcessing ? 0.8 : 0.6);
    // [FAZ C · C3] Konuşma durumu TEK kaynaktan (backend WS) gelir:
    // dinlerken gözbebeği büyür, konuşurken iris titrer.
    renderer.setListening($speechState === 'listening');
    renderer.setSpeaking($speechState === 'speaking');
  }

  onMount(() => {
    if (!canvasEl) return;
    const src = irisSrc || eyeSrc || livingDisk;
    try {
      renderer = new IrisRenderer(canvasEl, {
        irisImageSrc: src,
        size,
        mouseSensitivity: 5.2,
        breathingSpeed: 0.5,
        breathingAmplitude: 0.014,
      });
      renderer.start();
      window.addEventListener('mousemove', handleMouseMove, { passive: true });
      window.addEventListener('touchmove', handleTouchMove, { passive: true });

      // Resize observer - GPU friendly
      const ro = new ResizeObserver(() => {
        if (containerEl && renderer) {
          const rect = containerEl.getBoundingClientRect();
          const newSize = Math.min(rect.width, rect.height);
          if (newSize > 0) {
            renderer.resize(newSize);
          }
        }
      });
      if (containerEl) ro.observe(containerEl);

      return () => {
        ro.disconnect();
      };
    } catch (err) {
      console.error('IrisRenderer init hatasi', err);
    }
  });

  onDestroy(() => {
    if (renderer) {
      renderer.destroy();
      renderer = null;
    }
    window.removeEventListener('mousemove', handleMouseMove);
    window.removeEventListener('touchmove', handleTouchMove);
  });
</script>

<div class="organik-iris-container" bind:this={containerEl} style="--size:{size}px;">
  <div class="iris-glow"></div>
  <div class="iris-bezel">
    <span class="screw s-n"></span>
    <span class="screw s-e"></span>
    <span class="screw s-s"></span>
    <span class="screw s-w"></span>
    <div class="iris-socket">
      <canvas bind:this={canvasEl} class="iris-canvas gpu-accelerated" width={size} height={size}></canvas>
      <div class="iris-inner-shadow"></div>
      {#if $isProcessing || scanning}
        <div class="iris-scan-beam"></div>
      {/if}
    </div>
  </div>
  <div class="iris-halo" class:scanning={$isProcessing || scanning}></div>
</div>

<style>
  .organik-iris-container {
    position: relative;
    width: var(--size);
    height: var(--size);
    display: flex;
    align-items: center;
    justify-content: center;
    transform: translateZ(0);
    will-change: transform;
  }

  .iris-glow {
    position: absolute;
    inset: -18%;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(212, 175, 55, 0.22) 0%, rgba(212, 175, 55, 0.08) 40%, transparent 70%);
    filter: blur(18px);
    animation: irisGlowPulse 4s ease-in-out infinite;
    pointer-events: none;
    transform: translateZ(0);
  }

  @keyframes irisGlowPulse {
    0%, 100% { opacity: 0.7; transform: scale(1) translateZ(0); }
    50% { opacity: 1; transform: scale(1.08) translateZ(0); }
  }

  .iris-bezel {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background: conic-gradient(from 210deg, #5a3a16, #d8b45a, #8a6332, #fef0be, #8a6332, #5a3a16, #e8c766, #5a3a16);
    padding: 4.5%;
    box-shadow:
      0 0 0 2px #120803,
      0 0 0 3px #ffecb3,
      0 14px 44px rgba(0, 0, 0, 0.9),
      0 0 55px rgba(212, 175, 55, 0.35),
      inset 0 2px 4px rgba(255, 255, 255, 0.7),
      inset 0 -3px 6px rgba(0, 0, 0, 0.7);
    transform: translateZ(0);
    will-change: transform;
  }

  .screw {
    position: absolute;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #a67f38 0%, #3a220e 70%, #120803 100%);
    border: 1px solid #0d0602;
    box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.5);
    z-index: 3;
  }
  .s-n { top: 1.6%; left: calc(50% - 3.5px); }
  .s-s { bottom: 1.6%; left: calc(50% - 3.5px); }
  .s-e { right: 1.6%; top: calc(50% - 3.5px); }
  .s-w { left: 1.6%; top: calc(50% - 3.5px); }

  .iris-socket {
    position: relative;
    width: 100%;
    height: 100%;
    border-radius: 50%;
    overflow: hidden;
    background: #050302;
    box-shadow: inset 0 0 14% rgba(0, 0, 0, 0.95), 0 0 0 2px #120904;
    transform: translateZ(0);
  }

  .iris-canvas {
    position: absolute;
    inset: 0;
    width: 100% !important;
    height: 100% !important;
    border-radius: 50%;
    display: block;
    transform: translateZ(0);
    will-change: transform;
    backface-visibility: hidden;
  }

  .iris-inner-shadow {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    box-shadow: inset 0 0 30px rgba(0, 0, 0, 0.85), inset 0 2px 8px rgba(0, 0, 0, 0.9);
    pointer-events: none;
    z-index: 2;
  }

  .iris-scan-beam {
    position: absolute;
    left: -5%;
    right: -5%;
    top: -25%;
    height: 22%;
    background: linear-gradient(180deg, transparent, rgba(56, 239, 125, 0.5) 42%, rgba(225, 255, 236, 0.9) 50%, rgba(56, 239, 125, 0.5) 58%, transparent);
    filter: blur(0.5px);
    animation: beamSweep 1.15s linear infinite;
    z-index: 3;
    pointer-events: none;
  }

  @keyframes beamSweep {
    from { top: -25%; }
    to { top: 112%; }
  }

  .iris-halo {
    position: absolute;
    inset: -8%;
    border-radius: 50%;
    border: 1px solid rgba(212, 175, 55, 0.18);
    box-shadow: 0 0 0 1px rgba(212, 175, 55, 0.08), inset 0 0 20px rgba(212, 175, 55, 0.06);
    pointer-events: none;
    animation: haloRotate 20s linear infinite;
  }

  .iris-halo.scanning {
    border-color: rgba(56, 239, 125, 0.45);
    box-shadow: 0 0 20px rgba(56, 239, 125, 0.3), inset 0 0 20px rgba(56, 239, 125, 0.1);
    animation-duration: 3s;
  }

  @keyframes haloRotate {
    from { transform: rotate(0deg) translateZ(0); }
    to { transform: rotate(360deg) translateZ(0); }
  }
</style>
