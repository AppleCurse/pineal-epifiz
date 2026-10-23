<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import {
    apiFetch, clientId, isProcessing, taskStatus, logs, agentStatuses,
    vaultLocked, supportRequests, refreshSupport, activeViewMode
  } from '../store';

  // --- MODEL TANIMLARI ---
  interface PipelineStep {
    id: string;
    title: string;
    description: string;
    status: 'idle' | 'running' | 'completed' | 'warning' | 'error';
    meta?: string;
  }

  interface SocialProbeItem {
    platform: string;
    url: string;
    status: 'claimed' | 'absent' | 'unknown' | 'pending';
    http_status?: number;
    reason?: string;
  }

  interface GraphNode {
    id: string;
    label: string;
    type: 'root' | 'platform' | 'url' | 'entity' | 'risk';
    status: 'claimed' | 'absent' | 'unknown' | 'active';
    x: number;
    y: number;
    vx: number;
    vy: number;
    radius: number;
    data?: any;
  }

  interface GraphLink {
    source: string;
    target: string;
    label?: string;
  }

  // --- STATE ---
  let targetInput = '';
  let selectedMode: 'full' | 'quick' | 'probe' = 'full';
  let isTargetValid = false;
  let activeTab: 'graph' | 'matrix' | 'correlations' | 'evidence' | 'agents' = 'graph';
  let selectedNode: GraphNode | null = null;
  let currentMissionId: string | null = null;
  let missionStartTime: number | null = null;
  let elapsedTime = '00:00';
  let timerInterval: any = null;

  // Aspasia Chat
  let aspasiaPrompt = '';
  let aspasiaMessages: Array<{ role: 'user' | 'aspasia'; text: string; time: string }> = [
    {
      role: 'aspasia',
      text: 'Operasyon Kokpiti devrede. Hedef kullanıcı adını veya profil URL\'sini girin, 10 sosyal ağ ve tüm harici biyografi bağlantılarını çapraz haritalandıralım.',
      time: new Date().toLocaleTimeString()
    }
  ];
  let isAskingAspasia = false;

  // Pipeline Adımları
  let pipelineSteps: PipelineStep[] = [
    {
      id: 'target_intake',
      title: '1. Hedef Rota & Ayrıştırma',
      description: 'Girdi inceleniyor, platform ve format tespit ediliyor.',
      status: 'idle'
    },
    {
      id: 'handle_probe',
      title: '2. 10 Ağda Çapraz Varlık Yoklaması',
      description: 'Instagram, X, Threads, TikTok, GitHub, Reddit taranıyor.',
      status: 'idle'
    },
    {
      id: 'link_harvesting',
      title: '3. Biyografi & Gönderi Link Avı',
      description: 'Bio ve paylaşımlardaki Linktree, Beacons ve siteler toplanıyor.',
      status: 'idle'
    },
    {
      id: 'deep_scan',
      title: '4. Derin Profil Çözümleme',
      description: 'Tespit edilen ikincil bağlantıların içine giriliyor.',
      status: 'idle'
    },
    {
      id: 'synthesis',
      title: '5. Adli Sentez & Karar',
      description: 'Bilişsel motorlar ve Aspasia Chief nihai profili çıkarıyor.',
      status: 'idle'
    }
  ];

  // 10 Platform Sosyal Matris
  let socialMatrix: SocialProbeItem[] = [
    { platform: 'Instagram', url: '', status: 'pending' },
    { platform: 'X (Twitter)', url: '', status: 'pending' },
    { platform: 'Facebook', url: '', status: 'pending' },
    { platform: 'Threads', url: '', status: 'pending' },
    { platform: 'TikTok', url: '', status: 'pending' },
    { platform: 'GitHub', url: '', status: 'pending' },
    { platform: 'Reddit', url: '', status: 'pending' },
    { platform: 'Telegram', url: '', status: 'pending' },
    { platform: 'YouTube', url: '', status: 'pending' },
    { platform: 'Pinterest', url: '', status: 'pending' },
  ];

  // Düğümler ve İlişkiler (SpiderFoot Graph)
  let canvas: HTMLCanvasElement | null = null;
  let ctx: CanvasRenderingContext2D | null = null;
  let animationFrameId: any = null;
  let nodes: GraphNode[] = [];
  let links: GraphLink[] = [];
  let zoom = 1;
  let panX = 0;
  let panY = 0;
  let isDraggingCanvas = false;
  let draggedNode: GraphNode | null = null;
  let dragStartX = 0;
  let dragStartY = 0;

  // Korelasyonlar & Riskler
  let correlations: Array<{ type: 'risk' | 'match' | 'anomaly'; title: string; desc: string; confidence: number }> = [];

  // Toplanan Kanıtlar
  let evidenceItems: Array<{ id: string; type: string; value: string; source: string; verified: boolean; time: string }> = [];

  $: isTargetValid = targetInput.trim().length > 1;

  // --- İNTERAKTİF DÜĞÜM HARİTASI KURULUMU ---
  function resetGraph(rootLabel: string = 'HEDEF') {
    const width = canvas ? canvas.width : 800;
    const height = canvas ? canvas.height : 500;
    const centerX = width / 2;
    const centerY = height / 2;

    nodes = [
      {
        id: 'root',
        label: rootLabel,
        type: 'root',
        status: 'active',
        x: centerX,
        y: centerY,
        vx: 0,
        vy: 0,
        radius: 26,
        data: { target: rootLabel }
      }
    ];
    links = [];
  }

  function addPlatformNode(platform: string, url: string, status: 'claimed' | 'absent' | 'unknown') {
    const existing = nodes.find(n => n.id === `plat_${platform}`);
    if (existing) {
      existing.status = status;
      existing.data = { platform, url, status };
      return;
    }

    const angle = Math.random() * Math.PI * 2;
    const dist = 140 + Math.random() * 40;
    const root = nodes.find(n => n.id === 'root') || { x: 400, y: 250 };

    const newNode: GraphNode = {
      id: `plat_${platform}`,
      label: platform,
      type: 'platform',
      status,
      x: root.x + Math.cos(angle) * dist,
      y: root.y + Math.sin(angle) * dist,
      vx: (Math.random() - 0.5) * 2,
      vy: (Math.random() - 0.5) * 2,
      radius: 18,
      data: { platform, url, status }
    };

    nodes.push(newNode);
    links.push({ source: 'root', target: newNode.id, label: status === 'claimed' ? 'BAĞLI' : 'YOKLANDI' });
    nodes = [...nodes];
    links = [...links];
  }

  function addUrlNode(parentPlatform: string, url: string, label: string) {
    const id = `url_${encodeURIComponent(url).slice(0, 24)}`;
    if (nodes.find(n => n.id === id)) return;

    const parentNode = nodes.find(n => n.id === `plat_${parentPlatform}`) || nodes[0];
    const angle = Math.random() * Math.PI * 2;
    const dist = 90 + Math.random() * 30;

    const newNode: GraphNode = {
      id,
      label: label.length > 20 ? label.slice(0, 18) + '...' : label,
      type: 'url',
      status: 'active',
      x: parentNode.x + Math.cos(angle) * dist,
      y: parentNode.y + Math.sin(angle) * dist,
      vx: (Math.random() - 0.5) * 1.5,
      vy: (Math.random() - 0.5) * 1.5,
      radius: 14,
      data: { fullUrl: url, parent: parentPlatform }
    };

    nodes.push(newNode);
    links.push({ source: parentNode.id, target: id, label: 'BİO LİNK' });
    nodes = [...nodes];
    links = [...links];
  }

  // Fizik Motoru ve Render Döngüsü
  function runPhysicsStep() {
    if (!canvas || !ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    const cx = width / 2;
    const cy = height / 2;

    // Düğümler arası itme kuvveti
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[j].x - nodes[i].x;
        const dy = nodes[j].y - nodes[i].y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const minDist = nodes[i].radius + nodes[j].radius + 50;
        if (dist < minDist) {
          const force = (minDist - dist) / dist * 0.4;
          nodes[i].vx -= dx * force;
          nodes[i].vy -= dy * force;
          nodes[j].vx += dx * force;
          nodes[j].vy += dy * force;
        }
      }
    }

    // Bağlantılar arası çekme kuvveti
    for (const link of links) {
      const src = nodes.find(n => n.id === link.source);
      const tgt = nodes.find(n => n.id === link.target);
      if (src && tgt) {
        const dx = tgt.x - src.x;
        const dy = tgt.y - src.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const idealDist = src.type === 'root' ? 140 : 80;
        const force = (dist - idealDist) * 0.015;
        src.vx += dx * force;
        src.vy += dy * force;
        tgt.vx -= dx * force;
        tgt.vy -= dy * force;
      }
    }

    // Merkeze hafif yerçekimi & sönümleme
    for (const node of nodes) {
      if (node !== draggedNode) {
        node.vx += (cx - node.x) * 0.002;
        node.vy += (cy - node.y) * 0.002;
        node.vx *= 0.88;
        node.vy *= 0.88;
        node.x += node.vx;
        node.y += node.vy;
      }
    }

    // ÇİZİM
    ctx.clearRect(0, 0, width, height);
    ctx.save();
    ctx.translate(panX, panY);
    ctx.scale(zoom, zoom);

    // Çizgiler (Bağlantılar)
    for (const link of links) {
      const src = nodes.find(n => n.id === link.source);
      const tgt = nodes.find(n => n.id === link.target);
      if (src && tgt) {
        ctx.beginPath();
        ctx.moveTo(src.x, src.y);
        ctx.lineTo(tgt.x, tgt.y);
        ctx.strokeStyle = 'rgba(56, 239, 125, 0.25)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        if (link.label) {
          const midX = (src.x + tgt.x) / 2;
          const midY = (src.y + tgt.y) / 2;
          ctx.font = '9px "JetBrains Mono", monospace';
          ctx.fillStyle = 'rgba(212, 175, 55, 0.7)';
          ctx.fillText(link.label, midX - 10, midY - 4);
        }
      }
    }

    // Düğümler (Nodes)
    for (const node of nodes) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);

      // Renk paleti
      let fillColor = '#0f172a';
      let strokeColor = '#38ef7d';

      if (node.type === 'root') {
        fillColor = '#dc2626';
        strokeColor = '#f59e0b';
      } else if (node.type === 'platform') {
        if (node.status === 'claimed') {
          fillColor = '#065f46';
          strokeColor = '#10b981';
        } else if (node.status === 'absent') {
          fillColor = '#1e293b';
          strokeColor = '#64748b';
        } else {
          fillColor = '#854d0e';
          strokeColor = '#eab308';
        }
      } else if (node.type === 'url') {
        fillColor = '#1e1b4b';
        strokeColor = '#818cf8';
      }

      ctx.fillStyle = fillColor;
      ctx.fill();
      ctx.lineWidth = node === selectedNode ? 3 : 1.5;
      ctx.strokeStyle = node === selectedNode ? '#ffffff' : strokeColor;
      ctx.stroke();

      // Düğüm İçi / Yanı Yazı
      ctx.font = node.type === 'root' ? 'bold 11px "JetBrains Mono", monospace' : '10px "JetBrains Mono", monospace';
      ctx.fillStyle = '#f8fafc';
      ctx.textAlign = 'center';
      ctx.fillText(node.label, node.x, node.y + node.radius + 14);
    }

    ctx.restore();
    animationFrameId = requestAnimationFrame(runPhysicsStep);
  }

  // --- CANLI GÖREV BAŞLATMA & VERİ DİNLEME ---
  async function startMission() {
    if (!targetInput.trim()) return;

    const target = targetInput.trim();
    isProcessing.set(true);
    missionStartTime = Date.now();
    currentMissionId = `mis_${Math.random().toString(36).substring(2, 9)}`;

    // Kronometre
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(() => {
      if (missionStartTime) {
        const sec = Math.floor((Date.now() - missionStartTime) / 1000);
        const m = Math.floor(sec / 60).toString().padStart(2, '0');
        const s = (sec % 60).toString().padStart(2, '0');
        elapsedTime = `${m}:${s}`;
      }
    }, 1000);

    // Sıfırlamalar
    resetGraph(target);
    pipelineSteps.forEach(s => s.status = 'idle');
    pipelineSteps[0].status = 'running';
    pipelineSteps = [...pipelineSteps];

    socialMatrix.forEach(p => p.status = 'pending');
    socialMatrix = [...socialMatrix];
    correlations = [];
    evidenceItems = [];

    aspasiaMessages = [
      ...aspasiaMessages,
      {
        role: 'aspasia',
        text: `"${target}" hedefi için operasyon başlatıldı. Rota inceleniyor ve 10 platformlu yoklama motoru devreye giriyor.`,
        time: new Date().toLocaleTimeString()
      }
    ];

    try {
      // 1. Backend initiate çağrısı
      const payload = {
        client_id: get(clientId) || 'default',
        url: target,
        rituals: '',
        playlist: '',
        envies: ''
      };

      const res = await apiFetch('/api/initiate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        pipelineSteps[0].status = 'completed';
        pipelineSteps[1].status = 'running';
        pipelineSteps = [...pipelineSteps];
      } else {
        const err = await res.json().catch(() => ({}));
        pipelineSteps[0].status = 'error';
        pipelineSteps = [...pipelineSteps];
        aspasiaMessages = [
          ...aspasiaMessages,
          {
            role: 'aspasia',
            text: `⚠️ Başlatma engellendi: ${err?.error?.message || 'Bilinmeyen hata'}. Kasa anahtarınızı veya izinleri kontrol edin.`,
            time: new Date().toLocaleTimeString()
          }
        ];
      }
    } catch (e: any) {
      pipelineSteps[0].status = 'error';
      pipelineSteps = [...pipelineSteps];
    }
  }

  async function abortMission() {
    isProcessing.set(false);
    if (timerInterval) clearInterval(timerInterval);
    try {
      await apiFetch('/api/override', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: get(clientId) || 'default', action: 'HALT' })
      });
    } catch {}

    aspasiaMessages = [
      ...aspasiaMessages,
      {
        role: 'aspasia',
        text: '🛑 Operatör müdahalesi: Görev ve çalışan tüm alt sensörler derhal durduruldu.',
        time: new Date().toLocaleTimeString()
      }
    ];
  }

  // Aspasia Sohbeti
  async function askAspasia() {
    if (!aspasiaPrompt.trim() || isAskingAspasia) return;

    const userText = aspasiaPrompt.trim();
    aspasiaPrompt = '';
    isAskingAspasia = true;

    aspasiaMessages = [
      ...aspasiaMessages,
      { role: 'user', text: userText, time: new Date().toLocaleTimeString() }
    ];

    try {
      const res = await apiFetch('/api/aspasia/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: get(clientId) || 'default',
          user_message: userText
        })
      });

      if (res.ok) {
        const data = await res.json();
        aspasiaMessages = [
          ...aspasiaMessages,
          {
            role: 'aspasia',
            text: data.reply || data.response || 'Bilgi sentezlendi.',
            time: new Date().toLocaleTimeString()
          }
        ];
      } else {
        aspasiaMessages = [
          ...aspasiaMessages,
          {
            role: 'aspasia',
            text: 'Aspasia motoru meşgul veya kilitli. Lütfen kasa durumunu kontrol edin.',
            time: new Date().toLocaleTimeString()
          }
        ];
      }
    } catch (err: any) {
      aspasiaMessages = [
        ...aspasiaMessages,
        {
          role: 'aspasia',
          text: `İletişim hatası: ${err.message}`,
          time: new Date().toLocaleTimeString()
        }
      ];
    } finally {
      isAskingAspasia = false;
    }
  }

  // Kasa Açma / Kapama Hızlı Anahtarı
  async function toggleVault() {
    const isLocked = get(vaultLocked);
    try {
      await apiFetch('/api/vault/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: get(clientId) || 'default',
          action: isLocked ? 'unlock' : 'lock'
        })
      });
      vaultLocked.set(!isLocked);
    } catch {}
  }

  // --- KANIT & LOG GÖZLEMCİSİ (Store Takibi) ---
  const unsubTask = taskStatus.subscribe((ts: any) => {
    if (!ts) return;

    // Platform sonuçları varsa matrisi ve grafiği güncelle
    if (ts.osint_footprint?.username_scan?.found_sites) {
      for (const site of ts.osint_footprint.username_scan.found_sites) {
        const pName = site.site || 'Harici';
        addPlatformNode(pName, site.url || '', 'claimed');

        const mat = socialMatrix.find(m => m.platform.toLowerCase().includes(pName.toLowerCase()));
        if (mat) {
          mat.status = 'claimed';
          mat.url = site.url || '';
        }
      }
      socialMatrix = [...socialMatrix];
      pipelineSteps[1].status = 'completed';
      pipelineSteps[2].status = 'running';
      pipelineSteps = [...pipelineSteps];
    }

    // Biyografi linkleri tespit edildiyse
    if (ts.target_profile?.detected_urls || ts.target_profile?.external_urls) {
      const urls = [...(ts.target_profile.detected_urls || []), ...(ts.target_profile.external_urls || [])];
      for (const u of urls) {
        addUrlNode('Instagram', u, u.replace(/^https?:\/\/(www\.)?/, ''));
        evidenceItems.push({
          id: `ev_${Math.random().toString(36).substring(2, 6)}`,
          type: 'Biyografi Bağlantısı',
          value: u,
          source: 'Instagram Ghost Scraper',
          verified: true,
          time: new Date().toLocaleTimeString()
        });
      }
      evidenceItems = [...evidenceItems];
      pipelineSteps[2].status = 'completed';
      pipelineSteps[3].status = 'running';
      pipelineSteps = [...pipelineSteps];
    }

    // Görev tamamlandıysa
    if (ts.status === 'completed' || ts.status === 'done') {
      isProcessing.set(false);
      pipelineSteps.forEach(s => s.status = 'completed');
      pipelineSteps = [...pipelineSteps];
      if (timerInterval) clearInterval(timerInterval);
    }
  });

  // --- CANVAS FARE ETKİLEŞİMİ (Pan/Zoom/Drag) ---
  function onCanvasMouseDown(e: MouseEvent) {
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = (e.clientX - rect.left - panX) / zoom;
    const mouseY = (e.clientY - rect.top - panY) / zoom;

    // Tıklanan düğüm var mı?
    let clickedNode: GraphNode | null = null;
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      const dx = mouseX - n.x;
      const dy = mouseY - n.y;
      if (dx * dx + dy * dy <= n.radius * n.radius) {
        clickedNode = n;
        break;
      }
    }

    if (clickedNode) {
      draggedNode = clickedNode;
      selectedNode = clickedNode;
    } else {
      isDraggingCanvas = true;
      dragStartX = e.clientX - panX;
      dragStartY = e.clientY - panY;
      selectedNode = null;
    }
  }

  function onCanvasMouseMove(e: MouseEvent) {
    if (!canvas) return;
    if (draggedNode) {
      const rect = canvas.getBoundingClientRect();
      draggedNode.x = (e.clientX - rect.left - panX) / zoom;
      draggedNode.y = (e.clientY - rect.top - panY) / zoom;
      draggedNode.vx = 0;
      draggedNode.vy = 0;
    } else if (isDraggingCanvas) {
      panX = e.clientX - dragStartX;
      panY = e.clientY - dragStartY;
    }
  }

  function onCanvasMouseUp() {
    draggedNode = null;
    isDraggingCanvas = false;
  }

  function onCanvasWheel(e: WheelEvent) {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    zoom = Math.min(Math.max(zoom * zoomFactor, 0.4), 2.5);
  }

  onMount(() => {
    if (canvas) {
      canvas.width = canvas.parentElement?.clientWidth || 800;
      canvas.height = canvas.parentElement?.clientHeight || 500;
      ctx = canvas.getContext('2d');
      resetGraph('HEDEF');
      runPhysicsStep();
    }
  });

  onDestroy(() => {
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    if (timerInterval) clearInterval(timerInterval);
    unsubTask();
  });
