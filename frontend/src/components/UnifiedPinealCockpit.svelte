<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import TaskEvidence from './TaskEvidence.svelte';
  import Icon from './Icon.svelte';
  import { get } from 'svelte/store';
  import {
    apiToken, setApiToken, currentApiToken, apiFetch, isAuthFailure, clientId, wsUrl, logs, taskStatus,
    speechState, lastSpeech, voiceEnabled,
    isProcessing, powerEngaged, armEngaged, recordEngaged, agentStatuses, vaultLocked,
    activeViewMode, agentStatusSource, supportRequests, supportTaskId, refreshSupport, mergeTaskSnapshot,
    missionElapsed, activeTargetUrl
  } from '../store';
  import { uplinkState, health, sysTelemetry, apiAuthRequired, startHealthPoll, stopHealthPoll } from '../lib/telemetry';
  import { playClick, playHalt, playRunning } from '../lib/consoleAudio';
  import { hasEvidence, buildPillarSummaries, evidenceChainToReportItems } from '../lib/evidence';
  import { taskRuns, taskRunLabel, rackAvailability } from '../lib/taskRunStatus';
  import { checkVaultStatus, vaultExists } from '../lib/tauriBridge';

  // --- 1. SOVEREIGNS (ASPASIA & LILITH) ---
  const SOVEREIGNS = [
    {
      id: 'aspasia', name: 'ASPASIA', short: 'ASPASIA',
      role: 'Baş Stratejist & Argüman Analisti',
      title: 'Sokratik Retorik, Hakikat Aynası ve Empatik Strateji',
      icon: 'diamond', accent: '#10b981', badge: 'STRATEJİ',
      presets: [
        'Hedefle olan uyumu ve rezonansını stratejik olarak özetle',
        'Hedefin kalkanını kırmadan sahici bir temas stratejisi kur',
        'Kullanıcının frekansına ayna tutarak zayıf/güçlü yönleri değerlendir'
      ]
    },
    {
      id: 'lilith', name: 'LILITH', short: 'LILITH',
      role: 'Büyüme & Nörobilim',
      title: 'Dopamin Kancası, Amigdala Uyarımı, Maske Yırtıcı ve Viralite',
      icon: 'sparkle', accent: '#ec4899', badge: 'BÜYÜME',
      presets: [
        'Dopaminerjik ödül tahmin hatasıyla beklenti kırıcı viral kanca kurgula',
        'Hedefin vitrindeki duruşu ile bastırılmış narsistik dürtüleri analiz et',
        'Amigdala uyarımı ve kayiptan kaçınma alışkanlığıyla hipnotik bir ilk temas yaz'
      ]
    }
  ];

  // --- 2. 12 SAHA AJANI ---
  const FIELD_AGENTS = [
    { id: 'osint_investigator', name: 'OSINT INVESTIGATOR', short: 'OSINT', icon: 'target', color: '#8b5cf6', desc: 'Açık kaynak, web ve dijital ayak izi taraması', preset: 'Tüm web platformlarında çapraz kullanıcı adı ve dijital parmak izi tara' },
    { id: 'depth_analyst', name: 'DEPTH ANALYST', short: 'DEPTH', icon: 'layers', color: '#eab308', desc: 'Gerçeklik endeksi ve kişilik derinliği analizi', preset: 'Kişilik özgünlüğü ve sosyal medyadaki yapay maskeyi derinlemesine incele' },
    { id: 'human_behavior', name: 'HUMAN BEHAVIOR', short: 'BEHAVIOR', icon: 'diamond', color: '#f59e0b', desc: 'Dijital cold reading ve akıl tendonu analizi', preset: 'Hedefin alışkanlıklarını, ritüellerini ve zayıf hassasiyet noktasını çıkar' },
    { id: 'friction_detector', name: 'FRICTION & BOUNDS', short: 'FRICTION', icon: 'triangle-up', color: '#ef4444', desc: 'Sınırlar, hassasiyet ve sürtünme dedektörü', preset: 'Konuşulmaması gereken kırmızı çizgileri ve sürtünme tetikleyicilerini belirle' },
    { id: 'pattern_interrupt', name: 'PATTERN INTERRUPT', short: 'PATTERN', icon: 'refresh', color: '#dc2626', desc: 'Beklenti kırma ve temas stratejisi', preset: 'Sıradan mesajların ötesinde ezber bozan bir kalıp kırıcı ilk cümle kur' },
    { id: 'passion_mapper', name: 'PASSION MAPPER', short: 'PASSION', icon: 'square', color: '#eab308', desc: 'Tutku, neşe ve akış tetikleyicileri haritası', preset: 'Hedefin gözlerini parlatan, gerçek tutkularını ve akış alanlarını haritala' },
    { id: 'cognitive_profiler', name: 'COGNITIVE PROFILER', short: 'COGNITIVE', icon: 'hexagon', color: '#06b6d4', desc: 'Bilişsel dil, üslup ve tonlama profili', preset: 'Hedefin kelime dağarcığını, resmiyet derecesini ve iletişim ritmini modelle' },
    { id: 'mirror_truth', name: 'MIRROR TRUTH', short: 'MIRROR', icon: 'circle-hollow', color: '#10b981', desc: 'İç-z-frekans yansıtma ve kullanıcı uyumu', preset: 'Kullanıcının ritmeleri ile hedefin profili arasındaki doğal frekans bağını test et' },
    { id: 'autonomous_verifier', name: 'AUTONOMOUS VERIFIER', short: 'VERIFIER', icon: 'triangle-down', color: '#a855f7', desc: 'Otonom çapraz doğrulama ve hakem paneli', preset: 'Takipçi/beğeni oranlarındaki bot veya manipülasyon şüphesini denetle' },
    { id: 'resonance_calculator', name: 'RESONANCE CALC', short: 'CALC', icon: 'star', color: '#3b82f6', desc: 'Numpy vektörel rezonans ve açı hesaplaması', preset: 'Çok boyutlu semantik uzayda rezonans ve uyum açısını matematiksel hesapla' },
    { id: 'authenticity_auditor', name: 'AUTHENTICITY AUDITOR', short: 'AUTH', icon: 'star', color: '#14b8a6', desc: 'Orijinallik ve güvenilirlik denetimi', preset: 'Gönderilerin doğallığı ile alıntı/kurgu oranını ölçerek maske puanı çıkar' },
    { id: 'resonance_synthesizer', name: 'RESONANCE SYNTH', short: 'SYNTH', icon: 'sparkle', color: '#ec4899', desc: 'Sahici köprü sentezi ve önerilen ilk mesaj', preset: 'Tüm bulguları sentezleyerek hedefe ulaşacak en etkili ve zarif köprüyü inşa et' },
  ];

  // --- 3. 7 ADLİ SÜTUN ---
  const PILLARS = [
    { id: 'follower',  label: 'FOLLOWER',  tr: 'TAKİPÇİ',  icon: 'diamond', color: '#8b5cf6' },
    { id: 'timing',    label: 'TIMING',    tr: 'ZAMAN',    icon: 'clock', color: '#f59e0b' },
    { id: 'depth',     label: 'DEPTH',     tr: 'DERİNLİK', icon: 'layers', color: '#ec4899' },
    { id: 'visual',    label: 'VISUAL',    tr: 'GÖRSEL',   icon: 'eye', color: '#06b6d4' },
    { id: 'shadow',    label: 'SHADOW',    tr: 'GÖLGE',    icon: 'sparkle', color: '#a855f7' },
    { id: 'osint',     label: 'OSINT',     tr: 'OSINT',    icon: 'target', color: '#10b981' },
    { id: 'resonance', label: 'RESONANCE', tr: 'REZONANS', icon: 'star', color: '#ec4899' },
  ];

  // --- STATE ---
  let targetUrl = '';
  let contextRituals = '';
  let contextPlaylist = '';
  let contextEnvies = '';
  let showContextInputs = false;
  let telemetryVisible = true;
  let selectedAgentId: string | null = 'aspasia';
  // Task History & Report Factory Modal
  let showHistoryModal = false;
  let historyTab: 'tasks' | 'reports' = 'tasks';
  let tasksLoading = false;
  let tasksError = '';
  let taskHistoryList: any[] = [];
  let reportStatusLoading = false;
  let reportStatusData: any = null;
  let reportListData: any[] = [];
  let reportTitle = 'Pineal Adli Analiz Raporu';
  let reportSubject = '';
  let reportFormats: Record<string, boolean> = { markdown: true, pdf: true, diagram: true, video: false };
  let reportBuilding = false;
  let reportBuildResult: any = null;
  let reportBuildError = '';

  // Commander Override
  let injectType = 'twin_url';
  let injectValue = '';
  let injectTargetAgent = 'all';
  let injectNote = '';
  let isInjecting = false;
  let vaultKnown = false;
  let vaultBusy = false;
  let vaultError = '';

  // Ayarlar & Çoklu LLM Kasası + Ajan-Model Haritası
  let showSettingsModal = false;
  let settingsTab: 'providers' | 'search' | 'routing' = 'providers';
  let settingsSaving = false;
  let settingsStatusMsg = '';
  let settingsErrorMsg = '';
  let routingLoading = false;
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
    'google-gemini-vertex': ''
  };
  let localUrl = 'http://localhost:11434/v1';
  let localModel = 'dolphin-llama3:latest';
  let useLocal = false;
  let tavilyKey = '';
  let serpapiKey = '';
  let exaKey = '';
  let xCookie = '';
  let igCookie = '';
  let isAdultDeclared = false;

  // llm_gateway._AGENT_DIRECT_PROVIDER_KEYS ile birebir uyumlu (aktif OpenAI-chat rotalı sağlayıcılar)
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
    { id: 'alibaba-dashscope', label: 'Alibaba DashScope', placeholder: 'sk-...' }
  ];

  // llm_gateway._DIAGNOSTIC_ONLY_PROVIDERS ile birebir uyumlu (doğrudan taşıyıcısı yok; yalnızca tanı/envanter)
  const DIAGNOSTIC_PROVIDERS = [
    { id: 'anthropic', label: 'Anthropic (Tanı / OpenRouter)', placeholder: 'sk-ant-...' },
    { id: 'openai', label: 'OpenAI (Tanı / OpenRouter)', placeholder: 'sk-...' },
    { id: 'xai', label: 'xAI Grok (Tanı / OpenRouter)', placeholder: 'xai-...' },
    { id: 'cohere', label: 'Cohere (Tanı / OpenRouter)', placeholder: '...' },
    { id: 'azure-openai', label: 'Azure OpenAI (Tanı)', placeholder: '...' },
    { id: 'iflow', label: 'iFlow (Tanı)', placeholder: '...' },
    { id: 'google-gemini-vertex', label: 'Google Gemini Vertex (Tanı)', placeholder: '...' }
  ];

  function routeInfo(agentId: string): any {
    return routingData?.routing?.agents?.[agentId] || null;
  }

  function routeChain(agentId: string): string {
    const info = routeInfo(agentId);
    return Array.isArray(info?.chain) && info.chain.length ? info.chain.join(' > ') : 'Rota bilgisi yüklenmedi';
  }

  function routeTier(agentId: string): string {
    const info = routeInfo(agentId);
    return info?.tier || routingData?.routing?.tiers?.[agentId] || '—';
  }

  function routeSource(agentId: string): string {
    return routeInfo(agentId)?.source || '—';
  }

  async function loadRoutingSnapshot() {
    routingLoading = true;
    try {
      const cid = get(clientId) || 'default';
      const res = await apiFetch(`/api/llm/routing?client_id=${encodeURIComponent(cid)}`);
      if (res.ok) {
        routingData = await res.json();
        if (typeof routingData.use_local === 'boolean') useLocal = routingData.use_local;
      }
    } catch (_e) {
      // Routing önizlemesi opsiyonel
    } finally {
      routingLoading = false;
    }
  }

  function openSettingsModal(tab: 'providers' | 'search' | 'routing' = 'providers') {
    settingsTab = tab;
    settingsStatusMsg = '';
    settingsErrorMsg = '';
    appTokenInput = currentApiToken();
    showSettingsModal = true;
    void loadRoutingSnapshot();
    void refreshVaultState();
  }

  async function saveMultiVaultSettings() {
    if (settingsSaving) return;
    settingsSaving = true;
    settingsStatusMsg = '';
    settingsErrorMsg = '';
    try {
      if (appTokenInput !== undefined && appTokenInput.trim()) {
        setApiToken(appTokenInput.trim());
      }
      const cid = get(clientId) || 'default';
      const cleanedProviders: Record<string, string> = {};
      for (const [pid, val] of Object.entries(providerInputs)) {
        if (val && val.trim()) cleanedProviders[pid] = val.trim();
      }
      const payload: Record<string, any> = {
        client_id: cid,
        use_local: useLocal,
      };
      if (openRouterInput.trim()) payload.api_key = openRouterInput.trim();
      if (Object.keys(cleanedProviders).length > 0) payload.provider_keys = cleanedProviders;
      if (useLocal || localUrl.trim()) payload.local_url = localUrl.trim();
      if (useLocal || localModel.trim()) payload.local_model = localModel.trim();
      if (tavilyKey.trim()) payload.tavily_key = tavilyKey.trim();
      if (serpapiKey.trim()) payload.serpapi_key = serpapiKey.trim();
      if (exaKey.trim()) payload.exa_key = exaKey.trim();
      if (xCookie.trim()) payload.x_cookie = xCookie.trim();
      if (igCookie.trim()) payload.ig_sessionid = igCookie.trim();

      const res = await apiFetch('/api/vault', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data?.error?.message || data?.detail || `HTTP ${res.status}`);
      }
      settingsStatusMsg = 'Anahtarlar ve çoklu LLM yapılandırması kasaya mühürlendi.';
      openRouterInput = '';
      for (const k of Object.keys(providerInputs)) providerInputs[k] = '';
      tavilyKey = '';
      serpapiKey = '';
      exaKey = '';
      xCookie = '';
      igCookie = '';
      await refreshVaultState();
      await loadRoutingSnapshot();
    } catch (e: any) {
      settingsErrorMsg = `Kayıt hatası: ${e?.message || 'bağlantı hatası'}`;
    } finally {
      settingsSaving = false;
    }
  }
  let injectHistory: Array<{ type: string; value: string; target: string; note: string; ts: string }> = [];

  // Phone OSINT
  let isProbingPhone = false;
  let phoneProbeResult: any = null;

  // Chat & Mission
  let chatMessages: Array<{ ts: string; sender: string; text: string }> = [
    { ts: nowTime(), sender: 'Aspasia', text: 'Sistem çevrimiçi Müşteri. 12 saha ajanı operasyona hazır. (Lilith viral büyüme motoru bağımsız devrededir). Hedef profil girin veya dilediğiniz ajana doğrudan emir verin.' }
  ];
  let inputMessage = '';
  let isSending = false;
  let missionStartTime: number | null = null;
  let missionTimer: any = null;
  let missionElapsedStr = '00:00';

  // 7 Adli Sütun Listesi + Backend evidence_chain bağlantısı
  $: followerAudit = $taskStatus?.follower_audit || null;
  $: timingForensics = $taskStatus?.timing_forensics || null;
  $: depthReport = $taskStatus?.depth_report || null;
  $: visualEvidence = $taskStatus?.visual_evidence || null;
  $: shadowProfile = $taskStatus?.shadow_profile || null;
  $: osintFootprint = $taskStatus?.osint_footprint || null;
  $: resonanceCalc = $taskStatus?.resonance_calc || $taskStatus?.reso || null;
  $: evidenceChain = Array.isArray($taskStatus?.evidence_chain) ? $taskStatus.evidence_chain : [];
  $: pillarSummaries = buildPillarSummaries($taskStatus);

  const INSUFFICIENT_EVIDENCE = 'YETERSİZ KANIT';

  // Özet alanlarının varlığı, kanonik ve doğrulanmış kanıt anlamına gelmez.
  function hasSummaryValue(val: any): boolean {
    if (val === null || val === undefined) return false;
    if (typeof val === 'number') return Number.isFinite(val);
    if (typeof val === 'boolean') return true;
    if (typeof val === 'string') return val.trim().length > 0;
    if (Array.isArray(val)) return val.some(hasSummaryValue);
    if (typeof val === 'object') return Object.values(val).some(hasSummaryValue);
    return false;
  }

  function getPillarHasData(pillarId: string): boolean {
    const summaries: Record<string, [any, string[]]> = {
      follower: [followerAudit, ['avg_followers', 'authenticity_score', 'bot_risk']],
      timing: [timingForensics, ['hour_distribution', 'automation_score', 'timezone_inferred']],
      // [P0 · DOĞRULAMA 2026-11-23] ÖNCE `personality_type / depth_score /
      // mask_score` aranıyordu — bu alanlar DepthReport modelinde HİÇ YOK
      // (agent_core/agents/depth_analyst.py:35-50). Sonuç: analiz başarılı
      // olsa bile sütun "VERİ YOK" diyordu; LLM `extra="allow"` ile bu alanları
      // üretirse doğrulanmamış kişilik etiketi ekrana basılıyordu. Gerçek
      // alanlar: reality_index, essence_one_liner, contradictions, findings.
      depth: [depthReport, ['reality_index', 'essence_one_liner', 'contradictions', 'reality_findings']],
      visual: [visualEvidence, ['consistency_score', 'deepfake_risk', 'aesthetic_signature']],
      shadow: [shadowProfile, ['shadow_accounts', 'link_weight', 'coordination_score']],
      osint: [osintFootprint, ['usernames', 'email_leaks', 'phone_exposed']],
      resonance: [resonanceCalc, ['resonance_angle', 'alignment_score', 'vector_dimensions']],
    };
    const entry = summaries[pillarId];
    return !!entry && !!entry[0] && entry[1].some(key => hasSummaryValue(entry[0][key]));
  }

  let preflightResult: any = null;
  // [P0 · DOĞRULAMA 2026-11-23] Düğme neden çalışmadı? Cevap Eskiden yalnız
  // sol sütundaki ASPASIA sohbet akışına yazılıyordu; kullanıcı oraya bakmıyorsa
  // "hiçbir şey olmadı" algısı doğuyordu (ölçülen şikâyet). Artık aynı mesaj
  // düğmenin hemen altında, role="alert" ile de gösteriliyor.
  // [P0 · DOĞRULAMA 2026-11-23] TOKEN'SIZ VİTRİN.
  // Eskiden ziyaretçi siteyi açar açmaz 401 görüyordu ve ürünün ne yaptığını
  // anlayamıyordu. Artık iki SENTEİTİK örnek rapor herkese açık:
  // `/api/public/demo-reports` (auth_middleware allowlist'inde).
  let showDemoModal = false;
  let demoReports: any[] = [];
  let demoSelected: any = null;
  let demoLoading = false;
  let demoError = '';
  // Yasal uyarı — `/api/public/notice` ile aynı kaynak (agent_core/legal).
  let legalNotice: any = null;
  let showTermsModal = false;

  // [KVKK · 2026-11-23] Telefon numarası kişisel veridir; sorgu için hedefin
  // AÇIK RIZASI gerekir. Beyan verilmeden düğme kilitli, istek hiç gönderilmez.
  let phoneConsentGiven = false;

  let launchNotice: { tone: 'err' | 'warn' | 'ok'; text: string } | null = null;
  function setLaunchNotice(tone: 'err' | 'warn' | 'ok', text: string) {
    launchNotice = { tone, text };
  }
  $: scopedRuns = taskRuns($taskStatus);
  // Koşu provenance'ı: model yalnızca backend'in canlı run.model alanından gelir.
  $: liveRunModels = Object.entries(scopedRuns).filter(([, run]) => (run as any)?.model).map(([agent, run]) => ({ agent, model: (run as any).model }));
  $: activeTaskAgentIds = (() => {
    const ids = new Set<string>(Object.keys(scopedRuns));
    for (const a of ($taskStatus?.planned_agents || [])) if (a) ids.add(String(a));
    for (const a of ($taskStatus?.completed_agents || [])) if (a) ids.add(String(a));
    if ($taskStatus?.current_agent) ids.add(String($taskStatus.current_agent));
    return Array.from(ids);
  })();
  $: channelStatusList = Array.isArray($taskStatus?.channel_status) ? $taskStatus.channel_status : [];
  const liveModelLabel = 'ÇALIŞMA MODELİ';
  let userRituals = '';
  let userPlaylist = '';
  let userEnvies = '';
  $: jurors = ($taskStatus as any)?.output_summary?.jurors ?? null;
  // Dürüstlük sözleşmesi: eksik canlı veri açıkça belirtilir; varsayılan sonuç üretilmez.
  const slotLabels: string[] = [];
  $: readyCount = slotLabels.filter((label) => label === 'READY').length;
  $: errorCount = slotLabels.filter((label) => label === 'ERROR').length;
  const operatorDataLabel = 'OPERATÖR VERİSİ';

  // Dynamic Waveform based on real telemetry resonance score and processing state
  $: waveAmp = $isProcessing ? 22 : ($taskStatus?.resonance_score ? Math.round(Number($taskStatus.resonance_score) * 20) : 6);
  $: dynamicWavePath = `M0,30 Q50,${30 - waveAmp} 100,30 T200,${30 + waveAmp} T300,${30 - Math.round(waveAmp * 0.7)} T400,30`;
  const sourceLabel = 'KAYNAK';
  $: statusSourceText = $agentStatusSource;
  const sourceDescriptions = {
    redis_bus: 'REDIS PUB/SUB',
    in_memory: 'YEREL BELLEK (REDIS YOK)',
  };
  const honestUnavailableLabels = ['veri yok', 'ölçülmedi', 'kanıt yok'];

  // Aktif Ajan Algılama
  $: anyActiveAgent = Object.entries($agentStatuses || {}).find(([k, v]) => (v as any)?.status?.toLowerCase() === 'active');
  $: anyActiveAgentKey = anyActiveAgent ? anyActiveAgent[0] : null;

  $: plainLiveStatus = (() => {
    const st = String($taskStatus?.status || '');
    const cur = $taskStatus?.current_agent ? ($taskStatus.current_agent.toUpperCase()) : null;
    const activeLabel = anyActiveAgentKey ? anyActiveAgentKey.toUpperCase() : null;
    const doneCount = $taskStatus?.completed_agents?.length || 0;
    const planCount = $taskStatus?.planned_agents?.length || 0;
    const tName = $taskStatus?.target_profile?.name || $taskStatus?.target_profile?.username || targetUrl || $activeTargetUrl || '';

    if (st === 'running' || st === 'processing' || (!st && ($isProcessing || anyActiveAgentKey))) {
      const step = cur || activeLabel || 'Kazı & Analiz Sürüyor';
      return `ŞU AN ÇALIŞIYOR: ${tName ? `[${tName}] — ` : ''}${step} (${doneCount}/${planCount} tamamlandı)`;
    }
    if (st === 'partially_completed') return 'GÖREV KİSMİ SONLANDI — tüm koşullar tamamlanmadı.';
    if (st === 'completed' && $taskStatus?.task_outcome === 'completed') return 'PLANLANAN KOŞULLAR BİTTİ — karar durumu BELİRSİZ.';
    if (st === 'completed') return 'GÖREV SONLANDI — tamamlama kanıtı BELİRSİZ.';
    if (st === 'timed_out') return 'GÖREV ZAMAN AŞIMINA UĞRADI.';
    if (st.startsWith('halted') || st === 'failed') return 'GÖREV DURDU.';
    return 'HAZIR — Hedef girin, ajana görev verin veya komutan yetkisiyle kanıt mühürleyin.';
  })();

  // Kazıyıcı Canlı Logları
  $: scraperLogs = ($logs || []).filter(l => {
    const m = (l.msg || '').toUpperCase();
    return m.includes('UPLINK') || m.includes('TELEMETRİ') || m.includes('KAZI') || m.includes('SCRAPE') || m.includes('SENSÖR') || m.includes('INSTAGRAM') || m.includes('X ');
  }).slice(-30);

  function nowTime() {
    return new Date().toLocaleTimeString('tr-TR', { hour12: false });
  }

  async function loadPublicShowcase() {
    // Token GEREKTİRMEZ: bu iki uç auth_middleware allowlist'indedir.
    try {
      const n = await apiFetch('/api/public/notice');
      if (n.ok) legalNotice = await n.json();
    } catch {
      // uyarı metni gelmezse arayüz yine çalışır; sadece satır boş kalır.
    }
    if (demoReports.length) return;
    demoLoading = true;
    demoError = '';
    try {
      const res = await apiFetch('/api/public/demo-reports');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      demoReports = Array.isArray(data?.reports) ? data.reports : [];
      if (demoReports.length && !demoSelected) {
        demoSelected = demoReports[0];
        void loadDemoReport(demoReports[0].id);
      }
    } catch (e: any) {
      demoError = e?.message || 'Örnek raporlar yüklenemedi';
    } finally {
      demoLoading = false;
    }
  }

  async function loadDemoReport(id: string) {
    const existing = demoReports.find((r) => r.id === id && r.findings);
    if (existing) {
      demoSelected = existing;
      return;
    }
    demoLoading = true;
    try {
      const res = await apiFetch(`/api/public/demo-reports/${encodeURIComponent(id)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const full = await res.json();
      demoReports = demoReports.map((r) => (r.id === id ? full : r));
      demoSelected = full;
      demoError = '';
    } catch (e: any) {
      demoError = e?.message || 'Örnek rapor yüklenemedi';
    } finally {
      demoLoading = false;
    }
  }

  onMount(() => {
    void loadPublicShowcase();
    void refreshVaultState();
    void loadRoutingSnapshot();
    missionTimer = setInterval(() => {
      if (missionStartTime) {
        const diff = Math.floor((Date.now() - missionStartTime) / 1000);
        const m = Math.floor(diff / 60).toString().padStart(2, '0');
        const s = (diff % 60).toString().padStart(2, '0');
        missionElapsedStr = `${m}:${s}`;
        missionElapsed.set(missionElapsedStr);
      }
    }, 1000);

    return () => {
      if (missionTimer) clearInterval(missionTimer);
    };
  });

  function formatPresetWithTarget(preset: string): string {
    const t = (targetUrl || $activeTargetUrl || '').trim();
    return t ? `${t} — ${preset}` : preset;
  }

  function selectAgent(agentId: string) {
    selectedAgentId = agentId;
    playClick(400, 30);
    const sov = SOVEREIGNS.find(s => s.id === agentId);
    if (sov && sov.presets.length > 0) {
      inputMessage = formatPresetWithTarget(sov.presets[0]);
    } else {
      const fa = FIELD_AGENTS.find(a => a.id === agentId);
      if (fa && fa.preset) inputMessage = formatPresetWithTarget(fa.preset);
    }
  }

  // --- ACTIONS ---
  async function emergencyStop() {
    playHalt();
    const taskId = $taskStatus?.task_id;
    isProcessing.set(false);
    armEngaged.set(false);

    if (!taskId) {
      chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: 'ACİL DUR tetiklendi: ARM şalteri kapatıldı (aktif görev ID bulunamadı).' }];
      return;
    }

    try {
      const res = await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}/halt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          reason: 'Emergency halt from cockpit'
        })
      });
      if (!res.ok && res.status !== 409) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.error?.message || `HTTP ${res.status}`);
      }
      taskStatus.update(s => s ? { ...s, status: 'halted' } : s);
      chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: `ACİL DUR uygulandı (${taskId}). Görev durduruldu ve ARM kapatıldı.` }];
    } catch (e: any) {
      chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: `ACİL DUR sunucu uyarısı: ${e?.message || e}. Yerel ARM kapatıldı.` }];
    }
  }

  function getPlatformSupportWarning(raw: string, crossEnabled: boolean | undefined): string | null {
    const trimmed = (raw || '').trim();
    if (!trimmed || isPhoneInput(trimmed) || crossEnabled !== false) return null;
    if (!trimmed.includes('.') && !trimmed.includes('://')) return null;
    try {
      const candidate = trimmed.includes('://') ? trimmed : `https://${trimmed}`;
      const host = new URL(candidate).hostname.toLowerCase().replace(/\.$/, '');
      const isNative =
        host === 'instagram.com' || host.endsWith('.instagram.com') || host === 'instagr.am' ||
        host === 'x.com' || host.endsWith('.x.com') ||
        host === 'twitter.com' || host.endsWith('.twitter.com');
      if (isNative) return null;
      return `Platform Uyarısı: "${host}" için çapraz platform taraması (ENABLE_CROSS_PLATFORM) kapalı. Doğrudan kazıma yalnızca Instagram ve X için etkindir.`;
    } catch {
      return null;
    }
  }

  $: platformWarning = getPlatformSupportWarning(targetUrl, routingData?.cross_platform_enabled);

  async function launchAnalysis() {
    const url = targetUrl.trim();
    if (!url || $isProcessing) return;
    // [P0 · DOĞRULAMA 2026-11-23] ARM ŞALTERİ ZORUNLULUĞU KALDIRILDI.
    // Neden: ARM yalnız görsel bir göstergeydi; `disabled` ifadesinde hiç
    // yer almıyordu, ama handler içinde kapıydı. Sonuç: düğme aktif görünür,
    // tıklanınca sessizce sohbete mesaj yazıp geri dönerdi — "hiçbir şey
    // yapmıyor" şikâyetinin ikinci kaynağı buydu. Gerçek kapılar (18+ beyanı,
    // vault interlock, minor gate, rate limit) backend'de ve aşağıda duruyor.
    launchNotice = null;
    if (!isAdultDeclared) {
      const msg = 'Analiz başlatılamadı: hedefin 18 yaşından büyük (reşit) olduğu beyan edilmelidir. Lütfen "18+ REŞİT" kutusunu işaretleyin.';
      setLaunchNotice('err', msg);
      chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: msg }];
      playHalt();
      return;
    }
    const platWarn = getPlatformSupportWarning(url, routingData?.cross_platform_enabled);
    if (platWarn) {
      chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: platWarn }];
    }

    preflightResult = null;
    try {
      const pfRes = await apiFetch('/api/target/preflight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          url,
          scraper_type: 'cross',
        }),
      });
      if (pfRes.ok) {
        const pf = await pfRes.json();
        preflightResult = pf;
        if (pf.eligible === false) {
          playHalt();
          const reasons = Array.isArray(pf.reasons) && pf.reasons.length
            ? pf.reasons.join(' | ')
            : 'Hedef ön-kontrolü geçemedi.';
          // Tek kanal: uyarı düğmenin altında. Sohbete de yazılırsa aynı metin
          // iki kez görünür ve kullanıcı hangisinin güncel olduğunu bilemez.
          setLaunchNotice('err', `Ön-kontrol engeli [${pf.platform || 'unknown'}]: ${reasons}`);
          return;
        }
      }
    } catch {
      // Ağ hatası durumunda /api/initiate kendi güvenlik kapılarını uygular
    }

    isProcessing.set(true);
    activeTargetUrl.set(url);
    missionStartTime = Date.now();
    playRunning();

    chatMessages = [...chatMessages, {
      ts: nowTime(),
      sender: 'Aspasia',
      text: `Görev başlatma isteği gönderiliyor: [${url}]. Çalışan kanallar ve ajanlar sunucudan bildirilince gösterilecek.`
    }];

    try {
      const res = await apiFetch('/api/initiate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId,
          url,
          rituals: contextRituals.trim(),
          playlist: contextPlaylist.trim(),
          envies: contextEnvies.trim(),
          scraper_type: 'cross',
        })
      });
      if (!res.ok) {
        if (isAuthFailure(res)) throw new Error('PINEAL_TOKEN yetki hatası');
        if (res.status === 423) throw new Error('KASA KİLİTLİ (423): Lütfen üst paneldeki Kasa mandalını açın.');
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson?.error?.message || errJson?.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      launchNotice = null;
      if (data.task_id) {
        // Aynı görevin WS sonucu yanıttan önce gelmiş olabilir; onu ezme.
        // Yeni görevde önceki görevin kanıt ve özetlerini asla taşıma.
        taskStatus.update(s => s?.task_id === data.task_id ? s : mergeTaskSnapshot(null, { task_id: data.task_id, status: 'processing' }));
      }
      chatMessages = [...chatMessages, {
        ts: nowTime(),
        sender: 'Aspasia',
        text: data.task_id
          ? `Görev kabul edildi (ID: ${data.task_id}) — [${url}]. Planlanan ajanlar ve sensörler arka planda başlatılıyor; canlı durumlar akıştan izlenecek.`
          : `Görev kabul edildi — [${url}]. Canlı durumlar akıştan izlenecek.`
      }];
    } catch (e: any) {
      isProcessing.set(false);
      playHalt();
      setLaunchNotice('err', `Görev başlatılamadı: ${e?.message || e}`);
    }
  }

  function isPhoneInput(val: string): boolean {
    if (!val) return false;
    const clean = val.trim();
    if (clean.startsWith('http://') || clean.startsWith('https://')) return false;
    const digits = clean.replace(/[^\d]/g, '');
    return digits.length >= 7 && (clean.includes('(') || clean.includes('-') || clean.startsWith('+') || clean.startsWith('0') || digits.length >= 10);
  }

  async function probePhoneAction() {
    const phone = targetUrl.trim();
    if (!phone || isProbingPhone) return;
    // [KVKK · 2026-11-23] Düğme disabled olsa bile burada tekrar kontrol:
    // `disabled` yalnızca UI'dır; programatik tıklamayı (ve fireEvent'i) durdurmaz.
    if (!phoneConsentGiven) {
      setLaunchNotice('err', 'Telefon sorgusu için önce "AÇIK RIZA ALINDI" kutusunu işaretleyin.');
      return;
    }
    launchNotice = null;
    isProbingPhone = true;
    playClick(480, 50);

    chatMessages = [...chatMessages, {
      ts: nowTime(),
      sender: 'OSINT İSTİHBARAT',
      text: `Telefon numarası analiz ediliyor: [${phone}] (Operatör, şebeke ve mesajlaşma protokolleri taranıyor...)`
    }];

    try {
      const res = await apiFetch('/api/commander/phone-probe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          phone,
          auto_bridge_social: false,
          // KVKK md.4: açık rıza beyanı. Kutu işaretlenmeden istek gidemez.
          subject_consent: phoneConsentGiven
        })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      phoneProbeResult = await res.json();
      playClick(700, 60);

      const m = phoneProbeResult.metadata;
      chatMessages = [...chatMessages, {
        ts: nowTime(),
        sender: 'OSINT İSTİHBARAT',
        text: `[${m.e164 || phone}] Şebeke: ${m.carrier_name || 'Bilinmiyor'} | Bölge: ${m.country_name} | Tür: ${m.line_type}. WhatsApp ve Telegram doğrudan linkleri hazırlandı.`
      }];
    } catch (e: any) {
      playHalt();
      chatMessages = [...chatMessages, {
        ts: nowTime(),
        sender: 'OSINT İSTİHBARAT',
        text: `Telefon sorgulaması başarısız: ${e?.message || e}`
      }];
    } finally {
      isProbingPhone = false;
    }
  }

  async function loadTaskHistory() {
    tasksLoading = true;
    tasksError = '';
    try {
      const cid = $clientId || 'default';
      const res = await apiFetch(`/api/tasks?client_id=${encodeURIComponent(cid)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      taskHistoryList = Array.isArray(data.tasks) ? data.tasks : [];
    } catch (e: any) {
      tasksError = e?.message || 'Görev geçmişi alınamadı';
    } finally {
      tasksLoading = false;
    }
  }

  async function loadPastTaskIntoCockpit(taskId: string) {
    tasksError = '';
    try {
      const cid = $clientId || 'default';
      const res = await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}?client_id=${encodeURIComponent(cid)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const detail = await res.json();
      taskStatus.set({
        task_id: detail.task_id,
        status: detail.status || 'completed',
        confidence: detail.confidence,
        target_profile: detail.target_profile || null,
        evidence_chain: Array.isArray(detail.evidence_chain) ? detail.evidence_chain : [],
        runs: {},
      });
      if (detail.target_profile?.url) {
        reportSubject = detail.target_profile.url;
      } else if (detail.target_profile?.username) {
        reportSubject = `@${detail.target_profile.username}`;
      }
      reportTitle = `Pineal Rapor — ${detail.task_id}`;
      showHistoryModal = false;
      chatMessages = [...chatMessages, {
        ts: nowTime(),
        sender: 'Aspasia',
        text: `Geçmiş görev yüklendi: ${detail.task_id} (${detail.evidence_count ?? 0} kanıt kaydı).`
      }];
    } catch (e: any) {
      tasksError = e?.message || 'Görev detayı yüklenemedi';
    }
  }

  async function deletePastTask(taskId: string) {
    tasksError = '';
    try {
      const cid = $clientId || 'default';
      const res = await apiFetch(`/api/tasks/${encodeURIComponent(taskId)}?client_id=${encodeURIComponent(cid)}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadTaskHistory();
    } catch (e: any) {
      tasksError = e?.message || 'Görev silinemedi';
    }
  }

  async function loadReportCenter() {
    reportStatusLoading = true;
    try {
      const cid = $clientId || 'default';
      const [sRes, lRes] = await Promise.all([
        apiFetch('/api/report/status'),
        apiFetch(`/api/report/list?client_id=${encodeURIComponent(cid)}`),
      ]);
      if (sRes.ok) reportStatusData = await sRes.json();
      if (lRes.ok) {
        const lJson = await lRes.json();
        reportListData = Array.isArray(lJson.reports) ? lJson.reports : [];
      }
    } catch {
      // non-fatal
    } finally {
      reportStatusLoading = false;
    }
  }

  function openHistoryModal(tab: 'tasks' | 'reports' = 'tasks') {
    historyTab = tab;
    showHistoryModal = true;
    if (!reportSubject) {
      reportSubject = targetUrl || $activeTargetUrl || $taskStatus?.target_profile?.url || '';
    }
    void loadTaskHistory();
    void loadReportCenter();
  }

  async function buildReportFromCockpit() {
    if (reportBuilding) return;
    reportBuilding = true;
    reportBuildError = '';
    reportBuildResult = null;
    const selectedFormats = Object.entries(reportFormats)
      .filter(([, on]) => on)
      .map(([fmt]) => fmt);
    if (selectedFormats.length === 0) {
      reportBuildError = 'En az bir çıktı formatı seçin.';
      reportBuilding = false;
      return;
    }
    const evidenceItems = evidenceChainToReportItems($taskStatus);
    try {
      const res = await apiFetch('/api/report/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          title: (reportTitle || 'Pineal Adli Analiz Raporu').trim(),
          subject: (reportSubject || targetUrl || $activeTargetUrl || '').trim(),
          evidence: evidenceItems,
          formats: selectedFormats,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data?.error?.message || `HTTP ${res.status}`);
      }
      reportBuildResult = data;
      await loadReportCenter();
    } catch (e: any) {
      reportBuildError = e?.message || 'Rapor üretilemedi';
    } finally {
      reportBuilding = false;
    }
  }

  async function injectCommanderEvidence() {
    if (!injectValue.trim() || isInjecting) return;
    isInjecting = true;
    playClick(450, 40);

    try {
      const res = await apiFetch('/api/commander/inject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          evidence_type: injectType,
          evidence_value: injectValue.trim(),
          target_agent: injectTargetAgent,
          note: injectNote.trim()
        })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.error?.message || `HTTP ${res.status}`);
      if (data?.status !== 'stored' || data?.applied_to_agent !== false) {
        throw new Error('Kanıt kaydı doğrulanamadı.');
      }
      playClick(700, 60);

      injectHistory = [{
        type: injectType,
        value: injectValue.trim(),
        target: injectTargetAgent,
        note: injectNote.trim(),
        ts: nowTime()
      }, ...injectHistory];

      chatMessages = [...chatMessages, {
        ts: nowTime(),
        sender: 'MANUEL KANIT GİRİŞİ',
        text: `Kanıt kaydedildi [${injectType.toUpperCase()}]; ajana veya göreve aktarım henüz bağlı değil.`
      }];
      injectValue = '';
      injectNote = '';
    } catch (e: any) {
      playHalt();
      alert('Kanıt kaydedilemedi: ' + (e?.message || e));
    } finally {
      isInjecting = false;
    }
  }

  function formatLilithReply(data: any): string {
    const parts: string[] = [];
    const lilith = data?.lilith || {};
    const neuro = data?.neuro_metrics || lilith?.neuro_metrics;
    if (lilith.hook) parts.push(`ETKİLEŞİM: ${lilith.hook}`);
    if (lilith.psychological_angle) parts.push(`AÇI: ${lilith.psychological_angle}`);
    if (neuro) {
      const vc = neuro.viral_coefficient_score ?? '?';
      const dom = neuro.dominant_neurotransmitter ?? '?';
      const src = data?.metrics_source || 'formül';
      parts.push(`NÖRO FORMÜL [${src}]: Vc=${vc}/10 · Baskın=${dom}`);
    }
    const hookStudio = data?.hook_studio || {};
    if (hookStudio.evidence_verification_status) {
      parts.push(`ETKİLEŞİM DOĞRULAMASI: ${hookStudio.evidence_verification_status}${hookStudio.data_confidence ? ' (doğrulandı)' : ' (doğrulanmadı)'}`);
    }
    if (data?.shadow?.strategy) {
      parts.push(`BÜYÜME STRATEJİSİ: ${data.shadow.strategy}`);
    }
    const moves = Array.isArray(data?.counter_moves) ? data.counter_moves : [];
    if (moves.length > 0) {
      const moveLines = moves.map((m: any) => `• [${m.scenario}] ${m.our_counter_move}`);
      parts.push(`KARŞI HAMLELER:\n${moveLines.join('\n')}`);
    }
    if (data?.fallback_reason) {
      const why = data.fallback_reason;
      parts.push(why === 'engine_signals_missing'
        ? 'Not: Nöro formülü üretilemedi (motor sinyali yok) — yalnız metin çıktısı gösteriliyor.'
        : `Not: ${why} (üretim çıktısı; doğrulanmış kanıt değildir).`);
    }
    if (hookStudio.fallback_reason) {
      parts.push(`Kanca hattı: ${hookStudio.fallback_reason}.`);
    }
    return parts.join('\n') || 'Lilith strateji hattından yanıt döndü.';
  }

  async function sendAspasiaMessage() {
    const text = inputMessage.trim();
    if (!text || isSending) return;
    inputMessage = '';
    isSending = true;
    chatMessages = [...chatMessages, { ts: nowTime(), sender: 'SÖZ', text }];

    try {
      const activeTaskId = ($taskStatus as any)?.task_id || null;
      const targetHint = (targetUrl || '').trim().replace(/^https?:\/\/(?:www\.)?(?:instagram\.com|x\.com|twitter\.com)\//i, '').replace(/\/.*$/, '').replace(/^@/, '') || undefined;

      // 1. LILITH hattı seçiliyse doğrudan birleşik /api/lilith/strategy motorunu çalıştır
      if (selectedAgentId === 'lilith') {
        const lRes = await apiFetch('/api/lilith/strategy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: $clientId,
            task_id: activeTaskId,
            instruction: text,
            target_username: targetHint,
          })
        });
        if (!lRes.ok) {
          const errBody = await lRes.json().catch(() => ({}));
          throw Object.assign(new Error(errBody?.error?.message || `HTTP ${lRes.status}`), { status: lRes.status });
        }
        const lData = await lRes.json();
        chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Lilith', text: formatLilithReply(lData) }];
        return;
      }

      // 2. Hafıza Kristali, İlişki Grafı veya Şirket/Domain sorgusuysa /api/brain/route'a bağlan
      const lower = text.toLocaleLowerCase('tr-TR').replace(/\u0307/g, '');
      const isBrainSpecial =
        /(hafıza|hafiza|kristal|ilişki graf|iliski graf|bağlantı haritası|baglanti haritasi)/.test(lower) ||
        (/(şirket|sirket|kurum|domain|alan adı|alan adi|firma)/.test(lower) && /\.[a-z]{2,}\b/i.test(text));
      if (isBrainSpecial) {
        const bRes = await apiFetch('/api/brain/route', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: $clientId,
            message: text,
            mode: 'auto',
            task_id: activeTaskId,
            target: targetHint,
          })
        });
        if (!bRes.ok) {
          const errBody = await bRes.json().catch(() => ({}));
          throw Object.assign(new Error(errBody?.error?.message || `HTTP ${bRes.status}`), { status: bRes.status });
        }
        const bData = await bRes.json();
        const r = bData?.result || {};
        const summary =
          r.machine_note ||
          (bData?.route === 'graph'
            ? `İlişki grafı: ${r.node_count ?? 0} düğüm, ${r.edge_count ?? 0} bağ (${r.available ? 'hazır' : r.reason || 'kanıt yok'}).`
            : bData?.route === 'company'
              ? `Kurum taraması (${bData.domain || ''}): ${r.available ? 'tamamlandı' : r.reason || 'kapı kapalı'}.`
              : JSON.stringify(r).slice(0, 320));
        chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: `[${String(bData?.route || 'brain').toUpperCase()}] ${summary}` }];
        return;
      }

      let commandReason = '';
      try {
        const command = await apiFetch('/api/aspasia/command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ client_id: $clientId, user_message: text })
        });
        if ([401, 403, 423, 429, 451].includes(command.status)) {
          const errBody = await command.json().catch(() => ({}));
          throw Object.assign(new Error(errBody?.error?.message || `HTTP ${command.status}`), { status: command.status });
        }
        if (command.ok) {
          const data = await command.json();
          if (data.accepted && data.task_id) {
            isProcessing.set(true);
            taskStatus.update(s => ({ ...(s || {}), task_id: data.task_id, status: 'processing' }));
            chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: `Emir alındı. Görev: ${data.task_id}` }];
            return;
          }
          commandReason = data.reason || 'görev başlatılmadı';
        } else {
          commandReason = `komut kanalı HTTP ${command.status}`;
        }
      } catch (error: any) {
        if (error?.status && [401, 403, 423, 429, 451].includes(error.status)) throw error;
        commandReason = 'komut durumu doğrulanamadı';
      }
      const res = await apiFetch('/api/aspasia/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: $clientId, user_message: text })
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw Object.assign(new Error(errBody?.error?.message || `HTTP ${res.status}`), { status: res.status });
      }
      const data = await res.json();
      if (data.error) throw new Error(data.error.message || data.error.code || 'sohbet kullanılamıyor');
      const reply = data.message || data.reply || data.response || 'Sohbet yanıtı boş.';
      chatMessages = [...chatMessages, { ts: nowTime(), sender: 'Aspasia', text: `Komut: ${commandReason}. ${reply}` }];
    } catch (e: any) {
      const status = (e as any)?.status;
      const detail = e?.message ? ` (${e.message})` : '';
      let text: string;
      if (status === 423) {
        text = `Kasa kilitli — dış dünyaya hiçbir istek çıkamaz. Anahtarı girip kasayı açın, sonra tekrar deneyin.${detail}`;
      } else if (status === 451) {
        text = `Reşitlik kapısı — bu hedef için çalışma yapılamaz (çocuk kilidi).${detail}`;
      } else if (status === 429) {
        text = 'Hız sınırı — kısa bir mola verip tekrar deneyin.';
      } else if (status === 401 || status === 403) {
        text = `Yetki reddedildi.${detail}`;
      } else {
        text = `Bağlantı kesintisi: ${e?.message || e}`;
      }
      chatMessages = [...chatMessages, { ts: nowTime(), sender: selectedAgentId === 'lilith' ? 'Lilith' : 'Aspasia', text }];
    } finally {
      isSending = false;
    }
  }

  async function refreshVaultState() {
    const cid = $clientId || 'default';
    try {
      const res = await apiFetch(`/api/vault/status?client_id=${encodeURIComponent(cid)}`);
      if (isAuthFailure(res)) {
        // [P0 · 2026-11-23] Kasa hakkında bir şey bilinmiyor — bu bir KASA
        // hatası değil, ERİŞİM sorunu. Eski mesaj "Kasa durumu doğrulanamadı:
        // HTTP 401" idi ve kullanıcı kasayı açmaya çalışıyordu.
        apiAuthRequired.set(true);
        throw new Error('yetki gerekli (PINEAL_TOKEN)');
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const state = await res.json();
      if (typeof state?.locked !== 'boolean') throw new Error('Geçersiz kasa durumu');
      if (cid !== ($clientId || 'default')) throw new Error('İstemci değişti');
      vaultLocked.set(state.locked);
      vaultKnown = true;
      return state.locked as boolean;
    } catch (error: any) {
      vaultKnown = false;
      vaultError = `Kasa durumu doğrulanamadı: ${error?.message || 'ağ hatası'}`;
      return null;
    }
  }

  async function toggleVaultLock() {
    if (vaultBusy) return;
    vaultBusy = true;
    vaultError = '';
    try {
      // [P0 · 2026-11-23] Yetki yoksa kasa mandalı değil, token girişi gerekir.
      if ($apiAuthRequired) {
        vaultError = 'Sunucu yetki anahtarı (PINEAL_TOKEN) gerekli. Api anahtarı penceresinden girin.';
        openSettingsModal('providers');
        return;
      }
      if (!vaultKnown) {
        await refreshVaultState();
        return;
      }
      const desiredLocked = !$vaultLocked;
      const res = await apiFetch('/api/vault/status', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: $clientId || 'default', action: desiredLocked ? 'lock' : 'unlock' })
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body?.error?.message || `HTTP ${res.status}`);
      const actual = await refreshVaultState();
      if (actual !== null && actual !== desiredLocked) vaultError = 'Kasa istenen duruma geçmedi.';
      if (actual === desiredLocked) playClick(400, 30);
    } catch (error: any) {
      const detail = error?.message || 'ağ hatası';
      await refreshVaultState();
      vaultError = `Kasa işlemi başarısız: ${detail}`;
    } finally {
      vaultBusy = false;
    }
  }
