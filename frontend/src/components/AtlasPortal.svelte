<script lang="ts">
  import { activeViewMode, activeTargetUrl, isProcessing, apiFetch, clientId, taskStatus } from '../store';
  import { playClick } from '../lib/consoleAudio';

  // Seçili hizmet sekmesi
  type ServiceType = 'osint' | 'risk' | 'kul' | 'sedef';
  let activeService: ServiceType = 'osint';

  let inputVal = '';
  let noteVal = '';
  let statusNotice = '';
  let isSubmitting = false;

  const SERVICES = [
    {
      id: 'osint' as ServiceType,
      num: '01',
      title: 'HEDEF & HESAP İSTİHBARATI',
      tagline: 'Bir hesabı veya şahsı 360° açık kaynaklardan çözün',
      desc: 'Sosyal medya hesaplarını, dijital ayak izlerini, gizlenen ilgi alanlarını, hassasiyet noktalarını ve muhatabın savunmasını düşüren en doğru ilk temas stratejisini çıkarır.',
      placeholder: 'İncelenecek profil linki veya kullanıcı adı (örn: https://instagram.com/kullanici)...',
      badge: 'AÇIK KAYNAK // OSINT',
      color: '#10b981',
      actionLabel: 'HESABI İNCELEMEYE AL'
    },
    {
      id: 'risk' as ServiceType,
      num: '02',
      title: 'GÜVENİLİRLİK & RİSK RADARI',
      tagline: 'Kiminle masaya oturduğunuzu kanıtıyla bilin',
      desc: 'Ortaklık, evlilik, iş anlaşması veya yatırım öncesi karşı tarafın gerçekliğini test eder. Takipçi şişirmesini, bot oranını, uyku saatlerinden gerçek konumunu ve sahnelenen vitrin çelişkilerini belgeler.',
      placeholder: 'Analiz edilecek şahıs profili, web adresi veya kullanıcı adı...',
      badge: 'ADLİ DENETİM // RADAR',
      color: '#06b6d4',
      actionLabel: 'RİSK RAPORUNU BAŞLAT'
    },
    {
      id: 'kul' as ServiceType,
      num: '03',
      title: 'DİJİTAL KÜL (İZLERİ SİLME)',
      tagline: 'İnternetteki bütün varlığınızı küle gömün',
      desc: 'Geçmişte kalmış hatalı, yanıltıcı, sızmış veya unutulmasını istediğiniz verilerinizi arama motorlarından, veritabanlarından ve platformlardan yasal ve teknik yollarla kökünden kaldırtır.',
      placeholder: 'Kaldırılmasını / silinmesini istediğiniz isim, URL veya konu başlığı...',
      badge: 'PROTOKOL 02 // UNUTULMA',
      color: '#ef4444',
      actionLabel: 'SİLME TALEBİ OLUŞTUR'
    },
    {
      id: 'sedef' as ServiceType,
      num: '04',
      title: 'DİJİTAL SEDEF (YENİDEN İNŞA)',
      tagline: 'Yeni bir insan, lekesiz ve sarsılmaz yeni bir itibar kurun',
      desc: 'Geçmişi arkada bırakın. İnternette arandığında hakkınızda yalnızca saygın, doğru ve hedefinize uygun profesyonel kayıtların çıkacağı koruyucu bir sedef itibar kalkanı inşa eder.',
      placeholder: 'İnşa etmek istediğiniz yeni kimlik, unvan, uzmanlık veya alan...',
      badge: 'PROTOKOL 03 // YENİ KİMLİK',
      color: '#d4af37',
      actionLabel: 'YENİDEN İNŞAYI BAŞLAT'
    }
  ];

  $: currentServiceObj = SERVICES.find(s => s.id === activeService) || SERVICES[0];

  function selectService(id: ServiceType) {
    activeService = id;
    statusNotice = '';
    playClick(450, 30);
  }

  async function submitRequest() {
    const val = inputVal.trim();
    if (!val || isSubmitting) return;
    isSubmitting = true;
    statusNotice = '';
    playClick(550, 40);

    try {
      if (activeService === 'osint' || activeService === 'risk') {
        // Doğrudan backend analizini tetikle
        activeTargetUrl.set(val);
        const res = await apiFetch('/api/initiate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: $clientId || 'default',
            url: val,
            rituals: '',
            playlist: '',
            envies: noteVal.trim(),
            scraper_type: 'cross',
          })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(data?.error?.message || data?.detail || `Sunucu yanıtı: ${res.status}`);
        }
        if (data.task_id) {
          taskStatus.update(s => ({ ...(s || {}), task_id: data.task_id, status: 'processing' }));
          isProcessing.set(true);
          statusNotice = `Operasyon başlatıldı (Görev ID: ${data.task_id}). Ajanlar taramaya başladı.`;
          // İsteğe bağlı olarak kokpite yönlendir
        } else {
          statusNotice = 'Talebiniz kabul edildi. İnceleme sıraya alındı.';
        }
      } else {
        // KÜL veya SEDEF talebi: Komutan/Destek kaydı
        const res = await apiFetch('/api/commander/inject', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: $clientId || 'default',
            evidence_type: activeService === 'kul' ? 'ground_truth' : 'note',
            evidence_value: `[TALEP-${activeService.toUpperCase()}] ${val} | Not: ${noteVal.trim()}`,
            target_agent: 'all',
            note: `${currentServiceObj.title} başvurusu`
          })
        });
        if (!res.ok) throw new Error('Talep sunucuya iletilemedi.');
        statusNotice = `✓ Talebiniz güvenli sisteme mühürlendi. ${currentServiceObj.title} protokolü incelemeye alındı.`;
        inputVal = '';
        noteVal = '';
      }
    } catch (e: any) {
      statusNotice = `Bilgi: ${e?.message || 'İşlem kaydedildi.'}`;
    } finally {
      isSubmitting = false;
    }
  }

  function goToCockpit() {
    playClick(600, 30);
    activeViewMode.set('cockpit');
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('pineal_view_mode', 'cockpit');
    }
  }
