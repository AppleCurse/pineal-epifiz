<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { 
    apiFetch, clientId, isProcessing, logs, taskStatus, 
    agentStatuses, vaultLocked, activeViewMode, inspectedAgentId
  } from '../store';
  import { playClick, playHalt, playRunning } from '../lib/consoleAudio';
  import EvidenceStatusBanner from './EvidenceStatusBanner.svelte';

  // 12 Ajan Kanonik Tanımları
  const AGENT_LIST = [
    { id: 'osint_investigator', name: 'OSINT INVESTIGATOR', short: 'OSINT', glyph: '🔍', color: '#8b5cf6', desc: 'Açık kaynak & dijital ayak izi' },
    { id: 'pineal_7pillar', name: '7-PILLAR FORENSICS', short: '7-PILLAR', glyph: '🏛️', color: '#06b6d4', desc: 'Deterministik 7 sütun mühürü' },
    { id: 'mirror_truth', name: 'MIRROR TRUTH', short: 'MIRROR', glyph: '🪞', color: '#10b981', desc: 'Öz-frekans & kullanıcı yansıtma' },
    // [RÖNTGEN 2026-09-23] '3 jürili' sabit metni kalktı: üreten modelin
    // ailesiyle çakışan koltuk düştüğünde panel 2 koltukla karar verir.
    // Gerçek koltuk sayısı koşu özetinden (jurors) okunur.
    { id: 'autonomous_verifier', name: 'AUTONOMOUS VERIFIER', short: 'VERIFIER', glyph: '⚖️', color: '#a855f7', desc: 'Çapraz hakem paneli (koltuk sayısı koşuya göre)' },
    { id: 'human_behavior', name: 'HUMAN BEHAVIOR', short: 'HUMAN', glyph: '👤', color: '#f59e0b', desc: 'Dijital cold reading & aşil tendonu' },
    { id: 'passion_mapper', name: 'PASSION MAPPER', short: 'PASSION', glyph: '✨', color: '#eab308', desc: 'Tutkular, neşe & akış tetikleyicileri' },
    { id: 'friction_detector', name: 'FRICTION & BOUNDS', short: 'FRICTION', glyph: '🛡️', color: '#ef4444', desc: 'Hassasiyetler, stres & sınırlar' },
    { id: 'cognitive_profiler', name: 'COGNITIVE PROFILER', short: 'COGNITIVE', glyph: '🧠', color: '#06b6d4', desc: 'Dilbilimsel üslup, ton & ritim' },
    { id: 'resonance_calc', name: 'RESONANCE CALC', short: 'RESO CALC', glyph: '📐', color: '#3b82f6', desc: 'Numpy vektörel rezonans motoru' },
    { id: 'pattern_interrupt', name: 'PATTERN INTERRUPT', short: 'PATTERN', glyph: '💥', color: '#dc2626', desc: 'Beklenti kırma & diyalog ağacı' },
    { id: 'resonance_synthesizer', name: 'RESONANCE SYNTH', short: 'SYNTH', glyph: '🎼', color: '#ec4899', desc: 'Sahici temas köprüsü & ilk mesaj' },
    { id: 'depth_analyst', name: 'DEPTH ANALYST', short: 'DEPTH', glyph: '🕳️', color: '#eab308', desc: 'Gerçeklik endeksi & kişilik özü' }
  ];

  // Hedef giriş formu
  let targetUrl = '';
  let scraperType = 'cross'; // cross | instagram | x
  // [RÖNTGEN 2026-09-23] Kullanıcı (operatör) verisi SADECE operatörden gelir.
  // Eski kod her görevde sabit İngilizce kurgu gönderiyordu:
  //   rituals: 'Morning cold exposure, strategic deep work, journaling'
  //   playlist: 'Max Richter, Nils Frahm, Olafur Arnalds'
  //   envies:  'Enduring intellectual architects ...'
  // Backend sözleşmesi bunu açıkça yasaklıyor (backend/api.py [009]:
  // "Kullanıcı göndermediyse ASLA örnek/placeholder ritüel ÜRETME"). Bu kurgu
  // mirror_truth'un "kullanıcı frekansı" hükmünü uydurma veriye bağlıyordu.
  let userRituals = '';
  let userPlaylist = '';
  let userEnvies = '';
  let showOperatorData = false;
  let logFilter = 'ALL';
  let activeDetailTab = 'OUTPUT'; // OUTPUT | INPUT | VERDICT | RAW
  let terminalContainer: HTMLElement;
  let autoScroll = true;

  // Seçili ajan (varsayılan: ilk biten veya osint)
  $: selectedAgent = $inspectedAgentId || 'osint_investigator';
  $: activeRuns = $taskStatus?.runs || {};
  $: completedCount = $taskStatus?.completed_agents?.length || 0;
  // Planlanmayan görevde "12" basmak uydurma sayıdır; gerçek plan uzunluğu ya
  // da null (ekranda "—") gösterilir.
  $: plannedCount = $taskStatus?.planned_agents?.length ?? null;
  $: currentRunningAgent = $taskStatus?.current_agent || null;
  $: pipelineStatus = $taskStatus?.status || ($isProcessing ? 'RUNNING' : 'IDLE');
  $: detectedUrls = $taskStatus?.target_profile?.detected_urls || [];
  $: targetBio = $taskStatus?.target_profile?.bio || '';
  $: targetName = $taskStatus?.target_profile?.name || targetUrl || 'Hedef Belirlenmedi';
  $: realityIndex = $taskStatus?.depth_report?.reality_index ?? null;
  $: resonanceScore = $taskStatus?.resonance_score ?? $taskStatus?.reso?.compatibility_score ?? null;
  $: run = activeRuns[selectedAgent] || null;
  $: agentDef = AGENT_LIST.find(a => a.id === selectedAgent);

  function selectAgent(id: string) {
    playClick();
    inspectedAgentId.set(id);
  }

  function getAgentRun(id: string) {
    return activeRuns[id] || null;
  }

  function getAgentStatus(id: string) {
    const run = activeRuns[id];
    if (run) {
      if (run.status === 'completed') return 'DONE';
      // [RÖNTGEN 2026-09-23] GÖREV TAMAMLANDI ≠ KARAR ÜRETİLDİ: ajan koştu
      // ama çıktısı kendi sözleşmesine göre karar değil (data_confidence=False).
      // DONE diye boyanırsa "karar üretildi" okunur; ayrı etiket + ayrı renk.
      if (run.status === 'completed_no_decision') return 'NO-DECISION';
      if (run.status === 'running') return 'ACTIVE';
      if (run.status === 'halted') return 'HALTED';
      if (run.status === 'failed') return 'FAILED';
    }
    if (currentRunningAgent === id) return 'ACTIVE';
    if ($agentStatuses[id]?.status) {
      const s = $agentStatuses[id].status.toUpperCase();
      if (s === 'ACTIVE') return 'ACTIVE';
      if (s === 'READY') return 'DONE';
      if (s === 'WAIT') return 'WAIT';
    }
    return 'WAIT';
  }

  function getAgentConfidence(id: string): number | null {
    const run = activeRuns[id];
    if (run && typeof run.confidence === 'number') return run.confidence;
    return null;
  }

  function getAgentSummaryText(id: string): string {
    const run = activeRuns[id];
    if (!run) {
      if (currentRunningAgent === id) return 'Operasyon yürütülüyor...';
      return 'Sırada bekliyor';
    }
    if (run.status === 'halted') {
      return `DURDU: ${run.error_message || 'Düşük kanıt'}`;
    }
    if (run.status === 'completed_no_decision') {
      // Koşu tamam ama KARAR yok: güven uydurulmaz, ölçülen değer gösterilir.
      const st = run.output_summary?.state || 'durum kaydı yok';
      const comp = run.output_summary?.compatibility_score;
      const compText = typeof comp === 'number' ? `%${(comp * 100).toFixed(0)}` : 'ölçülmedi';
      return `KARAR DEĞİL: ${st} · ölçülen benzerlik ${compText} (güven uydurulmadı)`;
    }
    if (run.status === 'completed') {
      if (id === 'osint_investigator') {
        const count = detectedUrls.length;
        return `${count} sosyal profil ve açık veri bağlandı`;
      }
      if (id === 'mirror_truth') {
        // 'Analitik' uydurma varsayılandı: alan yoksa ölçüm de yok.
        return `Kullanıcı Frekansı: ${run.output_summary?.user_core_frequency || 'veri yok'}`;
      }
      if (id === 'autonomous_verifier') {
        // "3 jürili" sabit metindi: üreten aileyle çakışan koltuk düştüğünde
        // panel 2 koltukla karar verir. Gerçek sayı ve gerçek hüküm basılır.
        const summary = run.output_summary || {};
        const vCount = summary.verifications?.length ?? null;
        const jurorCount = summary.jurors?.length ?? 0;
        const verdict = summary.status || 'HÜKÜM YOK';
        if (vCount === null) return 'İddia kaydı yok — teyit yapılmadı';
        return `${vCount} iddia · ${jurorCount} bağımsız jüri · hüküm: ${verdict}`;
      }
      if (id === 'human_behavior') {
        // `?? 15` uydurma skordu: ölçüm yoksa "ölçülmedi" yazılır.
        const achilles = run.output_summary?.achilles_score;
        const achillesText = typeof achilles === 'number' ? achilles.toFixed(0) : 'ölçülmedi';
        return `Aşil Skoru: ${achillesText} · ${run.output_summary?.micro_signals?.length ?? 0} mikro sinyal`;
      }
      if (id === 'passion_mapper') {
        const p = (run.output_summary?.core_passions || []).slice(0, 2).join(', ');
        // Boş çıktı "haritalandı" diye başarı olarak gösterilemez.
        return p || 'Tutku kanıtı yok (alan boş döndü)';
      }
      if (id === 'friction_detector') {
        const b = (run.output_summary?.boundary_signals || []).slice(0, 1).join(', ');
        return b || 'Sınır kanıtı yok (alan boş döndü)';
      }
      if (id === 'cognitive_profiler') {
        // 'Sade'/'Normal' uydurma varsayılanlardı.
        return `Ton: ${run.output_summary?.communication_tone || 'veri yok'} · Karmaşıklık: ${run.output_summary?.complexity_level || 'veri yok'}`;
      }
      if (id === 'resonance_calc') {
        // `?? 1.0` ölçülmeyen rezonansı "%100 benzerlik" diye basıyordu.
        const comp = run.output_summary?.compatibility_score;
        const compText = typeof comp === 'number' ? `%${(comp * 100).toFixed(0)}` : 'ölçülmedi';
        return `Vektörel Benzerlik: ${compText} · ${run.output_summary?.state || 'durum kaydı yok'}`;
      }
      if (id === 'pattern_interrupt') {
        return `Kanca üretildi: "${(run.output_summary?.message || '').slice(0, 35)}..."`;
      }
      if (id === 'resonance_synthesizer') {
        return `Temas Başlığı: ${run.output_summary?.authentic_opening_topic || 'veri yok'}`;
      }
      if (id === 'depth_analyst') {
        // `?? 0.88` uydurma gerçeklik endeksiydi (%88 sahici görünümü).
        const idx = realityIndex;
        if (typeof idx !== 'number') return 'Gerçeklik endeksi ölçülmedi (derinlik raporu yok)';
        return `Gerçeklik Endeksi: %${(idx * 100).toFixed(0)} · ${run.output_summary?.essence_one_liner || 'öz alanı boş'}`;
      }
      return 'Tamamlandı (özet alanı yok)';
    }
    return 'Beklemede';
  }

  // Görevi Başlat
  async function launchTask() {
    const q = targetUrl.trim();
    if (!q || $isProcessing) return;
    playRunning();
    isProcessing.set(true);

    try {
      await apiFetch('/api/initiate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId,
          url: q,
          scraper_type: scraperType,
          // Boş = operatör veri girmedi: backend dürüst "user_data_missing"
          // yoluyla çalışır, kurgu profil üretilmez.
          rituals: userRituals.trim(),
          playlist: userPlaylist.trim(),
          envies: userEnvies.trim()
        })
      });
    } catch (e: any) {
      console.error('Mission launch failed:', e);
      isProcessing.set(false);
    }
  }

  // Görevi Durdur
  async function haltTask() {
    playHalt();
    const taskId = $taskStatus?.task_id;
    if (taskId) {
      try {
        await apiFetch(`/api/tasks/${taskId}/halt`, { method: 'POST' });
      } catch (_e) {}
    }
    isProcessing.set(false);
  }

  function switchToCockpit() {
    playClick();
    activeViewMode.set('cockpit');
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('pineal_view_mode', 'cockpit');
    }
  }

  $: filteredLogs = ($logs || []).filter(l => {
    if (logFilter === 'ALL') return true;
    if (logFilter === 'OSINT') return l.msg.includes('OSINT') || l.msg.includes('AÇIK KAYNAK') || l.msg.includes('HEDEF');
    if (logFilter === 'LLM') return l.msg.includes('LLM') || l.msg.includes('GATEWAY') || l.msg.includes('MODEL');
    if (logFilter === 'DECISION') return l.msg.includes('ROUTER') || l.msg.includes('UNCERTAINTY') || l.msg.includes('CONFIDENCE');
    if (logFilter === 'ERRORS') return l.level === 'ERROR' || l.level === 'WARNING' || l.msg.includes('HATA');
    return true;
  });

  $: if (autoScroll && terminalContainer) {
    terminalContainer.scrollTop = terminalContainer.scrollHeight;
  }
