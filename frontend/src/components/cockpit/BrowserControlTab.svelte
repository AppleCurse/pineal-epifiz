<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import Icon from '../Icon.svelte';
  import { apiFetch, clientId, formatApiError } from '../../store';

  export let targetUrl: string = '';

  let urlInput = 'https://www.instagram.com/';
  let typeText = '';
  let keyInput = 'Enter';
  let browserState: any = null;
  let shotObjectUrl = '';
  let busy = false;
  let notice = '';
  let errorMsg = '';

  const QUICK_LINKS = [
    { label: 'Instagram Giriş', url: 'https://www.instagram.com/accounts/login/' },
    { label: 'Google Arama', url: 'https://www.google.com/' },
    { label: 'X (Twitter)', url: 'https://x.com/' },
  ];

  function revokeOldShot() {
    if (shotObjectUrl) {
      URL.revokeObjectURL(shotObjectUrl);
      shotObjectUrl = '';
    }
  }

  async function refreshStateAndShot() {
    const cid = encodeURIComponent($clientId || 'default');
    try {
      const stateRes = await apiFetch(`/api/browser/state?client_id=${cid}`);
      if (stateRes.ok) {
        browserState = await stateRes.json();
      }
      if (browserState?.open) {
        const shotRes = await apiFetch(`/api/browser/shot?client_id=${cid}&_=${Date.now()}`);
        if (shotRes.ok) {
          const blob = await shotRes.blob();
          revokeOldShot();
          shotObjectUrl = URL.createObjectURL(blob);
        }
      } else {
        revokeOldShot();
      }
    } catch {
      /* sessizce geç */
    }
  }

  async function openPage(customUrl?: string) {
    const target = (customUrl || urlInput).trim();
    if (!target || busy) return;
    urlInput = target;
    busy = true;
    errorMsg = '';
    notice = '';
    try {
      const res = await apiFetch('/api/browser/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          url: target,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        errorMsg = formatApiError(data, `Tarayıcı açılamadı (${res.status}).`);
      } else {
        notice = 'Sayfa açıldı. Aşağıdaki ekrandan kontrol edebilirsiniz.';
        await refreshStateAndShot();
      }
    } catch {
      errorMsg = 'Tarayıcı sunucusuna ulaşılamadı.';
    } finally {
      busy = false;
    }
  }

  async function handleImageClick(event: MouseEvent) {
    if (busy || !browserState?.open) return;
    const img = event.currentTarget as HTMLImageElement;
    const rect = img.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    const naturalW = img.naturalWidth || rect.width;
    const naturalH = img.naturalHeight || rect.height;
    const x = Math.round(((event.clientX - rect.left) / rect.width) * naturalW);
    const y = Math.round(((event.clientY - rect.top) / rect.height) * naturalH);

    busy = true;
    errorMsg = '';
    try {
      const res = await apiFetch('/api/browser/click', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: $clientId || 'default', x, y }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        errorMsg = formatApiError(d, `Tıklama uygulanamadı (${res.status}).`);
      }
      await refreshStateAndShot();
    } catch {
      errorMsg = 'Tıklama gönderilemedi.';
    } finally {
      busy = false;
    }
  }

  async function sendTypedText() {
    if (!typeText || busy) return;
    busy = true;
    errorMsg = '';
    try {
      const res = await apiFetch('/api/browser/type', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: $clientId || 'default', text: typeText }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        errorMsg = formatApiError(d, `Yazı gönderilemedi (${res.status}).`);
      } else {
        typeText = '';
      }
      await refreshStateAndShot();
    } catch {
      errorMsg = 'Yazı gönderilemedi.';
    } finally {
      busy = false;
    }
  }

  async function sendKey(key?: string) {
    const k = key || keyInput;
    if (!k || busy) return;
    busy = true;
    errorMsg = '';
    try {
      const res = await apiFetch('/api/browser/press', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: $clientId || 'default', key: k }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        errorMsg = formatApiError(d, `Tuş gönderilemedi (${res.status}).`);
      }
      await refreshStateAndShot();
    } catch {
      errorMsg = 'Tuş gönderilemedi.';
    } finally {
      busy = false;
    }
  }

  async function runSimpleAction(endpoint: 'back' | 'save' | 'close', okText: string) {
    if (busy) return;
    busy = true;
    errorMsg = '';
    notice = '';
    try {
      const res = await apiFetch(`/api/browser/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: $clientId || 'default' }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) {
        errorMsg = formatApiError(d, `İşlem başarısız (${res.status}).`);
      } else {
        notice = okText;
      }
      await refreshStateAndShot();
    } catch {
      errorMsg = 'İşlem gerçekleştirilemedi.';
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    if (targetUrl && targetUrl.startsWith('http')) {
      urlInput = targetUrl;
    }
    refreshStateAndShot();
  });

  onDestroy(() => {
    revokeOldShot();
  });
</script>

<div class="tab-wrap">
  <div class="section-head">
    <div>
      <h2 class="section-title">Canlı Tarayıcı ve Oturum Girişi</h2>
      <p class="section-intro">
        Instagram veya başka bir site giriş ekranı istediğinde buradan kendi hesabınızla güvenle giriş yapıp oturumu kaydedebilirsiniz.
      </p>
    </div>
    <div class="head-actions">
      <button type="button" class="btn btn-secondary btn-sm" on:click={refreshStateAndShot} disabled={busy}>
        <Icon name="refresh" size={0.9} />
        Ekranı Yenile
      </button>
    </div>
  </div>

  <div class="card guide-banner">
    <Icon name="help" size={1} />
    <div>
      <strong>Nasıl kullanılır?</strong> Önce gitmek istediğiniz siteyi açın. Aşağıdaki görüntüde tıklamak istediğiniz kutuya basın, ardından "Yazı Gönder" kutusundan bilginizi yollayın. İşiniz bitince <strong>Oturumu Kaydet</strong> düğmesine tıklayın.
    </div>
  </div>

  <div class="card controls-card">
    <div class="quick-links">
      <span class="quick-label">Hızlı Sayfalar:</span>
      {#each QUICK_LINKS as item}
        <button type="button" class="btn btn-ghost btn-sm" on:click={() => openPage(item.url)} disabled={busy}>
          {item.label}
        </button>
      {/each}
    </div>

    <div class="url-bar">
      <input
        type="text"
        class="field-input"
        bind:value={urlInput}
        placeholder="https://www.instagram.com/"
        on:keydown={(e) => e.key === 'Enter' && openPage()}
      />
      <button type="button" class="btn btn-primary" on:click={() => openPage()} disabled={busy || !urlInput.trim()}>
        <Icon name="globe" size={0.95} />
        Sayfayı Aç
      </button>
    </div>

    <div class="action-bar">
      <div class="type-box">
        <input
          type="text"
          class="field-input"
          bind:value={typeText}
          placeholder="Seçili kutuya yazılacak metin..."
          on:keydown={(e) => e.key === 'Enter' && sendTypedText()}
        />
        <button type="button" class="btn btn-secondary btn-sm" on:click={sendTypedText} disabled={busy || !typeText}>
          Yazıyı Gönder
        </button>
      </div>

      <div class="key-box">
        <select class="field-select key-select" bind:value={keyInput}>
          <option value="Enter">Enter (Onayla)</option>
          <option value="Tab">Tab (Sonraki Kutu)</option>
          <option value="Backspace">Geri Sil</option>
          <option value="Escape">Vazgeç (ESC)</option>
        </select>
        <button type="button" class="btn btn-secondary btn-sm" on:click={() => sendKey()} disabled={busy}>
          Tuşa Bas
        </button>
      </div>
    </div>

    <div class="session-actions">
      <button
        type="button"
        class="btn btn-ghost btn-sm"
        on:click={() => runSimpleAction('back', 'Bir önceki sayfaya dönüldü.')}
        disabled={busy || !browserState?.open}
      >
        Geri Git
      </button>
      <button
        type="button"
        class="btn btn-primary btn-sm"
        on:click={() => runSimpleAction('save', 'Giriş oturumunuz güvenle kaydedildi.')}
        disabled={busy || !browserState?.open}
      >
        <Icon name="check" size={0.9} />
        Oturumu Kaydet
      </button>
      <button
        type="button"
        class="btn btn-danger btn-sm"
        on:click={() => runSimpleAction('close', 'Tarayıcı oturumu kapatıldı.')}
        disabled={busy || !browserState?.open}
      >
        Tarayıcıyı Kapat
      </button>

      {#if browserState}
        <span class="pill" class:pill-ok={browserState.open}>
          {browserState.open ? `Açık: ${browserState.title || browserState.url || 'Sayfa yüklü'}` : 'Tarayıcı Kapalı'}
        </span>
      {/if}
    </div>

    {#if notice}
      <div class="alert-banner ok">{notice}</div>
    {/if}
    {#if errorMsg}
      <div class="alert-banner err">{errorMsg}</div>
    {/if}
  </div>

  <div class="card viewport-card">
    {#if shotObjectUrl}
      <div class="viewport-hint">Görsel üzerine tıklayarak sayfayla doğrudan etkileşime geçebilirsiniz.</div>
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
      <img
        src={shotObjectUrl}
        alt="Canlı tarayıcı görüntüsü"
        class="browser-shot"
        on:click={handleImageClick}
      />
    {:else}
      <div class="empty-state">
        Tarayıcı şu an kapalı. Başlamak için yukarıdan "Instagram Giriş" gibi bir hızlı sayfaya veya "Sayfayı Aç" düğmesine tıklayın.
      </div>
    {/if}
  </div>
</div>

<style>
  .tab-wrap {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .guide-banner {
    padding: 12px 14px;
    display: flex;
    align-items: flex-start;
    gap: 10px;
    font-size: 13px;
    color: var(--text-secondary);
    background: var(--accent-soft);
    border-color: rgba(16, 185, 129, 0.3);
  }

  .controls-card,
  .viewport-card {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .quick-links {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }

  .quick-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
  }

  .url-bar {
    display: flex;
    gap: 10px;
  }

  .action-bar {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
  }

  @media (max-width: 720px) {
    .action-bar {
      grid-template-columns: 1fr;
    }
  }

  .type-box,
  .key-box {
    display: flex;
    gap: 8px;
  }

  .key-select {
    width: auto;
    min-width: 150px;
  }

  .session-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }

  .viewport-hint {
    font-size: 12px;
    color: var(--text-muted);
  }

  .browser-shot {
    width: 100%;
    max-width: 960px;
    border-radius: 10px;
    border: 1px solid var(--border-strong);
    cursor: crosshair;
    background: #000;
  }
</style>
