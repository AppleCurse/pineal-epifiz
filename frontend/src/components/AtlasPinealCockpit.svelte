<script lang="ts">
  import { onMount } from 'svelte';
  import {
    apiFetch, clientId, isAuthFailure, logs, taskStatus, isProcessing,
    apiToken, agentStatuses, vaultLocked, activeViewMode, inspectedAgentId,
    speechState, lastSpeech, voiceEnabled
  } from '../store';
  import { playClick, playHalt, playRunning } from '../lib/consoleAudio';
  import HolographicResonanceMesh from './HolographicResonanceMesh.svelte';
  import AgentRack from './AgentRack.svelte';

  function openWarRoom(agentId?: string) {
    playClick(500, 30);
    if (agentId) {
      inspectedAgentId.set(agentId);
    }
    activeViewMode.set('warroom');
  }

  // Tek dokunulmaz ana şasi görseli (Kayıpsız 16:9 Master Referans) — PINEAL-HERETIC v5.0
  import cockpitSkin from '../assets/cockpit-v10-reference.png';
  import livingPinealDisk from '../assets/living_pineal_disk.png';

  // --- STATE ---
  let targetUrl = '';
  let inputMessage = '';
  let isSending = false;
  let activePillarModal: string | null = null;
  let activeTab = 'ASPASIA';
  let showAgentRack = true;
  let meshSize = 180;

  // Vault interlock - mandal durumu (gözün üzerinde rozet YOK, sadece LED)
  $: isVaultLocked = $vaultLocked;

  // --- YAŞAYAN PİNEAL GÖZ (ORGANİK VE YAVAŞ HAREKET) — ORİJİNAL %12.2 PİRİNÇ YUVA KORUNDU ---
  let eyeX = 0;
  let eyeY = 0;
  let targetEyeX = 0;
  let targetEyeY = 0;
  let eyeScale = 1.0;
  let animFrameId: number;

  function handleMouseMove(e: MouseEvent) {
    const width = typeof window !== 'undefined' ? window.innerWidth : 1920;
    const height = typeof window !== 'undefined' ? window.innerHeight : 1080;
    const normX = (e.clientX - width / 2) / (width / 2);
    const normY = (e.clientY - height / 2) / (height / 2);
    targetEyeX = Math.max(-4.5, Math.min(4.5, normX * 4.5));
    targetEyeY = Math.max(-3.5, Math.min(3.5, normY * 3.5));
  }

  onMount(() => {
    let startTime = performance.now();

    function animate(time: number) {
      const elapsed = (time - startTime) * 0.001;
      const organicDriftX = Math.sin(elapsed * 0.45) * 2.2 + Math.sin(elapsed * 0.18) * 1.0;
      const organicDriftY = Math.cos(elapsed * 0.35) * 1.8 + Math.cos(elapsed * 0.12) * 0.8;
      const processingFlutter = $isProcessing ? Math.sin(elapsed * 3.5) * 0.6 : 0;
      const desiredX = targetEyeX + organicDriftX + processingFlutter;
      const desiredY = targetEyeY + organicDriftY;
      eyeX += (desiredX - eyeX) * 0.04;
      eyeY += (desiredY - eyeY) * 0.04;
      eyeScale = 1.016 + Math.sin(elapsed * 0.5) * 0.012;
      animFrameId = requestAnimationFrame(animate);
    }

    animFrameId = requestAnimationFrame(animate);

    function updateMeshSize() {
      const vw = window.innerWidth;
      if (vw < 1200) meshSize = 120;
      else if (vw < 1600) meshSize = 150;
      else meshSize = 180;
    }
    updateMeshSize();
    window.addEventListener('resize', updateMeshSize);

    return () => {
      if (animFrameId) cancelAnimationFrame(animFrameId);
      window.removeEventListener('resize', updateMeshSize);
    };
  });

  // 7 Sütun Adli Rapor Listesi
  const pillarsList = [
    { id: 'follower',  label: 'FOLLOWER',  tr: 'TAKİPÇİ' },
    { id: 'timing',    label: 'TIMING',    tr: 'ZAMAN' },
    { id: 'depth',     label: 'DEPTH',     tr: 'DERİNLİK' },
    { id: 'visual',    label: 'VISUAL',    tr: 'GÖRSEL' },
    { id: 'shadow',    label: 'SHADOW',    tr: 'GÖLGE' },
    { id: 'osint',     label: 'OSINT',     tr: 'OSINT' },
    { id: 'resonance', label: 'RESONANCE', tr: 'REZONANS' },
  ];

  // Adli Telemetri Durumları
  $: followerAudit = $taskStatus?.follower_audit || null;
  $: timingForensics = $taskStatus?.timing_forensics || null;
  $: depthReport = $taskStatus?.depth_report || null;
  $: visualEvidence = $taskStatus?.visual_evidence || null;
  $: shadowProfile = $taskStatus?.shadow_profile || null;
  $: osintFootprint = $taskStatus?.osint_footprint || null;
  $: resonanceCalc = $taskStatus?.runs?.resonance_calc?.output_summary || null;

  // --- [FAZ B · B4] GERÇEK İLİŞKİ GRAFI ---
  // Örgü artık rastgele düğüm üretmiyor: görev bitince kanıt zincirinden
  // üretilen gerçek graf çekilir. Kanıt yoksa graf boş kalır (uydurma yok).
  let evidenceGraph: {
    available: boolean;
    nodes: Array<{ id: string; label: string; kind: string; weight: number; evidence_count: number }>;
    edges: Array<{ source: string; target: string; weight: number }>;
    node_count?: number;
    edge_count?: number;
    machine_note?: string;
  } | null = null;
  let lastGraphTaskId: string | null = null;

  const TERMINAL_STATUSES = new Set([
    'completed', 'partially_completed', 'failed',
    'halted_evidence', 'halted_frequency', 'halted_insufficient_evidence', 'halted_critical',
  ]);

  // --- [FAZ B · B2/B3] KALICI HAFIZA KRİSTALİ ---
  // Görev bitince hafıza sıfırlanmıyor: hedefin geçmiş taramalarından kalan
  // hatıralar burada görünür. Yoksa "HAFIZA YOK" yazar (uydurma geçmiş yok).
  let memoryCrystal: { available: boolean; fragment_count: number; task_count: number; note: string } | null = null;
  let lastMemoryTaskId: string | null = null;

  async function fetchMemoryCrystal(taskId: string) {
    try {
      const res = await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}/memory?client_id=${encodeURIComponent($clientId)}`);
      if (!res.ok) {
        memoryCrystal = null;
        return;
      }
      const data = await res.json();
      memoryCrystal = {
        available: Boolean(data?.available),
        fragment_count: Number(data?.fragment_count ?? 0),
        task_count: Number(data?.task_count ?? 0),
        note: String(data?.machine_note ?? ''),
      };
    } catch (_e) {
      memoryCrystal = null;
    }
  }

  // --- [E6 · Md.1 UYDURMA YASAĞI] ADLİ SÜTUN KANIT KONTROLÜ ---
  // Bulunan açık: modal alanları `|| "Veri mevcut değil"` benzeri dolgu ve `?? 0` ile
  // dolduruluyordu. İkisi de aynı yalanı söylüyordu: ÖLÇÜM YOKKEN kart DOLU
  // görünüyordu (sayı alanında ise "0" gerçek bir ölçüm gibi okunuyordu).
  // Kural: alan boşsa uydurma değer değil, DURUM gösterilir.
  //
  // `0` GEÇERLİ bir ölçümdür (sıfır takipçi = ölçülmüş sıfır); yalnız
  // null/undefined/boş metin/NaN/boş dizi "kanıt yok" sayılır.
  function hasEvidence(value: unknown): boolean {
    if (value === null || value === undefined) return false;
    if (typeof value === 'number') return Number.isFinite(value);
    if (typeof value === 'string') return value.trim().length > 0;
    if (Array.isArray(value)) return value.length > 0;
    return true;
  }

  //: Ölçüm yokluğunun TEK metni (arama/değiştirme ve test için tek kaynak).
  const INSUFFICIENT_EVIDENCE = 'YETERSİZ KANIT';

  // --- [FAZ D · D4] DİL PİLİ ---
  // Kanıta işlenen GERÇEK tespiti gösterir: web çıkarıcıları (trafilatura →
  // crawl4ai → scrapling) çıkardıkları metnin dilini ölçer ve kaydeder; pil
  // o kaydı okur. Hiç ölçüm yoksa "ÖLÇÜLMEDİ" yazar (uydurma etiket yok).
  let langInfo: {
    language: string;
    confidence: number;
    reason: string | null;
    source_engine: string;
    url: string;
  } | null = null;

  async function fetchLanguageStatus() {
    try {
      const res = await apiFetch(`/api/language/status?client_id=${encodeURIComponent($clientId)}`);
      if (!res.ok) {
        langInfo = null;
        return;
      }
      const data = await res.json();
      const last = data?.last;
      if (!last || !last.language) {
        langInfo = null;
        return;
      }
      langInfo = {
        language: String(last.language),
        confidence: Number(last.confidence ?? 0),
        reason: (last.reason as string | null) ?? null,
        source_engine: String(last.source_engine ?? ''),
        url: String(last.url ?? ''),
      };
    } catch (_e) {
      langInfo = null; // ağ hatası: uydurma etiket ÜRETİLMEZ
    }
  }

  // --- [FAZ D · D6] KURUM PİLİ ---
  // Kurum/kuruluş hedefi: theHarvester + açık SEO + kişi künyesi. Pil
  // GERÇEK yetenek durumunu gösterir (defterden): kapı kapalıysa ya da
  // theHarvester yoksa "hazır" DENMEZ.
  let companyInfo: {
    anyAvailable: boolean;
    gate: string;
    modes: { mode: string; available: boolean; reason: string | null }[];
  } | null = null;

  async function fetchCompanyStatus() {
    try {
      const res = await apiFetch('/api/company/status');
      if (!res.ok) {
        companyInfo = null;
        return;
      }
      const data = await res.json();
      companyInfo = {
        anyAvailable: Boolean(data?.any_available),
        gate: String(data?.gate ?? ''),
        modes: Array.isArray(data?.modes)
          ? data.modes.map((row: { mode?: string; available?: boolean; reason?: string | null }) => ({
              mode: String(row?.mode ?? ''),
              available: Boolean(row?.available),
              reason: (row?.reason as string | null) ?? null,
            }))
          : [],
      };
    } catch (_e) {
      companyInfo = null; // ağ hatası: uydurma "hazır" göstergesi ÜRETİLMEZ
    }
  }

  // --- [FAZ D · D2] JÜRİ PİLİ ---
  // Karar tek modele bırakılmaz: aynı kanıt birden çok YEREL modelde bağımsız
  // oylanır. Pil gerçeği gösterir: kaç BAĞIMSIZ koltuk var ve uç yerel mi.
  // Motor yoksa "KAPALI" yazar (uydurma "hazır" göstergesi yok).
  let juryInfo: {
    available: boolean;
    seats: number;
    independentSeats: boolean;
    reason: string | null;
    quorum: number;
  } | null = null;

  async function fetchJuryStatus() {
    try {
      const res = await apiFetch('/api/jury/status');
      if (!res.ok) {
        juryInfo = null;
        return;
      }
      const data = await res.json();
      juryInfo = {
        available: Boolean(data?.available),
        seats: Number(data?.seats ?? 0),
        independentSeats: Boolean(data?.independent_seats),
        reason: (data?.reason as string | null) ?? null,
        quorum: Number(data?.quorum ?? 1),
      };
    } catch (_e) {
      juryInfo = null; // ağ hatası: uydurma koltuk sayısı ÜRETİLMEZ
    }
  }

  // --- [FAZ D · D1] MCP PİLİ ---
  // Pineal'in yetenekleri standart MCP kapısından dışarıya açılıyor. Pil
  // GERÇEK durumu gösterir: kaç yetenek araç olarak yayınlanıyor ve kasa
  // mandalı ne durumda. Kasa kapalıyken araçlar KİLİTLİ yazar (yetenekler
  // koşmaz) — uydurma "hazır" göstergesi yok.
  let mcpInfo: {
    tools: number;
    capabilities: number;
    vaultLocked: boolean;
    protocol: string;
    command: string;
  } | null = null;

  async function fetchMcpStatus() {
    try {
      const res = await apiFetch(`/api/mcp/status?client_id=${encodeURIComponent($clientId)}`);
      if (!res.ok) {
        mcpInfo = null;
        return;
      }
      const data = await res.json();
      if (!data?.available) {
        mcpInfo = null;
        return;
      }
      mcpInfo = {
        tools: Number(data?.tools ?? 0),
        capabilities: Number(data?.capabilities ?? 0),
        vaultLocked: Boolean(data?.vault_locked),
        protocol: String(data?.protocol_current ?? ''),
        command: String(data?.command ?? ''),
      };
    } catch (_e) {
      mcpInfo = null; // ağ hatası: uydurma araç sayısı ÜRETİLMEZ
    }
  }

  async function fetchEvidenceGraph(taskId: string) {
    try {
      const res = await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}/graph?client_id=${encodeURIComponent($clientId)}`);
      if (!res.ok) {
        evidenceGraph = null;
        return;
      }
      const data = await res.json();
      evidenceGraph = {
        available: Boolean(data?.available),
        nodes: Array.isArray(data?.nodes) ? data.nodes : [],
        edges: Array.isArray(data?.edges) ? data.edges : [],
        node_count: data?.node_count ?? 0,
        edge_count: data?.edge_count ?? 0,
        machine_note: data?.machine_note ?? '',
      };
    } catch (_e) {
      evidenceGraph = null; // ağ hatası: uydurma graf ÜRETİLMEZ
    }
  }

  $: {
    const taskId = $taskStatus?.task_id ?? null;
    const status = $taskStatus?.status ?? '';
    if (taskId && TERMINAL_STATUSES.has(String(status)) && taskId !== lastGraphTaskId) {
      lastGraphTaskId = taskId;
      fetchEvidenceGraph(taskId);
    }
    if (taskId && TERMINAL_STATUSES.has(String(status)) && taskId !== lastMemoryTaskId) {
      lastMemoryTaskId = taskId;
      fetchMemoryCrystal(taskId);
    }
    // [FAZ D · D4] Görev bittiğinde kanıta işlenen dil ölçümünü tazele.
    if (taskId && TERMINAL_STATUSES.has(String(status))) {
      fetchLanguageStatus();
    }
  }

  // --- [FAZ B · B5] EŞİK KALİBRASYONU ---
  // 0.70 sabit değil: ölçüldüyse ÖLÇÜLEN değer görünür, ölçülmediyse
  // "ölçülmedi" açıkça yazılır (uydurma kesinlik yok).
  let thresholdInfo: {
    threshold: number;
    source: string;
    reason: string;
    note: string;
  } | null = null;

  async function fetchThreshold() {
    try {
      const res = await apiFetch(`/api/calibration?client_id=${encodeURIComponent($clientId)}`);
      if (!res.ok) {
        thresholdInfo = null;
        return;
      }
      const data = await res.json();
      const quote = data?.scopes?.quote ?? null;
      if (!quote) {
        thresholdInfo = null;
        return;
      }
      thresholdInfo = {
        threshold: Number(quote.threshold ?? 0.7),
        source: String(quote.source ?? 'varsayılan'),
        reason: String(quote.reason ?? ''),
        note: String(quote?.report?.machine_note ?? ''),
      };
    } catch (_e) {
      thresholdInfo = null;
    }
  }

  $: if ($clientId) fetchThreshold();

  $: voiceLabel =
    $speechState === 'speaking'
      ? 'SES: KONUŞUYOR'
      : $speechState === 'listening'
        ? 'SES: DİNLİYOR'
        : $speechState === 'interrupted'
          ? 'SES: SUSTURULDU'
          : $speechState === 'denied'
            ? 'SES: MOTOR YOK'
            : 'SES: SUSKUN';

  function toggleVoice() {
    voiceEnabled.update((v) => !v);
  }

  $: memoryLabel = memoryCrystal?.available
    ? `HAFIZA ${memoryCrystal.fragment_count} HATIRA · ${memoryCrystal.task_count} GÖREV`
    : 'HAFIZA YOK';

  $: thresholdLabel = thresholdInfo
    ? `EŞİK ${thresholdInfo.threshold.toFixed(2)} · ${thresholdInfo.source === 'kalibre' ? 'ÖLÇÜLDÜ' : thresholdInfo.source === 'elle_sabitleme' ? 'ELLE SABİT' : 'ÖLÇÜLMEDİ'}`
    : 'EŞİK —';

  // [FAZ D · D4] DİL pili etiketi: ölçüm yoksa ÖLÇÜLMEDİ (uydurma etiket yok).
  $: langLabel = langInfo
    ? langInfo.language === 'unknown'
      ? 'DİL: ÖLÇÜLEMEDİ'
      : `DİL: ${langInfo.language.toUpperCase()} · ${langInfo.confidence.toFixed(2)}`
    : 'DİL: ÖLÇÜLMEDİ';
  $: if ($clientId) fetchLanguageStatus();

  // [FAZ D · D6] KURUM pili: mod sayısı gerçek yetenek durumundan gelir.
  $: companyLabel = companyInfo
    ? companyInfo.anyAvailable
      ? `KURUM: ${companyInfo.modes.filter((m) => m.available).length}/${companyInfo.modes.length} MOD`
      : companyInfo.modes.length > 0
        ? 'KURUM: KAPALI'
        : 'KURUM: —'
    : 'KURUM: —';
  $: if ($clientId) fetchCompanyStatus();

  // [FAZ D · D2] JÜRİ pili: koltuk sayısı GERÇEK yapılandırmadan gelir.
  $: juryLabel = juryInfo
    ? juryInfo.available
      ? juryInfo.independentSeats
        ? `JÜRİ: ${juryInfo.seats} YEREL KOLTUK`
        : `JÜRİ: 1 KOLTUK · BAĞIMSIZ DEĞİL`
      : `JÜRİ: KAPALI`
    : 'JÜRİ: —';
  $: if ($clientId) fetchJuryStatus();

  // [FAZ D · D1] MCP pili: araç sayısı defterden gelir, kasa durumu gizlenmez.
  $: mcpLabel = mcpInfo
    ? mcpInfo.vaultLocked
      ? `MCP: ${mcpInfo.tools} ARAÇ · KİLİTLİ`
      : `MCP: ${mcpInfo.tools} ARAÇ · AÇIK`
    : 'MCP: —';
  $: if ($clientId) fetchMcpStatus();

  function nowTime() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function addLog(msg: string, level = 'INFO') {
    logs.update(l => [...l, { ts: nowTime(), level, msg }].slice(-80));
  }

  // --- ACTIONS ---
  async function launchAnalysis() {
    const url = targetUrl.trim();
    if (!url || $isProcessing) return;
    isProcessing.set(true);
    playRunning();
    addLog(`ANALİZ BAŞLATILDI: ${url}`, 'INFO');
    chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: `Hedef profil kilitlendi Mösyö: [${url}]. 12 kişilik ajan timi sahaya indi.` }];
    scrollToBottom();

    try {
      const res = await apiFetch('/api/initiate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId,
          url,
          rituals: '',
          playlist: '',
          envies: '',
          scraper_type: 'cross',
        })
      });
      if (!res.ok) throw new Error(isAuthFailure(res) ? 'PINEAL_TOKEN yetki hatası' : `HTTP ${res.status}`);
      const data = await res.json();
      if (data.task_id) {
        taskStatus.update(s => ({ ...(s || {}), task_id: data.task_id, status: 'processing' }));
        addLog(`GÖREV DEVREDE: ${data.task_id}`, 'INFO');
        chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: `Görev #${data.task_id} resmen devrede. Epifiz gözü taramaya odaklandı.` }];
        scrollToBottom();
      }
    } catch (e: any) {
      isProcessing.set(false);
      playHalt();
      addLog(`HATA: ${e?.message || e}`, 'ERROR');
      chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: `Görev başlatılamadı Mösyö: ${e?.message || e}` }];
      scrollToBottom();
    }
  }

  function selectTab(tab: string) {
    activeTab = tab;
    playClick(300, 30);
    const tabDesc: Record<string, string> = {
      'ASPASIA': 'Ana Komuta ve Gözlemci Modu aktif.',
      'VISION': 'Görsel & Estetik Forensik kanalı önceliklendirildi.',
      'OSINT': 'Açık Kaynak Dijital Ayak İzi taraması devrede.',
      'FRICTION': 'Sınır & Hassasiyet (Friction) dedektörü odaklandı.',
      'VERIFY': 'Otonom Heyet Çapraz Doğrulama süzgeci açık.'
    };
    addLog(`GÜVERTE SEÇİMİ: [${tab}] — ${tabDesc[tab] || ''}`, 'INFO');
    chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: `Güverte modu güncellendi Mösyö: [${tab}] — ${tabDesc[tab] || ''}` }];
    scrollToBottom();
  }

  async function toggleVaultLock() {
    playClick(400, 30);
    const targetAction = isVaultLocked ? 'unlock' : 'lock';
    isVaultLocked = !isVaultLocked;
    vaultLocked.set(isVaultLocked);
    const stateText = isVaultLocked ? 'KİLİTLENDİ (OSINT/Scraping korumalı)' : 'AÇILDI (Tam erişim serbest)';
    chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: `Vault mandalı Mösyö: ${stateText}.` }];
    scrollToBottom();

    try {
      await apiFetch('/api/vault/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: $clientId || 'default', action: targetAction })
      });
    } catch (_e) {
      // background sync handled
    }
  }

  // Aspasia Canlı CRT Sohbet Akışı
  let chatMessages: Array<{ ts: string; sender: string; text: string }> = [
    { ts: nowTime(), sender: 'Aspasia', text: 'Sistem çevrimiçi. Dinliyorum Mösyö; hedefin durumunu, riskleri veya aklınızdaki soruları doğrudan sorabilirsiniz.' }
  ];
  let terminalEl: HTMLElement | null = null;

  function scrollToBottom() {
    if (typeof window !== 'undefined') {
      setTimeout(() => {
        if (terminalEl) terminalEl.scrollTop = terminalEl.scrollHeight;
      }, 40);
    }
  }

  // --- [FAZ C · C4] SESLİ RAPOR: bulunanı SÖYLE (göz ekrana bakmak zorunda değil) ---
  // Yalnız GERÇEK alanlar gönderilir; olmayan alan için cümle UYDURULMAZ.
  let isReadingReport = false;

  function reportDigest(status: any): Record<string, unknown> | null {
    if (!status || typeof status !== 'object') return null;
    const runs: Record<string, unknown> = {};
    const rawRuns = status.runs || {};
    for (const [name, entry] of Object.entries<any>(rawRuns)) {
      runs[name] = { status: entry?.status ?? null, confidence: entry?.confidence ?? null };
    }
    return {
      task_id: status.task_id ?? null,
      status: status.status ?? null,
      target_profile: status.target_profile ?? null,
      evidence_chain: (status.evidence_chain || []).map((e: any) => ({ agent: e?.agent ?? null })),
      runs,
      changes: status.changes ?? null,
      depth_report: status.depth_report ?? null,
      follower_audit: status.follower_audit ?? null,
      timing_forensics: status.timing_forensics ?? null,
      minor_gate: status.minor_gate ?? status.child_safety ?? null
    };
  }

  async function readReportAloud() {
    const digest = reportDigest($taskStatus);
    if (!digest || isReadingReport) return;
    isReadingReport = true;
    playClick(590, 40);
    try {
      const res = await apiFetch('/api/speech/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: $clientId || 'default', report: digest })
      });
      const data = await res.json();
      if (data.script) addLog(`SES: rapor okundu → ${data.script}`, 'INFO');
      if (!data.available) addLog(`SES: ses ÜRETİLEMEDİ — ${data.reason}`, 'WARNING');
    } catch (_e) {
      addLog('SES: rapor okunamadı', 'WARNING');
    } finally {
      isReadingReport = false;
    }
  }

  // --- [FAZ C · C3] DİNLEYEN GÖZ: mikrofon -> yerel STT -> Aspasia ---
  // Kayıt TARAYICIDA tutulur, yalnız transkript için YEREL motora gider;
  // ses dosyası dışarı çıkmaz. Motor yoksa uydurma metin yazılmaz.
  let micRecorder: MediaRecorder | null = null;
  let micChunks: Blob[] = [];
  let micStream: MediaStream | null = null;
  let isListening = false;

  async function toggleListening() {
    if (isListening) {
      stopListening();
      return;
    }
    // ARAYA GİRME: Aspasia konuşurken mikrofon açılırsa SUSAR.
    if ($speechState === 'speaking') {
      try {
        await apiFetch(`/api/speech/stop?client_id=${encodeURIComponent($clientId)}`, { method: 'POST' });
        addLog('SES: araya girildi — Aspasia sustu', 'INFO');
      } catch (_e) {
        addLog('SES: araya girilemedi', 'WARNING');
      }
    }
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (_e) {
      addLog('SES: mikrofon izni yok / cihaz yok', 'WARNING');
      return;
    }
    micChunks = [];
    const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4';
    micRecorder = new MediaRecorder(micStream, { mimeType: mime });
    micRecorder.ondataavailable = (e) => { if (e.data && e.data.size > 0) micChunks.push(e.data); };
    micRecorder.onstop = () => { void transcribeAndSend(); };
    micRecorder.start();
    isListening = true;
    playClick(660, 40);
    addLog('SES: dinliyorum...', 'INFO');
  }

  function stopListening() {
    if (micRecorder && micRecorder.state !== 'inactive') micRecorder.stop();
    micStream?.getTracks().forEach((t) => t.stop());
    micStream = null;
    isListening = false;
    playClick(330, 40);
  }

  async function transcribeAndSend() {
    if (!micChunks.length) {
      addLog('SES: kayıt boş', 'WARNING');
      return;
    }
    const form = new FormData();
    form.append('file', new Blob(micChunks, { type: micChunks[0].type || 'audio/webm' }), 'mic.webm');
    micChunks = [];
    try {
      const res = await apiFetch(
        `/api/speech/listen?client_id=${encodeURIComponent($clientId)}`,
        { method: 'POST', body: form }
      );
      const data = await res.json();
      if (!data.available) {
        addLog(`SES: duyulamadı — ${data.reason || 'motor yok'}`, 'WARNING');
        return;
      }
      const heard = String(data.transcript || '').trim();
      if (!heard) {
        addLog('SES: transkript boş', 'WARNING');
        return;
      }
      addLog(`SES: duyuldu (${data.engine}) → ${heard}`, 'INFO');
      inputMessage = heard;
      // Eller serbest: duyulan metin doğrudan Aspasia'ya gider (kayıt üstünde).
      await sendAspasiaMessage();
    } catch (_e) {
      addLog('SES: dinleme başarısız', 'WARNING');
    }
  }

  async function sendAspasiaMessage() {
    const text = inputMessage.trim();
    if (!text || isSending) return;
    inputMessage = '';
    isSending = true;
    playClick(440, 30);
    
    // Anında canlı ekrana yaz
    chatMessages = [...chatMessages, { ts: nowTime(), sender: 'SİZ', text }];
    scrollToBottom();
    addLog(`SİZ: ${text}`, 'INFO');

    try {
      const res = await apiFetch('/api/aspasia/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          user_message: text
        })
      });

      if (res.ok) {
        const data = await res.json();
        const reply = data.message || data.reply || data.response || 'Emir alındı Mösyö.';
        chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: reply }];
        scrollToBottom();
        addLog(`ASPASIA: ${reply}`, 'INFO');
        playClick(520, 40);
      } else {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch (err: any) {
      const errMsg = `Aspasia yanıt veremedi: ${err.message || err}`;
      chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: errMsg }];
      scrollToBottom();
      addLog(`ASPASIA HATA: ${err.message}`, 'ERROR');
    } finally {
      isSending = false;
    }
  }

  function togglePillar(pillarId: string) {
    playClick(320, 40);
    activePillarModal = activePillarModal === pillarId ? null : pillarId;
    addLog(`7 SÜTUN: ${pillarId.toUpperCase()} raporu açıldı`, 'INFO');
  }