</script>

<div class="spiderfoot-cockpit">
  <!-- 1. ÜST KOMUTA & HEDEF ŞERİDİ -->
  <header class="mission-header">
    <div class="brand-zone">
      <div class="radar-pulse-icon"></div>
      <div>
        <h1 class="cockpit-title">PINEAL OPERASYON KOKPİTİ</h1>
        <span class="sub-badge">ADLİ OSINT & ÇAPRAZ İLİŞKİ HARİTALAMA MOTORU</span>
      </div>
    </div>

    <!-- Hedef Arama Barı -->
    <div class="target-control-bar">
      <div class="input-wrapper">
        <span class="input-icon">🎯</span>
        <input
          type="text"
          placeholder="@kullanici_adi veya https://instagram.com/..., x.com/..."
          bind:value={targetInput}
          on:keydown={(e) => e.key === 'Enter' && startMission()}
          disabled={$isProcessing}
        />
      </div>

      <div class="mode-toggles">
        <button
          class="mode-btn"
          class:active={selectedMode === 'full'}
          on:click={() => selectedMode = 'full'}
          title="Tüm platformlar, bio linkleri ve derin analiz"
        >TAM ADLİ TARAMA</button>
        <button
          class="mode-btn"
          class:active={selectedMode === 'probe'}
          on:click={() => selectedMode = 'probe'}
          title="Yalnız 10 platformlu hızlı varlık yoklaması"
        >HIZLI RADAR</button>
      </div>

      {#if !$isProcessing}
        <button
          class="launch-btn"
          disabled={!isTargetValid}
          on:click={startMission}
        >
          🚀 GÖREVİ BAŞLAT
        </button>
      {:else}
        <button class="abort-btn" on:click={abortMission}>
          🛑 GÖREVİ DURDUR ({elapsedTime})
        </button>
      {/if}
    </div>

    <!-- Güvenlik Anahtarları -->
    <div class="flight-controls">
      <button
        class="switch-btn"
        class:is-unlocked={!$vaultLocked}
        on:click={toggleVault}
        title="Kasa kilidi (Vault Interlock). Açıkken dış OSINT ve kazıma serbesttir."
      >
        <span class="status-dot"></span>
        KASA: {!$vaultLocked ? 'AÇIK' : 'KİLİTLİ'}
      </button>

      <div class="telemetry-pill">
        <span class="label">SÜRE:</span>
        <span class="value">{elapsedTime}</span>
      </div>
    </div>
  </header>

  <!-- 2. CANLI 5 ADIMLI PIPELINE STEPPER -->
  <section class="pipeline-stepper-bar">
    {#each pipelineSteps as step, i}
      <div class="step-card" class:active={step.status === 'running'} class:done={step.status === 'completed'} class:error={step.status === 'error'}>
        <div class="step-num">
          {#if step.status === 'completed'}
            ✓
          {:else if step.status === 'running'}
            <span class="spinner"></span>
          {:else}
            {i + 1}
          {/if}
        </div>
        <div class="step-info">
          <div class="step-title">{step.title}</div>
          <div class="step-desc">{step.description}</div>
        </div>
        {#if i < pipelineSteps.length - 1}
          <div class="step-connector"></div>
        {/if}
      </div>
    {/each}
  </section>

  <!-- 3. ANA ÇALIŞMA ALANI: GRAFİK + SEKMELER -->
  <div class="workspace-body">
    <!-- Sol/Orta Ana Bölüm -->
    <div class="center-stage">
      <!-- Görünüm Sekmeleri -->
      <div class="stage-nav">
        <button
          class="tab-btn"
          class:active={activeTab === 'graph'}
          on:click={() => activeTab = 'graph'}
        >🕸️ İLİŞKİ AĞI GRAFİĞİ ({nodes.length})</button>

        <button
          class="tab-btn"
          class:active={activeTab === 'matrix'}
          on:click={() => activeTab = 'matrix'}
        >📊 10 PLATFORM RADARI</button>

        <button
          class="tab-btn"
          class:active={activeTab === 'evidence'}
          on:click={() => activeTab = 'evidence'}
        >📁 TOPLANAN KANITLAR ({evidenceItems.length})</button>

        <button
          class="tab-btn"
          class:active={activeTab === 'agents'}
          on:click={() => activeTab = 'agents'}
        >🤖 12 AJAN YUVASI</button>
      </div>

      <!-- TAB 1: GRAFİK ÇİZİM ALANI -->
      {#if activeTab === 'graph'}
        <div class="canvas-container">
          <canvas
            bind:this={canvas}
            on:mousedown={onCanvasMouseDown}
            on:mousemove={onCanvasMouseMove}
            on:mouseup={onCanvasMouseUp}
            on:wheel={onCanvasWheel}
          ></canvas>

          <!-- Grafik Yardım İpuçları -->
          <div class="graph-legend">
            <span class="legend-item"><span class="dot root"></span> Hedef</span>
            <span class="legend-item"><span class="dot claimed"></span> Bulunan Profil</span>
            <span class="legend-item"><span class="dot absent"></span> Yok</span>
            <span class="legend-item"><span class="dot url"></span> Bio/Dış Link</span>
            <span class="zoom-text">Yakınlaştır: Fare Tekerleği · Kaydır: Sürükle</span>
          </div>
        </div>

      <!-- TAB 2: 10 PLATFORM MATRİSİ -->
      {:else if activeTab === 'matrix'}
        <div class="matrix-grid">
          {#each socialMatrix as item}
            <div class="matrix-card" class:claimed={item.status === 'claimed'} class:absent={item.status === 'absent'}>
              <div class="card-header">
                <span class="plat-name">{item.platform}</span>
                <span class="status-badge {item.status}">
                  {item.status === 'claimed' ? 'BULUNDU' : item.status === 'absent' ? 'YOK (404)' : item.status === 'unknown' ? 'KİLİTLİ/DUVAR' : 'BEKLİYOR'}
                </span>
              </div>
              <div class="card-body">
                {#if item.url}
                  <a href={item.url} target="_blank" rel="noopener noreferrer" class="plat-link">{item.url}</a>
                {:else}
                  <span class="plat-placeholder">Arama sonucu bekleniyor...</span>
                {/if}
              </div>
            </div>
          {/each}
        </div>

      <!-- TAB 3: KANIT DOSYASI -->
      {:else if activeTab === 'evidence'}
        <div class="evidence-list">
          {#if evidenceItems.length === 0}
            <div class="empty-state">Henüz doğrulanmış adli kanıt kaydı yok. Görevi başlatın.</div>
          {:else}
            {#each evidenceItems as ev}
              <div class="evidence-row">
                <span class="ev-time">{ev.time}</span>
                <span class="ev-type">{ev.type}</span>
                <span class="ev-val">{ev.value}</span>
                <span class="ev-source">{ev.source}</span>
                <span class="ev-check">✓ Mühürlü</span>
              </div>
            {/each}
          {/if}
        </div>

      <!-- TAB 4: 12 AJAN YUVASI -->
      {:else if activeTab === 'agents'}
        <div class="agents-grid">
          {#each Object.entries($agentStatuses) as [id, info]}
            <div class="agent-card">
              <div class="agent-head">
                <span class="agent-id">{id}</span>
                <span class="agent-stat {info.status.toLowerCase()}">{info.status}</span>
              </div>
              <div class="agent-meta">Canlılık: Aktif Beacon Yuvası</div>
            </div>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Sağ Panel: Düğüm Denetçisi + Canlı Aspasia Asistanı -->
    <aside class="side-inspector">
      <!-- Seçilen Düğüm Detayı -->
      {#if selectedNode}
        <div class="inspector-card">
          <div class="card-title">
            <span>DÜĞÜM DENETÇİSİ</span>
            <button class="close-btn" on:click={() => selectedNode = null}>×</button>
          </div>
          <div class="node-meta">
            <div class="meta-row"><span class="k">Etiket:</span> <span class="v">{selectedNode.label}</span></div>
            <div class="meta-row"><span class="k">Tip:</span> <span class="v">{selectedNode.type.toUpperCase()}</span></div>
            <div class="meta-row"><span class="k">Durum:</span> <span class="v">{selectedNode.status}</span></div>
            {#if selectedNode.data?.fullUrl}
              <div class="meta-row"><span class="k">URL:</span> <a href={selectedNode.data.fullUrl} target="_blank" class="v link">{selectedNode.data.fullUrl}</a></div>
            {/if}
          </div>
        </div>
      {/if}

      <!-- Aspasia Canlı İstihbarat Danışmanı -->
      <div class="aspasia-chat-card">
        <div class="chat-header">
          <span class="chat-dot"></span>
          <span>ASPASIA CANLI ANALİZ DANIŞMANI</span>
        </div>

        <div class="chat-messages">
          {#each aspasiaMessages as msg}
            <div class="message-bubble {msg.role}">
              <div class="msg-sender">{msg.role === 'aspasia' ? 'ASPASIA CHIEF' : 'OPERATÖR'} · {msg.time}</div>
              <div class="msg-text">{msg.text}</div>
            </div>
          {/each}
        </div>

        <div class="chat-input-bar">
          <input
            type="text"
            placeholder="Aspasia'ya soru sor..."
            bind:value={aspasiaPrompt}
            on:keydown={(e) => e.key === 'Enter' && askAspasia()}
            disabled={isAskingAspasia}
          />
          <button on:click={askAspasia} disabled={isAskingAspasia || !aspasiaPrompt.trim()}>
            {isAskingAspasia ? '...' : 'GÖNDER'}
          </button>
        </div>
      </div>
    </aside>
  </div>
</div>

<style>
  .spiderfoot-cockpit {
    width: 100vw;
    height: 100vh;
    background-color: #030712;
    color: #f3f4f6;
    font-family: 'JetBrains Mono', monospace;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* 1. ÜST KOMUTA */
  .mission-header {
    background: #0f172a;
    border-bottom: 1px solid rgba(56, 239, 125, 0.2);
    padding: 10px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }

  .brand-zone {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .radar-pulse-icon {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #38ef7d;
    box-shadow: 0 0 10px #38ef7d;
    animation: pulse 1.8s infinite;
  }

  @keyframes pulse {
    0% { transform: scale(0.9); opacity: 0.8; }
    50% { transform: scale(1.2); opacity: 1; }
    100% { transform: scale(0.9); opacity: 0.8; }
  }

  .cockpit-title {
    font-size: 14px;
    font-weight: 800;
    letter-spacing: 1.5px;
    color: #38ef7d;
    margin: 0;
  }

  .sub-badge {
    font-size: 9px;
    color: #94a3b8;
    letter-spacing: 0.8px;
  }

  .target-control-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    max-width: 820px;
  }

  .input-wrapper {
    display: flex;
    align-items: center;
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 0 10px;
    flex: 1;
  }

  .input-icon {
    font-size: 13px;
    margin-right: 6px;
  }

  .input-wrapper input {
    width: 100%;
    background: transparent;
    border: none;
    color: #f8fafc;
    font-family: inherit;
    font-size: 12px;
    padding: 8px 0;
    outline: none;
  }

  .mode-toggles {
    display: flex;
    border: 1px solid #334155;
    border-radius: 4px;
    overflow: hidden;
  }

  .mode-btn {
    background: #1e293b;
    border: none;
    color: #94a3b8;
    font-size: 10px;
    padding: 7px 10px;
    cursor: pointer;
    font-family: inherit;
  }

  .mode-btn.active {
    background: #334155;
    color: #38ef7d;
    font-weight: bold;
  }

  .launch-btn {
    background: #059669;
    color: #ffffff;
    border: none;
    font-family: inherit;
    font-size: 11px;
    font-weight: bold;
    padding: 8px 14px;
    border-radius: 4px;
    cursor: pointer;
    transition: 0.2s;
  }

  .launch-btn:hover:not(:disabled) {
    background: #10b981;
    box-shadow: 0 0 12px rgba(16, 185, 129, 0.4);
  }

  .launch-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .abort-btn {
    background: #dc2626;
    color: #ffffff;
    border: none;
    font-family: inherit;
    font-size: 11px;
    font-weight: bold;
    padding: 8px 14px;
    border-radius: 4px;
    cursor: pointer;
    animation: pulse-red 1.2s infinite;
  }

  @keyframes pulse-red {
    0% { box-shadow: 0 0 0 rgba(220, 38, 38, 0.4); }
    50% { box-shadow: 0 0 10px rgba(220, 38, 38, 0.8); }
    100% { box-shadow: 0 0 0 rgba(220, 38, 38, 0.4); }
  }

  .flight-controls {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .switch-btn {
    background: #1e293b;
    border: 1px solid #334155;
    color: #ef4444;
    font-family: inherit;
    font-size: 10px;
    padding: 6px 10px;
    border-radius: 4px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .switch-btn.is-unlocked {
    color: #10b981;
    border-color: rgba(16, 185, 129, 0.4);
  }

  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
  }

  .telemetry-pill {
    background: #1e293b;
    border: 1px solid #334155;
    padding: 5px 8px;
    border-radius: 4px;
    font-size: 10px;
    display: flex;
    gap: 6px;
  }

  .telemetry-pill .label { color: #64748b; }
  .telemetry-pill .value { color: #f59e0b; font-weight: bold; }

  /* 2. PIPELINE STEPPER */
  .pipeline-stepper-bar {
    background: #090d16;
    border-bottom: 1px solid #1e293b;
    display: flex;
    padding: 8px 16px;
    gap: 8px;
    overflow-x: auto;
  }

  .step-card {
    display: flex;
    align-items: center;
    gap: 8px;
    background: #0f172a;
    border: 1px solid #1e293b;
    padding: 6px 12px;
    border-radius: 4px;
    flex: 1;
    min-width: 170px;
    transition: 0.2s;
  }

  .step-card.active {
    border-color: #38ef7d;
    background: rgba(56, 239, 125, 0.08);
  }

  .step-card.done {
    border-color: #10b981;
  }

  .step-card.error {
    border-color: #ef4444;
    background: rgba(239, 68, 68, 0.08);
  }

  .step-num {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: #1e293b;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: bold;
    color: #94a3b8;
  }

  .step-card.active .step-num {
    background: #38ef7d;
    color: #000;
  }

  .step-card.done .step-num {
    background: #10b981;
    color: #fff;
  }

  .step-info {
    display: flex;
    flex-direction: column;
  }

  .step-title {
    font-size: 10.5px;
    font-weight: 700;
    color: #f1f5f9;
  }

  .step-desc {
    font-size: 8.5px;
    color: #64748b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 140px;
  }

  .spinner {
    width: 10px;
    height: 10px;
    border: 2px solid #000;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* 3. ANA ÇALIŞMA ALANI */
  .workspace-body {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  .center-stage {
    flex: 1;
    display: flex;
    flex-direction: column;
    border-right: 1px solid #1e293b;
    overflow: hidden;
  }

  .stage-nav {
    display: flex;
    background: #0b1120;
    border-bottom: 1px solid #1e293b;
    padding: 0 12px;
    gap: 4px;
  }

  .tab-btn {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: #94a3b8;
    font-family: inherit;
    font-size: 10.5px;
    font-weight: 600;
    padding: 8px 12px;
    cursor: pointer;
    transition: 0.15s;
  }

  .tab-btn:hover {
    color: #f8fafc;
  }

  .tab-btn.active {
    color: #38ef7d;
    border-bottom-color: #38ef7d;
    background: rgba(56, 239, 125, 0.05);
  }

  /* CANVAS */
  .canvas-container {
    flex: 1;
    position: relative;
    background: #020617;
    overflow: hidden;
  }

  canvas {
    width: 100%;
    height: 100%;
    cursor: grab;
  }

  canvas:active {
    cursor: grabbing;
  }

  .graph-legend {
    position: absolute;
    bottom: 12px;
    left: 12px;
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid #334155;
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 9.5px;
    display: flex;
    gap: 12px;
    align-items: center;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .dot.root { background: #dc2626; }
  .dot.claimed { background: #10b981; }
  .dot.absent { background: #64748b; }
  .dot.url { background: #818cf8; }
  .zoom-text { color: #64748b; margin-left: 8px; border-left: 1px solid #334155; padding-left: 8px; }

  /* MATRİS GRID */
  .matrix-grid {
    flex: 1;
    padding: 16px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 12px;
    overflow-y: auto;
    background: #020617;
  }

  .matrix-card {
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 4px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .matrix-card.claimed {
    border-color: rgba(16, 185, 129, 0.5);
  }

  .matrix-card.absent {
    border-color: rgba(100, 116, 139, 0.3);
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .plat-name {
    font-weight: 700;
    font-size: 11px;
    color: #f8fafc;
  }

  .status-badge {
    font-size: 8.5px;
    padding: 2px 6px;
    border-radius: 3px;
    font-weight: bold;
  }

  .status-badge.claimed { background: rgba(16, 185, 129, 0.2); color: #10b981; }
  .status-badge.absent { background: rgba(100, 116, 139, 0.2); color: #94a3b8; }
  .status-badge.unknown { background: rgba(234, 179, 8, 0.2); color: #eab308; }
  .status-badge.pending { background: rgba(30, 41, 59, 0.5); color: #64748b; }

  .plat-link {
    font-size: 10px;
    color: #38ef7d;
    word-break: break-all;
    text-decoration: none;
  }

  .plat-link:hover {
    text-decoration: underline;
  }

  .plat-placeholder {
    font-size: 9.5px;
    color: #64748b;
  }

  /* KANIT LİSTESİ */
  .evidence-list {
    flex: 1;
    padding: 16px;
    overflow-y: auto;
    background: #020617;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .evidence-row {
    background: #0f172a;
    border: 1px solid #1e293b;
    padding: 8px 12px;
    border-radius: 4px;
    display: grid;
    grid-template-columns: 80px 140px 1fr 160px 80px;
    gap: 8px;
    align-items: center;
    font-size: 10px;
  }

  .ev-time { color: #64748b; }
  .ev-type { color: #f59e0b; font-weight: bold; }
  .ev-val { color: #38ef7d; word-break: break-all; }
  .ev-source { color: #94a3b8; }
  .ev-check { color: #10b981; font-weight: bold; }

  /* 12 AJAN GRID */
  .agents-grid {
    flex: 1;
    padding: 16px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 10px;
    overflow-y: auto;
    background: #020617;
  }

  .agent-card {
    background: #0f172a;
    border: 1px solid #1e293b;
    padding: 10px;
    border-radius: 4px;
  }

  .agent-head {
    display: flex;
    justify-content: space-between;
    font-size: 10px;
    font-weight: bold;
    margin-bottom: 4px;
  }

  .agent-id { color: #f8fafc; }
  .agent-stat.ready { color: #10b981; }
  .agent-stat.active { color: #38ef7d; }
  .agent-stat.idle { color: #94a3b8; }
  .agent-meta { font-size: 8.5px; color: #64748b; }

  /* SAĞ PANEL */
  .side-inspector {
    width: 340px;
    background: #0b1120;
    border-left: 1px solid #1e293b;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px;
  }

  .inspector-card {
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 10px;
  }

  .card-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 10px;
    font-weight: bold;
    color: #f59e0b;
    border-bottom: 1px solid #1e293b;
    padding-bottom: 6px;
    margin-bottom: 8px;
  }

  .close-btn {
    background: transparent;
    border: none;
    color: #64748b;
    font-size: 14px;
    cursor: pointer;
  }

  .meta-row {
    font-size: 9.5px;
    margin-bottom: 4px;
    display: flex;
    gap: 6px;
  }

  .meta-row .k { color: #64748b; min-width: 50px; }
  .meta-row .v { color: #f8fafc; word-break: break-all; }
  .meta-row .v.link { color: #38ef7d; }

  /* ASPASIA CHAT */
  .aspasia-chat-card {
    flex: 1;
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 4px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .chat-header {
    background: #1e293b;
    padding: 8px 10px;
    font-size: 9.5px;
    font-weight: bold;
    color: #38ef7d;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .chat-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #38ef7d;
  }

  .chat-messages {
    flex: 1;
    padding: 10px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .message-bubble {
    padding: 8px;
    border-radius: 4px;
    font-size: 10px;
    line-height: 1.4;
  }

  .message-bubble.aspasia {
    background: rgba(56, 239, 125, 0.08);
    border: 1px solid rgba(56, 239, 125, 0.2);
    color: #f8fafc;
  }

  .message-bubble.user {
    background: #1e293b;
    border: 1px solid #334155;
    color: #cbd5e1;
    align-self: flex-end;
  }

  .msg-sender {
    font-size: 8px;
    color: #64748b;
    margin-bottom: 3px;
  }

  .chat-input-bar {
    padding: 8px;
    border-top: 1px solid #1e293b;
    display: flex;
    gap: 6px;
    background: #090d16;
  }

  .chat-input-bar input {
    flex: 1;
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 3px;
    color: #fff;
    font-family: inherit;
    font-size: 10px;
    padding: 6px 8px;
    outline: none;
  }

  .chat-input-bar button {
    background: #059669;
    color: #fff;
    border: none;
    font-family: inherit;
    font-size: 9.5px;
    font-weight: bold;
    padding: 0 10px;
    border-radius: 3px;
    cursor: pointer;
  }

  .empty-state {
    text-align: center;
    color: #64748b;
    font-size: 11px;
    padding: 40px 0;
  }
</style>
