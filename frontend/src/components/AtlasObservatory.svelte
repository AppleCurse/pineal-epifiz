<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import {
    apiFetch, apiToken, currentApiToken, setApiToken, clientId,
    taskStatus, isProcessing, agentStatuses, vaultLocked,
    powerEngaged, armEngaged, recordEngaged, sigintEngaged
  } from '../store';
  import { playClick, playHalt } from '../lib/consoleAudio';

  export let onOpenDossier: () => void = () => {};

  // Göz animasyonu için canvas referansı
  let eyeCanvas: HTMLCanvasElement;
  let radarCanvas: HTMLCanvasElement;
  let plasmaCanvasLeft: HTMLCanvasElement;
  let plasmaCanvasRight: HTMLCanvasElement;
  let animFrameId: number;

  // Hedef giriş alanı
  let targetInput = '';
  let activeTabNav: 'agents' | 'aspasia' | 'reports' | 'settings' = 'agents';
  let activeAspasiaMode: 'konsept' | 'strateji' | 'rapor' | 'iletisim' = 'strateji';

  // Canlı ajan listesi (14 Ajan)
  const AGENT_MANIFEST = [
    { id: 'osint_investigator', code: '01', name: 'OSINT-01', desc: 'Açık Kaynak Tarama' },
    { id: 'depth_analyst', code: '02', name: 'WEB-INTEL-02', desc: 'Derin Ağ İstihbaratı' },
    { id: 'human_behavior', code: '03', name: 'SOCIAL-03', desc: 'Sosyal Matris & Davranış' },
    { id: 'friction_detector', code: '04', name: 'GEO-04', desc: 'Coğrafi & Ağ Sınırları' },
    { id: 'pattern_interrupt', code: '05', name: 'FIN-05', desc: 'Mali & Varlık Taraması' },
    { id: 'passion_mapper', code: '06', name: 'ARCHIVE-06', desc: 'Tarihsel Arşiv & Wayback' },
    { id: 'cognitive_profiler', code: '07', name: 'ANALYSIS-07', desc: 'Bilişsel Profilleme' },
    { id: 'mirror_truth', code: '08', name: 'LINK-08', desc: 'Bağlantı & Korelasyon' },
    { id: 'autonomous_verifier', code: '09', name: 'VERIFY-09', desc: 'Otonom Hakem Heyeti' },
    { id: 'resonance_calc', code: '10', name: 'CALC-10', desc: 'Matematiksel Rezonans' },
    { id: 'authenticity_auditor', code: '11', name: 'AUDIT-11', desc: 'Orijinallik Denetimi' },
    { id: 'resonance_synthesizer', code: '12', name: 'SYNTH-12', desc: 'Köprü & Sentez' },
    { id: 'aspasia_prime', code: '13', name: 'ASPASIA-13', desc: 'Bilinç & Baş Strateji' },
    { id: 'lilith_growth', code: '14', name: 'LILITH-14', desc: 'Gölge & Nörobiliş' }
  ];

  // Acil Stop Fonksiyonu
  async function emergencyHalt() {
    try {
      playHalt();
    } catch {}
    if (confirm('DİKKAT: ACİL STOP TETİKLENİYOR!\nTüm çalışan ajan görevleri ve ağ bağlantıları derhal durdurulacaktır. Onaylıyor musunuz?')) {
      try {
        await apiFetch('/api/tasks/emergency-stop', { method: 'POST' });
      } catch {}
      isProcessing.set(false);
      sigintEngaged.set(true);
      alert('ACİL STOP DEVREDE: Görevler mühürlendi ve durduruldu.');
    }
  }

  // Yeni Görev Başlat
  async function triggerDeepScan() {
    if (!targetInput.trim()) {
      alert('Lütfen taranacak hedef profil, alan adı veya kişi adını girin.');
      return;
    }
    try { playClick(); } catch {}
    isProcessing.set(true);
    try {
      const res = await apiFetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target: targetInput.trim(),
          mode: 'dossier',
          parameters: { observer: 'Salim Gümüş', cockpit: 'Atlas Observatory' }
        })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      taskStatus.set(data);
    } catch (e: any) {
      alert(`Görev başlatma uyarısı: ${e.message}`);
      isProcessing.set(false);
    }
  }

  // Canvas Animasyonları (Göz, Plazma, Radar)
  onMount(() => {
    let t = 0;

    // 1. Ocular Iris Canvas
    const ctxEye = eyeCanvas?.getContext('2d');
    const ctxRadar = radarCanvas?.getContext('2d');
    const ctxPlasmaL = plasmaCanvasLeft?.getContext('2d');
    const ctxPlasmaR = plasmaCanvasRight?.getContext('2d');

    function renderLoop() {
      t += 0.03;

      // Eye Animation
      if (ctxEye && eyeCanvas) {
        const w = eyeCanvas.width;
        const h = eyeCanvas.height;
        ctxEye.clearRect(0, 0, w, h);

        const cx = w / 2;
        const cy = h / 2;
        const r = w / 2 - 4;

        // Sclera gradient
        const grad = ctxEye.createRadialGradient(cx, cy, 10, cx, cy, r);
        grad.addColorStop(0, '#f2ece1');
        grad.addColorStop(0.7, '#d6c7b2');
        grad.addColorStop(1, '#8c765c');
        ctxEye.fillStyle = grad;
        ctxEye.beginPath();
        ctxEye.arc(cx, cy, r, 0, Math.PI * 2);
        ctxEye.fill();

        // Iris
        const irisR = r * 0.58;
        const irisGrad = ctxEye.createRadialGradient(cx, cy, 5, cx, cy, irisR);
        irisGrad.addColorStop(0, '#0a3d31');
        irisGrad.addColorStop(0.4, '#1b6352');
        irisGrad.addColorStop(0.8, '#c29b38');
        irisGrad.addColorStop(1, '#11221b');
        ctxEye.fillStyle = irisGrad;
        ctxEye.beginPath();
        ctxEye.arc(cx, cy, irisR, 0, Math.PI * 2);
        ctxEye.fill();

        // Pupil (pulses slightly)
        const pupilPulse = Math.sin(t * 1.5) * 2;
        const pupilR = r * 0.24 + pupilPulse;
        ctxEye.fillStyle = '#050706';
        ctxEye.beginPath();
        ctxEye.arc(cx, cy, pupilR, 0, Math.PI * 2);
        ctxEye.fill();

        // Light reflection
        ctxEye.fillStyle = 'rgba(255, 255, 255, 0.75)';
        ctxEye.beginPath();
        ctxEye.arc(cx - irisR * 0.35, cy - irisR * 0.35, r * 0.08, 0, Math.PI * 2);
        ctxEye.fill();
      }

      // Radar Sweep
      if (ctxRadar && radarCanvas) {
        const rw = radarCanvas.width;
        const rh = radarCanvas.height;
        ctxRadar.clearRect(0, 0, rw, rh);
        const rcx = rw / 2;
        const rcy = rh / 2;

        ctxRadar.strokeStyle = 'rgba(56, 239, 125, 0.2)';
        ctxRadar.lineWidth = 1;
        ctxRadar.beginPath();
        ctxRadar.arc(rcx, rcy, rw * 0.42, 0, Math.PI * 2);
        ctxRadar.arc(rcx, rcy, rw * 0.26, 0, Math.PI * 2);
        ctxRadar.arc(rcx, rcy, rw * 0.12, 0, Math.PI * 2);
        ctxRadar.stroke();

        // Sweep line
        const angle = t * 2;
        ctxRadar.strokeStyle = '#38ef7d';
        ctxRadar.lineWidth = 2;
        ctxRadar.beginPath();
        ctxRadar.moveTo(rcx, rcy);
        ctxRadar.lineTo(rcx + Math.cos(angle) * rw * 0.45, rcy + Math.sin(angle) * rw * 0.45);
        ctxRadar.stroke();
      }

      // Plasma Left (Amber)
      if (ctxPlasmaL && plasmaCanvasLeft) {
        const pw = plasmaCanvasLeft.width;
        const ph = plasmaCanvasLeft.height;
        ctxPlasmaL.clearRect(0, 0, pw, ph);
        ctxPlasmaL.strokeStyle = 'rgba(245, 158, 11, 0.85)';
        ctxPlasmaL.lineWidth = 1.5;
        ctxPlasmaL.beginPath();
        ctxPlasmaL.moveTo(pw / 2, 0);
        for (let y = 0; y < ph; y += 8) {
          const x = pw / 2 + Math.sin(y * 0.1 + t * 5) * 6;
          ctxPlasmaL.lineTo(x, y);
        }
        ctxPlasmaL.stroke();
      }

      // Plasma Right (Cyan)
      if (ctxPlasmaR && plasmaCanvasRight) {
        const pw = plasmaCanvasRight.width;
        const ph = plasmaCanvasRight.height;
        ctxPlasmaR.clearRect(0, 0, pw, ph);
        ctxPlasmaR.strokeStyle = 'rgba(6, 182, 212, 0.85)';
        ctxPlasmaR.lineWidth = 1.5;
        ctxPlasmaR.beginPath();
        ctxPlasmaR.moveTo(pw / 2, 0);
        for (let y = 0; y < ph; y += 8) {
          const x = pw / 2 + Math.cos(y * 0.1 - t * 5) * 6;
          ctxPlasmaR.lineTo(x, y);
        }
        ctxPlasmaR.stroke();
      }

      animFrameId = requestAnimationFrame(renderLoop);
    }

    renderLoop();

    return () => {
      if (animFrameId) cancelAnimationFrame(animFrameId);
    };
  });
