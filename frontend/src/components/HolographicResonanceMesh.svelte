<script lang="ts">
  /**
   * HOLOGRAPHIC RESONANCE MESH — [FAZ B · B4] ARTIK GERÇEK VERİ ÇİZER.
   *
   * Eski durum: `generateNodes()` 12 dış + 8 iç düğümü `Math.random()` ile
   * üretiyordu; örgü tamamen SÜSTÜ, kanıtla ilgisi yoktu.
   *
   * Yeni durum: düğüm ve kenarlar `graph` prop'undan gelir ve yalnızca
   * KANITTAN üretilir (`agent_core/services/graph_builder.py`):
   *   - hedef (merkez) · kaynak sunucu (dış halka) · motor (orta) · gün (iç)
   *   - kenar = aynı kanıt kaydında birlikte geçme (co-occurrence)
   * Graf yoksa/boşsa rastgele düğüm ÜRETİLMEZ: ortam halkaları ve çekirdek
   * kalır, boşluk dürüstçe boş çizilir.
   */
  import { onMount, onDestroy } from 'svelte';
  import { isProcessing } from '../store';

  export let size: number = 520;
  export let active: boolean = false;
  export let intensity: number = 0.85;
  /** Kanıttan üretilmiş gerçek graf (yoksa null → uydurma düğüm yok). */
  export let graph: {
    available: boolean;
    nodes: Array<{ id: string; label: string; kind: string; weight: number; evidence_count: number }>;
    edges: Array<{ source: string; target: string; weight: number }>;
    node_count?: number;
    edge_count?: number;
    machine_note?: string;
  } | null = null;

  let canvasEl: HTMLCanvasElement | null = null;
  let ctx: CanvasRenderingContext2D | null = null;
  let rafId = 0;
  let alive = false;
  let startTime = 0;

  interface Placed {
    id: string;
    label: string;
    kind: string;
    weight: number;
    angle: number;
    radius: number;
    dot: number;
    x: number;
    y: number;
  }

  interface Link {
    a: Placed;
    b: Placed;
    weight: number;
  }

  let placed: Placed[] = [];
  let links: Link[] = [];

  // Halka yerleşimi: tür -> yarıçap oranı (hedef merkezde).
  const RADIUS_BY_KIND: Record<string, number> = {
    target: 0.0,
    engine: 0.22,
    day: 0.3,
    host: 0.42,
  };
  const KIND_ORDER: Record<string, number> = { target: 0, engine: 1, day: 2, host: 3 };
  const COLOR_BY_KIND: Record<string, string> = {
    target: '255, 255, 255',
    host: '56, 239, 125',
    engine: '212, 175, 55',
    day: '120, 200, 255',
  };

  function kindRank(kind: string): number {
    return KIND_ORDER[kind] ?? 2;
  }

  /**
   * Graf -> deterministik yerleşim. `Math.random()` YOKTUR: aynı kanıt her
   * zaman aynı örgüyü çizer (denetlenebilirlik).
   */
  function layout(g: typeof graph): void {
    placed = [];
    links = [];
    if (!g || !g.available || !Array.isArray(g.nodes) || g.nodes.length === 0) {
      return; // uydurma düğüm YOK
    }

    const order = [...g.nodes].sort(
      (a, b) => kindRank(a.kind) - kindRank(b.kind) || a.id.localeCompare(b.id)
    );
    const totals = new Map<string, number>();
    const seen = new Map<string, number>();
    for (const n of order) totals.set(n.kind, (totals.get(n.kind) ?? 0) + 1);

    const byId = new Map<string, Placed>();
    for (const n of order) {
      const i = seen.get(n.kind) ?? 0;
      seen.set(n.kind, i + 1);
      const total = totals.get(n.kind) ?? 1;
      const kind = n.kind || 'host';
      const angle = (i / total) * Math.PI * 2 + kindRank(kind) * 0.35;
      const weight = Math.max(1, Number(n.weight) || 1);
      const p: Placed = {
        id: n.id,
        label: n.label,
        kind,
        weight,
        angle,
        radius: RADIUS_BY_KIND[kind] ?? 0.34,
        dot: 1.8 + Math.min(3.2, Math.log2(1 + weight) * 0.9),
        x: 0,
        y: 0,
      };
      placed.push(p);
      byId.set(n.id, p);
    }

    for (const e of g.edges ?? []) {
      const a = byId.get(e.source);
      const b = byId.get(e.target);
      if (a && b) links.push({ a, b, weight: Math.max(1, Number(e.weight) || 1) });
    }
  }

  $: layout(graph);

  function resizeCanvas() {
    if (!canvasEl) return;
    const dpr = window.devicePixelRatio || 1;
    canvasEl.width = size * dpr;
    canvasEl.height = size * dpr;
    canvasEl.style.width = `${size}px`;
    canvasEl.style.height = `${size}px`;
    if (ctx) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
  }

  // Reactive processing flag — svelte-check için $isProcessing'i reactive statement'ta tut
  let isProc = false;
  $: isProc = $isProcessing || active;

  function render(t: number) {
    if (!ctx || !canvasEl) return;
    // Local non-null narrowed reference — svelte-check için kritik
    const c = ctx as CanvasRenderingContext2D;
    const elapsed = (t - startTime) * 0.001;
    const center = size / 2;
    const processing = isProc;
    const procSpeed = processing ? 1.8 : 0.6;

    c.clearRect(0, 0, size, size);

    // Background subtle radial
    const bgGrad = c.createRadialGradient(center, center, 0, center, center, size * 0.5);
    bgGrad.addColorStop(0, `rgba(56, 239, 125, ${0.03 * intensity})`);
    bgGrad.addColorStop(0.5, `rgba(16, 185, 129, ${0.015 * intensity})`);
    bgGrad.addColorStop(1, 'transparent');
    c.fillStyle = bgGrad;
    c.beginPath();
    c.arc(center, center, size * 0.5, 0, Math.PI * 2);
    c.fill();

    c.save();
    c.translate(center, center);

    // --- ORTAM HALKALARI (dekoratif kasa; veri DEĞİLDİR) ---
    c.rotate(elapsed * 0.15 * procSpeed);
    c.strokeStyle = `rgba(56, 239, 125, ${0.35 * intensity})`;
    c.lineWidth = 1.2;
    c.setLineDash([8, 12]);
    c.lineDashOffset = -elapsed * 20 * procSpeed;
    c.beginPath();
    c.arc(0, 0, size * 0.42, 0, Math.PI * 2);
    c.stroke();
    c.setLineDash([]);

    c.strokeStyle = `rgba(56, 239, 125, ${0.22 * intensity})`;
    c.lineWidth = 0.8;
    c.setLineDash([4, 8]);
    c.lineDashOffset = elapsed * 15 * procSpeed;
    c.beginPath();
    c.arc(0, 0, size * 0.24, 0, Math.PI * 2);
    c.stroke();
    c.setLineDash([]);
    c.rotate(-elapsed * 0.15 * procSpeed);

    // --- GERÇEK GRAF (kanıt varsa) ---
    // Yörünge dönüşü yalnızca veri düğümleri için; pozisyonlar deterministik.
    for (const node of placed) {
      const orbit = node.kind === 'target' ? 0 : elapsed * 0.04 * procSpeed;
      const r = node.radius * size * (1 + Math.sin(elapsed * 0.6 + node.angle) * 0.006);
      node.x = Math.cos(node.angle + orbit) * r;
      node.y = Math.sin(node.angle + orbit) * r;
    }

    // Kenarlar: ağırlık -> parlaklık (kanıt tekrarı)
    for (const link of links) {
      const alpha = Math.min(0.5, 0.08 + Math.log2(1 + link.weight) * 0.06);
      c.strokeStyle = `rgba(56, 239, 125, ${alpha * intensity})`;
      c.lineWidth = 0.5 + Math.min(1.2, link.weight * 0.15);
      c.beginPath();
      c.moveTo(link.a.x, link.a.y);
      c.lineTo(link.b.x, link.b.y);
      c.stroke();
    }

    // Düğümler: tür -> renk, ağırlık -> çap
    for (const node of placed) {
      const color = COLOR_BY_KIND[node.kind] ?? '56, 239, 125';
      const pulse = Math.sin(elapsed * 2.0 + node.angle * 3) * 0.5 + 0.5;
      c.fillStyle = `rgba(${color}, ${0.45 + pulse * 0.45})`;
      c.shadowColor = `rgb(${color})`;
      c.shadowBlur = 5 + pulse * 5;
      c.beginPath();
      c.arc(node.x, node.y, node.dot + pulse * 0.8, 0, Math.PI * 2);
      c.fill();
      c.shadowBlur = 0;
    }

    // Etiketler: yalnız hedef ve en ağır üç düğüm (kalabalık olmasın)
    const labelled = [...placed].sort((a, b) => b.weight - a.weight).slice(0, 4);
    c.font = '8px "JetBrains Mono", monospace';
    c.textAlign = 'center';
    for (const node of labelled) {
      if (node.kind === 'target') continue;
      c.fillStyle = `rgba(180, 255, 210, ${0.5 * intensity})`;
      const text = node.label.length > 14 ? `${node.label.slice(0, 13)}…` : node.label;
      c.fillText(text, node.x, node.y - node.dot - 4);
    }

    // Merkez çekirdek
    const corePulse = Math.sin(elapsed * 1.2) * 0.5 + 0.5;
    c.fillStyle = `rgba(56, 239, 125, ${0.15 + corePulse * 0.15})`;
    c.beginPath();
    c.arc(0, 0, 6 + corePulse * 3, 0, Math.PI * 2);
    c.fill();
    c.fillStyle = `rgba(255, 255, 255, ${0.8 + corePulse * 0.2})`;
    c.beginPath();
    c.arc(0, 0, 1.5, 0, Math.PI * 2);
    c.fill();

    // Radial scan line when processing
    if (processing) {
      c.strokeStyle = `rgba(56, 239, 125, ${0.12 + corePulse * 0.08})`;
      c.lineWidth = 1;
      c.beginPath();
      c.moveTo(0, 0);
      const scanAngle = elapsed * 2.5;
      c.lineTo(Math.cos(scanAngle) * size * 0.42, Math.sin(scanAngle) * size * 0.42);
      c.stroke();
    }

    c.restore();
  }

  function loop(t: number) {
    if (!alive) return;
    render(t);
    rafId = requestAnimationFrame(loop);
  }

  onMount(() => {
    if (!canvasEl) return;
    const context = canvasEl.getContext('2d', { alpha: true });
    if (!context) return;
    ctx = context;
    resizeCanvas();
    startTime = performance.now();
    alive = true;
    rafId = requestAnimationFrame(loop);
  });

  onDestroy(() => {
    alive = false;
    if (rafId) cancelAnimationFrame(rafId);
  });

  // Resize reactive — sadece size değiştiğinde
  $: if (canvasEl && size) {
    resizeCanvas();
  }

  $: graphEmpty = !!graph && (!graph.available || (graph.nodes?.length ?? 0) === 0);
</script>

<div class="holographic-mesh-container" style="--size:{size}px;">
  <canvas bind:this={canvasEl} class="holographic-canvas gpu-accelerated" width={size} height={size}></canvas>
  <div class="mesh-vignette"></div>
  {#if graphEmpty}
    <!-- Uydurma düğüm YOK: kanıt yoksa boşluk dürüstçe boş çizilir. -->
    <div class="mesh-empty" title="Kanıt yok — graf boş">KANIT YOK</div>
  {/if}
</div>

<style>
  .holographic-mesh-container {
    position: relative;
    width: var(--size);
    height: var(--size);
    pointer-events: none;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .holographic-canvas {
    display: block;
    will-change: transform;
    transform: translateZ(0);
  }

  .mesh-vignette {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: radial-gradient(
      circle at center,
      transparent 55%,
      rgba(0, 0, 0, 0.35) 100%
    );
    mix-blend-mode: multiply;
  }

  .mesh-empty {
    position: absolute;
    bottom: 6px;
    left: 50%;
    transform: translateX(-50%);
    font-family: 'JetBrains Mono', monospace;
    font-size: 7px;
    letter-spacing: 0.12em;
    color: rgba(180, 255, 210, 0.35);
    white-space: nowrap;
  }
</style>
