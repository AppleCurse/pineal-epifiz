<script lang="ts">
  import Icon from '../Icon.svelte';
  import {
    powerEngaged,
    armEngaged,
    recordEngaged,
    isProcessing,
    vaultLocked,
  } from '../../store';
  import { uplinkState, health, apiAuthRequired } from '../../lib/telemetry';
  import { playClick } from '../../lib/consoleAudio';
  import { theme, toggleTheme, sidebarOpen } from '../../lib/theme';

  export let missionElapsedStr: string = '00:00';
  export let vaultKnown: boolean = false;
  export let vaultBusy: boolean = false;
  export let vaultError: string = '';
  export let onEmergencyStop: () => void = () => {};
  export let onToggleVault: () => void = () => {};
  export let onOpenSettings: () => void = () => {};
  export let onOpenHistory: () => void = () => {};
  export let onOpenDemo: () => void = () => {};

  $: systemTone =
    $uplinkState !== 'ONLINE' || $health?.status === 'unreachable'
      ? 'danger'
      : $health?.status === 'ready'
        ? 'ok'
        : 'warn';

  $: systemLabel =
    $uplinkState !== 'ONLINE' || $health?.status === 'unreachable'
      ? 'Bağlantı Yok'
      : $health?.status === 'ready'
        ? 'Sistem Hazır'
        : 'Eksik Parça Var';

  $: vaultButtonText = $apiAuthRequired
    ? 'Erişim Anahtarı Gir'
    : !vaultKnown
      ? 'Kasa Durumu'
      : $vaultLocked
        ? 'Kasa Kilitli'
        : 'Kasa Açık';
</script>