</script>

<div class="atlas-observatory-frame">
  <!-- ÜST KONTROL & LOGO BAŞLIĞI -->
  <header class="observatory-header">
    <div class="header-left">
      <div class="beacon-wrap">
        <span class="beacon-dot"></span>
        <span class="beacon-label">PINEAL CORE</span>
      </div>
      <div class="sub-core-tags">OBSERVE · ANALYZE · CORRELATE</div>
    </div>

    <div class="header-center">
      <div class="brass-plaque">
        <span class="amber-jewel"></span>
        <h1>ATLAS EPİFİZ</h1>
        <div class="plaque-sub">✦ PINEAL OBSERVATORY ✦</div>
      </div>
    </div>

    <div class="header-right">
      <div class="motto-box">
        <p>"Göz görür. Pineal ayırır. Atlas ilişkilendirir."</p>
        <span class="signature">.SG</span>
      </div>
    </div>
  </header>

  <!-- HIZLI HEDEF VE OPERASYON ÇUBUĞU -->
  <div class="target-quick-bar">
    <div class="target-input-wrap">
      <span class="input-prefix">HEDEF GİRİŞİ:</span>
      <input
        type="text"
        placeholder="LinkedIn profili, X kullanıcı adı, şirket alan adı veya kişi adı..."
        bind:value={targetInput}
        on:keydown={(e) => e.key === 'Enter' && triggerDeepScan()}
      />
    </div>
    <button class="scan-trigger-btn" disabled={$isProcessing} on:click={triggerDeepScan}>
      {#if $isProcessing}
        <span class="spin-icon">⏳</span> İSTİHBARAT ÇALIŞIYOR...
      {:else}
        ⚡ GÖREVİ BAŞLAT (DERİN TARAMA)
      {/if}
    </button>
  </div>

  <!-- ANA KOKPİT ÇALIŞMA ALANI (3 SÜTUN) -->
  <div class="observatory-grid">
    <!-- ==================== SOL SÜTUN ==================== -->
    <aside class="col-left">
      <!-- 1. Operatör Kartı -->
      <section class="card operator-card">
        <div class="card-inner-bevel">
          <div class="token-status-pill">
            <span class="auth-icon">✦</span> PINEAL TOKEN: AUTHORIZED
          </div>
          <div class="op-profile">
            <div class="op-avatar">
              <span class="avatar-glyph">👤</span>
            </div>
            <div class="op-info">
              <h3>SALİM GÜMÜŞ</h3>
              <p class="op-role">Operator // PINEAL</p>
            </div>
          </div>
          <div class="op-nav-buttons">
            <button class:active={activeTabNav === 'agents'} on:click={() => activeTabNav = 'agents'}>AJANLAR</button>
            <button class:active={activeTabNav === 'aspasia'} on:click={() => activeTabNav = 'aspasia'}>ASPASIA</button>
            <button class:active={activeTabNav === 'reports'} on:click={() => activeTabNav = 'reports'}>RAPORLAR</button>
            <button class:active={activeTabNav === 'settings'} on:click={() => activeTabNav = 'settings'}>AYARLAR</button>
          </div>
        </div>
      </section>

      <!-- 2. Kaynak Alanı -->
      <section class="card source-area-card">
        <div class="card-title">KAYNAK ALANI</div>
        <div class="source-metrics">
          <div class="dial-placeholder">
            <div class="analog-dial-ring">
              <span class="dial-needle"></span>
            </div>
            <div class="dial-stats">
              <div><strong>127</strong> Aktif</div>
              <div><strong>14</strong> Arşiv</div>
              <div><strong>03</strong> Çelişkili</div>
              <div><strong>07</strong> Karartılmış</div>
            </div>
          </div>
          <ul class="source-status-list">
            <li><span class="led green"></span> Web Kanalları</li>
            <li><span class="led green"></span> Sosyal Medya Sensörleri</li>
            <li><span class="led amber"></span> Derin Arşiv (Wayback)</li>
            <li><span class="led green"></span> Veri Tabanı Kristali</li>
            <li><span class="led red"></span> Karanlık Ağ / Dark Web</li>
          </ul>
        </div>
      </section>

      <!-- 3. Zaman Çizelgesi -->
      <section class="card timeline-card">
        <div class="card-title">ZAMAN ÇİZELGESİ (1987 ➔ 2026)</div>
        <div class="timeline-row">
          <div class="pocket-watch-icon">⏱️</div>
          <div class="timeline-data">
            <div><strong>14</strong> Tespit Edilen Olay</div>
            <div><strong>03</strong> Kronolojik Anomali</div>
          </div>
        </div>
      </section>

      <!-- 4. Pineal Analitik Motor (Beyin Fanusu) -->
      <section class="card brain-chamber-card">
        <div class="card-title">PİNEAL ANALİTİK MOTOR</div>
        <div class="brain-display-wrap">
          <div class="brain-jar">
            <div class="golden-brain-glow">🧠</div>
          </div>
          <ul class="engine-features-list">
            <li><span class="led green"></span> OSINT Tarama</li>
            <li><span class="led green"></span> Yapay Zekâ Analizi</li>
            <li><span class="led green"></span> Bağlantı Analizi</li>
            <li><span class="led green"></span> Zaman Serisi</li>
            <li><span class="led green"></span> Davranış Profili</li>
            <li><span class="led green"></span> Risk Skorlama</li>
          </ul>
        </div>
      </section>
    </aside>

    <!-- ==================== ORTA SÜTUN (MABED & GÖZ) ==================== -->
    <main class="col-center">
      <!-- Dev Göz Makinesi (Ocular Sanctum) -->
      <div class="ocular-shrine">
        <!-- Sol Plazma Silindiri -->
        <div class="plasma-tube tube-left">
          <div class="tube-cap top"></div>
          <canvas bind:this={plasmaCanvasLeft} width="30" height="220"></canvas>
          <div class="tube-cap bottom"></div>
        </div>

        <!-- Merkez Ocular Çark -->
        <div class="ocular-assembly">
          <div class="ocular-brass-ring ring-outer">
            <span class="ring-label label-top">KAYNAK</span>
            <span class="ring-label label-top-right">KORELASYON</span>
            <span class="ring-label label-bottom-right">ANALİZ</span>
            <span class="ring-label label-bottom-left">DOĞRULAMA</span>
            <span class="ring-label label-top-left">BAĞLAM</span>
          </div>

          <div class="ocular-iris-holder">
            <canvas bind:this={eyeCanvas} width="160" height="160"></canvas>
          </div>
        </div>

        <!-- Sağ Plazma Silindiri -->
        <div class="plasma-tube tube-right">
          <div class="tube-cap top"></div>
          <canvas bind:this={plasmaCanvasRight} width="30" height="220"></canvas>
          <div class="tube-cap bottom"></div>
        </div>
      </div>

      <!-- Üç Alşimi Bölmesi (KÜL / SEDEF / İZ) -->
      <div class="trinity-pods">
        <div class="pod pod-ash">
          <div class="pod-header">KÜL</div>
          <div class="pod-sub">REMOVAL / REMEDIATION</div>
          <div class="pod-screen screen-ash">
            <span class="pod-pulse-glyph">⚡</span>
          </div>
        </div>

        <div class="pod pod-mother">
          <div class="pod-header">SEDEF</div>
          <div class="pod-sub">IDENTITY / TRANSFORMATION</div>
          <div class="pod-screen screen-pearl">
            <span class="pod-pulse-glyph">💎</span>
          </div>
        </div>

        <div class="pod pod-trace">
          <div class="pod-header">İZ</div>
          <div class="pod-sub">INTELLIGENCE / ANALYSIS</div>
          <div class="pod-screen screen-trace">
            <span class="pod-pulse-glyph">🌐</span>
          </div>
        </div>
      </div>

      <!-- Küresel İz & Dünya Haritası -->
      <section class="card global-trace-card">
        <div class="card-title">GLOBAL İZ & TELEMETRİ</div>
        <div class="global-trace-content">
          <div class="geo-tags">
            <span><strong>TR</strong> 184</span>
            <span><strong>EU</strong> 97</span>
            <span><strong>US</strong> 66</span>
            <span><strong>RU</strong> 32</span>
            <span><strong>CN</strong> 28</span>
            <span><strong>Other</strong> 41</span>
          </div>
          <div class="data-flow-meters">
            <div class="meter-col">TOPLAM VERİ: <strong>448.721</strong></div>
            <div class="meter-col">İŞLENEN: <strong>97.346</strong></div>
            <div class="meter-col">DOĞRULANAN: <strong>61.208</strong></div>
          </div>
        </div>
      </section>
    </main>

    <!-- ==================== SAĞ SÜTUN ==================== -->
    <aside class="col-right">
      <!-- 1. Aktif 14 Ajan Yuvası -->
      <section class="card agents-rack-card">
        <div class="card-title">AKTİF AJANLAR (14/14)</div>
        <div class="agents-scroll-box">
          {#each AGENT_MANIFEST as agent}
            <div class="agent-row">
              <span class="ag-code">{agent.code}</span>
              <span class="ag-name">{agent.name}</span>
              <span class="ag-desc">{agent.desc}</span>
              <span class="ag-status-dot led green"></span>
            </div>
          {/each}
        </div>
      </section>

      <!-- 2. Sosyal Medya Ayak İzi -->
      <section class="card social-reach-card">
        <div class="card-title">SOSYAL MEDYA İZİ</div>
        <div class="social-reach-grid">
          <div class="social-item"><span>𝕏 (Twitter)</span> <strong>1.2M</strong></div>
          <div class="social-item"><span>Instagram</span> <strong>842K</strong></div>
          <div class="social-item"><span>YouTube</span> <strong>421K</strong></div>
          <div class="social-item"><span>LinkedIn</span> <strong>318K</strong></div>
          <div class="social-item"><span>TikTok</span> <strong>275K</strong></div>
          <div class="social-item"><span>Facebook</span> <strong>193K</strong></div>
        </div>
      </section>

      <!-- 3. Aspasia Prime Strateji Zekâsı -->
      <section class="card aspasia-card">
        <div class="card-title">ASPASIA (STRATEJİ ZEKÂ)</div>
        <div class="aspasia-head">
          <div class="aspasia-portrait">👑</div>
          <div class="aspasia-speech">
            <em>"Duygular değil, veriler konuşsun."</em>
          </div>
        </div>
        <div class="aspasia-modes">
          <button class:active={activeAspasiaMode === 'konsept'} on:click={() => activeAspasiaMode = 'konsept'}>KONSEPT</button>
          <button class:active={activeAspasiaMode === 'strateji'} on:click={() => activeAspasiaMode = 'strateji'}>STRATEJİ</button>
          <button class:active={activeAspasiaMode === 'rapor'} on:click={() => activeAspasiaMode = 'rapor'}>RAPOR</button>
          <button class:active={activeAspasiaMode === 'iletisim'} on:click={() => activeAspasiaMode = 'iletisim'}>İLETİŞİM</button>
        </div>
      </section>

      <!-- 4. İz Alanı & Radar -->
      <section class="card trace-area-card">
        <div class="card-title">İZ ALANI & RADAR</div>
        <div class="radar-box">
          <canvas bind:this={radarCanvas} width="120" height="120"></canvas>
          <div class="radar-telemetry">
            <div><strong>842</strong> Sinyal</div>
            <div><strong>61</strong> Korelasyon</div>
            <div><strong>07</strong> Çözülmemiş</div>
            <div><strong>02</strong> Yüksek Risk</div>
          </div>
        </div>
      </section>

      <!-- 5. Risk Analizi -->
      <section class="card risk-card">
        <div class="card-title">RİSK ANALİZİ</div>
        <div class="risk-distribution">
          <div class="risk-col">Düşük <strong>%42</strong></div>
          <div class="risk-col">Orta <strong>%37</strong></div>
          <div class="risk-col highlight">Yüksek <strong>%21</strong></div>
        </div>
        <div class="risk-threat-tags">
          <span class="threat-tag"><span class="led red"></span> TEHDİT</span>
          <span class="threat-tag"><span class="led red"></span> SAHTECİLİK</span>
          <span class="threat-tag"><span class="led red"></span> MALWARE</span>
          <span class="threat-tag"><span class="led red"></span> DEZENFORMASYON</span>
        </div>
      </section>

      <!-- 6. Son Rapor & Detay -->
      <section class="card last-case-card">
        <div class="card-title">SON RAPOR</div>
        <div class="case-brief">
          <div class="case-title">CASE #AT-2025-0918 <span class="tag-done">TAMAMLANDI</span></div>
          <p>Konu: Dijital İz & İlk Temas Kancası</p>
          <p>Kaynak: 37 Doğrulanmış Kayıt</p>
          <button class="view-dossier-btn" on:click={onOpenDossier}>DETAY GÖR</button>
        </div>
      </section>
    </aside>
  </div>

  <!-- ==================== ALT ENDÜSTRİYEL KONTROL RAYI ==================== -->
  <footer class="observatory-bottom-rail">
    <!-- GETA Amblemi -->
    <div class="rail-block geta-block">
      <div class="sacred-triangle-mini">▲</div>
      <div class="geta-text">
        <strong>GETA</strong>
        <small>Güvenli Erişim Terminali</small>
      </div>
    </div>

    <!-- Analog Anahtarlar: PWR, ARM, REC, SIGINT -->
    <div class="rail-block toggle-switches-block">
      <!-- PWR -->
      <div class="hardware-switch">
        <button
          class="switch-btn"
          class:engaged={$powerEngaged}
          on:click={() => powerEngaged.update(v => !v)}
          title="Ana Uplink / Güç Şalteri"
        >
          <span class="switch-toggle"></span>
        </button>
        <span class="switch-lamp" class:lit={$powerEngaged}></span>
        <span class="switch-label">PWR</span>
      </div>

      <!-- ARM -->
      <div class="hardware-switch">
        <button
          class="switch-btn"
          class:engaged={$armEngaged}
          on:click={() => armEngaged.update(v => !v)}
          title="Operasyon Silahlandırma (ARM)"
        >
          <span class="switch-toggle"></span>
        </button>
        <span class="switch-lamp" class:lit={$armEngaged}></span>
        <span class="switch-label">ARM</span>
      </div>

      <!-- REC -->
      <div class="hardware-switch">
        <button
          class="switch-btn"
          class:engaged={$recordEngaged}
          on:click={() => recordEngaged.update(v => !v)}
          title="Adli Kayıt ve Loglama"
        >
          <span class="switch-toggle"></span>
        </button>
        <span class="switch-lamp" class:lit={$recordEngaged}></span>
        <span class="switch-label">REC</span>
      </div>

      <!-- SIGINT -->
      <div class="hardware-switch">
        <button
          class="switch-btn"
          class:engaged={$sigintEngaged}
          on:click={() => sigintEngaged.update(v => !v)}
          title="Sinyal İstihbaratı Filtresi"
        >
          <span class="switch-toggle"></span>
        </button>
        <span class="switch-lamp" class:lit={$sigintEngaged}></span>
        <span class="switch-label">SIGINT</span>
      </div>
    </div>

    <!-- Merkez Piramit Butonu -->
    <div class="rail-block sacred-core-block">
      <button class="sacred-core-btn" title="Pineal Epifiz Çekirdek Rezonansı">
        <span class="sacred-glyph">▲</span>
      </button>
    </div>

    <!-- ACİL STOP BUTONU (Sarı-Siyah Şeritli) -->
    <div class="rail-block emergency-stop-block">
      <button class="emergency-mushroom-btn" on:click={emergencyHalt}>
        <span class="mushroom-cap"></span>
        <span class="stop-label">ACİL STOP</span>
      </button>
    </div>

    <!-- PINEAL TOKEN / VAULT YUVASI -->
    <div class="rail-block vault-token-block">
      <div class="crystal-slot">
        <span class="crystal-icon">💎</span>
        <span class="token-code">PINEAL_TOKEN</span>
        <span class="lock-indicator" class:locked={$vaultLocked}>
          {$vaultLocked ? '🔒' : '🔓'}
        </span>
      </div>
    </div>
  </footer>
</div>

<style>
  /* =========================================================================
     ATLAS EPİFİZ // PINEAL OBSERVATORY — STEAMPUNK DARK GOLD STYLESHEET
     ========================================================================= */
  .atlas-observatory-frame {
    width: 100vw;
    height: 100vh;
    box-sizing: border-box;
    background: radial-gradient(circle at 50% 30%, #17110a 0%, #080604 100%);
    color: #e6dfd5;
    font-family: 'Georgia', -apple-system, BlinkMacSystemFont, 'Segoe UI', serif;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    user-select: none;
    border: 4px solid #3d2a13;
    box-shadow: inset 0 0 100px rgba(0, 0, 0, 0.95);
  }

  /* ---------------- Üst Başlık ---------------- */
  .observatory-header {
    height: 64px;
    background: linear-gradient(180deg, #1c150e 0%, #0d0a06 100%);
    border-bottom: 2px solid #5a3e19;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 24px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.8);
    position: relative;
    z-index: 10;
  }

  .header-left .beacon-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .beacon-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 10px #10b981;
    animation: blink 2s infinite;
  }
  .beacon-label {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 2px;
    color: #38ef7d;
  }
  .sub-core-tags {
    font-size: 9px;
    letter-spacing: 2px;
    color: #a89474;
    margin-top: 2px;
  }

  .brass-plaque {
    background: linear-gradient(180deg, #3a2712 0%, #1e1307 100%);
    border: 2px solid #d4af37;
    border-radius: 4px;
    padding: 4px 32px;
    text-align: center;
    box-shadow: 0 0 20px rgba(212, 175, 55, 0.25);
    position: relative;
  }
  .brass-plaque h1 {
    margin: 0;
    font-size: 18px;
    letter-spacing: 3px;
    color: #ffd700;
    text-shadow: 0 2px 4px rgba(0,0,0,0.8);
  }
  .plaque-sub {
    font-size: 9px;
    letter-spacing: 3px;
    color: #d4af37;
  }
  .amber-jewel {
    position: absolute;
    top: -5px;
    left: 50%;
    transform: translateX(-50%);
    width: 8px;
    height: 8px;
    background: #f59e0b;
    border-radius: 50%;
    box-shadow: 0 0 8px #f59e0b;
  }

  .motto-box {
    text-align: right;
  }
  .motto-box p {
    margin: 0;
    font-size: 11px;
    font-style: italic;
    color: #c9b493;
  }
  .signature {
    font-size: 10px;
    color: #d4af37;
    font-weight: bold;
  }

  /* ---------------- Hedef Giriş Çubuğu ---------------- */
  .target-quick-bar {
    padding: 8px 24px;
    background: #110c07;
    border-bottom: 1px solid #3d2a13;
    display: flex;
    gap: 12px;
    align-items: center;
  }
  .target-input-wrap {
    flex: 1;
    display: flex;
    align-items: center;
    background: #090704;
    border: 1px solid #5a3e19;
    border-radius: 4px;
    padding: 0 12px;
  }
  .input-prefix {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #d4af37;
    margin-right: 10px;
  }
  .target-input-wrap input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: #38ef7d;
    font-family: 'Courier New', monospace;
    font-size: 12px;
    padding: 8px 0;
  }
  .scan-trigger-btn {
    background: linear-gradient(180deg, #b8860b 0%, #664303 100%);
    border: 1px solid #ffd700;
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 8px 18px;
    border-radius: 4px;
    cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,0.6);
  }
  .scan-trigger-btn:hover {
    background: linear-gradient(180deg, #d4af37 0%, #855805 100%);
    box-shadow: 0 0 12px rgba(212, 175, 55, 0.4);
  }

  /* ---------------- Ana Izgara ---------------- */
  .observatory-grid {
    flex: 1;
    display: grid;
    grid-template-columns: 280px 1fr 340px;
    gap: 12px;
    padding: 12px 20px;
    overflow-y: auto;
  }

  .card {
    background: linear-gradient(180deg, #171109 0%, #0d0a06 100%);
    border: 1px solid #4a3418;
    border-radius: 4px;
    padding: 10px;
    box-shadow: inset 0 0 15px rgba(0, 0, 0, 0.8), 0 2px 6px rgba(0, 0, 0, 0.5);
    margin-bottom: 10px;
  }
  .card-title {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    color: #d4af37;
    border-bottom: 1px solid #2b1d0c;
    padding-bottom: 4px;
    margin-bottom: 8px;
  }

  /* Sol Sütun */
  .operator-card .card-inner-bevel {
    background: #110c07;
    padding: 8px;
    border: 1px solid #2b1d0c;
  }
  .token-status-pill {
    font-size: 9px;
    color: #38ef7d;
    background: rgba(56, 239, 125, 0.1);
    border: 1px solid rgba(56, 239, 125, 0.3);
    padding: 2px 6px;
    border-radius: 10px;
    display: inline-block;
    margin-bottom: 8px;
  }
  .op-profile {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-bottom: 10px;
  }
  .op-avatar {
    width: 44px;
    height: 44px;
    background: #2b1d0c;
    border: 2px solid #d4af37;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
  }
  .op-info h3 {
    margin: 0;
    font-size: 13px;
    color: #e6dfd5;
    letter-spacing: 1px;
  }
  .op-role {
    margin: 2px 0 0 0;
    font-size: 9px;
    color: #a89474;
  }
  .op-nav-buttons {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 4px;
  }
  .op-nav-buttons button {
    background: #1c140b;
    border: 1px solid #4a3418;
    color: #c4b196;
    font-size: 9px;
    padding: 4px 0;
    cursor: pointer;
    border-radius: 2px;
  }
  .op-nav-buttons button.active {
    background: #d4af37;
    color: #0d0a06;
    font-weight: bold;
  }

  .source-metrics .dial-placeholder {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-bottom: 8px;
  }
  .analog-dial-ring {
    width: 46px;
    height: 46px;
    border-radius: 50%;
    border: 2px solid #d4af37;
    background: #090704;
    position: relative;
  }
  .dial-needle {
    position: absolute;
    width: 2px;
    height: 18px;
    background: #ef4444;
    top: 5px;
    left: 21px;
    transform: rotate(45deg);
    transform-origin: bottom center;
  }
  .dial-stats {
    font-size: 10px;
    color: #a89474;
    line-height: 1.4;
  }
  .dial-stats strong { color: #ffd700; }
  .source-status-list {
    list-style: none;
    padding: 0;
    margin: 0;
    font-size: 10px;
  }
  .source-status-list li {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 3px;
  }

  .timeline-row {
    display: flex;
    gap: 12px;
    align-items: center;
  }
  .pocket-watch-icon { font-size: 24px; }
  .timeline-data { font-size: 10px; color: #c4b196; line-height: 1.5; }
  .timeline-data strong { color: #d4af37; }

  .brain-display-wrap {
    display: flex;
    gap: 12px;
    align-items: center;
  }
  .brain-jar {
    width: 60px;
    height: 80px;
    background: rgba(16, 185, 129, 0.05);
    border: 2px solid #5a3e19;
    border-radius: 30px 30px 4px 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: inset 0 0 15px rgba(245, 158, 11, 0.2);
  }
  .golden-brain-glow {
    font-size: 32px;
    filter: drop-shadow(0 0 8px #ffd700);
    animation: brain-pulse 3s infinite ease-in-out;
  }
  .engine-features-list {
    list-style: none;
    padding: 0;
    margin: 0;
    font-size: 10px;
    line-height: 1.4;
  }
  .engine-features-list li { display: flex; align-items: center; gap: 6px; }

  /* LED Stilleri */
  .led {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
  }
  .led.green { background: #10b981; box-shadow: 0 0 6px #10b981; }
  .led.amber { background: #f59e0b; box-shadow: 0 0 6px #f59e0b; }
  .led.red { background: #ef4444; box-shadow: 0 0 6px #ef4444; }

  /* ---------------- Orta Sütun (Ocular Sanctum) ---------------- */
  .col-center {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .ocular-shrine {
    background: radial-gradient(circle, #24170a 0%, #0d0905 100%);
    border: 2px solid #8c6508;
    border-radius: 6px;
    padding: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 20px;
    box-shadow: inset 0 0 40px rgba(0,0,0,0.9), 0 0 20px rgba(212, 175, 55, 0.15);
  }

  .plasma-tube {
    width: 32px;
    height: 220px;
    background: rgba(0, 0, 0, 0.7);
    border: 1px solid #5a3e19;
    border-radius: 16px;
    position: relative;
    overflow: hidden;
  }
  .tube-cap {
    position: absolute;
    width: 100%;
    height: 10px;
    background: #b8860b;
    border: 1px solid #d4af37;
  }
  .tube-cap.top { top: 0; border-radius: 16px 16px 0 0; }
  .tube-cap.bottom { bottom: 0; border-radius: 0 0 16px 16px; }

  .ocular-assembly {
    width: 220px;
    height: 220px;
    border: 3px solid #d4af37;
    border-radius: 50%;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #060402;
    box-shadow: 0 0 30px rgba(212, 175, 55, 0.25);
  }
  .ring-outer {
    position: absolute;
    width: 100%;
    height: 100%;
    border-radius: 50%;
    animation: rotate-dial 60s infinite linear;
  }
  .ring-label {
    position: absolute;
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #d4af37;
  }
  .label-top { top: 6px; left: 50%; transform: translateX(-50%); }
  .label-top-right { top: 40px; right: 12px; }
  .label-bottom-right { bottom: 40px; right: 12px; }
  .label-bottom-left { bottom: 40px; left: 12px; }
  .label-top-left { top: 40px; left: 12px; }

  .ocular-iris-holder {
    width: 160px;
    height: 160px;
    border-radius: 50%;
    overflow: hidden;
    border: 2px solid #5a3e19;
  }

  /* Üç Alşimi Bölmesi */
  .trinity-pods {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }
  .pod {
    background: #110d08;
    border: 1px solid #4a3418;
    border-radius: 4px;
    padding: 8px;
    text-align: center;
  }
  .pod-header { font-size: 11px; font-weight: 700; color: #ffd700; letter-spacing: 1.5px; }
  .pod-sub { font-size: 8px; color: #8c7355; letter-spacing: 1px; margin-bottom: 6px; }
  .pod-screen {
    height: 60px;
    background: #060402;
    border: 1px solid #2b1d0c;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .pod-pulse-glyph { font-size: 20px; }
  .screen-ash .pod-pulse-glyph { filter: drop-shadow(0 0 6px #ef4444); }
  .screen-pearl .pod-pulse-glyph { filter: drop-shadow(0 0 6px #a855f7); }
  .screen-trace .pod-pulse-glyph { filter: drop-shadow(0 0 6px #06b6d4); }

  .global-trace-card { flex: 1; }
  .geo-tags {
    display: flex;
    justify-content: space-between;
    font-size: 10px;
    color: #a89474;
    border-bottom: 1px solid #2b1d0c;
    padding-bottom: 6px;
    margin-bottom: 8px;
  }
  .geo-tags strong { color: #38ef7d; }
  .data-flow-meters {
    display: flex;
    justify-content: space-around;
    font-size: 10px;
    color: #c4b196;
  }
  .data-flow-meters strong { color: #ffd700; }

  /* ---------------- Sağ Sütun ---------------- */
  .col-right .agents-scroll-box {
    max-height: 140px;
    overflow-y: auto;
  }
  .agent-row {
    display: flex;
    align-items: center;
    font-size: 10px;
    padding: 3px 0;
    border-bottom: 1px solid #1a1208;
  }
  .ag-code { width: 24px; color: #ffd700; font-family: monospace; }
  .ag-name { width: 95px; font-weight: 600; color: #e6dfd5; }
  .ag-desc { flex: 1; color: #8c7355; font-size: 9px; }

  .social-reach-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    font-size: 10px;
  }
  .social-item {
    background: #0f0b06;
    padding: 4px 8px;
    border: 1px solid #2b1d0c;
    display: flex;
    justify-content: space-between;
  }
  .social-item strong { color: #38ef7d; font-family: monospace; }

  .aspasia-head {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-bottom: 8px;
  }
  .aspasia-portrait {
    width: 36px;
    height: 36px;
    background: #1c140b;
    border: 1px solid #d4af37;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
  }
  .aspasia-speech {
    font-size: 10px;
    color: #ffd700;
  }
  .aspasia-modes {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 4px;
  }
  .aspasia-modes button {
    background: #140d06;
    border: 1px solid #3d2a13;
    color: #a89474;
    font-size: 8px;
    padding: 4px 0;
    cursor: pointer;
  }
  .aspasia-modes button.active {
    background: #5a3e19;
    color: #fff;
    border-color: #d4af37;
  }

  .radar-box {
    display: flex;
    gap: 12px;
    align-items: center;
  }
  .radar-telemetry {
    font-size: 10px;
    color: #a89474;
    line-height: 1.5;
  }
  .radar-telemetry strong { color: #38ef7d; font-family: monospace; }

  .risk-distribution {
    display: flex;
    justify-content: space-around;
    font-size: 10px;
    margin-bottom: 6px;
  }
  .risk-col strong { color: #38ef7d; }
  .risk-col.highlight strong { color: #ef4444; }
  .risk-threat-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    font-size: 8px;
    color: #ef4444;
  }
  .threat-tag {
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    padding: 2px 6px;
    border-radius: 2px;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .case-brief {
    font-size: 10px;
    color: #a89474;
    line-height: 1.4;
  }
  .case-title {
    font-weight: 700;
    color: #ffd700;
    display: flex;
    justify-content: space-between;
    margin-bottom: 4px;
  }
  .tag-done {
    color: #38ef7d;
    background: rgba(56, 239, 125, 0.1);
    border: 1px solid rgba(56, 239, 125, 0.3);
    padding: 1px 4px;
    border-radius: 2px;
    font-size: 8px;
  }
  .view-dossier-btn {
    width: 100%;
    margin-top: 6px;
    background: #1c140b;
    border: 1px solid #5a3e19;
    color: #d4af37;
    font-size: 9px;
    letter-spacing: 1px;
    padding: 5px;
    cursor: pointer;
    border-radius: 2px;
  }
  .view-dossier-btn:hover {
    background: #2b1d0c;
    border-color: #d4af37;
  }

  /* ---------------- Alt Endüstriyel Kontrol Rayı ---------------- */
  .observatory-bottom-rail {
    height: 70px;
    background: linear-gradient(180deg, #18120b 0%, #090704 100%);
    border-top: 3px solid #5a3e19;
    box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.9);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 24px;
    z-index: 10;
  }

  .geta-block {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .sacred-triangle-mini {
    font-size: 18px;
    color: #d4af37;
    border: 1px solid #5a3e19;
    padding: 2px 6px;
    border-radius: 2px;
  }
  .geta-text strong {
    display: block;
    font-size: 11px;
    letter-spacing: 1.5px;
    color: #ffd700;
  }
  .geta-text small {
    font-size: 8px;
    color: #8c7355;
  }

  .toggle-switches-block {
    display: flex;
    gap: 18px;
    align-items: center;
  }
  .hardware-switch {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
  }
  .switch-btn {
    width: 22px;
    height: 34px;
    background: #0a0704;
    border: 2px solid #5a3e19;
    border-radius: 4px;
    padding: 2px;
    cursor: pointer;
    position: relative;
  }
  .switch-toggle {
    display: block;
    width: 14px;
    height: 14px;
    background: #73532b;
    border-radius: 2px;
    transition: transform 0.15s;
    transform: translateY(12px);
  }
  .switch-btn.engaged .switch-toggle {
    transform: translateY(0);
    background: #d4af37;
  }
  .switch-lamp {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #2b1d0c;
  }
  .switch-lamp.lit {
    background: #38ef7d;
    box-shadow: 0 0 8px #38ef7d;
  }
  .hardware-switch .switch-label {
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #a89474;
  }

  .sacred-core-btn {
    width: 44px;
    height: 44px;
    background: radial-gradient(circle, #3d2a13 0%, #171109 100%);
    border: 2px solid #d4af37;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 0 15px rgba(212, 175, 55, 0.3);
  }
  .sacred-glyph { font-size: 16px; color: #ffd700; }

  /* Acil Stop */
  .emergency-stop-block {
    background: repeating-linear-gradient(
      -45deg,
      #1a150c,
      #1a150c 10px,
      #eab308 10px,
      #eab308 20px
    );
    padding: 4px;
    border: 2px solid #000;
    border-radius: 4px;
  }
  .emergency-mushroom-btn {
    background: linear-gradient(180deg, #dc2626 0%, #7f1d1d 100%);
    border: 2px solid #ef4444;
    border-radius: 4px;
    padding: 6px 18px;
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    box-shadow: 0 4px 10px rgba(0,0,0,0.8);
    transition: transform 0.1s;
  }
  .emergency-mushroom-btn:active {
    transform: scale(0.95);
  }
  .mushroom-cap {
    width: 14px;
    height: 14px;
    background: #ff4d4d;
    border-radius: 50%;
    box-shadow: 0 0 6px #ff4d4d;
  }
  .stop-label {
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 1.5px;
    color: #fff;
    text-shadow: 0 1px 2px #000;
  }

  /* Vault Token Slotu */
  .vault-token-block .crystal-slot {
    background: #090704;
    border: 1px solid #4a3418;
    border-radius: 4px;
    padding: 6px 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 10px;
    color: #06b6d4;
  }
  .token-code { font-family: monospace; letter-spacing: 1px; }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
  @keyframes rotate-dial {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  @keyframes brain-pulse {
    0%, 100% { transform: scale(1); filter: drop-shadow(0 0 6px #ffd700); }
    50% { transform: scale(1.06); filter: drop-shadow(0 0 15px #f59e0b); }
  }
</style>