</script>

<main class="command-deck">
  <!-- ==================== 1. MASTER HUD HEADER ==================== -->
  <header class="master-hud-header">
    <!-- Sol: Marka + Canlı Durum -->
    <div class="hud-brand">
      <span class="pulse-beacon" class:active={$isProcessing}></span>
      <div class="brand-titles">
        <h1 class="brand-title">PINEAL EPİFİZ</h1>
        <span class="live-status-badge">{plainLiveStatus}</span>
        <p class="intro-help">Pineal, erişilebilen açık kaynak verilerini araştırmanıza yardımcı olur. Başlamak için hedef girin, "18+ REŞİT" beyanını işaretleyin ve analizi başlatın. Kullanılabilir kaynaklar kurulum ve platforma göre değişir.</p>
        {#if legalNotice?.headline}
          <p class="intro-notice">{legalNotice.headline}</p>
        {/if}
      </div>
    </div>

    <!-- Orta: Hedef Kaseti -->
    <div class="target-cassette-bar">
      <div class="cassette-input-wrap">
        <span class="cassette-icon"><Icon name="target" /></span>
        <input
          type="text"
          class="cassette-text-input"
          bind:value={targetUrl}
          placeholder="Hedef Profil URL, @kullanıcı veya Telefon (örn: (552) 956-87-63)..."
          disabled={$isProcessing || isProbingPhone}
          on:keydown={(e) => {
            if (e.key === 'Enter') {
              if (isPhoneInput(targetUrl)) probePhoneAction();
              else launchAnalysis();
            }
          }}
        />
      </div>
      {#if isPhoneInput(targetUrl)}
        <label class="consent-badge" title="Telefon numarası KVKK md.6 uyarınca kişisel veridir. İşlenmesi için hedefin açık rızası gerekir (md.4).">
          <input type="checkbox" bind:checked={phoneConsentGiven} />
          <span>AÇIK RIZA ALINDI</span>
        </label>
        <button
          class="phone-launch-btn"
          class:is-running={isProbingPhone}
          on:click={probePhoneAction}
          disabled={isProbingPhone || !phoneConsentGiven}
          title={phoneConsentGiven
            ? 'Numarayı OSINT Sensörleriyle Tara'
            : 'Önce "AÇIK RIZA ALINDI" kutusunu işaretleyin — telefon numarası kişisel veridir.'}
        >
          <Icon name="target" size={0.85} />
          {isProbingPhone ? 'TARANIYOR...' : 'NUMARAYI SORGULA'}
        </button>
      {/if}
      <label class="adult-consent-badge" title="Hedef kişinin 18 yaşından büyük (reşit) olduğu beyanıdır.">
        <input type="checkbox" bind:checked={isAdultDeclared} />
        <span>18+ REŞİT</span>
      </label>
      <button
        class="cassette-launch-btn"
        class:is-running={$isProcessing}
        on:click={launchAnalysis}
        disabled={$isProcessing || !targetUrl.trim() || !isAdultDeclared}
      >
        <Icon name={$isProcessing ? 'refresh' : 'triangle-up'} size={0.85} />
        {$isProcessing ? 'ANALİZ EDİLİYOR...' : 'ANALİZİ BAŞLAT'}
      </button>
      <button
        type="button"
        class="context-toggle-btn"
        class:is-open={showContextInputs}
        on:click={() => showContextInputs = !showContextInputs}
        title="Kişisel alışkanlıklar, çalma listesi ve hedef bağlamını ekle"
      >
        <Icon name={showContextInputs ? 'chevron-down' : 'sparkle'} size={0.85} />
        {showContextInputs ? 'BAĞLAMI KAPAT' : 'BAĞLAM (ALIŞKANLIK / MÜZİK / HEDEF)'}
      </button>
      {#if showContextInputs}
        <div class="context-inputs-flyout">
          <input
            type="text"
            class="context-mini-input"
            bind:value={contextRituals}
            placeholder="Kişisel alışkanlıklar (örn: Gece okumaları, felsefe, çay)..."
          />
          <input
            type="text"
            class="context-mini-input"
            bind:value={contextPlaylist}
            placeholder="Çalma Listesi / Müzik (örn: Neşet Ertaş, Klasik, Ambient)..."
          />
          <input
            type="text"
            class="context-mini-input"
            bind:value={contextEnvies}
            placeholder="Derin Hedef / Arzu (örn: Sahici ve derin bağ kurmak)..."
          />
        </div>
      {/if}
      {#if platformWarning}
        <div class="platform-warning" role="status">{platformWarning}</div>
      {/if}
    </div>

    <!-- [P0 · DOĞRULAMA 2026-11-23] Başlatma sonucu düğmenin hemen altında.
         Eskiden tüm hatalar yalnız sohbet akışına yazılıyordu. -->
    {#if launchNotice}
      <div class="launch-notice {launchNotice.tone}" role="alert">
        <Icon name={launchNotice.tone === 'ok' ? 'check' : 'warning'} size={0.9} />
        <span>{launchNotice.text}</span>
      </div>
    {/if}

    <!-- Sağ: Sistem Metrikleri + Şalterler + Acil Stop + Vault -->
    <div class="hud-meters">
      <div class="hud-switches" role="group" aria-label="Konsol Şalterleri">
        <button
          type="button"
          class="hud-switch-btn"
          class:engaged={$powerEngaged}
          aria-pressed={$powerEngaged}
          on:click={() => { playClick(520, 35); powerEngaged.update(v => !v); }}
          title="Bağlantı ve güç durumu"
        >
          <span class="switch-dot"></span>GÜÇ
        </button>
        <button
          type="button"
          class="hud-switch-btn arm-switch"
          class:engaged={$armEngaged}
          aria-pressed={$armEngaged}
          on:click={() => { playClick(620, 40); armEngaged.update(v => !v); }}
          title="Hazır durumu göstergesi — analizi başlatmak için zorunlu değildir"
        >
          <span class="switch-dot"></span>HAZIR
        </button>
        <button
          type="button"
          class="hud-switch-btn rec-switch"
          class:engaged={$recordEngaged}
          aria-pressed={$recordEngaged}
          on:click={() => { playClick(480, 35); recordEngaged.update(v => !v); }}
          title="Kayıt ve loglama"
        >
          <span class="switch-dot"></span>KAYIT
        </button>
        <button
          type="button"
          class="emergency-stop-btn"
          on:click={emergencyStop}
          title="Aktif görevi acil durdur ve hazır durumunu kapat"
        >
          <Icon name="stop" size={0.9} /> ACİL DUR
        </button>
      </div>
      <div class="hud-meter-box" title="Geçen Görev Süresi">
        <span class="hm-icon"><Icon name="clock" /></span>
        <span class="hm-val">{missionElapsedStr}</span>
      </div>
      <button
        class="settings-gear-btn history-hub-btn"
        data-testid="open-demo-btn"
        on:click={() => { showDemoModal = true; void loadPublicShowcase(); }}
        title="Ürünün çıktısını gösteren 2 sentetik örnek rapor — token gerektirmez"
      >
        <Icon name="file" size={0.9} /> ÖRNEK RAPORLAR
      </button>
      <button
        class="settings-gear-btn"
        data-testid="open-terms-btn"
        on:click={() => { showTermsModal = true; void loadPublicShowcase(); }}
        title="Sorumluluk reddi ve kullanım koşulları"
      >
        <Icon name="warning" size={0.9} /> KULLANIM KOŞULLARI
      </button>
      <button
        class="settings-gear-btn history-hub-btn"
        data-testid="open-history-btn"
        on:click={() => openHistoryModal('tasks')}
        title="Görev Geçmişi, Rapor Fabrikası ve Geçmiş Raporlar"
      >
        <Icon name="scroll" size={0.9} /> GEÇMİŞ &amp; RAPORLAR
      </button>
      <button
        class="settings-gear-btn"
        data-testid="open-settings-btn"
        on:click={() => openSettingsModal('providers')}
        title="Çoklu LLM Sağlayıcı Anahtarları, Arama Motorları ve Ajan-Model Haritası"
      >
        <Icon name="key" size={0.9} /> API ANAHTARLARI &amp; MODEL HARİTASI
      </button>
      <!--
        [AUDIT 2026-11-17 · EK H.2-F] TR/EN dil düğmesi BURADAN KALDIRILDI.
        Sebep (ölçüldü): `frontend/src/i18n.ts` 94 TR + 94 EN anahtarı taşıyor,
        ama bunların yalnız **10'u** bugünkü arayüz metinleriyle birebir örtüşüyor
        (appTitle, active, vaultSaving, liveStatus, playlistPlaceholder, confidence,
        runningBtn, system, resonanceScore, statusRunning). Tablo eski yerleşim için
        yazılmış: örn. `initiateBtn="ANALİZİ BAŞLAT"` ama ekrandaki düğme
        "KAZIYI BAŞLAT". Düğme bu hâliyle `currentLang`'ı değiştiriyor, ekranda
        değişen tek şey düğmenin kendi harfleri oluyordu — Tüzük §3.3'ün
        yasakladığı "çalışır görünen kontrol".
        Gerçek iki dillilik ayrı bir iştir: 94 anahtarın güncellenmesi + eksik
        anahtarların eklenmesi + çocuk kilidi/KVKK metinlerinin çeviri incelemesi.
        O iş bitmeden bu düğme geri konmamalı.
      -->

      <button
        class="vault-lock-btn"
        class:locked={!vaultKnown || $vaultLocked}
        on:click={toggleVaultLock}
        disabled={vaultBusy}
        title={$apiAuthRequired
          ? 'Sunucu yetki anahtarı (PINEAL_TOKEN) gerekli — ayarlar penceresini açar'
          : !vaultKnown ? 'Kasa durumu bilinmiyor — yeniden kontrol et'
          : $vaultLocked ? 'Kasa kilitli — açmayı dene' : 'Kasa açık — kilitle'}
      >
        <span class="vault-dot"></span>
        <span class="vault-label">{$apiAuthRequired ? 'ERİŞİM: YETKİ GEREKLİ' : !vaultKnown ? 'KASA DURUMU BİLİNMİYOR' : $vaultLocked ? 'KASA KİLİTLİ' : 'KASA AÇIK'}</span>
      </button>
    </div>
    {#if vaultError}<span role="alert" class="vault-error">{vaultError}</span>{/if}
  </header>

  <!-- ==================== 2. ANA 3 SÜTUNLU GÖVDE ==================== -->
  <div class="master-grid-container">

    <!-- SÜTUN 1: DANIŞMAN AJANLAR (Sol - 28%) -->
    <section class="column-deck col-left">
      <div class="deck-title-ribbon">
        <span class="ribbon-icon"><Icon name="diamond" /></span>
        <h2>DANIŞMAN AJANLAR</h2>
      </div>

      <!-- ASPASIA -->
      <div
        class="sovereign-station aspasia-station {selectedAgentId === 'aspasia' ? 'selected' : ''}"
        role="button"
        tabindex="0"
        aria-pressed={selectedAgentId === 'aspasia'}
        on:click={() => selectAgent('aspasia')}
        on:keydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectAgent('aspasia'); } }}
      >
        <div class="station-header">
          <span class="station-glyph" style="color: #10b981;"><Icon name="diamond" /></span>
          <div>
            <h3 class="station-name">ASPASIA</h3>
            <span class="station-role">Baş Stratejist & Argüman Analisti</span>
          </div>
          <span class="station-badge badge-green">STRATEJİ</span>
        </div>
        <p class="station-desc">Sokratik sorgulama, argüman analizi, stratejik sentez ve empatik yaklaşım</p>
        <div class="station-presets">
          {#each SOVEREIGNS[0].presets as p}
            <button class="preset-btn" on:click|stopPropagation={() => { selectAgent('aspasia'); inputMessage = formatPresetWithTarget(p); }}>
              <Icon name="diamond" size={0.8} /> {p.slice(0, 36)}...
            </button>
          {/each}
        </div>
      </div>

      <!-- LILITH -->
      <div
        class="sovereign-station lilith-station {selectedAgentId === 'lilith' ? 'selected' : ''}"
        role="button"
        tabindex="0"
        aria-pressed={selectedAgentId === 'lilith'}
        on:click={() => selectAgent('lilith')}
        on:keydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectAgent('lilith'); } }}
      >
        <div class="station-header">
          <span class="station-glyph" style="color: #ec4899;"><Icon name="sparkle" /></span>
          <div>
            <h3 class="station-name">LILITH</h3>
            <span class="station-role">Büyüme & Nörobilim</span>
          </div>
          <span class="station-badge badge-pink">BÜYÜME</span>
        </div>
        <p class="station-desc">Dopamin döngüsü, amigdala tepkisi, içerik viralliği ve büyüme taktikleri</p>
        <div class="station-presets">
          {#each SOVEREIGNS[1].presets as p}
            <button class="preset-btn btn-pink" on:click|stopPropagation={() => { selectAgent('lilith'); inputMessage = formatPresetWithTarget(p); }}>
              <Icon name="sparkle" size={0.8} /> {p.slice(0, 36)}...
            </button>
          {/each}
        </div>
      </div>

      <!-- MANUEL KANIT GİRİŞİ -->
      <div class="commander-override-box">
        <div class="box-header">
          <span class="box-icon"><Icon name="triangle-up" /></span>
          <h3>MANUEL KANIT GİRİŞİ</h3>
        </div>
        <p class="box-sub">Kanıtları kaydedin. Ajanlara veya aktif göreve aktarım henüz bağlı değil; hedef seçimi yalnızca kayıt bilgisidir.</p>

        <div class="override-form">
          <div class="form-dual-fields">
            <select bind:value={injectType} class="select-field">
              <option value="twin_url">Eş Profil URL (Twin URL)</option>
              <option value="phone">Telefon Numarası / GSM</option>
              <option value="bio_fact">Biyografi / Meslek Bilgisi</option>
              <option value="ground_truth">Doğrulanmış Bilgi (Ground Truth)</option>
              <option value="note">Kritik Not</option>
            </select>
            <select bind:value={injectTargetAgent} class="select-field">
              <option value="all">Tümü (kayıt etiketi)</option>
              <option value="lilith">Lilith (Büyüme & Etkileşim)</option>
              <option value="osint_investigator">OSINT Investigator</option>
              <option value="depth_analyst">Depth Analyst</option>
            </select>
          </div>
          <input
            type="text"
            class="input-field"
            bind:value={injectValue}
            placeholder="Kanıtı girin (örn: https://x.com/gercek_hesap veya 'Mesleği Mimar')..."
          />
          <input
            type="text"
            class="input-field"
            bind:value={injectNote}
            placeholder="Ek not (opsiyonel)..."
          />
          <button
            class="override-submit-btn"
            class:injecting={isInjecting}
            on:click={injectCommanderEvidence}
            disabled={isInjecting || !injectValue.trim()}
          >
            <Icon name={isInjecting ? 'refresh' : 'sparkle'} size={0.85} />
            {isInjecting ? 'KAYDEDİLİYOR...' : 'KANITI KAYDET'}
          </button>
        </div>

        {#if injectHistory.length > 0}
          <div class="inject-history-ticker">
            <span class="ticker-title">KAYDEDİLEN KANITLAR:</span>
            {#each injectHistory.slice(0, 2) as h}
              <div class="ticker-row">
                <span class="t-type">[{h.type.toUpperCase()}]</span>
                <span class="t-val">{h.value}</span>
                <span class="t-agent"><Icon name="arrow-right" size={0.85} /> {h.target}</span>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </section>

    <!-- SÜTUN 2: 12 SAHA AJANI & CANLI MUHAKEME (Orta - 44%) -->
    <section class="column-deck col-center">
      <div class="deck-title-ribbon">
        <span class="ribbon-icon"><Icon name="triangle-up" /></span>
        <h2>12 ANALİZ AJANI & CANLI MUHAKEME (CHAIN-OF-THOUGHT)</h2>
      </div>

      <!-- GÖREVDE GERÇEKTEN ÇALIŞAN AJANLAR -->
      {#if activeTaskAgentIds.length > 0}
        <div class="field-matrix-grid">
          {#each activeTaskAgentIds as agId}
            {@const agMeta = FIELD_AGENTS.find(a => a.id === agId)}
            {@const run = scopedRuns[agId]}
            {@const rStatus = run ? taskRunLabel(run) : ($taskStatus?.current_agent === agId ? 'RUNNING' : 'PLANNED')}
            {@const isActive = rStatus === 'ACTIVE' || rStatus === 'RUNNING'}
            {@const isReady = rStatus === 'DONE' || rStatus === 'READY' || rStatus === 'COMPLETED'}
            {@const isError = rStatus === 'FAILED' || rStatus === 'ERROR' || rStatus === 'HALTED'}
            {@const isWait = !isActive && !isReady && !isError}
            <div
              class="agent-tile {isActive ? 'active' : ''} {isReady ? 'ready' : ''} {isError ? 'error' : ''} {isWait ? 'wait' : ''} {selectedAgentId === agId ? 'selected' : ''}"
              style="--agent-color: {agMeta?.color || '#06b6d4'};"
              on:click={() => selectAgent(agId)}
              role="button"
              tabindex="0"
              on:keydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectAgent(agId); } }}
            >
              <div class="tile-glyph"><Icon name={agMeta?.icon || 'diamond'} size={1.3} /></div>
              <div class="tile-info">
                <div class="tile-name">{agMeta?.name || agId.toUpperCase()}</div>
                <div class="tile-short">{run?.model || 'model bekleniyor'}</div>
                <div class="tile-route">
                  {#if Array.isArray(run?.call_ids) && run.call_ids.length > 0}
                    LLM ÇAĞRI KİMLİĞİ: {run.call_ids.slice(0, 2).join(', ')}
                  {:else}
                    {routeChain(agId)}
                  {/if}
                </div>
                <div class="tile-tier">{routeTier(agId)} · {routeSource(agId)}</div>
              </div>
              <div class="tile-status" style="color: {agMeta?.color || '#06b6d4'};">
                <span class="status-pulse" style="background: {agMeta?.color || '#06b6d4'};"></span>
                <span class="status-label">{rStatus}</span>
              </div>
              {#if isActive}
                <div class="activity-bar"><div class="activity-fill"></div></div>
              {/if}
            </div>
          {/each}
        </div>
      {:else}
        <div class="cot-empty" style="margin-bottom: 0.5rem;">
          <p>Bu görevde henüz çalışmış ajan yok.</p>
          <small>Hedef girip ANALİZİ BAŞLAT dediğinizde yalnızca bu görevde gerçekten koşan ajanlar burada görünür.</small>
        </div>
      {/if}

      <details class="catalog-details">
        <summary>Sistemdeki Ajan Kataloğu ({FIELD_AGENTS.length} ajan)</summary>
        <div class="field-matrix-grid" style="margin-top: 0.45rem;">
          {#each FIELD_AGENTS as ag}
            <div
              class="agent-tile wait {selectedAgentId === ag.id ? 'selected' : ''}"
              style="--agent-color: {ag.color};"
              on:click={() => selectAgent(ag.id)}
              role="button"
              tabindex="0"
              on:keydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectAgent(ag.id); } }}
            >
              <div class="tile-glyph"><Icon name={ag.icon} size={1.3} /></div>
              <div class="tile-info">
                <div class="tile-name">{ag.name}</div>
                <div class="tile-route" title={routeChain(ag.id)}>{routeChain(ag.id)}</div>
                <div class="tile-tier">{routeTier(ag.id)} · {routeSource(ag.id)}</div>
              </div>
            </div>
          {/each}
        </div>
      </details>

      <!-- VERİ KANALLARI (channel_status) -->
      {#if channelStatusList.length > 0}
        <div class="channel-status-box">
          <div class="cot-header">
            <span class="cot-icon"><Icon name="satellite" /></span>
            <h3>VERİ KANALLARI (channel_status — {channelStatusList.length})</h3>
          </div>
          <div class="channel-list">
            {#each channelStatusList as ch}
              {@const cStatus = String(ch?.status || 'unknown').toLowerCase()}
              <div class="channel-row" class:ch-ok={cStatus === 'ok'} class:ch-fail={cStatus === 'failed' || cStatus === 'timed_out' || cStatus === 'unavailable' || cStatus === 'not_run'}>
                <span class="ch-name">{ch?.channel || 'kanal'}</span>
                <span class="ch-badge">{cStatus.toUpperCase()}</span>
                {#if ch?.reason || ch?.detail}
                  <span class="ch-reason">{ch.reason || ch.detail}</span>
                {/if}
              </div>
            {/each}
          </div>
        </div>
      {/if}

      <!-- SOVEREIGN PULSE BAR -->
      <div class="sovereign-pulse-section">
        <div class="pulse-header">
          <span class="pulse-icon"><Icon name="approx" /></span>
          <h3>AJAN SENKRONİZASYONU (ASPASIA / LILITH)</h3>
        </div>
        <div class="pulse-waveform" aria-label="Senkronizasyon dalgaformu">
          <svg viewBox="0 0 400 60" preserveAspectRatio="none">
            <defs>
              <linearGradient id="pulseGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#10b981" />
                <stop offset="50%" stop-color="#ec4899" />
                <stop offset="100%" stop-color="#10b981" />
              </linearGradient>
            </defs>
            <path
              class="wave-path"
              class:processing={$isProcessing}
              d={dynamicWavePath}
              stroke="url(#pulseGrad)"
              stroke-width="2"
              fill="none"
              stroke-linecap="round"
              style="filter: drop-shadow(0 0 6px #10b981);"
            />
            <path
              class="wave-glow"
              class:processing={$isProcessing}
              d={dynamicWavePath}
              stroke="#ec4899"
              stroke-width="1"
              fill="none"
              stroke-linecap="round"
              style="opacity: 0.4; filter: drop-shadow(0 0 12px #ec4899);"
            />
          </svg>
          <div class="pulse-metrics">
            <span class="pulse-metric"><strong>ASPASIA</strong> <Icon name="diamond" size={0.8} /></span>
            <span class="pulse-metric"><strong>LILITH</strong> <Icon name="sparkle" size={0.8} /></span>
            <span class="pulse-metric">FREKANS: <span class="freq-val">{$taskStatus?.resonance_result?.frequency_hz ? `${$taskStatus.resonance_result.frequency_hz} Hz` : ($isProcessing ? 'Ölçülüyor...' : 'Beklemede')}</span></span>
            <span class="pulse-metric">SENKRON: <span class="sync-val">{$taskStatus?.resonance_score != null ? `${Math.round($taskStatus.resonance_score * 100)}%` : ($isProcessing ? 'Hesaplanıyor...' : '—')}</span></span>
          </div>
        </div>
      </div>

      <!-- TELEFON OSINT İSTİHBARAT KARTI -->
      {#if phoneProbeResult}
        <div class="phone-osint-dossier-card">
          <div class="pod-header">
            <span class="pod-icon"><Icon name="phone" /></span>
            <div class="pod-title-block">
              <span class="pod-title">TELEFON OSINT İSTİHBARATI</span>
              <strong class="pod-num">{phoneProbeResult.metadata?.e164 || phoneProbeResult.phone_input}</strong>
            </div>
            <button type="button" class="pod-close-btn" on:click={() => { phoneProbeResult = null; }} aria-label="Telefon kartını kapat"><Icon name="close" size={0.9} /></button>
          </div>

          <div class="pod-grid">
            <div class="pod-chip">
              <span class="pod-lbl">Operatör / Şebeke</span>
              <strong class="pod-val highlight-gold">{phoneProbeResult.metadata?.carrier_name || 'Bilinmiyor'}</strong>
            </div>
            <div class="pod-chip">
              <span class="pod-lbl">Ülke & Bölge</span>
              <span class="pod-val">{phoneProbeResult.metadata?.country_name || 'Bilinmiyor'}</span>
            </div>
            <div class="pod-chip">
              <span class="pod-lbl">Hat Türü</span>
              <span class="pod-val">{phoneProbeResult.metadata?.line_type || 'Bilinmiyor'}</span>
            </div>
            <div class="pod-chip">
              <span class="pod-lbl">Doğruluk</span>
              <span class="pod-val highlight-green">{phoneProbeResult.metadata?.is_valid ? 'Geçerli numara formatı' : 'Doğrulanamadı'}</span>
            </div>
          </div>

          {#if (phoneProbeResult.messaging_probes || []).length > 0}
            <div class="pod-messaging-strip">
              <span class="pod-sub-title">Açık Profil / Doğrudan Kanallar:</span>
              <div class="pod-actions-row">
                {#each phoneProbeResult.messaging_probes as mp}
                  <a href={mp.url} target="_blank" rel="noopener noreferrer" class="pod-action-pill" title={mp.note}>
                    <strong>{mp.platform}</strong> Profilini Aç
                  </a>
                {/each}
              </div>
            </div>
          {/if}

          {#if (phoneProbeResult.associated_handles || []).length > 0}
            <div class="pod-handles-strip">
              <span class="pod-sub-title">Doğrulanmamış aday kullanıcı adları (@):</span>
              <div class="pod-handle-pills">
                {#each phoneProbeResult.associated_handles as handle}
                  <button
                    type="button"
                    class="pod-handle-btn"
                    on:click={() => { targetUrl = handle; launchAnalysis(); }}
                    title="Bu kullanıcı adını doğrudan analize al"
                  >
                    @{handle} — [ANALİZE AL]
                  </button>
                {/each}
              </div>
            </div>
          {/if}

          {#if (phoneProbeResult.social_probes || []).length > 0}
            <div class="pod-social-strip">
              <span class="pod-sub-title">İlişkisi doğrulanmamış aday profiller:</span>
              <div class="pod-social-pills">
                {#each phoneProbeResult.social_probes as sp}
                  <a href={sp.url} target="_blank" rel="noopener noreferrer" class="pod-social-pill">
                    {sp.platform.toUpperCase()}: @{sp.handle}
                  </a>
                {/each}
              </div>
            </div>
          {/if}

          <button
            type="button"
            class="pod-inject-btn"
            on:click={() => {
              injectType = 'phone';
              injectValue = `${phoneProbeResult.metadata?.e164 || phoneProbeResult.phone_input} (${phoneProbeResult.metadata?.carrier_name || 'Bilinmiyor'})`;
              injectCommanderEvidence();
            }}
          >
            <Icon name="flame" size={0.9} /> Bu Numarayı Kanıt Olarak Kaydet
          </button>
        </div>
      {/if}

      <!-- CANLI KANIT ZİNCİRİ (BACKEND evidence_chain) -->
      <div class="chain-of-thought-section">
        <div class="cot-header">
          <span class="cot-icon"><Icon name="triangle-down" /></span>
          <h3>CANLI KANIT ZİNCİRİ (evidence_chain — {evidenceChain.length})</h3>
          <button
            type="button"
            class="cot-report-shortcut"
            on:click={() => openHistoryModal('reports')}
            title="Bu kanıt zincirinden Rapor Fabrikası ile rapor üret"
          >
            <Icon name="file" size={0.9} /> Rapor Üret
          </button>
        </div>
        <div class="cot-content">
          {#if evidenceChain.length > 0}
            <div class="thought-chain">
              {#each evidenceChain.slice(0, 12) as item, i}
                {@const ep = item?.epistemic_type || item?.evidence_type || 'kayıt'}
                {@const src = item?.provenance?.engine || item?.source_agent || item?.agent || 'bilinmiyor'}
                {@const conf = item?.uncertainty?.confidence ?? item?.result?.confidence ?? item?.confidence}
                <div class="thought-node" style="--delay: {i * 40}ms;">
                  <span class="thought-index">{i + 1}</span>
                  <span class="thought-text">
                    <strong>{item?.agent || 'pipeline'}</strong> · [{ep}] · kaynak: {src}
                    {#if typeof conf === 'number'} · güven: {conf <= 1 ? Math.round(conf * 100) : Math.round(conf)}%{/if}
                  </span>
                </div>
              {/each}
            </div>
          {:else if $taskStatus?.current_agent}
            <div class="cot-placeholder">
              <span class="cot-agent">{$taskStatus.current_agent.toUpperCase()}</span>
              <span class="cot-action">kanıt topluyor...</span>
              <div class="cot-typing"><span></span><span></span><span></span></div>
            </div>
          {:else}
            <div class="cot-empty">
              <span class="empty-glyph"><Icon name="triangle-down" /></span>
              <p>Henüz mühürlenmiş kanıt zinciri yok.</p>
              <small>Operasyon başlatın veya Geçmiş &amp; Raporlar üzerinden önceki bir görevi yükleyin.</small>
            </div>
          {/if}
        </div>
      </div>

      <!-- SEÇİLİ AJAN GERÇEK KOŞU / KANIT DETAYI -->
      {#if selectedAgentId && (scopedRuns[selectedAgentId] || evidenceChain.some((e: any) => e?.agent === selectedAgentId || e?.source_agent === selectedAgentId))}
        {@const selRun = scopedRuns[selectedAgentId]}
        {@const selChain = evidenceChain.filter((e: any) => e?.agent === selectedAgentId || e?.source_agent === selectedAgentId)}
        <div class="selected-agent-detail">
          <div class="detail-header">
            <span class="detail-glyph" style="color: {FIELD_AGENTS.find(a => a.id === selectedAgentId)?.color || SOVEREIGNS.find(s => s.id === selectedAgentId)?.accent}">
              <Icon name={FIELD_AGENTS.find(a => a.id === selectedAgentId)?.icon || SOVEREIGNS.find(s => s.id === selectedAgentId)?.icon || 'sparkle'} size={1.4} />
            </span>
            <h3>{selectedAgentId.toUpperCase()} — CANLI ANALİZ &amp; KANIT ({selChain.length})</h3>
          </div>
          <div class="detail-output">
            {#if selRun}
              <div>Durum: <strong>{selRun.status || '-'}</strong> · Model: <code>{selRun.model || 'bilinmiyor'}</code></div>
            {/if}
            {#each selChain.slice(0, 3) as entry}
              <div class="detail-chain-row">[{entry.epistemic_type || entry.evidence_type || 'kanıt'}] {JSON.stringify(entry.result ?? entry.content ?? entry).slice(0, 220)}</div>
            {/each}
          </div>
        </div>
      {/if}
    </section>

    <!-- SÜTUN 3: 7 ADLİ SÜTUN + ASPASIA SOHBET + TELEMETRİ (Sağ - 28%) -->
    <section class="column-deck col-right">
      <div class="deck-title-ribbon deck-title-stack">
        <div class="ribbon-row">
          <span class="ribbon-icon"><Icon name="triangle-down" /></span>
          <h2>7 ANALİZ KATEGORİSİ — RADAR</h2>
        </div>
        <small class="pillars-sub">Ajanlar + 7 deterministik dalga motoru (Frequency, Seismos, Void, Strata, Gravity, Pulse, Key) bulgularını toplar</small>
      </div>

      <p class="summary-disclaimer">Bu kartlar analiz özetleridir; tek başına doğrulanmış kanıt değildir. Skorların kaynakları ve güven düzeyi burada gösterilmiyor.</p>

      <!-- 7 ADLİ SÜTUN GRİD -->
      <div class="pillars-grid">
        {#each PILLARS as p}
          {@const summary = (pillarSummaries as any)[p.id]}
          {@const hasData = getPillarHasData(p.id) || Boolean(summary?.hasData)}
          <div class="pillar-column {hasData ? 'has-data' : ''} {p.id}-pillar" style="--pillar-color: {p.color};">
            <div class="pillar-header">
              <span class="pillar-icon">{p.icon}</span>
              <span class="pillar-label">{p.label}</span>
              <span class="pillar-badge">{hasData ? 'ÖZET VERİ' : 'VERİ YOK'}</span>
              <span class="pillar-badge">{hasData ? `KANIT (${summary?.evidenceCount ?? 0})` : 'YETERSİZ / YOK'}</span>
            </div>
            <div class="pillar-content">
              <div class="pillar-epistemic-meta">
                <span><strong>Kanıt:</strong> {summary?.evidenceCount ?? 0}</span>
                <span><strong>Güven:</strong> {summary?.confidence !== null && summary?.confidence !== undefined ? summary.confidence + '%' : 'ölçülmedi'}</span>
                <span><strong>Kaynak:</strong> {summary?.sources?.length ? summary.sources.slice(0, 2).join(', ') : 'yok'}</span>
                <span><strong>Epistemik:</strong> {summary?.epistemicTypes?.length ? summary.epistemicTypes.join(', ') : 'yok'}</span>
                <span><strong>Yeterlilik:</strong> {summary?.sufficiency || 'yetersiz'}</span>
              </div>
              {#if hasData}
                <div class="evidence-preview">
                  {#if p.id === 'follower' && followerAudit}
                    <div class="evidence-item"><strong>Ortalama:</strong> {followerAudit.avg_followers ?? '—'}</div>
                    <div class="evidence-item"><strong>Gerçeklik:</strong> {followerAudit.authenticity_score !== undefined ? followerAudit.authenticity_score + '%' : '—'}</div>
                    <div class="evidence-item"><strong>Bot Riski:</strong> {followerAudit.bot_risk !== undefined ? followerAudit.bot_risk + '%' : '—'}</div>
                  {:else if p.id === 'timing' && timingForensics}
                    <div class="evidence-item"><strong>Saat Dağılımı:</strong> {timingForensics.hour_distribution ? 'Mevcut' : '—'}</div>
                    <div class="evidence-item"><strong>Otomatik Skor:</strong> {timingForensics.automation_score !== undefined ? timingForensics.automation_score + '%' : '—'}</div>
                    <div class="evidence-item"><strong>Zaman Dilimi:</strong> {timingForensics.timezone_inferred || '—'}</div>
                  {:else if p.id === 'depth' && depthReport}
                    <div class="evidence-item">
                      <strong>Gerçeklik Endeksi (0–1):</strong>
                      {typeof depthReport.reality_index === 'number' ? depthReport.reality_index.toFixed(2) : '—'}
                    </div>
                    <div class="evidence-item">
                      <strong>Özet:</strong>
                      {depthReport.essence_one_liner || '—'}
                    </div>
                    <div class="evidence-item">
                      <strong>Bulgu / Çelişki:</strong>
                      {(depthReport.reality_findings?.length || 0) + ' / ' + (depthReport.contradictions?.length || 0)}
                    </div>
                  {:else if p.id === 'visual' && visualEvidence}
                    <div class="evidence-item"><strong>Görsel Tutarlılık:</strong> {visualEvidence.consistency_score !== undefined ? visualEvidence.consistency_score + '%' : '—'}</div>
                    <div class="evidence-item"><strong>Deepfake Riski:</strong> {visualEvidence.deepfake_risk !== undefined ? visualEvidence.deepfake_risk + '%' : '—'}</div>
                    <div class="evidence-item"><strong>Estetik İmza:</strong> {visualEvidence.aesthetic_signature || '—'}</div>
                  {:else if p.id === 'shadow' && shadowProfile}
                    <div class="evidence-item"><strong>Gölge Hesaplar:</strong> {shadowProfile.shadow_accounts?.length || 0}</div>
                    <div class="evidence-item"><strong>Bağlantı Ağırlığı:</strong> {shadowProfile.link_weight !== undefined ? shadowProfile.link_weight : '—'}</div>
                    <div class="evidence-item"><strong>Koordinasyon:</strong> {shadowProfile.coordination_score !== undefined ? shadowProfile.coordination_score + '%' : '—'}</div>
                  {:else if p.id === 'osint' && osintFootprint}
                    <div class="evidence-item"><strong>Kullanıcı Adları:</strong> {osintFootprint.usernames?.length || 0}</div>
                    <div class="evidence-item"><strong>E-posta Sızıntıları:</strong> {osintFootprint.email_leaks?.length || 0}</div>
                    <div class="evidence-item"><strong>Telefon:</strong> {osintFootprint.phone_exposed == null ? 'Bilinmiyor' : osintFootprint.phone_exposed ? 'Açık' : 'Kapalı'}</div>
                  {:else if p.id === 'resonance' && resonanceCalc}
                    <div class="evidence-item"><strong>Rezonans Açısı:</strong> {resonanceCalc.resonance_angle !== undefined ? resonanceCalc.resonance_angle + '°' : '—'}</div>
                    <div class="evidence-item"><strong>Uyum Skoru:</strong> {(resonanceCalc.alignment_score ?? resonanceCalc.compatibility_score) !== undefined ? (resonanceCalc.alignment_score ?? resonanceCalc.compatibility_score) + '%' : '—'}</div>
                    <div class="evidence-item"><strong>Vektör Uzayı:</strong> {resonanceCalc.vector_dimensions || '—'} boyut</div>
                  {:else if summary?.chainEntries?.length}
                    <div class="evidence-item"><strong>Zincir Kaydı:</strong> {JSON.stringify(summary.chainEntries[0]?.result ?? summary.chainEntries[0]).slice(0, 140)}</div>
                  {:else}
                    <div class="evidence-empty">Yapılandırılmış özet bekleniyor...</div>
                  {/if}
                </div>
              {:else}
                <div class="evidence-empty">
                  <span class="empty-pulse"></span>
                  <small>Henüz veri yok. Operasyon başlatın.</small>
                </div>
              {/if}
            </div>
            <div class="pillar-footer">
              <span class="pillar-tr">{p.tr}</span>
            </div>
          </div>
        {/each}
      </div>

      <TaskEvidence task={$taskStatus} />

      <!-- ASPASIA CANLI SOHBET -->
      <div class="aspasia-chat-section">
        <div class="chat-header">
          <span class="chat-icon" style="color: #10b981;"><Icon name="diamond" /></span>
          <h3>ASPASIA CANLI SOHBET</h3>
          <span class="chat-status" class:speaking={$speechState === 'speaking'}>{$speechState === 'speaking' ? 'KONUŞUYOR' : $speechState === 'listening' ? 'DİNLİYOR' : $speechState === 'denied' ? 'MOTOR YOK' : 'HAZIR'}</span>
        </div>
        <div class="chat-messages">
          {#each chatMessages.slice(-40) as msg}
            <div class="chat-message {msg.sender === 'Aspasia' ? 'from-aspasia' : msg.sender === 'SÖZ' ? 'from-user' : 'from-agent'}">
              <span class="msg-time">{msg.ts}</span>
              <span class="msg-sender">{msg.sender}</span>
              <span class="msg-text">{msg.text}</span>
            </div>
          {/each}
        </div>
        <div class="chat-input-area">
          <input
            type="text"
            class="chat-input"
            bind:value={inputMessage}
            placeholder="Aspasia ile konuşun... (Enter ile gönder)"
            on:keydown={(e) => e.key === 'Enter' && sendAspasiaMessage()}
            disabled={isSending}
          />
          <button class="chat-send-btn" on:click={sendAspasiaMessage} disabled={isSending || !inputMessage.trim()}>
            <Icon name={isSending ? 'refresh' : 'sparkle'} size={0.9} />
          </button>
        </div>
      </div>

      <!-- TELEMETRİ PANOSU (Açılır) -->
      <div class="telemetry-section">
        <button class="telemetry-toggle" on:click={() => telemetryVisible = !telemetryVisible} aria-expanded={telemetryVisible}>
          <Icon name={telemetryVisible ? 'chevron-down' : 'chevron-up'} size={0.85} />
          {telemetryVisible ? 'TELEMETRİYİ GİZLE' : 'TELEMETRİYİ GÖSTER'}
        </button>
        {#if telemetryVisible}
          <div class="telemetry-panel">
            <div class="telemetry-row">
              <div class="telemetry-item">
                <span class="tl-label">UPLINK</span>
                <span class="tl-value" class:online={$uplinkState === 'ONLINE'}>{$uplinkState}</span>
              </div>
              <div class="telemetry-item">
                <span class="tl-label">HEALTH</span>
                <span class="tl-value">{$health?.status || '—'}</span>
              </div>
              <div class="telemetry-item">
                <span class="tl-label">BÜTÇE</span>
                <span class="tl-value">${$sysTelemetry?.spendUsd || 0} / ${$sysTelemetry?.spendCapUsd || 0}</span>
              </div>
            </div>
            <div class="telemetry-row">
              <div class="telemetry-item">
                <span class="tl-label">LATENCY</span>
                <span class="tl-value">{$health?.latencyMs !== null ? $health.latencyMs + 'ms' : '—'}</span>
              </div>
              <div class="telemetry-item">
                <span class="tl-label">AGENT SRC</span>
                <span class="tl-value">{$agentStatusSource || '—'}</span>
              </div>
              <div class="telemetry-item">
                <span class="tl-label">VAULT</span>
                <span class="tl-value">{$vaultLocked ? 'KİLİTLİ' : 'AÇIK'}</span>
              </div>
            </div>
          </div>
        {/if}
      </div>
    </section>
  </div>

  <!-- ==================== 3. ALT KAYAN VERİ HAVUZU (LOGS) ==================== -->
  <footer class="data-pool-footer">
    <div class="pool-header">
      <span class="pool-icon"><Icon name="chevron-down" /></span>
      <h3>CANLI VERİ AKIŞI — SON 30 KAYIT</h3>
    </div>
    <div class="pool-logs">
      {#each scraperLogs as log}
        <div class="pool-log" style="border-left-color: {log.level === 'ERROR' ? '#ef4444' : log.level === 'WARNING' ? '#f59e0b' : '#10b981'};">
          <span class="pl-time">{log.ts}</span>
          <span class="pl-level">{log.level}</span>
          <span class="pl-msg">{log.msg}</span>
        </div>
      {:else}
        <div class="pool-empty">Log akışı bekleniyor... (UPLINK kurulduğunda başlar)</div>
      {/each}
    </div>
  </footer>

  {#if showHistoryModal}
    <div class="cockpit-modal-backdrop" role="dialog" aria-modal="true" aria-label="Görev Geçmişi ve Rapor Fabrikası">
      <div class="cockpit-modal-card">
        <div class="cockpit-modal-head">
          <h3><Icon name="scroll" size={0.95} /> GÖREV GEÇMİŞİ &amp; RAPOR FABRİKASI</h3>
          <button class="modal-close-btn" on:click={() => showHistoryModal = false} aria-label="Kapat"><Icon name="close" size={0.9} /></button>
        </div>

        <div class="cockpit-modal-tabs">
          <button class:active={historyTab === 'tasks'} on:click={() => { historyTab = 'tasks'; void loadTaskHistory(); }}>
            Görev Geçmişi ({taskHistoryList.length})
          </button>
          <button class:active={historyTab === 'reports'} on:click={() => { historyTab = 'reports'; void loadReportCenter(); }}>
            Rapor Fabrikası &amp; Geçmiş Raporlar ({reportListData.length})
          </button>
        </div>

        <div class="cockpit-modal-body">
          {#if historyTab === 'tasks'}
            <div class="modal-section-box">
              <div class="history-toolbar">
                <h4>Kayıtlı Görevler <code class="endpoint-path">GET /api/tasks</code></h4>
                <button type="button" class="modal-cancel-btn" on:click={loadTaskHistory} disabled={tasksLoading}>
                  {tasksLoading ? 'Yükleniyor...' : 'Yenile'}
                </button>
              </div>
              {#if tasksError}
                <div class="modal-alert err">{tasksError}</div>
              {/if}
              {#if tasksLoading && taskHistoryList.length === 0}
                <p class="routing-note">Görev geçmişi yükleniyor...</p>
              {:else if taskHistoryList.length === 0}
                <p class="routing-note">Bu oda için henüz kayıtlı görev yok.</p>
              {:else}
                <div class="routing-table-wrap">
                  <table class="routing-table">
                    <thead>
                      <tr>
                        <th>Görev ID</th>
                        <th>Durum</th>
                        <th>Kanıt</th>
                        <th>Güven</th>
                        <th>Tarih</th>
                        <th>İşlem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {#each taskHistoryList as t}
                        <tr>
                          <td class="rt-agent">{t.task_id}</td>
                          <td>{t.status || t.memory_state || '-'}</td>
                          <td>{t.evidence_count ?? 0}</td>
                          <td>{typeof t.confidence === 'number' ? Math.round(t.confidence * 100) + '%' : '-'}</td>
                          <td>{t.last_updated || '-'}</td>
                          <td class="history-actions">
                            <button type="button" class="mini-action-btn" on:click={() => loadPastTaskIntoCockpit(t.task_id)}>YÜKLE</button>
                            <button type="button" class="mini-action-btn danger" on:click={() => deletePastTask(t.task_id)}>SİL</button>
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              {/if}
            </div>
          {:else}
            <div class="modal-section-box">
              <h4>Rapor Fabrikası — Kanıttan Rapor Üret (POST /api/report/build)</h4>
              {#if reportStatusData}
                <p class="routing-note">
                  Kapı: <code>{reportStatusData.gate}</code> · Dizin: <code>{reportStatusData.report_dir}</code>
                </p>
                <div class="format-chips">
                  {#each reportStatusData.formats || [] as fmt}
                    <label class="format-chip" class:disabled={!fmt.available}>
                      <input type="checkbox" bind:checked={reportFormats[fmt.format]} />
                      <span>{fmt.format.toUpperCase()}</span>
                      <small>({fmt.available ? 'hazır' : fmt.reason || 'yok'})</small>
                    </label>
                  {/each}
                </div>
              {:else if reportStatusLoading}
                <p class="routing-note">Rapor fabrikası durumu kontrol ediliyor...</p>
              {/if}

              <div class="provider-grid" style="margin-top: 0.6rem;">
                <label class="provider-field">
                  <span>Rapor Başlığı</span>
                  <input type="text" bind:value={reportTitle} placeholder="Pineal Adli Analiz Raporu" />
                </label>
                <label class="provider-field">
                  <span>Konu / Hedef</span>
                  <input type="text" bind:value={reportSubject} placeholder="https://instagram.com/..." />
                </label>
              </div>
              <p class="routing-note" style="margin-top: 0.45rem;">
                Aktif kanıt zincirinden taşınacak satır: <strong>{evidenceChainToReportItems($taskStatus).length}</strong>
              </p>
              <div style="margin-top: 0.5rem;">
                <button type="button" class="modal-save-btn" on:click={buildReportFromCockpit} disabled={reportBuilding}>
                  {reportBuilding ? 'ÜRETİLİYOR...' : 'RAPOR PAKETİ ÜRET'}
                </button>
              </div>

              {#if reportBuildError}
                <div class="modal-alert err" style="margin-top: 0.5rem;">{reportBuildError}</div>
              {/if}
              {#if reportBuildResult}
                <div class="modal-alert ok" style="margin-top: 0.5rem;">
                  <strong>Rapor sonucu ({reportBuildResult.title}):</strong>
                  {#each Object.entries(reportBuildResult.formats || {}) as [fmtName, fmtRes]}
                    {@const r = fmtRes as any}
                    <div class="report-res-row">
                      <code>{fmtName}</code>: {r.available ? 'ÜRETİLDİ' : `ENGELLENDİ / YOK (${r.denied_by || r.reason || 'bilinmiyor'})`}
                      {#if r.manifest_sha256} · sha256: <code>{r.manifest_sha256.slice(0, 12)}…</code>{/if}
                    </div>
                  {/each}
                </div>
              {/if}
            </div>

            <div class="modal-section-box">
              <div class="history-toolbar">
                <h4>Geçmiş Raporlar (GET /api/report/list)</h4>
                <button type="button" class="modal-cancel-btn" on:click={loadReportCenter} disabled={reportStatusLoading}>
                  <Icon name="refresh" size={0.85} /> Yenile
                </button>
              </div>
              {#if reportListData.length === 0}
                <p class="routing-note">Henüz üretilmiş rapor paketi bulunamadı.</p>
              {:else}
                <div class="report-history-list">
                  {#each reportListData as rep}
                    <div class="report-history-card">
                      <div class="rh-head">
                        <strong>{rep.title}</strong>
                        <span>{rep.created_at || '-'}</span>
                      </div>
                      <div class="rh-meta">
                        Hedef: {rep.subject || '-'} · Kanıt: {rep.evidence_count} · Manifest: <code>{(rep.manifest_sha256 || '').slice(0, 12)}…</code>
                      </div>
                      <div class="rh-links">
                        {#each rep.artifacts || [] as art}
                          {#if art.download_url}
                            <a class="report-dl-link" href={`${art.download_url}?client_id=${encodeURIComponent($clientId || "default")}`} target="_blank" rel="noopener">
                              <Icon name="download" size={0.85} /> {art.kind} ({art.bytes} B)
                            </a>
                          {/if}
                        {/each}
                        {#if rep.manifest_url}
                          <a class="report-dl-link" href={`${rep.manifest_url}?client_id=${encodeURIComponent($clientId || "default")}`} target="_blank" rel="noopener"><Icon name="download" size={0.85} /> manifest.json</a>
                        {/if}
                      </div>
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  {#if showSettingsModal}
    <div class="cockpit-modal-backdrop" role="presentation" on:click|self={() => (showSettingsModal = false)}>
      <div class="cockpit-modal-card" role="dialog" aria-modal="true" aria-label="Ayarlar ve Çoklu LLM Kasası">
        <div class="cockpit-modal-head">
          <div>
            <h3><Icon name="gear" size={0.95} /> AYARLAR, ÇOKLU LLM KASASI &amp; AJAN MODEL HARİTASI</h3>
            <p class="cockpit-modal-sub">Her sağlayıcıya doğrudan anahtar girin; sistemdeki her ajan/özellik kendi uzman modelini kullanır.</p>
          </div>
          <button class="modal-x-btn" on:click={() => (showSettingsModal = false)} aria-label="Kapat"><Icon name="close" size={0.9} /></button>
        </div>

        <div class="cockpit-modal-tabs">
          <button class:active={settingsTab === 'providers'} on:click={() => (settingsTab = 'providers')}>Çoklu LLM Anahtarları</button>
          <button class:active={settingsTab === 'search'} on:click={() => (settingsTab = 'search')}>Arama & Oturum (OSINT)</button>
          <button class:active={settingsTab === 'routing'} on:click={() => { settingsTab = 'routing'; void loadRoutingSnapshot(); }}>Ajan &gt; Model Haritası ({routingData?.routing?.agents ? Object.keys(routingData.routing.agents).length : 21})</button>
        </div>

        <div class="cockpit-modal-body">
          {#if settingsTab === 'providers'}
            <div class="modal-section-box">
              <h4>Doğrudan Aktif Rota Sağlayıcıları (llm_gateway)</h4>
              <div class="provider-grid">
                {#each DIRECT_PROVIDERS as prov}
                  {@const isSet = (routingData?.provider_keys_set || []).includes(prov.id)}
                  <label class="provider-field">
                    <span class="pf-top">
                      <span>{prov.label}</span>
                      <span class="pf-badge" class:active={isSet}>{isSet ? 'AKTİF' : 'BOŞ'}</span>
                    </span>
                    <input type="password" placeholder={prov.placeholder} bind:value={providerInputs[prov.id]} />
                  </label>
                {/each}
              </div>
            </div>

            <div class="modal-section-box">
              <h4>Tanı / Envanter Sağlayıcıları (Doğrudan Taşıyıcı Yok — Claude/GPT/Grok OpenRouter Üzerinden Çalışır)</h4>
              <div class="provider-grid">
                {#each DIAGNOSTIC_PROVIDERS as prov}
                  {@const isSet = (routingData?.provider_keys_set || []).includes(prov.id)}
                  <label class="provider-field">
                    <span class="pf-top">
                      <span>{prov.label}</span>
                      <span class="pf-badge" class:active={isSet}>{isSet ? 'KAYITLI (TANI)' : 'BOŞ'}</span>
                    </span>
                    <input type="password" placeholder={prov.placeholder} bind:value={providerInputs[prov.id]} />
                  </label>
                {/each}
              </div>
            </div>

            <div class="modal-section-box">
              <h4>OpenRouter Yedek Anahtarı & Yetki Tokenı</h4>
              <div class="provider-grid">
                <label class="provider-field">
                  <span class="pf-top">
                    <span>OpenRouter (Yedek / Çoklu Model Ağ Geçidi)</span>
                    <span class="pf-badge" class:active={routingData?.has_openrouter}>{routingData?.has_openrouter ? 'AKTİF' : 'BOŞ'}</span>
                  </span>
                  <input type="password" placeholder="sk-or-v1-..." bind:value={openRouterInput} />
                </label>
                <label class="provider-field">
                  <span class="pf-top"><span>PINEAL_TOKEN (Sunucu Yetki Anahtarı)</span></span>
                  <input type="password" placeholder="Opsiyonel (üretim modu için)" bind:value={appTokenInput} />
                </label>
              </div>
            </div>

            <div class="modal-section-box">
              <h4>Yerel LLM (Ollama / LM Studio)</h4>
              <label class="local-toggle-row">
                <input type="checkbox" bind:checked={useLocal} />
                <span>Yerel LLM Kullan (Bulut yerine yerel model)</span>
              </label>
              <div class="provider-grid">
                <label class="provider-field">
                  <span class="pf-top"><span>Base URL</span></span>
                  <input type="text" bind:value={localUrl} placeholder="http://localhost:11434/v1" />
                </label>
                <label class="provider-field">
                  <span class="pf-top"><span>Model Adı</span></span>
                  <input type="text" bind:value={localModel} placeholder="dolphin-llama3:latest" />
                </label>
              </div>
            </div>
          {:else if settingsTab === 'search'}
            <div class="modal-section-box">
              <h4>OSINT Arama Motoru Anahtarları & Sosyal Oturum</h4>
              <div class="provider-grid">
                <label class="provider-field">
                  <span class="pf-top">
                    <span>Tavily API Key</span>
                    <span class="pf-badge" class:active={routingData?.has_tavily}>{routingData?.has_tavily ? 'AKTİF' : 'BOŞ'}</span>
                  </span>
                  <input type="password" placeholder="tvly-..." bind:value={tavilyKey} />
                </label>
                <label class="provider-field">
                  <span class="pf-top">
                    <span>SerpAPI Key</span>
                    <span class="pf-badge" class:active={routingData?.has_serpapi}>{routingData?.has_serpapi ? 'AKTİF' : 'BOŞ'}</span>
                  </span>
                  <input type="password" placeholder="..." bind:value={serpapiKey} />
                </label>
                <label class="provider-field">
                  <span class="pf-top">
                    <span>Exa API Key</span>
                    <span class="pf-badge" class:active={routingData?.has_exa}>{routingData?.has_exa ? 'AKTİF' : 'BOŞ'}</span>
                  </span>
                  <input type="password" placeholder="..." bind:value={exaKey} />
                </label>
                <label class="provider-field">
                  <span class="pf-top"><span>Instagram Session / Cookie (sessionid)</span></span>
                  <input type="password" placeholder="sessionid=... veya doğrudan sessionid" bind:value={igCookie} />
                </label>
                <label class="provider-field">
                  <span class="pf-top"><span>X / Twitter Cookie (auth_token / ct0)</span></span>
                  <input type="password" placeholder="auth_token=...; ct0=..." bind:value={xCookie} />
                </label>
              </div>
            </div>
          {:else}
            <div class="modal-section-box">
              <h4>Gerçek Ajan &amp; Özellik / Uzman Model Zinciri (llm_gateway)</h4>
              <p class="routing-note">Bu tablo OpenRouter tekilleştirmesi değildir: her ajan kendi tier ve uzman zinciriyle çalışır. Kaynak <strong>9router_canonical</strong> görünüyorsa aktif 9Router overlay zinciri üstüne yazmaktadır.</p>
              {#if routingData?.routing?.tier_violations && Object.keys(routingData.routing.tier_violations).length > 0}
                <div class="routing-warning"><Icon name="warning" size={0.85} /> Tier uyarıları: {Object.entries(routingData.routing.tier_violations).map(([name, reason]) => `${name}: ${reason}`).join(' · ')}</div>
              {/if}
              {#if routingLoading && !routingData}
                <p class="routing-note">Model haritası yükleniyor...</p>
              {:else if routingData?.routing?.agents}
                <div class="routing-table-wrap">
                  <table class="routing-table">
                    <thead>
                      <tr>
                        <th>Ajan / Özellik</th>
                        <th>Tier</th>
                        <th>Uzman Model Zinciri (Sırayla)</th>
                        <th>Kaynak / Durum</th>
                      </tr>
                    </thead>
                    <tbody>
                      {#each Object.entries(routingData.routing.agents as Record<string, any>) as [agentName, info]}
                        <tr>
                          <td class="rt-agent">{agentName}</td>
                          <td class="rt-tier">{info?.tier || routingData?.routing?.tiers?.[agentName] || '—'}</td>
                          <td class="rt-chain">{Array.isArray(info?.chain) ? info.chain.join(' > ') : '—'}</td>
                          <td class="rt-src">{info?.source || '—'}{routingData?.routing?.tier_violations?.[agentName] ? ` · ! ${routingData.routing.tier_violations[agentName]}` : ''}</td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              {:else}
                <p class="routing-note">Model yönlendirme verisi alınamadı.</p>
              {/if}
            </div>
          {/if}

          {#if settingsStatusMsg}<div class="modal-alert ok">{settingsStatusMsg}</div>{/if}
          {#if settingsErrorMsg}<div class="modal-alert err" role="alert">{settingsErrorMsg}</div>{/if}
        </div>

        <div class="cockpit-modal-foot">
          <button class="modal-cancel-btn" on:click={() => (showSettingsModal = false)}>Kapat</button>
          {#if settingsTab !== 'routing'}
            <button class="modal-save-btn" on:click={saveMultiVaultSettings} disabled={settingsSaving}>
              <Icon name="lock" size={0.85} />
              {settingsSaving ? 'KAYDEDİLİYOR...' : 'KAYDET VE UYGULA'}
            </button>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  <!-- ============ ÖRNEK RAPORLAR (token'sız vitrin) ============ -->
  {#if showDemoModal}
    <div class="cockpit-modal-backdrop" role="dialog" aria-modal="true" aria-label="Örnek analiz raporları">
      <div class="cockpit-modal-card demo-modal-card">
        <div class="cockpit-modal-head">
          <h3><Icon name="file" size={0.95} /> ÖRNEK ANALİZ RAPORLARI</h3>
          <p class="cockpit-modal-sub">
            Ürünün çıktı biçimini gösteren 2 SENTEİTİK örnek. Gerçek kişi/kurum taranmadı — token gerekmez.
          </p>
          <button class="modal-close-btn" on:click={() => (showDemoModal = false)} aria-label="Kapat">
            <Icon name="close" size={0.9} />
          </button>
        </div>
        <div class="cockpit-modal-body demo-body">
          {#if demoError}
            <div class="modal-alert err" role="alert">{demoError}</div>
          {/if}
          {#if demoLoading && !demoReports.length}
            <div class="demo-loading">Yükleniyor...</div>
          {/if}
          <div class="demo-layout">
            <div class="demo-index" role="tablist" aria-label="Örnek raporlar">
              {#each demoReports as r (r.id)}
                <button
                  class="demo-index-item"
                  class:active={demoSelected?.id === r.id}
                  role="tab"
                  aria-selected={demoSelected?.id === r.id}
                  on:click={() => void loadDemoReport(r.id)}
                >
                  <span class="demo-index-title">{r.title}</span>
                  <span class="demo-index-sub">{r.scenario}</span>
                  <span class="demo-index-meta">{r.finding_count} bulgu · {r.evidence_count} kanıt</span>
                </button>
              {/each}
            </div>

            <div class="demo-report" role="tabpanel">
              {#if demoSelected}
                <div class="demo-report-head">
                  <h4>{demoSelected.title}</h4>
                  <div class="demo-subject">{demoSelected.subject_label}</div>
                  <div class="demo-tags">
                    <span class="demo-tag">SENTEİTİK</span>
                    <span class="demo-tag">{demoSelected.engine}</span>
                    <span class="demo-tag">{demoSelected.duration_seconds} sn</span>
                  </div>
                </div>

                <div class="demo-confidence">
                  <strong>{demoSelected.confidence?.label}</strong>
                  <span>{demoSelected.confidence?.caveat}</span>
                </div>

                <h5>Bulgular</h5>
                {#each demoSelected.findings as f (f.id)}
                  <div class="demo-finding">
                    <div class="demo-finding-head">
                      <span class="demo-sev sev-{(f.severity || '').toLowerCase()}">{f.severity}</span>
                      <strong>{f.title}</strong>
                    </div>
                    <blockquote>{f.quote}</blockquote>
                    <div class="demo-finding-meta">
                      Kanıt: {(f.evidence || []).join(', ')} · Güven: {f.confidence}
                    </div>
                  </div>
                {/each}

                <h5>Kanıt Zinciri</h5>
                <ul class="demo-evidence">
                  {#each demoSelected.evidence_chain as e, i (i)}
                    <li>
                      <strong>{e.agent}</strong> — {e.result?.claim}
                      <span class="demo-ev-status">[{e.result?.verification || 'BİLİNMİYOR'}]</span>
                    </li>
                  {/each}
                </ul>

                <h5>Sütun Durumları</h5>
                <div class="demo-pillars">
                  {#each demoSelected.pillars as pl (pl.id)}
                    <div class="demo-pillar st-{(pl.status || '').toLowerCase()}">
                      <span class="demo-pillar-label">{pl.label}</span>
                      <span class="demo-pillar-status">{pl.status}</span>
                      <span class="demo-pillar-summary">{pl.summary}</span>
                    </div>
                  {/each}
                </div>

                <h5>Sınırlar</h5>
                <ul class="demo-limits">
                  {#each demoSelected.limitations as lim, i (i)}
                    <li>{lim}</li>
                  {/each}
                </ul>

                <p class="demo-note">{demoSelected.notice}</p>
              {:else}
                <div class="demo-loading">Soldan bir örnek seçin.</div>
              {/if}
            </div>
          </div>
        </div>
      </div>
    </div>
  {/if}

  <!-- ============ KULLANIM KOŞULLARI ============ -->
  {#if showTermsModal}
    <div class="cockpit-modal-backdrop" role="dialog" aria-modal="true" aria-label="Sorumluluk reddi ve kullanım koşulları">
      <div class="cockpit-modal-card demo-modal-card">
        <div class="cockpit-modal-head">
          <h3><Icon name="warning" size={0.95} /> SORUMLULUK REDDİ VE KULLANIM KOŞULLARI</h3>
          <button class="modal-close-btn" on:click={() => (showTermsModal = false)} aria-label="Kapat">
            <Icon name="close" size={0.9} />
          </button>
        </div>
        <div class="cockpit-modal-body demo-body">
          {#if legalNotice}
            <div class="terms-headline">{legalNotice.headline}</div>
            <p class="terms-par">{legalNotice.disclaimer}</p>
            <h4>Açık Rıza Beyanı</h4>
            <p class="terms-par">{legalNotice.consent_declaration}</p>
            <h4>Kullanım Koşulları</h4>
            <ul class="terms-list">
              {#each legalNotice.usage_terms as t, i (i)}
                <li>{t}</li>
              {/each}
            </ul>
            <p class="terms-par terms-muted">{legalNotice.not_legal_advice}</p>
            <p class="terms-par terms-muted">Yargı çevresi: {legalNotice.jurisdiction} · Dil: {legalNotice.language}</p>
          {:else}
            <div class="demo-loading">Metin yüklenemedi — sunucuya erişilemiyor.</div>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</main>

<style>
  /* ==================== TEMEL RENK PALETİ ==================== */
  :root {
    --bg-deep: #030305;
    --bg-panel: #080a0f;
    --bg-elevated: #0d1117;
    --border-dim: #1a1f2e;
    --border-glow: #2a3f5a;
    --text-primary: #e8eef8;
    --text-dim: #6b7b94;
    --text-muted: #4a5a7a;
    --gold: #d4af37;
    --cyan: #06b6d4;
    --emerald: #10b981;
    --amber: #f59e0b;
    --magenta: #ec4899;
    --violet: #a855f7;
    --red: #ef4444;
    --scanline-opacity: 0.035;
  }

  /* ==================== GLOBAL RESET & SCANLINES ==================== */
  * { box-sizing: border-box; margin: 0; padding: 0; }
  /* Scanlines overlay */
  .command-deck::before {
    content: ''; position: fixed; inset: 0; z-index: 1000; pointer-events: none;
    background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,var(--scanline-opacity)) 2px, rgba(0,0,0,var(--scanline-opacity)) 4px);
    animation: scanline-drift 8s linear infinite;
  }
  @keyframes scanline-drift { 0% { transform: translateY(0); } 100% { transform: translateY(4px); } }

  /* Subtle vignette */
  .command-deck::after {
    content: ''; position: fixed; inset: 0; z-index: 999; pointer-events: none;
    background: radial-gradient(ellipse at center, transparent 40%, rgba(3,3,5,0.85) 100%);
  }

  .command-deck { display: grid; grid-template-rows: auto 1fr auto; height: 100vh; width: 100vw; position: relative; z-index: 1; }

  /* ==================== 1. MASTER HUD HEADER ==================== */
  .master-hud-header {
    display: grid; grid-template-columns: 1fr auto 1fr; gap: 1.5rem;
    align-items: center; padding: 1rem 2rem; position: relative; z-index: 10;
    background: linear-gradient(180deg, rgba(8,10,15,0.95) 0%, rgba(3,3,5,0.98) 100%);
    border-bottom: 1px solid var(--border-dim);
    box-shadow: 0 4px 40px -10px rgba(0,0,0,0.8), inset 0 1px 0 rgba(255,255,255,0.02);
  }

  .hud-brand { display: flex; align-items: center; gap: 1rem; }
  .pulse-beacon {
    width: 14px; height: 14px; border-radius: 50%;
    background: var(--emerald); box-shadow: 0 0 12px var(--emerald), 0 0 24px var(--emerald);
    opacity: 0.6; animation: beacon-pulse 2.5s ease-in-out infinite;
  }
  .pulse-beacon.active { background: var(--amber); box-shadow: 0 0 16px var(--amber), 0 0 32px var(--amber); opacity: 1; animation: beacon-active 0.8s ease-in-out infinite; }
  @keyframes beacon-pulse { 0%,100% { opacity: 0.4; transform: scale(1); } 50% { opacity: 0.9; transform: scale(1.15); } }
  @keyframes beacon-active { 0%,100% { opacity: 0.7; transform: scale(1); } 50% { opacity: 1; transform: scale(1.2); } }

  .intro-help, .summary-disclaimer { color: #b3c1d4; font-size: 0.75rem; line-height: 1.5; margin-top: 0.4rem; }
  /* [P0 · 2026-11-23] Yasal uyarı satırı — `/api/public/notice` ile aynı metin. */
  .intro-notice {
    margin-top: 0.25rem; font-size: 0.62rem; line-height: 1.45;
    color: var(--amber); max-width: 62ch;
  }
  .brand-title { font-size: clamp(1rem, 2.2vw, 1.4rem); font-weight: 800; letter-spacing: 0.12em; color: var(--text-primary); text-transform: uppercase; }
  .live-status-badge {
    display: inline-block; margin-top: 0.3rem; padding: 0.25rem 0.6rem;
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em;
    color: var(--emerald); background: rgba(16,185,129,0.12);
    border: 1px solid rgba(16,185,129,0.35); border-radius: 3px;
    font-family: 'JetBrains Mono', monospace;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 480px;
  }

  /* Target Cassette */
  .target-cassette-bar { display: flex; align-items: center; gap: 0.75rem; }
  .cassette-input-wrap { position: relative; display: flex; align-items: center; }
  .cassette-icon { font-size: 1.1rem; color: var(--cyan); margin-right: 0.5rem; text-shadow: 0 0 8px var(--cyan); }
  .cassette-text-input {
    width: 380px; max-width: 45vw; padding: 0.65rem 1rem;
    background: rgba(8,10,15,0.9); border: 1px solid var(--border-glow);
    border-radius: 4px; color: var(--text-primary); font-family: inherit; font-size: 0.85rem;
    outline: none; transition: all 0.2s;
  }
  .cassette-text-input:focus { border-color: var(--cyan); box-shadow: 0 0 0 2px rgba(6,182,212,0.2); }
  .cassette-text-input::placeholder { color: var(--text-muted); }

  .phone-launch-btn, .cassette-launch-btn {
    padding: 0.65rem 1.2rem; font-family: inherit; font-size: 0.78rem; font-weight: 800; letter-spacing: 0.06em;
    border: none; border-radius: 4px; cursor: pointer; transition: all 0.15s;
    text-transform: uppercase; white-space: nowrap;
  }
  .cassette-launch-btn { background: linear-gradient(135deg, var(--emerald), #059669); color: #02140a; box-shadow: 0 0 20px rgba(16,185,129,0.35); }
  .cassette-launch-btn:hover:not(:disabled) { box-shadow: 0 0 30px rgba(16,185,129,0.55); transform: translateY(-1px); }
  .cassette-launch-btn.is-running { background: linear-gradient(135deg, var(--amber), #d97706); color: #1a0d00; animation: btn-pulse 1.2s ease-in-out infinite; }
  @keyframes btn-pulse { 0%,100% { box-shadow: 0 0 15px rgba(245,158,11,0.4); } 50% { box-shadow: 0 0 30px rgba(245,158,11,0.7); } }
  .phone-launch-btn { background: linear-gradient(135deg, var(--magenta), #be185d); color: #1a020a; box-shadow: 0 0 20px rgba(236,72,153,0.35); }
  .phone-launch-btn:hover:not(:disabled) { box-shadow: 0 0 30px rgba(236,72,153,0.55); }
  .phone-launch-btn.is-running { background: linear-gradient(135deg, var(--amber), #d97706); animation: btn-pulse 1.2s ease-in-out infinite; }
  .cassette-launch-btn:disabled, .phone-launch-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }

  .adult-consent-badge {
    display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.45rem 0.65rem;
    font-size: 0.68rem; font-weight: 800; color: var(--gold);
    background: rgba(212,175,55,0.08); border: 1px solid rgba(212,175,55,0.3);
    border-radius: 4px; cursor: pointer; user-select: none; white-space: nowrap;
  }
  .adult-consent-badge input { cursor: pointer; accent-color: var(--gold); }

  /* [KVKK · 2026-11-23] Açık rıza beyanı — telefon sorgusu için zorunlu. */
  .consent-badge {
    display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.45rem 0.65rem;
    font-size: 0.66rem; font-weight: 800; color: var(--emerald);
    background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.35);
    border-radius: 4px; cursor: pointer; user-select: none; white-space: nowrap;
  }
  .consent-badge input { cursor: pointer; accent-color: var(--emerald); }

  .context-toggle-btn {
    padding: 0.5rem 0.8rem; font-family: inherit; font-size: 0.68rem; font-weight: 700;
    color: var(--cyan); background: rgba(6,182,212,0.1); border: 1px solid rgba(6,182,212,0.3);
    border-radius: 4px; cursor: pointer; transition: all 0.2s; white-space: nowrap;
  }
  .context-toggle-btn:hover, .context-toggle-btn.is-open {
    background: rgba(6,182,212,0.22); border-color: var(--cyan); box-shadow: 0 0 10px rgba(6,182,212,0.3);
  }
  .context-inputs-flyout {
    position: absolute; top: calc(100% + 8px); left: 0; right: 0; z-index: 50;
    display: flex; gap: 0.5rem; padding: 0.75rem; background: rgba(10,14,20,0.98);
    border: 1px solid var(--border-glow); border-radius: 6px; box-shadow: 0 8px 30px rgba(0,0,0,0.9);
  }
  .context-mini-input {
    flex: 1; padding: 0.5rem 0.8rem; background: rgba(5,7,12,0.9);
    border: 1px solid rgba(255,255,255,0.12); border-radius: 4px;
    color: var(--text-primary); font-family: inherit; font-size: 0.78rem; outline: none;
  }
  .context-mini-input:focus {
    border-color: var(--cyan); box-shadow: 0 0 0 1px var(--cyan);
  }

  /* Hud Meters */
  .hud-meters { display: flex; align-items: center; gap: 1rem; justify-content: flex-end; }
  .hud-meter-box { display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.8rem; background: rgba(8,10,15,0.8); border: 1px solid var(--border-dim); border-radius: 4px; }
  .hm-icon { font-size: 1rem; color: var(--cyan); }
  .hm-val { font-family: 'JetBrains Mono', monospace; font-size: 1rem; font-weight: 700; color: var(--text-primary); font-variant-numeric: tabular-nums; }

  .vault-lock-btn { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1rem; font-family: inherit; font-size: 0.7rem; font-weight: 800; letter-spacing: 0.08em; border-radius: 4px; cursor: pointer; transition: all 0.2s; text-transform: uppercase; }
  .vault-lock-btn { background: linear-gradient(135deg, var(--red), #b91c1c); color: #fff; border: 1px solid rgba(239,68,68,0.5); box-shadow: 0 0 18px rgba(239,68,68,0.25); }
  .vault-lock-btn.locked { background: linear-gradient(135deg, var(--emerald), #059669); color: #02140a; border-color: rgba(16,185,129,0.5); box-shadow: 0 0 18px rgba(16,185,129,0.25); }
  .vault-lock-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .vault-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; box-shadow: 0 0 8px currentColor; animation: vault-dot-pulse 1.5s ease-in-out infinite; }
  @keyframes vault-dot-pulse { 0%,100% { opacity: 0.7; } 50% { opacity: 1; } }
  .vault-error { display: block; margin-top: 0.4rem; font-size: 0.65rem; color: var(--red); font-family: inherit; }

  /* ==================== 2. MASTER GRID ==================== */
  .master-grid-container {
    display: grid; grid-template-columns: 28% 44% 28%; gap: 1rem; padding: 1rem; height: calc(100vh - 140px - 180px); min-height: 0; position: relative; z-index: 5;
  }

  .column-deck {
    display: flex; flex-direction: column; gap: 1rem;
    background: linear-gradient(180deg, rgba(8,10,15,0.7) 0%, rgba(3,3,5,0.9) 100%);
    border: 1px solid var(--border-dim); border-radius: 8px;
    padding: 1rem; overflow: hidden; position: relative;
  }
  .col-right { overflow-y: auto; }
  .column-deck::before {
    content: ''; position: absolute; inset: 0; border-radius: 8px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), inset 0 -1px 0 rgba(0,0,0,0.3);
    pointer-events: none;
  }

  .deck-title-ribbon { display: flex; align-items: center; gap: 0.6rem; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border-dim); flex-shrink: 0; }
  .ribbon-icon { font-size: 1.1rem; color: var(--cyan); text-shadow: 0 0 10px var(--cyan); }
  .deck-title-ribbon h2 { font-size: 0.7rem; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase; color: var(--text-dim); }

  /* ==================== SOVEREIGN STATIONS ==================== */
  .sovereign-station {
    background: linear-gradient(145deg, rgba(8,10,15,0.9), rgba(3,3,5,0.95));
    border: 1px solid var(--border-dim); border-radius: 6px; padding: 1rem;
    transition: all 0.25s; cursor: pointer; position: relative; overflow: hidden;
  }
  .sovereign-station::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--accent, var(--emerald)); opacity: 0; transition: opacity 0.2s;
  }
  .sovereign-station:hover { border-color: var(--border-glow); box-shadow: 0 4px 24px -8px rgba(0,0,0,0.6); }
  .sovereign-station.selected { border-color: var(--accent, var(--emerald)); box-shadow: 0 0 0 1px var(--accent, var(--emerald)), 0 8px 32px -12px var(--accent, var(--emerald)); }
  .sovereign-station.selected::before { opacity: 1; }
  .aspasia-station { --accent: #10b981; }
  .lilith-station { --accent: #ec4899; }

  .station-header { display: flex; align-items: flex-start; gap: 0.75rem; margin-bottom: 0.5rem; }
  .station-glyph { font-size: 1.5rem; line-height: 1; filter: drop-shadow(0 0 8px currentColor); }
  .station-name { font-size: 0.85rem; font-weight: 800; letter-spacing: 0.04em; color: var(--text-primary); }
  .station-role { display: block; margin-top: 0.15rem; font-size: 0.62rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.06em; }
  .station-badge { margin-left: auto; padding: 0.15rem 0.5rem; font-size: 0.55rem; font-weight: 800; letter-spacing: 0.08em; border-radius: 3px; text-transform: uppercase; }
  .badge-green { background: rgba(16,185,129,0.18); color: var(--emerald); border: 1px solid rgba(16,185,129,0.35); }
  .badge-pink { background: rgba(236,72,153,0.18); color: var(--magenta); border: 1px solid rgba(236,72,153,0.35); }

  .station-desc { font-size: 0.7rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.75rem; }
  .station-presets { display: flex; flex-direction: column; gap: 0.4rem; }
  .preset-btn { text-align: left; padding: 0.45rem 0.6rem; font-family: inherit; font-size: 0.6rem; font-weight: 700; letter-spacing: 0.04em; color: var(--text-dim); background: rgba(8,10,15,0.8); border: 1px solid var(--border-dim); border-radius: 3px; cursor: pointer; transition: all 0.15s; }
  .preset-btn:hover { color: var(--text-primary); border-color: var(--accent, var(--emerald)); background: rgba(16,185,129,0.08); }
  .preset-btn.btn-pink:hover { border-color: var(--magenta); background: rgba(236,72,153,0.08); }

  /* Lilith Neuro Meters */
  .lilith-neuro-meters { font-size: 0.65rem; color: var(--text-muted); padding: 0.5rem; background: rgba(236,72,153,0.05); border: 1px dashed rgba(236,72,153,0.2); border-radius: 4px; margin-bottom: 0.75rem; }

  /* Commander Override */
  .commander-override-box { background: rgba(8,10,15,0.8); border: 1px solid var(--border-dim); border-radius: 6px; padding: 1rem; }
  .box-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem; }
  .box-icon { font-size: 1.1rem; color: var(--amber); text-shadow: 0 0 8px var(--amber); }
  .box-header h3 { font-size: 0.7rem; font-weight: 800; letter-spacing: 0.08em; color: var(--amber); text-transform: uppercase; }
  .box-sub { font-size: 0.6rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.85rem; }
  .override-form { display: flex; flex-direction: column; gap: 0.6rem; }
  .form-dual-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
  .select-field, .input-field { padding: 0.5rem 0.7rem; font-family: inherit; font-size: 0.68rem; color: var(--text-primary); background: rgba(3,3,5,0.9); border: 1px solid var(--border-dim); border-radius: 3px; outline: none; }
  .select-field:focus, .input-field:focus { border-color: var(--amber); box-shadow: 0 0 0 2px rgba(245,158,11,0.15); }
  .override-submit-btn { padding: 0.6rem; font-family: inherit; font-size: 0.7rem; font-weight: 800; letter-spacing: 0.06em; color: #02140a; background: linear-gradient(135deg, var(--gold), #b8962e); border: none; border-radius: 3px; cursor: pointer; transition: all 0.15s; text-transform: uppercase; }
  .override-submit-btn:hover:not(:disabled) { box-shadow: 0 0 20px rgba(212,175,55,0.5); transform: translateY(-1px); }
  .override-submit-btn.injecting { background: linear-gradient(135deg, var(--amber), #d97706); animation: btn-pulse 1.2s ease-in-out infinite; }
  .override-submit-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .inject-history-ticker { margin-top: 0.85rem; padding-top: 0.75rem; border-top: 1px dashed var(--border-dim); }
  .ticker-title { display: block; font-size: 0.55rem; font-weight: 800; letter-spacing: 0.08em; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.4rem; }
  .ticker-row { display: flex; gap: 0.5rem; font-size: 0.58rem; padding: 0.25rem 0; font-family: inherit; }
  .t-type { color: var(--amber); font-weight: 700; min-width: 70px; }
  .t-val { color: var(--text-primary); flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .t-agent { color: var(--text-dim); font-size: 0.55rem; }

  /* ==================== FIELD AGENT MATRIX ==================== */
  .field-matrix-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; flex: 0 0 auto; }
  .agent-tile {
    display: flex; flex-direction: column; align-items: center; gap: 0.35rem;
    padding: 0.75rem 0.5rem; background: rgba(8,10,15,0.85); border: 1px solid var(--border-dim); border-radius: 6px;
    cursor: pointer; transition: all 0.2s; position: relative; overflow: hidden;
  }
  .agent-tile::before { content: ''; position: absolute; inset: 0; background: var(--agent-color); opacity: 0; transition: opacity 0.2s; }
  .agent-tile:hover { border-color: var(--agent-color); box-shadow: 0 4px 20px -6px var(--agent-color); transform: translateY(-2px); }
  .agent-tile.selected { border-color: var(--agent-color); box-shadow: 0 0 0 1px var(--agent-color), 0 6px 24px -8px var(--agent-color); }
  .agent-tile.selected::before { opacity: 0.06; }
  .agent-tile.active { border-color: var(--amber); box-shadow: 0 0 0 1px var(--amber), 0 0 20px -4px var(--amber); animation: tile-active-pulse 1.5s ease-in-out infinite; }
  @keyframes tile-active-pulse { 0%,100% { box-shadow: 0 0 0 1px var(--amber), 0 0 16px -4px var(--amber); } 50% { box-shadow: 0 0 0 2px var(--amber), 0 0 28px -2px var(--amber); } }
  .agent-tile.ready { border-color: var(--emerald); background: rgba(16,185,129,0.05); }
  .agent-tile.error { border-color: var(--red); background: rgba(239,68,68,0.05); }
  .agent-tile.wait { opacity: 0.65; }

  .tile-glyph { font-size: 1.3rem; line-height: 1; filter: drop-shadow(0 0 6px var(--agent-color)); }
  .tile-name { font-size: 0.58rem; font-weight: 700; letter-spacing: 0.03em; color: var(--text-primary); text-align: center; }
  .tile-short { font-size: 0.52rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.06em; }
  .tile-route { font-size: 0.48rem; color: var(--cyan); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
  .tile-tier { font-size: 0.45rem; color: var(--gold); text-transform: uppercase; }
  .tile-status { display: flex; align-items: center; gap: 0.3rem; font-size: 0.55rem; font-weight: 800; letter-spacing: 0.06em; }
  .status-pulse { width: 6px; height: 6px; border-radius: 50%; animation: status-pulse 1.2s ease-in-out infinite; }
  .agent-tile.active .status-pulse { background: var(--amber); box-shadow: 0 0 8px var(--amber); }
  .agent-tile.ready .status-pulse { background: var(--emerald); box-shadow: 0 0 8px var(--emerald); animation: none; }
  .agent-tile.error .status-pulse { background: var(--red); box-shadow: 0 0 8px var(--red); animation: none; }
  .agent-tile.wait .status-pulse { background: var(--text-dim); animation: status-pulse 2s ease-in-out infinite; }
  @keyframes status-pulse { 0%,100% { opacity: 0.4; transform: scale(1); } 50% { opacity: 1; transform: scale(1.3); } }
  .status-label { text-transform: uppercase; }

  .activity-bar { width: 100%; height: 3px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden; margin-top: 0.25rem; }
  .activity-fill { width: 100%; height: 100%; background: var(--agent-color); box-shadow: 0 0 8px var(--agent-color); animation: activity-sweep 1.2s ease-in-out infinite; transform-origin: left; }
  @keyframes activity-sweep { 0% { transform: scaleX(0); transform-origin: left; } 50% { transform: scaleX(1); transform-origin: left; } 100% { transform: scaleX(0); transform-origin: right; } }

  /* ==================== SOVEREIGN PULSE ==================== */
  .sovereign-pulse-section { flex: 0 0 auto; margin-top: 0.5rem; }
  .pulse-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.6rem; }
  .pulse-icon { font-size: 1.1rem; color: var(--magenta); text-shadow: 0 0 10px var(--magenta); }
  .pulse-header h3 { font-size: 0.62rem; font-weight: 800; letter-spacing: 0.1em; color: var(--text-dim); text-transform: uppercase; }
  .pulse-waveform { position: relative; height: 70px; background: linear-gradient(180deg, rgba(8,10,15,0.6), rgba(3,3,5,0.8)); border: 1px solid var(--border-dim); border-radius: 6px; overflow: hidden; }
  .pulse-waveform svg { width: 100%; height: 100%; display: block; }
  .wave-path { animation: wave-flow 3s linear infinite; }
  .wave-glow { animation: wave-flow 3s linear infinite reverse; }
  @keyframes wave-flow { 0% { stroke-dashoffset: 0; } 100% { stroke-dashoffset: 400; } }
  .pulse-metrics { display: flex; justify-content: space-between; margin-top: 0.5rem; font-size: 0.58rem; color: var(--text-dim); flex-wrap: wrap; gap: 0.5rem; }
  .pulse-metric { display: flex; align-items: center; gap: 0.35rem; }
  .freq-val, .sync-val { color: var(--emerald); font-weight: 700; font-family: 'JetBrains Mono', monospace; }

  /* ==================== CHAIN OF THOUGHT ==================== */
  .chain-of-thought-section { flex: 1; display: flex; flex-direction: column; min-height: 0; margin-top: 0.75rem; }
  .cot-header { display: flex; align-items: center; gap: 0.5rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border-dim); flex-shrink: 0; }
  .cot-icon { font-size: 1.1rem; color: var(--violet); text-shadow: 0 0 10px var(--violet); }
  .cot-header h3 { font-size: 0.62rem; font-weight: 800; letter-spacing: 0.1em; color: var(--text-dim); text-transform: uppercase; }
  .cot-content { flex: 1; overflow-y: auto; padding: 0.5rem 0; }
  .thought-chain { display: flex; flex-direction: column; gap: 0.4rem; }
  .thought-node { display: flex; gap: 0.6rem; padding: 0.6rem 0.75rem; background: linear-gradient(145deg, rgba(8,10,15,0.9), rgba(3,3,5,0.95)); border: 1px solid var(--border-dim); border-left: 3px solid var(--violet); border-radius: 4px; animation: thought-appear 0.4s ease-out backwards; }
  @keyframes thought-appear { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: translateX(0); } }
  .thought-index { min-width: 24px; font-size: 0.6rem; font-weight: 800; color: var(--violet); font-family: 'JetBrains Mono', monospace; }
  .thought-text { font-size: 0.7rem; color: var(--text-primary); line-height: 1.5; flex: 1; }
  .cot-placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; min-height: 120px; color: var(--text-muted); text-align: center; gap: 0.5rem; }
  .cot-agent { font-size: 0.75rem; font-weight: 800; color: var(--violet); letter-spacing: 0.06em; }
  .cot-action { font-size: 0.7rem; }
  .cot-typing { display: flex; gap: 3px; }
  .cot-typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--violet); animation: typing-bounce 1s ease-in-out infinite; }
  .cot-typing span:nth-child(2) { animation-delay: 0.15s; }
  .cot-typing span:nth-child(3) { animation-delay: 0.3s; }
  @keyframes typing-bounce { 0%,100% { transform: translateY(0); opacity: 0.5; } 50% { transform: translateY(-6px); opacity: 1; } }
  .cot-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; min-height: 120px; color: var(--text-muted); text-align: center; gap: 0.5rem; }
  .empty-glyph { font-size: 2.5rem; opacity: 0.3; }
  .cot-empty small { font-size: 0.65rem; }

  /* Selected Agent Detail */
  .selected-agent-detail { flex: 0 0 auto; margin-top: 0.75rem; padding: 0.85rem; background: rgba(8,10,15,0.8); border: 1px solid var(--border-dim); border-radius: 6px; animation: detail-slide 0.3s ease-out; }
  @keyframes detail-slide { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  .detail-header { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.5rem; }
  .detail-glyph { font-size: 1.3rem; filter: drop-shadow(0 0 8px currentColor); }
  .detail-header h3 { font-size: 0.7rem; font-weight: 800; letter-spacing: 0.06em; color: var(--text-primary); }
  .detail-output { font-size: 0.7rem; color: var(--text-primary); line-height: 1.6; white-space: pre-wrap; word-break: break-word; }

  /* ==================== PILLARS GRID ==================== */
  .pillars-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 0.4rem; flex: 0 0 auto; }
  .pillar-column { display: flex; flex-direction: column; background: rgba(8,10,15,0.85); border: 1px solid var(--border-dim); border-radius: 6px; padding: 0.6rem; transition: all 0.2s; position: relative; }
  .pillar-column::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--pillar-color); opacity: 0.6; border-radius: 6px 6px 0 0; }
  .pillar-column.has-data { border-color: var(--pillar-color); box-shadow: 0 0 0 1px var(--pillar-color), 0 4px 20px -8px var(--pillar-color); }
  .pillar-column.has-data::before { opacity: 1; }
  .pillar-header { display: flex; flex-direction: column; align-items: center; gap: 0.2rem; text-align: center; margin-bottom: 0.5rem; }
  .pillar-icon { font-size: 1.2rem; color: var(--pillar-color); filter: drop-shadow(0 0 6px var(--pillar-color)); }
  .pillar-label { font-size: 0.55rem; font-weight: 800; letter-spacing: 0.06em; color: var(--text-primary); text-transform: uppercase; }
  .pillar-badge { font-size: 0.5rem; font-weight: 800; letter-spacing: 0.04em; padding: 0.1rem 0.4rem; border-radius: 2px; text-transform: uppercase; }
  .pillar-column.has-data .pillar-badge { background: rgba(16,185,129,0.18); color: var(--emerald); border: 1px solid rgba(16,185,129,0.35); }
  .pillar-column:not(.has-data) .pillar-badge { background: rgba(245,158,11,0.15); color: var(--amber); border: 1px solid rgba(245,158,11,0.3); }
  .pillar-content { flex: 1; min-height: 80px; }
  .evidence-preview { display: flex; flex-direction: column; gap: 0.3rem; }
  .evidence-item { font-size: 0.58rem; color: var(--text-primary); padding: 0.25rem 0.4rem; background: rgba(255,255,255,0.03); border-radius: 3px; border-left: 2px solid var(--pillar-color); }
  .evidence-item strong { color: var(--pillar-color); }
  .evidence-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; min-height: 80px; color: var(--text-muted); font-size: 0.55rem; text-align: center; gap: 0.3rem; }
  .empty-pulse { width: 20px; height: 20px; border: 2px solid var(--pillar-color); border-radius: 50%; opacity: 0.4; animation: empty-pulse 2s ease-in-out infinite; }
  @keyframes empty-pulse { 0%,100% { transform: scale(1); opacity: 0.3; } 50% { transform: scale(1.3); opacity: 0.6; } }
  .pillar-footer { margin-top: 0.4rem; padding-top: 0.4rem; border-top: 1px dashed var(--border-dim); text-align: center; }
  .pillar-tr { font-size: 0.5rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; }

  /* ==================== ASPASIA CHAT ==================== */
  .aspasia-chat-section { flex: 1; display: flex; flex-direction: column; min-height: 0; margin-top: 0.75rem; }
  .chat-header { display: flex; align-items: center; gap: 0.5rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border-dim); flex-shrink: 0; }
  .chat-icon { font-size: 1.1rem; filter: drop-shadow(0 0 8px currentColor); }
  .chat-header h3 { font-size: 0.62rem; font-weight: 800; letter-spacing: 0.1em; color: var(--text-dim); text-transform: uppercase; flex: 1; }
  .chat-status { font-size: 0.55rem; font-weight: 800; letter-spacing: 0.06em; padding: 0.15rem 0.5rem; border-radius: 3px; text-transform: uppercase; }
  .chat-status { background: rgba(16,185,129,0.15); color: var(--emerald); border: 1px solid rgba(16,185,129,0.3); }
  .chat-status.speaking { background: rgba(236,72,153,0.18); color: var(--magenta); border-color: rgba(236,72,153,0.4); animation: status-speak 0.8s ease-in-out infinite; }
  @keyframes status-speak { 0%,100% { opacity: 0.8; } 50% { opacity: 1; box-shadow: 0 0 10px var(--magenta); } }

  .chat-messages { flex: 1; overflow-y: auto; padding: 0.5rem 0; display: flex; flex-direction: column; gap: 0.4rem; }
  .chat-message { display: flex; flex-direction: column; gap: 0.15rem; padding: 0.5rem 0.7rem; background: rgba(8,10,15,0.7); border-radius: 6px; border-left: 3px solid var(--border-dim); animation: msg-appear 0.25s ease-out; }
  @keyframes msg-appear { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  .chat-message.from-aspasia { border-left-color: var(--emerald); background: rgba(16,185,129,0.05); }
  .chat-message.from-user { border-left-color: var(--cyan); background: rgba(6,182,212,0.05); }
  .chat-message.from-agent { border-left-color: var(--violet); background: rgba(168,85,247,0.05); }
  .msg-time { font-size: 0.55rem; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }
  .msg-sender { font-size: 0.58rem; font-weight: 800; letter-spacing: 0.04em; color: var(--text-dim); text-transform: uppercase; }
  .chat-message.from-aspasia .msg-sender { color: var(--emerald); }
  .chat-message.from-user .msg-sender { color: var(--cyan); }
  .chat-message.from-agent .msg-sender { color: var(--violet); }
  .msg-text { font-size: 0.7rem; color: var(--text-primary); line-height: 1.5; white-space: pre-wrap; word-break: break-word; }

  .chat-input-area { display: flex; gap: 0.5rem; margin-top: 0.5rem; flex-shrink: 0; }
  .chat-input { flex: 1; padding: 0.55rem 0.8rem; font-family: inherit; font-size: 0.7rem; color: var(--text-primary); background: rgba(3,3,5,0.9); border: 1px solid var(--border-dim); border-radius: 4px; outline: none; }
  .chat-input:focus { border-color: var(--emerald); box-shadow: 0 0 0 2px rgba(16,185,129,0.15); }
  .chat-input::placeholder { color: var(--text-muted); }
  .chat-send-btn { width: 44px; padding: 0.5rem; font-family: inherit; font-size: 1rem; font-weight: 800; color: #02140a; background: linear-gradient(135deg, var(--emerald), #059669); border: none; border-radius: 4px; cursor: pointer; transition: all 0.15s; }
  .chat-send-btn:hover:not(:disabled) { box-shadow: 0 0 18px rgba(16,185,129,0.5); transform: translateY(-1px); }
  .chat-send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ==================== TELEMETRY ==================== */
  .telemetry-section { flex: 0 0 auto; margin-top: 0.75rem; }
  .telemetry-toggle { width: 100%; padding: 0.5rem; font-family: inherit; font-size: 0.6rem; font-weight: 800; letter-spacing: 0.08em; color: var(--gold); background: rgba(8,10,15,0.8); border: 1px solid rgba(212,175,55,0.35); border-radius: 4px; cursor: pointer; transition: all 0.2s; text-transform: uppercase; }
  .telemetry-toggle:hover { border-color: rgba(212,175,55,0.7); background: rgba(212,175,55,0.08); }
  .telemetry-panel { margin-top: 0.5rem; padding: 0.75rem; background: rgba(3,3,5,0.9); border: 1px solid var(--border-dim); border-radius: 6px; animation: panel-slide 0.25s ease-out; }
  @keyframes panel-slide { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: translateY(0); } }
  .telemetry-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin-bottom: 0.5rem; }
  .telemetry-row:last-child { margin-bottom: 0; }
  .telemetry-item { display: flex; flex-direction: column; align-items: center; gap: 0.15rem; padding: 0.5rem; background: rgba(8,10,15,0.7); border-radius: 4px; }
  .tl-label { font-size: 0.52rem; font-weight: 800; letter-spacing: 0.06em; color: var(--text-muted); text-transform: uppercase; }
  .tl-value { font-size: 0.65rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); }
  .tl-value.online { color: var(--emerald); }

  /* HUD Console Switches & Emergency Stop */
  .hud-switches { display: flex; align-items: center; gap: 0.4rem; }
  .hud-switch-btn { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.4rem 0.6rem; font-family: inherit; font-size: 0.65rem; font-weight: 800; letter-spacing: 0.08em; color: var(--text-muted); background: rgba(8,10,15,0.85); border: 1px solid var(--border-dim); border-radius: 4px; cursor: pointer; transition: all 0.15s; text-transform: uppercase; }
  .hud-switch-btn .switch-dot { width: 6px; height: 6px; border-radius: 50%; background: rgba(255,255,255,0.2); transition: all 0.15s; }
  .hud-switch-btn.engaged { color: var(--emerald); border-color: rgba(16,185,129,0.55); background: rgba(16,185,129,0.12); box-shadow: 0 0 12px rgba(16,185,129,0.2); }
  .hud-switch-btn.engaged .switch-dot { background: var(--emerald); box-shadow: 0 0 6px var(--emerald); }
  .hud-switch-btn.arm-switch.engaged { color: var(--amber); border-color: rgba(245,158,11,0.65); background: rgba(245,158,11,0.14); box-shadow: 0 0 12px rgba(245,158,11,0.25); }
  .hud-switch-btn.arm-switch.engaged .switch-dot { background: var(--amber); box-shadow: 0 0 6px var(--amber); }
  .hud-switch-btn.rec-switch.engaged { color: var(--cyan); border-color: rgba(6,182,212,0.55); background: rgba(6,182,212,0.12); box-shadow: 0 0 12px rgba(6,182,212,0.2); }
  .hud-switch-btn.rec-switch.engaged .switch-dot { background: var(--cyan); box-shadow: 0 0 6px var(--cyan); }
  .emergency-stop-btn { padding: 0.4rem 0.7rem; font-family: inherit; font-size: 0.65rem; font-weight: 900; letter-spacing: 0.08em; color: #fff; background: linear-gradient(135deg, #dc2626, #991b1b); border: 1px solid rgba(239,68,68,0.7); border-radius: 4px; cursor: pointer; transition: all 0.15s; text-transform: uppercase; white-space: nowrap; }
  .emergency-stop-btn:hover { box-shadow: 0 0 16px rgba(239,68,68,0.6); transform: translateY(-1px); }

  .cot-report-shortcut {
    margin-left: auto;
    padding: 0.2rem 0.55rem;
    font-family: inherit;
    font-size: 0.62rem;
    font-weight: 700;
    color: var(--emerald);
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 4px;
    cursor: pointer;
  }
  .pillar-epistemic-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem 0.6rem;
    font-size: 0.6rem;
    color: var(--text-dim);
    margin-bottom: 0.4rem;
    padding-bottom: 0.35rem;
    border-bottom: 1px dashed rgba(255,255,255,0.08);
  }
  .detail-chain-row { margin-top: 0.35rem; font-size: 0.66rem; color: var(--text-dim); font-family: 'JetBrains Mono', monospace; }
  .history-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
  .history-actions { display: flex; gap: 0.3rem; }
  .mini-action-btn {
    padding: 0.2rem 0.45rem;
    font-family: inherit;
    font-size: 0.6rem;
    font-weight: 700;
    color: var(--cyan);
    background: rgba(6, 182, 212, 0.12);
    border: 1px solid rgba(6, 182, 212, 0.35);
    border-radius: 3px;
    cursor: pointer;
  }
  .mini-action-btn.danger { color: #fca5a5; background: rgba(239, 68, 68, 0.12); border-color: rgba(239, 68, 68, 0.35); }
  .format-chips { display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.45rem; }
  .format-chip {
    display: inline-flex; align-items: center; gap: 0.3rem;
    padding: 0.25rem 0.5rem; font-size: 0.66rem;
    background: rgba(255,255,255,0.04); border: 1px solid var(--border-dim); border-radius: 4px; cursor: pointer;
  }
  .format-chip.disabled { opacity: 0.65; }
  .report-res-row { font-size: 0.66rem; margin-top: 0.25rem; }
  .report-history-list { display: flex; flex-direction: column; gap: 0.5rem; max-height: 240px; overflow: auto; }
  .report-history-card { padding: 0.55rem; background: rgba(0,0,0,0.28); border: 1px solid var(--border-dim); border-radius: 5px; }
  .rh-head { display: flex; justify-content: space-between; font-size: 0.7rem; color: var(--text-primary); }
  .rh-meta { font-size: 0.62rem; color: var(--text-dim); margin: 0.25rem 0; }
  .rh-links { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .report-dl-link {
    font-size: 0.62rem; color: var(--cyan); text-decoration: none;
    padding: 0.15rem 0.45rem; border: 1px solid rgba(6, 182, 212, 0.35); border-radius: 3px;
  }

  /* Phone OSINT Dossier Card */
  .phone-osint-dossier-card { padding: 0.85rem; background: linear-gradient(135deg, rgba(236,72,153,0.08), rgba(8,10,15,0.92)); border: 1px solid rgba(236,72,153,0.4); border-radius: 6px; display: flex; flex-direction: column; gap: 0.65rem; flex-shrink: 0; }
  .pod-header { display: flex; align-items: center; gap: 0.6rem; }
  .pod-icon { font-size: 1.2rem; }
  .pod-title-block { flex: 1; display: flex; flex-direction: column; }
  .pod-title { font-size: 0.58rem; font-weight: 800; letter-spacing: 0.1em; color: var(--magenta); }
  .pod-num { font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: var(--text-primary); }
  .pod-close-btn { background: transparent; border: 1px solid var(--border-dim); color: var(--text-muted); border-radius: 4px; padding: 0.2rem 0.45rem; cursor: pointer; font-size: 0.7rem; }
  .pod-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.45rem; }
  .pod-chip { padding: 0.4rem 0.55rem; background: rgba(3,3,5,0.8); border: 1px solid var(--border-dim); border-radius: 4px; display: flex; flex-direction: column; gap: 0.15rem; }
  .pod-lbl { font-size: 0.55rem; color: var(--text-muted); text-transform: uppercase; }
  .pod-val { font-size: 0.72rem; color: var(--text-primary); }
  .pod-val.highlight-gold { color: var(--gold); }
  .pod-val.highlight-green { color: var(--emerald); }
  .pod-sub-title { display: block; font-size: 0.6rem; font-weight: 700; color: var(--text-dim); margin-bottom: 0.3rem; }
  .pod-actions-row, .pod-handle-pills, .pod-social-pills { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .pod-action-pill, .pod-social-pill { padding: 0.3rem 0.6rem; font-size: 0.65rem; color: var(--cyan); background: rgba(6,182,212,0.1); border: 1px solid rgba(6,182,212,0.35); border-radius: 4px; text-decoration: none; }
  .pod-handle-btn { padding: 0.3rem 0.6rem; font-family: inherit; font-size: 0.65rem; color: var(--emerald); background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.35); border-radius: 4px; cursor: pointer; }
  .pod-inject-btn { padding: 0.45rem 0.75rem; font-family: inherit; font-size: 0.68rem; font-weight: 800; color: #02140a; background: linear-gradient(135deg, var(--gold), #ca8a04); border: none; border-radius: 4px; cursor: pointer; align-self: flex-start; }

  /* ==================== DATA POOL FOOTER ==================== */
  .data-pool-footer { grid-column: 1 / -1; height: 180px; background: linear-gradient(180deg, rgba(3,3,5,0.95) 0%, rgba(0,0,0,0.98) 100%); border-top: 1px solid var(--border-dim); display: flex; flex-direction: column; position: relative; z-index: 5; }
  .data-pool-footer::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: linear-gradient(90deg, transparent, var(--cyan), transparent); opacity: 0.6; }
  .pool-header { display: flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1.5rem; border-bottom: 1px solid var(--border-dim); flex-shrink: 0; }
  .pool-icon { font-size: 1rem; color: var(--cyan); }
  .pool-header h3 { font-size: 0.6rem; font-weight: 800; letter-spacing: 0.12em; color: var(--text-dim); text-transform: uppercase; }
  .pool-logs { flex: 1; overflow-y: auto; padding: 0.5rem 1.5rem; display: flex; flex-direction: column; gap: 0.2rem; font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; }
  .pool-log { display: flex; gap: 0.6rem; padding: 0.25rem 0.5rem; background: rgba(8,10,15,0.6); border-radius: 3px; border-left: 2px solid var(--border-dim); transition: all 0.15s; }
  .pool-log:hover { background: rgba(8,10,15,0.9); }
  .pl-time { color: var(--text-muted); min-width: 60px; }
  .pl-level { font-weight: 700; min-width: 50px; text-transform: uppercase; }
  .pl-msg { color: var(--text-primary); flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pool-empty { color: var(--text-muted); text-align: center; padding: 2rem; font-size: 0.65rem; }

  /* ==================== RESPONSIVE ==================== */
  @media (max-width: 1600px) {
    .master-grid-container { grid-template-columns: 30% 40% 30%; }
    .pillars-grid { grid-template-columns: repeat(7, 1fr); }
    .field-matrix-grid { grid-template-columns: repeat(3, 1fr); }
  }
  @media (max-width: 1300px) {
    .command-deck { height: auto; min-height: 100vh; width: 100%; }
    .column-deck { overflow: visible; }
    .master-hud-header { grid-template-columns: 1fr; gap: 1rem; text-align: center; }
    .target-cassette-bar { justify-content: center; flex-wrap: wrap; }
    .hud-meters { justify-content: center; }
    .master-grid-container { grid-template-columns: 1fr; grid-template-rows: auto auto auto; height: auto; min-height: calc(100vh - 140px - 180px); }
    .pillars-grid { grid-template-columns: repeat(4, 1fr); }
  }
  @media (max-width: 900px) {
    .pillars-grid { grid-template-columns: repeat(2, 1fr); }
    .field-matrix-grid { grid-template-columns: repeat(2, 1fr); }
    .form-dual-fields { grid-template-columns: 1fr; }
    .master-hud-header { padding: 1rem; }
    .hud-meters { flex-wrap: wrap; }
    .cassette-text-input { width: 100%; max-width: none; }
    .cassette-input-wrap { width: 100%; }
  }

  .settings-gear-btn {
    padding: 0.45rem 0.75rem;
    font-family: inherit;
    font-size: 0.65rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    color: var(--cyan);
    background: rgba(6, 182, 212, 0.12);
    border: 1px solid rgba(6, 182, 212, 0.45);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
  }
  .settings-gear-btn:hover { background: rgba(6, 182, 212, 0.25); color: #fff; }
  .cockpit-modal-backdrop {
    position: fixed; inset: 0; z-index: 9999;
    background: rgba(2, 4, 10, 0.85);
    backdrop-filter: blur(8px);
    display: flex; align-items: center; justify-content: center; padding: 1rem;
  }
  .cockpit-modal-card {
    width: min(880px, 96vw); max-height: 90vh;
    background: #0a0e17; border: 1px solid rgba(6, 182, 212, 0.45);
    border-radius: 10px; display: flex; flex-direction: column; overflow: hidden;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.8);
  }
  .cockpit-modal-head {
    display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;
    padding: 1rem 1.25rem; border-bottom: 1px solid var(--border-dim);
  }
  .cockpit-modal-head h3 { font-size: 0.9rem; color: var(--gold); margin: 0 0 0.25rem; }
  .cockpit-modal-sub { font-size: 0.7rem; color: var(--text-dim); margin: 0; }
  .modal-x-btn {
    background: transparent; border: 1px solid var(--border-dim); color: var(--text-dim);
    border-radius: 4px; padding: 0.25rem 0.55rem; cursor: pointer;
  }
  .cockpit-modal-tabs {
    display: flex; gap: 0.5rem; padding: 0.65rem 1.25rem;
    background: rgba(5, 7, 12, 0.8); border-bottom: 1px solid var(--border-dim);
    flex-wrap: wrap;
  }
  .cockpit-modal-tabs button {
    padding: 0.4rem 0.8rem; font-family: inherit; font-size: 0.7rem; font-weight: 700;
    color: var(--text-dim); background: rgba(255,255,255,0.03);
    border: 1px solid var(--border-dim); border-radius: 5px; cursor: pointer;
  }
  .cockpit-modal-tabs button.active {
    color: #02140a; background: var(--cyan); border-color: var(--cyan);
  }
  .cockpit-modal-body {
    padding: 1rem 1.25rem;
    /* [P0 · DOĞRULAMA 2026-11-23] flex:1 + min-height:0 EKSİKTİ. Kart
       `display:flex; flex-direction:column; overflow:hidden; max-height:90vh`
       olduğundan, gövdenin varsayılan `min-height:auto`'su onu içerik
       yüksekliğinde tutuyor, kartı 90vh'nin üstüne zorluyor ve taşan kısım
       `overflow:hidden` ile KESİLİYORDU — `overflow-y:auto` hiç devreye
       girmiyordu. Ölçülen sonuç: Ayarlar modalındaki OpenRouter/PINEAL_TOKEN
       kutusu (sıralamada 5. bölüm) alt barda görünmüyordu. */
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto; display: flex; flex-direction: column; gap: 1rem;
  }
  .modal-section-box {
    background: rgba(15, 20, 32, 0.7); border: 1px solid var(--border-dim);
    border-radius: 8px; padding: 0.85rem;
  }
  .modal-section-box h4 { font-size: 0.72rem; color: var(--cyan); margin: 0 0 0.65rem; text-transform: uppercase; }
  /* [P0 · DOĞRULAMA 2026-11-23] `lang="tr"` + `text-transform:uppercase`
     etkileşimi tarayıcıda Türkçe büyük harf kuralını uygulatır: "api" →
     "APİ" (noktalı İ). Ölçülen hata: modal başlığında "GET /APİ/TASKS"
     görünüyordu. Endpoint yolu bir kimliktir, büyük harfe çevrilmemelidir. */
  .endpoint-path {
    text-transform: none;
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-size: 0.68rem;
    font-weight: 500;
    letter-spacing: 0;
    color: var(--text-dim);
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-dim);
    border-radius: 4px;
    padding: 0.05rem 0.35rem;
    margin-left: 0.4rem;
    vertical-align: 0.05em;
    white-space: nowrap;
  }
  /* [P0 · DOĞRULAMA 2026-11-23] `.modal-close-btn` sınıfının HİÇ stili yoktu:
     düğme tarayıcı varsayılan butonuna düşüyor, koyu temada görünmüyordu.
     (✕ glifi de JetBrains Mono'da yoktu → Icon ile değiştirildi.) */
  .modal-close-btn {
    flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    width: 1.85rem; height: 1.85rem;
    background: transparent;
    border: 1px solid var(--border-dim);
    border-radius: 4px;
    color: var(--text-dim);
    cursor: pointer;
    transition: color 0.15s, border-color 0.15s, background 0.15s;
  }
  .modal-close-btn:hover,
  .modal-close-btn:focus-visible {
    color: var(--gold);
    border-color: var(--gold);
    background: rgba(212, 175, 55, 0.08);
  }
  .provider-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.65rem; }
  .provider-field { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.68rem; color: var(--text-dim); }
  .pf-top { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }
  .pf-badge { font-size: 0.58rem; padding: 0.1rem 0.35rem; border-radius: 3px; background: rgba(255,255,255,0.08); color: var(--text-muted); }
  .pf-badge.active { background: rgba(16, 185, 129, 0.2); color: var(--emerald); border: 1px solid rgba(16, 185, 129, 0.4); }
  .provider-field input {
    padding: 0.45rem 0.6rem; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
    color: var(--text-primary); background: #05080f; border: 1px solid var(--border-dim); border-radius: 4px;
  }
  .local-toggle-row { display: flex; align-items: center; gap: 0.5rem; font-size: 0.7rem; color: var(--text-primary); margin-bottom: 0.6rem; }
  .routing-table-wrap { max-height: 360px; overflow: auto; }
  .routing-table { width: 100%; border-collapse: collapse; font-size: 0.66rem; }
  .routing-table th, .routing-table td { text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border-dim); }
  .routing-table th { color: var(--gold); font-weight: 800; }
  .rt-agent { color: var(--cyan); font-weight: 700; font-family: 'JetBrains Mono', monospace; }
  .rt-tier { color: var(--gold); font-weight: 700; }
  .rt-chain { color: var(--text-primary); font-family: 'JetBrains Mono', monospace; }
  .rt-src { color: var(--text-muted); }
  .routing-warning { margin: .5rem 0; padding: .5rem; color: #fbbf24; background: rgba(120, 70, 0, .2); border: 1px solid rgba(251, 191, 36, .35); font-size: .68rem; }
  .routing-note { font-size: 0.7rem; color: var(--text-dim); }
  .modal-alert { padding: 0.55rem 0.75rem; border-radius: 5px; font-size: 0.72rem; }
  .modal-alert.ok { background: rgba(16, 185, 129, 0.15); border: 1px solid var(--emerald); color: var(--emerald); }
  .modal-alert.err { background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #fca5a5; }
  .cockpit-modal-foot {
    display: flex; justify-content: flex-end; gap: 0.65rem;
    padding: 0.85rem 1.25rem; border-top: 1px solid var(--border-dim);
  }
  .modal-cancel-btn {
    padding: 0.45rem 0.9rem; font-family: inherit; font-size: 0.7rem;
    background: transparent; color: var(--text-dim); border: 1px solid var(--border-dim); border-radius: 5px; cursor: pointer;
  }
  .modal-save-btn {
    padding: 0.45rem 1rem; font-family: inherit; font-size: 0.7rem; font-weight: 800;
    background: linear-gradient(135deg, var(--emerald), #059669); color: #02140a; border: none; border-radius: 5px; cursor: pointer;
  }
  .platform-warning {
    width: 100%;
    margin-top: 0.35rem;
    padding: 0.35rem 0.6rem;
    font-size: 0.66rem;
    color: #fbbf24;
    background: rgba(120, 70, 0, 0.22);
    border: 1px solid rgba(251, 191, 36, 0.4);
    border-radius: 4px;
  }
  /* [P0 · DOĞRULAMA 2026-11-23] Başlatma uyarısı: başlığın tam genişliğinde,
       hedef kutusunun hemen altında. role="alert" ile ekran okuyucuya da
       duyurulur. grid-column 1/-1: header 3 sütunlu grid (1fr auto 1fr). */
  .launch-notice {
    grid-column: 1 / -1;
    display: flex;
    align-items: flex-start;
    gap: 0.45rem;
    margin-top: -0.4rem;
    padding: 0.5rem 0.75rem;
    font-size: 0.7rem;
    line-height: 1.45;
    border-radius: 5px;
    border: 1px solid transparent;
  }
  .launch-notice.err {
    color: #fca5a5;
    background: rgba(239, 68, 68, 0.14);
    border-color: rgba(239, 68, 68, 0.55);
  }
  .launch-notice.warn {
    color: #fbbf24;
    background: rgba(120, 70, 0, 0.22);
    border-color: rgba(251, 191, 36, 0.4);
  }
  .launch-notice.ok {
    color: var(--emerald);
    background: rgba(16, 185, 129, 0.14);
    border-color: rgba(16, 185, 129, 0.5);
  }
  .launch-notice :global(.icon) { margin-top: 0.12rem; }

  /* ==================== ÖRNEK RAPORLAR / KULLANIM KOŞULLARI ==================== */
  .demo-modal-card { width: min(1080px, 96vw); }
  .demo-body { gap: 0.75rem; }
  .demo-loading { color: var(--text-dim); font-size: 0.78rem; padding: 1rem 0; }

  .demo-layout { display: grid; grid-template-columns: 260px 1fr; gap: 1rem; min-height: 0; }
  .demo-index { display: flex; flex-direction: column; gap: 0.5rem; }
  .demo-index-item {
    display: flex; flex-direction: column; gap: 0.25rem; text-align: left;
    padding: 0.65rem 0.75rem; cursor: pointer; font-family: inherit;
    background: rgba(15, 20, 32, 0.6); border: 1px solid var(--border-dim);
    border-radius: 6px; color: var(--text-dim); transition: all 0.15s;
  }
  .demo-index-item:hover { border-color: var(--cyan); color: var(--text-primary); }
  .demo-index-item.active { border-color: var(--emerald); background: rgba(16, 185, 129, 0.08); color: var(--text-primary); }
  .demo-index-title { font-size: 0.78rem; font-weight: 800; letter-spacing: 0.02em; }
  .demo-index-sub { font-size: 0.62rem; color: var(--text-muted); }
  .demo-index-meta { font-size: 0.6rem; color: var(--cyan); }

  .demo-report { min-width: 0; padding-right: 0.25rem; }
  .demo-report-head h4 { font-size: 0.95rem; color: var(--gold); margin: 0 0 0.2rem; }
  .demo-subject { font-size: 0.68rem; color: var(--cyan); margin-bottom: 0.4rem; }
  .demo-tags { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 0.6rem; }
  .demo-tag {
    font-size: 0.58rem; font-weight: 700; letter-spacing: 0.06em;
    padding: 0.1rem 0.4rem; border-radius: 3px;
    background: rgba(255, 255, 255, 0.06); border: 1px solid var(--border-dim);
    color: var(--text-dim); text-transform: uppercase;
  }
  .demo-confidence {
    display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: baseline;
    padding: 0.5rem 0.65rem; margin-bottom: 0.6rem; border-radius: 5px;
    background: rgba(6, 182, 212, 0.08); border: 1px solid rgba(6, 182, 212, 0.3);
    font-size: 0.68rem;
  }
  .demo-confidence strong { color: var(--cyan); }
  .demo-confidence span { color: var(--text-dim); }

  .demo-report h5 {
    font-size: 0.62rem; letter-spacing: 0.12em; text-transform: uppercase;
    color: var(--text-muted); margin: 0.75rem 0 0.35rem;
  }
  .demo-finding {
    padding: 0.5rem 0.65rem; margin-bottom: 0.4rem; border-radius: 5px;
    background: rgba(15, 20, 32, 0.65); border-left: 2px solid var(--border-dim);
  }
  .demo-finding-head { display: flex; align-items: center; gap: 0.5rem; font-size: 0.74rem; }
  .demo-finding blockquote {
    margin: 0.3rem 0; padding-left: 0.6rem; border-left: 1px solid var(--border-dim);
    font-size: 0.7rem; font-style: italic; color: var(--text-dim);
  }
  .demo-finding-meta { font-size: 0.6rem; color: var(--text-muted); }
  .demo-sev { font-size: 0.58rem; font-weight: 800; padding: 0.08rem 0.35rem; border-radius: 3px; }
  .demo-sev.sev-high { background: rgba(239, 68, 68, 0.18); color: #fca5a5; }
  .demo-sev.sev-medium { background: rgba(251, 191, 36, 0.16); color: #fbbf24; }
  .demo-sev.sev-low { background: rgba(16, 185, 129, 0.14); color: var(--emerald); }

  .demo-evidence, .demo-limits, .terms-list {
    margin: 0; padding-left: 1.1rem; font-size: 0.68rem; color: var(--text-dim);
    display: flex; flex-direction: column; gap: 0.25rem;
  }
  .demo-evidence strong { color: var(--cyan); }
  .demo-ev-status { color: var(--text-muted); margin-left: 0.25rem; }

  .demo-pillars { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.4rem; }
  .demo-pillar {
    display: flex; flex-direction: column; gap: 0.15rem;
    padding: 0.4rem 0.5rem; border-radius: 4px; font-size: 0.62rem;
    background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-dim);
  }
  .demo-pillar-label { font-weight: 800; color: var(--text-primary); letter-spacing: 0.06em; }
  .demo-pillar-status { font-size: 0.58rem; font-weight: 700; }
  .demo-pillar.st-observed .demo-pillar-status { color: var(--emerald); }
  .demo-pillar.st-partial .demo-pillar-status { color: var(--amber); }
  .demo-pillar.st-no_data .demo-pillar-status { color: var(--text-muted); }
  .demo-pillar-summary { color: var(--text-muted); line-height: 1.35; }

  .demo-note {
    margin-top: 0.6rem; padding: 0.5rem 0.65rem; border-radius: 5px;
    font-size: 0.66rem; color: #fbbf24;
    background: rgba(120, 70, 0, 0.18); border: 1px solid rgba(251, 191, 36, 0.3);
  }

  /* Kullanım koşulları */
  .terms-headline {
    font-size: 0.82rem; font-weight: 800; color: var(--gold);
    padding: 0.65rem 0.8rem; border-radius: 5px;
    background: rgba(212, 175, 55, 0.08); border: 1px solid rgba(212, 175, 55, 0.3);
  }
  .terms-par { font-size: 0.75rem; line-height: 1.6; color: var(--text-dim); margin: 0; }
  .terms-muted { color: var(--text-muted); font-size: 0.68rem; }
  .terms-list li { line-height: 1.5; }
  .ca-disabled-badge { color: #fbbf24; font-weight: 700; font-size: 0.62rem; }
  .deck-title-stack { flex-direction: column; align-items: flex-start; gap: 0.2rem; }
  .ribbon-row { display: flex; align-items: center; gap: 0.4rem; }
  .pillars-sub { font-size: 0.62rem; color: var(--text-dim); line-height: 1.3; }
  .catalog-details { margin: 0.35rem 0 0.55rem; font-size: 0.66rem; color: var(--text-dim); }
  .catalog-details summary { cursor: pointer; padding: 0.25rem 0.4rem; border: 1px dashed var(--border-dim); border-radius: 4px; }
  .channel-status-box { padding: 0.65rem; background: rgba(8,10,15,0.85); border: 1px solid var(--border-dim); border-radius: 6px; margin-bottom: 0.5rem; }
  .channel-list { display: flex; flex-direction: column; gap: 0.3rem; margin-top: 0.35rem; }
  .channel-row { display: flex; align-items: center; gap: 0.5rem; font-size: 0.65rem; padding: 0.25rem 0.45rem; border-radius: 4px; background: rgba(255,255,255,0.03); }
  .channel-row.ch-ok { border-left: 3px solid var(--emerald); }
  .channel-row.ch-fail { border-left: 3px solid #ef4444; color: #fca5a5; }
  .ch-name { font-family: 'JetBrains Mono', monospace; font-weight: 700; }
  .ch-badge { font-size: 0.58rem; padding: 0.08rem 0.35rem; border-radius: 3px; background: rgba(255,255,255,0.08); }
  .ch-reason { color: var(--text-dim); font-size: 0.6rem; }
</style>