<header class="top-header">
  <div class="header-left">
    <button
      type="button"
      class="btn btn-ghost btn-sm mobile-menu-btn"
      on:click={() => sidebarOpen.update((v) => !v)}
      aria-label="Menüyü aç veya kapat"
    >
      <Icon name="menu" size={1.1} />
    </button>

    <div class="brand-wrap">
      <div class="brand-name">
        <span class="brand-dot" class:processing={$isProcessing}></span>
        <span>PINEAL EPİFİZ</span>
      </div>
      <span
        class="pill"
        class:pill-ok={systemTone === 'ok'}
        class:pill-warn={systemTone === 'warn'}
        class:pill-danger={systemTone === 'danger'}
        title="Sunucu ve araçların canlı bağlantı durumu"
      >
        {systemLabel}
      </span>
      {#if $isProcessing || missionElapsedStr !== '00:00'}
        <span class="pill pill-indigo code-mono" title="Aktif işlem süresi">
          <Icon name="clock" size={0.85} />
          {missionElapsedStr}
        </span>
      {/if}
    </div>
  </div>

  <div class="header-center" role="group" aria-label="Canlı kontrol anahtarları">
    <button
      type="button"
      class="switch-pill"
      class:on={$powerEngaged}
      aria-pressed={$powerEngaged}
      on:click={() => {
        playClick(520, 35);
        powerEngaged.update((v) => !v);
      }}
      title="Sunucuyla canlı akış bağlantısını açar veya kapatır"
    >
      <span class="dot"></span>
      <span>GÜÇ</span>
    </button>

    <button
      type="button"
      class="switch-pill"
      class:on={$armEngaged}
      aria-pressed={$armEngaged}
      on:click={() => {
        playClick(620, 40);
        armEngaged.update((v) => !v);
      }}
      title="Hazır göstergesi — işaretlemeden de analiz başlatabilirsiniz"
    >
      <span class="dot"></span>
      <span>HAZIR</span>
    </button>

    <button
      type="button"
      class="switch-pill"
      class:on={$recordEngaged}
      aria-pressed={$recordEngaged}
      on:click={() => {
        playClick(480, 35);
        recordEngaged.update((v) => !v);
      }}
      title="Alt kısımdaki canlı kayıt günlüğünü tutar"
    >
      <span class="dot"></span>
      <span>KAYIT</span>
    </button>

    <button
      type="button"
      class="btn btn-danger btn-sm"
      on:click={onEmergencyStop}
      title="Çalışan incelemeyi hemen durdurur"
    >
      <Icon name="stop" size={0.9} />
      <span>ACİL DUR</span>
    </button>
  </div>

  <div class="header-right">
    <button
      type="button"
      class="btn btn-ghost btn-sm"
      data-testid="theme-toggle-btn"
      on:click={toggleTheme}
      title={$theme === 'dark' ? 'Açık (beyaz) temaya geç' : 'Koyu temaya geç'}
    >
      <Icon name={$theme === 'dark' ? 'sun' : 'moon'} size={0.95} />
      <span class="hide-sm">{$theme === 'dark' ? 'Açık Tema' : 'Koyu Tema'}</span>
    </button>

    <button
      type="button"
      class="btn btn-sm vault-btn"
      class:btn-primary={vaultKnown && !$vaultLocked && !$apiAuthRequired}
      class:btn-secondary={$apiAuthRequired || !vaultKnown || $vaultLocked}
      on:click={onToggleVault}
      disabled={vaultBusy}
      title={$apiAuthRequired
        ? 'Önce erişim anahtarı girmek için Ayarları açar'
        : $vaultLocked
          ? 'Kasayı açar (anahtar yoksa Ayarlardan ekleyebilirsiniz)'
          : 'Kasayı kilitler — dış ağa çıkış durur'}
    >
      <Icon name={vaultKnown && !$vaultLocked && !$apiAuthRequired ? 'unlock' : 'lock'} size={0.9} />
      <span>{vaultButtonText}</span>
    </button>

    <button
      type="button"
      class="btn btn-ghost btn-sm"
      data-testid="open-demo-btn"
      on:click={onOpenDemo}
      title="Anahtar gerektirmeyen 2 örnek raporu inceleyin"
    >
      <Icon name="file" size={0.9} />
      <span class="hide-md">Örnekler</span>
    </button>

    <button
      type="button"
      class="btn btn-ghost btn-sm"
      data-testid="open-history-btn"
      on:click={onOpenHistory}
      title="Önceki görevler ve Rapor Fabrikası"
    >
      <Icon name="scroll" size={0.9} />
      <span class="hide-md">Geçmiş &amp; Raporlar</span>
    </button>

    <button
      type="button"
      class="btn btn-secondary btn-sm"
      data-testid="open-settings-btn"
      on:click={onOpenSettings}
      title="Yapay zekâ anahtarları, arama anahtarları ve model listesi"
    >
      <Icon name="gear" size={0.9} />
      <span>Ayarlar</span>
    </button>
  </div>
</header>

{#if vaultError}
  <div class="vault-error-strip" role="alert">
    <Icon name="warning" size={0.9} />
    <span>{vaultError}</span>
  </div>
{/if}

<style>
  .top-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px 14px;
    padding: 10px 18px;
    background: var(--bg-sidebar);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    z-index: 30;
  }

  .header-left,
  .header-center,
  .header-right {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .mobile-menu-btn {
    display: none;
    padding: 6px 8px;
  }

  @media (max-width: 1024px) {
    .mobile-menu-btn {
      display: inline-flex;
    }
  }

  .brand-wrap {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .brand-name {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: var(--text-primary);
    white-space: nowrap;
  }

  .brand-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .brand-dot.processing {
    background: var(--warning);
    box-shadow: 0 0 0 3px var(--warning-soft);
    animation: pulse-dot 1.2s infinite ease-in-out;
  }

  @keyframes pulse-dot {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.25); opacity: 0.7; }
  }

  .switch-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 10px;
    border-radius: 8px;
    border: 1px solid var(--border-strong);
    background: var(--bg-elevated);
    color: var(--text-muted);
    font-family: inherit;
    font-size: 11px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .switch-pill .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-muted);
  }

  .switch-pill.on {
    border-color: rgba(16, 185, 129, 0.45);
    background: var(--accent-soft);
    color: var(--text-primary);
  }

  .switch-pill.on .dot {
    background: var(--accent);
  }

  .vault-error-strip {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 18px;
    background: var(--danger-soft);
    border-bottom: 1px solid rgba(239, 68, 68, 0.35);
    color: var(--text-primary);
    font-size: 12.5px;
  }

  @media (max-width: 1260px) {
    .hide-md {
      display: none;
    }
  }

  @media (max-width: 720px) {
    .hide-sm {
      display: none;
    }
    .top-header {
      padding: 8px 12px;
    }
  }
</style>
