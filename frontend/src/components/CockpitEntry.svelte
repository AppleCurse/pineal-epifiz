<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import PinealEye from './PinealEye.svelte';
  import defaultEye from '../assets/eye.jpg';
  import { eyeImage } from '../store';
  import { playClick, playRunning, playToggle } from '../lib/consoleAudio';

  // KOKPİT GİRİŞİ — görseldeki izometrik plakalar süzülür, tam ortada göz durur.
  // Göze tıklayınca (veya Enter) retina taraması başlar, sonra kokpite geçilir.
  export let onEnter: () => void = () => {};

  const EYE_KEY = 'pineal_custom_eye';

  let rootEl: HTMLDivElement | null = null;
  let tiltEl: HTMLDivElement | null = null;
  let eyeWrapEl: HTMLDivElement | null = null;
  let fileInput: HTMLInputElement | null = null;
  let eyeComp: any = null;

  let customEye: string | null = null;
  let entering = false;
  let warping = false;
  let progress = 0;
  let done = false;

  $: statusText = !entering
    ? 'RETİNA SENKRONİZE · GÖZ KİLİDİ AÇIK'
    : progress < 30
      ? 'İRİS DESENİ OKUNUYOR...'
      : progress < 65
        ? 'RETİNA EŞLEŞTİ ✓'
        : progress < 100
          ? 'KOKPİT MÜHRÜ ÇÖZÜLÜYOR...'
          : 'GİRİŞ ONAYLANDI ✓';

  // Süzülen toz parçacıkları
  const particles = Array.from({ length: 26 }, () => ({
    x: Math.random() * 100,
    y: Math.random() * 100,
    s: Math.random() * 2.4 + 1,
    d: 7 + Math.random() * 9,
    dl: -Math.random() * 12,
    gold: Math.random() > 0.45,
  }));

  function onMouse(e: MouseEvent) {
    if (!rootEl || warping) return;
    const nx = e.clientX / window.innerWidth - 0.5;
    const ny = e.clientY / window.innerHeight - 0.5;
    if (tiltEl) {
      tiltEl.style.transform = `translate(-50%, -50%) rotateX(${(-ny * 12).toFixed(2)}deg) rotateY(${(nx * 14).toFixed(2)}deg)`;
    }
    if (eyeWrapEl) {
      eyeWrapEl.style.setProperty('--ex', `${(nx * -16).toFixed(1)}px`);
      eyeWrapEl.style.setProperty('--ey', `${(ny * -12).toFixed(1)}px`);
    }
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !entering) startEnter();
  }

  function startEnter() {
    if (entering || done) return;
    entering = true;
    playRunning();
    try {
      eyeComp?.blink?.();
    } catch {
      /* göz ref'i yoksa sessiz geç */
    }
    const t0 = performance.now();
    const dur = 1700;
    const step = (t: number) => {
      if (!entering) return;
      const p = Math.min((t - t0) / dur, 1);
      progress = Math.round(p * 100);
      if (p >= 0.5 && p < 0.53) playClick(520, 40);
      if (p < 1) {
        requestAnimationFrame(step);
      } else {
        beginWarp();
      }
    };
    requestAnimationFrame(step);
  }

  function beginWarp() {
    warping = true;
    playToggle(true);
    setTimeout(() => playClick(660, 90), 120);
    setTimeout(() => {
      done = true;
      onEnter();
    }, 780);
  }

  function openUpload() {
    playClick(300, 40);
    fileInput?.click();
  }

  function onFile(e: Event) {
    const input = e.target as HTMLInputElement;
    const f = input.files?.[0];
    input.value = '';
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        try {
          // localStorage şişmesin diye en uzun kenarı 512px'e indir.
          const max = 512;
          const scale = Math.min(1, max / Math.max(img.width, img.height));
          const w = Math.max(1, Math.round(img.width * scale));
          const h = Math.max(1, Math.round(img.height * scale));
          const c = document.createElement('canvas');
          c.width = w;
          c.height = h;
          c.getContext('2d')?.drawImage(img, 0, 0, w, h);
          customEye = c.toDataURL('image/jpeg', 0.85);
          eyeImage.set(customEye);
          try {
            localStorage.setItem(EYE_KEY, customEye);
          } catch {
            /* kota dolarsa yalnızca oturumluk kullan */
          }
          playClick(420, 60);
        } catch {
          /* bozuk dosya: sessiz geç */
        }
      };
      img.src = reader.result as string;
    };
    reader.readAsDataURL(f);
  }

  function resetEye() {
    customEye = null;
    eyeImage.set(null);
    try {
      localStorage.removeItem(EYE_KEY);
    } catch {
      /* yoksay */
    }
    playClick(200, 40);
  }

  onMount(() => {
    try {
      customEye = localStorage.getItem(EYE_KEY);
    } catch {
      customEye = null;
    }
    eyeImage.set(customEye);
    document.body.style.overflow = 'hidden';
    window.addEventListener('mousemove', onMouse, { passive: true });
    window.addEventListener('keydown', onKey);
  });

  onDestroy(() => {
    document.body.style.overflow = '';
    window.removeEventListener('mousemove', onMouse);
    window.removeEventListener('keydown', onKey);
  });