</script>

<div class="atlas-portal-root">
  <!-- Scanlines & ambient vignette -->
  <div class="portal-scanlines" aria-hidden="true"></div>

  <!-- Üst Gezinme Çubuğu -->
  <header class="portal-navbar">
    <div class="nav-brand">
      <span class="brand-eye-icon">👁</span>
      <div class="brand-text">
        <strong class="brand-name">ATLAS EPİFİZ</strong>
        <span class="brand-sub">PINEAL OBSERVATORY // ÖZEL DİJİTAL İSTİHBARAT</span>
      </div>
    </div>

    <div class="nav-actions">
      <a href="#services" class="nav-link">Hizmet Alanları</a>
      <a href="#protocols" class="nav-link">Üç Protokol</a>
      <a href="#principles" class="nav-link">İlkelerimiz</a>
      <button type="button" class="cockpit-switch-btn" on:click={goToCockpit} title="12 Saha Ajanı ve Gelişmiş Konsol">
        <span class="btn-icon">⚙</span> TEKNİK KOKPİT'E GEÇ
      </button>
    </div>
  </header>

  <!-- Hero Karşılama Bölümü -->
  <section class="portal-hero">
    <div class="hero-badge">PINEAL EPİFİZ EKOSİSTEMİ // RESMÎ HİZMET PORTALI</div>
    <h1 class="hero-title">
      Dijital dünya hafızası değil, <span class="highlight-gold">kayıt sistemidir</span>.
    </h1>
    <p class="hero-lead">
      O kayıtlara her gün tıklanıyor. <strong>Atlas Epifiz</strong> der ki: <em>Kayıtları siz yöneteceksiniz.</em><br />
      Merkezde hiç kapanmayan <strong>Epifiz Gözü</strong> var.
    </p>

    <!-- Hızlı Başlatma Kartı -->
    <div class="portal-terminal-card" id="start">
      <!-- 4 Hizmet Sekmesi -->
      <div class="service-tabs" role="tablist">
        {#each SERVICES as s}
          <button
            type="button"
            role="tab"
            class="service-tab-btn"
            class:active={activeService === s.id}
            on:click={() => selectService(s.id)}
            style="--accent-color: {s.color};"
          >
            <span class="tab-num">{s.num}</span>
            <span class="tab-label">{s.title}</span>
          </button>
        {/each}
      </div>

      <!-- Aktif Hizmet Açıklaması ve Form -->
      <div class="terminal-body">
        <div class="service-info-header">
          <div>
            <span class="service-badge" style="background: {currentServiceObj.color}22; color: {currentServiceObj.color}; border: 1px solid {currentServiceObj.color}55;">
              {currentServiceObj.badge}
            </span>
            <h2 class="service-headline">{currentServiceObj.tagline}</h2>
          </div>
          <p class="service-desc">{currentServiceObj.desc}</p>
        </div>

        <div class="terminal-form">
          <div class="input-wrap">
            <span class="input-icon">⌖</span>
            <input
              type="text"
              class="main-input"
              bind:value={inputVal}
              placeholder={currentServiceObj.placeholder}
              on:keydown={(e) => e.key === 'Enter' && submitRequest()}
            />
          </div>

          <div class="secondary-row">
            <input
              type="text"
              class="sub-input"
              bind:value={noteVal}
              placeholder="Ek bağlam, özel not veya hedefiniz (opsiyonel)..."
            />
            <button
              type="button"
              class="action-submit-btn"
              class:busy={isSubmitting}
              disabled={isSubmitting || !inputVal.trim()}
              on:click={submitRequest}
              style="--btn-color: {currentServiceObj.color};"
            >
              {isSubmitting ? 'İŞLENİYOR...' : currentServiceObj.actionLabel}
            </button>
          </div>

          {#if statusNotice}
            <div class="status-alert" role="status">
              {statusNotice}
              {#if isProcessing && (activeService === 'osint' || activeService === 'risk')}
                <button type="button" class="cockpit-link-inline" on:click={goToCockpit}>
                  Canlı Ajan Akışını İzle ➔
                </button>
              {/if}
            </div>
          {/if}
        </div>
      </div>
    </div>
  </section>

  <!-- 4 Hizmet Alanı Detayları -->
  <section class="portal-section" id="services">
    <div class="section-head">
      <span class="section-tag">ÖZEL HİZMETLERİMİZ</span>
      <h2 class="section-title">İnternetteki Kaosu Dört Ayrı Disiplinle Yönetin</h2>
      <p class="section-sub">Kişiler ve kurumlar için kanıta dayalı, yasal ve stratejik çözümler.</p>
    </div>

    <div class="services-grid">
      <article class="service-card">
        <div class="card-icon" style="color: #10b981;">⌖</div>
        <span class="card-num">01</span>
        <h3>Bir Hesabı / Şahsı Araştırmak</h3>
        <p>Açık kaynaklardan (OSINT) 360° derinlemesine profil çözümü. Hedefin gerçek kimliği, gizlenen ilgi alanları, hassasiyet ve sürtünme noktaları ve savunmasını düşüren ilk temas stratejisi.</p>
        <button class="card-action" on:click={() => selectService('osint')}>Bu Hizmeti Seç ➔</button>
      </article>

      <article class="service-card">
        <div class="card-icon" style="color: #06b6d4;">🛡</div>
        <span class="card-num">02</span>
        <h3>Kiminle Masaya Oturuyorsunuz?</h3>
        <p>Ortaklık, evlilik, iş anlaşması veya yatırım öncesi adli risk radarı. Takipçi şişirmesi, bot ağları, paylaşım saatlerinden gerçek sirkadiyen ritim ve sahnelenen vitrin çelişkileri.</p>
        <button class="card-action" on:click={() => selectService('risk')}>Bu Hizmeti Seç ➔</button>
      </article>

      <article class="service-card">
        <div class="card-icon" style="color: #ef4444;">🔥</div>
        <span class="card-num">03</span>
        <h3>Varlığınızı İnternetten Silmek (KÜL)</h3>
        <p>İnternette kalmış eski, hatalı, yanıltıcı veya sızmış kayıtlarınızı yok edin. KVKK/GDPR ve arama motoru dizin çıkarma süreçleriyle verileri kaynağından söndürün.</p>
        <button class="card-action" on:click={() => selectService('kul')}>Bu Hizmeti Seç ➔</button>
      </article>

      <article class="service-card">
        <div class="card-icon" style="color: #d4af37;">🐚</div>
        <span class="card-num">04</span>
        <h3>Yeni Bir Kişilik & İtibar İnşası (SEDEF)</h3>
        <p>Geçmişi arkada bırakıp yeni bir insan olarak doğun. Arandığınızda hakkınızda yalnızca saygın, güçlü ve doğru kayıtların çıkacağı sarsılmaz bir itibar kalkanı örün.</p>
        <button class="card-action" on:click={() => selectService('sedef')}>Bu Hizmeti Seç ➔</button>
      </article>
    </div>
  </section>

  <!-- Üç Temel Protokol -->
  <section class="portal-section dark-bg" id="protocols">
    <div class="section-head">
      <span class="section-tag">METODOLOJİ</span>
      <h2 class="section-title">Üç Temel Protokol: İZ · KÜL · SEDEF</h2>
    </div>

    <div class="protocols-row">
      <div class="protocol-box">
        <span class="proto-glyph">🔍</span>
        <h4>PROTOKOL 01: İZ</h4>
        <strong>Harita & İstihbarat</strong>
        <p>İster bir başkasını araştırın, ister kendi dijital izinizi görün. Arama motorları, siciller ve sosyal platformlardaki her kayıt URL ve zaman damgasıyla haritalandırılır.</p>
      </div>

      <div class="protocol-box">
        <span class="proto-glyph">🔥</span>
        <h4>PROTOKOL 02: KÜL</h4>
        <strong>Düzeltme & Silme Talebi</strong>
        <p>Hatalı veya süresi dolmuş veriler sihirle değil; hukuki ve resmî kanallardan (KVKK, arama motoru başvuruları) talep süreciyle kaynağından söndürülür.</p>
      </div>

      <div class="protocol-box">
        <span class="proto-glyph">🛡</span>
        <h4>PROTOKOL 03: SEDEF</h4>
        <strong>Güçlendirme & Yeniden İnşa</strong>
        <p>Sahte kimlik değil; bireyin/kurumun kendi kontrolünde, resmî kanallarda doğru ve eksiksiz bilgilerle donatılarak itibar saldırılarına karşı doğal kalkan oluşturulmasıdır.</p>
      </div>
    </div>
  </section>

  <!-- İlkelerimiz (Dürüstlük & Sınırlar) -->
  <section class="portal-section" id="principles">
    <div class="section-head">
      <span class="section-tag">DÜRÜSTLÜK VE ANAYASA</span>
      <h2 class="section-title">Kırmızı Çizgilerimiz ve Çalışma İlkelerimiz</h2>
    </div>

    <div class="principles-grid">
      <div class="principle-item">
        <strong>✦ Hedef Rıza Kapısı Yoktur</strong>
        <p>Kamuya açık profil ve açık kaynak istihbaratında hedef rızası aranmaz. Veri açıktaysa incelenir, yetki operatördedir.</p>
      </div>
      <div class="principle-item">
        <strong>✦ Şifre Kırma / Hackleme Yapılmaz</strong>
        <p>Sistem hacker aracı değildir. Yalnızca açık kaynakları (OSINT) tarar ve matematiksel ölçümlerle adli kanıt üretir.</p>
      </div>
      <div class="principle-item warning-item">
        <strong>⛔ TEK Kırmızı Çizgi: 18 Yaş Altı</strong>
        <p>18 yaşından küçük hiçbir çocuk araştırılamaz (MinorGate). Tek istisna resmi kayıp vakalarıdır.</p>
      </div>
      <div class="principle-item">
        <strong>✦ Sıfır Halüsinasyon</strong>
        <p>Kuru falcılık ve tahmin yapılmaz. Veri yoksa "bilmiyorum" denir; her iddianın arkasına kriptografik kanıt mühürlenir.</p>
      </div>
    </div>
  </section>

  <!-- Alt Bilgi (Footer) -->
  <footer class="portal-footer">
    <div class="footer-inner">
      <div class="footer-brand">
        <strong>ATLAS EPİFİZ // PINEAL OBSERVATORY</strong>
        <p>Dijital Maruziyet Zekası, Adli İstihbarat ve İtibar Yönetimi.</p>
      </div>
      <div class="footer-links">
        <button type="button" class="footer-btn" on:click={goToCockpit}>
          👁️ Operatör Konsolu
        </button>
      </div>
    </div>
    <div class="footer-copy">
      © 2026 Atlas Epifiz · Pineal Ekosistemi · Tüm Hakları Saklıdır.
    </div>
  </footer>
</div>

<style>
  :root {
    --gold: #d4af37;
    --gold-glow: rgba(212, 175, 55, 0.35);
    --bg-dark: #07090e;
    --bg-card: rgba(13, 17, 23, 0.85);
    --border-color: rgba(212, 175, 55, 0.22);
    --text-primary: #e6edf3;
    --text-dim: #8b949e;
  }

  .atlas-portal-root {
    min-height: 100vh;
    width: 100vw;
    background: radial-gradient(ellipse at 50% 15%, #141b24 0%, #06080b 70%, #020304 100%);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
    overflow-x: hidden;
    position: relative;
  }

  .portal-scanlines {
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 99;
    background: repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0, 0, 0, 0.12) 3px, rgba(0, 0, 0, 0.12) 4px);
    opacity: 0.6;
  }

  /* Navbar */
  .portal-navbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.2rem 3rem;
    border-bottom: 1px solid var(--border-color);
    background: rgba(7, 9, 14, 0.85);
    backdrop-filter: blur(12px);
    position: sticky;
    top: 0;
    z-index: 50;
  }

  .nav-brand {
    display: flex;
    align-items: center;
    gap: 0.8rem;
  }

  .brand-eye-icon {
    font-size: 1.6rem;
    color: var(--gold);
    text-shadow: 0 0 12px var(--gold-glow);
  }

  .brand-text {
    display: flex;
    flex-direction: column;
  }

  .brand-name {
    font-size: 1.1rem;
    letter-spacing: 0.15em;
    color: var(--gold);
    font-weight: 800;
  }

  .brand-sub {
    font-size: 0.65rem;
    color: var(--text-dim);
    letter-spacing: 0.08em;
  }

  .nav-actions {
    display: flex;
    align-items: center;
    gap: 1.5rem;
  }

  .nav-link {
    color: var(--text-dim);
    text-decoration: none;
    font-size: 0.85rem;
    transition: color 0.2s;
  }

  .nav-link:hover {
    color: var(--gold);
  }

  .cockpit-switch-btn {
    padding: 0.55rem 1.1rem;
    background: rgba(212, 175, 55, 0.12);
    border: 1px solid var(--gold);
    border-radius: 4px;
    color: var(--gold);
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    cursor: pointer;
    transition: all 0.2s;
  }

  .cockpit-switch-btn:hover {
    background: var(--gold);
    color: #07090e;
    box-shadow: 0 0 20px var(--gold-glow);
  }

  /* Hero */
  .portal-hero {
    max-width: 1040px;
    margin: 3.5rem auto 5rem;
    padding: 0 1.5rem;
    text-align: center;
  }

  .hero-badge {
    display: inline-block;
    padding: 0.3rem 0.9rem;
    background: rgba(212, 175, 55, 0.1);
    border: 1px solid rgba(212, 175, 55, 0.35);
    border-radius: 999px;
    color: var(--gold);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    margin-bottom: 1.5rem;
  }

  .hero-title {
    font-size: clamp(2rem, 4.5vw, 3.2rem);
    font-weight: 800;
    line-height: 1.25;
    margin-bottom: 1.2rem;
    letter-spacing: -0.02em;
  }

  .highlight-gold {
    color: var(--gold);
    text-shadow: 0 0 24px var(--gold-glow);
  }

  .hero-lead {
    font-size: clamp(1rem, 1.8vw, 1.25rem);
    color: var(--text-dim);
    max-width: 780px;
    margin: 0 auto 3rem;
  }

  .hero-lead strong {
    color: var(--text-primary);
  }

  /* Terminal Card */
  .portal-terminal-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    box-shadow: 0 20px 60px -15px rgba(0, 0, 0, 0.7), 0 0 40px -10px var(--gold-glow);
    overflow: hidden;
    text-align: left;
  }

  .service-tabs {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    background: rgba(5, 7, 10, 0.9);
    border-bottom: 1px solid var(--border-color);
  }

  .service-tab-btn {
    padding: 1rem 0.8rem;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--text-dim);
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
    transition: all 0.2s;
  }

  .service-tab-btn:hover {
    color: var(--text-primary);
    background: rgba(255, 255, 255, 0.02);
  }

  .service-tab-btn.active {
    color: var(--text-primary);
    border-bottom-color: var(--accent-color);
    background: rgba(255, 255, 255, 0.04);
  }

  .tab-num {
    font-size: 0.65rem;
    font-weight: 800;
    color: var(--gold);
    letter-spacing: 0.08em;
  }

  .tab-label {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-align: center;
  }

  .terminal-body {
    padding: 2.2rem 2.5rem;
  }

  .service-info-header {
    margin-bottom: 1.8rem;
  }

  .service-badge {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    margin-bottom: 0.6rem;
  }

  .service-headline {
    font-size: 1.3rem;
    font-weight: 700;
    margin-bottom: 0.4rem;
    color: var(--text-primary);
  }

  .service-desc {
    color: var(--text-dim);
    font-size: 0.9rem;
    line-height: 1.5;
  }

  .terminal-form {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .input-wrap {
    position: relative;
    display: flex;
    align-items: center;
  }

  .input-icon {
    position: absolute;
    left: 1.2rem;
    color: var(--gold);
    font-size: 1.2rem;
  }

  .main-input {
    width: 100%;
    padding: 1.1rem 1.2rem 1.1rem 3.2rem;
    background: rgba(5, 7, 10, 0.95);
    border: 1px solid rgba(212, 175, 55, 0.4);
    border-radius: 8px;
    color: var(--text-primary);
    font-size: 1rem;
    outline: none;
    transition: all 0.2s;
  }

  .main-input:focus {
    border-color: var(--gold);
    box-shadow: 0 0 20px var(--gold-glow);
  }

  .secondary-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 1rem;
  }

  .sub-input {
    padding: 0.85rem 1.2rem;
    background: rgba(5, 7, 10, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 0.85rem;
    outline: none;
  }

  .action-submit-btn {
    padding: 0.85rem 1.8rem;
    background: var(--btn-color);
    border: none;
    border-radius: 6px;
    color: #07090e;
    font-size: 0.85rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.2s;
  }

  .action-submit-btn:hover:not(:disabled) {
    box-shadow: 0 0 25px var(--btn-color);
    transform: translateY(-1px);
  }

  .action-submit-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none;
  }

  .status-alert {
    padding: 0.8rem 1.2rem;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.4);
    border-radius: 6px;
    color: #10b981;
    font-size: 0.85rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .cockpit-link-inline {
    background: transparent;
    border: 1px solid #10b981;
    color: #10b981;
    padding: 0.3rem 0.8rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 700;
    cursor: pointer;
  }

  .cockpit-link-inline:hover {
    background: #10b981;
    color: #07090e;
  }

  /* Portal Sections */
  .portal-section {
    max-width: 1100px;
    margin: 0 auto;
    padding: 5rem 1.5rem;
  }

  .portal-section.dark-bg {
    max-width: 100vw;
    background: rgba(4, 6, 9, 0.7);
    border-top: 1px solid var(--border-color);
    border-bottom: 1px solid var(--border-color);
  }

  .portal-section.dark-bg > * {
    max-width: 1100px;
    margin-left: auto;
    margin-right: auto;
  }

  .section-head {
    text-align: center;
    margin-bottom: 3.5rem;
  }

  .section-tag {
    font-size: 0.72rem;
    font-weight: 800;
    color: var(--gold);
    letter-spacing: 0.15em;
  }

  .section-title {
    font-size: 2rem;
    font-weight: 800;
    margin: 0.5rem 0;
  }

  .section-sub {
    color: var(--text-dim);
    font-size: 1rem;
  }

  /* Services Grid */
  .services-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 1.5rem;
  }

  .service-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    padding: 2rem 1.6rem;
    display: flex;
    flex-direction: column;
    position: relative;
    transition: all 0.25s;
  }

  .service-card:hover {
    border-color: var(--gold);
    transform: translateY(-3px);
    box-shadow: 0 10px 30px -10px var(--gold-glow);
  }

  .card-icon {
    font-size: 2rem;
    margin-bottom: 0.8rem;
  }

  .card-num {
    position: absolute;
    top: 1.5rem;
    right: 1.5rem;
    font-size: 0.75rem;
    font-weight: 800;
    color: var(--text-dim);
    opacity: 0.5;
  }

  .service-card h3 {
    font-size: 1.1rem;
    font-weight: 700;
    margin-bottom: 0.8rem;
  }

  .service-card p {
    color: var(--text-dim);
    font-size: 0.85rem;
    line-height: 1.55;
    margin-bottom: 1.5rem;
    flex: 1;
  }

  .card-action {
    background: transparent;
    border: none;
    color: var(--gold);
    font-size: 0.8rem;
    font-weight: 700;
    cursor: pointer;
    text-align: left;
    padding: 0;
  }

  .card-action:hover {
    text-decoration: underline;
  }

  /* Protocols Row */
  .protocols-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 2rem;
  }

  .protocol-box {
    background: rgba(13, 17, 23, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 2rem;
    text-align: center;
  }

  .proto-glyph {
    font-size: 2.2rem;
    display: block;
    margin-bottom: 0.8rem;
  }

  .protocol-box h4 {
    font-size: 1.1rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    color: var(--gold);
  }

  .protocol-box strong {
    display: block;
    font-size: 0.8rem;
    color: var(--text-dim);
    margin-bottom: 1rem;
    text-transform: uppercase;
  }

  .protocol-box p {
    font-size: 0.85rem;
    color: var(--text-dim);
    line-height: 1.55;
  }

  /* Principles Grid */
  .principles-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1.5rem;
  }

  .principle-item {
    background: var(--bg-card);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 8px;
    padding: 1.5rem;
  }

  .principle-item.warning-item {
    border-color: rgba(239, 68, 68, 0.35);
    background: rgba(239, 68, 68, 0.05);
  }

  .principle-item strong {
    display: block;
    font-size: 0.95rem;
    margin-bottom: 0.4rem;
    color: var(--text-primary);
  }

  .warning-item strong {
    color: #ef4444;
  }

  .principle-item p {
    color: var(--text-dim);
    font-size: 0.85rem;
    line-height: 1.5;
  }

  /* Footer */
  .portal-footer {
    border-top: 1px solid var(--border-color);
    background: #030407;
    padding: 3rem 2rem 2rem;
  }

  .footer-inner {
    max-width: 1100px;
    margin: 0 auto 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .footer-brand strong {
    font-size: 1rem;
    color: var(--gold);
    letter-spacing: 0.1em;
  }

  .footer-brand p {
    color: var(--text-dim);
    font-size: 0.75rem;
    margin-top: 0.2rem;
  }

  .footer-btn {
    padding: 0.6rem 1.2rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--gold);
    font-size: 0.8rem;
    font-weight: 700;
    cursor: pointer;
  }

  .footer-btn:hover {
    background: var(--gold);
    color: #07090e;
  }

  .footer-copy {
    text-align: center;
    color: var(--text-dim);
    font-size: 0.72rem;
    padding-top: 1.5rem;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
    max-width: 1100px;
    margin: 0 auto;
  }

  @media (max-width: 768px) {
    .portal-navbar { padding: 1rem; }
    .nav-actions .nav-link { display: none; }
    .service-tabs { grid-template-columns: repeat(2, 1fr); }
    .secondary-row { grid-template-columns: 1fr; }
    .protocols-row { grid-template-columns: 1fr; }
    .principles-grid { grid-template-columns: 1fr; }
    .footer-inner { flex-direction: column; gap: 1.5rem; text-align: center; }
  }
</style>
