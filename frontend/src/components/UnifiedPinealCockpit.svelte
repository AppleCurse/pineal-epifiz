<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import Icon from './Icon.svelte';
  import TaskEvidence from './TaskEvidence.svelte';
  import CockpitHeader from './cockpit/CockpitHeader.svelte';
  import CockpitSidebar from './cockpit/CockpitSidebar.svelte';
  import HomeDashboardTab from './cockpit/HomeDashboardTab.svelte';
  import CrossScanTab from './cockpit/CrossScanTab.svelte';
  import AspasiaChatTab from './cockpit/AspasiaChatTab.svelte';
  import LilithStudioTab from './cockpit/LilithStudioTab.svelte';
  import CompanyTab from './cockpit/CompanyTab.svelte';
  import MediaVoiceTab from './cockpit/MediaVoiceTab.svelte';
  import BrowserControlTab from './cockpit/BrowserControlTab.svelte';
  import ReportsMemoryTab from './cockpit/ReportsMemoryTab.svelte';
  import SystemToolsTab from './cockpit/SystemToolsTab.svelte';
  import SettingsModal from './cockpit/SettingsModal.svelte';
  import HistoryReportModal from './cockpit/HistoryReportModal.svelte';
  import DemoAndTermsModal from './cockpit/DemoAndTermsModal.svelte';

  import { activeTab } from '../lib/theme';
  import {
    setApiToken,
    currentApiToken,
    apiFetch,
    isAuthFailure,
    clientId,
    logs,
    taskStatus,
    speechState,
    isProcessing,
    armEngaged,
    agentStatuses,
    vaultLocked,
    agentStatusSource,
    mergeTaskSnapshot,
    missionElapsed,
    activeTargetUrl,
  } from '../store';
  import { startHealthPoll, stopHealthPoll } from '../lib/telemetry';
  import { playClick, playHalt, playRunning } from '../lib/consoleAudio';
  import { hasEvidence, buildPillarSummaries, evidenceChainToReportItems } from '../lib/evidence';
  import { taskRuns } from '../lib/taskRunStatus';
  import { checkVaultStatus, vaultExists } from '../lib/tauriBridge';

  const INSUFFICIENT_EVIDENCE = 'YETERSİZ KANIT';
  const HONEST_EMPTY_LABELS = {
    missing: 'veri yok',
    unmeasured: 'ölçülmedi',
    noEvidence: 'kanıt yok',
  };

  // --- 1. BAŞ DANIŞMANLAR (ASPASIA & LILITH) ---
  const SOVEREIGNS = [
    {
      id: 'aspasia',
      name: 'ASPASIA',
      short: 'ASPASIA',
      role: 'Baş Stratejist & Argüman Analisti',
      title: 'Sokratik Retorik, Hakikat Aynası ve Empatik Strateji',
      icon: 'diamond',
      accent: '#10b981',
      badge: 'STRATEJİ',
      presets: [
        'Hedefle olan uyumu ve rezonansını stratejik olarak özetle',
        'Hedefin kalkanını kırmadan sahici bir temas stratejisi kur',
        'Kullanıcının frekansına ayna tutarak eksik/kuvvetli yönleri değerlendir',
      ],
    },
    {
      id: 'lilith',
      name: 'LILITH',
      short: 'LILITH',
      role: 'Büyüme & Nörobilim',
      title: 'Dopamin Kancası, Amigdala Uyarımı, Maske Yırtıcı ve Viralite',
      icon: 'sparkle',
      accent: '#ec4899',
      badge: 'BÜYÜME',
      presets: [
        'Dopaminerjik ödül tahmin hatasıyla beklenti kırıcı viral kanca kurgula',
        'Hedefin vitrindeki duruşu ile bastırılmış narsistik dürtüleri analiz et',
        'Amigdala uyarımı ve kayıptan kaçınma alışkanlığıyla hipnotik bir ilk temas yaz',
      ],
    },
  ];

  // --- 2. 12 UZMAN SAHA AJANI ---
  const FIELD_AGENTS = [
    { id: 'osint_investigator', name: 'Açık Kaynak', short: 'OSINT', icon: 'target', color: '#8b5cf6', desc: 'Açık kaynak, web ve dijital ayak izi taraması', preset: 'Tüm web platformlarında çapraz kullanıcı adı ve dijital parmak izi tara' },
    { id: 'depth_analyst', name: 'Derinlik', short: 'DEPTH', icon: 'layers', color: '#eab308', desc: 'Gerçeklik endeksi ve kişilik derinliği analizi', preset: 'Kişilik özgünlüğü ve sosyal medyadaki yapay maskeyi derinlemesine incele' },
    { id: 'human_behavior', name: 'Davranış', short: 'BEHAVIOR', icon: 'diamond', color: '#f59e0b', desc: 'Dijital cold reading ve akıl tendonu analizi', preset: 'Hedefin alışkanlıklarını, ritüellerini ve zayıf hassasiyet noktasını çıkar' },
    { id: 'friction_detector', name: 'Sınırlar', short: 'FRICTION', icon: 'triangle-up', color: '#ef4444', desc: 'Sınırlar, hassasiyet ve sürtünme dedektörü', preset: 'Konuşulmaması gereken kırmızı çizgileri ve sürtünme tetikleyicilerini belirle' },
    { id: 'pattern_interrupt', name: 'Ezber Bozan', short: 'PATTERN', icon: 'refresh', color: '#dc2626', desc: 'Beklenti kırma ve temas stratejisi', preset: 'Sıradan mesajların ötesinde ezber bozan bir kalıp kırıcı ilk cümle kur' },
    { id: 'passion_mapper', name: 'Tutku Haritası', short: 'PASSION', icon: 'square', color: '#eab308', desc: 'Tutku, neşe ve akış tetikleyicileri haritası', preset: 'Hedefin gözlerini parlatan, gerçek tutkularını ve akış alanlarını haritala' },
    { id: 'cognitive_profiler', name: 'Dil ve Üslup', short: 'COGNITIVE', icon: 'hexagon', color: '#06b6d4', desc: 'Bilişsel dil, üslup ve tonlama profili', preset: 'Hedefin kelime dağarcığını, resmiyet derecesini ve iletişim ritmini modelle' },
    { id: 'mirror_truth', name: 'Ayna', short: 'MIRROR', icon: 'circle-hollow', color: '#10b981', desc: 'İç-z-frekans yansıtma ve kullanıcı uyumu', preset: 'Kullanıcının ritüelleri ile hedefin profili arasındaki doğal frekans bağını test et' },
    { id: 'autonomous_verifier', name: 'Doğrulayan', short: 'VERIFIER', icon: 'triangle-down', color: '#a855f7', desc: 'Otonom çapraz doğrulama ve hakem paneli', preset: 'Takipçi/beğeni oranlarındaki bot veya manipülasyon şüphesini denetle' },
    { id: 'resonance_calculator', name: 'Uyum Hesabı', short: 'CALC', icon: 'star', color: '#3b82f6', desc: 'Numpy vektörel rezonans ve açı hesaplaması', preset: 'Çok boyutlu semantik uzayda rezonans ve uyum açısını matematiksel hesapla' },
    { id: 'authenticity_auditor', name: 'Sahicilik', short: 'AUTH', icon: 'star', color: '#14b8a6', desc: 'Orijinallik ve güvenilirlik denetimi', preset: 'Gönderilerin doğallığı ile alıntı/kurgu oranını ölçerek maske puanı çıkar' },
    { id: 'resonance_synthesizer', name: 'Köprü', short: 'SYNTH', icon: 'sparkle', color: '#ec4899', desc: 'Sahici köprü sentezi ve önerilen ilk mesaj', preset: 'Tüm bulguları sentezleyerek hedefe ulaşacak en etkili ve zarif köprüyü inşa et' },
  ];

  // --- 3. 7 ANA ANALİZ SÜTUNU ---
  const PILLARS = [
    { id: 'follower', label: 'FOLLOWER', tr: 'TAKİPÇİ', icon: 'diamond', color: '#8b5cf6' },
    { id: 'timing', label: 'TIMING', tr: 'ZAMAN', icon: 'clock', color: '#f59e0b' },
    { id: 'depth', label: 'DEPTH', tr: 'DERİNLİK', icon: 'layers', color: '#ec4899' },
    { id: 'visual', label: 'VISUAL', tr: 'GÖRSEL', icon: 'eye', color: '#06b6d4' },
    { id: 'shadow', label: 'SHADOW', tr: 'GÖLGE', icon: 'sparkle', color: '#a855f7' },
    { id: 'osint', label: 'OSINT', tr: 'OSINT', icon: 'target', color: '#10b981' },
    { id: 'resonance', label: 'RESONANCE', tr: 'REZONANS', icon: 'star', color: '#ec4899' },
  ];

  const DIRECT_PROVIDERS = [
    { id: 'groq', label: 'Groq', placeholder: 'gsk_...' },
    { id: 'deepseek', label: 'DeepSeek', placeholder: 'sk-...' },
    { id: 'google-gemini', label: 'Google Gemini', placeholder: 'AIza...' },
    { id: 'google-gemini-backup', label: 'Google Gemini (Yedek)', placeholder: 'AIza...' },
    { id: 'mistral', label: 'Mistral AI', placeholder: '...' },
    { id: 'cerebras', label: 'Cerebras', placeholder: '...' },
    { id: 'together', label: 'Together AI', placeholder: '...' },
    { id: 'fireworks', label: 'Fireworks AI', placeholder: '...' },
    { id: 'perplexity', label: 'Perplexity', placeholder: 'pplx-...' },
    { id: 'sambanova', label: 'SambaNova', placeholder: '...' },
    { id: 'nvidia-nim', label: 'NVIDIA NIM', placeholder: 'nvapi-...' },
    { id: 'deepinfra', label: 'DeepInfra', placeholder: '...' },
    { id: 'huggingface', label: 'HuggingFace', placeholder: 'hf_...' },
    { id: 'nous-research', label: 'Nous Research', placeholder: '...' },
    { id: 'alibaba-dashscope', label: 'Alibaba DashScope', placeholder: 'sk-...' },
  ];

  const DIAGNOSTIC_PROVIDERS = [
    { id: 'anthropic', label: 'Anthropic (Tanı / OpenRouter)', placeholder: 'sk-ant-...' },
    { id: 'openai', label: 'OpenAI (Tanı / OpenRouter)', placeholder: 'sk-...' },
    { id: 'xai', label: 'xAI Grok (Tanı / OpenRouter)', placeholder: 'xai-...' },
    { id: 'cohere', label: 'Cohere (Tanı / OpenRouter)', placeholder: '...' },
    { id: 'azure-openai', label: 'Azure OpenAI (Tanı)', placeholder: '...' },
    { id: 'iflow', label: 'iFlow (Tanı)', placeholder: '...' },
    { id: 'google-gemini-vertex', label: 'Google Gemini Vertex (Tanı)', placeholder: '...' },
  ];

  const sourceDescriptions: Record<string, string> = {
    redis_bus: 'REDIS PUB/SUB',
    in_memory: 'YEREL BELLEK (REDIS YOK)',
    fallback: 'YEDEK DURUM (SUNUCU KAPALI)',
    error: 'BAĞLANTI HATASI',
    unreachable: 'SUNUCUYA ULAŞILAMIYOR',
    none: 'henüz bağlanmadı',
  };

  // --- HEDEF & OPERATÖR DURUMU ---
  let targetUrl = '';
  let isAdultDeclared = false;
  let showContextInputs = false;
  let contextRituals = '';
  let contextPlaylist = '';
  let contextEnvies = '';
  let userRituals = '';
  let userPlaylist = '';
  let userEnvies = '';
  const operatorSectionTitle = 'OPERATÖR VERİSİ';

  let phoneConsentGiven = false;
  let isProbingPhone = false;
  let phoneProbeResult: any = null;
  let launchNotice: { tone: 'err' | 'warn' | 'ok'; text: string } | null = null;
  let legalNotice: any = null;

  // --- SOHBET & DANIŞMAN ---
  let selectedAgentId: string | null = 'aspasia';
  let inputMessage = '';
  let isSending = false;
  let chatMessages: Array<{ ts: string; sender: string; text: string }> = [
    {
      ts: 'SİSTEM',
      sender: 'Aspasia',
      text: 'Hoş geldiniz. Hedef profili yukarıdan girip analizi başlatabilir veya bana doğrudan soru sorabilirsiniz.',
    },
  ];

  // --- MANUEL KANIT & OPERATÖR NOTU ---
  let injectType = 'twin_url';
  let injectValue = '';
  let injectTargetAgent = 'all';
  let injectNote = '';
  let isInjecting = false;
  let injectHistory: Array<{ type: string; value: string; target: string; note: string; ts: string }> = [];

  let overrideFact = '';
  let overrideTag = 'operator_note';
  let overrideBusy = false;
  let overrideNotice = '';

  // --- KASA & AYARLAR ---
  let vaultKnown = false;
  let vaultBusy = false;
  let vaultError = '';
  let showSettingsModal = false;
  let settingsSaving = false;
  let settingsNotice = '';
  let settingsError = '';
  let routingData: any = null;
  let appTokenInput = currentApiToken();
  let openRouterInput = '';
  let providerInputs: Record<string, string> = {
    groq: '',
    deepseek: '',
    'google-gemini': '',
    'google-gemini-backup': '',
    mistral: '',
    cerebras: '',
    together: '',
    fireworks: '',
    perplexity: '',
    sambanova: '',
    'nvidia-nim': '',
    deepinfra: '',
    huggingface: '',
    'nous-research': '',
    'alibaba-dashscope': '',
    anthropic: '',
    openai: '',
    xai: '',
    cohere: '',
    'azure-openai': '',
    iflow: '',
    'google-gemini-vertex': '',
  };
  let tavilyKey = '';
  let serpapiKey = '';
  let exaKey = '';
  let xCookie = '';
  let igCookie = '';
  let useLocal = false;
  let localUrl = 'http://localhost:11434/v1';
  let localModel = 'dolphin-llama3:latest';

  // --- GEÇMİŞ & RAPOR FABRİKASI & ÖRNEK VİTRİN ---
  let showHistoryModal = false;
  let historyModalTab: 'tasks' | 'reports' = 'tasks';
  let pastTasks: any[] = [];
  let taskHistoryLoading = false;
  let tasksError = '';
  let reportStatusData: any = null;
  let reportList: any[] = [];
  let reportTitle = 'Pineal Adli Analiz Raporu';
  let reportFormats: Record<string, boolean> = {
    markdown: true,
    pdf: true,
    diagram: true,
    video: false,
  };
  let reportBuildBusy = false;
  let reportBuildResult: any = null;
  let reportBuildError = '';

  let showDemoModal = false;
  let demoLoading = false;
  let demoData: any = null;
  let selectedDemoReport: any = null;
  let showTermsModal = false;

  // --- REAKTİF TÜRETİMLER ---
  $: activeTargetUrl.set(targetUrl);
  $: jurors = ($taskStatus as any)?.output_summary?.jurors ?? null;
  $: pillarSummaries = buildPillarSummaries($taskStatus);
  $: statusSourceText = $agentStatusSource || 'none';
  $: statusSourceDisplay = `KAYNAK: ${sourceDescriptions[statusSourceText] || statusSourceText}`;

  const READY_STATUS_SET = new Set(['WAIT', 'ONLINE', 'READY']);
  const ERROR_STATUS_SET = new Set(['ERROR', 'FAILED']);
  $: slotLabels = Object.values($agentStatuses || {}).map((x: any) =>
    String(x?.status || x || '').toUpperCase()
  );
  $: readyCount = slotLabels.filter((s) => READY_STATUS_SET.has(s)).length;
  $: errorCount = slotLabels.filter((s) => ERROR_STATUS_SET.has(s)).length;

  $: missionElapsedStr = (() => {
    const s = Math.max(0, Number($missionElapsed) || 0);
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    return `${mm}:${ss}`;
  })();

  function isInstagramOrX(urlStr: string): boolean {
    const raw = (urlStr || '').trim().toLowerCase();
    if (!raw) return true;
    if (!raw.includes('://') && !raw.includes('.')) return true;
    return (
      raw.includes('instagram.com') ||
      raw.includes('instagr.am') ||
      raw.includes('x.com') ||
      raw.includes('twitter.com')
    );
  }

  $: platformWarning =
    routingData?.cross_platform_enabled === false &&
    targetUrl.trim() &&
    !isPhoneInput(targetUrl) &&
    !isInstagramOrX(targetUrl)
      ? 'Not: Sistemde yalnızca Instagram ve X varsayılan olarak açık. Diğer siteler için sunucuda ENABLE_CROSS_PLATFORM ayarının açık olması gerekir.'
      : null;

  function isPhoneInput(val: string): boolean {
    const cleaned = (val || '').trim();
    if (!cleaned || cleaned.includes('http://') || cleaned.includes('https://') || cleaned.startsWith('@')) {
      return false;
    }
    const digits = cleaned.replace(/[\s\-().+]/g, '');
    return /^\+?\d[\d\s\-().]{6,18}$/.test(cleaned) && digits.length >= 7 && digits.length <= 15;
  }

  function getPillarHasData(pillarId: string): boolean {
    const map = pillarSummaries as Record<string, any>;
    if (map?.[pillarId]?.hasData) return true;
    if (pillarId === 'osint') {
      const os = ($taskStatus as any)?.osint_footprint ?? ($taskStatus as any)?.key_matrix;
      return Boolean(os && (typeof os.phone_exposed === 'boolean' || hasEvidence(os)));
    }
    return false;
  }

  function summarizeAgentRun(agentId: string) {
    const run = taskRuns($taskStatus)?.[agentId];
    if (!run) return null;
    const label = 'ÇALIŞMA MODELİ';
    const model = run.model || HONEST_EMPTY_LABELS.missing;
    const calls = Array.isArray(run.call_ids) ? run.call_ids.length : 0;
    return {
      label,
      model,
      calls,
      fallback: INSUFFICIENT_EVIDENCE,
      readyCount,
      errorCount,
      operatorTitle: operatorSectionTitle,
    };
  }

  // --- YARDIMCI FONKSİYONLAR ---
  function routeInfo(agentId: string): any {
    return routingData?.routing?.agents?.[agentId] || null;
  }

  function routeChain(agentId: string): string {
    const info = routeInfo(agentId);
    if (Array.isArray(info?.chain) && info.chain.length > 0) return info.chain.join(' > ');
    const summary = summarizeAgentRun(agentId);
    return summary?.model && summary.model !== HONEST_EMPTY_LABELS.missing ? summary.model : 'Rota bilgisi yüklenmedi';
  }

  function routeTier(agentId: string): string {
    const info = routeInfo(agentId);
    return info?.tier || routingData?.routing?.tiers?.[agentId] || '—';
  }

  function routeSource(agentId: string): string {
    return routeInfo(agentId)?.source || '—';
  }

  function selectAgent(id: string) {
    selectedAgentId = id;
    playClick();
  }

  function formatPresetWithTarget(preset: string): string {
    const t = targetUrl.trim();
    return t ? `[Hedef: ${t}] ${preset}` : preset;
  }

  function pushChat(sender: string, text: string) {
    const now = new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
    chatMessages = [...chatMessages, { ts: now, sender, text }];
  }

  // --- KASA & ROTA ---
  async function refreshVaultState() {
    try {
      const cid = encodeURIComponent(get(clientId) || 'default');
      const res = await apiFetch(`/api/vault/status?client_id=${cid}`);
      if (res.ok) {
        const d = await res.json();
        vaultLocked.set(Boolean(d.locked));
        vaultKnown = true;
      } else {
        const localOk = await vaultExists().catch(() => false);
        vaultKnown = Boolean(localOk);
      }
    } catch {
      const localHasVault = await vaultExists().catch(() => false);
      const localUnlocked = await checkVaultStatus().catch(() => false);
      if (localHasVault) {
        vaultLocked.set(!localUnlocked);
        vaultKnown = true;
      }
    }
  }

  async function toggleVaultLock() {
    if (vaultBusy) return;
    vaultBusy = true;
    vaultError = '';
    try {
      const cid = get(clientId) || 'default';
      const lockedNow = get(vaultLocked);
      const endpoint = lockedNow ? '/api/vault/unlock' : '/api/vault/lock';
      const res = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: cid, action: lockedNow ? 'unlock' : 'lock' }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        vaultError = data?.error?.message || data?.detail || 'Kasa işlemi gerçekleştirilemedi. Anahtar ayarlarını kontrol edin.';
        if (res.status === 423) showSettingsModal = true;
      } else {
        vaultLocked.set(!lockedNow);
        vaultKnown = true;
      }
    } catch {
      vaultError = 'Kasa durumuna ulaşılamadı.';
    } finally {
      vaultBusy = false;
    }
  }

  async function loadRoutingSnapshot() {
    try {
      const cid = encodeURIComponent(get(clientId) || 'default');
      const res = await apiFetch(`/api/llm/routing?client_id=${cid}`);
      if (res.ok) {
        routingData = await res.json();
        if (typeof routingData.use_local === 'boolean') useLocal = routingData.use_local;
      }
    } catch {
      /* rota özeti isteğe bağlı */
    }
  }

  async function saveMultiVaultSettings() {
    if (settingsSaving) return;
    settingsSaving = true;
    settingsError = '';
    settingsNotice = '';
    try {
      setApiToken(appTokenInput.trim());
      const sealedProviders: Record<string, string> = {};
      for (const [k, v] of Object.entries(providerInputs)) {
        const trimmed = (v || '').trim();
        if (trimmed) sealedProviders[k] = trimmed;
      }

      const body: Record<string, any> = {
        client_id: get(clientId) || 'default',
        api_key: openRouterInput.trim(),
        tavily_key: tavilyKey.trim(),
        serpapi_key: serpapiKey.trim(),
        exa_key: exaKey.trim(),
        x_cookie: xCookie.trim(),
        ig_sessionid: igCookie.trim(),
        use_local: useLocal,
        local_url: localUrl.trim(),
        local_model: localModel.trim(),
      };
      if (Object.keys(sealedProviders).length > 0) {
        body.provider_keys = sealedProviders;
      }

      const res = await apiFetch('/api/vault', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        settingsError = data?.error?.message || data?.detail || `Ayarlar kaydedilemedi (${res.status}).`;
      } else {
        settingsNotice = data?.message || 'Anahtarlar kaydedildi ve kasa güncellendi.';
        await refreshVaultState();
        await loadRoutingSnapshot();
      }
    } catch {
      settingsError = 'Sunucuyla bağlantı kurulamadı.';
    } finally {
      settingsSaving = false;
    }
  }

  // --- ANALİZ BAŞLATMA & ACİL DURDURMA & TELEFON YOKLAMA ---
  async function launchAnalysis() {
    const url = targetUrl.trim();
    if (!url || !isAdultDeclared || !$armEngaged) return;

    playRunning();
    launchNotice = null;
    isProcessing.set(true);

    try {
      const cid = get(clientId) || 'default';
      const preRes = await apiFetch('/api/target/preflight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: cid, url }),
      });
      if (preRes.ok) {
        const pre = await preRes.json().catch(() => null);
        if (pre && pre.eligible === false) {
          const reasonStr = Array.isArray(pre.reasons) ? pre.reasons.join(' · ') : pre.reason || 'Hedef uygun değil';
          launchNotice = { tone: 'err', text: `Ön-kontrol engeli: ${reasonStr}` };
          isProcessing.set(false);
          return;
        }
      }

      const rituals = (contextRituals || userRituals).trim();
      const playlist = (contextPlaylist || userPlaylist).trim();
      const envies = (contextEnvies || userEnvies).trim();

      const res = await apiFetch('/api/initiate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: cid,
          url,
          rituals,
          playlist,
          envies,
          scraper_type: 'cross',
          subject_consent: isAdultDeclared,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (isAuthFailure(res)) {
          launchNotice = { tone: 'err', text: 'Erişim anahtarı geçersiz veya eksik. Ayarlardan kontrol edin.' };
        } else {
          launchNotice = {
            tone: 'err',
            text: data?.error?.message || data?.detail || `Analiz başlatılamadı (${res.status}).`,
          };
        }
        isProcessing.set(false);
        return;
      }

      const acceptedTaskId = data?.task_id || '';
      if (acceptedTaskId) {
        const cur = get(taskStatus);
        if (!cur || cur.task_id !== acceptedTaskId) {
          taskStatus.set({ task_id: acceptedTaskId, status: data?.status || 'queued' });
        }
        launchNotice = { tone: 'ok', text: `Görev kabul edildi (ID: ${acceptedTaskId})` };
      } else {
        launchNotice = { tone: 'ok', text: 'Görev kabul edildi ve sıraya alındı.' };
      }
    } catch {
      launchNotice = { tone: 'err', text: 'Sunucuyla bağlantı kurulamadı.' };
      isProcessing.set(false);
    }
  }

  async function emergencyStop() {
    playHalt();
    const cur = get(taskStatus);
    const taskId = cur?.task_id;
    try {
      if (taskId) {
        await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}/halt`, {
          method: 'POST',
        });
      }
    } catch {
      /* yerel durdurmayı her koşulda uygula */
    } finally {
      armEngaged.set(false);
      isProcessing.set(false);
    }
  }

  async function probePhoneAction() {
    const phone = targetUrl.trim();
    if (!phone || !phoneConsentGiven || isProbingPhone) return;
    isProbingPhone = true;
    launchNotice = null;
    try {
      const res = await apiFetch('/api/commander/phone-probe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: get(clientId) || 'default',
          phone,
          auto_bridge_social: true,
          subject_consent: phoneConsentGiven,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        launchNotice = {
          tone: 'err',
          text: data?.error?.message || data?.detail || `Numara sorgusu tamamlanamadı (${res.status}).`,
        };
      } else {
        phoneProbeResult = data;
      }
    } catch {
      launchNotice = { tone: 'err', text: 'Telefon sorgusu sırasında bağlantı hatası oluştu.' };
    } finally {
      isProbingPhone = false;
    }
  }

  // --- DANIŞMAN SOHBETİ (ASPASIA / LILITH / BEYİN ROTASI) ---
  async function sendAspasiaMessage() {
    const msg = inputMessage.trim();
    if (!msg || isSending) return;
    inputMessage = '';
    pushChat('SÖZ', msg);
    isSending = true;

    const cid = get(clientId) || 'default';
    const curTask = get(taskStatus);
    const looksLikeBrainQuery = /\b(graf|graph|hafıza|memory|ilişki ağı|değişim)\b/i.test(msg);

    try {
      if (selectedAgentId === 'lilith') {
        const res = await apiFetch('/api/lilith/strategy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: cid,
            target_url: targetUrl.trim(),
            instruction: msg,
            subject_consent: isAdultDeclared,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          pushChat('Sistem', data?.error?.message || data?.detail || `Lilith yanıt veremedi (${res.status}).`);
        } else {
          const lines: string[] = [];
          if (data?.lilith?.hook) lines.push(`İlk Mesaj / Kanca: ${data.lilith.hook}`);
          if (data?.lilith?.psychological_angle) lines.push(`Yaklaşım: ${data.lilith.psychological_angle}`);
          if (Array.isArray(data?.counter_moves) && data.counter_moves.length > 0) {
            lines.push('Karşı Hamleler:');
            for (const cm of data.counter_moves) {
              lines.push(`• ${cm.scenario || 'Durum'}: ${cm.our_counter_move || ''}`);
            }
          }
          pushChat('Lilith', lines.join('\n') || data?.reply || JSON.stringify(data));
        }
      } else if (looksLikeBrainQuery) {
        const res = await apiFetch('/api/brain/route', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: cid,
            query: msg,
            target: targetUrl.trim(),
            task_id: curTask?.task_id || '',
            subject_consent: isAdultDeclared,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          pushChat('Sistem', data?.error?.message || data?.detail || `Sorgu tamamlanamadı (${res.status}).`);
        } else {
          const note = data?.result?.machine_note || data?.reply || data?.answer || JSON.stringify(data?.result || data);
          pushChat('Aspasia', note);
        }
      } else {
        const res = await apiFetch('/api/aspasia/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: cid,
            message: msg,
            agent_id: selectedAgentId || 'aspasia',
            task_id: curTask?.task_id || '',
            subject_consent: isAdultDeclared,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          pushChat('Sistem', data?.error?.message || data?.detail || `Danışman yanıt veremedi (${res.status}).`);
        } else {
          pushChat('Aspasia', data?.reply || data?.message || data?.response || JSON.stringify(data));
        }
      }
    } catch {
      pushChat('Sistem', 'Bağlantı hatası nedeniyle mesaj gönderilemedi.');
    } finally {
      isSending = false;
    }
  }

  // --- MANUEL KANIT & OPERATÖR NOTU ---
  async function injectCommanderEvidence() {
    const val = injectValue.trim();
    if (!val || isInjecting) return;
    isInjecting = true;
    overrideNotice = '';
    try {
      const res = await apiFetch('/api/commander/inject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: get(clientId) || 'default',
          evidence_type: injectType,
          evidence_value: val,
          target_agent: injectTargetAgent || 'all',
          note: injectNote.trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data?.error?.message || data?.detail || `HTTP ${res.status}`);
      }
      if (data?.status !== 'stored') {
        throw new Error('Kanıt kaydı doğrulanamadı.');
      }
      const statusMsg = data?.applied_to_agent
        ? 'Kanıt ajan hafızasına yazıldı.'
        : 'Kanıt dosyaya kaydedildi; ajana aktarım bağlanamadı.';
      injectHistory = [
        {
          type: injectType,
          value: val,
          target: injectTargetAgent,
          note: injectNote.trim() || statusMsg,
          ts: new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }),
        },
        ...injectHistory,
      ];
      injectValue = '';
      injectNote = '';
      overrideNotice = statusMsg;
    } catch (e: any) {
      overrideNotice = e?.message || 'Kanıt kaydedilemedi.';
    } finally {
      isInjecting = false;
    }
  }

  async function submitOperatorOverride() {
    const fact = overrideFact.trim();
    if (!fact || overrideBusy) return;
    overrideBusy = true;
    overrideNotice = '';
    try {
      const res = await apiFetch('/api/override', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: get(clientId) || 'default',
          fact,
          tag: (overrideTag || 'operator_note').trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        overrideNotice = data?.error?.message || data?.detail || `Not eklenemedi (${res.status}).`;
      } else {
        overrideNotice = 'Operatör notu kalıcı hafızaya eklendi.';
        overrideFact = '';
      }
    } catch {
      overrideNotice = 'Not kaydedilirken bağlantı kesildi.';
    } finally {
      overrideBusy = false;
    }
  }

  // --- GEÇMİŞ GÖREVLER & RAPOR FABRİKASI ---
  async function loadTaskHistory() {
    taskHistoryLoading = true;
    tasksError = '';
    try {
      const cid = encodeURIComponent(get(clientId) || 'default');
      const res = await apiFetch(`/api/tasks?client_id=${cid}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        tasksError = data?.error?.message || data?.detail || `Geçmiş yüklenemedi (${res.status}).`;
      } else {
        pastTasks = Array.isArray(data?.tasks) ? data.tasks : Array.isArray(data) ? data : [];
      }
    } catch {
      tasksError = 'Geçmiş listesi alınamadı.';
    } finally {
      taskHistoryLoading = false;
    }
  }

  async function loadPastTaskIntoCockpit(taskId: string) {
    if (!taskId) return;
    try {
      const cid = encodeURIComponent(get(clientId) || 'default');
      const res = await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}?client_id=${cid}`);
      if (!res.ok) return;
      const detail = await res.json();
      taskStatus.update((prev) => mergeTaskSnapshot(prev, detail));
      if (detail?.target_profile?.url) {
        targetUrl = detail.target_profile.url;
      }
      launchNotice = { tone: 'ok', text: `Geçmiş görev yüklendi: ${taskId}` };
      showHistoryModal = false;
    } catch {
      tasksError = 'Görev detayı yüklenemedi.';
    }
  }

  async function deletePastTask(taskId: string) {
    if (!taskId) return;
    try {
      const cid = encodeURIComponent(get(clientId) || 'default');
      const res = await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}?client_id=${cid}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        pastTasks = pastTasks.filter((t) => t.task_id !== taskId);
      }
    } catch {
      tasksError = 'Görev silinemedi.';
    }
  }

  async function loadReportCenter() {
    try {
      const cid = encodeURIComponent(get(clientId) || 'default');
      const [sRes, lRes] = await Promise.all([
        apiFetch('/api/report/status'),
        apiFetch(`/api/report/list?client_id=${cid}`),
      ]);
      if (sRes.ok) reportStatusData = await sRes.json();
      if (lRes.ok) {
        const d = await lRes.json();
        reportList = Array.isArray(d?.reports) ? d.reports : Array.isArray(d) ? d : [];
      }
    } catch {
      /* sessizce geç */
    }
  }

  async function buildReportFromCockpit() {
    const cur = get(taskStatus);
    if (!cur || reportBuildBusy) return;
    reportBuildBusy = true;
    reportBuildError = '';
    reportBuildResult = null;
    try {
      const selectedFormats = Object.entries(reportFormats)
        .filter(([, on]) => on)
        .map(([k]) => k);
      const evidenceItems = evidenceChainToReportItems(cur);
      const res = await apiFetch('/api/report/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: (reportTitle || '').trim() || `Pineal Rapor — ${cur.task_id || 'Oturum'}`,
          client_id: get(clientId) || 'default',
          subject: cur?.target_profile?.url || targetUrl.trim() || cur.task_id || 'Hedef',
          evidence: evidenceItems,
          formats: selectedFormats.length > 0 ? selectedFormats : ['markdown'],
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        reportBuildError = data?.error?.message || data?.detail || `Rapor oluşturulamadı (${res.status}).`;
      } else {
        reportBuildResult = data;
        await loadReportCenter();
      }
    } catch {
      reportBuildError = 'Rapor oluşturulurken bağlantı kesildi.';
    } finally {
      reportBuildBusy = false;
    }
  }

  // --- ÖRNEK VİTRİN & YASAL BİLDİRİM ---
  async function loadPublicShowcase() {
    demoLoading = true;
    selectedDemoReport = null;
    try {
      const res = await apiFetch('/api/public/demo-reports');
      if (res.ok) demoData = await res.json();
    } catch {
      /* sessizce geç */
    } finally {
      demoLoading = false;
    }
  }

  async function loadDemoReport(id: string) {
    if (!id) return;
    try {
      const res = await apiFetch(`/api/public/demo-reports/${encodeURIComponent(id)}`);
      if (res.ok) selectedDemoReport = await res.json();
    } catch {
      /* sessizce geç */
    }
  }

  async function loadLegalNotice() {
    try {
      const res = await apiFetch('/api/public/notice');
      if (res.ok) legalNotice = await res.json();
    } catch {
      /* sessizce geç */
    }
  }

  function openHistoryModal(tab: 'tasks' | 'reports' = 'tasks') {
    historyModalTab = tab;
    showHistoryModal = true;
    loadTaskHistory();
    loadReportCenter();
  }

  function openSettingsModal() {
    settingsNotice = '';
    settingsError = '';
    showSettingsModal = true;
    loadRoutingSnapshot();
  }

  function openDemoModal() {
    showDemoModal = true;
    loadPublicShowcase();
  }

  function openTermsModal() {
    showTermsModal = true;
    loadLegalNotice();
  }

  onMount(() => {
    startHealthPoll();
    refreshVaultState();
    loadRoutingSnapshot();
    loadLegalNotice();
  });

  onDestroy(() => {
    stopHealthPoll();
  });
</script>

<div class="cockpit-app" data-source-caption={statusSourceDisplay}>
  <CockpitHeader
    {missionElapsedStr}
    {vaultKnown}
    {vaultBusy}
    {vaultError}
    onEmergencyStop={emergencyStop}
    onToggleVault={toggleVaultLock}
    onOpenSettings={openSettingsModal}
    onOpenHistory={() => openHistoryModal('tasks')}
    onOpenDemo={openDemoModal}
  />

  <div class="cockpit-workspace">
    <CockpitSidebar onOpenTerms={openTermsModal} />

    <main class="cockpit-main">
      {#if $activeTab === 'home'}
        <HomeDashboardTab
          {SOVEREIGNS}
          {FIELD_AGENTS}
          {PILLARS}
          bind:targetUrl
          bind:isAdultDeclared
          bind:showContextInputs
          bind:contextRituals
          bind:contextPlaylist
          bind:contextEnvies
          {userRituals}
          {userPlaylist}
          {userEnvies}
          bind:phoneConsentGiven
          {isProbingPhone}
          {phoneProbeResult}
          {launchNotice}
          {platformWarning}
          {legalNotice}
          {selectedAgentId}
          {chatMessages}
          bind:inputMessage
          {isSending}
          bind:injectType
          bind:injectValue
          bind:injectTargetAgent
          bind:injectNote
          {isInjecting}
          {injectHistory}
          bind:overrideFact
          bind:overrideTag
          {overrideBusy}
          {overrideNotice}
          {routingData}
          {statusSourceText}
          {sourceDescriptions}
          {jurors}
          {isPhoneInput}
          {getPillarHasData}
          {pillarSummaries}
          {launchAnalysis}
          {probePhoneAction}
          {selectAgent}
          {formatPresetWithTarget}
          {sendAspasiaMessage}
          {injectCommanderEvidence}
          {submitOperatorOverride}
          {openHistoryModal}
          {openTermsModal}
          {openSettingsModal}
          {routeChain}
          {routeTier}
          {routeSource}
        />
      {:else if $activeTab === 'cross'}
        <CrossScanTab {targetUrl} />
      {:else if $activeTab === 'aspasia'}
        <AspasiaChatTab
          {chatMessages}
          bind:inputMessage
          {isSending}
          {sendAspasiaMessage}
          {selectAgent}
          onOpenSettings={openSettingsModal}
          onToggleVault={toggleVaultLock}
        />
      {:else if $activeTab === 'lilith'}
        <LilithStudioTab {targetUrl} />
      {:else if $activeTab === 'company'}
        <CompanyTab {targetUrl} />
      {:else if $activeTab === 'media'}
        <MediaVoiceTab {targetUrl} />
      {:else if $activeTab === 'browser'}
        <BrowserControlTab {targetUrl} />
      {:else if $activeTab === 'reports'}
        <ReportsMemoryTab
          {pastTasks}
          {taskHistoryLoading}
          {reportStatusData}
          {reportList}
          {reportBuildBusy}
          {reportBuildResult}
          bind:reportTitle
          {targetUrl}
          onLoadTaskHistory={loadTaskHistory}
          onLoadPastTask={loadPastTaskIntoCockpit}
          onDeletePastTask={deletePastTask}
          onLoadReportCenter={loadReportCenter}
          onBuildReport={buildReportFromCockpit}
        />
      {:else if $activeTab === 'system'}
        <SystemToolsTab
          {routingData}
          onLoadRoutingSnapshot={loadRoutingSnapshot}
          onOpenSettings={openSettingsModal}
          onOpenTerms={openTermsModal}
        />
      {/if}
    </main>
  </div>

  <SettingsModal
    {showSettingsModal}
    {routingData}
    {DIRECT_PROVIDERS}
    {DIAGNOSTIC_PROVIDERS}
    {SOVEREIGNS}
    {FIELD_AGENTS}
    bind:appTokenInput
    bind:openRouterInput
    bind:providerKeys={providerInputs}
    bind:tavilyKey
    bind:serpapiKey
    bind:exaKey
    bind:xCookie
    bind:igCookie
    bind:useLocal
    bind:localUrl
    bind:localModel
    {settingsSaving}
    {settingsError}
    {settingsNotice}
    {routeChain}
    {routeTier}
    {routeSource}
    onSave={saveMultiVaultSettings}
    onClose={() => { showSettingsModal = false; }}
  />

  <HistoryReportModal
    {showHistoryModal}
    bind:historyModalTab
    {pastTasks}
    {taskHistoryLoading}
    {tasksError}
    {reportStatusData}
    {reportList}
    bind:reportFormats
    {reportBuildBusy}
    {reportBuildResult}
    {reportBuildError}
    bind:reportTitle
    onClose={() => { showHistoryModal = false; }}
    onRefreshTasks={loadTaskHistory}
    onRefreshReports={loadReportCenter}
    onLoadPastTask={loadPastTaskIntoCockpit}
    onDeletePastTask={deletePastTask}
    onBuildReport={buildReportFromCockpit}
  />

  <DemoAndTermsModal
    {showDemoModal}
    {demoLoading}
    {demoData}
    {selectedDemoReport}
    {showTermsModal}
    {legalNotice}
    onCloseDemo={() => { showDemoModal = false; }}
    onSelectDemoReport={loadDemoReport}
    onCloseTerms={() => { showTermsModal = false; }}
  />
</div>

<style>
  .cockpit-app {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    min-height: 0;
    background-color: var(--bg-app);
    color: var(--text-primary);
  }

  :global([data-theme='dark']) .cockpit-app {
    background-image:
      radial-gradient(ellipse at 70% 15%, rgba(62, 24, 18, 0.08), rgba(14, 6, 5, 0.36) 85%),
      url('/atelier/ground.webp');
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
  }

  .cockpit-workspace {
    display: flex;
    flex: 1 1 auto;
    min-height: 0;
    overflow: hidden;
  }

  .cockpit-main {
    flex: 1 1 auto;
    min-width: 0;
    min-height: 0;
    overflow-y: auto;
    padding: 20px 24px 68px;
  }

  @media (max-width: 1024px) {
    .cockpit-workspace {
      overflow: visible;
    }

    .cockpit-main {
      padding: 14px 14px 72px;
      overflow-y: visible;
    }
  }
</style>