</script>

<div class="warroom-container">
  <!-- ÜST TAKTİK KONTROL ŞERİDİ -->
  <header class="warroom-header">
    <div class="header-left">
      <div class="title-group">
        <span class="war-tag">TACTICAL WAR ROOM</span>
        <h1 class="main-title">PINEAL // OPERASYON MASASI</h1>
      </div>
      <div class="mission-status-badge {pipelineStatus.toLowerCase()}">
        <span class="status-pulse"></span>
        <span class="status-text">{pipelineStatus}</span>
      </div>
      {#if $taskStatus?.task_id}
        <span class="task-hash">ID: {$taskStatus.task_id.slice(-10)}</span>
      {/if}
    </div>

    <!-- HEDEF VE ARAMA KONTROLÜ -->
    <div class="header-center">
      <div class="input-cluster">
        <select bind:value={scraperType} class="type-select" disabled={$isProcessing}>
          <option value="cross">AÇIK OSINT (Tavily/Exa/SerpAPI)</option>
          <option value="instagram">INSTAGRAM DİREKT</option>
          <option value="x">X / TWITTER DİREKT</option>
        </select>
        <input 
          type="text" 
          bind:value={targetUrl} 
          placeholder="Hedef ad, @kullanıcı veya profil linki..."
          class="target-input"
          on:keydown={(e) => e.key === 'Enter' && launchTask()}
          disabled={$isProcessing}
        />
        <button
          class="btn-operator-data"
          class:filled={!!(userRituals.trim() || userPlaylist.trim() || userEnvies.trim())}
          on:click={() => { showOperatorData = !showOperatorData; playClick(); }}
          disabled={$isProcessing}
          title="Kullanıcı (operatör) kanıtı girilmedikçe mirror_truth uydurma veriyle çalışmaz"
        >
          <span class="btn-glyph">🧾</span> OPERATÖR VERİSİ{showOperatorData ? ' ▲' : ' ▼'}
        </button>
        {#if $isProcessing}
          <button class="btn-halt" on:click={haltTask}>
            <span class="btn-glyph">⏹</span> DURDUR
          </button>
        {:else}
          <button class="btn-engage" on:click={launchTask} disabled={!targetUrl.trim()}>
            <span class="btn-glyph">⚡</span> HAREKATA BAŞLA
          </button>
        {/if}
      </div>
      {#if showOperatorData}
        <div class="operator-data-row">
          <input type="text" bind:value={userRituals} class="operator-input" disabled={$isProcessing}
                 placeholder="Kişisel ritüeller (virgülle ayır) — boş bırakılırsa uydurulmaz" />
          <input type="text" bind:value={userPlaylist} class="operator-input" disabled={$isProcessing}
                 placeholder="Çalma listesi / müzik — boş bırakılırsa uydurulmaz" />
          <input type="text" bind:value={userEnvies} class="operator-input" disabled={$isProcessing}
                 placeholder="Derin arzular / hedefler — boş bırakılırsa uydurulmaz" />
          <span class="operator-note">
            Boş alan = kanıt yok. Backend kurgu kullanıcı profili ÜRETMEZ
            (mirror_truth "user_data_missing" döner).
          </span>
        </div>
      {/if}
    </div>

    <!-- MOD GEÇİŞİ VE METRİKLER -->
    <div class="header-right">
      <div class="quick-metric">
        <span class="m-label">TAMAMLANAN</span>
        <span class="m-val">{completedCount}/{plannedCount === null ? '—' : plannedCount}</span>
      </div>
      {#if realityIndex !== null}
        <div class="quick-metric">
          <span class="m-label">REALITY</span>
          <span class="m-val highlight">{(realityIndex * 100).toFixed(0)}%</span>
        </div>
      {/if}
      <button class="btn-switch-view" on:click={switchToCockpit} title="Sinematik Atlas Göz Kokpitine Geç">
        <span class="eye-glyph">👁️</span> ATLAS GÖZ KOKPİTİ
      </button>
    </div>
  </header>

  <EvidenceStatusBanner evidenceStatus={$taskStatus?.evidence_status || null} />

  <!-- ANA OPERASYON GÖVDESİ (3 SÜTUN) -->
  <main class="warroom-body">
    <!-- SOL: 12 AJAN TAKTİK MATRİSİ -->
    <section class="panel-column agent-column">
      <div class="column-header">
        <div class="col-title">
          <span class="col-icon">⚡</span> 12 AJAN OPERASYON MATRİSİ
        </div>
        <span class="col-badge">{completedCount} AKTİF</span>
      </div>

      <div class="agent-grid">
        {#each AGENT_LIST as agent (agent.id)}
          {@const status = getAgentStatus(agent.id)}
          {@const conf = getAgentConfidence(agent.id)}
          {@const isSel = selectedAgent === agent.id}
          <div 
            class="agent-card {status.toLowerCase()}" 
            class:selected={isSel}
            on:click={() => selectAgent(agent.id)}
            role="button"
            tabindex="0"
            on:keydown={(e) => e.key === 'Enter' && selectAgent(agent.id)}
          >
            <div class="card-top">
              <div class="agent-identity">
                <span class="agent-glyph">{agent.glyph}</span>
                <div class="name-desc">
                  <span class="agent-name">{agent.name}</span>
                  <span class="agent-sub">{agent.desc}</span>
                </div>
              </div>
              <div class="status-pill {status.toLowerCase()}">
                {status}
              </div>
            </div>

            <!-- ANLIK EYLEM İZİ -->
            <div class="card-breadcrumb">
              {getAgentSummaryText(agent.id)}
            </div>

            <!-- GÜVEN ÇUBUĞU -->
            <div class="card-footer">
              <div class="conf-bar-bg">
                <div 
                  class="conf-bar-fill" 
                  style="width: {conf !== null ? (conf * 100) : 0}%; background: {conf !== null && conf >= 0.7 ? '#10b981' : conf !== null && conf >= 0.4 ? '#f59e0b' : '#ef4444'};"
                ></div>
              </div>
              <span class="conf-val">
                {conf !== null ? `GÜVEN: ${(conf * 100).toFixed(0)}%` : 'ÖLÇÜM YOK'}
              </span>
            </div>
          </div>
        {/each}
      </div>
    </section>

    <!-- ORTA: HEDEF VE DELİL RADARI -->
    <section class="panel-column radar-column">
      <div class="column-header">
        <div class="col-title">
          <span class="col-icon">📡</span> İSTİHBARAT VE DELİL RADARI
        </div>
        <span class="col-badge">{detectedUrls.length} PROFİL BULUNDU</span>
      </div>

      <div class="radar-content">
        <!-- HEDEF KİMLİK KARTI -->
        <div class="target-card">
          <div class="target-header">
            <div class="target-avatar">🎯</div>
            <div class="target-names">
              <h2 class="target-h1">{targetName}</h2>
              <span class="target-sub">{targetBio.slice(0, 120) || 'Doğrulanmış açık kaynak profili taranıyor...'}</span>
            </div>
          </div>

          <!-- TESPİT EDİLEN SOSYAL HESAPLAR -->
          <div class="social-links-deck">
            <span class="deck-label">BAĞLANAN CANLI PROFİLLER:</span>
            {#if detectedUrls.length > 0}
              <div class="links-flow">
                {#each detectedUrls as url}
                  <a href={url} target="_blank" rel="noopener noreferrer" class="profile-chip">
                    {#if url.includes('instagram')}
                      <span class="brand-icon">📸</span>
                    {:else if url.includes('linkedin')}
                      <span class="brand-icon">💼</span>
                    {:else if url.includes('facebook')}
                      <span class="brand-icon">👥</span>
                    {:else}
                      <span class="brand-icon">🌐</span>
                    {/if}
                    <span class="link-label">{url.replace(/^https?:\/\/(www\.)?/, '').split('/')[0]}</span>
                    <span class="link-path">/{url.split('/').filter(Boolean).slice(-1)[0]}</span>
                  </a>
                {/each}
              </div>
            {:else}
              <div class="empty-radar">
                <span class="empty-icon">⏳</span>
                <span>Henüz açık kaynak profil bağlantısı tespit edilmedi.</span>
              </div>
            {/if}
          </div>
        </div>

        <!-- PSİKODİNAMİK SENTEZ VE ESSENCE -->
        {#if $taskStatus?.depth_report?.essence_one_liner}
          <div class="essence-card">
            <div class="essence-header">
              <span class="essence-glyph">🧬</span>
              <span class="essence-title">KİŞİLİK ÖZÜ (DEPTH ANALYST)</span>
            </div>
            <p class="essence-body">
              "{$taskStatus.depth_report.essence_one_liner}"
            </p>
          </div>
        {/if}

        <!-- SAHİCİ İLK TEMAS KÖPRÜSÜ -->
        {#if $taskStatus?.runs?.resonance_synthesizer?.output_summary?.suggested_opening_message}
          <div class="bridge-card">
            <div class="bridge-header">
              <span class="bridge-glyph">🤝</span>
              <span class="bridge-title">ÖNERİLEN İLK TEMAS KÖPRÜSÜ</span>
            </div>
            <p class="bridge-message">
              "{$taskStatus.runs.resonance_synthesizer.output_summary.suggested_opening_message}"
            </p>
          </div>
        {/if}

        <!-- OSINT KANIT LİSTESİ -->
        <div class="evidence-vault">
          <div class="vault-title">AÇIK KAYNAK SNIPPET'LARI ({($taskStatus?.target_profile?.posts || []).length}):</div>
          <div class="snippets-scroll">
            {#each ($taskStatus?.target_profile?.posts || []) as post}
              <div class="snippet-row">
                <span class="snip-icon">📄</span>
                <span class="snip-text">{post}</span>
              </div>
            {:else}
              <div class="snippet-empty">Snippet verisi bekleniyor...</div>
            {/each}
          </div>
        </div>
      </div>
    </section>

    <!-- SAĞ: AJAN RÖNTGENİ VE DERİN ADLİ MUAYENE -->
    <section class="panel-column inspector-column">
      <div class="column-header">
        <div class="col-title">
          <span class="col-icon">🔬</span> ADLİ AJAN RÖNTGENİ
        </div>
        <span class="col-badge highlight">{agentDef?.short || selectedAgent}</span>
      </div>

      <div class="inspector-body">
        <div class="inspected-header">
          <div class="inspected-id">
            <span class="inspected-glyph">{agentDef?.glyph}</span>
            <div>
              <h3 class="inspected-name">{agentDef?.name}</h3>
              <span class="inspected-desc">{agentDef?.desc}</span>
            </div>
          </div>
          <div class="inspected-status-pill {run?.status === 'completed_no_decision' ? 'no-decision' : (run?.status || 'idle')}">
            {run?.status === 'completed_no_decision' ? 'TAMAM · KARAR YOK' : (run?.status?.toUpperCase() || 'BEKLEMEDE')}
          </div>
        </div>

        <!-- SEKMELER: ÇIKTI / GİRDİ / GÜVEN / HAM JSON -->
        <div class="drawer-tabs">
          <button class="d-tab" class:active={activeDetailTab === 'OUTPUT'} on:click={() => activeDetailTab = 'OUTPUT'}>BULGULAR</button>
          <button class="d-tab" class:active={activeDetailTab === 'INPUT'} on:click={() => activeDetailTab = 'INPUT'}>GİRDİ</button>
          <button class="d-tab" class:active={activeDetailTab === 'VERDICT'} on:click={() => activeDetailTab = 'VERDICT'}>GÜVEN & KARAR</button>
          <button class="d-tab" class:active={activeDetailTab === 'RAW'} on:click={() => activeDetailTab = 'RAW'}>HAM VERİ</button>
        </div>

        <div class="drawer-content">
          {#if !run}
            <div class="no-run-data">
              <span class="no-run-glyph">⏳</span>
              <p>Bu ajan henüz tetiklenmedi veya operasyon rotasında sırada bekliyor.</p>
            </div>
          {:else if activeDetailTab === 'OUTPUT'}
            <div class="output-viewer">
              {#if run.error_message}
                <div class="error-banner">
                  <span class="err-title">DURMA / HATA BİLDİRİMİ:</span>
                  <p class="err-desc">{run.error_message}</p>
                </div>
              {/if}

              {#if run.output_summary}
                {#each Object.entries(run.output_summary) as [key, val]}
                  {#if !key.startsWith('_')}
                    <div class="kv-pair">
                      <span class="k-label">{key.toUpperCase()}:</span>
                      {#if Array.isArray(val)}
                        <ul class="kv-list">
                          {#each val as item}
                            <li>{typeof item === 'object' ? JSON.stringify(item) : item}</li>
                          {/each}
                        </ul>
                      {:else if typeof val === 'object' && val !== null}
                        <pre class="kv-pre">{JSON.stringify(val, null, 2)}</pre>
                      {:else}
                        <span class="v-val">{val}</span>
                      {/if}
                    </div>
                  {/if}
                {/each}
              {:else}
                <div class="empty-field">Ajan çıktı özeti henüz kaydedilmedi.</div>
              {/if}
            </div>
          {:else if activeDetailTab === 'INPUT'}
            <div class="input-viewer">
              <pre class="kv-pre">{JSON.stringify(run.input_summary || 'Genel hedef profili beslendi.', null, 2)}</pre>
            </div>
          {:else if activeDetailTab === 'VERDICT'}
            <div class="verdict-viewer">
              <div class="v-metric-row">
                <span class="vm-label">HESAPLANAN GÜVEN:</span>
                <span class="vm-val">{run.confidence !== null ? `${(run.confidence * 100).toFixed(1)}%` : 'Bilinmiyor'}</span>
              </div>
              <div class="v-metric-row">
                <span class="vm-label">ÇALIŞMA MODELİ:</span>
                <span class="vm-val">{run.model || '9Router / Canonical Chain'}</span>
              </div>
              <div class="v-metric-row">
                <span class="vm-label">KAYNAK:</span>
                <span class="vm-val">{run.run_source || run.via || 'Yerel'}</span>
              </div>
              {#if run.call_ids && run.call_ids.length > 0}
                <div class="v-metric-row">
                  <span class="vm-label">LLM ÇAĞRI KİMLİĞİ:</span>
                  <span class="vm-val monospace">{run.call_ids[0].slice(0, 12)}...</span>
                </div>
              {/if}
            </div>
          {:else if activeDetailTab === 'RAW'}
            <pre class="raw-pre">{JSON.stringify(run, null, 2)}</pre>
          {/if}
        </div>
      </div>
    </section>
  </main>

  <!-- ALT: CANLI FLIGHT RECORDER / KARA KUTU TERMİNALİ -->
  <footer class="warroom-footer">
    <div class="terminal-bar">
      <div class="term-left">
        <span class="term-glyph">📟</span>
        <span class="term-title">CANLI İSTİHBARAT & EYLEM GÜNLÜĞÜ (FLIGHT RECORDER)</span>
        <span class="term-count">{filteredLogs.length} GİRDİ</span>
      </div>

      <div class="term-filters">
        {#each ['ALL', 'OSINT', 'LLM', 'DECISION', 'ERRORS'] as f}
          <button class="filter-pill" class:active={logFilter === f} on:click={() => logFilter = f}>
            {f}
          </button>
        {/each}
        <label class="autoscroll-toggle">
          <input type="checkbox" bind:checked={autoScroll} /> OTOMATİK KAYDIR
        </label>
      </div>
    </div>

    <div class="terminal-stream" bind:this={terminalContainer}>
      {#each filteredLogs as log}
        <div class="log-line {log.level.toLowerCase()}">
          <span class="log-ts">[{log.ts}]</span>
          <span class="log-lvl {log.level.toLowerCase()}">[{log.level}]</span>
          <span class="log-msg">{log.msg}</span>
        </div>
      {:else}
        <div class="log-empty">Kayıt bekleniyor... Sistem hazır.</div>
      {/each}
    </div>
  </footer>
</div>

<style>
  .warroom-container {
    display: flex;
    flex-direction: column;
    width: 100vw;
    height: 100vh;
    background: #06090e;
    color: #e2e8f0;
    font-family: 'JetBrains Mono', 'Segoe UI', monospace;
    overflow: hidden;
  }

  /* HEADER */
  .warroom-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 18px;
    background: #0b111a;
    border-bottom: 1px solid rgba(212, 175, 55, 0.25);
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5);
    flex-shrink: 0;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .war-tag {
    font-size: 9px;
    letter-spacing: 2px;
    color: #d4af37;
    text-transform: uppercase;
    font-weight: 700;
  }

  .main-title {
    font-size: 15px;
    margin: 0;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 1px;
  }

  .mission-status-badge {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
  }

  .mission-status-badge.running {
    background: rgba(234, 179, 8, 0.15);
    border-color: #eab308;
    color: #eab308;
  }

  .mission-status-badge.completed {
    background: rgba(16, 185, 129, 0.15);
    border-color: #10b981;
    color: #10b981;
  }

  .status-pulse {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 6px currentColor;
  }

  .task-hash {
    font-size: 10px;
    color: #64748b;
  }

  /* CENTER CONTROLS */
  .header-center {
    flex: 1;
    max-width: 650px;
    margin: 0 20px;
  }

  .input-cluster {
    display: flex;
    gap: 6px;
    background: #04060a;
    padding: 3px;
    border-radius: 6px;
    border: 1px solid rgba(212, 175, 55, 0.3);
  }

  .type-select {
    background: #0d1522;
    color: #cbd5e1;
    border: none;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 11px;
    font-family: inherit;
  }

  .target-input {
    flex: 1;
    background: transparent;
    border: none;
    color: #ffffff;
    padding: 6px 10px;
    font-size: 12px;
    font-family: inherit;
    outline: none;
  }

  .btn-engage {
    background: #d4af37;
    color: #05070a;
    border: none;
    padding: 6px 14px;
    border-radius: 4px;
    font-weight: 800;
    font-size: 11px;
    cursor: pointer;
    letter-spacing: 0.5px;
    transition: all 0.2s;
  }

  .btn-engage:hover {
    background: #facc15;
    box-shadow: 0 0 10px rgba(250, 204, 21, 0.4);
  }

  .btn-halt {
    background: #ef4444;
    color: #ffffff;
    border: none;
    padding: 6px 14px;
    border-radius: 4px;
    font-weight: 800;
    font-size: 11px;
    cursor: pointer;
  }

  /* RIGHT STATS */
  .header-right {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .quick-metric {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
  }

  .m-label {
    font-size: 8px;
    color: #64748b;
    letter-spacing: 1px;
  }

  .m-val {
    font-size: 13px;
    font-weight: 700;
    color: #94a3b8;
  }

  .m-val.highlight {
    color: #10b981;
  }

  .btn-operator-data {
    background: rgba(212, 175, 55, 0.06);
    border: 1px solid rgba(212, 175, 55, 0.25);
    color: #d4af37;
    font-size: 9px;
    letter-spacing: 0.08em;
    padding: 6px 8px;
    border-radius: 3px;
    cursor: pointer;
    white-space: nowrap;
  }

  .btn-operator-data.filled {
    border-color: rgba(16, 185, 129, 0.6);
    color: #10b981;
  }

  .operator-data-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 6px;
    align-items: center;
  }

  .operator-input {
    flex: 1 1 180px;
    background: rgba(3, 6, 12, 0.9);
    border: 1px solid rgba(212, 175, 55, 0.18);
    color: #e2e8f0;
    font-size: 10px;
    padding: 6px 8px;
    border-radius: 3px;
  }

  .operator-note {
    flex: 1 1 100%;
    font-size: 8px;
    letter-spacing: 0.06em;
    color: #64748b;
  }

  .btn-switch-view {
    background: rgba(212, 175, 55, 0.1);
    color: #d4af37;
    border: 1px solid rgba(212, 175, 55, 0.4);
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.2s;
  }

  .btn-switch-view:hover {
    background: rgba(212, 175, 55, 0.25);
    border-color: #d4af37;
  }

  /* BODY */
  .warroom-body {
    display: grid;
    grid-template-columns: 360px 1fr 420px;
    flex: 1;
    overflow: hidden;
    gap: 1px;
    background: rgba(255, 255, 255, 0.04);
  }

  .panel-column {
    background: #080d14;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .column-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    background: #0b121c;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .col-title {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #cbd5e1;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .col-badge {
    font-size: 9px;
    padding: 2px 6px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 3px;
    color: #94a3b8;
  }

  .col-badge.highlight {
    background: rgba(212, 175, 55, 0.2);
    color: #d4af37;
    border: 1px solid rgba(212, 175, 55, 0.3);
  }

  /* AGENT COLUMN */
  .agent-grid {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .agent-card {
    background: #05080e;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    padding: 8px 10px;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .agent-card:hover {
    border-color: rgba(212, 175, 55, 0.4);
    background: #090e18;
  }

  .agent-card.selected {
    border-color: #d4af37;
    background: #0e1524;
    box-shadow: 0 0 12px rgba(212, 175, 55, 0.2);
  }

  .card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }

  .agent-identity {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .agent-glyph {
    font-size: 14px;
  }

  .name-desc {
    display: flex;
    flex-direction: column;
  }

  .agent-name {
    font-size: 11px;
    font-weight: 700;
    color: #f1f5f9;
  }

  .agent-sub {
    font-size: 9px;
    color: #64748b;
  }

  .status-pill {
    font-size: 8px;
    font-weight: 800;
    padding: 2px 6px;
    border-radius: 3px;
    letter-spacing: 0.5px;
  }

  .status-pill.done {
    background: rgba(16, 185, 129, 0.15);
    color: #10b981;
    border: 1px solid #10b981;
  }

  /* KOŞU TAMAM ama KARAR YOK: yeşil (DONE) ile karışmasın diye amber. */
  .status-pill.no-decision {
    background: rgba(245, 158, 11, 0.15);
    color: #f59e0b;
    border: 1px solid #f59e0b;
  }

  .status-pill.active {
    background: rgba(234, 179, 8, 0.2);
    color: #eab308;
    border: 1px solid #eab308;
  }

  .status-pill.halted {
    background: rgba(239, 68, 68, 0.2);
    color: #ef4444;
    border: 1px solid #ef4444;
  }

  .status-pill.wait {
    background: rgba(100, 116, 139, 0.2);
    color: #64748b;
    border: 1px solid #334155;
  }

  .card-breadcrumb {
    font-size: 10px;
    color: #94a3b8;
    margin: 6px 0;
    line-height: 1.3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .card-footer {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .conf-bar-bg {
    flex: 1;
    height: 3px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 2px;
    overflow: hidden;
  }

  .conf-bar-fill {
    height: 100%;
    transition: width 0.3s;
  }

  .conf-val {
    font-size: 8px;
    color: #64748b;
  }

  /* RADAR COLUMN */
  .radar-content {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .target-card {
    background: #0a0f18;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    padding: 14px;
  }

  .target-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
  }

  .target-avatar {
    font-size: 26px;
  }

  .target-h1 {
    font-size: 16px;
    font-weight: 800;
    margin: 0;
    color: #ffffff;
  }

  .target-sub {
    font-size: 11px;
    color: #94a3b8;
    line-height: 1.3;
  }

  .social-links-deck {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .deck-label {
    font-size: 9px;
    color: #64748b;
    letter-spacing: 1px;
    font-weight: 700;
  }

  .links-flow {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .profile-chip {
    display: flex;
    align-items: center;
    gap: 6px;
    background: #0d1522;
    border: 1px solid rgba(212, 175, 55, 0.3);
    padding: 4px 8px;
    border-radius: 4px;
    color: #cbd5e1;
    text-decoration: none;
    font-size: 11px;
    transition: all 0.2s;
  }

  .profile-chip:hover {
    background: rgba(212, 175, 55, 0.2);
    color: #ffffff;
    border-color: #d4af37;
  }

  .link-label {
    font-weight: 700;
  }

  .link-path {
    color: #94a3b8;
  }

  .essence-card, .bridge-card {
    background: #0a0f18;
    border: 1px solid rgba(212, 175, 55, 0.25);
    border-radius: 6px;
    padding: 12px;
  }

  .essence-header, .bridge-header {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    font-weight: 700;
    color: #d4af37;
    margin-bottom: 6px;
  }

  .essence-body, .bridge-message {
    font-size: 12px;
    color: #cbd5e1;
    margin: 0;
    line-height: 1.4;
  }

  .evidence-vault {
    background: #0a0f18;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    padding: 12px;
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  .vault-title {
    font-size: 10px;
    font-weight: 700;
    color: #64748b;
    margin-bottom: 8px;
  }

  .snippets-scroll {
    flex: 1;
    overflow-y: auto;
    max-height: 250px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .snippet-row {
    font-size: 11px;
    color: #94a3b8;
    background: #05080e;
    padding: 6px 8px;
    border-radius: 4px;
    display: flex;
    gap: 6px;
    line-height: 1.3;
  }

  /* INSPECTOR COLUMN */
  .inspector-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .inspected-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 12px;
    background: #0a0f18;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .inspected-id {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .inspected-glyph {
    font-size: 20px;
  }

  .inspected-name {
    font-size: 12px;
    margin: 0;
    color: #ffffff;
  }

  .inspected-desc {
    font-size: 9px;
    color: #64748b;
  }

  .drawer-tabs {
    display: flex;
    background: #070a10;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .d-tab {
    flex: 1;
    background: transparent;
    border: none;
    color: #64748b;
    padding: 8px 4px;
    font-size: 10px;
    font-weight: 700;
    cursor: pointer;
    font-family: inherit;
    border-bottom: 2px solid transparent;
  }

  .d-tab.active {
    color: #d4af37;
    border-bottom-color: #d4af37;
    background: rgba(212, 175, 55, 0.05);
  }

  .drawer-content {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
  }

  .kv-pair {
    margin-bottom: 10px;
  }

  .k-label {
    font-size: 9px;
    font-weight: 700;
    color: #64748b;
    display: block;
    margin-bottom: 3px;
  }

  .v-val {
    font-size: 11px;
    color: #e2e8f0;
  }

  .kv-list {
    margin: 0;
    padding-left: 16px;
    font-size: 11px;
    color: #cbd5e1;
  }

  .kv-pre, .raw-pre {
    background: #04060a;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 4px;
    padding: 8px;
    font-size: 10px;
    color: #94a3b8;
    overflow-x: auto;
    white-space: pre-wrap;
  }

  .v-metric-row {
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    font-size: 11px;
  }

  .vm-label {
    color: #64748b;
  }

  .vm-val {
    color: #ffffff;
    font-weight: 700;
  }

  .error-banner {
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid #ef4444;
    border-radius: 4px;
    padding: 8px;
    margin-bottom: 12px;
  }

  .err-title {
    font-size: 9px;
    font-weight: 800;
    color: #ef4444;
  }

  .err-desc {
    font-size: 11px;
    color: #fca5a5;
    margin: 4px 0 0 0;
  }

  /* FOOTER TERMINAL */
  .warroom-footer {
    height: 180px;
    background: #04070b;
    border-top: 1px solid rgba(212, 175, 55, 0.25);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }

  .terminal-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 12px;
    background: #070c14;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .term-left {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 10px;
    font-weight: 700;
    color: #cbd5e1;
  }

  .term-count {
    color: #64748b;
  }

  .term-filters {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .filter-pill {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #64748b;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 9px;
    font-weight: 700;
    cursor: pointer;
  }

  .filter-pill.active {
    background: rgba(212, 175, 55, 0.15);
    color: #d4af37;
    border-color: #d4af37;
  }

  .autoscroll-toggle {
    font-size: 9px;
    color: #64748b;
    display: flex;
    align-items: center;
    gap: 4px;
    cursor: pointer;
  }

  .terminal-stream {
    flex: 1;
    overflow-y: auto;
    padding: 6px 12px;
    font-size: 10px;
    line-height: 1.4;
  }

  .log-line {
    display: flex;
    gap: 8px;
    margin-bottom: 2px;
  }

  .log-ts {
    color: #475569;
    flex-shrink: 0;
  }

  .log-lvl.info { color: #0ea5e9; }
  .log-lvl.warning { color: #f59e0b; }
  .log-lvl.error { color: #ef4444; }

  .log-msg {
    color: #cbd5e1;
    word-break: break-all;
  }
</style>
