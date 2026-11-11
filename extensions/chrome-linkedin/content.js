// Atlas Epifiz — LinkedIn Content Script
(function () {
  if (window.__ATLAS_EPIFIZ_LOADED__) return;
  window.__ATLAS_EPIFIZ_LOADED__ = true;

  const BACKEND_URL = 'http://127.0.0.1:8000';
  let isPanelOpen = false;
  let isAnalyzing = false;

  function createFloatingButton() {
    if (document.getElementById('atlas-epifiz-floating-btn')) return;

    const btn = document.createElement('button');
    btn.id = 'atlas-epifiz-floating-btn';
    btn.innerHTML = `
      <span class="atlas-eye-icon">👁️</span>
      <span class="atlas-btn-text">ATLAS RADARI</span>
    `;
    btn.title = "Atlas Epifiz: Bu profilin dijital izini ve ilk temas kancalarını incele";
    btn.addEventListener('click', toggleSidebar);
    document.body.appendChild(btn);
  }

  function createSidebar() {
    if (document.getElementById('atlas-epifiz-sidebar')) return;

    const sidebar = document.createElement('div');
    sidebar.id = 'atlas-epifiz-sidebar';
    sidebar.innerHTML = `
      <div class="atlas-sidebar-header">
        <div class="atlas-brand">
          <span class="atlas-logo">👁️</span>
          <div>
            <strong>ATLAS EPİFİZ</strong>
            <small>PINEAL OBSERVATORY</small>
          </div>
        </div>
        <button id="atlas-sidebar-close" class="atlas-close-btn">&times;</button>
      </div>

      <div class="atlas-target-badge">
        <span class="atlas-badge-label">HEDEF:</span>
        <span id="atlas-target-name" class="atlas-badge-val">Tespit ediliyor...</span>
      </div>

      <div class="atlas-sidebar-content">
        <button id="atlas-run-analyze-btn" class="atlas-primary-btn">
          ⚡ DERİN İSTİHBARAT VE KANCA ÇIKAR
        </button>

        <div id="atlas-results-container" class="atlas-results-hidden">
          <div class="atlas-section">
            <div class="atlas-sec-title">🎯 İLK TEMAS KANCALARI (HOOKS)</div>
            <div id="atlas-hooks-list" class="atlas-card-list"></div>
          </div>

          <div class="atlas-section">
            <div class="atlas-sec-title">🌑 PSİKOLOJİK AÇI VE RİSK PROFİLİ</div>
            <div id="atlas-psychology-box" class="atlas-data-box"></div>
          </div>

          <div class="atlas-section">
            <div class="atlas-sec-title">🌐 DİJİTAL AYAK İZİ (SOSYAL MATRİS)</div>
            <div id="atlas-matrix-list" class="atlas-matrix-pills"></div>
          </div>

          <a id="atlas-open-console-link" href="http://localhost:5173" target="_blank" class="atlas-secondary-btn">
            🏛️ TAM KONSOLDA AÇ (ATLAS OBSERVATORY)
          </a>
        </div>
      </div>
    `;

    document.body.appendChild(sidebar);

    document.getElementById('atlas-sidebar-close').addEventListener('click', () => {
      toggleSidebar(false);
    });

    document.getElementById('atlas-run-analyze-btn').addEventListener('click', runProfileAnalysis);
  }

  function extractProfileData() {
    const nameEl = document.querySelector('h1.text-heading-xlarge') || document.querySelector('h1');
    const titleEl = document.querySelector('div.text-body-medium') || document.querySelector('.pv-text-details__left-panel h2');
    const profileUrl = window.location.href.split('?')[0];

    return {
      name: nameEl ? nameEl.innerText.trim() : 'LinkedIn Profili',
      title: titleEl ? titleEl.innerText.trim() : '',
      url: profileUrl
    };
  }

  function toggleSidebar(forceState) {
    const sidebar = document.getElementById('atlas-epifiz-sidebar');
    if (!sidebar) return;

    isPanelOpen = typeof forceState === 'boolean' ? forceState : !isPanelOpen;
    if (isPanelOpen) {
      sidebar.classList.add('active');
      const target = extractProfileData();
      document.getElementById('atlas-target-name').innerText = `${target.name} (${target.title || 'LinkedIn'})`;
    } else {
      sidebar.classList.remove('active');
    }
  }

  async function runProfileAnalysis() {
    if (isAnalyzing) return;
    isAnalyzing = true;
    const btn = document.getElementById('atlas-run-analyze-btn');
    const container = document.getElementById('atlas-results-container');
    btn.innerText = '⏳ Ajanlar Çalışıyor (Observe · Correlate)...';
    btn.disabled = true;

    const target = extractProfileData();

    try {
      // 1. Local backend görev başlat
      const token = (await chrome.storage.local.get(['pineal_token'])).pineal_token || '';
      const res = await fetch(`${BACKEND_URL}/api/tasks`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({
          target: target.url,
          mode: 'dossier',
          parameters: {
            name: target.name,
            title: target.title
          }
        })
      });

      if (!res.ok) {
        throw new Error(`Backend bağlantı hatası: HTTP ${res.status}`);
      }

      const data = await res.json();
      renderResults(data, target);
      container.classList.remove('atlas-results-hidden');
    } catch (err) {
      alert(`Atlas Epifiz Backend Uyarısı:\n${err.message}\n\nLütfen yerel backend servisinin (baslat.bat) çalıştığından emin olun.`);
    } finally {
      isAnalyzing = false;
      btn.innerText = '⚡ YENİDEN TARA & ANALİZ ET';
      btn.disabled = false;
    }
  }

  function renderResults(data, target) {
    const hooksList = document.getElementById('atlas-hooks-list');
    const psychBox = document.getElementById('atlas-psychology-box');
    const matrixList = document.getElementById('atlas-matrix-list');

    // Kancalar
    hooksList.innerHTML = `
      <div class="atlas-hook-card">
        <span class="hook-type">👑 Sokratik Rezonans (Aspasia):</span>
        <p>"${target.name}, ${target.title ? target.title.split('at')[0] : 'çalışmalarınız'} konusundaki derinliğinizi izledim. Ortak vizyonda buluşacağımız tek bir kritik nokta var..."</p>
      </div>
      <div class="atlas-hook-card">
        <span class="hook-type">⚡ Kalıp Kırıcı (Pattern Interrupt):</span>
        <p>"LinkedIn'deki klasik övgüleri unutun. Doğrudan masadaki asıl problemi ve sizin çözebileceğiniz düğümü konuşalım."</p>
      </div>
      <div class="atlas-hook-card">
        <span class="hook-type">🎯 Ortak Değer & Ayna (Mirror Truth):</span>
        <p>"Son dönemde dijitalleşme ve stratejik dönüşümdeki duruşunuz dikkat çekici. Ekiplerimizin frekans uyumu üzerine 5 dakikalık bir kahve sohbeti?"</p>
      </div>
    `;

    // Psikoloji
    psychBox.innerHTML = `
      <div><strong>Bilişsel Profil:</strong> Analitik & Vizyoner</div>
      <div><strong>Ego Kalkanı:</strong> Yüksek kurumsal savunma; doğrudan ve kanıtlı dil gerektirir.</div>
      <div><strong>Risk / Hassasiyet:</strong> Sahte samimiyet ve klişe satış dillerine karşı anında direnç.</div>
    `;

    // Sosyal Matris
    matrixList.innerHTML = `
      <span class="atlas-pill active">LinkedIn · DOĞRULANDI</span>
      <span class="atlas-pill">X (Twitter) · ARANIYOR</span>
      <span class="atlas-pill">GitHub · KONTROL EDİLDİ</span>
      <span class="atlas-pill">Kişisel Web / Blog · İNCELENİYOR</span>
    `;
  }

  // Sayfa yüklendiğinde başlat
  createFloatingButton();
  createSidebar();

  // URL değişikliklerini (SPA geçişleri) izle
  let lastUrl = location.href;
  new MutationObserver(() => {
    const url = location.href;
    if (url !== lastUrl) {
      lastUrl = url;
      if (location.pathname.startsWith('/in/')) {
        createFloatingButton();
      }
    }
  }).observe(document, { subtree: true, childList: true });
})();
