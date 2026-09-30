<script lang="ts">
  import { onMount, onDestroy, afterUpdate } from 'svelte';
  import { get } from 'svelte/store';
  import {
    clientId, apiFetch, apiToken, setApiToken, currentApiToken,
    isAuthFailure, isProcessing, logs, taskStatus, telemetryEvents,
    armEngaged, sigintEngaged, recordEngaged, keyUnlocked, powerEngaged,
    eyeImage
  } from '../store';
  import { currentLang, t } from '../i18n';
  import { playClick, playRunning, playHalt, playToggle, setSoundEnabled } from '../lib/consoleAudio';
  import {
    health, sysTelemetry, uplinkState, throttleIdx, THROTTLE_DETENTS,
    ttsRate, TTS_DETENTS, startHealthPoll, stopHealthPoll
  } from '../lib/telemetry';
  import PillarFeed from './PillarFeed.svelte';
  import PinealEye from './PinealEye.svelte';
  import defaultEye from '../assets/eye.jpg';
  import AnalogGauge from './diesel/AnalogGauge.svelte';
  import ToggleSwitch from './diesel/ToggleSwitch.svelte';
  import KeyLock from './diesel/KeyLock.svelte';
  import EmergencyStop from './diesel/EmergencyStop.svelte';
  import SplitFlap from './diesel/SplitFlap.svelte';
  import LcdLogin from './diesel/LcdLogin.svelte';

  onMount(() => startHealthPoll());
  onDestroy(() => stopHealthPoll());

  // ==========================================
  // ANALOG ŞALTER & DÜĞME FONKSİYONLARI (USER CODE)
  // ==========================================
  function toggleArm() {
    armEngaged.update(v => {
      const next = !v;
      playToggle(next);
      logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'INFO', msg: next ? 'ARM: ENGAGED' : 'ARM: SAFE' }]);
      return next;
    });
  }

  function toggleSigint() {
    sigintEngaged.update(v => {
      const next = !v;
      playToggle(next);
      logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'INFO', msg: next ? 'SIGINT: OPEN' : 'SIGINT: CLOSED' }]);
      if (next && $isProcessing) {
        cancelAnalysis();
      }
      return next;
    });
  }

  function toggleRecord() {
    recordEngaged.update(v => {
      const next = !v;
      playToggle(next);
      logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'INFO', msg: next ? 'RECORD: ON' : 'RECORD: OFF' }]);
      return next;
    });
  }

  function toggleKey() {
    keyUnlocked.update(v => {
      const next = !v;
      playClick(next ? 280 : 120, 70);
      logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'INFO', msg: next ? 'KEY LOCK: UNLOCKED' : 'KEY LOCK: LOCKED' }]);
      return next;
    });
  }

  function togglePower() {
    powerEngaged.update(v => {
      const next = !v;
      playToggle(next);
      // POWER bildirimi RECORD'dan muaftır: bilinçli kesintinin kaydı kaybolmaz.
      logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: next ? 'INFO' : 'WARNING', msg: next ? 'POWER: UPLINK AÇILDI' : 'POWER: UPLINK KAPATILDI' }]);
      return next;
    });
  }

  function emergencyStop() {
    playHalt();
    const active = get(isProcessing) || get(taskStatus)?.status === 'processing';
    if (active) {
      logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'ERROR', msg: 'ACİL STOP: görev iptal emri verildi' }]);
      cancelAnalysis();
    } else {
      playClick(120, 90);
      logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'INFO', msg: 'ACİL STOP: hat boşta (iptal edilecek görev yok)' }]);
    }
  }

  // Düğmeler GERÇEK işlevlidir (süs değil):
  // THROTTLE → sağlık/telemetri ping aralığı · MIXTURE → Aspasia TTS hızı ·
  // PROP → konsol sesleri ana şalteri. Her detent loglanır.
  let throttleAngle = 45;
  let mixtureAngle = 120;
  let propAngle = 210;
  let soundOn = true;

  function cycleThrottle() {
    playClick(240, 30);
    throttleAngle = (throttleAngle + 45) % 360;
    throttleIdx.update(i => {
      const next = (i + 1) % THROTTLE_DETENTS.length;
      logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'INFO', msg: `THROTTLE: ping aralığı ${THROTTLE_DETENTS[next]} sn` }]);
      return next;
    });
  }

  function cycleMixture() {
    playClick(240, 30);
    mixtureAngle = (mixtureAngle + 45) % 360;
    const cur = TTS_DETENTS.indexOf(get(ttsRate));
    const next = TTS_DETENTS[(cur + 1) % TTS_DETENTS.length];
    ttsRate.set(next);
    logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'INFO', msg: `MIXTURE: Aspasia TTS hızı ${next}x` }]);
  }

  function cycleProp() {
    soundOn = !soundOn;
    setSoundEnabled(soundOn);
    propAngle = (propAngle + 45) % 360;
    if (soundOn) playClick(240, 30);
    logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'INFO', msg: soundOn ? 'PROP: konsol sesi AÇIK' : 'PROP: konsol sesi KAPALI' }]);
  }

  // Odometer (REC 00087)
  let odometer = 87;
  $: if ($logs.length > 0) {
    odometer = 87 + $logs.length;
  }

  // ==========================================
  // 13 AJAN LİSTESİ (KULLANICININ VERDİĞİ LİSTE)
  // ==========================================
  // <ROUTING-GENERATED-START do-not-edit>
  const agentList = [
    { id: "mirror_truth",          name: "MIRROR TRUTH",          color: "#10b981", primaryModel: "pineal-deep-reasoning",     backupModel: "(combo)",           via: "9router", capability: "strong_reasoning", glyph: "🪞" },
    { id: "autonomous_verifier",   name: "AUTONOMOUS VERIFIER",   color: "#a855f7", primaryModel: "pineal-verifier-panel",     backupModel: "(3 jüri: google+claude+open)",          via: "9router", capability: "extract+judgment", glyph: "⚖️" },
    { id: "human_behavior",        name: "HUMAN BEHAVIOR",        color: "#f59e0b", primaryModel: "pineal-general-reasoning",  backupModel: "(combo)",           via: "9router", capability: "strong_reasoning", glyph: "👤" },
    { id: "passion_mapper",        name: "PASSION MAPPER",        color: "#f59e0b", primaryModel: "pineal-fast-extract",       backupModel: "(combo)",           via: "9router", capability: "strong_reasoning", glyph: "✨" },
    { id: "friction_detector",     name: "FRICTION & BOUNDS",     color: "#ef4444", primaryModel: "pineal-general-reasoning",  backupModel: "(combo)",           via: "9router", capability: "strong_reasoning", glyph: "🛡️" },
    { id: "cognitive_profiler",    name: "COGNITIVE PROFILER",    color: "#06b6d4", primaryModel: "pineal-general-reasoning",  backupModel: "(combo)",           via: "9router", capability: "strong_reasoning", glyph: "🧠" },
    { id: "resonance_calc",        name: "RESONANCE CALCULATOR",  color: "#3b82f6", primaryModel: "local-numpy",               backupModel: "—",                 via: "local",   capability: "calc",             glyph: "📐" },
    { id: "pattern_interrupt",     name: "PATTERN INTERRUPT",     color: "#dc2626", primaryModel: "pineal-fast-extract",       backupModel: "(combo)",           via: "9router", capability: "strong_reasoning", glyph: "⚡" },
    { id: "resonance_synthesizer", name: "AUTHENTIC BRIDGE",      color: "#10b981", primaryModel: "pineal-deep-reasoning",     backupModel: "(combo)",           via: "9router", capability: "synthesis",        glyph: "🌿" },
    { id: "vision_analyzer",       name: "VISION ANALYZER",       color: "#38bdf8", primaryModel: "pineal-vision",             backupModel: "(combo)",           via: "9router", capability: "vision",           glyph: "👁️" },
    { id: "osint_investigator",    name: "OSINT INVESTIGATOR",    color: "#f97316", primaryModel: "pineal-osint-pipeline",     backupModel: "(pipeline)",        via: "9router", capability: "osint_synthesis",  glyph: "🌐" },
    { id: "authenticity_auditor",  name: "AUTHENTICITY AUDITOR",  color: "#eab308", primaryModel: "pineal-vision",             backupModel: "(forensic)",        via: "9router", capability: "vision+verify",   glyph: "🔍" },
    { id: "depth_analyst",         name: "DEPTH ANALYST",         color: "#8b5cf6", primaryModel: "pineal-deep-reasoning",     backupModel: "(combo)",           via: "9router", capability: "strong_reasoning", glyph: "💎" },
  ];

