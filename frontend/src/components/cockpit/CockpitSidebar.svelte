<script lang="ts">
  import Icon from '../Icon.svelte';
  import { activeTab, sidebarOpen, type CockpitTab } from '../../lib/theme';
  import { APP_VERSION } from '../../lib/version';

  export let onOpenTerms: () => void = () => {};

  const NAV_ITEMS: Array<{
    id: CockpitTab;
    title: string;
    subtitle: string;
    icon: string;
    accent?: 'emerald' | 'pink' | 'indigo';
  }> = [
    {
      id: 'home',
      title: 'Ana Ekran',
      subtitle: 'Hedef analiz, ajanlar, özet',
      icon: 'home',
      accent: 'emerald',
    },
    {
      id: 'cross',
      title: 'Çapraz Tarama',
      subtitle: 'Kullanıcı adı, e-posta, telefon',
      icon: 'search',
      accent: 'indigo',
    },
    {
      id: 'aspasia',
      title: 'Aspasia Sohbet',
      subtitle: 'Danışman ile yazışma',
      icon: 'message',
      accent: 'emerald',
    },
    {
      id: 'lilith',
      title: 'Lilith & İlk Mesaj',
      subtitle: 'İlk temas mesajı ve büyüme',
      icon: 'sparkle',
      accent: 'pink',
    },
    {
      id: 'company',
      title: 'Şirket Tarama',
      subtitle: 'Alan adı, SEO, çalışanlar',
      icon: 'building',
    },
    {
      id: 'media',
      title: 'Medya & Ses',
      subtitle: 'Video, kare, sesli rapor',
      icon: 'film',
    },
    {
      id: 'browser',
      title: 'Canlı Tarayıcı',
      subtitle: 'Instagram / Google oturumu',
      icon: 'globe',
    },
    {
      id: 'reports',
      title: 'Raporlar & Hafıza',
      subtitle: 'PDF/Şema/Video ve geçmiş',
      icon: 'folder',
    },
    {
      id: 'system',
      title: 'Tüm Yetenekler (28)',
      subtitle: 'Durum tablosu ve araçlar',
      icon: 'sliders',
    },
  ];

  function selectTab(id: CockpitTab) {
    activeTab.set(id);
    sidebarOpen.set(false);
  }
</script>

{#if $sidebarOpen}
  <div
    class="sidebar-backdrop"
    role="presentation"
    on:click={() => sidebarOpen.set(false)}
  ></div>
{/if}

<aside class="cockpit-sidebar" class:open={$sidebarOpen} aria-label="Ana menü">
  <div class="sidebar-top-mobile">
    <span class="sidebar-label">BÖLÜMLER</span>
    <button
      type="button"
      class="btn btn-ghost btn-sm"
      on:click={() => sidebarOpen.set(false)}
      aria-label="Menüyü kapat"
    >
      <Icon name="close" size={0.95} />
    </button>
  </div>

  <div class="atelier-crest">
    <img src="/atelier/mark.webp" alt="Pineal Epifiz mührü" class="atelier-emblem" width="56" height="56" />
    <div class="crest-copy">
      <span class="crest-sign">Atelier Épifiz</span>
      <span class="atelier-kicker crest-kicker">İÇİNDEKİLER</span>
    </div>
  </div>

  <nav class="nav-list">
    {#each NAV_ITEMS as item, idx (item.id)}
      <button
        type="button"
        class="nav-item"
        class:active={$activeTab === item.id}
        data-tab={item.id}
        on:click={() => selectTab(item.id)}
      >
        <span class="nav-num code-mono">{String(idx + 1).padStart(2, '0')}</span>
        <span
          class="nav-icon"
          class:accent-pink={item.accent === 'pink'}
          class:accent-indigo={item.accent === 'indigo'}
        >
          <Icon name={item.icon} size={1.05} />
        </span>
        <span class="nav-text">
          <span class="nav-title">{item.title}</span>
          <span class="nav-sub">{item.subtitle}</span>
        </span>
      </button>
    {/each}
  </nav>

  <div class="sidebar-foot">
    <button
      type="button"
      class="terms-btn"
      data-testid="open-terms-btn"
      on:click={onOpenTerms}
    >
      <Icon name="shield" size={0.95} />
      <span>Kullanım Koşulları &amp; KVKK</span>
    </button>
    <div class="version-line">
      <span>Sürüm</span>
      <span class="code-mono">v{APP_VERSION}</span>
    </div>
  </div>
</aside>

<style>
  .sidebar-backdrop {
    display: none;
  }

  .cockpit-sidebar {
    width: 262px;
    flex-shrink: 0;
    background: var(--bg-sidebar);
    backdrop-filter: blur(16px);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 14px 12px;
    overflow-y: auto;
  }

  .atelier-crest {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 4px 6px 14px;
    margin-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }

  .atelier-emblem {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    border: 1px solid var(--gold);
    object-fit: cover;
    flex-shrink: 0;
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .crest-copy {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .crest-sign {
    font-family: 'Cormorant Garamond', Georgia, 'Times New Roman', serif;
    font-style: italic;
    font-size: 16px;
    font-weight: 600;
    color: var(--gold);
    letter-spacing: 0.04em;
    line-height: 1.15;
  }

  .crest-kicker {
    margin-bottom: 0;
  }

  .nav-num {
    font-size: 10.5px;
    font-weight: 600;
    color: var(--gold);
    opacity: 0.8;
    min-width: 18px;
    flex-shrink: 0;
  }

  .sidebar-top-mobile {
    display: none;
    align-items: center;
    justify-content: space-between;
    padding: 4px 6px 10px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 8px;
  }

  .sidebar-label {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--text-muted);
  }

  .nav-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .nav-item {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 10px;
    border-radius: 9px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-secondary);
    text-align: left;
    font-family: inherit;
    cursor: pointer;
    transition: background-color 0.14s ease, border-color 0.14s ease, color 0.14s ease;
  }

  .nav-item:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .nav-item.active {
    background: var(--accent-soft);
    border-color: var(--border-strong);
    color: var(--text-primary);
  }

  .nav-icon {
    width: 30px;
    height: 30px;
    border-radius: 8px;
    background: var(--bg-elevated);
    color: var(--accent);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .nav-icon.accent-pink {
    color: var(--pink);
  }

  .nav-icon.accent-indigo {
    color: var(--accent-2);
  }

  .nav-item.active .nav-icon {
    background: var(--accent);
    color: var(--accent-contrast);
  }

  .nav-text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .nav-title {
    font-size: 13px;
    font-weight: 600;
    line-height: 1.25;
  }

  .nav-sub {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sidebar-foot {
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .terms-btn {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    color: var(--text-secondary);
    font-family: inherit;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    text-align: left;
  }

  .terms-btn:hover {
    border-color: var(--border-strong);
    color: var(--text-primary);
  }

  .version-line {
    display: flex;
    justify-content: space-between;
    padding: 0 6px;
    font-size: 11px;
    color: var(--text-muted);
  }

  @media (max-width: 1024px) {
    .sidebar-backdrop {
      display: block;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.55);
      z-index: 48;
    }

    .cockpit-sidebar {
      position: fixed;
      top: 0;
      bottom: 0;
      left: 0;
      z-index: 49;
      transform: translateX(-100%);
      transition: transform 0.2s ease;
      box-shadow: var(--shadow-md);
    }

    .cockpit-sidebar.open {
      transform: translateX(0);
    }

    .sidebar-top-mobile {
      display: flex;
    }
  }
</style>