</script>

<div class="cockpit-entry {warping ? 'is-warping' : ''}" bind:this={rootEl} role="dialog" aria-label="Kokpit girişi">
  <div class="void-bg"></div>
  <div class="stars" aria-hidden="true">
    {#each particles as p}
      <span
        class="mote {p.gold ? 'mote-gold' : 'mote-pale'}"
        style="left:{p.x}%; top:{p.y}%; width:{p.s}px; height:{p.s}px; animation-duration:{p.d}s; animation-delay:{p.dl}s;"
      ></span>
    {/each}
  </div>

  <div class="entry-frame">
    <span class="corner c-tl"></span>
    <span class="corner c-tr"></span>
    <span class="corner c-bl"></span>
    <span class="corner c-br"></span>

    <div class="top-plaque">
      <div class="plaque-title font-cinzel">PINEAL-HERETIC</div>
      <div class="plaque-sub">360° BÜTÜNCÜL İNSAN TANIMA İSTASYONU</div>
    </div>

    <div class="stage">
      <!-- İzometrik süzülen plakalar (görseldeki gibi) -->
      <div class="tilt" bind:this={tiltEl}>
        <div class="bob">
          <div class="iso-scene" aria-hidden="true">
            <div class="plate plate-top"></div>
            <div class="plate plate-bottom"></div>
          </div>
          <div class="connectors" aria-hidden="true">
            <span class="conn conn-l"></span>
            <span class="conn conn-r"></span>
            <span class="conn conn-t"></span>
            <span class="conn conn-b"></span>
          </div>
        </div>
        <div class="orbit orbit-a" aria-hidden="true">
          <div class="spin spin-a"><span class="sat"></span></div>
        </div>
        <div class="orbit orbit-b" aria-hidden="true">
          <div class="spin spin-b"><span class="sat sat-b"></span></div>
        </div>
        <div class="core-glow" aria-hidden="true"></div>
      </div>

      <!-- TAM ORTADAKİ GÖZ -->
      <div class="eye-center" bind:this={eyeWrapEl}>
        <div
          class="eye-click"
          role="button"
          tabindex="0"
          aria-label="Kokpite girmek için göze tıkla"
          on:click={startEnter}
          on:keydown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              startEnter();
            }
          }}
        >
          <PinealEye bind:this={eyeComp} size={232} scanning={entering} customImage={customEye ?? defaultEye} interactive={!warping} />
        </div>
      </div>
    </div>

    <div class="hud">
      <div class="status-line">
        <span class="pulse-dot"></span>
        <span>{statusText}</span>
        <span class="cursor">▌</span>
      </div>
      {#if entering}
        <div class="scanbar" aria-label="Tarama ilerlemesi">
          <div class="scanfill" style="width:{progress}%"></div>
          <span class="scanpct">%{progress}</span>
        </div>
      {/if}
      <div class="btn-row">
        <button class="btn-brass enter-btn" on:click={startEnter} disabled={entering}>
          {entering ? 'TARAMA SÜRÜYOR...' : '◉ KOKPİTE GİR'}
        </button>
      </div>
      <div class="btn-row ghost-row">
        <button class="btn-dark" on:click={openUpload}>👁 GÖZÜ DEĞİŞTİR</button>
        {#if customEye}
          <button class="btn-dark" on:click={resetEye}>↺ GÖZÜMÜ GERİ GETİR</button>
        {/if}
      </div>
      <input type="file" accept="image/*" bind:this={fileInput} on:change={onFile} hidden aria-hidden="true" tabindex="-1" />
      <div class="hint">Göz seni takip eder · Göze tıkla ya da Enter'a bas</div>
    </div>
  </div>

  <div class="scanlines" aria-hidden="true"></div>
  <div class="vignette" aria-hidden="true"></div>
  <div class="flash" aria-hidden="true"></div>
</div>

<style>
  .cockpit-entry {
    position: fixed;
    inset: 0;
    z-index: 10000;
    overflow: hidden;
    background: #030201;
    font-family: 'JetBrains Mono', monospace;
  }

  .void-bg {
    position: absolute;
    inset: 0;
    background:
      radial-gradient(ellipse at 50% 42%, rgba(88, 52, 16, 0.5) 0%, rgba(10, 6, 3, 0.9) 55%, #020101 100%),
      repeating-linear-gradient(45deg, rgba(0, 0, 0, 0.14) 0 2px, transparent 2px 6px),
      repeating-linear-gradient(-45deg, rgba(0, 0, 0, 0.14) 0 2px, transparent 2px 6px);
  }

  .stars { position: absolute; inset: 0; pointer-events: none; }
  .mote {
    position: absolute;
    border-radius: 50%;
    opacity: 0;
    animation-name: moteFloat;
    animation-timing-function: linear;
    animation-iteration-count: infinite;
  }
  .mote-gold { background: #d4af37; box-shadow: 0 0 6px rgba(212, 175, 55, 0.8); }
  .mote-pale { background: #cfd8ff; box-shadow: 0 0 6px rgba(207, 216, 255, 0.7); }
  @keyframes moteFloat {
    0% { transform: translateY(0); opacity: 0; }
    12% { opacity: 0.7; }
    85% { opacity: 0.5; }
    100% { transform: translateY(-110px); opacity: 0; }
  }

  .entry-frame {
    position: relative;
    z-index: 3;
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
    transition: opacity 0.45s ease;
  }

  .corner {
    position: absolute;
    width: 34px;
    height: 34px;
    border: 2px solid rgba(212, 175, 55, 0.65);
    pointer-events: none;
  }
  .c-tl { top: 12px; left: 12px; border-right: none; border-bottom: none; border-radius: 8px 0 0 0; }
  .c-tr { top: 12px; right: 12px; border-left: none; border-bottom: none; border-radius: 0 8px 0 0; }
  .c-bl { bottom: 12px; left: 12px; border-right: none; border-top: none; border-radius: 0 0 0 8px; }
  .c-br { bottom: 12px; right: 12px; border-left: none; border-top: none; border-radius: 0 0 8px 0; }

  .top-plaque {
    text-align: center;
    padding: 26px 16px 6px;
    transition: opacity 0.45s ease;
  }
  .plaque-title {
    font-size: clamp(22px, 4.5vw, 34px);
    font-weight: 900;
    letter-spacing: 0.28em;
    text-indent: 0.28em;
    color: var(--gold);
    text-shadow: 0 0 18px rgba(212, 175, 55, 0.55), 0 2px 3px #000;
  }
  .plaque-sub {
    margin-top: 6px;
    font-size: clamp(9px, 1.8vw, 12px);
    letter-spacing: 0.32em;
    text-indent: 0.32em;
    color: var(--text-dim);
  }

  /* ---------- SAHNE ---------- */
  .stage {
    position: relative;
    flex: 1;
    min-height: 440px;
    perspective: 1100px;
  }

  .tilt {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 0;
    height: 0;
    transform: translate(-50%, -50%);
    transform-style: preserve-3d;
    transition: opacity 0.45s ease;
  }

  .bob {
    --plate: 300px;
    --field: 450px;
    position: absolute;
    left: 0;
    top: 0;
    width: 0;
    height: 0;
    transform-style: preserve-3d;
    animation: bobY 7s ease-in-out infinite alternate;
  }
  @keyframes bobY {
    from { transform: translateY(-10px); }
    to { transform: translateY(10px); }
  }

  .iso-scene {
    position: absolute;
    left: 0;
    top: 0;
    width: 0;
    height: 0;
    transform: rotateX(58deg) rotateZ(45deg);
    transform-style: preserve-3d;
  }

  .plate {
    position: absolute;
    width: var(--plate);
    height: var(--plate);
    left: calc(var(--plate) / -2);
    top: calc(var(--plate) / -2);
    border-radius: 22%;
  }
  .plate-top {
    background: radial-gradient(circle at 50% 38%, #0e0a06 0%, #050302 70%);
    border: 2px solid rgba(255, 255, 255, 0.9);
    box-shadow: 0 0 26px rgba(255, 255, 255, 0.16), inset 0 0 44px rgba(0, 0, 0, 0.9);
    animation: floatTop 4.6s ease-in-out infinite alternate;
  }
  @keyframes floatTop {
    from { transform: translateZ(92px); }
    to { transform: translateZ(118px); }
  }

  .plate-bottom {
    background: linear-gradient(135deg, #0c0716 0%, #050308 100%);
    border: 2px solid rgba(167, 139, 250, 0.65);
    transform-style: preserve-3d;
    animation: floatBottom 6.2s ease-in-out infinite alternate;
  }
  .plate-bottom::before,
  .plate-bottom::after {
    content: '';
    position: absolute;
    inset: -2px;
    border-radius: inherit;
    background: linear-gradient(135deg, #6d3df5 0%, #3b1a9e 42%, #1c0b52 100%);
    z-index: -1;
  }
  .plate-bottom::before {
    transform: translateZ(-15px);
    box-shadow: 0 0 30px rgba(139, 92, 246, 0.5);
  }
  .plate-bottom::after {
    transform: translateZ(-30px);
    background: linear-gradient(135deg, #4c26c4 0%, #241058 60%, #120822 100%);
    box-shadow: 0 0 55px rgba(139, 92, 246, 0.65);
  }
  @keyframes floatBottom {
    from { transform: translateZ(0px); }
    to { transform: translateZ(10px); }
  }

  /* Plakalar arası kesik çizgi kolonlar */
  .connectors {
    position: absolute;
    left: calc(var(--field) / -2);
    top: calc(var(--field) / -2);
    width: var(--field);
    height: var(--field);
    pointer-events: none;
  }
  .conn {
    position: absolute;
    width: 2px;
    background: repeating-linear-gradient(180deg, rgba(255, 255, 255, 0.55) 0 5px, transparent 5px 10px);
    animation: dashFall 1.1s linear infinite;
  }
  .conn-l { left: 3%; top: 50%; height: 88px; margin-top: -44px; opacity: 0.65; }
  .conn-r { right: 3%; top: 50%; height: 88px; margin-top: -44px; opacity: 0.65; }
  .conn-t { left: 50%; top: calc(50% - 168px); height: 44px; opacity: 0.28; }
  .conn-b { left: 50%; bottom: calc(50% - 168px); height: 44px; opacity: 0.28; }
  @keyframes dashFall {
    from { background-position-y: 0; }
    to { background-position-y: 10px; }
  }

  /* Yörünge halkaları */
  .orbit {
    position: absolute;
    left: 0;
    top: 0;
    border-radius: 50%;
    pointer-events: none;
  }
  .orbit-a {
    width: 384px;
    height: 384px;
    margin: -192px 0 0 -192px;
    border: 1px dashed rgba(212, 175, 55, 0.45);
    animation: orbitSpinA 22s linear infinite;
  }
  .orbit-b {
    width: 486px;
    height: 486px;
    margin: -243px 0 0 -243px;
    border: 1px dashed rgba(56, 239, 125, 0.28);
    animation: orbitSpinB 34s linear infinite reverse;
  }
  @keyframes orbitSpinA {
    from { transform: scaleY(0.58) rotate(0deg); }
    to { transform: scaleY(0.58) rotate(360deg); }
  }
  @keyframes orbitSpinB {
    from { transform: scaleY(0.58) rotate(0deg); }
    to { transform: scaleY(0.58) rotate(360deg); }
  }
  .spin { position: absolute; inset: 0; }
  .spin-a { animation: spinZ 9s linear infinite; }
  .spin-b { animation: spinZ 15s linear infinite reverse; }
  @keyframes spinZ {
    to { transform: rotate(360deg); }
  }
  .sat {
    position: absolute;
    left: 50%;
    top: -4px;
    width: 8px;
    height: 8px;
    margin-left: -4px;
    border-radius: 50%;
    background: #ffd978;
    box-shadow: 0 0 12px #d4af37, 0 0 22px rgba(212, 175, 55, 0.6);
  }
  .sat-b {
    background: #7dfcd0;
    box-shadow: 0 0 12px #10b981, 0 0 22px rgba(16, 185, 129, 0.6);
  }

  .core-glow {
    position: absolute;
    left: -170px;
    top: -170px;
    width: 340px;
    height: 340px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(212, 175, 55, 0.22) 0%, rgba(109, 61, 245, 0.1) 45%, transparent 70%);
    filter: blur(14px);
    animation: corePulse 5s ease-in-out infinite;
    pointer-events: none;
  }
  @keyframes corePulse {
    0%, 100% { opacity: 0.7; transform: scale(1); }
    50% { opacity: 1; transform: scale(1.12); }
  }

  /* ---------- TAM ORTADAKİ GÖZ ---------- */
  .eye-center {
    --ex: 0px;
    --ey: 0px;
    --es: 1;
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(calc(-50% + var(--ex)), calc(-50% + var(--ey))) scale(var(--es));
    z-index: 5;
  }
  .eye-click {
    cursor: pointer;
    border-radius: 50%;
    outline: none;
    transition: transform 0.7s cubic-bezier(0.2, 0.7, 0.3, 1), filter 0.7s ease;
  }
  .eye-click:hover { filter: brightness(1.1); }
  .eye-click:focus-visible {
    box-shadow: 0 0 0 3px #030201, 0 0 0 5px var(--gold), 0 0 34px rgba(212, 175, 55, 0.7);
  }

  /* ---------- HUD ---------- */
  .hud {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 4px 16px 30px;
    transition: opacity 0.45s ease;
  }
  .status-line {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.18em;
    color: var(--text-phosphor);
    text-shadow: 0 0 8px rgba(56, 239, 125, 0.6);
    text-align: center;
  }
  .pulse-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: #38ef7d;
    box-shadow: 0 0 10px #38ef7d;
    animation: dotBlink 1.2s ease-in-out infinite;
    flex-shrink: 0;
  }
  @keyframes dotBlink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }
  .cursor {
    animation: dotBlink 0.9s steps(1) infinite;
    color: #baffdb;
  }

  .scanbar {
    position: relative;
    width: min(340px, 72vw);
    height: 12px;
    background: #060302;
    border: 1px solid #4d3319;
    border-radius: 6px;
    overflow: hidden;
    box-shadow: inset 0 2px 5px #000;
  }
  .scanfill {
    height: 100%;
    background: linear-gradient(90deg, #0c5c36, #38ef7d, #d4af37);
    box-shadow: 0 0 12px rgba(56, 239, 125, 0.8);
    transition: width 0.08s linear;
  }
  .scanpct {
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 9px;
    font-weight: 800;
    color: #eafff2;
    text-shadow: 0 1px 2px #000;
  }

  .btn-row { display: flex; gap: 10px; }
  .enter-btn {
    font-size: 15px;
    letter-spacing: 0.14em;
    padding: 12px 34px;
  }
  .ghost-row .btn-dark { font-size: 10px; }

  .hint {
    font-size: 10px;
    letter-spacing: 0.14em;
    color: var(--text-muted);
  }

  /* ---------- Geçiş / warp ---------- */
  .flash {
    position: absolute;
    inset: 0;
    z-index: 8;
    background: radial-gradient(circle at 50% 46%, rgba(255, 250, 230, 0.98) 0%, rgba(212, 175, 55, 0.85) 34%, rgba(20, 12, 4, 0.9) 72%, rgba(3, 2, 1, 1) 100%);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.7s ease;
  }
  .is-warping .eye-click {
    transform: scale(2.7);
    filter: brightness(2.4) saturate(1.3);
  }
  .is-warping .flash { opacity: 1; }
  .is-warping .tilt,
  .is-warping .hud,
  .is-warping .top-plaque {
    opacity: 0;
  }

  .scanlines {
    position: absolute;
    inset: 0;
    z-index: 9;
    background: repeating-linear-gradient(180deg, rgba(0, 0, 0, 0.16) 0 2px, transparent 2px 4px);
    opacity: 0.4;
    pointer-events: none;
  }
  .vignette {
    position: absolute;
    inset: 0;
    z-index: 9;
    background: radial-gradient(ellipse at 50% 46%, transparent 42%, rgba(0, 0, 0, 0.78) 100%);
    pointer-events: none;
  }

  @media (max-width: 640px) {
    .bob { --plate: 208px; --field: 320px; }
    .eye-center { --es: 0.72; }
    .stage { min-height: 380px; }
    .orbit-a { width: 300px; height: 300px; margin: -150px 0 0 -150px; }
    .orbit-b { width: 380px; height: 380px; margin: -190px 0 0 -190px; }
    .conn-l, .conn-r { height: 64px; margin-top: -32px; }
    .conn-t { top: calc(50% - 128px); }
    .conn-b { bottom: calc(50% - 128px); }
    .enter-btn { padding: 11px 26px; font-size: 13px; }
  }

  @media (prefers-reduced-motion: reduce) {
    .bob, .plate-top, .plate-bottom, .orbit-a, .orbit-b, .spin-a, .spin-b,
    .core-glow, .mote, .conn, .pulse-dot, .cursor {
      animation: none;
    }
  }
</style>