</script>

<svelte:window on:mousemove={handleMouseMove} />

<div class="cockpit-viewport-frame" role="region" aria-label="Atlas Epifiz Pineal Observatory">
  <!-- 1. TEK VE DOKUNULMAZ ANA ŞASİ GÖRSELİ (Kayıpsız 16:9) — PINEAL-HERETIC İMZASI -->
  <img class="master-cockpit-bg" src={cockpitSkin} alt="Atlas Pineal Observatory Cockpit" />

  <!-- 2. ORİJİNAL %12.2 YAŞAYAN PİNEAL GÖZ — PİRİNÇ HALKA İÇİNDE, TAŞMA YOK -->
  <div class="living-eye-viewport" aria-label="Atlas Pineal Eye - Original Brass">
    <!-- Arkada: Holografik tel kafes — pirinç halka içinde, düşük yoğunluk -->
    <div class="mesh-layer">
      <HolographicResonanceMesh
        size={meshSize}
        active={$isProcessing}
        intensity={isVaultLocked ? 0.22 : 0.48}
        graph={evidenceGraph}
      />
    </div>
    <!-- Önde: Orijinal living_pineal_disk.png — organik drift korunuyor -->
    <img
      class="living-eye-disk"
      src={livingPinealDisk}
      alt="Atlas Pineal Eye"
      style="transform: translate(calc(-50% + {eyeX.toFixed(2)}px), calc(-50% + {eyeY.toFixed(2)}px)) scale({eyeScale.toFixed(3)});"
    />
  </div>

  <!-- [FAZ B · B2/B3] HAFIZA PİLİ: geçmiş hatıralar (kristal) -->
  <div
    class="memory-pill"
    class:has-memory={Boolean(memoryCrystal?.available)}
    title={memoryCrystal?.note || 'Bu hedef için geçmiş hatıra yok'}
  >
    {memoryLabel}
  </div>

  <!-- [FAZ C · C2] SES PİLİ: konuşma durumu backend'den gelir (uydurma değil) -->
  <button
    class="voice-pill"
    class:speaking={$speechState === 'speaking'}
    class:muted={!$voiceEnabled}
    on:click={toggleVoice}
    title={$lastSpeech?.machine_note || 'Ses durumu: konuşma yok (motor yerel)'}
  >
    {voiceLabel}{$voiceEnabled ? '' : ' · KAPALI'}
  </button>

  <!-- [FAZ D · D4] DİL PİLİ: kanıta işlenen gerçek tespit (uydurma etiket yok) -->
  <div
    class="language-pill"
    class:detected={Boolean(langInfo && langInfo.language !== 'unknown')}
    class:unknown={Boolean(langInfo && langInfo.language === 'unknown')}
    title={langInfo
      ? langInfo.language === 'unknown'
        ? langInfo.reason || 'Dil sinyali ölçülemedi'
        : `${langInfo.source_engine}${langInfo.url ? ' → ' + langInfo.url : ''} · güven ${langInfo.confidence.toFixed(2)}`
      : 'Henüz dil ölçümü yok — web çıkarıcıları çıkardıkları metnin dilini işler'}
  >
    {langLabel}
  </div>

  <!-- [FAZ D · D1] MCP PİLİ: yetenekler standart kapıdan dışarıda (gerçek sayı) -->
  <div
    class="mcp-pill"
    class:ready={Boolean(mcpInfo && !mcpInfo.vaultLocked)}
    class:locked={Boolean(mcpInfo && mcpInfo.vaultLocked)}
    title={mcpInfo
      ? `${mcpInfo.capabilities} yetenek · protokol ${mcpInfo.protocol} · ${mcpInfo.command}`
      : 'MCP durumu okunamadı — sunucu kapalı olabilir'}
  >
    {mcpLabel}
  </div>

  <!-- [FAZ D · D2] JÜRİ PİLİ: kaç bağımsız YEREL koltuk (uydurma hazır yok) -->
  <div
    class="jury-pill"
    class:ready={Boolean(juryInfo?.available && juryInfo?.independentSeats)}
    class:thin={Boolean(juryInfo?.available && !juryInfo?.independentSeats)}
    title={juryInfo
      ? juryInfo.available
        ? `${juryInfo.seats} koltuk · yeter sayı ${juryInfo.quorum} · uç yalnız yerel`
        : `Jüri kapalı: ${juryInfo.reason || 'sebep yok'}`
      : 'Jüri durumu okunamadı'}
  >
    {juryLabel}
  </div>

  <!-- [FAZ D · D6] KURUM PİLİ: theHarvester + açık SEO + kişi künyesi -->
  <div
    class="company-pill"
    class:ready={Boolean(companyInfo?.anyAvailable)}
    title={companyInfo
      ? companyInfo.anyAvailable
        ? companyInfo.modes
            .map((m) => `${m.mode}:${m.available ? 'hazır' : m.reason || 'kapalı'}`)
            .join(' · ')
        : `Kurum hedefi kapalı — kapı ${companyInfo.gate}`
      : 'Kurum durumu okunamadı'}
  >
    {companyLabel}
  </div>

  <!-- [FAZ B · B5] EŞİK PİLİ: sabit 0.70 değil, ölçülen değer -->
  <div
    class="threshold-pill"
    class:measured={thresholdInfo?.source === 'kalibre'}
    title={thresholdInfo?.note || 'Kalibrasyon verisi yok — eşik varsayılan'}
  >
    {thresholdLabel}
  </div>

  <!-- HIZLI GEÇİŞ BUTONU: TACTICAL WAR ROOM (100% ŞEFFAF MUHAREBE MASASI) -->
  <button 
    class="war-room-switch-pill" 
    on:click={() => openWarRoom()} 
    title="100% Şeffaf Muharebe Masası & Ajan Teftiş Odasına Geç"
  >
    <span class="war-icon">⚔️</span>
    <span class="war-text">MUHAREBE MASASI</span>
    <span class="war-tag">WAR ROOM</span>
  </button>

  <!-- Sağda: Agent Rack — Redis Pub/Sub canlı -->
  <div class="agent-rack-dock" class:visible={showAgentRack}>
    <AgentRack compact={false} on:select={(e) => openWarRoom(e.detail?.agentId)} />
    <button class="rack-toggle-btn" on:click={() => showAgentRack = !showAgentRack} title="Agent Rack Toggle">
      {showAgentRack ? '◀' : '▶'}
    </button>
  </div>

  <!-- Vault LED — gözün üzerinde DEĞİL, sol alt Aspasia konsolunda küçük nokta -->
  <div
    class="vault-led"
    class:locked={isVaultLocked}
    class:open={!isVaultLocked}
    role="button"
    tabindex="0"
    on:click={toggleVaultLock}
    on:keydown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleVaultLock(); }}
    title={isVaultLocked ? 'VAULT KİLİTLİ: Tıkla ve Aç (OSINT/Scraper serbest bırak)' : 'VAULT AÇIK: Tıkla ve Kilitle'}
  >
    <span class="vault-dot"></span>
    <span class="vault-label">{isVaultLocked ? 'VAULT' : 'OPEN'}</span>
  </div>

  <!-- 2. SADECE İŞLEVSEL ŞEFFAF HİTBOX'LAR (TIKLAMA ALANLARI) -->

  <!-- Orta Güverte 5 Tab Butonları -->
  <div class="tabs-hitbox-group">
    {#each ['ASPASIA', 'VISION', 'OSINT', 'FRICTION', 'VERIFY'] as tab}
      <button
        class="tab-touch-seal {activeTab === tab ? 'tab-active' : ''}"
        on:click={() => selectTab(tab)}
        title="{tab} Ekranı"
      ></button>
    {/each}
  </div>

  <!-- URL Yazma Kutusu (Kaset ekranına tam oturan şeffaf giriş alanı) -->
  <div class="url-cassette-chamber">
    <input
      type="text"
      class="url-cassette-input"
      bind:value={targetUrl}
      placeholder="> Hedef profil / URL kaseti girin..."
      disabled={$isProcessing}
      on:keydown={(e) => { if (e.key === 'Enter') launchAnalysis(); }}
      title="Hedef Profil / URL Kaseti"
    />
  </div>

  <!-- Mekanik CAPTURE Butonu (Yeşil başlatma butonu üzerine şeffaf alan) -->
  <button
    class="antique-touch-btn capture-mechanical-spot {$isProcessing ? 'capture-running' : ''}"
    on:click={launchAnalysis}
    disabled={$isProcessing || !targetUrl.trim()}
    title="ANALİZİ BAŞLAT (CAPTURE)"
  ></button>

  <!-- Aspasia Canlı CRT Terminal Ekranı (Dinamik Canlı Sohbet & Rapor Akışı) -->
  <div class="aspasia-crt-terminal" bind:this={terminalEl}>
    {#each chatMessages as msg}
      <div class="term-line {msg.sender === 'SİZ' ? 'user-line' : 'aspasia-line'}">
        <span class="ts">[{msg.ts}]</span>
        <span class={msg.sender === 'SİZ' ? 'sender-user' : 'sender-aspasia'}>{msg.sender}</span>
        <span class="arrow">&gt;</span>
        <span class="term-text">{msg.text}</span>
      </div>
    {/each}
    {#if isSending}
      <div class="term-line typing-line">
        <span class="ts">[{nowTime()}]</span>
        <span class="sender-aspasia">Aspasia</span>
        <span class="arrow">&gt;</span>
        <span class="term-text typing-glow">Düşünüyor ve sistem verilerini inceliyor...</span>
      </div>
    {/if}
  </div>

  <!-- Aspasia Sohbet/Komut Satırı (Sol alttaki '> Komut veya sorgu gir...' alanı) -->
  <div class="aspasia-command-slot">
    <input
      type="text"
      class="aspasia-command-input"
      bind:value={inputMessage}
      placeholder="> Komut veya soru girin (Enter ile gönder)..."
      disabled={isSending}
      on:keydown={(e) => { if (e.key === 'Enter') sendAspasiaMessage(); }}
      title="Aspasia Komut Satırı"
    />
  </div>

  <!-- [FAZ C · C4] SESLİ RAPOR: son görevin özetini YÜKSEK SESLE okur -->
  <button
    class="mic-spot report-spot"
    on:click={readReportAloud}
    disabled={isReadingReport || !$taskStatus}
    title={$taskStatus ? 'Son raporu sesli oku' : 'Okunacak rapor yok'}
  >
    {isReadingReport ? 'OKUYOR' : 'RAPORU OKU'}
  </button>

  <!-- [FAZ C · C3] MİKROFON: bas -> dinler, bırak -> yerel STT -> Aspasia -->
  <button
    class="mic-spot"
    class:listening={isListening}
    on:click={toggleListening}
    title={isListening ? 'Dinliyorum — bırakmak için tıkla' : 'Mikrofon: konuş, Aspasia duysun'}
  >
    {isListening ? 'DİNLİYOR' : 'MİK'}
  </button>

  <!-- Aspasia GÖNDER Butonu ('GÖNDER' butonu üzerine şık buton) -->
  <button
    class="aspasia-send-spot"
    on:click={sendAspasiaMessage}
    disabled={isSending || !inputMessage.trim()}
    title="GÖNDER"
  >
    GÖNDER
  </button>

  <!-- 7 Sütun Dokunmatik Butonları (FOLLOWER, TIMING, DEPTH, VISUAL, SHADOW, OSINT, RESONANCE) -->
  <div class="seven-pillars-hitbox-rack">
    {#each pillarsList as p}
      <button
        class="pillar-touch-seal {activePillarModal === p.id ? 'pillar-active' : ''}"
        on:click={() => togglePillar(p.id)}
        title="{p.label} ({p.tr}) Adli Raporu"
      ></button>
    {/each}
  </div>

  <!-- 3. ADLİ RAPOR KARTI (Sadece bir sütuna tıklandığında açılır) -->
  {#if activePillarModal}
    <div class="forensic-backdrop" role="presentation" on:click={() => activePillarModal = null} on:keydown={(e) => { if (e.key === 'Escape') activePillarModal = null; }}>
      <div class="forensic-card" role="dialog" aria-modal="true" tabindex="-1" on:click|stopPropagation on:keydown|stopPropagation>
        <div class="forensic-card-header">
          <span class="card-title">ADLİ SÜTUN: {activePillarModal.toUpperCase()}</span>
          <button class="close-x" on:click={() => activePillarModal = null}>✕</button>
        </div>
        <div class="forensic-card-body">
          {#if activePillarModal === 'follower' && followerAudit}
            <div class="report-block">
              <h4>Takipçi & Kitle Bütünlüğü</h4>
              <p>Hüküm: <strong>{followerAudit.verdict || 'BİLİNMİYOR'}</strong> ({followerAudit.verdict_code || 'nominal'})</p>
              <p>
                Takipçi Sayısı:
                {#if hasEvidence(followerAudit.follower_count)}{followerAudit.follower_count}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}
                · Takip: {#if hasEvidence(followerAudit.following_count)}{followerAudit.following_count}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}
              </p>
              <p>Etkileşim Katsayısı: {#if hasEvidence(followerAudit.engagement_rate)}{followerAudit.engagement_rate}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Veri Tamlığı: {#if hasEvidence(followerAudit.data_completeness)}%{(followerAudit.data_completeness * 100).toFixed(0)}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
            </div>
          {:else if activePillarModal === 'timing' && timingForensics}
            <div class="report-block">
              <h4>Zaman & Sirkadiyen Forensik</h4>
              <p>Gece Payı: {#if hasEvidence(timingForensics.night_share)}%{(timingForensics.night_share * 100).toFixed(0)}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Tepe Saati: {#if hasEvidence(timingForensics.peak_hour)}{timingForensics.peak_hour}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Medyan Kayma: {#if hasEvidence(timingForensics.median_drift_hours)}{timingForensics.median_drift_hours}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if} saat</p>
            </div>
          {:else if activePillarModal === 'depth' && depthReport}
            <div class="report-block">
              <h4>Derinlik & Alıntı Kalkanı</h4>
              <p>Gerçeklik İndeksi: {#if hasEvidence(depthReport.reality_index)}%{(depthReport.reality_index * 100).toFixed(0)}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Öz Çıkarım: {#if hasEvidence(depthReport.essence_one_liner)}{depthReport.essence_one_liner}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
            </div>
          {:else if activePillarModal === 'visual' && visualEvidence}
            <div class="report-block">
              <h4>Görsel & Estetik Forensik</h4>
              <p>Estetik Stil: {#if hasEvidence(visualEvidence.aesthetic_style)}{visualEvidence.aesthetic_style}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Özet: {#if hasEvidence(visualEvidence.visual_evidence_summary)}{visualEvidence.visual_evidence_summary}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
            </div>
          {:else if activePillarModal === 'shadow' && shadowProfile}
            <div class="report-block">
              <h4>Gölge Profili (Karanlık Üçlü)</h4>
              <p>Narsisizm Skoru: {#if hasEvidence(shadowProfile.dark_profile?.narcissism)}{shadowProfile.dark_profile?.narcissism}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Tespit Edilen Strateji: {#if hasEvidence(shadowProfile.strategy)}{shadowProfile.strategy}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
            </div>
          {:else if activePillarModal === 'osint' && osintFootprint}
            <div class="report-block">
              <h4>OSINT Dijital Ayak İzi</h4>
              <p>İlişkili Platformlar: {#if hasEvidence(osintFootprint.associated_platforms)}{osintFootprint.associated_platforms.join(', ')}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
            </div>
          {:else if activePillarModal === 'resonance' && resonanceCalc}
            <div class="report-block">
              <h4>Rezonans & Uyum</h4>
              <p>Uyum Skoru: {#if hasEvidence(resonanceCalc.compatibility_score)}%{(resonanceCalc.compatibility_score * 100).toFixed(0)}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
              <p>Yaklaşım Protokolü: {#if hasEvidence(resonanceCalc.recommended_approach)}{resonanceCalc.recommended_approach}{:else}<span class="evidence-insufficient" title="Alan boş döndü — ölçüm yok">{INSUFFICIENT_EVIDENCE}</span>{/if}</p>
            </div>
          {:else}
            <div class="report-block">
              <h4>{activePillarModal.toUpperCase()} Sinyali</h4>
              <p>Bu sütun için henüz aktif analiz verisi işlenmedi. Hedef kasetine profil girip CAPTURE tuşuna basın.</p>
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  /* =========================================================
     TAM EKRAN SİNEMATİK KOKPİT (TEK ANA ŞASİ)
     ========================================================= */
  .cockpit-viewport-frame {
    position: relative;
    width: 100vw;
    height: 100vh;
    max-width: calc(100vh * 16 / 9);
    max-height: calc(100vw * 9 / 16);
    aspect-ratio: 16 / 9;
    margin: auto;
    overflow: hidden;
    background: #000;
    user-select: none;
    font-family: 'JetBrains Mono', monospace;
  }

  /* Tek Dokunulmaz Orijinal Ana Şasi */
  .master-cockpit-bg {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: fill;
    pointer-events: none;
    z-index: 1;
  }

  /* =========================================================
     YAŞAYAN PİNEAL GÖZ — ORİJİNAL %12.2 PİRİNÇ HALKA, TAŞMA YOK
     PINEAL-HERETIC imzası: living_pineal_disk.png merkezde, mesh halka içinde
     ========================================================= */
  .living-eye-viewport {
    position: absolute;
    left: 49.76%;
    top: 45.70%;
    width: 12.2%;
    aspect-ratio: 1;
    transform: translate(-50%, -50%);
    border-radius: 50%;
    overflow: hidden;
    pointer-events: none;
    z-index: 3;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow:
      inset 0 0 10px rgba(0, 0, 0, 0.85),
      inset 0 2px 6px rgba(0, 0, 0, 0.95),
      0 0 0 1px rgba(212, 175, 55, 0.15);
  }

  .living-eye-viewport .mesh-layer {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1;
    pointer-events: none;
    border-radius: 50%;
    overflow: hidden;
  }

  .living-eye-disk {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 108%;
    height: 108%;
    border-radius: 50%;
    object-fit: cover;
    pointer-events: none;
    will-change: transform;
    filter: contrast(1.02) brightness(1.01);
    z-index: 2;
  }

  /* Vault LED — gözün üzerinde DEĞİL, sol alt küçük nokta */
  .vault-led {
    position: absolute;
    left: 2.8%;
    top: 91.2%;
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 7px;
    font-weight: 800;
    letter-spacing: 0.14em;
    z-index: 15;
    pointer-events: auto;
    cursor: pointer;
    background: rgba(0, 0, 0, 0.55);
    border: 1px solid rgba(212, 175, 55, 0.25);
    backdrop-filter: blur(2px);
    transition: all 0.3s ease;
  }

  .vault-led.locked {
    color: #fca5a5;
    border-color: rgba(239, 68, 68, 0.35);
    box-shadow: 0 0 8px rgba(239, 68, 68, 0.25);
  }

  .vault-led.open {
    color: #6ee7b7;
    border-color: rgba(16, 185, 129, 0.35);
    box-shadow: 0 0 8px rgba(16, 185, 129, 0.25);
  }

  .vault-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .vault-led.locked .vault-dot {
    background: #ef4444;
    box-shadow: 0 0 6px #ef4444;
    animation: lockPulse 1.6s ease-in-out infinite;
  }

  .vault-led.open .vault-dot {
    background: #10b981;
    box-shadow: 0 0 6px #10b981;
  }

  @keyframes lockPulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.55; transform: scale(0.85); }
  }

  /* Agent Rack Dock - Sağ taraf — Redis canlı köprü korundu */
  .agent-rack-dock {
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%) translateX(100%);
    z-index: 90;
    transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    pointer-events: auto;
    max-height: 85vh;
    overflow: visible;
  }

  .agent-rack-dock.visible {
    transform: translateY(-50%) translateX(0);
  }

  .rack-toggle-btn {
    position: absolute;
    left: -24px;
    top: 50%;
    transform: translateY(-50%);
    width: 24px;
    height: 60px;
    background: linear-gradient(180deg, #1a1a2e 0%, #0a0e1a 100%);
    border: 1px solid rgba(212, 175, 55, 0.3);
    border-right: none;
    border-radius: 6px 0 0 6px;
    color: #d4af37;
    font-size: 10px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: -2px 0 8px rgba(0, 0, 0, 0.5);
  }

  .rack-toggle-btn:hover {
    background: linear-gradient(180deg, #2a2a4e 0%, #1a1e2a 100%);
    color: #fde68a;
  }

  /* =========================================================
     ŞEFFAF HİTBOX'LAR (SIFIR ÇİRKİN KENARLIK, HAFİF AMBER GLOW)
     ========================================================= */
  .antique-touch-btn {
    position: absolute;
    background: transparent;
    border: none;
    outline: none;
    cursor: pointer;
    z-index: 10;
    transition: box-shadow 0.25s ease, background 0.25s ease;
  }

  .antique-touch-btn:hover {
    box-shadow: 0 0 16px rgba(230, 140, 30, 0.45), inset 0 0 8px rgba(245, 158, 11, 0.25);
    background: rgba(230, 130, 20, 0.08);
  }

  /* 5 Orta Güverte Sekmesi */
  .tabs-hitbox-group {
    position: absolute;
    left: 28.5%;
    top: 67.0%;
    width: 38.0%;
    height: 4.5%;
    display: flex;
    gap: 2%;
    z-index: 10;
  }

  .tab-touch-seal {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    cursor: pointer;
    border-radius: 2px;
    transition: all 0.2s ease;
  }

  .tab-touch-seal:hover, .tab-touch-seal.tab-active {
    background: rgba(230, 140, 30, 0.18);
    box-shadow: 0 0 10px rgba(230, 140, 30, 0.4);
  }

  /* URL Yazma Kutusu */
  .url-cassette-chamber {
    position: absolute;
    left: 39.10%;
    top: 70.20%;
    width: 21.30%;
    height: 8.20%;
    z-index: 12;
    display: flex;
    align-items: center;
  }

  .url-cassette-input {
    width: 100%;
    height: 100%;
    background: rgba(3, 8, 5, 0.88);
    border: 1px solid rgba(212, 175, 55, 0.35);
    border-radius: 4px;
    outline: none;
    padding: 0 10px;
    color: #fde68a;
    font-size: clamp(9px, 0.95vw, 13px);
    font-family: 'JetBrains Mono', monospace;
    caret-color: #f59e0b;
    text-shadow: 0 0 8px rgba(245, 158, 11, 0.6);
    box-shadow: inset 0 0 8px rgba(0, 0, 0, 0.9);
    transition: all 0.2s ease;
  }

  .url-cassette-input::placeholder {
    color: rgba(212, 175, 55, 0.5);
    font-size: 0.9em;
  }

  .url-cassette-input:focus {
    background: #040907;
    border-color: rgba(245, 158, 11, 0.65);
    box-shadow: inset 0 0 12px rgba(0, 0, 0, 0.95), 0 0 8px rgba(245, 158, 11, 0.3);
  }

  /* CAPTURE Butonu */
  .capture-mechanical-spot {
    left: 60.60%;
    top: 70.80%;
    width: 4.80%;
    height: 7.20%;
    border-radius: 50%;
  }

  .capture-mechanical-spot:hover {
    box-shadow: 0 0 18px rgba(230, 140, 30, 0.65), inset 0 0 10px rgba(245, 158, 11, 0.35);
  }

  .capture-mechanical-spot.capture-running {
    box-shadow: 0 0 18px rgba(239, 68, 68, 0.7);
    animation: amberPulse 0.8s infinite alternate;
  }

  /* =========================================================
     CANLI ASPASIA CRT TERMİNAL EKRANI (DİNAMİK AKIŞ)
     ========================================================= */
  .aspasia-crt-terminal {
    position: absolute;
    left: 5.44%;
    top: 83.20%;
    width: 44.50%;
    height: 10.40%;
    background: #020705;
    border-radius: 3px;
    padding: 6px 10px;
    overflow-y: auto;
    overflow-x: hidden;
    z-index: 12;
    display: flex;
    flex-direction: column;
    gap: 4px;
    box-shadow: inset 0 0 12px rgba(0, 0, 0, 0.95), inset 0 0 4px rgba(6, 182, 212, 0.15);
    font-family: 'JetBrains Mono', monospace;
    font-size: clamp(9px, 0.76vw, 12px);
    line-height: 1.35;
    border: 1px solid rgba(16, 185, 129, 0.25);
  }

  .aspasia-crt-terminal::-webkit-scrollbar {
    width: 4px;
  }
  .aspasia-crt-terminal::-webkit-scrollbar-thumb {
    background: rgba(16, 185, 129, 0.4);
    border-radius: 2px;
  }

  .term-line {
    display: flex;
    align-items: baseline;
    gap: 6px;
    word-break: break-word;
  }

  .ts {
    color: #4b6e5e;
    font-size: 0.82em;
    flex-shrink: 0;
  }

  .sender-aspasia {
    color: #38ef7d;
    font-weight: 700;
    flex-shrink: 0;
    text-shadow: 0 0 6px rgba(56, 239, 125, 0.6);
  }

  .sender-user {
    color: #f59e0b;
    font-weight: 700;
    flex-shrink: 0;
    text-shadow: 0 0 6px rgba(245, 158, 11, 0.6);
  }

  .arrow {
    color: #2dd4bf;
    font-weight: bold;
    flex-shrink: 0;
  }

  .term-text {
    color: #a7f3d0;
    text-shadow: 0 0 4px rgba(167, 243, 208, 0.3);
  }

  .user-line .term-text {
    color: #fef3c7;
    text-shadow: 0 0 4px rgba(254, 243, 199, 0.3);
  }

  .typing-glow {
    color: #67e8f9;
    animation: textPulse 1s infinite alternate;
  }

  @keyframes textPulse {
    0% { opacity: 0.5; }
    100% { opacity: 1; }
  }

  /* Aspasia Sohbet/Komut Satırı */
  .aspasia-command-slot {
    position: absolute;
    left: 5.44%;
    top: 93.90%;
    width: 38.60%;
    height: 3.80%;
    z-index: 12;
    display: flex;
    align-items: center;
  }

  .aspasia-command-input {
    width: 100%;
    height: 100%;
    background: #020705;
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 3px;
    outline: none;
    padding: 0 10px;
    color: #34d399;
    font-size: clamp(9px, 0.82vw, 12px);
    font-family: 'JetBrains Mono', monospace;
    caret-color: #10b981;
    box-shadow: inset 0 0 8px rgba(0, 0, 0, 0.95);
    transition: all 0.2s ease;
  }

  .aspasia-command-input:focus {
    border-color: #10b981;
    box-shadow: inset 0 0 8px rgba(0, 0, 0, 0.95), 0 0 8px rgba(16, 185, 129, 0.35);
    color: #6ee7b7;
  }

  .aspasia-command-input::placeholder {
    color: rgba(52, 211, 153, 0.4);
    font-size: 0.9em;
  }

  /* Aspasia GÖNDER Butonu */
  .aspasia-send-spot {
    position: absolute;
    left: 44.50%;
    top: 93.90%;
    width: 5.44%;
    height: 3.80%;
    border-radius: 3px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(16, 185, 129, 0.18);
    border: 1px solid rgba(16, 185, 129, 0.4);
    color: #34d399;
    font-family: 'JetBrains Mono', monospace;
    font-size: clamp(8px, 0.70vw, 11px);
    font-weight: 700;
    letter-spacing: 0.08em;
    cursor: pointer;
    transition: all 0.2s ease;
    z-index: 12;
  }

  .aspasia-send-spot:hover:not(:disabled) {
    background: rgba(16, 185, 129, 0.35);
    box-shadow: 0 0 12px rgba(16, 185, 129, 0.5);
    color: #fff;
  }

  .aspasia-send-spot:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  /* 7 Sütun Dokunmatik Alanları */
  .seven-pillars-hitbox-rack {
    position: absolute;
    left: 53.95%;
    top: 86.72%;
    width: 42.05%;
    height: 9.88%;
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 1.2%;
    z-index: 10;
  }

  .pillar-touch-seal {
    background: transparent;
    border: none;
    outline: none;
    cursor: pointer;
    border-radius: 4px;
    transition: all 0.2s ease;
  }

  .pillar-touch-seal:hover, .pillar-touch-seal.pillar-active {
    background: rgba(230, 140, 30, 0.18);
    box-shadow: 0 0 16px rgba(230, 140, 30, 0.5), inset 0 0 8px rgba(245, 158, 11, 0.3);
  }

  /* =========================================================
     ADLİ RAPOR KARTI (SADECE TIKLANDIĞINDA AÇILIR)
     ========================================================= */
  .forensic-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.85);
    backdrop-filter: blur(5px);
    z-index: 99999;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .forensic-card {
    background: #0e0a06;
    border: 2px solid #8e6538;
    border-radius: 6px;
    box-shadow: 0 0 50px rgba(0, 0, 0, 0.95), inset 0 0 30px rgba(0, 0, 0, 0.8);
    width: min(88vw, 640px);
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    color: #f5edd8;
  }

  .forensic-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 16px;
    background: linear-gradient(180deg, #2a1a0c 0%, #160e06 100%);
    border-bottom: 1px solid #785226;
  }

  .card-title {
    font-family: 'Cinzel', serif;
    font-weight: 800;
    font-size: 13px;
    color: #d4af37;
    letter-spacing: 0.12em;
  }

  .close-x {
    background: transparent;
    border: none;
    color: #d4af37;
    font-size: 16px;
    cursor: pointer;
  }

  .forensic-card-body {
    padding: 16px;
    overflow-y: auto;
  }

  .report-block h4 {
    color: #d4af37;
    margin: 0 0 8px 0;
    font-size: 14px;
    border-bottom: 1px solid #5a3d1c;
    padding-bottom: 4px;
  }

  .report-block p {
    margin: 6px 0;
    font-size: 12px;
    color: #fde68a;
    line-height: 1.5;
  }

  /* [E6 · Md.1] ÖLÇÜM YOKLUĞU BİR DURUMDUR, dolgu metni değil: kart "dolu"
     görünmesin diye uyarı rengi + altı çizili + sebep tooltip'i. */
  .evidence-insufficient {
    color: #ef4444;
    font-weight: 700;
    letter-spacing: 0.04em;
    border-bottom: 1px dashed #ef4444;
    cursor: help;
  }

  @keyframes amberPulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.6; transform: scale(0.98); }
  }

  /* TACTICAL WAR ROOM GEÇİŞ BUTONU */
  .mic-spot {
    position: absolute;
    bottom: 168px;
    left: 300px;
    z-index: 106;
    padding: 6px 14px;
    background: rgba(10, 15, 29, 0.9);
    border: 1px solid rgba(148, 163, 184, 0.5);
    border-radius: 9999px;
    font-family: 'JetBrains Mono', monospace, sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: #94a3b8;
    cursor: pointer;
    white-space: nowrap;
    backdrop-filter: blur(6px);
  }

  .mic-spot.listening {
    border-color: rgba(34, 197, 94, 0.8);
    color: #86efac;
    box-shadow: 0 0 16px rgba(34, 197, 94, 0.35);
  }

  .report-spot {
    left: 404px;
    border-color: rgba(56, 189, 248, 0.5);
    color: #7dd3fc;
  }

  .voice-pill {
    position: absolute;
    top: 54px;
    right: 32px;
    z-index: 104;
    padding: 6px 14px;
    background: rgba(10, 15, 29, 0.82);
    border: 1px solid rgba(148, 163, 184, 0.45);
    border-radius: 9999px;
    font-family: 'JetBrains Mono', monospace, sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #94a3b8;
    backdrop-filter: blur(6px);
    white-space: nowrap;
    cursor: pointer;
  }

  .voice-pill.speaking {
    border-color: rgba(251, 191, 36, 0.75);
    color: #fcd34d;
    box-shadow: 0 0 14px rgba(251, 191, 36, 0.3);
  }

  .voice-pill.muted {
    opacity: 0.6;
    text-decoration: line-through;
  }

  .language-pill {
    position: absolute;
    top: 88px;
    right: 32px;
    z-index: 104;
    padding: 6px 14px;
    background: rgba(10, 15, 29, 0.82);
    border: 1px solid rgba(148, 163, 184, 0.45);
    border-radius: 9999px;
    font-family: 'JetBrains Mono', monospace, sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #94a3b8;
    backdrop-filter: blur(6px);
    white-space: nowrap;
    cursor: help;
  }

  .language-pill.detected {
    border-color: rgba(52, 211, 153, 0.7);
    color: #a7f3d0;
    box-shadow: 0 0 14px rgba(52, 211, 153, 0.28);
  }

  .language-pill.unknown {
    border-color: rgba(248, 113, 113, 0.55);
    color: #fca5a5;
  }

  .mcp-pill {
    position: absolute;
    top: 122px;
    right: 32px;
    z-index: 104;
    padding: 6px 14px;
    background: rgba(10, 15, 29, 0.82);
    border: 1px solid rgba(148, 163, 184, 0.45);
    border-radius: 9999px;
    font-family: 'JetBrains Mono', monospace, sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #94a3b8;
    backdrop-filter: blur(6px);
    white-space: nowrap;
    cursor: help;
  }

  .mcp-pill.ready {
    border-color: rgba(56, 189, 248, 0.7);
    color: #bae6fd;
    box-shadow: 0 0 14px rgba(56, 189, 248, 0.25);
  }

  .mcp-pill.locked {
    border-color: rgba(248, 113, 113, 0.55);
    color: #fca5a5;
  }

  .jury-pill {
    position: absolute;
    top: 156px;
    right: 32px;
    z-index: 104;
    padding: 6px 14px;
    background: rgba(10, 15, 29, 0.82);
    border: 1px solid rgba(148, 163, 184, 0.45);
    border-radius: 9999px;
    font-family: 'JetBrains Mono', monospace, sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #94a3b8;
    backdrop-filter: blur(6px);
    white-space: nowrap;
    cursor: help;
  }

  .jury-pill.ready {
    border-color: rgba(167, 139, 250, 0.7);
    color: #ddd6fe;
    box-shadow: 0 0 14px rgba(167, 139, 250, 0.25);
  }

  .jury-pill.thin {
    border-color: rgba(251, 191, 36, 0.6);
    color: #fcd34d;
  }

  .company-pill {
    position: absolute;
    top: 190px;
    right: 32px;
    z-index: 104;
    padding: 6px 14px;
    background: rgba(10, 15, 29, 0.82);
    border: 1px solid rgba(148, 163, 184, 0.45);
    border-radius: 9999px;
    font-family: 'JetBrains Mono', monospace, sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #94a3b8;
    backdrop-filter: blur(6px);
    white-space: nowrap;
    cursor: help;
  }

  .company-pill.ready {
    border-color: rgba(52, 211, 153, 0.65);
    color: #a7f3d0;
    box-shadow: 0 0 14px rgba(52, 211, 153, 0.22);
  }

  .memory-pill {
    position: absolute;
    top: 22px;
    right: 418px;
    z-index: 104;
    padding: 6px 14px;
    background: rgba(10, 15, 29, 0.82);
    border: 1px solid rgba(148, 163, 184, 0.45);
    border-radius: 9999px;
    font-family: 'JetBrains Mono', monospace, sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #94a3b8;
    backdrop-filter: blur(6px);
    white-space: nowrap;
    cursor: help;
  }

  .memory-pill.has-memory {
    border-color: rgba(129, 140, 248, 0.7);
    color: #c7d2fe;
    box-shadow: 0 0 14px rgba(129, 140, 248, 0.28);
  }

  .threshold-pill {
    position: absolute;
    top: 22px;
    right: 210px;
    z-index: 104;
    padding: 6px 14px;
    background: rgba(10, 15, 29, 0.82);
    border: 1px solid rgba(148, 163, 184, 0.45);
    border-radius: 9999px;
    font-family: 'JetBrains Mono', monospace, sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #94a3b8;
    backdrop-filter: blur(6px);
    white-space: nowrap;
    cursor: help;
  }

  .threshold-pill.measured {
    border-color: rgba(34, 197, 94, 0.65);
    color: #86efac;
    box-shadow: 0 0 14px rgba(34, 197, 94, 0.25);
  }

  .war-room-switch-pill {
    position: absolute;
    top: 22px;
    right: 32px;
    z-index: 105;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 16px;
    background: rgba(10, 15, 29, 0.88);
    border: 1px solid rgba(6, 182, 212, 0.55);
    border-radius: 9999px;
    cursor: pointer;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.7), 0 0 16px rgba(6, 182, 212, 0.25);
    backdrop-filter: blur(8px);
    transition: all 0.25s ease;
    font-family: 'JetBrains Mono', monospace, sans-serif;
  }

  .war-room-switch-pill:hover {
    background: rgba(15, 23, 42, 0.98);
    border-color: rgba(6, 182, 212, 0.95);
    box-shadow: 0 4px 25px rgba(6, 182, 212, 0.45), inset 0 0 10px rgba(6, 182, 212, 0.2);
    transform: translateY(-1px);
  }

  .war-icon {
    font-size: 14px;
    filter: drop-shadow(0 0 4px rgba(6, 182, 212, 0.6));
  }

  .war-text {
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.12em;
    color: #e2e8f0;
    text-shadow: 0 0 6px rgba(255, 255, 255, 0.3);
  }

  .war-tag {
    font-size: 8px;
    font-weight: 900;
    letter-spacing: 0.1em;
    padding: 2px 6px;
    border-radius: 4px;
    background: rgba(6, 182, 212, 0.25);
    color: #22d3ee;
    border: 1px solid rgba(6, 182, 212, 0.4);
  }
</style>
