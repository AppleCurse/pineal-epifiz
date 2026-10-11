<script lang="ts">
  import { onMount, onDestroy, afterUpdate } from 'svelte';
  import { get } from 'svelte/store';
  import {
    clientId, apiFetch, apiToken, setApiToken, currentApiToken,
    isAuthFailure, isProcessing, logs, taskStatus, telemetryEvents,
    armEngaged, sigintEngaged, recordEngaged, keyUnlocked, powerEngaged
  } from '../store';
  import { currentLang, t } from '../i18n';
  import { playClick, playRunning, playHalt, playToggle, setSoundEnabled } from '../lib/consoleAudio';
  import {
    health, sysTelemetry, uplinkState, throttleIdx, THROTTLE_DETENTS,
    ttsRate, TTS_DETENTS, startHealthPoll, stopHealthPoll
  } from '../lib/telemetry';
  import PillarFeed from './PillarFeed.svelte';
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

  // [PROD AUDIT 2026-10-11 · P2] Svelte store UPDATER'I SAF OLMALIDIR.
  // Eski kod `sigintEngaged.update(v => {...})` içinde ses çalıyor, log
  // yazıyor ve AĞA İSTEK ATIYORDU (cancelAnalysis, await'siz + catch'siz).
  // Updater içinde yan etki iki somut risk taşır: (a) Svelte updater'ı birden
  // çok çağırırsa ağ isteği de ses de ÇOĞALIR, (b) reddedilen promise kimse
  // tutmadığı için konsola unhandled rejection düşer. Yan etkiler updater
  // DIŞINA alındı; durum geçişi `get` + `set` ile deterministik.
  async function toggleSigint() {
    const next = !get(sigintEngaged);
    sigintEngaged.set(next);
    playToggle(next);
    logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'INFO', msg: next ? 'SIGINT: OPEN' : 'SIGINT: CLOSED' }]);
    if (next && get(isProcessing)) {
      const cancelled = await cancelAnalysis();
      if (!cancelled) {
        logs.update(l => [...l, { ts: new Date().toLocaleTimeString(), level: 'ERROR', msg: 'SIGINT: iptal BAŞARISIZ — görev hâlâ çalışıyor olabilir' }]);
      }
    }
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

  // [PROD AUDIT 2026-10-11 · P1] ACİL STOP artık SONUCU BEKLER ve SONUCU
  // SÖYLER. Eski sürüm "görev iptal emri verildi" logunu istek GÖNDERİLMEDEN
  // basıyor ve `cancelAnalysis()`'i await/catch etmiyordu: iptal 401/429/503
  // ile başarısız olsa bile operatör başarılı bir acil stop izliyordu ve
  // görev (LLM harcaması + hedefe yönelik tarama) arka planda sürüyordu.
  async function emergencyStop() {
    playHalt();
    const active = get(isProcessing) || get(taskStatus)?.status === 'processing';
    const stamp = () => new Date().toLocaleTimeString();
    if (!active) {
      playClick(120, 90);
      logs.update(l => [...l, { ts: stamp(), level: 'INFO', msg: 'ACİL STOP: hat boşta (iptal edilecek görev yok)' }]);
      return;
    }
    // Dürüst sıra: önce "emir GÖNDERİLİYOR", sonra backend'in GERÇEK kararı.
    logs.update(l => [...l, { ts: stamp(), level: 'ERROR', msg: 'ACİL STOP: iptal emri GÖNDERİLİYOR (sonuç bekleniyor)…' }]);
    const cancelled = await cancelAnalysis();
    logs.update(l => [...l, {
      ts: stamp(),
      level: cancelled ? 'INFO' : 'ERROR',
      msg: cancelled
        ? 'ACİL STOP: görev backend tarafından DURDURULDU'
        : 'ACİL STOP: İPTAL EDİLEMEDİ — görev hâlâ çalışıyor olabilir, bağlantıyı/token’ı denetleyin',
    }]);
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

      // [UI-BRIDGE] Chat ağızları: tüm sekmeler aynı TEK /api/aspasia/chat
      // ağzını kullanır.
      // [PROD AUDIT 2026-10-11 · P2] ÖLÜ KOŞUL KALDIRILDI. Eski satır:
      //     const chatUrl = activeAgentId === 'ASPASIA' ? '/api/aspasia/chat'
      //                                                 : '/api/aspasia/chat';
      // İki kol BİREBİR aynıydı: ternary hiçbir şey seçmiyordu. Daha önemlisi
      // yorum "sekme yalnız bağlam değiştirir" diyordu ama bağlam GÖVDEDE
      // TAŞINMIYORDU — AspasiaChatPayload (backend/api.py) yalnız
      // client_id/user_message/model_override/image_data kabul eder, sekme
      // alanı YOKTUR. Yani seçili ajan sekmesi isteği HİÇ etkilemiyordu.
      // Uydurma bir alan göndermek yerine gerçek davranış açıkça yazılır:
      // sekme GÖRSEL bağlamdır, sohbet ucu tektir. Sekme gerçekten sunucuya
      // taşınacaksa AspasiaChatPayload'a alan EKLENEREK yapılmalıdır (sessiz
      // sözleşme farkı bırakılmaz — bkz. docs/PINEAL_TUZUK.md giriş).
      const chatUrl = '/api/aspasia/chat';
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

  // [PROD AUDIT 2026-10-11 · P1] İPTAL, SONUCU DOĞRULANAN BİR İŞLEMDİR.
  //
  // Eski kod:
  //     async function cancelAnalysis() {
  //       ...
  //       await apiFetch(`/api/tasks/${activeTaskId}/cancel?...`, {method:'POST'});
  //     }
  // ve çağıranlar (emergencyStop, toggleSigint) bunu `await` ETMEDEN,
  // `.catch()` BAĞLAMADAN çağırıyordu. Üç ölçülen sonuç:
  //   1. YAKALANMAMIŞ PROMISE REJECTION: ağ hatası / 401 / 429 / 503
  //      durumunda reddedilen promise kimse tutmuyordu -> konsola unhandled
  //      rejection düşüyordu.
  //   2. ARAYÜZ YALAN SÖYLÜYORDU: `playHalt()` sesi ve "ACİL STOP: görev iptal
  //      emri verildi" logu istekten ÖNCE ve sonuçtan BAĞIMSIZ basılıyordu;
  //      `res.ok` hiç kontrol edilmiyordu. Yani 401/404/429/503 bile
  //      "başarılı acil stop" gibi görünüyordu.
  //   3. GÖREV ÇALIŞMAYA DEVAM EDİYORDU: bu sistem iptal edilmeyen görevde
  //      LLM bütçesi harcamayı ve hedefe karşı OSINT/tarama sürdürmeyi
  //      sürdürür. Operatörün kill-switch'i SESSİZCE başarısız oluyordu.
  //
  // Yeni sözleşme: true = backend iptali KABUL ETTİ; false = iptal EDİLEMEDİ
  // ve görev hâlâ çalışıyor olabilir. Başarı iddiası yalnız 2xx'te basılır.
  async function cancelAnalysis(): Promise<boolean> {
    const activeTaskId = $taskStatus?.task_id;
    if (!activeTaskId) return false;
    playHalt();
    const stamp = () => new Date().toLocaleTimeString();
    try {
      const res = await apiFetch(
        `/api/tasks/${encodeURIComponent(activeTaskId)}/cancel?client_id=${encodeURIComponent($clientId)}`,
        { method: 'POST' }
      );
      if (!res.ok) {
        // Hata kodunu gövdeden çıkar (backend tutarlı {error:{code}} döner);
        // gövde JSON değilse sessizce boş bırak — asıl bilgi status kodudur.
        let code = '';
        try {
          code = (await res.json())?.error?.code || '';
        } catch { /* gövde JSON değil */ }
        const detail = code ? `${res.status} ${code}` : `${res.status}`;
        if (isAuthFailure(res)) {
          logs.update(l => [...l, { ts: stamp(), level: 'ERROR', msg: `İPTAL BAŞARISIZ (${detail}): PINEAL_TOKEN geçersiz/eksik — GÖREV HÂLÂ ÇALIŞIYOR OLABİLİR` }]);
        } else if (res.status === 429) {
          logs.update(l => [...l, { ts: stamp(), level: 'ERROR', msg: `İPTAL BAŞARISIZ (${detail}): hız sınırı — birkaç saniye sonra yeniden deneyin, GÖREV ÇALIŞIYOR` }]);
        } else {
          logs.update(l => [...l, { ts: stamp(), level: 'ERROR', msg: `İPTAL BAŞARISIZ (${detail}) — GÖREV HÂLÂ ÇALIŞIYOR OLABİLİR` }]);
        }
        return false;
      }
      logs.update(l => [...l, { ts: stamp(), level: 'INFO', msg: `İPTAL ONAYLANDI (${res.status}): backend görevi durdurdu — ${activeTaskId}` }]);
      return true;
    } catch (e: any) {
      // Ağ katmanı hatası (backend erişilemez, CORS, DNS, bağlantı koptu).
      // Yutulmaz: operatöre iptalin OLMADIĞI açıkça söylenir.
      logs.update(l => [...l, { ts: stamp(), level: 'ERROR', msg: `İPTAL GÖNDERİLEMEDİ: ${e?.message || e} — GÖREV HÂLÂ ÇALIŞIYOR OLABİLİR` }]);
      return false;
    }
  }

  afterUpdate(() => {
    if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
  });
</script>

<div class="steampunk-console">
  <!-- ==================== ÜST SIRA: CANLI GÖSTERGELER + DURUM PANOSU ==================== -->
  <!-- İbreler /health + /api/telemetry ölçümlerine bağlıdır; veri yoksa park eder. -->
  <div class="top-dials-row">
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
    </div>
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

  <!-- ==================== ANA KOKPİT GÖVDESİ (3 SÜTUN) ==================== -->
  <div class="main-cockpit-grid">

    <!-- SOL PANEL: DONANIM VE ŞALTERLER -->
    <aside class="left-hardware-rack">
      <!-- 1. VAULT KEY LOCK (ateşleme interlock'u) -->
      <div class="hardware-module keylock-module">
        <div class="module-title">VAULT KEY LOCK<span class="module-tr">KASA ANAHTAR KİLİDİ</span></div>
        <KeyLock unlocked={$keyUnlocked} onToggle={toggleKey} />
        <span class="knob-detent">{$keyUnlocked ? 'AÇIK · ateş serbest' : 'KİLİTLİ'}</span>
      </div>

      <!-- 2. THROTTLE · MIXTURE · PROP (gerçek işlevli detentler) -->
      <div class="hardware-module knobs-module">
        <div class="module-title">THROTTLE &bull; MIXTURE &bull; PROP<span class="module-tr">GAZ · KARIŞIM · PERVANE</span></div>
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
      </div>

      <!-- 3. POWER · ARM · RECORD · SIGINT -->
      <div class="hardware-module switches-module">
        <div class="module-title">POWER<span class="module-tr">GÜÇ</span></div>
        <div class="switches-row">
          <ToggleSwitch label="POWER" tr="GÜÇ" engaged={$powerEngaged} led="green" onToggle={togglePower} />
          <ToggleSwitch label="ARM" tr="KURMA" engaged={$armEngaged} led="green" onToggle={toggleArm} />
          <ToggleSwitch label="RECORD" tr="KAYIT" engaged={$recordEngaged} led="green" onToggle={toggleRecord} />
          <ToggleSwitch label="SIGINT" tr="SİNYAL" engaged={$sigintEngaged} led="red" onToggle={toggleSigint} />
        </div>
      </div>

      <!-- 4. EMERGENCY STOP (işleyen görevi iptal eder) -->
      <div class="hardware-module estop-module">
        <EmergencyStop armed={$isProcessing || taskState === 'processing'} onPress={emergencyStop} />
      </div>

      <!-- 4. REC ODOMETER COUNTER (00087) -->
      <div class="hardware-module odometer-module">
        <span class="counter-tag">REC <span class="tr-micro">(KAYIT)</span></span>
        <div class="odometer-bezel">
          <div class="odometer-digits">
            {#each String(odometer).padStart(5, '0').split('') as digit}
              <span class="odo-digit">{digit}</span>
            {/each}
          </div>
        </div>
      </div>

      <!-- 6. STATUS ACTIVE LAMP -->
      <div class="hardware-module status-module">
        <span class="status-title">STATUS<br>ACTIVE<br><span class="tr-micro">DURUM: AKTİF</span></span>
        <div class="big-jewel-lamp {$isProcessing ? 'lamp-pulse' : 'lamp-steady'}"></div>
      </div>

      <!-- 7. PINEAL TOKEN PLAQUE (canlı kasa durumu — uydurma seri no yok) -->
      <div class="hardware-module token-plaque">
        <div class="plaque-screw top-left"></div>
        <div class="plaque-screw top-right"></div>
        <div class="plaque-screw btm-left"></div>
        <div class="plaque-screw btm-right"></div>
        <div class="plaque-header">PINEAL TOKEN</div>
        <div class="plaque-tr">PİNEAL ANAHTARI</div>
        <div class="plaque-code">{$apiToken ? 'KASA · AÇIK' : 'KASA · KİLİTLİ'}</div>
        <div class="plaque-sub">{$clientId}</div>
      </div>
    </aside>

    <!-- ORTA PANEL: AGENT DECK • ASPASIA OBSERVER -->
    <main class="center-monitor-chassis">
      <div class="crt-screen-bezel">
        <div class="crt-screen-inner">
          <!-- Monitor Header -->
          <div class="crt-header">
            <div class="header-title-group">
              <span class="font-cinzel deck-title">AGENT DECK &bull; ASPASIA OBSERVER<span class="deck-tr">AJAN GÜVERTESİ • ASPASİA GÖZLEM</span></span>
              <span class="sound-wave-icon {isSending ? 'wave-active' : ''}">)))</span>
            </div>

            <!-- Tabs: ASPASIA, VISION, OSINT, FRICTION, VERIFY -->
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
          </div>

          <!-- Active Route Bar (Dinamik Telemetri) -->
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

          <!-- Hedef Profil Girişi (Kompakt Çubuk) -->
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
              {$isProcessing ? 'İŞLENİYOR (BUSY)...' : 'BAŞLAT (LAUNCH)'}
            </button>
          </div>

          <!-- Chat Dialogue Feed -->
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

          <!-- Input Bar -->
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
        </div>
      </div>
    </main>

    <!-- SAĞ PANEL: AJAN ZİNCİRİ (KULLANICININ VERDİĞİ KODUN TAM VE EKSİKSİZ UYARLAMASI) -->
    <aside class="right-agent-rack">
      <div class="rack-header">
        <span class="font-cinzel rack-title">AJAN ZİNCİRİ<span class="rack-tr">AGENT CHAIN · 13 CANLI AJAN</span></span>
        <div class="jewel-led led-on-green"></div>
      </div>

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

              <div class="agent-info-meta">
                <div class="agent-title-text">{agent.name}</div>
                <div class="agent-tr">{agentTr[agent.id] || ''}</div>
                <div class="agent-spec-lines">
                  <div><b style="color: var(--gold);">DURUM:</b> {isCompleted ? 'TAMAM' : isHalted ? 'DURDU' : isRunning ? 'ÇALIŞIYOR' : 'BEKLİYOR'}</div>
                  <div><b style="color: var(--gold);">MODEL:</b> {liveModel}</div>
                  <div><b style="color: var(--gold);">YOL:</b> {liveVia}</div>
                  <div><b style="color: var(--gold);">ÇAĞRI:</b> {provCallId ? provCallId.slice(0, 14) + '…' : '—'}</div>
                </div>
              </div>

              <!-- İlerleme Çubuğu -->
              <div class="agent-meter-bar">
                <div 
                  class="meter-fill {isCompleted ? 'fill-green' : isRunning ? 'fill-running-red' : isHalted ? 'fill-red' : 'fill-dim'}"
                  style="width: {isCompleted ? '100%' : isRunning ? '65%' : isHalted ? '100%' : '0%'};"
                ></div>
              </div>
            </div>
          </div>
        {/each}
      </div>
    </aside>

  </div>

  <!-- ==================== ALT SIRA: 8 ADLİ DAMGA YUVARLAK BUTONU ==================== -->
  <footer class="bottom-forensic-bar">
    <div class="forensic-buttons-track">
      <button class="round-brass-btn {activeForensicModal === 'follower' ? 'btn-active' : ''}" on:click={() => toggleForensic('follower')}>
        <div class="btn-inner-disc">
          <span class="forensic-icon">🕸️</span>
        </div>
        <span class="forensic-name">FOLLOWER</span>
        <span class="forensic-tr">TAKİPÇİ</span>
      </button>

      <button class="round-brass-btn {activeForensicModal === 'timing' ? 'btn-active' : ''}" on:click={() => toggleForensic('timing')}>
        <div class="btn-inner-disc">
          <span class="forensic-icon">⏱️</span>
        </div>
        <span class="forensic-name">TIMING</span>
        <span class="forensic-tr">ZAMANLAMA</span>
      </button>

      <button class="round-brass-btn {activeForensicModal === 'depth' ? 'btn-active' : ''}" on:click={() => toggleForensic('depth')}>
        <div class="btn-inner-disc">
          <span class="forensic-icon">📑</span>
        </div>
        <span class="forensic-name">DEPTH</span>
        <span class="forensic-tr">DERİNLİK</span>
      </button>

      <button class="round-brass-btn {activeForensicModal === 'visual' ? 'btn-active' : ''}" on:click={() => toggleForensic('visual')}>
        <div class="btn-inner-disc">
          <span class="forensic-icon">👁️</span>
        </div>
        <span class="forensic-name">VISUAL</span>
        <span class="forensic-tr">GÖRSEL</span>
      </button>

      <button class="round-brass-btn {activeForensicModal === 'shadow' ? 'btn-active' : ''}" on:click={() => toggleForensic('shadow')}>
        <div class="btn-inner-disc">
          <span class="forensic-icon">🎭</span>
        </div>
        <span class="forensic-name">SHADOW</span>
        <span class="forensic-tr">GÖLGE</span>
      </button>

      <button class="round-brass-btn {activeForensicModal === 'osint' ? 'btn-active' : ''}" on:click={() => toggleForensic('osint')}>
        <div class="btn-inner-disc">
          <span class="forensic-icon">🌐</span>
        </div>
        <span class="forensic-name">OSINT</span>
        <span class="forensic-tr">OSINT</span>
      </button>

      <button class="round-brass-btn {activeForensicModal === 'resonance' ? 'btn-active' : ''}" on:click={() => toggleForensic('resonance')}>
        <div class="btn-inner-disc">
          <span class="forensic-icon">🎯</span>
        </div>
        <span class="forensic-name">RESONANCE</span>
        <span class="forensic-tr">REZONANS</span>
      </button>

      <button class="round-brass-btn {activeForensicModal === 'pillars' ? 'btn-active' : ''}" on:click={() => toggleForensic('pillars')}>
        <div class="btn-inner-disc">
          <span class="forensic-icon">◈</span>
        </div>
        <span class="forensic-name">7 PILLARS</span>
        <span class="forensic-tr">7 SÜTUN</span>
      </button>
    </div>
  </footer>

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
     HERETIC VICTORIAN STEAMPUNK INSTRUMENT CONSOLE CSS
     =================================================== */
  .steampunk-console {
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
    gap: 18px;
    position: relative;
  }

  /* --- TOP DIALS ROW (canlı göstergeler + split-flap pano) --- */
  .top-dials-row {
    background: 
      linear-gradient(180deg, rgba(255,255,255,0.06) 0%, transparent 30%, rgba(0,0,0,0.4) 100%),
      linear-gradient(90deg, #1f1208 0%, #2b190d 50%, #1f1208 100%);
    border: 1px solid #5a3d1c;
    box-shadow: 
      inset 0 1px 2px rgba(255,235,175,0.25),
      inset 0 -2px 5px rgba(0,0,0,0.8),
      0 4px 14px rgba(0,0,0,0.65);
    border-radius: 10px;
    padding: 14px 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 20px;
    flex-wrap: wrap;
    position: relative;
  }
  .dials-cluster {
    display: flex;
    gap: 28px;
    flex-wrap: wrap;
    justify-content: center;
    align-items: flex-start;
  }

  /* --- MAIN COCKPIT 3-COLUMN GRID --- */
  .main-cockpit-grid {
    display: grid;
    grid-template-columns: 215px 1fr 285px;
    gap: 18px;
    align-items: stretch;
  }

  /* --- LEFT HARDWARE RACK --- */
  .left-hardware-rack {
    background: 
      linear-gradient(90deg, #2b1a0e 0%, #1c1008 8%, #140b05 92%, #2b1a0e 100%);
    border: 2px solid #6b4b24;
    border-radius: 10px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    box-shadow: 
      inset 0 2px 4px rgba(255,235,175,0.25),
      inset 0 0 25px rgba(0,0,0,0.9),
      0 6px 16px rgba(0,0,0,0.7);
    position: relative;
  }

  .hardware-module {
    background: 
      linear-gradient(135deg, rgba(255,255,255,0.06) 0%, transparent 40%, rgba(0,0,0,0.4) 100%),
      linear-gradient(180deg, #2a1a0f 0%, #180e07 100%);
    border: 1px solid #664622;
    border-radius: 8px;
    padding: 10px 8px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    box-shadow: 
      inset 1px 1px 1px rgba(255,235,175,0.25),
      inset -1px -1px 2px rgba(0,0,0,0.8),
      0 3px 8px rgba(0,0,0,0.6);
    position: relative;
  }

  .module-title {
    font-family: 'Cinzel', serif;
    font-size: 8px;
    font-weight: 800;
    color: var(--gold);
    text-shadow: 0 1px 2px rgba(0,0,0,0.9);
    letter-spacing: 0.8px;
    margin-bottom: 6px;
  }

  /* Knobs (Throttle, Mixture, Prop) */
  .knobs-row {
    display: flex;
    justify-content: space-around;
    width: 100%;
    gap: 6px;
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
    background: 
      radial-gradient(circle at 35% 30%, #fef0be 0%, #d4af37 25%, #8c6728 65%, #3a240d 100%);
    border: 2px solid #5a3d1c;
    box-shadow: 
      0 4px 8px rgba(0,0,0,0.85),
      0 0 0 2px #221307,
      0 0 0 3px #8c6728,
      inset 0 1px 2px rgba(255,255,255,0.7),
      inset 0 -2px 4px rgba(0,0,0,0.8);
    cursor: pointer;
    position: relative;
    transition: transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1), filter 0.15s;
  }
  .knurled-knob:hover {
    filter: brightness(1.15);
  }
  .knurled-knob:active {
    transform: scale(0.96);
  }
  .knob-notch {
    position: absolute;
    top: 2px;
    left: 16px;
    width: 4px;
    height: 9px;
    background: #ffffff;
    border-radius: 1px;
    box-shadow: 0 0 3px rgba(255,255,255,0.9), 0 1px 2px #000;
  }
  .knob-label {
    font-size: 7px;
    color: var(--text-dim);
    font-weight: 700;
  }

  /* Switches (ToggleSwitch bileşenleri; 4'lü sıra) */
  .switches-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    width: 100%;
    gap: 4px;
  }
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
    box-shadow: inset 0 1px 3px rgba(0,0,0,0.8);
  }
  .estop-module {
    padding: 6px 10px 10px;
  }
  .jewel-led {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    border: 1px solid #160d04;
    box-shadow: inset 0 1px 2px rgba(255,255,255,0.5);
  }
  .led-on-green {
    background: #10b981;
    box-shadow: 0 0 10px #10b981, 0 0 2px #fff, inset 0 1px 2px #fff;
  }

  /* Mechanical Odometer */
  .odometer-module {
    flex-direction: row;
    justify-content: space-between;
    padding: 8px 12px;
  }
  .counter-tag {
    font-size: 8px;
    font-weight: 800;
    color: var(--gold);
    text-shadow: 0 1px 2px #000;
  }
  .odometer-bezel {
    background: #0d0703;
    border: 2px solid #5a3d1c;
    padding: 3px 8px;
    border-radius: 4px;
    box-shadow: inset 0 0 8px #000, 0 2px 4px rgba(0,0,0,0.6);
  }
  .odometer-digits {
    display: flex;
    gap: 3px;
  }
  .odo-digit {
    background: linear-gradient(180deg, #1f1f1f 0%, #111111 48%, #000000 52%, #141414 100%);
    color: #fff;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    font-weight: 800;
    padding: 2px 4px;
    border-radius: 2px;
    border: 1px solid #333;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.2), 0 1px 2px #000;
  }

  /* Status Lamp */
  .status-module {
    flex-direction: row;
    justify-content: space-between;
    padding: 8px 14px;
  }
  .status-title {
    font-size: 8px;
    font-weight: 800;
    color: var(--gold);
    text-align: left;
    line-height: 1.2;
    text-shadow: 0 1px 2px #000;
  }
  .big-jewel-lamp {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #fff 0%, #34d399 25%, #059669 65%, #064e3b 100%);
    border: 2px solid #5a3d1c;
    box-shadow: 0 0 15px #10b981, inset 0 1px 2px #fff;
  }
  .lamp-pulse {
    animation: lampBlink 1s infinite alternate;
  }
  @keyframes lampBlink {
    from { opacity: 0.5; box-shadow: 0 0 6px #10b981; }
    to { opacity: 1; box-shadow: 0 0 20px #10b981, 0 0 30px rgba(16, 185, 129, 0.4); }
  }

  /* Token Plaque */
  .token-plaque {
    position: relative;
    background: 
      linear-gradient(180deg, #fef0be 0%, #d4af37 25%, #8c6728 65%, #3a240d 100%);
    border: 1px solid #ffecb3;
    color: #120904;
    padding: 8px;
    box-shadow: 
      inset 0 1px 1px rgba(255,255,255,0.7),
      inset 0 -1px 2px rgba(0,0,0,0.6),
      0 4px 8px rgba(0,0,0,0.7);
    border-radius: 4px;
  }
  .plaque-screw {
    position: absolute;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #3a220e, #140b05);
    border: 0.5px solid #ffecb3;
    box-shadow: inset 0 1px 0 #000;
  }
  .plaque-screw.top-left { top: 3px; left: 3px; }
  .plaque-screw.top-right { top: 3px; right: 3px; }
  .plaque-screw.btm-left { bottom: 3px; left: 3px; }
  .plaque-screw.btm-right { bottom: 3px; right: 3px; }
  .plaque-header { font-family: 'Cinzel', serif; font-size: 8px; font-weight: 900; letter-spacing: 0.6px; }
  .plaque-code { font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
  .plaque-sub { font-family: 'JetBrains Mono', monospace; font-size: 7px; font-weight: 500; letter-spacing: 0.5px; opacity: 0.85; margin-top: 2px; }

  /* =========================================================
     CENTER MONITOR CHASSIS & VINTAGE CRT DISPLAY
     ========================================================= */
  .center-monitor-chassis {
    display: flex;
    flex-direction: column;
  }

  .crt-screen-bezel {
    background: 
      linear-gradient(135deg, rgba(255,255,255,0.08) 0%, transparent 45%, rgba(0,0,0,0.6) 100%),
      linear-gradient(180deg, #2b1a0d 0%, #170d06 100%);
    border: 4px solid #7a542b;
    border-radius: 14px;
    padding: 12px;
    box-shadow: 
      inset 0 2px 4px rgba(255,235,175,0.35),
      inset 0 -3px 6px rgba(0,0,0,0.9),
      inset 0 0 25px rgba(0,0,0,0.85),
      0 8px 24px rgba(0,0,0,0.8);
    height: 100%;
    display: flex;
    flex-direction: column;
    position: relative;
  }

  .crt-screen-inner {
    position: relative;
    background: 
      /* Curved Glass Reflection / Specular Highlight */
      radial-gradient(ellipse at 50% 12%, rgba(255, 255, 255, 0.12) 0%, transparent 60%),
      /* Deep CRT Vignette / Curved Tube Shadow */
      radial-gradient(ellipse at 50% 50%, rgba(16, 28, 20, 0.95) 0%, rgba(8, 14, 10, 0.98) 70%, #030604 100%);
    border: 3px solid #142018;
    border-radius: 10px;
    padding: 14px;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 10px;
    box-shadow: 
      inset 0 0 45px rgba(0, 0, 0, 0.95),
      inset 0 0 15px rgba(56, 239, 125, 0.15),
      0 0 8px rgba(0, 0, 0, 0.9);
    overflow: hidden;
  }

  /* Authentic CRT Scanline Overlay */
  .crt-screen-inner::before {
    content: " ";
    display: block;
    position: absolute;
    top: 0; left: 0; bottom: 0; right: 0;
    background: 
      linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.35) 50%), 
      linear-gradient(90deg, rgba(255, 0, 0, 0.02), rgba(0, 255, 0, 0.01), rgba(0, 0, 255, 0.02));
    z-index: 2;
    background-size: 100% 3px, 6px 100%;
    pointer-events: none;
    opacity: 0.85;
  }

  .crt-header {
    display: flex;
    flex-direction: column;
    gap: 8px;
    border-bottom: 1px solid #1f3829;
    padding-bottom: 8px;
    position: relative;
    z-index: 4;
  }

  .header-title-group {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .deck-title {
    font-size: 12px;
    font-weight: 800;
    color: var(--text-phosphor);
    text-shadow: 0 0 6px rgba(56, 239, 125, 0.7);
    letter-spacing: 1.2px;
  }

  .sound-wave-icon {
    color: #10b981;
    font-weight: 900;
    font-size: 13px;
    text-shadow: 0 0 6px #10b981;
  }
  .wave-active {
    animation: wavePulse 0.5s infinite alternate;
  }
  @keyframes wavePulse {
    from { color: #10b981; text-shadow: 0 0 4px #10b981; }
    to { color: #34d399; text-shadow: 0 0 14px #34d399, 0 0 25px rgba(52, 211, 153, 0.6); }
  }

  /* Monitor Tabs as Mechanical Pushbuttons */
  .monitor-tabs-bar {
    display: flex;
    gap: 6px;
    position: relative;
    z-index: 4;
  }
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
    box-shadow: 0 2px 4px rgba(0,0,0,0.6), inset 0 1px 1px rgba(255,255,255,0.1);
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
    box-shadow: 
      0 0 12px rgba(56, 239, 125, 0.4),
      inset 0 1px 2px rgba(255,255,255,0.3);
    text-shadow: 0 0 6px rgba(56, 239, 125, 0.8);
  }

  /* Active Route Subbar */
  .active-route-subbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #08110b;
    border: 1px solid #163020;
    padding: 5px 10px;
    border-radius: 4px;
    font-size: 8px;
    letter-spacing: 0.4px;
    position: relative;
    z-index: 4;
  }
  .route-text {
    color: #729a80;
  }
  .route-dots {
    display: flex;
    gap: 5px;
  }
  .dot-led {
    width: 6px;
    height: 6px;
    border-radius: 50%;
  }
  .dot-green { background: #10b981; box-shadow: 0 0 6px #10b981; }
  .dot-amber { background: #f59e0b; box-shadow: 0 0 6px #f59e0b; }

  /* Quick Target Strip */
  .quick-target-strip {
    display: flex;
    gap: 8px;
    position: relative;
    z-index: 4;
  }
  .quick-target-strip input {
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
  .launch-btn {
    font-family: 'Cinzel', serif;
    font-size: 10px;
    font-weight: 800;
    padding: 7px 16px;
    border-radius: 5px;
    cursor: pointer;
    transition: all 0.12s ease;
  }
  .btn-armed {
    background: linear-gradient(180deg, #34d399 0%, #10b981 40%, #065f46 100%);
    color: #062b1e;
    text-shadow: 0 1px 0 rgba(255,255,255,0.5);
    border: 1px solid #6ee7b7;
    box-shadow: 
      0 4px 10px rgba(0,0,0,0.7),
      0 0 14px rgba(16,185,129,0.6),
      inset 0 1px 2px #fff;
  }
  .btn-armed:hover {
    filter: brightness(1.15);
    transform: translateY(-1px);
  }
  .btn-armed:active {
    transform: translateY(2px);
    box-shadow: inset 0 2px 4px #000;
  }
  .btn-unarmed {
    background: linear-gradient(180deg, #2b1f13 0%, #170d06 100%);
    color: var(--text-muted);
    border: 1px solid #4a3017;
    box-shadow: inset 0 1px 2px #000;
  }

  /* Dialogue Area */
  .dialogue-scroll-area {
    flex: 1;
    min-height: 250px;
    max-height: 320px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-right: 6px;
    position: relative;
    z-index: 4;
  }
  .chat-row {
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }
  .row-user {
    flex-direction: row-reverse;
  }
  .avatar-disc {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #4a2e12, #1f1309);
    border: 1px solid #b8860b;
    box-shadow: 0 2px 5px rgba(0,0,0,0.8), inset 0 1px 1px rgba(255,255,255,0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .avatar-glyph {
    font-size: 14px;
  }
  .bubble-body {
    background: rgba(14, 26, 18, 0.9);
    border: 1px solid #1f452e;
    border-radius: 6px;
    padding: 9px 12px;
    max-width: 85%;
    box-shadow: 
      inset 0 1px 2px rgba(56, 239, 125, 0.15),
      0 3px 8px rgba(0,0,0,0.7);
  }
  .row-user .bubble-body {
    background: rgba(38, 22, 10, 0.9);
    border-color: #8c5d28;
    box-shadow: 
      inset 0 1px 2px rgba(255, 194, 71, 0.2),
      0 3px 8px rgba(0,0,0,0.7);
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
  .check-marks {
    color: #10b981;
    text-shadow: 0 0 4px #10b981;
  }

  /* Monitor Input Tray */
  .monitor-input-tray {
    display: flex;
    gap: 8px;
    align-items: center;
    border-top: 1px solid #1f3829;
    padding-top: 10px;
    position: relative;
    z-index: 4;
  }
  .cam-btn {
    background: linear-gradient(180deg, #2b1f13 0%, #150c05 100%);
    border: 1px solid #5a3d1c;
    color: #fff;
    padding: 7px 11px;
    border-radius: 4px;
    cursor: pointer;
    box-shadow: 0 2px 4px rgba(0,0,0,0.6), inset 0 1px 1px rgba(255,255,255,0.2);
    transition: all 0.15s;
  }
  .cam-btn:hover {
    border-color: var(--gold);
    transform: translateY(-1px);
  }
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
    background: 
      linear-gradient(180deg, #fff3c8 0%, #e2b94c 18%, #ad8228 65%, #634612 100%);
    color: #1a0f04;
    text-shadow: 0 1px 0 rgba(255,255,255,0.6);
    font-family: 'Cinzel', serif;
    font-size: 11px;
    font-weight: 800;
    padding: 7px 18px;
    border-radius: 5px;
    border: 1px solid #fff5cf;
    cursor: pointer;
    box-shadow: 
      0 4px 8px rgba(0,0,0,0.7),
      inset 0 1px 2px rgba(255,255,255,0.9),
      inset 0 -2px 3px rgba(0,0,0,0.6);
    transition: all 0.12s ease;
  }
  .brass-send-btn:hover:not(:disabled) {
    filter: brightness(1.15);
    transform: translateY(-1px);
  }
  .brass-send-btn:active:not(:disabled) {
    transform: translateY(2px);
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.8);
  }
  .brass-send-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
    filter: grayscale(0.5);
  }

  /* --- RIGHT AGENT RACK --- */
  .right-agent-rack {
    background: 
      linear-gradient(90deg, #2b1a0e 0%, #1c1008 8%, #140b05 92%, #2b1a0e 100%);
    border: 2px solid #6b4b24;
    border-radius: 10px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    box-shadow: 
      inset 0 2px 4px rgba(255,235,175,0.25),
      inset 0 0 25px rgba(0,0,0,0.9),
      0 6px 16px rgba(0,0,0,0.7);
    max-height: 520px;
    overflow-y: auto;
  }

  .rack-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #4a3017;
    padding-bottom: 8px;
  }
  .rack-title {
    font-size: 11px;
    font-weight: 800;
    color: var(--gold);
    text-shadow: 0 1px 2px #000;
    letter-spacing: 1px;
  }

  .agent-cards-stack {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }

  .agent-instrument-card {
    background: 
      linear-gradient(135deg, rgba(255,255,255,0.05) 0%, transparent 40%, rgba(0,0,0,0.4) 100%),
      linear-gradient(180deg, #201309 0%, #130a04 100%);
    border: 1px solid #54391c;
    border-radius: 6px;
    padding: 7px 10px;
    box-shadow: 
      inset 1px 1px 1px rgba(255,235,175,0.18),
      inset -1px -1px 2px rgba(0,0,0,0.7),
      0 2px 5px rgba(0,0,0,0.6);
    transition: all 0.2s ease;
    position: relative;
  }
  .agent-instrument-card:hover {
    border-color: var(--brass-bright);
    transform: translateX(-2px);
    box-shadow: 
      inset 1px 1px 1px rgba(255,235,175,0.3),
      0 4px 10px rgba(0,0,0,0.8),
      0 0 10px rgba(212,175,55,0.25);
  }
  .card-running {
    border-color: #ef4444 !important;
    background: linear-gradient(180deg, #2d1008 0%, #180803 100%) !important;
    box-shadow: 0 0 12px rgba(239,68,68,0.45), inset 0 0 8px rgba(239,68,68,0.2) !important;
    animation: runningCardPulse 1.2s infinite alternate;
  }
  @keyframes runningCardPulse {
    from { border-color: #ef4444; box-shadow: 0 0 6px rgba(239,68,68,0.3); }
    to { border-color: #f87171; box-shadow: 0 0 16px rgba(239,68,68,0.7); }
  }
  .card-done {
    border-color: #10b981 !important;
  }

  .card-top-line {
    display: flex;
    align-items: center;
    gap: 9px;
  }

  .agent-medal {
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #ffd978 0%, #b8860b 45%, #523714 85%, #241607 100%);
    border: 1px solid #ffecb3;
    box-shadow: 
      0 2px 5px rgba(0,0,0,0.8),
      inset 0 1px 1px rgba(255,255,255,0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .medal-pulse-red {
    border-color: #ef4444;
    box-shadow: 0 0 10px #ef4444;
    animation: medalBlink 1s infinite alternate;
  }
  @keyframes medalBlink {
    from { box-shadow: 0 0 3px #ef4444; }
    to { box-shadow: 0 0 12px #ef4444; }
  }
  .medal-symbol {
    font-size: 12px;
  }

  .agent-info-meta {
    flex: 1;
    min-width: 0;
  }
  .agent-title-text {
    font-family: 'Cinzel', serif;
    font-size: 9px;
    font-weight: 800;
    color: #f5edd8;
    text-shadow: 0 1px 2px #000;
    letter-spacing: 0.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .agent-spec-lines {
    font-size: 7px;
    color: var(--text-muted);
    line-height: 1.3;
    margin-top: 2px;
  }

  .agent-meter-bar {
    width: 52px;
    height: 6px;
    background: #000;
    border: 1px solid #4a3017;
    border-radius: 3px;
    overflow: hidden;
    flex-shrink: 0;
    box-shadow: inset 0 1px 2px #000;
  }
  .meter-fill {
    height: 100%;
    transition: width 0.3s;
  }
  .fill-green {
    background: linear-gradient(90deg, #059669, #10b981);
    box-shadow: 0 0 8px #10b981;
  }
  .fill-running-red {
    background: linear-gradient(90deg, #ef4444, #f59e0b);
    box-shadow: 0 0 10px #ef4444;
    animation: barPulse 1s infinite alternate;
  }
  @keyframes barPulse {
    from { opacity: 0.7; }
    to { opacity: 1; }
  }
  .fill-red { background: #ef4444; }
  .fill-dim { background: transparent; }

  /* --- İKİ DİLLİ ALT SATIRLAR (TR) --- */
  .module-tr { display: block; font-family: 'JetBrains Mono', monospace; font-size: 7px; font-weight: 500; color: var(--text-muted); letter-spacing: 0.4px; margin-top: 1px; }
  .knob-tr { font-family: 'JetBrains Mono', monospace; font-size: 6px; font-weight: 700; color: var(--text-muted); }
  .tr-micro { font-family: 'JetBrains Mono', monospace; font-size: 7px; color: var(--text-muted); }
  .deck-tr { display: block; font-family: 'JetBrains Mono', monospace; font-size: 7px; font-weight: 500; color: var(--text-muted); letter-spacing: 0.8px; margin-top: 1px; }
  .tab-tr { display: block; font-family: 'JetBrains Mono', monospace; font-size: 6px; font-weight: 500; color: var(--text-muted); }
  .rack-tr { display: block; font-family: 'JetBrains Mono', monospace; font-size: 7px; font-weight: 500; color: var(--text-muted); letter-spacing: 0.8px; }
  .agent-tr { font-family: 'JetBrains Mono', monospace; font-size: 7px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .forensic-tr { font-family: 'JetBrains Mono', monospace; font-size: 6px; font-weight: 700; color: var(--text-muted); }
  .plaque-tr { font-family: 'JetBrains Mono', monospace; font-size: 6px; font-weight: 700; letter-spacing: 0.5px; opacity: 0.8; }

  /* --- BOTTOM FORENSIC BAR --- */
  .bottom-forensic-bar {
    background: 
      linear-gradient(180deg, rgba(255,255,255,0.06) 0%, transparent 30%, rgba(0,0,0,0.5) 100%),
      linear-gradient(90deg, #1f1208 0%, #2b1a0d 50%, #1f1208 100%);
    border: 2px solid #6b4b24;
    border-radius: 10px;
    padding: 12px 16px;
    box-shadow: 
      inset 0 2px 4px rgba(255,235,175,0.25),
      inset 0 0 20px rgba(0,0,0,0.85),
      0 4px 12px rgba(0,0,0,0.7);
  }
  .forensic-buttons-track {
    display: flex;
    justify-content: space-around;
    align-items: center;
  }
  .round-brass-btn {
    background: transparent;
    border: none;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    transition: transform 0.15s;
  }
  .round-brass-btn:hover {
    transform: translateY(-2px);
  }
  .btn-inner-disc {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: 
      radial-gradient(circle at 35% 30%, #fef0be 0%, #d4af37 25%, #8c6728 65%, #3a240d 100%);
    border: 2px solid #ffecb3;
    box-shadow: 
      0 5px 12px rgba(0,0,0,0.85),
      0 0 0 2px #221307,
      0 0 0 4px #7a542b,
      inset 0 2px 3px rgba(255,255,255,0.8),
      inset 0 -3px 5px rgba(0,0,0,0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.12s ease;
  }
  .round-brass-btn:hover .btn-inner-disc {
    filter: brightness(1.15);
    transform: translateY(-2px);
    box-shadow: 
      0 7px 16px rgba(0,0,0,0.9),
      0 0 0 2px #221307,
      0 0 0 4px #d4af37,
      inset 0 2px 3px rgba(255,255,255,0.9);
  }
  .round-brass-btn:active .btn-inner-disc {
    transform: translateY(2px) scale(0.96);
    box-shadow: 
      0 1px 3px rgba(0,0,0,0.9),
      0 0 0 2px #221307,
      0 0 0 3px #7a542b,
      inset 0 3px 6px rgba(0,0,0,0.95);
  }
  .round-brass-btn.btn-active .btn-inner-disc {
    border-color: #38ef7d;
    box-shadow: 
      0 0 16px rgba(56,239,125,0.7),
      0 0 0 2px #221307,
      0 0 0 4px #38ef7d,
      inset 0 0 10px rgba(56,239,125,0.5);
  }
  .forensic-icon {
    font-size: 19px;
  }
  .forensic-name {
    font-family: 'Cinzel', serif;
    font-size: 8px;
    font-weight: 800;
    color: var(--gold);
    text-shadow: 0 1px 2px #000;
    letter-spacing: 0.8px;
  }

  /* --- FORENSIC MODAL POPUP --- */
  .forensic-modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0,0,0,0.85);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
  }
  .forensic-modal-card {
    background: 
      linear-gradient(180deg, #201309 0%, #120904 100%);
    border: 3px solid var(--gold);
    border-radius: 10px;
    width: 90%;
    max-width: 520px;
    box-shadow: 
      0 0 0 4px #26170b,
      0 20px 50px rgba(0,0,0,0.95);
    overflow: hidden;
  }
  .modal-header-brass {
    background: linear-gradient(180deg, #fff3c8 0%, #d4af37 30%, #8a6332 100%);
    color: #150c04;
    text-shadow: 0 1px 0 rgba(255,255,255,0.6);
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
  .modal-close:hover {
    background: rgba(0,0,0,0.2);
  }
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
</style>
