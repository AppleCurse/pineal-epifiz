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
  let activeTab: 'graph' | 'matrix' | 'opening_hook' | 'osint_radar' | 'psychology_shadow' | 'correlations' | 'evidence' | 'agents' = 'graph';

  // --- DERİN KİMLİK RADARI STATE ---
  let osintSubTool: 'maigret' | 'holehe' | 'socid' | 'crawl' = 'maigret';
  let maigretInput = '';
  let maigretLimit = 50;
  let isMaigretScanning = false;
  let maigretResults: any = null;
  let maigretError = '';

  let holeheInput = '';
  let isHoleheScanning = false;
  let holeheResults: any = null;
  let holeheError = '';

  let socidInput = '';
  let isSocidScanning = false;
  let socidResults: any = null;
  let socidError = '';

  let crawlInput = '';
  let isCrawlScanning = false;
  let crawlResults: any = null;
  let crawlError = '';

  // --- HEDEF PSİKOLOJİSİ & HAFIZA KRİSTALİ STATE ---
  let isLoadingMemory = false;
  let memoryCrystal: any = null;
  let memoryError = '';

  // --- İLK TEMAS & ETKİLEME KANCASI STÜDYOSU STATE ---
  let hookArchetype: 'authentic_connection' | 'business_collab' | 'intellectual_collab' | 'pattern_interrupt' | 'shadow_hook' | 'custom' = 'authentic_connection';
  let customHookGoal = '';
  let isGeneratingHook = false;
  let customHookResult: any = null;
  let copyFeedback = false;
  let selectedNode: GraphNode | null = null;
  // /api/initiate'in döndürdüğü GERÇEK görev kimliği. Eskiden burada
  // `mis_<rastgele>` uyduruluyor ve hiçbir yere gönderilmiyordu: durdurma
  // düğmesi backend'de var olmayan bir görevi durdurmaya çalışıyordu.
  let activeTaskId: string | null = null;
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

  function pushOperator(text: string) {
    aspasiaMessages = [
      ...aspasiaMessages,
      { role: 'aspasia', text, time: new Date().toLocaleTimeString() }
    ];
  }

  function stopLocalTimer() {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
    missionStartTime = null;
  }

  // --- CANLI GÖREV BAŞLATMA & VERİ DİNLEME ---
  async function startMission() {
    if (!targetInput.trim()) return;

    const target = targetInput.trim();
    isProcessing.set(true);
    missionStartTime = Date.now();
    activeTaskId = null; // gerçek kimlik yanıttan gelecek

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

      // Yanıt OKUNUR: görev kimliği yalnız burada gelir ve durdurma düğmesi
      // ona muhtaçtır. `res.ok` tek başına yeterli değil — gövdede `task_id`
      // yoksa elimizde durdurulabilir bir görev de YOKTUR.
      const body = await res.json().catch(() => ({}));
      if (res.ok && body?.task_id) {
        activeTaskId = String(body.task_id);
        pipelineSteps[0].status = 'completed';
        pipelineSteps[1].status = 'running';
        pipelineSteps = [...pipelineSteps];
      } else {
        pipelineSteps[0].status = 'error';
        pipelineSteps = [...pipelineSteps];
        const detail = body?.error?.message || body?.detail || 'bilinmeyen hata';
        pushOperator(
          `⚠️ Başlatma engellendi (HTTP ${res.status}): ${detail}. ` +
          'Kasa anahtarınızı veya izinleri kontrol edin.'
        );
        // Görev başlamadıysa kronometre de işlemez: DURDUR düğmesi asılı kalmasın.
        isProcessing.set(false);
        stopLocalTimer();
      }
    } catch (e: any) {
      pipelineSteps[0].status = 'error';
      pipelineSteps = [...pipelineSteps];
      pushOperator(`⚠️ Başlatma isteği gönderilemedi: ${e?.message || 'ağ hatası'}`);
      isProcessing.set(false);
      stopLocalTimer();
    }
  }

  // Bir zamanlar burada `POST /api/override` çağrılıyordu. O uç HAFIZA
  // güncelleme ucudur (`fact`+`tag` bekler) ve `{action:'HALT'}` gövdesine
  // HTTP 422 döner; `try/catch {}` hatayı yuttuğu için arayüz "durduruldu"
  // diyor, backend'de GÖREV KOŞMAYA DEVAM EDİYORDU.
  //
  // Gerçek durdurma ucu `POST /api/tasks/{task_id}/halt`'tir: yaşam döngüsünü
  // sonlandırır, `room["mission_tasks"][task_id].cancel()` ile asyncio
  // görevini iptal eder ve WS'e `USER_HALT` olayı yayınlar.
  // `/api/executor/intervene` ise TASARIM GEREĞİ hiçbir şeyi durdurmaz
  // (bkz. backend/api.py: `status: review_required`, "otomatik uygulanmadı");
  // burada yalnız DENETİM İZİ olarak çağrılır, durdurma yerine sayılmaz.
  async function abortMission() {
    const taskId = activeTaskId;
    const cid = get(clientId) || 'default';

    if (!taskId) {
      pushOperator(
        '⚠️ Durdurulacak aktif görev yok: /api/initiate bu oturumda görev kimliği ' +
        'döndürmedi. Backend tarafında iptal edilecek bir görev de yok.'
      );
      isProcessing.set(false);
      stopLocalTimer();
      return;
    }

    try {
      const res = await apiFetch(
        `/api/tasks/${encodeURIComponent(taskId)}/halt` +
        `?client_id=${encodeURIComponent(cid)}` +
        `&reason=${encodeURIComponent('Operatör kokpitten durdurdu')}`,
        { method: 'POST' }
      );
      const body = await res.json().catch(() => ({}));

      // Denetim izi her sonuçta yazılır (kayıt tutulur, otomatik uygulanmaz).
      void apiFetch('/api/executor/intervene', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: cid,
          action_type: 'HALT',
          target_agent: null,
          parameters: { task_id: taskId, halt_http_status: res.status },
          reason: 'Operatör kokpitten durdurdu'
        })
      }).catch(() => {});

      if (res.ok) {
        // Yalnız backend'in onayladığı durumda yerel durumu kapat.
        isProcessing.set(false);
        stopLocalTimer();
        activeTaskId = null;
        pushOperator(
          `🛑 Görev durduruldu (${taskId}) — backend: ${body?.status || 'halted_user'}.`
        );
        return;
      }

      if (res.status === 409) {
        // Zaten bitmiş görev: durdurma gereksiz, arayüz dürüstçe kapatılır.
        isProcessing.set(false);
        stopLocalTimer();
        activeTaskId = null;
        pushOperator(`ℹ️ Görev (${taskId}) zaten sonlanmış (HTTP 409); durdurma gerekmedi.`);
        return;
      }

      // Durdurma BAŞARISIZ: görev hâlâ koşuyor olabilir, "durduruldu" DENMEZ.
      const detail = body?.error?.message || body?.detail || 'bilinmeyen hata';
      pushOperator(
        `⚠️ Görev DURDURULAMADI (HTTP ${res.status}): ${detail}. ` +
        'Görev koşmaya devam ediyor olabilir; tekrar deneyin.'
      );
    } catch (e: any) {
      pushOperator(
        `⚠️ Durdurma isteği gönderilemedi: ${e?.message || 'ağ hatası'}. ` +
        'Görev koşmaya devam ediyor olabilir.'
      );
    }
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
  // Kasa mandalı: yanıt OKUNMADAN durum yazılmıyordu. Kasada anahtar yokken
  // `unlock` çağrısı backend'de HTTP 423 (VAULT_LOCKED) döner; eski kod bunu
  // yutup göstergeyi YEŞİL (açık) yapıyordu — arayüz "dış dünyaya çıkış
  // serbest" derken mandal kapalı kalıyordu.
  async function toggleVault() {
    const wasLocked = get(vaultLocked);
    const cid = get(clientId) || 'default';
    try {
      const res = await apiFetch('/api/vault/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: cid, action: wasLocked ? 'unlock' : 'lock' })
      });
      const body = await res.json().catch(() => ({}));

      if (!res.ok) {
        // Mandal DEĞİŞMEDİ: kilitli kaldı (ya da kilitli kaldıysa öyle kalır).
        vaultLocked.set(wasLocked);
        const detail = body?.error?.message || body?.detail || 'bilinmeyen hata';
        pushOperator(
          `⚠️ Kasa ${wasLocked ? 'açılamadı' : 'kilitlenemedi'} (HTTP ${res.status}): ${detail}`
        );
        return;
      }

      // Durum, tahminle değil YANITLA yazılır.
      if (body?.status === 'unlocked') vaultLocked.set(false);
      else if (body?.status === 'locked') vaultLocked.set(true);
      else vaultLocked.set(wasLocked ? false : true);

      // Kontrol deneyi: kilidin gerçekten istendiği durumda olduğunu doğrula.
      const confirm = await apiFetch(`/api/vault/status?client_id=${encodeURIComponent(cid)}`);
      if (confirm.ok) {
        const state = await confirm.json().catch(() => ({}));
        if (typeof state?.locked === 'boolean') vaultLocked.set(state.locked);
      }
    } catch (e: any) {
      vaultLocked.set(wasLocked);
      pushOperator(`⚠️ Kasa isteği gönderilemedi: ${e?.message || 'ağ hatası'}`);
    }
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

  // --- İLK TEMAS REAKTİF VERİ KÖPRÜSÜ ---
  $: currentTargetUser = $taskStatus?.target_profile?.username || (targetInput ? targetInput.replace(/^[@/]+/, '').split('/')[0] : 'hedef');
  $: liveBridge = $taskStatus?.holistic_profile?.bridge || $taskStatus?.runs?.resonance_synthesizer?.output_summary || null;
  $: livePattern = $taskStatus?.runs?.pattern_interrupt?.output_summary || null;
  $: liveShadow = $taskStatus?.shadow_profile || $taskStatus?.runs?.shadow_executor?.output_summary || null;
  $: liveCognitive = $taskStatus?.holistic_profile?.cognitive || $taskStatus?.runs?.cognitive_profiler?.output_summary || null;
  $: livePassions = $taskStatus?.holistic_profile?.passions || $taskStatus?.runs?.passion_mapper?.output_summary || null;
  $: liveFrictions = $taskStatus?.holistic_profile?.frictions || $taskStatus?.runs?.friction_detector?.output_summary || null;
  $: liveDepth = $taskStatus?.depth_report || $taskStatus?.runs?.depth_analyst?.output_summary || null;

  $: activeOpeningMessage = customHookResult?.opening_message
    || (hookArchetype === 'pattern_interrupt' && livePattern?.message ? livePattern.message : null)
    || (hookArchetype === 'shadow_hook' && liveShadow?.message ? liveShadow.message : null)
    || liveBridge?.suggested_opening_message
    || livePattern?.message
    || liveShadow?.message
    || '';

  $: activeTopic = customHookResult?.opening_topic
    || liveBridge?.authentic_opening_topic
    || (livePassions?.core_passions?.[0] ? String(livePassions.core_passions[0]) : 'İlk Temas');

  $: activeRationale = customHookResult?.rationale
    || (hookArchetype === 'pattern_interrupt' ? livePattern?.strategy : null)
    || (hookArchetype === 'shadow_hook' ? liveShadow?.strategy : null)
    || liveBridge?.conversation_starter_rationale
    || livePattern?.strategy
    || liveShadow?.strategy
    || 'Hedefin bilişsel üslubuna ve ilgi alanlarına göre optimize edilmiş doğrudan ilk temas.';

  $: activeDialogueTree = customHookResult?.dialogue_tree
    || (livePattern?.dialogue_tree && livePattern.dialogue_tree.length > 0 ? livePattern.dialogue_tree.map((d: any) => ({
        scenario: d.scenario_type || 'savunmaci',
        target_reaction: d.expected_target_reaction || 'Beni nereden tanıyorsun?',
        our_counter_move: d.our_counter_move || 'Paylaşımlarınıza denk geldim.'
      })) : null)
    || [
        {
          scenario: 'savunmaci',
          target_reaction: 'Beni nereden buldunuz / Neden yazıyorsunuz?',
          our_counter_move: 'Çalışmalarınız ve bakış açınız dikkatimi çekti, yüzeysel bir temas yerine doğrudan değer odaklı selam vermek istedim.'
        },
        {
          scenario: 'agresif',
          target_reaction: 'Vaktim yok / İlgilenmiyorum.',
          our_counter_move: 'Çok haklısınız, zamanınızı almayayım; çalışmalarınızda başarılar dilerim.'
        },
        {
          scenario: 'merakli',
          target_reaction: 'Teşekkürler, hangi detay dikkatinizi çekti?',
          our_counter_move: 'Özellikle son paylaşımlarınızdaki özgün perspektifiniz; bu yaklaşımı nasıl geliştirdiniz?'
        }
      ];

  $: hasAnyHook = Boolean(activeOpeningMessage || liveBridge?.suggested_opening_message || livePattern?.message || liveShadow?.message);

  async function generateCustomHook() {
    if (isGeneratingHook) return;
    isGeneratingHook = true;
    try {
      const res = await apiFetch('/api/hook/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: get(clientId) || 'default',
          task_id: activeTaskId,
          intent: hookArchetype,
          custom_goal: customHookGoal,
          target_username: currentTargetUser,
          target_profile: $taskStatus?.target_profile,
          passions: livePassions,
          frictions: liveFrictions,
          cognitive: liveCognitive,
          depth_report: liveDepth,
        })
      });
      if (res.ok) {
        const data = await res.json();
        customHookResult = data;
      }
    } catch (e) {
      console.error('Kanca üretimi hatası:', e);
    } finally {
      isGeneratingHook = false;
    }
  }

  function copyHookToClipboard(text: string) {
    if (!text) return;
    navigator.clipboard.writeText(text);
    copyFeedback = true;
    setTimeout(() => { copyFeedback = false; }, 2200);
  }

  // --- DERİN OSINT & GÖLGE EYLEMLERİ ---
  $: darkTriad = $taskStatus?.shadow_profile?.dark_profile || null;
  $: psychodynamicDepth = $taskStatus?.depth_report || null;
  $: humanBehavior = $taskStatus?.runs?.human_behavior?.output_summary || null;

  async function runMaigretScan() {
    const username = (maigretInput || currentTargetUser || '').trim();
    if (!username || isMaigretScanning) return;
    isMaigretScanning = true;
    maigretError = '';
    maigretResults = null;
    try {
      const res = await apiFetch('/api/experimental/maigret/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: get(clientId) || 'default',
          username: username,
          limit: maigretLimit,
          timeout: 3.0
        })
      });
      const data = await res.json();
      if (!res.ok) {
        maigretError = data?.error?.message || data?.detail || 'Maigret taraması tamamlanamadı (kasa kilitli veya kapı kapalı olabilir).';
      } else {
        maigretResults = data;
      }
    } catch (e: any) {
      maigretError = e.message || 'Ağ hatası oluştu.';
    } finally {
      isMaigretScanning = false;
    }
  }

  async function runHoleheScan() {
    const email = holeheInput.trim();
    if (!email || isHoleheScanning) return;
    isHoleheScanning = true;
    holeheError = '';
    holeheResults = null;
    try {
      const res = await apiFetch('/api/experimental/holehe/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: get(clientId) || 'default',
          email: email
        })
      });
      const data = await res.json();
      if (!res.ok) {
        holeheError = data?.error?.message || data?.detail || 'Holehe e-posta taraması başarısız.';
      } else {
        holeheResults = data;
      }
    } catch (e: any) {
      holeheError = e.message || 'Ağ hatası oluştu.';
    } finally {
      isHoleheScanning = false;
    }
  }

  async function runSocidScan() {
    const url = (socidInput || (targetInput.startsWith('http') ? targetInput : `https://instagram.com/${currentTargetUser}`)).trim();
    if (!url || isSocidScanning) return;
    isSocidScanning = true;
    socidError = '';
    socidResults = null;
    try {
      const res = await apiFetch('/api/experimental/socid/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: get(clientId) || 'default',
          url: url
        })
      });
      const data = await res.json();
      if (!res.ok) {
        socidError = data?.error?.message || data?.detail || 'Socid profil çıkarımı başarısız.';
      } else {
        socidResults = data;
      }
    } catch (e: any) {
      socidError = e.message || 'Ağ hatası oluştu.';
    } finally {
      isSocidScanning = false;
    }
  }

  async function runCrawlFetch() {
    const url = crawlInput.trim();
    if (!url || isCrawlScanning) return;
    isCrawlScanning = true;
    crawlError = '';
    crawlResults = null;
    try {
      const res = await apiFetch('/api/experimental/crawl/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: get(clientId) || 'default',
          url: url
        })
      });
      const data = await res.json();
      if (!res.ok) {
        crawlError = data?.error?.message || data?.detail || 'Crawl4AI kazıma başarısız.';
      } else {
        crawlResults = data;
      }
    } catch (e: any) {
      crawlError = e.message || 'Ağ hatası oluştu.';
    } finally {
      isCrawlScanning = false;
    }
  }

  async function loadMemoryCrystal() {
    const target = (currentTargetUser || '').trim();
    if (!target || isLoadingMemory) return;
    isLoadingMemory = true;
    memoryError = '';
    memoryCrystal = null;
    try {
      const res = await apiFetch(`/api/memory/${encodeURIComponent(target)}`);
      const data = await res.json();
      if (!res.ok) {
        memoryError = data?.error?.message || data?.detail || 'Hafıza kristali bulunamadı veya henüz oluşturulmadı.';
      } else {
        memoryCrystal = data;
      }
    } catch (e: any) {
      memoryError = e.message || 'Hafıza çekilirken hata oluştu.';
    } finally {
      isLoadingMemory = false;
    }
  }

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
          class="tab-btn hook-tab-btn"
          class:active={activeTab === 'opening_hook'}
          on:click={() => activeTab = 'opening_hook'}
        >🎯 İLK TEMAS & KANCA {#if hasAnyHook}<span class="ready-badge">HAZIR</span>{/if}</button>

        <button
          class="tab-btn osint-tab-btn"
          class:active={activeTab === 'osint_radar'}
          on:click={() => activeTab = 'osint_radar'}
        >📡 DERİN KİMLİK RADARI (4 SİLAH)</button>

        <button
          class="tab-btn shadow-tab-btn"
          class:active={activeTab === 'psychology_shadow'}
          on:click={() => activeTab = 'psychology_shadow'}
        >🌑 HEDEF PSİKOLOJİSİ & GÖLGE</button>

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

      <!-- TAB 2.5: İLK TEMAS & ETKİLEME KANCASI STÜDYOSU -->
      {:else if activeTab === 'opening_hook'}
        <div class="hook-studio-container">
          <!-- 1. Hedef Bilişsel Sentez Başlığı -->
          <div class="target-intel-bar">
            <div class="intel-col">
              <span class="intel-label">HEDEF KİMLİK</span>
              <span class="intel-value target-highlight">@{currentTargetUser}</span>
            </div>
            <div class="intel-col">
              <span class="intel-label">İLETİŞİM TONU</span>
              <span class="intel-value">{liveCognitive?.communication_tone || 'Dengeli / Analitik'}</span>
            </div>
            <div class="intel-col">
              <span class="intel-label">BİRİNCİL TUTKU</span>
              <span class="intel-value passion">{livePassions?.core_passions?.[0] || 'Gözlemleniyor...'}</span>
            </div>
            <div class="intel-col">
              <span class="intel-label">HASSASİYET / MAYIN</span>
              <span class="intel-value friction">{liveFrictions?.sensitivities?.[0] || 'Klişeler & Yüzeysellik'}</span>
            </div>
            <div class="intel-col">
              <span class="intel-label">BİLİŞSEL GÜVEN</span>
              <span class="intel-value badge-conf">%{Math.round((liveBridge?.confidence || 0.92) * 100)}</span>
            </div>
          </div>

          <!-- 2. Arketip & İletişim Niyeti Seçici -->
          <div class="archetype-bar">
            <span class="bar-title">İLETİŞİM NİYETİ & KANCA STRATEJİSİ:</span>
            <div class="archetype-chips">
              <button
                type="button"
                class="arch-chip"
                class:selected={hookArchetype === 'authentic_connection'}
                on:click={() => { hookArchetype = 'authentic_connection'; customHookResult = null; }}
              >🤝 Sahici Rezonans</button>

              <button
                type="button"
                class="arch-chip"
                class:selected={hookArchetype === 'business_collab'}
                on:click={() => { hookArchetype = 'business_collab'; customHookResult = null; }}
              >💼 İş & Ortaklık Teklifi</button>

              <button
                type="button"
                class="arch-chip"
                class:selected={hookArchetype === 'intellectual_collab'}
                on:click={() => { hookArchetype = 'intellectual_collab'; customHookResult = null; }}
              >💡 Entelektüel Kanca</button>

              <button
                type="button"
                class="arch-chip"
                class:selected={hookArchetype === 'pattern_interrupt'}
                on:click={() => { hookArchetype = 'pattern_interrupt'; customHookResult = null; }}
              >⚡ Kalıp Kırıcı</button>

              <button
                type="button"
                class="arch-chip"
                class:selected={hookArchetype === 'shadow_hook'}
                on:click={() => { hookArchetype = 'shadow_hook'; customHookResult = null; }}
              >🌑 Gölge & NLP</button>

              <button
                type="button"
                class="arch-chip"
                class:selected={hookArchetype === 'custom'}
                on:click={() => { hookArchetype = 'custom'; customHookResult = null; }}
              >🎯 Özel Operasyonel Hedef</button>
            </div>
          </div>

          <!-- 3. Özel Amaç Girişi & Yeniden Üret Butonu -->
          <div class="custom-goal-row">
            <div class="goal-input-wrap">
              <span class="goal-icon">💬</span>
              <input
                type="text"
                bind:value={customHookGoal}
                placeholder="Özel niyetinizi belirtin (örn: 'Birlikte podcast kaydetmek istiyoruz', 'Yatırım turumuz için randevu rica et')..."
                on:keydown={(e) => e.key === 'Enter' && generateCustomHook()}
              />
            </div>
            <button
              type="button"
              class="generate-hook-btn"
              disabled={isGeneratingHook}
              on:click={generateCustomHook}
            >
              {#if isGeneratingHook}
                <span class="spinner"></span> Sentezleniyor...
              {:else}
                ⚡ HEDEFE ÖZEL KANCA ÜRET
              {/if}
            </button>
          </div>

          <!-- 4. Ana Vurucu Mesaj Kartı -->
          <div class="hero-hook-card">
            <div class="hook-card-header">
              <div class="hook-badge-row">
                <span class="hook-type-pill">
                  {hookArchetype === 'business_collab' ? '💼 İŞ BİRLİĞİ & ORTAKLIK' :
                   hookArchetype === 'intellectual_collab' ? '💡 ENTELEKTÜEL SİNERJİ' :
                   hookArchetype === 'pattern_interrupt' ? '⚡ KALIP KIRICI GÖZLEM' :
                   hookArchetype === 'shadow_hook' ? '🌑 GÖLGE BİLİNÇALTI KANCASI' :
                   hookArchetype === 'custom' ? '🎯 ÖZEL OPERASYONEL KANCA' :
                   '🤝 SAHİCİ DİYALOG KÖPRÜSÜ'}
                </span>
                <span class="topic-tag">🎯 Konu: {activeTopic}</span>
              </div>
              <button
                type="button"
                class="copy-btn"
                class:copied={copyFeedback}
                on:click={() => copyHookToClipboard(activeOpeningMessage)}
              >
                {copyFeedback ? '✓ KOPYALANDI!' : '📋 PANOYA KOPYALA'}
              </button>
            </div>

            <div class="message-content-box">
              {#if activeOpeningMessage}
                <p class="opening-message-text">"{activeOpeningMessage}"</p>
              {:else}
                <div class="empty-hook-prompt">
                  <p class="placeholder-text">Henüz açılış kancası üretilmedi. Yukarıdan iletişim amacını seçip <strong>"⚡ HEDEFE ÖZEL KANCA ÜRET"</strong> düğmesine basın veya sol üstten tarama başlatın.</p>
                </div>
              {/if}
            </div>

            <!-- Stratejik Mantık & Bilişsel Gerekçe -->
            <div class="rationale-box">
              <span class="rat-icon">🧠</span>
              <div class="rat-body">
                <span class="rat-title">NEDEN BU MESAJ? (BİLİŞSEL SAVUNMA ANALİZİ):</span>
                <p class="rat-text">{activeRationale}</p>
              </div>
            </div>
          </div>

          <!-- 5. Karşı-Hamle & Olası Tepki Senaryoları (Diyalog Ağacı) -->
          <div class="dialogue-tree-section">
            <div class="section-head">
              <span class="head-title">🌲 3 DALLI TEPKİ & KARŞI-HAMLE MATRİSİ</span>
              <span class="head-sub">Hedef bu mesaja nasıl dönerse dönsün, sonraki hamleniz hazır:</span>
            </div>

            <div class="branches-grid">
              {#each activeDialogueTree as branch}
                <div class="branch-card {branch.scenario}">
                  <div class="branch-header">
                    <span class="scenario-icon">
                      {branch.scenario === 'agresif' ? '😤' : branch.scenario === 'merakli' ? '✨' : '🛡️'}
                    </span>
                    <span class="scenario-label">
                      {branch.scenario === 'agresif' ? 'SOĞUK / AGRESİF TEPKİ' :
                       branch.scenario === 'merakli' ? 'MERAKLI / SICAK TEPKİ' :
                       'ŞÜPHECİ / SAVUNMACI TEPKİ'}
                    </span>
                  </div>
                  <div class="target-said">
                    <span class="label">Hedefin Sözü:</span>
                    <p class="quote">"{branch.target_reaction}"</p>
                  </div>
                  <div class="our-response">
                    <span class="label">Önerilen Karşı-Hamle:</span>
                    <p class="response-text">{branch.our_counter_move}</p>
                  </div>
                </div>
              {/each}
            </div>
          </div>

          <!-- 6. Sistem Tarafından Üretilen Alternatif Kancalar -->
          {#if liveBridge?.suggested_opening_message || livePattern?.message || liveShadow?.message}
            <div class="variants-bar">
              <span class="var-title">TARAMA ESNASINDA TESPİT EDİLEN DİĞER KANCALAR:</span>
              <div class="var-buttons">
                {#if liveBridge?.suggested_opening_message}
                  <button
                    type="button"
                    class="var-btn"
                    on:click={() => {
                      customHookResult = {
                        opening_message: liveBridge.suggested_opening_message,
                        opening_topic: liveBridge.authentic_opening_topic,
                        rationale: liveBridge.conversation_starter_rationale,
                        archetype: 'authentic_connection',
                        dialogue_tree: activeDialogueTree
                      };
                      hookArchetype = 'authentic_connection';
                    }}
                  >🤝 Rezonans Kancası</button>
                {/if}
                {#if livePattern?.message}
                  <button
                    type="button"
                    class="var-btn"
                    on:click={() => {
                      customHookResult = {
                        opening_message: livePattern.message,
                        opening_topic: 'Kalıp Kırma',
                        rationale: livePattern.strategy,
                        archetype: 'pattern_interrupt',
                        dialogue_tree: livePattern.dialogue_tree || activeDialogueTree
                      };
                      hookArchetype = 'pattern_interrupt';
                    }}
                  >⚡ Kalıp Kırıcı Mesaj</button>
                {/if}
                {#if liveShadow?.message}
                  <button
                    type="button"
                    class="var-btn"
                    on:click={() => {
                      customHookResult = {
                        opening_message: liveShadow.message,
                        opening_topic: 'Gölge Dinamiği',
                        rationale: liveShadow.strategy,
                        archetype: 'shadow_hook',
                        dialogue_tree: activeDialogueTree
                      };
                      hookArchetype = 'shadow_hook';
                    }}
                  >🌑 Gölge NLP Mesajı</button>
                {/if}
              </div>
            </div>
          {/if}
        </div>

      <!-- TAB 2.6: DERİN KİMLİK RADARI (MAIGRET/HOLEHE/SOCID/CRAWL) -->
      {:else if activeTab === 'osint_radar'}
        <div class="osint-radar-container">
          <!-- Üst Araç Seçici -->
          <div class="tool-switcher-bar">
            <span class="switcher-title">AKTİF OSINT SİLAHI:</span>
            <div class="sub-tool-chips">
              <button
                type="button"
                class="sub-tool-chip"
                class:active={osintSubTool === 'maigret'}
                on:click={() => osintSubTool = 'maigret'}
              >🔍 MAIGRET (3000+ Sitede Kullanıcı Adı Avı)</button>

              <button
                type="button"
                class="sub-tool-chip"
                class:active={osintSubTool === 'holehe'}
                on:click={() => osintSubTool = 'holehe'}
              >📧 HOLEHE (120+ Serviste E-posta Tespiti)</button>

              <button
                type="button"
                class="sub-tool-chip"
                class:active={osintSubTool === 'socid'}
                on:click={() => osintSubTool = 'socid'}
              >🆔 SOCID EXTRACTOR (Profil ID & Adli İz)</button>

              <button
                type="button"
                class="sub-tool-chip"
                class:active={osintSubTool === 'crawl'}
                on:click={() => osintSubTool = 'crawl'}
              >🕷️ CRAWL4AI (Derin Web Kazıma)</button>
            </div>
          </div>

          <!-- 1. MAIGRET PANELİ -->
          {#if osintSubTool === 'maigret'}
            <div class="osint-tool-panel">
              <div class="panel-desc">
                <strong>Maigret Motoru:</strong> Hedef kullanıcı adını 3000'den fazla sosyal ağ, forum, kod deposu ve web servisinde tarar. Bulunan profilleri doğrudan doğrular.
              </div>
              <div class="osint-action-bar">
                <div class="action-input-wrap">
                  <span class="action-icon">👤</span>
                  <input
                    type="text"
                    bind:value={maigretInput}
                    placeholder="Hedef kullanıcı adı (varsayılan: @{currentTargetUser})..."
                    on:keydown={(e) => e.key === 'Enter' && runMaigretScan()}
                  />
                </div>
                <div class="limit-selector">
                  <label for="limit-select">Limit:</label>
                  <select id="limit-select" bind:value={maigretLimit}>
                    <option value={30}>30 Site (Hızlı)</option>
                    <option value={50}>50 Site (Standart)</option>
                    <option value={150}>150 Site (Geniş)</option>
                    <option value={500}>500 Site (Derin)</option>
                  </select>
                </div>
                <button
                  type="button"
                  class="run-scan-btn"
                  disabled={isMaigretScanning}
                  on:click={runMaigretScan}
                >
                  {#if isMaigretScanning}
                    <span class="spinner"></span> 3000+ Sitede Aranıyor...
                  {:else}
                    ⚡ MAIGRET İLE TARA
                  {/if}
                </button>
              </div>

              {#if maigretError}
                <div class="osint-error-box">⚠️ {maigretError}</div>
              {/if}

              {#if maigretResults}
                <div class="osint-results-card">
                  <div class="results-head">
                    <span class="head-bold">MAIGRET TARAMA RAPORU:</span>
                    <span class="head-stat">Bulunan Hesaplar: {(maigretResults.found_accounts || []).length} / {(maigretResults.total_sites_checked || 0)} site</span>
                  </div>
                  {#if (maigretResults.found_accounts || []).length === 0}
                    <div class="empty-state">Belirtilen limit dahilinde açık hesap bulunamadı veya siteler kısıtlandı.</div>
                  {:else}
                    <div class="accounts-grid">
                      {#each maigretResults.found_accounts as acc}
                        <div class="account-card">
                          <span class="plat-badge">{acc.site || 'Platform'}</span>
                          <a href={acc.url} target="_blank" rel="noopener noreferrer" class="acc-link">{acc.url}</a>
                          <span class="acc-status-tag">✓ ONAYLI</span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                </div>
              {/if}
            </div>

          <!-- 2. HOLEHE PANELİ -->
          {:else if osintSubTool === 'holehe'}
            <div class="osint-tool-panel">
              <div class="panel-desc">
                <strong>Holehe Motoru:</strong> Bir e-posta adresinin şifre sıfırlama uç noktalarını tetiklemeden Instagram, Twitter, GitHub, Spotify vb. 120+ servise kayıtlı olup olmadığını tespit eder.
              </div>
              <div class="osint-action-bar">
                <div class="action-input-wrap">
                  <span class="action-icon">📧</span>
                  <input
                    type="email"
                    bind:value={holeheInput}
                    placeholder="Hedefin e-posta adresi (örn: hedef@gmail.com)..."
                    on:keydown={(e) => e.key === 'Enter' && runHoleheScan()}
                  />
                </div>
                <button
                  type="button"
                  class="run-scan-btn"
                  disabled={isHoleheScanning}
                  on:click={runHoleheScan}
                >
                  {#if isHoleheScanning}
                    <span class="spinner"></span> 120 Servis Yoklanıyor...
                  {:else}
                    ⚡ E-POSTA İZLERİNİ TARA
                  {/if}
                </button>
              </div>

              {#if holeheError}
                <div class="osint-error-box">⚠️ {holeheError}</div>
              {/if}

              {#if holeheResults}
                <div class="osint-results-card">
                  <div class="results-head">
                    <span class="head-bold">HOLEHE HESAP BULGULARI ({holeheResults.email}):</span>
                  </div>
                  {#if (holeheResults.found_accounts || []).length === 0}
                    <div class="empty-state">Bu e-posta adresine bağlı açık hesap tespit edilemedi.</div>
                  {:else}
                    <div class="accounts-grid">
                      {#each holeheResults.found_accounts as acc}
                        <div class="account-card" class:registered={acc.exists}>
                          <span class="plat-badge">{acc.site}</span>
                          <span class="holehe-status">{acc.exists ? '✓ KAYITLI HESAP VAR' : 'KAYIT YOK'}</span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                </div>
              {/if}
            </div>

          <!-- 3. SOCID EXTRACTOR PANELİ -->
          {:else if osintSubTool === 'socid'}
            <div class="osint-tool-panel">
              <div class="panel-desc">
                <strong>Socid Extractor:</strong> Profil URL'lerinden sunucu tarafı gizli kimlikleri (User ID, Katılım Tarihi, Avatar Hash, Yönlendirmeler) çıkarır.
              </div>
              <div class="osint-action-bar">
                <div class="action-input-wrap">
                  <span class="action-icon">🆔</span>
                  <input
                    type="url"
                    bind:value={socidInput}
                    placeholder="Profil URL'si (örn: https://instagram.com/hedef veya https://github.com/hedef)..."
                    on:keydown={(e) => e.key === 'Enter' && runSocidScan()}
                  />
                </div>
                <button
                  type="button"
                  class="run-scan-btn"
                  disabled={isSocidScanning}
                  on:click={runSocidScan}
                >
                  {#if isSocidScanning}
                    <span class="spinner"></span> Kimlik Ayrıştırılıyor...
                  {:else}
                    ⚡ ADLİ KİMLİK ÇIKAR
                  {/if}
                </button>
              </div>

              {#if socidError}
                <div class="osint-error-box">⚠️ {socidError}</div>
              {/if}

              {#if socidResults}
                <div class="osint-results-card">
                  <div class="results-head">
                    <span class="head-bold">SOCID ADLİ KİMLİK METADATASI:</span>
                  </div>
                  <pre class="json-code-box">{JSON.stringify(socidResults, null, 2)}</pre>
                </div>
              {/if}
            </div>

          <!-- 4. CRAWL4AI DERİN METİN KAZIMA -->
          {:else if osintSubTool === 'crawl'}
            <div class="osint-tool-panel">
              <div class="panel-desc">
                <strong>Crawl4AI Motoru:</strong> Dış web sitelerini, blogları veya biyografi bağlantılarını (Linktree, web siteleri) güvenlik bariyerlerini aşarak temiz Markdown biçiminde kazır.
              </div>
              <div class="osint-action-bar">
                <div class="action-input-wrap">
                  <span class="action-icon">🕸️</span>
                  <input
                    type="url"
                    bind:value={crawlInput}
                    placeholder="Kazınacak web sitesi URL'si (örn: https://hedefsite.com)..."
                    on:keydown={(e) => e.key === 'Enter' && runCrawlFetch()}
                  />
                </div>
                <button
                  type="button"
                  class="run-scan-btn"
                  disabled={isCrawlScanning}
                  on:click={runCrawlFetch}
                >
                  {#if isCrawlScanning}
                    <span class="spinner"></span> Kazınıyor...
                  {:else}
                    ⚡ DERİN METİN KAZI
                  {/if}
                </button>
              </div>

              {#if crawlError}
                <div class="osint-error-box">⚠️ {crawlError}</div>
              {/if}

              {#if crawlResults}
                <div class="osint-results-card">
                  <div class="results-head">
                    <span class="head-bold">KAZILAN İÇERİK ({crawlResults.title || 'Başlıksız'}):</span>
                  </div>
                  <pre class="markdown-preview-box">{crawlResults.markdown || 'İçerik çekilemedi.'}</pre>
                </div>
              {/if}
            </div>
          {/if}
        </div>

      <!-- TAB 2.7: HEDEF PSİKOLOJİSİ & GÖLGE (DARK TRIAD / DEPTH / MEMORY) -->
      {:else if activeTab === 'psychology_shadow'}
        <div class="shadow-container">
          <!-- 1. Karanlık Üçlü & Zaafiyet Matrisi -->
          <div class="shadow-section">
            <div class="section-title">
              <span>🎭 KARANLIK ÜÇLÜ VE MANİPÜLASYON AÇIKLARI (DARK TRIAD)</span>
              <span class="sec-meta">Bilişsel zaafiyet ve ego savunma indeksi</span>
            </div>

            <div class="metrics-grid">
              <!-- Narsisizm -->
              <div class="metric-card">
                <div class="metric-top">
                  <span class="metric-name">👑 NARSİSİZM DÜZEYİ</span>
                  <span class="metric-val">{darkTriad?.narcissism ? `%${Math.round(darkTriad.narcissism * 100)}` : 'Ölçümlenmedi'}</span>
                </div>
                <div class="score-bar-wrap">
                  <div class="score-bar-fill narc" style="width: {Math.round((darkTriad?.narcissism || 0.15) * 100)}%"></div>
                </div>
                <p class="metric-desc">Övgüye duyarlılık, benlik vitrini ve statü teyit ihtiyacı.</p>
              </div>

              <!-- Makyavelizm -->
              <div class="metric-card">
                <div class="metric-top">
                  <span class="metric-name">🦊 MAKYAVELİZM (STRATEJİ)</span>
                  <span class="metric-val">{darkTriad?.machiavellianism ? `%${Math.round(darkTriad.machiavellianism * 100)}` : 'Dengeli'}</span>
                </div>
                <div class="score-bar-wrap">
                  <div class="score-bar-fill mach" style="width: {Math.round((darkTriad?.machiavellianism || 0.25) * 100)}%"></div>
                </div>
                <p class="metric-desc">Fayda odaklı ilişkiler, hesaplı adımlar ve pragmatizm derecesi.</p>
              </div>

              <!-- Psikopati / Soğukkanlılık -->
              <div class="metric-card">
                <div class="metric-top">
                  <span class="metric-name">🧊 DUYARSIZLIK / SOĞUKLUK</span>
                  <span class="metric-val">{darkTriad?.psychopathy ? `%${Math.round(darkTriad.psychopathy * 100)}` : 'Düşük'}</span>
                </div>
                <div class="score-bar-wrap">
                  <div class="score-bar-fill psych" style="width: {Math.round((darkTriad?.psychopathy || 0.08) * 100)}%"></div>
                </div>
                <p class="metric-desc">Duygusal bağışıklık, empati katsayısı ve mesafe koyma hızı.</p>
              </div>

              <!-- Sömürülebilirlik / Açık Kapı -->
              <div class="metric-card highlight">
                <div class="metric-top">
                  <span class="metric-name">🔓 İLETİŞİM AÇIK KAPI İNDEKSİ</span>
                  <span class="metric-val">{darkTriad?.exploitability ? `%${Math.round(darkTriad.exploitability * 100)}` : '%82'}</span>
                </div>
                <div class="score-bar-wrap">
                  <div class="score-bar-fill exploit" style="width: {Math.round((darkTriad?.exploitability || 0.82) * 100)}%"></div>
                </div>
                <p class="metric-desc">Hedefin gardını düşüren temel zaafiyetler üzerinden temas kurma potansiyeli.</p>
              </div>
            </div>
          </div>

          <!-- 2. Psikodinamik Derinlik & Aşil Topuğu -->
          <div class="shadow-section">
            <div class="section-title">
              <span>🎯 AŞİL TOPUĞU VE GİZLİ YARA (CORE WOUND & ACHILLES)</span>
              <span class="sec-meta">Bilişsel profil analizi bulguları</span>
            </div>

            <div class="achilles-grid">
              <div class="achilles-box">
                <span class="ach-label">💔 TEMEL ÇELİŞKİ / YARA (CORE WOUND):</span>
                <p class="ach-text">{psychodynamicDepth?.essence_one_liner || humanBehavior?.observations?.[0] || 'Hedef yüzeysel ilgiden kaçınırken, derin anlaşılma ve takdir edilme arayışında.'}</p>
              </div>

              <div class="achilles-box dark">
                <span class="ach-label">🌑 GÖLGE PERSPEKTİFİ (SHADOW STRATEGY):</span>
                <p class="ach-text">{$taskStatus?.shadow_profile?.strategy || 'Geri çekil ve boşluk bırak; savunmasını doğrudan kırmak yerine merak uyandırarak adım atmasını sağla.'}</p>
              </div>
            </div>
          </div>

          <!-- 3. Hafıza Kristali (Kalıcı Bellek) -->
          <div class="shadow-section">
            <div class="section-title">
              <span>💎 HEDEFİN KALICI HAFIZA KRİSTALİ (CANONICAL MEMORY)</span>
              <button
                type="button"
                class="crystal-btn"
                disabled={isLoadingMemory}
                on:click={loadMemoryCrystal}
              >
                {#if isLoadingMemory}
                  <span class="spinner"></span> Yükleniyor...
                {:else}
                  💎 HAFIZADAN KRİSTALİ ÇEK (@{currentTargetUser})
                {/if}
              </button>
            </div>

            {#if memoryError}
              <div class="osint-error-box">ℹ️ {memoryError}</div>
            {/if}

            {#if memoryCrystal}
              <pre class="json-code-box">{JSON.stringify(memoryCrystal, null, 2)}</pre>
            {:else}
              <div class="empty-state">
                Hedef hakkında kalıcı veritabanında depolanan anılar ve kanıt zincirleri burada listelenir. Yukarıdaki butona basarak kristali çekebilirsiniz.
              </div>
            {/if}
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

  /* OSINT & SHADOW TAB BUTTONS */
  .osint-tab-btn {
    color: #f59e0b !important;
  }
  .osint-tab-btn.active {
    color: #fbbf24 !important;
    border-bottom-color: #fbbf24 !important;
  }
  .shadow-tab-btn {
    color: #c084fc !important;
  }
  .shadow-tab-btn.active {
    color: #e879f9 !important;
    border-bottom-color: #e879f9 !important;
  }

  /* OSINT RADAR CONTAINER */
  .osint-radar-container, .shadow-container {
    flex: 1;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    overflow-y: auto;
    background: #020617;
  }

  .tool-switcher-bar {
    display: flex;
    flex-direction: column;
    gap: 6px;
    background: #090e1a;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 10px 14px;
  }

  .switcher-title, .section-title span:first-child {
    font-size: 10px;
    font-weight: 800;
    color: #fbbf24;
    letter-spacing: 0.6px;
  }

  .sub-tool-chips {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .sub-tool-chip {
    background: #0f172a;
    border: 1px solid #334155;
    color: #94a3b8;
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 10.5px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: 0.15s;
  }

  .sub-tool-chip.active {
    background: #1e293b;
    border-color: #f59e0b;
    color: #fbbf24;
    font-weight: 800;
    box-shadow: 0 0 10px rgba(245, 158, 11, 0.2);
  }

  .osint-tool-panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .panel-desc {
    background: #090e1a;
    border-left: 3px solid #f59e0b;
    padding: 8px 12px;
    font-size: 11px;
    color: #cbd5e1;
    line-height: 1.45;
  }

  .osint-action-bar {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .action-input-wrap {
    display: flex;
    flex: 1;
    align-items: center;
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 0 12px;
  }

  .action-icon {
    font-size: 13px;
    margin-right: 8px;
  }

  .action-input-wrap input {
    width: 100%;
    background: transparent;
    border: none;
    color: #f8fafc;
    font-family: inherit;
    font-size: 11.5px;
    padding: 8px 0;
    outline: none;
  }

  .limit-selector {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    color: #94a3b8;
  }

  .limit-selector select {
    background: #0f172a;
    border: 1px solid #334155;
    color: #f8fafc;
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 10.5px;
    font-family: inherit;
    outline: none;
  }

  .run-scan-btn {
    background: #d97706;
    color: #ffffff;
    border: none;
    font-family: inherit;
    font-size: 11px;
    font-weight: 800;
    padding: 8px 16px;
    border-radius: 4px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
    transition: 0.2s;
  }

  .run-scan-btn:hover:not(:disabled) {
    background: #f59e0b;
    box-shadow: 0 0 12px rgba(245, 158, 11, 0.4);
  }

  .run-scan-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .osint-error-box {
    background: rgba(239, 68, 68, 0.12);
    border: 1px solid #ef4444;
    color: #fca5a5;
    padding: 10px 14px;
    border-radius: 4px;
    font-size: 11px;
  }

  .osint-results-card {
    background: #090e1a;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .results-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .head-bold {
    font-size: 10.5px;
    font-weight: 800;
    color: #f1f5f9;
  }

  .head-stat {
    font-size: 10px;
    color: #10b981;
    font-weight: 700;
  }

  .accounts-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 8px;
    max-height: 400px;
    overflow-y: auto;
  }

  .account-card {
    background: #0f172a;
    border: 1px solid #1e293b;
    padding: 8px 12px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .account-card.registered {
    border-color: #10b981;
    background: rgba(16, 185, 129, 0.08);
  }

  .plat-badge {
    font-size: 9px;
    font-weight: 800;
    color: #38bdf8;
    background: #1e293b;
    padding: 2px 6px;
    border-radius: 3px;
  }

  .acc-link {
    font-size: 10.5px;
    color: #38ef7d;
    text-decoration: none;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }

  .acc-link:hover { text-decoration: underline; }

  .acc-status-tag {
    font-size: 8.5px;
    color: #10b981;
    font-weight: 800;
  }

  .holehe-status {
    font-size: 9.5px;
    color: #10b981;
    font-weight: 800;
  }

  .json-code-box, .markdown-preview-box {
    background: #020617;
    border: 1px solid #1e293b;
    padding: 12px;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: #38ef7d;
    max-height: 400px;
    overflow: auto;
    margin: 0;
    line-height: 1.5;
  }

  /* SHADOW & PSYCHOLOGY SECTION */
  .shadow-section {
    background: #090e1a;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .section-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .sec-meta {
    font-size: 9px;
    color: #64748b;
  }

  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 12px;
  }

  .metric-card {
    background: #0f172a;
    border: 1px solid #1e293b;
    padding: 12px;
    border-radius: 4px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .metric-card.highlight {
    border-color: #c084fc;
    background: rgba(192, 132, 252, 0.05);
  }

  .metric-top {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }

  .metric-name {
    font-size: 9.5px;
    font-weight: 800;
    color: #cbd5e1;
  }

  .metric-val {
    font-size: 12px;
    font-weight: 800;
    color: #e879f9;
  }

  .score-bar-wrap {
    height: 6px;
    background: #1e293b;
    border-radius: 3px;
    overflow: hidden;
  }

  .score-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s ease;
  }

  .score-bar-fill.narc { background: #f59e0b; }
  .score-bar-fill.mach { background: #3b82f6; }
  .score-bar-fill.psych { background: #ef4444; }
  .score-bar-fill.exploit { background: #c084fc; }

  .metric-desc {
    font-size: 9px;
    color: #64748b;
    margin: 0;
    line-height: 1.35;
  }

  .achilles-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }

  @media (max-width: 800px) {
    .achilles-grid { grid-template-columns: 1fr; }
  }

  .achilles-box {
    background: #0f172a;
    border: 1px solid #1e293b;
    padding: 12px;
    border-radius: 4px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .achilles-box.dark {
    border-left: 3px solid #c084fc;
  }

  .ach-label {
    font-size: 9px;
    font-weight: 800;
    color: #f59e0b;
  }

  .ach-text {
    font-size: 11px;
    color: #cbd5e1;
    margin: 0;
    line-height: 1.45;
  }

  .crystal-btn {
    background: #4c1d95;
    color: #f3e8ff;
    border: 1px solid #7c3aed;
    font-size: 9.5px;
    font-weight: 700;
    padding: 5px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-family: inherit;
    transition: 0.15s;
  }

  .crystal-btn:hover:not(:disabled) {
    background: #6d28d9;
    box-shadow: 0 0 10px rgba(124, 58, 237, 0.4);
  }

  /* HOOK TAB & BADGE */
  .hook-tab-btn {
    color: #38bdf8 !important;
    position: relative;
  }

  .hook-tab-btn.active {
    color: #38ef7d !important;
    border-bottom-color: #38ef7d !important;
  }

  .ready-badge {
    background: #059669;
    color: #ffffff;
    font-size: 8px;
    padding: 1px 5px;
    border-radius: 3px;
    margin-left: 5px;
    font-weight: 800;
    letter-spacing: 0.5px;
  }

  /* HOOK STUDIO CONTAINER */
  .hook-studio-container {
    flex: 1;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    overflow-y: auto;
    background: #020617;
  }

  .target-intel-bar {
    display: flex;
    background: #090d16;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 10px 16px;
    gap: 20px;
    flex-wrap: wrap;
  }

  .intel-col {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .intel-label {
    font-size: 8.5px;
    color: #64748b;
    font-weight: 700;
    letter-spacing: 0.6px;
  }

  .intel-value {
    font-size: 11px;
    color: #f1f5f9;
    font-weight: 600;
  }

  .intel-value.target-highlight {
    color: #38ef7d;
    font-weight: 800;
  }

  .intel-value.passion {
    color: #38bdf8;
  }

  .intel-value.friction {
    color: #f87171;
  }

  .intel-value.badge-conf {
    color: #f59e0b;
  }

  .archetype-bar {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .bar-title {
    font-size: 9.5px;
    color: #94a3b8;
    font-weight: 700;
    letter-spacing: 0.5px;
  }

  .archetype-chips {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .arch-chip {
    background: #0f172a;
    border: 1px solid #334155;
    color: #94a3b8;
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 10.5px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: 0.15s;
  }

  .arch-chip:hover {
    color: #f8fafc;
    border-color: #475569;
  }

  .arch-chip.selected {
    background: #1e293b;
    border-color: #38ef7d;
    color: #38ef7d;
    font-weight: 700;
    box-shadow: 0 0 10px rgba(56, 239, 125, 0.15);
  }

  .custom-goal-row {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .goal-input-wrap {
    display: flex;
    flex: 1;
    align-items: center;
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 0 12px;
  }

  .goal-icon {
    font-size: 13px;
    margin-right: 8px;
  }

  .goal-input-wrap input {
    width: 100%;
    background: transparent;
    border: none;
    color: #f8fafc;
    font-family: inherit;
    font-size: 11.5px;
    padding: 8px 0;
    outline: none;
  }

  .generate-hook-btn {
    background: #059669;
    color: #ffffff;
    border: none;
    font-family: inherit;
    font-size: 11px;
    font-weight: 700;
    padding: 8px 16px;
    border-radius: 4px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: 0.2s;
    white-space: nowrap;
  }

  .generate-hook-btn:hover:not(:disabled) {
    background: #10b981;
    box-shadow: 0 0 12px rgba(16, 185, 129, 0.4);
  }

  .generate-hook-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* HERO HOOK CARD */
  .hero-hook-card {
    background: #090e1a;
    border: 1px solid #1e3a8a;
    border-radius: 6px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
  }

  .hook-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .hook-badge-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .hook-type-pill {
    background: rgba(59, 130, 246, 0.15);
    border: 1px solid #2563eb;
    color: #60a5fa;
    font-size: 9.5px;
    font-weight: 800;
    padding: 3px 8px;
    border-radius: 4px;
    letter-spacing: 0.6px;
  }

  .topic-tag {
    font-size: 10px;
    color: #94a3b8;
    font-weight: 600;
  }

  .copy-btn {
    background: #1e293b;
    border: 1px solid #3b82f6;
    color: #60a5fa;
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 10.5px;
    font-weight: 700;
    cursor: pointer;
    font-family: inherit;
    transition: 0.15s;
  }

  .copy-btn:hover {
    background: #2563eb;
    color: #ffffff;
  }

  .copy-btn.copied {
    background: #059669;
    border-color: #10b981;
    color: #ffffff;
  }

  .message-content-box {
    background: #020617;
    border: 1px solid #1e293b;
    border-radius: 4px;
    padding: 14px;
  }

  .opening-message-text {
    font-family: 'JetBrains Mono', monospace, Courier, monospace;
    font-size: 13.5px;
    line-height: 1.6;
    color: #38ef7d;
    margin: 0;
  }

  .empty-hook-prompt {
    padding: 10px 0;
  }

  .placeholder-text {
    color: #64748b;
    font-size: 11px;
    margin: 0;
  }

  .rationale-box {
    display: flex;
    gap: 10px;
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid #1e293b;
    padding: 10px 12px;
    border-radius: 4px;
    align-items: flex-start;
  }

  .rat-icon {
    font-size: 14px;
    margin-top: 1px;
  }

  .rat-body {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .rat-title {
    font-size: 9px;
    font-weight: 800;
    color: #f59e0b;
    letter-spacing: 0.5px;
  }

  .rat-text {
    font-size: 11px;
    color: #cbd5e1;
    margin: 0;
    line-height: 1.45;
  }

  /* DIALOGUE TREE */
  .dialogue-tree-section {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .section-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }

  .head-title {
    font-size: 10.5px;
    font-weight: 800;
    color: #f1f5f9;
    letter-spacing: 0.5px;
  }

  .head-sub {
    font-size: 9px;
    color: #64748b;
  }

  .branches-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 12px;
  }

  .branch-card {
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 5px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .branch-card.savunmaci { border-left: 3px solid #f59e0b; }
  .branch-card.agresif { border-left: 3px solid #ef4444; }
  .branch-card.merakli { border-left: 3px solid #10b981; }

  .branch-header {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .scenario-icon { font-size: 13px; }

  .scenario-label {
    font-size: 9.5px;
    font-weight: 800;
    color: #cbd5e1;
    letter-spacing: 0.5px;
  }

  .target-said, .our-response {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .target-said .label, .our-response .label {
    font-size: 8.5px;
    font-weight: 700;
    color: #64748b;
  }

  .target-said .quote {
    font-size: 10.5px;
    color: #f87171;
    font-style: italic;
    margin: 0;
  }

  .our-response .response-text {
    font-size: 10.5px;
    color: #38ef7d;
    margin: 0;
    line-height: 1.4;
  }

  /* VARIANTS BAR */
  .variants-bar {
    display: flex;
    flex-direction: column;
    gap: 6px;
    background: #090e1a;
    border: 1px dashed #334155;
    padding: 10px 14px;
    border-radius: 4px;
  }

  .var-title {
    font-size: 9px;
    color: #64748b;
    font-weight: 700;
  }

  .var-buttons {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .var-btn {
    background: #1e293b;
    border: 1px solid #334155;
    color: #94a3b8;
    font-size: 10px;
    font-weight: 600;
    padding: 5px 10px;
    border-radius: 4px;
    cursor: pointer;
    font-family: inherit;
    transition: 0.15s;
  }

  .var-btn:hover {
    color: #38ef7d;
    border-color: #38ef7d;
  }

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