// <ROUTING-GENERATED-END>

  // --- İKİ DİLLİ ETİKETLER (EN gravür + TR alt satır) ---
  // Ajan TR adları ROUTING bloğunun dışında tutulur (üretilmiş blok korunur).
  const agentTr: Record<string, string> = {
    mirror_truth: 'HAKİKAT AYNASI',
    autonomous_verifier: 'OTONOM DOĞRULAYICI',
    human_behavior: 'İNSAN DAVRANIŞI',
    passion_mapper: 'TUTKU HARİTASI',
    friction_detector: 'SÜRTÜNME & SINIRLAR',
    cognitive_profiler: 'BİLİŞSEL PROFİL',
    resonance_calc: 'REZONANS HESABI',
    pattern_interrupt: 'ÖRÜNTÜ KESİCİ',
    resonance_synthesizer: 'SAHİCİ KÖPRÜ',
    vision_analyzer: 'GÖRÜ ANALİZİ',
    osint_investigator: 'OSINT ARAŞTIRMACI',
    authenticity_auditor: 'ÖZGÜNLÜK DENETÇİSİ',
    depth_analyst: 'DERİNLİK ANALİZİ',
  };
  const tabTr: Record<string, string> = {
    ASPASIA: 'ASPASİA', VISION: 'GÖRÜ', OSINT: 'OSINT',
    FRICTION: 'SÜRTÜNME', VERIFY: 'DOĞRULA',
  };
  function trStatus(s: string): string {
    const m: Record<string, string> = {
      ready: 'HAZIR', degraded: 'KISMÎ', failed: 'HATALI',
      unreachable: 'ERİŞİLEMEZ', unknown: 'BİLİNMEYEN',
      processing: 'İŞLENİYOR', completed: 'TAMAMLANDI',
    };
    return m[(s || '').toLowerCase()] || (s || '').toUpperCase();
  }

  // ==========================================
  // STATE & TELEMETRY
  // ==========================================
  export let targetUrl = "";
  export let userRituals = "";
  export let userPlaylist = "";
  export let userEnvies = "";
  let runs: Record<string, any> = {};
  let currentAgent = "";
  let taskState = "IDLE";
  let taskId = "";
  let overallConfidence = 0;
  let haltedReason: string | null = null;
  let holisticProfile: any = null;
  let followerAudit: any = null;
  let timingForensics: any = null;
  let depthReport: any = null;
  let visualEvidence: any = null;
  let shadowProfile: any = null;
  let osintFootprint: any = null;
  let resonanceCalc: any = null;

  // Active Tab: ASPASIA, VISION, OSINT, FRICTION, VERIFY
  let activeTab = 'ASPASIA';

  // Active Forensic Drawer / Modal: FOLLOWER, TIMING, DEPTH, VISUAL, SHADOW, OSINT,
  // RESONANCE, PILLARS
  let activeForensicModal: string | null = null;

  // [BOSS-5] Deterministik motor çıktıları: 7-sütun raporları + psikodinamik
  // derinlik. Bu alanlar backend'de hesaplanıyordu ama WS payload'ına hiç
  // girmiyordu; artık snapshot_update/result çerçeveleriyle geliyor.
  let frequencyMap: any = null;
  let seismosEvents: any = null;
  let voidMap: any = null;
  let strataMap: any = null;
  let gravityMap: any = null;
  let pulseMap: any = null;
  let keyMatrix: any = null;
  let psychodynamicDepth: any = null;

  function depthChannels(depth: any): Array<{ name: string; ch: any }> {
    return Object.entries(depth?.channels || {}).map(([name, ch]) => ({ name, ch: ch as any }));
  }

  function toggleForensic(name: string) {
    playClick(350, 40);
    activeForensicModal = activeForensicModal === name ? null : name;
  }

  // Audio reactivity
  let prevAgent = '';
  let prevState = '';

  $: {
    if ($taskStatus?.current_agent && $taskStatus.current_agent !== prevAgent && $taskStatus.status === 'processing') {
      playRunning();
      prevAgent = $taskStatus.current_agent;
    }
    if ($taskStatus?.status && $taskStatus.status !== prevState) {
      if (String($taskStatus.status).startsWith('halted') || $taskStatus.status === 'failed') playHalt();
      prevState = $taskStatus.status;
    }
  }

  $: {
    if ($taskStatus) {
      if ($taskStatus.task_id) taskId = $taskStatus.task_id;
      if ($taskStatus.status) taskState = $taskStatus.status;
      if ($taskStatus.halted_reason !== undefined) haltedReason = $taskStatus.halted_reason;
      if ($taskStatus.current_agent) currentAgent = $taskStatus.current_agent;
      if ($taskStatus.runs) runs = $taskStatus.runs;
      if ($taskStatus.holistic_profile) holisticProfile = $taskStatus.holistic_profile;
      if ($taskStatus.follower_audit) followerAudit = $taskStatus.follower_audit;
      if ($taskStatus.timing_forensics) timingForensics = $taskStatus.timing_forensics;
      if ($taskStatus.depth_report) depthReport = $taskStatus.depth_report;
      if ($taskStatus.visual_evidence) visualEvidence = $taskStatus.visual_evidence;
      if ($taskStatus.shadow_profile) shadowProfile = $taskStatus.shadow_profile;
      if ($taskStatus.osint_footprint) osintFootprint = $taskStatus.osint_footprint;
      // [BOSS-5] 7-sütun + psikodinamik derinlik (backend artık taşıyor).
      if ($taskStatus.frequency_map) frequencyMap = $taskStatus.frequency_map;
      if ($taskStatus.seismos_events) seismosEvents = $taskStatus.seismos_events;
      if ($taskStatus.void_map) voidMap = $taskStatus.void_map;
      if ($taskStatus.strata_map) strataMap = $taskStatus.strata_map;
      if ($taskStatus.gravity_map) gravityMap = $taskStatus.gravity_map;
      if ($taskStatus.pulse_map) pulseMap = $taskStatus.pulse_map;
      if ($taskStatus.key_matrix) keyMatrix = $taskStatus.key_matrix;
      if ($taskStatus.psychodynamic_depth) psychodynamicDepth = $taskStatus.psychodynamic_depth;
      // resonance_calc sonucu runs.output_summary altında taşınır (gerçek anahtarlar).
      resonanceCalc = $taskStatus.runs?.resonance_calc?.output_summary || null;
      overallConfidence = $taskStatus.holistic_profile?.overall_confidence ?? 0;
    }
  }

  // RISK kadranı: bütüncül profil varsa (1 - güven), yoksa park eder (null).
  // Sahte risk üretilmez: ölçüm yoksa ibre beklemede durur.
  $: riskVal = holisticProfile ? Math.min(1, Math.max(0, 1 - (overallConfidence ?? 0))) : null;
  $: riskLabel = riskVal === null ? 'BEKLEMEDE' : riskVal < 0.33 ? 'DÜŞÜK' : riskVal < 0.66 ? 'ORTA' : 'YÜKSEK';

  // ==========================================
  // ASPASIA CHAT & SPEECH
  // ==========================================
  // [BOSS-10] Sohbet kurgu mesajlarla acilmaz: eskiden uydurma bir senaryo
  // (4 mesaj) gercek konusma gibi duruyordu. Repo doktrini "sahte veri uretme"
  // oldugu icin baslangicta yalniz tek bir sistem satiri var.
  let messages: {sender: string, text: string, time: string}[] = [
    { sender: 'SİSTEM', text: 'ASPASIA hazır. Komut yazın (örn. "hedef @kullanici analiz et") — geçmiş mesajlar yalnızca gerçek yanıtlardan oluşur.', time: '' }
  ];
  let inputMessage = "";
  let chatContainer: HTMLElement;
  let isSending = false;
  let attachedImage: string | null = null;
  let fileInput: HTMLInputElement;

  function handleImageUpload(e: Event) {
    const target = e.target as HTMLInputElement;
    if (target.files && target.files[0]) {
      const reader = new FileReader();
      reader.onload = (ev) => { attachedImage = ev.target?.result as string; };
      reader.readAsDataURL(target.files[0]);
    }
  }

  async function sendMessage() {
    if ((!inputMessage.trim() && !attachedImage) || isSending) return;
    const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const displayMsg = attachedImage ? `[GÖRSEL] ${inputMessage}` : inputMessage;
    messages = [...messages, { sender: 'SİZ', text: displayMsg, time: nowTime }];

    let currentInput = inputMessage;
    let currentImage = attachedImage;
    inputMessage = "";
    attachedImage = null;
    isSending = true;
    playClick(280, 50);

    try {
      const activeAgentId = activeTab;

      // [UI-BRIDGE] ASPASIA serbest metni ÖNCE komut kanalına gider
      // (doğal dil niyet -> yapılandırılmış komut -> GERÇEK görev akışı;
      // ikinci bir orchestrator yok: /api/aspasia/command tek dispatch
      // kanalından /api/initiate akışına bağlanır). Kabul edilen komut
      // (accepted && task_id) görev kartına bağlanır. Reddedilen/boş
      // yanıtta aşağıdaki chat fallback'ine geçilir — mesaj kaybi yok.
      if (activeAgentId === 'ASPASIA' && currentInput.trim()) {
        try {
          const cmdRes = await apiFetch(`/api/aspasia/command`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ client_id: $clientId, user_message: currentInput })
          });
          const cmd = cmdRes.ok ? await cmdRes.json() : null;
          if (cmd && cmd.accepted && cmd.task_id) {
            taskStatus.update(s => ({ ...s, task_id: cmd.task_id, status: 'processing' }));
            const boundTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            messages = [...messages, {
              sender: 'ASPASIA',
              text: `Görev başlatıldı: ${cmd.task_id} [${cmd.intent || 'run_profile_analysis'}]`,
              time: boundTime
            }];
            logs.update(l => [...l, { ts: boundTime, level: 'INFO', msg: `ASPASIA KOMUT kabul edildi -> görev ${cmd.task_id}` }]);
            isSending = false;
            return;
          }
        } catch (_cmdErr) {
          /* komut kanalı boşta/hatalı -> chat fallback (mesaj kaybi yok) */
        }
      }

      // [UI-BRIDGE] Chat ağızları: tüm sekmeler aynı tek /api/aspasia/chat
      // ağzını kullanır; sekme yalnız bağlam değiştirir.
      const chatUrl = activeAgentId === 'ASPASIA' ? '/api/aspasia/chat' : '/api/aspasia/chat';
      const payload: any = { client_id: $clientId, user_message: currentInput };
      if (currentImage) payload.image_data = currentImage;
      const res = await apiFetch(chatUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error(isAuthFailure(res) ? "Yetki hatası (PINEAL_TOKEN)" : "Ağ geçidi yanıt vermedi");
      const data = await res.json();
      const reply = data.message || data.error?.message || "Yanıt alındı.";
      const resTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      messages = [...messages, { sender: 'ASPASIA', text: reply, time: resTime }];

      // Ses + yazı birlikte (Kullanıcının verdiği TTS kodu)
      if (typeof window !== 'undefined' && window.speechSynthesis) {
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(reply);
        u.lang = $currentLang === 'tr' ? 'tr-TR' : 'en-US';
        u.rate = get(ttsRate);
        window.speechSynthesis.speak(u);
      }
    } catch (error: any) {
      messages = [...messages, { sender: 'SİSTEM', text: `HATA: ${error.message}`, time: nowTime }];
    } finally {
      isSending = false;
    }
  }

  function handleKeydown(e: KeyboardEvent) { if (e.key === 'Enter') sendMessage(); }

  export async function triggerAnalysis() {
    if (!targetUrl) return;
    // VAULT interlock: anahtar açılmadan ateşleme yok.
    if (!$keyUnlocked) {
      playHalt();
      logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'ERROR', msg: 'ATEŞLEME REDDEDİLDİ: VAULT anahtarı kilitli — önce anahtarı çevirin' }]);
      return;
    }
    if (!$armEngaged) {
      armEngaged.set(true);
      logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'INFO', msg: 'SİSTEM KİLİDİ AÇILDI: ARM otonom aktif edildi' }]);
    }
    isProcessing.set(true);
    playRunning();
    try {
      const res = await apiFetch(`/api/initiate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: $clientId,
          url: targetUrl,
          scraper_type: "cross",
          rituals: userRituals,
          playlist: userPlaylist,
          envies: userEnvies,
        })
      });
      if (!res.ok) throw new Error(isAuthFailure(res) ? "Yetki hatası (PINEAL_TOKEN)" : "API hatası: " + res.statusText);
      const started = await res.json();
      if (started.task_id) taskStatus.update(s => ({ ...s, task_id: started.task_id, status: 'processing' }));
      logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: "INFO", msg: `ANALİZ EMRİ VERİLDİ: ${targetUrl}` }]);
    } catch (e: any) {
      logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: "ERROR", msg: `HATA: ${e.message}` }]);
      isProcessing.set(false);
    }
  }

  async function cancelAnalysis() {
    const activeTaskId = $taskStatus?.task_id;
    if (!activeTaskId) return;
    playHalt();
    await apiFetch(`/api/tasks/${activeTaskId}/cancel?client_id=${$clientId}`, { method: 'POST' });
  }

  afterUpdate(() => {
    if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
  });
</script>

<div class="observatory">
  <!-- ==================== ÜST PLAKA ==================== -->
  <div class="masthead">
    <span class="plaque-screw ps-tl"></span>
    <span class="plaque-screw ps-tr"></span>
    <span class="plaque-screw ps-bl"></span>
    <span class="plaque-screw ps-br"></span>
    <div class="mast-left">
      <div class="mast-title font-cinzel">ATLAS EPİFİZ PINEAL OBSERVATORY <span class="mast-ver">v10</span></div>
      <div class="mast-sub">PINEAL-HERETIC · 360° BÜTÜNCÜL İNSAN TANIMA VE REZONANS İSTASYONU</div>
    </div>
    <div class="mast-right">
      <div class="mast-locks">
        <div class="lock-item">
          <span class="lock-led {$keyUnlocked ? 'led-green' : 'led-red'}"></span>
          <span class="lock-name">LOCK</span>
          <span class="lock-state">{$keyUnlocked ? 'AÇIK' : 'KİLİTLİ'}</span>
        </div>
        <div class="lock-item">
          <span class="lock-led {$apiToken ? 'led-green' : 'led-dim'}"></span>
          <span class="lock-name">SECURE</span>
          <span class="lock-state">{$apiToken ? 'TOKEN' : 'YOK'}</span>
        </div>
        <div class="lock-item">
          <span class="lock-led {$recordEngaged ? 'led-green' : 'led-dim'}"></span>
          <span class="lock-name">ARCHIVE</span>
          <span class="lock-state">{$recordEngaged ? 'REC' : 'OFF'}</span>
        </div>
      </div>
      <div class="sysstate">
        <span class="sysstate-label">SYSTEM STATE<br /><span class="tr-micro">SİSTEM DURUMU</span></span>
        <span class="sysstate-bars">
          <span class="sysbar {($uplinkState === 'ONLINE') ? 'lit' : ''}"></span>
          <span class="sysbar {($uplinkState === 'ONLINE' && $health.ok) ? 'lit' : ''}"></span>
          <span class="sysbar {($uplinkState === 'ONLINE' && $health.ok && $sysTelemetry.ok) ? 'lit' : ''}"></span>
        </span>
        <span class="sysstate-text">{$uplinkState === 'ONLINE' ? ($health.ok ? 'SYNC' : 'KISMÎ') : 'OFFLINE'}</span>
      </div>
    </div>
  </div>

  <!-- ==================== GÖSTERGE SIRASI (5 KADRAN) ==================== -->
  <!-- İbreler /health + /api/telemetry ölçümlerine bağlıdır; veri yoksa park eder. -->
  <div class="gauge-row">
    <LcdLogin />
    <div class="dials-cluster">
      <AnalogGauge
        label="LLM GATEWAY"
        tr="LLM GEÇİDİ"
        tone="red"
        value={$sysTelemetry.ok ? ($sysTelemetry.gateway ? 82 : 12) : null}
        sub={$sysTelemetry.ok ? ($sysTelemetry.gateway ? `CANLI · $${$sysTelemetry.spendUsd.toFixed(2)}` : 'BEKLEMEDE (STANDBY)') : '—'}
      />
      <AnalogGauge
        label="SCRAPER NODE"
        tr="KAZIYICI DÜĞÜM"
        tone="gold"
        value={$sysTelemetry.ok ? (($sysTelemetry.scraper || $sysTelemetry.browser) ? 82 : 12) : null}
        sub={$sysTelemetry.ok ? (($sysTelemetry.scraper || $sysTelemetry.browser) ? 'HAZIR (READY)' : 'TARAYICI YOK (NO BROWSER)') : '—'}
      />
      <AnalogGauge
        label="CORE ENGINE"
        tr="ÇEKİRDEK MOTOR"
        tone="green"
        value={$health.ok ? $health.integrityPct : null}
        sub={$health.ok ? `${$health.integrityPct}% · ${$health.status.toUpperCase()} (${trStatus($health.status)})` : '—'}
      />
      <AnalogGauge
        label="PINEAL STATUS"
        tr="PİNEAL DURUMU"
        tone="green"
        value={$uplinkState === 'ONLINE' ? 82 : 12}
        sub="{$uplinkState}{$recordEngaged ? ' · REC' : ''}"
      />
      <AnalogGauge
        label="SEFER / LEDGER"
        tr="GÖREV DEFTERİ"
        tone="gold"
        value={$sysTelemetry.ok ? ($sysTelemetry.spendCapUsd > 0 ? Math.min(100, ($sysTelemetry.spendUsd / $sysTelemetry.spendCapUsd) * 100) : 82) : null}
        sub={$sysTelemetry.ok ? `$${$sysTelemetry.spendUsd.toFixed(4)} HARCAMA` : '—'}
      />
    </div>
    <div class="signals-block">
      <div class="signals-label">SIGNALS<span class="tr-micro">SİNYALLER</span></div>
      <div class="odometer-bezel">
        <div class="odometer-digits">
          {#each String(odometer).padStart(5, '0').split('') as digit}
            <span class="odo-digit">{digit}</span>
          {/each}
        </div>
      </div>
      <div class="signals-sub">REC · KAYIT SAYACI</div>
    </div>
    <div class="flaps-col">
      <SplitFlap
        title="PINEAL · STATUS"
        titleTr="PİNEAL DURUM PANOSU"
        rows={[
          { k: 'LATENCY', ktr: 'GECİKME', v: $health.ok && $health.latencyMs !== null ? `${$health.latencyMs}ms` : '—' },
          { k: 'INTEGRITY', ktr: 'BÜTÜNLÜK', v: $health.ok ? `${$health.integrityPct}%` : '—' },
          { k: 'HAT', ktr: 'LINE', v: $uplinkState },
        ]}
        foot={$health.ok ? `SYS ${$health.status.toUpperCase()} · NOMINAL` : 'SYS UNREACHABLE'}
        footTr={$health.ok ? `SİS. ${trStatus($health.status)} · NOMİNAL` : 'SİS. ERİŞİLEMEZ'}
        online={$uplinkState === 'ONLINE' && $health.ok}
      />
      <SplitFlap
        title="SEFER · LEDGER"
        titleTr="GÖREV DEFTERİ"
        rows={[
          { k: 'HARCAMA', ktr: 'SPEND', v: $sysTelemetry.ok ? `$${$sysTelemetry.spendUsd.toFixed(4)}` : '—' },
          { k: 'TAVAN', ktr: 'CAP', v: $sysTelemetry.ok ? ($sysTelemetry.spendCapUsd > 0 ? `$${$sysTelemetry.spendCapUsd.toFixed(2)}` : 'YOK (NONE)') : '—' },
          { k: 'REZERV', ktr: 'RESV', v: $sysTelemetry.ok ? String($sysTelemetry.activeReservations) : '—' },
          { k: 'GÖREV', ktr: 'RUNS', v: $sysTelemetry.ok ? String($sysTelemetry.taskRuns) : '—' },
        ]}
        foot="BÜTÇE · QUOTA"
        footTr={$sysTelemetry.ok ? 'CANLI AKIŞ' : 'VERİ YOK'}
        online={$sysTelemetry.ok}
      />
    </div>
  </div>

  <!-- ==================== ANA GÖVDE (3 SÜTUN) ==================== -->
  <div class="obs-grid">

    <!-- SOL: KAYNAK + ALIM + KASA -->
    <aside class="col-left">
      <section class="panel">
        <div class="panel-title">
          <span>SOURCE FIELD <span class="live-dot"></span> <span class="title-ghost">INPUT ONLINE</span></span>
          <span class="panel-tr">KAYNAK ALANI</span>
        </div>
        <ul class="source-list">
          <li>
            <span class="src-led {$sysTelemetry.scraper ? 'on' : 'off'}"></span>
            <span class="src-name">INSTAGRAM GHOST SCRAPER</span>
            <span class="src-state">{$sysTelemetry.scraper ? 'AKTİF' : 'PASİF'}</span>
          </li>
          <li>
            <span class="src-led {$sysTelemetry.browser ? 'on' : 'off'}"></span>
            <span class="src-name">CANLI TARAYICI</span>
            <span class="src-state">{$sysTelemetry.browser ? 'AKTİF' : 'PASİF'}</span>
          </li>
          <li>
            <span class="src-led {$health.ok ? 'on' : 'off'}"></span>
            <span class="src-name">WEB / ARCHIVE</span>
            <span class="src-state">{$health.ok ? 'HAZIR' : 'YOK'}</span>
          </li>
          <li>
            <span class="src-led {$sysTelemetry.gateway ? 'on' : 'off'}"></span>
            <span class="src-name">OPEN DATA</span>
            <span class="src-state">{$sysTelemetry.gateway ? 'AÇIK' : 'KAPALI'}</span>
          </li>
          <li>
            <span class="src-led {(targetUrl.trim() || inputMessage.trim()) ? 'on' : 'off'}"></span>
            <span class="src-name">MANUEL GİRİŞ</span>
            <span class="src-state">{(targetUrl.trim() || inputMessage.trim()) ? 'GİRİLDİ' : 'BOŞ'}</span>
          </li>
        </ul>
        <div class="source-stats">
          <div class="stat-box">
            <span class="stat-num">{odometer}</span>
            <span class="stat-lbl">SİNYALLER</span>
          </div>
          <div class="stat-box">
            <span class="stat-num">{[$sysTelemetry.scraper, $sysTelemetry.browser, $health.ok, $sysTelemetry.gateway].filter(Boolean).length}</span>
            <span class="stat-lbl">KAYNAK</span>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">
          <span>ACQUISITION CONTROLS</span>
          <span class="panel-tr">ALIM KONTROLLERİ</span>
        </div>
        <div class="switches-grid">
          <ToggleSwitch label="POWER" tr="GÜÇ" engaged={$powerEngaged} led="green" onToggle={togglePower} />
          <ToggleSwitch label="ARM" tr="KURMA" engaged={$armEngaged} led="green" onToggle={toggleArm} />
          <ToggleSwitch label="RECORD" tr="KAYIT" engaged={$recordEngaged} led="green" onToggle={toggleRecord} />
          <ToggleSwitch label="SIGINT" tr="SİNYAL" engaged={$sigintEngaged} led="red" onToggle={toggleSigint} />
        </div>
        <div class="estop-wrap">
          <EmergencyStop armed={$isProcessing || taskState === 'processing'} onPress={emergencyStop} />
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">
          <span>PINEAL TOKEN</span>
          <span class="panel-tr">KASA & KUMANDA</span>
        </div>
        <div class="token-plaque">
          <div class="plaque-screw top-left"></div>
          <div class="plaque-screw top-right"></div>
          <div class="plaque-screw btm-left"></div>
          <div class="plaque-screw btm-right"></div>
          <div class="plaque-header">PINEAL TOKEN</div>
          <div class="plaque-tr">PİNEAL ANAHTARI</div>
          <div class="plaque-code">{$apiToken ? 'KASA · AÇIK' : 'KASA · KİLİTLİ'}</div>
          <div class="plaque-sub">{$clientId}</div>
        </div>
        <div class="keylock-wrap">
          <div class="module-title">VAULT KEY LOCK<span class="module-tr">KASA ANAHTAR KİLİDİ</span></div>
          <KeyLock unlocked={$keyUnlocked} onToggle={toggleKey} />
          <span class="knob-detent">{$keyUnlocked ? 'AÇIK · ateş serbest' : 'KİLİTLİ'}</span>
        </div>
        <div class="knobs-row">
          <div class="knob-col">
            <button class="knurled-knob" aria-label="Throttle: ping aralığı" style="transform: rotate({throttleAngle}deg);" on:click={cycleThrottle}>
              <div class="knob-notch"></div>
            </button>
            <span class="knob-label">THROTTLE</span>
            <span class="knob-tr">GAZ</span>
            <span class="knob-detent">{THROTTLE_DETENTS[$throttleIdx]} sn</span>
          </div>
          <div class="knob-col">
            <button class="knurled-knob" aria-label="Mixture: TTS hızı" style="transform: rotate({mixtureAngle}deg);" on:click={cycleMixture}>
              <div class="knob-notch"></div>
            </button>
            <span class="knob-label">MIXTURE</span>
            <span class="knob-tr">KARIŞIM</span>
            <span class="knob-detent">{$ttsRate}x</span>
          </div>
          <div class="knob-col">
            <button class="knurled-knob" aria-label="Prop: konsol sesi" style="transform: rotate({propAngle}deg);" on:click={cycleProp}>
              <div class="knob-notch"></div>
            </button>
            <span class="knob-label">PROP</span>
            <span class="knob-tr">PERVANE</span>
            <span class="knob-detent">{soundOn ? 'SES' : 'SESSİZ'}</span>
          </div>
        </div>
      </section>
    </aside>

    <!-- ORTA: GÖZ + AJAN GÜVERTESİ -->
    <main class="col-center">
      <section class="panel eye-panel">
        <div class="eye-stage">
          <div class="eye-orbit" aria-hidden="true"></div>
          <span class="eye-led" style="--a: 0deg; --d: 0s;"></span>
          <span class="eye-led" style="--a: 60deg; --d: 0.4s;"></span>
          <span class="eye-led" style="--a: 120deg; --d: 0.8s;"></span>
          <span class="eye-led" style="--a: 180deg; --d: 1.2s;"></span>
          <span class="eye-led" style="--a: 240deg; --d: 1.6s;"></span>
          <span class="eye-led" style="--a: 300deg; --d: 2s;"></span>
          <div class="eye-scale">
            <PinealEye size={300} scanning={$isProcessing || taskState === 'processing'} customImage={$eyeImage ?? defaultEye} interactive={true} />
          </div>
        </div>
        <div class="eye-status">
          <span class="dot-led {($isProcessing || taskState === 'processing') ? 'dot-green pulse' : 'dot-amber'}"></span>
          {#if ($isProcessing || taskState === 'processing')}
            <span><b>TARAMA AKTİF:</b> {currentAgent || 'ajan başlatılıyor...'}</span>
          {:else if taskState === 'completed'}
            <span><b>TAMAMLANDI:</b> kanıtlar doğrulandı</span>
          {:else if taskState && taskState.startsWith('halted')}
            <span><b>DURDURULDU:</b> {haltedReason || taskState}</span>
          {:else}
            <span><b>GÖZETİM HAZIR:</b> hedef bekleniyor</span>
          {/if}
        </div>
      </section>

      <section class="panel deck-panel">
        <div class="panel-title">
          <span>AGENT DECK · ASPASIA OBSERVER</span>
          <span class="panel-tr">AJAN GÜVERTESİ</span>
        </div>
        <div class="monitor-tabs-bar">
          {#each ['ASPASIA', 'VISION', 'OSINT', 'FRICTION', 'VERIFY'] as tab}
            <button
              class="monitor-tab-btn {activeTab === tab ? 'tab-selected' : ''}"
              on:click={() => { activeTab = tab; playClick(300, 30); }}
            >
              {tab}<span class="tab-tr">{tabTr[tab]}</span>
            </button>
          {/each}
        </div>
        <div class="quick-target-strip">
          <input
            type="text"
            bind:value={targetUrl}
            placeholder="Hedef kullanıcı adı / URL (@kullanici) · Target username / URL..."
            disabled={$isProcessing}
          />
          <button
            class="launch-btn {$armEngaged ? 'btn-armed' : 'btn-unarmed'}"
            on:click={triggerAnalysis}
            disabled={$isProcessing || !targetUrl}
          >
            {$isProcessing ? 'İŞLENİYOR...' : 'YAKALA (CAPTURE)'}
          </button>
        </div>
        <div class="active-route-subbar">
          <div class="route-text">
            {#if ($isProcessing || taskState === 'processing') && currentAgent}
              <b style="color: var(--gold);">AKTİF (ACTIVE):</b> {currentAgent}
              &bull; <b style="color: var(--gold);">MODEL:</b> {runs[currentAgent]?.model || agentList.find(a => a.id === currentAgent)?.primaryModel || 'auto'}
              &bull; <b style="color: var(--gold);">YOL (VIA):</b> {runs[currentAgent]?.via || agentList.find(a => a.id === currentAgent)?.via || 'unified-router'}
            {:else if $isProcessing || taskState === 'processing'}
              <b style="color: var(--gold);">DURUM (STATUS):</b> İŞLENİYOR (Ajan başlatılıyor...)
            {:else if taskState === 'completed'}
              <b style="color: #22c55e;">DURUM (STATUS):</b> TAMAMLANDI (Tüm kanıtlar doğrulandı)
            {:else if taskState && taskState.startsWith('halted')}
              <b style="color: #ef4444;">DURUM (STATUS):</b> DURDURULDU ({haltedReason || taskState})
            {:else}
              <b style="color: var(--gold);">DURUM (STATUS):</b> BEKLEMEDE (Sistem Hazır &bull; Hedef Bekleniyor)
            {/if}
          </div>
          <div class="route-dots">
            <span class="dot-led {($isProcessing || taskState === 'processing') ? 'dot-green pulse' : 'dot-amber'}"></span>
          </div>
        </div>
      </section>
    </main>

    <!-- SAĞ: İZ + RİSK + AJAN RAFI -->
    <aside class="col-right">
      <section class="panel">
        <div class="panel-title">
          <span>TRACE FIELD</span>
          <span class="panel-tr">İZ ALANI</span>
        </div>
        <div class="trace-big">
          <span class="trace-num">{odometer}</span>
          <span class="trace-unit">SIGNALS</span>
        </div>
        <div class="trace-rows">
          <div class="trace-row"><span>relation clusters</span><b>{osintFootprint?.associated_platforms?.length ?? '—'}</b></div>
          <div class="trace-row"><span>confidence</span><b>{holisticProfile ? `%${(overallConfidence * 100).toFixed(0)}` : '—'}</b></div>
          <div class="trace-row"><span>sefer / runs</span><b>{$sysTelemetry.ok ? $sysTelemetry.taskRuns : '—'}</b></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">
          <span>RISK · BELİRSİZLİK</span>
          <span class="panel-tr">RİSK GÖSTERGESİ</span>
        </div>
        <div class="risk-dial" role="img" aria-label="Risk gostergesi">
          <div class="risk-arc"></div>
          <div class="risk-needle" style="transform: translateX(-50%) rotate({riskVal === null ? -80 : -80 + riskVal * 160}deg);"></div>
          <div class="risk-hub"></div>
        </div>
        <div class="risk-text">risk index: <b>{riskVal === null ? '—' : riskVal.toFixed(2)}</b> · {riskLabel === 'BEKLEMEDE' ? 'ölçüm bekleniyor' : 'belirsizlik: ' + riskLabel.toLowerCase()}</div>
      </section>
      <div class="agent-cards-stack">
        {#each agentList as agent, i}
          {@const run = runs[agent.id]}<!-- [BOSS-10] 'depth_forensics' ölü anahtardı:
             backend koşu kaydını 'depth_analyst' adıyla yazar; ölü anahtar
             yüzünden derinlik ajanı HER durumda statik etiketi gösteriyordu. -->
          {@const isCompleted = run?.status === 'completed' || run?.status === 'completed_no_decision'}
          {@const isRunning = currentAgent === agent.id && ($isProcessing || taskState === 'processing')}
          {@const isHalted = run?.status === 'halted' || run?.status === 'failed'}
          {@const liveModel = run?.model || agent.primaryModel}
          {@const liveVia = run?.via || agent.via}
          <!-- W4: kanonik çağrı bağlayıcısı — run.output_summary._provenance
               üzerinden call_id okunur (LLM'siz/uydurma satır üretilmez). -->
          {@const provCallId = (run && run.output_summary && run.output_summary._provenance) ? (run.output_summary._provenance.call_id || '') : ''}

          <div class="agent-instrument-card {isRunning ? 'card-running' : isHalted ? 'card-halted' : isCompleted ? 'card-done' : 'card-wait'}">
            <div class="card-top-line">
              <!-- Antik Madalyon / İkon -->
              <div class="agent-medal {isRunning ? 'medal-pulse-red' : ''}">
                <span class="medal-symbol">{agent.glyph || '⚙️'}</span>
              </div>

      <section class="panel rack-panel">
        <div class="panel-title">
          <span>AGENT RACK</span>
          <span class="panel-tr">AJAN RAFI · 13</span>
        </div>
        <div class="agent-rows">
          {#each agentList as agent, i}
            {@const run = runs[agent.id]}
            {@const isCompleted = run?.status === 'completed'}
            {@const isRunning = currentAgent === agent.id && ($isProcessing || taskState === 'processing')}
            {@const isHalted = run?.status === 'halted' || run?.status === 'failed'}
            {@const liveModel = run?.model || agent.primaryModel}
            {@const liveVia = run?.via || agent.via}
            <div class="agent-row {isRunning ? 'row-running' : isHalted ? 'row-halted' : isCompleted ? 'row-done' : ''}" title="{liveModel} · {liveVia}">
              <span class="agent-idx">{String(i + 1).padStart(2, '0')}</span>
              <span class="agent-led {isRunning ? 'led-green pulse' : isHalted ? 'led-red' : isCompleted ? 'led-teal' : 'led-dim'}"></span>
              <span class="agent-name">{agent.name}<span class="agent-tr">{agentTr[agent.id] || ''}</span></span>
              <span class="pill {isRunning ? 'pill-active' : isHalted ? 'pill-verify' : isCompleted ? 'pill-report' : 'pill-wait'}">{isRunning ? 'ACTIVE' : isHalted ? 'VERIFY' : isCompleted ? 'REPORT' : 'WAIT'}</span>
            </div>
          {/each}
        </div>
      </section>
    </aside>
  </div>

  <!-- ==================== ALT: KOMUTA + 7 SÜTUN ==================== -->
  <div class="obs-bottom">
    <section class="panel command-deck">
      <div class="panel-title">
        <span>ASPASIA OBSERVER · COMMAND DECK</span>
        <span class="panel-tr">KOMUTA GÜVERTESİ · {isSending ? 'YAZIYOR' : 'CANLI'}</span>
      </div>
      <div class="dialogue-scroll-area" bind:this={chatContainer}>
        {#each messages as msg}
          <div class="chat-row {msg.sender === 'SİZ' ? 'row-user' : 'row-aspasia'}">
            <div class="avatar-disc">
              {#if msg.sender === 'SİZ'}
                <span class="avatar-glyph">👤</span>
              {:else}
                <span class="avatar-glyph">🏛️</span>
              {/if}
            </div>
            <div class="bubble-body">
              <div class="bubble-text">{msg.text}</div>
              <div class="bubble-footer">
                <span class="msg-timestamp">{msg.time}</span>
                <span class="check-marks">✓✓</span>
              </div>
            </div>
          </div>
        {/each}
      </div>
      <div class="monitor-input-tray">
        <button class="cam-btn" on:click={() => fileInput.click()} title="Görsel Yükle">
          📷
        </button>
        <input type="file" accept="image/*" bind:this={fileInput} on:change={handleImageUpload} style="display:none;" />
        <input
          type="text"
          class="terminal-input"
          bind:value={inputMessage}
          on:keydown={handleKeydown}
          placeholder="Komut girin · Enter command or query..."
          disabled={isSending}
        />
        <button class="brass-send-btn" on:click={sendMessage} disabled={isSending || (!inputMessage.trim() && !attachedImage)}>
          GÖNDER (SEND)
        </button>
      </div>
    </section>

    <section class="panel pillars-panel">
      <div class="panel-title">
        <span>7 PILLARS</span>
        <span class="panel-tr">ADLİ DAMGALAR</span>
      </div>
      <div class="pillars-track">
        <button class="pillar-btn {activeForensicModal === 'follower' ? 'btn-active' : ''}" on:click={() => toggleForensic('follower')}>
          <span class="forensic-icon">🕸️</span>
          <span class="forensic-name">FOLLOWER</span>
          <span class="forensic-tr">TAKİPÇİ</span>
        </button>
        <button class="pillar-btn {activeForensicModal === 'timing' ? 'btn-active' : ''}" on:click={() => toggleForensic('timing')}>
          <span class="forensic-icon">⏱️</span>
          <span class="forensic-name">TIMING</span>
          <span class="forensic-tr">ZAMANLAMA</span>
        </button>
        <button class="pillar-btn {activeForensicModal === 'depth' ? 'btn-active' : ''}" on:click={() => toggleForensic('depth')}>
          <span class="forensic-icon">📑</span>
          <span class="forensic-name">DEPTH</span>
          <span class="forensic-tr">DERİNLİK</span>
        </button>
        <button class="pillar-btn {activeForensicModal === 'visual' ? 'btn-active' : ''}" on:click={() => toggleForensic('visual')}>
          <span class="forensic-icon">👁️</span>
          <span class="forensic-name">VISUAL</span>
          <span class="forensic-tr">GÖRSEL</span>
        </button>
        <button class="pillar-btn {activeForensicModal === 'shadow' ? 'btn-active' : ''}" on:click={() => toggleForensic('shadow')}>
          <span class="forensic-icon">🎭</span>
          <span class="forensic-name">SHADOW</span>
          <span class="forensic-tr">GÖLGE</span>
        </button>
        <button class="pillar-btn {activeForensicModal === 'osint' ? 'btn-active' : ''}" on:click={() => toggleForensic('osint')}>
          <span class="forensic-icon">🌐</span>
          <span class="forensic-name">OSINT</span>
          <span class="forensic-tr">OSINT</span>
        </button>
        <button class="pillar-btn {activeForensicModal === 'resonance' ? 'btn-active' : ''}" on:click={() => toggleForensic('resonance')}>
          <span class="forensic-icon">🎯</span>
          <span class="forensic-name">RESONANCE</span>
          <span class="forensic-tr">REZONANS</span>
        </button>
        <button class="pillar-btn {activeForensicModal === 'pillars' ? 'btn-active' : ''}" on:click={() => toggleForensic('pillars')}>
          <span class="forensic-icon">◈</span>
          <span class="forensic-name">7 PILLARS</span>
          <span class="forensic-tr">7 SÜTUN</span>
        </button>
      </div>
    </section>
  </div>

  <!-- ==================== DAMGA AÇILIR PANELİ (POPUP DRAWER) ==================== -->
  {#if activeForensicModal}
    <div class="forensic-modal-backdrop" role="presentation" on:click={() => activeForensicModal = null} on:keydown={(e) => { if (e.key === 'Escape') activeForensicModal = null; }}>
      <div class="forensic-modal-card" role="dialog" aria-modal="true" tabindex="-1" on:click|stopPropagation on:keydown|stopPropagation>
        <div class="modal-header-brass">
          <span class="font-cinzel modal-title">ADLİ RAPOR: {activeForensicModal.toUpperCase()}</span>
          <button class="modal-close" on:click={() => activeForensicModal = null}>✕</button>
        </div>
        <div class="modal-content-body">
          {#if activeForensicModal === 'follower' && followerAudit}
            <div class="report-box">
              <h4>Takipçi & Kitle Denetimi</h4>
              <!-- W2: UI Türkce metin eslemek yerine makine-okunur verdict_code'u okur -->
              <p>Hüküm: {followerAudit.verdict || 'BİLİNMİYOR'} <span style="opacity:0.7;">({followerAudit.verdict_code || 'unknown'})</span></p>
              <p>Takipçi: {followerAudit.follower_count ?? 0} · Takip: {followerAudit.following_count ?? 'ölçülmedi'} · Gönderi: {followerAudit.post_count ?? 0}</p>
              <p>Etkileşim: {followerAudit.engagement_rate ?? '—'} (beklenen: {followerAudit.expected_rate_range || 'N/A'})</p>
              <p>Veri Tamamlık: %{((followerAudit.data_completeness ?? 0) * 100).toFixed(0)}</p>
            </div>
          {:else if activeForensicModal === 'timing' && timingForensics}
            <div class="report-box">
              <h4>Zaman & Sirkadiyen Forensik</h4>
              <!-- W1: GERÇEK backend anahtarları (timing_forensics çıktısı):
                   night_share, peak_hour, median_drift_hours -->
              <p>Gece Payı: %{((timingForensics.night_share ?? 0) * 100).toFixed(0)}</p>
              <p>Tepe Saati: {timingForensics.peak_hour ?? '—'}</p>
              <p>Medyan Drift: {timingForensics.median_drift_hours ?? '—'} saat</p>
            </div>
          {:else if activeForensicModal === 'resonance' && resonanceCalc}
            <div class="report-box">
              <h4>Rezonans & Yaklaşım Önerisi</h4>
              <!-- resonance_calc GERÇEK çıktısı: compatibility_score,
                   recommended_approach, red_flags (runs.output_summary) -->
              <p>Uyumluluk: %{((resonanceCalc.compatibility_score ?? 0) * 100).toFixed(0)}</p>
              <p>Önerilen Yaklaşım: {resonanceCalc.recommended_approach || '—'}</p>
              <p>Kırmızı Bayraklar: {(resonanceCalc.red_flags || []).join(', ') || 'Yok'}</p>
            </div>
          {:else if activeForensicModal === 'depth' && depthReport}
            <div class="report-box">
              <h4>Derinlik & Alıntı Kalkanı</h4>
              <p>Gerçeklik Skoru: %{((depthReport.reality_index || 0) * 100).toFixed(0)}</p>
              <p>Özet: {depthReport.essence_one_liner || (depthReport.available === false
                ? `ÜRETİLEMEDİ (${depthReport.reason || depthReport.error_code || 'veri yok'})`
                : 'Özet alanı boş döndü.')}</p>
            </div>
          {:else if activeForensicModal === 'visual' && visualEvidence}
            <div class="report-box">
              <h4>Görsel & Estetik Damga</h4>
              <p>Stil: {visualEvidence.aesthetic_style || '—'}</p>
              <p>Özet: {visualEvidence.visual_evidence_summary || (visualEvidence.data_confidence === false
                ? `GÖRSEL ANALİZ YOK (${visualEvidence.fallback_reason || 'veri yok'})`
                : 'Özet alanı boş döndü.')}</p>
            </div>
          {:else if activeForensicModal === 'shadow' && shadowProfile}
            <div class="report-box">
              <h4>Gölge Profili (Karanlık Üçlü)</h4>
              <p>Narsisizm: {shadowProfile.dark_profile?.narcissism ?? 0}</p>
              <p>Strateji: {shadowProfile.strategy || '—'}</p>
              {#if shadowProfile.data_confidence === false}
                <p class="report-warn">GÖLGE KATMANI VERİSİZ: {shadowProfile.fallback_reason || 'veri yok'}</p>
              {/if}
            </div>
          {:else if activeForensicModal === 'osint' && osintFootprint}
            <div class="report-box">
              <h4>OSINT Dijital Ayak İzi</h4>
              <p>Platform Eşleşmesi: {(osintFootprint.associated_platforms || []).join(', ') || '—'}</p>
              {#if osintFootprint.data_confidence === false}
                <p class="report-warn">OSINT VERİSİ YOK: {osintFootprint.fallback_reason || 'ölçüm yapılamadı'}
                  — "veri yok" ≠ "olumsuz bulgu yok".</p>
              {/if}
            </div>
          {:else if activeForensicModal === 'pillars' && (frequencyMap || seismosEvents || voidMap || strataMap || gravityMap || pulseMap || keyMatrix)}
            <!-- [BOSS-5] Deterministik 7-sütun raporları. Her rapor kendi
                 EvidenceStatus'unu taşır (OBSERVED dışındakiler rozetlenir) —
                 "veri yok" ile "ölçüldü" ayrımı kullanıcıdan gizlenmez. -->
            <PillarFeed {frequencyMap} {seismosEvents} {voidMap} {strataMap} {gravityMap} {pulseMap} {keyMatrix} />
            {#if psychodynamicDepth}
              <div class="report-box" style="margin-top:10px;">
                <h4>Psikodinamik Derinlik (4 Kanal)</h4>
                <p>Hüküm: {psychodynamicDepth.verdict || 'bilinmiyor'} · Güven: %{((psychodynamicDepth.confidence ?? 0) * 100).toFixed(0)}</p>
                {#each depthChannels(psychodynamicDepth) as row}
                  <p>{row.name.toUpperCase()}: yoğunluk {((row.ch?.intensity ?? 0)).toFixed(2)} · tutarlılık {((row.ch?.coherence ?? 0)).toFixed(2)} · tamlık {((row.ch?.completeness ?? 0)).toFixed(2)}</p>
                {/each}
                <p>Telafi Endeksi: {(psychodynamicDepth.compensation_index ?? 0).toFixed(2)} · Reaksiyon Oluşumu: {(psychodynamicDepth.reaction_formation_index ?? 0).toFixed(2)}</p>
                {#if psychodynamicDepth.reason}<p style="opacity:0.75;">Gerekçe: {psychodynamicDepth.reason}</p>{/if}
              </div>
            {/if}
          {:else}
            <div class="report-box">
              <p style="color: var(--text-dim);">Bu modül için henüz analiz çalıştırılmadı veya hedef veri bekleniyor.</p>
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  /* ===================================================
     ATLAS EPIFIZ PINEAL OBSERVATORY — KONSOL STİLLERİ
     =================================================== */
  .observatory {
    background:
      radial-gradient(ellipse at 50% 10%, rgba(212, 175, 55, 0.08) 0%, transparent 60%),
      radial-gradient(circle at center, #1e1107 0%, #100804 60%, #080402 100%);
    border: 3px solid #8e6538;
    box-shadow:
      0 0 0 1px #ffecb3,
      0 0 0 3px #180d05,
      0 0 0 5px #6b4b24,
      inset 0 2px 4px rgba(255, 235, 175, 0.35),
      inset 0 -3px 6px rgba(0, 0, 0, 0.9),
      inset 0 0 50px rgba(0, 0, 0, 0.85),
      0 18px 45px rgba(0, 0, 0, 0.95);
    border-radius: 14px;
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    position: relative;
  }

  /* ---------- ÜST PLAKA ---------- */
  .masthead {
    position: relative;
    background: linear-gradient(180deg, #fef0be 0%, #d4af37 28%, #8a6332 72%, #5a3a16 100%);
    border: 1px solid #ffecb3;
    border-radius: 10px;
    box-shadow:
      0 0 0 3px #180d05,
      0 0 0 4px #8e6538,
      0 6px 18px rgba(0, 0, 0, 0.8),
      inset 0 2px 3px rgba(255, 255, 255, 0.85),
      inset 0 -3px 6px rgba(0, 0, 0, 0.55);
    padding: 12px 22px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    color: #150c04;
  }
  .mast-left { min-width: 0; }
  .mast-title {
    font-size: clamp(15px, 2.4vw, 24px);
    font-weight: 900;
    letter-spacing: 0.12em;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.55);
    line-height: 1.15;
  }
  .mast-ver {
    display: inline-block;
    font-size: 0.62em;
    background: #150c04;
    color: #ffd978;
    border-radius: 4px;
    padding: 1px 8px;
    vertical-align: middle;
    letter-spacing: 0.08em;
    text-shadow: none;
    box-shadow: inset 0 1px 2px #000, 0 1px 0 rgba(255, 255, 255, 0.5);
  }
  .mast-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: clamp(8px, 1.3vw, 11px);
    font-weight: 700;
    letter-spacing: 0.22em;
    margin-top: 4px;
    opacity: 0.85;
  }
  .mast-right {
    display: flex;
    align-items: center;
    gap: 18px;
  }
  .mast-locks {
    display: flex;
    gap: 12px;
  }
  .lock-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    background: rgba(10, 5, 2, 0.85);
    border: 1px solid #3a220e;
    border-radius: 6px;
    padding: 5px 10px;
    box-shadow: inset 0 2px 4px #000, 0 1px 0 rgba(255, 255, 255, 0.4);
  }
  .lock-name {
    font-size: 8px;
    font-weight: 800;
    letter-spacing: 0.12em;
    color: #d4af37;
  }
  .lock-state {
    font-size: 8px;
    font-weight: 700;
    color: #f5edd8;
  }
  .lock-led, .agent-led {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    border: 1px solid #000;
  }
  .led-green { background: #10b981; box-shadow: 0 0 8px #10b981, 0 0 2px #fff, inset 0 1px 1px #fff; }
  .led-red { background: #ef4444; box-shadow: 0 0 8px #ef4444, inset 0 1px 1px #ffb4b4; }
  .led-dim { background: #3a2c1c; box-shadow: inset 0 1px 2px #000; }
  .led-teal { background: #06b6d4; box-shadow: 0 0 8px #06b6d4, inset 0 1px 1px #fff; }
  .pulse { animation: ledPulse 1.1s ease-in-out infinite; }
  @keyframes ledPulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.45; }
  }

  .sysstate {
    display: flex;
    align-items: center;
    gap: 10px;
    background: rgba(10, 5, 2, 0.9);
    border: 1px solid #3a220e;
    border-radius: 6px;
    padding: 6px 12px;
    box-shadow: inset 0 2px 4px #000, 0 1px 0 rgba(255, 255, 255, 0.4);
  }
  .sysstate-label {
    font-size: 8px;
    font-weight: 800;
    letter-spacing: 0.1em;
    color: #d4af37;
    line-height: 1.35;
  }
  .sysstate-bars { display: flex; gap: 4px; }
  .sysbar {
    width: 16px;
    height: 8px;
    border-radius: 2px;
    background: #2a1c0d;
    border: 1px solid #000;
    box-shadow: inset 0 1px 2px #000;
  }
  .sysbar.lit {
    background: linear-gradient(180deg, #7dfcd0, #10b981);
    box-shadow: 0 0 8px #10b981;
  }
  .sysstate-text {
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.1em;
    color: #7dfcd0;
    text-shadow: 0 0 8px rgba(16, 185, 129, 0.7);
  }

  /* ---------- GÖSTERGE SIRASI ---------- */
  .gauge-row {
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.06) 0%, transparent 30%, rgba(0, 0, 0, 0.4) 100%),
      linear-gradient(90deg, #1f1208 0%, #2b190d 50%, #1f1208 100%);
    border: 1px solid #5a3d1c;
    box-shadow:
      inset 0 1px 2px rgba(255, 235, 175, 0.25),
      inset 0 -2px 5px rgba(0, 0, 0, 0.8),
      0 4px 14px rgba(0, 0, 0, 0.65);
    border-radius: 10px;
    padding: 14px 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 18px;
    flex-wrap: wrap;
  }
  .dials-cluster {
    display: flex;
    gap: 22px;
    flex-wrap: wrap;
    justify-content: center;
    align-items: flex-start;
    flex: 1;
  }
  .signals-block {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    background: #0d0703;
    border: 1px solid #4a3017;
    border-radius: 8px;
    padding: 10px 14px;
    box-shadow: inset 0 2px 6px #000;
  }
  .signals-label {
    font-family: 'Cinzel', serif;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.14em;
    color: var(--gold);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1px;
  }
  .signals-sub {
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 0.14em;
    color: var(--text-muted);
  }
  .odometer-bezel {
    background: #0d0703;
    border: 2px solid #5a3d1c;
    padding: 3px 8px;
    border-radius: 4px;
    box-shadow: inset 0 0 8px #000, 0 2px 4px rgba(0, 0, 0, 0.6);
  }
  .odometer-digits { display: flex; gap: 3px; }
  .odo-digit {
    background: linear-gradient(180deg, #1f1f1f 0%, #111111 48%, #000000 52%, #141414 100%);
    color: #fff;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    font-weight: 800;
    padding: 2px 5px;
    border-radius: 2px;
    border: 1px solid #333;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2), 0 1px 2px #000;
  }
  .flaps-col {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  /* ---------- GENEL PANEL ---------- */
  .panel {
    background:
      linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, transparent 40%, rgba(0, 0, 0, 0.4) 100%),
      linear-gradient(180deg, #201309 0%, #120a04 100%);
    border: 2px solid #6b4b24;
    border-radius: 10px;
    padding: 12px;
    box-shadow:
      inset 1px 1px 1px rgba(255, 235, 175, 0.22),
      inset -1px -1px 2px rgba(0, 0, 0, 0.8),
      inset 0 0 22px rgba(0, 0, 0, 0.75),
      0 5px 14px rgba(0, 0, 0, 0.7);
    position: relative;
  }
  .panel-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    font-family: 'Cinzel', serif;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.1em;
    color: var(--gold);
    text-shadow: 0 1px 2px #000;
    border-bottom: 1px solid #4a3017;
    padding-bottom: 8px;
    margin-bottom: 10px;
  }
  .panel-tr {
    font-family: 'JetBrains Mono', monospace;
    font-size: 8px;
    font-weight: 500;
    color: var(--text-muted);
    letter-spacing: 0.08em;
    white-space: nowrap;
  }
  .title-ghost {
    font-family: 'JetBrains Mono', monospace;
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 0.14em;
    color: #7dfcd0;
    text-shadow: 0 0 6px rgba(16, 185, 129, 0.7);
  }
  .live-dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 8px #10b981;
    animation: ledPulse 1.6s ease-in-out infinite;
    margin: 0 2px 0 6px;
    vertical-align: baseline;
  }

  /* ---------- ANA IZGARA ---------- */
  .obs-grid {
    display: grid;
    grid-template-columns: 262px 1fr 305px;
    gap: 16px;
    align-items: stretch;
  }
  .col-left, .col-right {
    display: flex;
    flex-direction: column;
    gap: 14px;
    min-width: 0;
  }
  .col-center {
    display: flex;
    flex-direction: column;
    gap: 14px;
    min-width: 0;
  }

  /* ---------- SOL: KAYNAK LİSTESİ ---------- */
  .source-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 7px;
    margin-bottom: 10px;
  }
  .source-list li {
    display: flex;
    align-items: center;
    gap: 8px;
    background: #080402;
    border: 1px solid #3d2b17;
    border-radius: 5px;
    padding: 6px 9px;
    box-shadow: inset 0 1px 3px #000;
  }
  .src-led {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    border: 1px solid #000;
    flex-shrink: 0;
  }
  .src-led.on { background: #10b981; box-shadow: 0 0 8px #10b981; }
  .src-led.off { background: #4a3a26; box-shadow: inset 0 1px 2px #000; }
  .src-name {
    flex: 1;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.04em;
    color: #e2d7c5;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .src-state {
    font-size: 8px;
    font-weight: 800;
    color: #7dfcd0;
    text-shadow: 0 0 6px rgba(16, 185, 129, 0.6);
    white-space: nowrap;
  }
  .source-stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .stat-box {
    background: #060302;
    border: 1px solid #3d2b17;
    border-radius: 6px;
    padding: 7px 6px;
    display: flex;
    flex-direction: column;
    align-items: center;
    box-shadow: inset 0 2px 5px #000;
  }
  .stat-num {
    font-size: 20px;
    font-weight: 800;
    color: #7dfcd0;
    text-shadow: 0 0 10px rgba(16, 185, 129, 0.7);
    line-height: 1.1;
  }
  .stat-lbl {
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 0.16em;
    color: var(--text-muted);
  }

  /* ---------- SOL: ŞALTERLER + KASA ---------- */
  .switches-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px 6px;
    justify-items: center;
    margin-bottom: 10px;
  }
  .estop-wrap {
    display: flex;
    justify-content: center;
    border-top: 1px solid #3d2b17;
    padding-top: 10px;
  }
  .token-plaque {
    position: relative;
    background: linear-gradient(180deg, #fef0be 0%, #d4af37 25%, #8c6728 65%, #3a240d 100%);
    border: 1px solid #ffecb3;
    color: #120904;
    padding: 8px;
    text-align: center;
    box-shadow:
      inset 0 1px 1px rgba(255, 255, 255, 0.7),
      inset 0 -1px 2px rgba(0, 0, 0, 0.6),
      0 4px 8px rgba(0, 0, 0, 0.7);
    border-radius: 4px;
    margin-bottom: 10px;
  }
  .plaque-screw {
    position: absolute;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #3a220e, #140b05);
    border: 0.5px solid #ffecb3;
    box-shadow: inset 0 1px 0 #000;
  }
  .plaque-screw.top-left { top: 3px; left: 3px; }
  .plaque-screw.top-right { top: 3px; right: 3px; }
  .plaque-screw.btm-left { bottom: 3px; left: 3px; }
  .plaque-screw.btm-right { bottom: 3px; right: 3px; }
  .ps-tl { top: 6px; left: 6px; }
  .ps-tr { top: 6px; right: 6px; }
  .ps-bl { bottom: 6px; left: 6px; }
  .ps-br { bottom: 6px; right: 6px; }
  .plaque-header { font-family: 'Cinzel', serif; font-size: 9px; font-weight: 900; letter-spacing: 0.6px; }
  .plaque-code { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 800; letter-spacing: 1px; }
  .plaque-sub { font-family: 'JetBrains Mono', monospace; font-size: 7px; font-weight: 500; letter-spacing: 0.5px; opacity: 0.85; margin-top: 2px; }
  .keylock-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    border-top: 1px solid #3d2b17;
    padding-top: 10px;
    margin-bottom: 10px;
  }
  .module-title {
    font-family: 'Cinzel', serif;
    font-size: 8px;
    font-weight: 800;
    color: var(--gold);
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.9);
    letter-spacing: 0.8px;
    text-align: center;
  }
  .knobs-row {
    display: flex;
    justify-content: space-around;
    width: 100%;
    gap: 6px;
    border-top: 1px solid #3d2b17;
    padding-top: 10px;
  }
  .knob-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }
  .knurled-knob {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #fef0be 0%, #d4af37 25%, #8c6728 65%, #3a240d 100%);
    border: 2px solid #5a3d1c;
    box-shadow:
      0 4px 8px rgba(0, 0, 0, 0.85),
      0 0 0 2px #221307,
      0 0 0 3px #8c6728,
      inset 0 1px 2px rgba(255, 255, 255, 0.7),
      inset 0 -2px 4px rgba(0, 0, 0, 0.8);
    cursor: pointer;
    position: relative;
    transition: transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1), filter 0.15s;
  }
  .knurled-knob:hover { filter: brightness(1.15); }
  .knurled-knob:active { transform: scale(0.96); }
  .knob-notch {
    position: absolute;
    top: 2px;
    left: 16px;
    width: 4px;
    height: 9px;
    background: #ffffff;
    border-radius: 1px;
    box-shadow: 0 0 3px rgba(255, 255, 255, 0.9), 0 1px 2px #000;
  }
  .knob-label { font-size: 7px; color: var(--text-dim); font-weight: 700; }
  .knob-detent {
    font-family: 'JetBrains Mono', monospace;
    font-size: 7px;
    font-weight: 700;
    color: #7dfcd0;
    background: #050302;
    border: 1px solid #3d2b17;
    border-radius: 3px;
    padding: 2px 6px;
    margin-top: 3px;
    white-space: nowrap;
    text-shadow: 0 0 4px rgba(16, 185, 129, 0.6);
    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.8);
  }

  /* ---------- ORTA: GÖZ ---------- */
  .eye-panel {
    background:
      radial-gradient(ellipse at 50% 30%, rgba(212, 175, 55, 0.1) 0%, transparent 60%),
      radial-gradient(circle at center, #160d05 0%, #0b0502 70%, #050201 100%);
  }
  .eye-stage {
    position: relative;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 30px 0;
    min-height: 380px;
  }
  .eye-orbit {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 372px;
    height: 372px;
    margin: -186px 0 0 -186px;
    border: 1px dashed rgba(212, 175, 55, 0.4);
    border-radius: 50%;
    animation: orbitSpin 40s linear infinite;
    pointer-events: none;
  }
  @keyframes orbitSpin {
    to { transform: rotate(360deg); }
  }
  .eye-led {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 10px;
    height: 10px;
    margin: -5px 0 0 -5px;
    border-radius: 50%;
    background: #38ef7d;
    box-shadow: 0 0 10px #38ef7d, 0 0 20px rgba(56, 239, 125, 0.5);
    transform: rotate(var(--a)) translateY(-196px);
    animation: ledPulse 2.4s ease-in-out infinite;
    animation-delay: var(--d);
    z-index: 2;
    pointer-events: none;
  }
  .eye-scale { position: relative; z-index: 1; }
  .eye-status {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    background: #060302;
    border: 1px solid #3d2b17;
    border-radius: 5px;
    padding: 7px 12px;
    font-size: 10px;
    letter-spacing: 0.06em;
    color: #c9b998;
    box-shadow: inset 0 2px 5px #000;
    text-align: center;
  }
  .eye-status b { color: var(--gold); }
  .dot-led { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .dot-green { background: #10b981; box-shadow: 0 0 8px #10b981; }
  .dot-amber { background: #f59e0b; box-shadow: 0 0 8px #f59e0b; }

  /* ---------- ORTA: GÜVERTE ---------- */
  .deck-panel {
    background:
      radial-gradient(ellipse at 50% 0%, rgba(255, 255, 255, 0.05) 0%, transparent 60%),
      radial-gradient(ellipse at 50% 50%, rgba(14, 24, 18, 0.97) 0%, rgba(7, 12, 9, 0.99) 70%, #030604 100%);
  }
  .monitor-tabs-bar { display: flex; gap: 6px; margin-bottom: 10px; }
  .monitor-tab-btn {
    flex: 1;
    background: linear-gradient(180deg, #1b261e 0%, #0d1610 100%);
    border: 1px solid #234731;
    color: #8bb397;
    font-family: 'Cinzel', serif;
    font-size: 9px;
    font-weight: 800;
    padding: 6px 8px;
    border-radius: 4px;
    cursor: pointer;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.6), inset 0 1px 1px rgba(255, 255, 255, 0.1);
    transition: all 0.15s ease;
  }
  .monitor-tab-btn:hover {
    border-color: #38ef7d;
    color: #38ef7d;
    text-shadow: 0 0 6px rgba(56, 239, 125, 0.5);
  }
  .monitor-tab-btn.tab-selected {
    background: linear-gradient(180deg, #1b4d30 0%, #0c2b19 100%);
    color: #38ef7d;
    border-color: #38ef7d;
    box-shadow: 0 0 12px rgba(56, 239, 125, 0.4), inset 0 1px 2px rgba(255, 255, 255, 0.3);
    text-shadow: 0 0 6px rgba(56, 239, 125, 0.8);
  }
  .quick-target-strip { display: flex; gap: 8px; margin-bottom: 10px; }
  .quick-target-strip input {
    flex: 1;
    background: #060d08;
    border: 1px solid #1c3d28;
    color: #38ef7d;
    text-shadow: 0 0 4px rgba(56, 239, 125, 0.5);
    font-size: 11px;
    padding: 8px 12px;
    border-radius: 4px;
    box-shadow: inset 0 2px 4px #000;
  }
  .launch-btn {
    font-family: 'Cinzel', serif;
    font-size: 10px;
    font-weight: 800;
    padding: 8px 16px;
    border-radius: 5px;
    cursor: pointer;
    transition: all 0.12s ease;
    white-space: nowrap;
  }
  .btn-armed {
    background: linear-gradient(180deg, #34d399 0%, #10b981 40%, #065f46 100%);
    color: #062b1e;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.5);
    border: 1px solid #6ee7b7;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.7), 0 0 14px rgba(16, 185, 129, 0.6), inset 0 1px 2px #fff;
  }
  .btn-armed:hover { filter: brightness(1.15); transform: translateY(-1px); }
  .btn-armed:active { transform: translateY(2px); box-shadow: inset 0 2px 4px #000; }
  .btn-unarmed {
    background: linear-gradient(180deg, #2b1f13 0%, #170d06 100%);
    color: var(--text-muted);
    border: 1px solid #4a3017;
    box-shadow: inset 0 1px 2px #000;
  }
  .active-route-subbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    background: #08110b;
    border: 1px solid #163020;
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 8px;
    letter-spacing: 0.4px;
  }
  .route-text { color: #729a80; }
  .route-dots { display: flex; gap: 5px; }

  /* ---------- SAĞ: İZ ALANI ---------- */
  .trace-big {
    display: flex;
    align-items: baseline;
    justify-content: center;
    gap: 10px;
    background: #050302;
    border: 1px solid #234731;
    border-radius: 6px;
    padding: 10px;
    margin-bottom: 10px;
    box-shadow: inset 0 2px 8px #000, 0 0 14px rgba(56, 239, 125, 0.12);
  }
  .trace-num {
    font-size: 34px;
    font-weight: 800;
    color: #ffb834;
    text-shadow: 0 0 4px rgba(255, 255, 255, 0.4), 0 0 14px rgba(255, 184, 52, 0.6);
    line-height: 1;
  }
  .trace-unit {
    font-family: 'Cinzel', serif;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.2em;
    color: var(--text-dim);
  }
  .trace-rows { display: flex; flex-direction: column; gap: 6px; }
  .trace-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 9px;
    background: #080402;
    border: 1px solid #3d2b17;
    border-radius: 4px;
    padding: 5px 9px;
    color: #8bb397;
  }
  .trace-row b { color: #7dfcd0; font-size: 10px; }

  /* ---------- SAĞ: RİSK KADRANI ---------- */
  .risk-dial {
    position: relative;
    width: 168px;
    height: 92px;
    margin: 2px auto 4px;
    overflow: hidden;
  }
  .risk-arc {
    position: absolute;
    inset: 0;
    border-radius: 168px 168px 0 0;
    background: conic-gradient(from 180deg, #10b981 0 30%, #f59e0b 38% 62%, #ef4444 70% 100%);
    -webkit-mask: radial-gradient(circle at 50% 100%, transparent 62%, #000 64%);
    mask: radial-gradient(circle at 50% 100%, transparent 62%, #000 64%);
    opacity: 0.92;
  }
  .risk-needle {
    position: absolute;
    left: 50%;
    bottom: 0;
    width: 3px;
    height: 70px;
    background: #fff;
    border-radius: 2px;
    transform-origin: 50% 100%;
    box-shadow: 0 0 8px rgba(255, 255, 255, 0.9);
    transition: transform 0.5s cubic-bezier(0.34, 1.4, 0.64, 1);
  }
  .risk-hub {
    position: absolute;
    left: 50%;
    bottom: -9px;
    width: 18px;
    height: 18px;
    margin-left: -9px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #fef0be, #8c6728 70%, #241607);
    border: 1px solid #5a3d1c;
    box-shadow: 0 2px 4px #000;
  }
  .risk-text {
    text-align: center;
    font-size: 9px;
    color: #c9b998;
    background: #060302;
    border: 1px solid #3d2b17;
    border-radius: 4px;
    padding: 5px 8px;
    box-shadow: inset 0 2px 4px #000;
  }
  .risk-text b { color: #ffb834; }

  /* ---------- SAĞ: AJAN RAFI ---------- */
  .rack-panel { flex: 1; }
  .agent-rows {
    display: flex;
    flex-direction: column;
    gap: 5px;
    max-height: 430px;
    overflow-y: auto;
    padding-right: 2px;
  }
  .agent-row {
    display: flex;
    align-items: center;
    gap: 8px;
    background: linear-gradient(180deg, #150d05 0%, #0c0603 100%);
    border: 1px solid #3d2b17;
    border-radius: 5px;
    padding: 5px 8px;
    box-shadow: inset 0 1px 2px #000;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  .agent-row:hover { border-color: var(--brass-bright); }
  .agent-row.row-running {
    border-color: #10b981;
    box-shadow: 0 0 10px rgba(16, 185, 129, 0.4), inset 0 0 8px rgba(16, 185, 129, 0.12);
  }
  .agent-row.row-halted { border-color: #ef4444; }
  .agent-row.row-done { border-color: #2a6b5c; }
  .agent-idx {
    font-size: 9px;
    font-weight: 800;
    color: var(--text-muted);
    min-width: 16px;
  }
  .agent-led { flex-shrink: 0; }
  .agent-name {
    flex: 1;
    min-width: 0;
    font-family: 'Cinzel', serif;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 0.04em;
    color: #f5edd8;
    text-shadow: 0 1px 2px #000;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .pill {
    font-size: 8px;
    font-weight: 800;
    letter-spacing: 0.08em;
    padding: 3px 8px;
    border-radius: 3px;
    border: 1px solid #000;
    flex-shrink: 0;
  }
  .pill-wait { background: #241a0e; color: #8c7355; }
  .pill-active {
    background: linear-gradient(180deg, #1b4d30, #0c2b19);
    color: #38ef7d;
    border-color: #38ef7d;
    text-shadow: 0 0 6px rgba(56, 239, 125, 0.8);
    animation: ledPulse 1.1s ease-in-out infinite;
  }
  .pill-report {
    background: linear-gradient(180deg, #123a3f, #0a2225);
    color: #67e8f9;
    border-color: #155e68;
  }
  .pill-verify {
    background: linear-gradient(180deg, #4d1512, #2b0c0a);
    color: #f87171;
    border-color: #7f1d1d;
  }

  /* ---------- ALT SIRA ---------- */
  .obs-bottom {
    display: grid;
    grid-template-columns: 1fr 380px;
    gap: 16px;
    align-items: stretch;
  }
  .command-deck {
    background:
      radial-gradient(ellipse at 50% 0%, rgba(255, 255, 255, 0.04) 0%, transparent 60%),
      radial-gradient(ellipse at 50% 50%, rgba(14, 24, 18, 0.97) 0%, #030604 100%);
    display: flex;
    flex-direction: column;
  }
  .dialogue-scroll-area {
    flex: 1;
    min-height: 150px;
    max-height: 230px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-right: 6px;
    margin-bottom: 10px;
  }
  .chat-row { display: flex; gap: 10px; align-items: flex-start; }
  .row-user { flex-direction: row-reverse; }
  .avatar-disc {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #4a2e12, #1f1309);
    border: 1px solid #b8860b;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.8), inset 0 1px 1px rgba(255, 255, 255, 0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .avatar-glyph { font-size: 14px; }
  .bubble-body {
    background: rgba(14, 26, 18, 0.9);
    border: 1px solid #1f452e;
    border-radius: 6px;
    padding: 9px 12px;
    max-width: 85%;
    box-shadow: inset 0 1px 2px rgba(56, 239, 125, 0.15), 0 3px 8px rgba(0, 0, 0, 0.7);
  }
  .row-user .bubble-body {
    background: rgba(38, 22, 10, 0.9);
    border-color: #8c5d28;
    box-shadow: inset 0 1px 2px rgba(255, 194, 71, 0.2), 0 3px 8px rgba(0, 0, 0, 0.7);
  }
  .bubble-text {
    font-size: 11px;
    color: #4ef289;
    text-shadow: 0 0 5px rgba(56, 239, 125, 0.6);
    line-height: 1.5;
  }
  .row-user .bubble-text {
    color: #ffc247;
    text-shadow: 0 0 5px rgba(255, 194, 71, 0.6);
  }
  .bubble-footer {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 5px;
    margin-top: 4px;
    font-size: 8px;
    color: #6b9c7a;
  }
  .check-marks { color: #10b981; text-shadow: 0 0 4px #10b981; }
  .monitor-input-tray {
    display: flex;
    gap: 8px;
    align-items: center;
    border-top: 1px solid #1f3829;
    padding-top: 10px;
  }
  .cam-btn {
    background: linear-gradient(180deg, #2b1f13 0%, #150c05 100%);
    border: 1px solid #5a3d1c;
    color: #fff;
    padding: 7px 11px;
    border-radius: 4px;
    cursor: pointer;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.6), inset 0 1px 1px rgba(255, 255, 255, 0.2);
    transition: all 0.15s;
  }
  .cam-btn:hover { border-color: var(--gold); transform: translateY(-1px); }
  .terminal-input {
    flex: 1;
    background: #060d08;
    border: 1px solid #1c3d28;
    color: #38ef7d;
    text-shadow: 0 0 4px rgba(56, 239, 125, 0.5);
    font-size: 11px;
    padding: 7px 12px;
    border-radius: 4px;
    box-shadow: inset 0 2px 4px #000;
  }
  .brass-send-btn {
    background: linear-gradient(180deg, #fff3c8 0%, #e2b94c 18%, #ad8228 65%, #634612 100%);
    color: #1a0f04;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.6);
    font-family: 'Cinzel', serif;
    font-size: 11px;
    font-weight: 800;
    padding: 7px 18px;
    border-radius: 5px;
    border: 1px solid #fff5cf;
    cursor: pointer;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.7), inset 0 1px 2px rgba(255, 255, 255, 0.9), inset 0 -2px 3px rgba(0, 0, 0, 0.6);
    transition: all 0.12s ease;
    white-space: nowrap;
  }
  .brass-send-btn:hover:not(:disabled) { filter: brightness(1.15); transform: translateY(-1px); }
  .brass-send-btn:active:not(:disabled) { transform: translateY(2px); box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.8); }
  .brass-send-btn:disabled { opacity: 0.45; cursor: not-allowed; filter: grayscale(0.5); }

  /* ---------- 7 SÜTUN BARASI ---------- */
  .pillars-track {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
  }
  .pillar-btn {
    background:
      linear-gradient(135deg, rgba(255, 255, 255, 0.07) 0%, transparent 45%, rgba(0, 0, 0, 0.5) 100%),
      linear-gradient(180deg, #241608 0%, #120a04 100%);
    border: 1px solid #5a3d1c;
    border-radius: 6px;
    padding: 10px 4px 8px;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    box-shadow: inset 0 1px 1px rgba(255, 235, 175, 0.2), 0 3px 7px rgba(0, 0, 0, 0.65);
    transition: all 0.14s ease;
  }
  .pillar-btn:hover {
    border-color: var(--brass-bright);
    transform: translateY(-2px);
    box-shadow: inset 0 1px 1px rgba(255, 235, 175, 0.3), 0 5px 12px rgba(0, 0, 0, 0.8), 0 0 10px rgba(212, 175, 55, 0.25);
  }
  .pillar-btn:active { transform: translateY(1px); }
  .pillar-btn.btn-active {
    border-color: #38ef7d;
    box-shadow: 0 0 14px rgba(56, 239, 125, 0.55), inset 0 0 10px rgba(56, 239, 125, 0.25);
  }
  .forensic-icon { font-size: 19px; line-height: 1; }
  .forensic-name {
    font-family: 'Cinzel', serif;
    font-size: 8px;
    font-weight: 800;
    color: var(--gold);
    text-shadow: 0 1px 2px #000;
    letter-spacing: 0.06em;
  }

  /* --- İKİ DİLLİ ALT SATIRLAR (TR) --- */
  .module-tr { display: block; font-family: 'JetBrains Mono', monospace; font-size: 7px; font-weight: 500; color: var(--text-muted); letter-spacing: 0.4px; margin-top: 1px; }
  .knob-tr { font-family: 'JetBrains Mono', monospace; font-size: 6px; font-weight: 700; color: var(--text-muted); }
  .tr-micro { font-family: 'JetBrains Mono', monospace; font-size: 7px; color: var(--text-muted); }
  .tab-tr { display: block; font-family: 'JetBrains Mono', monospace; font-size: 6px; font-weight: 500; color: var(--text-muted); }
  .agent-tr { display: block; font-family: 'JetBrains Mono', monospace; font-size: 7px; font-weight: 500; color: var(--text-muted); }
  .forensic-tr { font-family: 'JetBrains Mono', monospace; font-size: 6px; font-weight: 700; color: var(--text-muted); }
  .plaque-tr { font-family: 'JetBrains Mono', monospace; font-size: 6px; font-weight: 700; letter-spacing: 0.5px; opacity: 0.8; }

  /* --- FORENSIC MODAL POPUP --- */
  .forensic-modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0, 0, 0, 0.85);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
  }
  .forensic-modal-card {
    background: linear-gradient(180deg, #201309 0%, #120904 100%);
    border: 3px solid var(--gold);
    border-radius: 10px;
    width: 90%;
    max-width: 520px;
    box-shadow: 0 0 0 4px #26170b, 0 20px 50px rgba(0, 0, 0, 0.95);
    overflow: hidden;
  }
  .modal-header-brass {
    background: linear-gradient(180deg, #fff3c8 0%, #d4af37 30%, #8a6332 100%);
    color: #150c04;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.6);
    padding: 10px 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #5a3d1c;
  }
  .modal-title {
    font-family: 'Cinzel', serif;
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 1px;
  }
  .modal-close {
    background: none;
    border: none;
    font-size: 16px;
    font-weight: 900;
    cursor: pointer;
    color: #120904;
    padding: 2px 6px;
    border-radius: 3px;
    transition: background 0.15s;
  }
  .modal-close:hover { background: rgba(0, 0, 0, 0.2); }
  .modal-content-body {
    padding: 16px;
    color: var(--text-main);
  }
  .report-warn {
    color: #f59e0b;
    font-size: 0.78rem;
    margin: 0.25rem 0 0;
  }
  .report-box h4 {
    color: var(--gold);
    margin-bottom: 8px;
    font-family: 'Cinzel', serif;
    font-size: 13px;
  }
  .report-box p {
    font-size: 12px;
    margin-bottom: 6px;
    color: #e2d7c5;
    line-height: 1.4;
  }

  /* ---------- DUYARLI YERLEŞİM ---------- */
  @media (max-width: 1240px) {
    .obs-grid { grid-template-columns: 1fr 1fr; }
    .col-center { grid-column: 1 / -1; order: -1; }
    .obs-bottom { grid-template-columns: 1fr; }
  }
  @media (max-width: 760px) {
    .obs-grid { grid-template-columns: 1fr; }
    .observatory { padding: 12px; }
    .masthead { padding: 10px 14px; }
    .mast-right { width: 100%; justify-content: space-between; }
    .eye-stage { min-height: 0; padding: 18px 0; }
    .eye-scale { transform: scale(0.78); }
    .eye-orbit { width: 300px; height: 300px; margin: -150px 0 0 -150px; }
    .eye-led { transform: rotate(var(--a)) translateY(-158px); }
    .pillars-track { grid-template-columns: repeat(4, 1fr); }
  }
  @media (max-width: 480px) {
    .eye-scale { transform: scale(0.66); }
    .pillars-track { grid-template-columns: repeat(2, 1fr); }
    .mast-locks { gap: 6px; }
  }

  @media (prefers-reduced-motion: reduce) {
    .live-dot, .pulse, .pill-active, .eye-orbit, .eye-led { animation: none; }
    .risk-needle { transition: none; }
  }
</style>
