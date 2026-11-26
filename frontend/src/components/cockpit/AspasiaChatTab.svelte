<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '../Icon.svelte';
  import { apiFetch, clientId, formatApiError, vaultLocked } from '../../store';

  export let chatMessages: Array<{ ts: string; sender: string; text: string }> = [];
  export let inputMessage: string = '';
  export let isSending: boolean = false;
  export let sendAspasiaMessage: () => void = () => {};
  export let selectAgent: (id: string) => void = () => {};
  export let onOpenSettings: () => void = () => {};
  export let onToggleVault: () => void = () => {};

  let mode: 'chat' | 'coach' | 'sessions' = 'chat';
  let aspasiaState: any = null;
  let stateLoading = false;

  let coachInput = '';
  let coachLang = 'tr';
  let coachBusy = false;
  let coachMessages: Array<{ sender: string; text: string; meta?: string }> = [];

  let sessionsLoading = false;
  let sessionsData: any = null;

  const STARTERS = [
    'Aktif görevi sade Türkçe ile özetle',
    'İlişki grafını çiz',
    'Hafıza kayıtlarını kontrol et',
    'Bu hedefe ilk adımı nasıl atmalıyız?',
  ];

  async function loadAspasiaState() {
    stateLoading = true;
    try {
      const cid = encodeURIComponent($clientId || 'default');
      const res = await apiFetch(`/api/aspasia/state?client_id=${cid}`);
      if (res.ok) aspasiaState = await res.json();
    } catch {
      /* sessizce geç */
    } finally {
      stateLoading = false;
    }
  }

  async function loadSessions() {
    sessionsLoading = true;
    try {
      const res = await apiFetch('/api/dialogue/sessions');
      if (res.ok) sessionsData = await res.json();
    } catch {
      /* sessizce geç */
    } finally {
      sessionsLoading = false;
    }
  }

  async function sendMobileCoach() {
    const msg = coachInput.trim();
    if (!msg || coachBusy) return;
    coachInput = '';
    coachBusy = true;
    coachMessages = [...coachMessages, { sender: 'Siz', text: msg }];
    try {
      const res = await apiFetch('/api/mobile/coach', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          user_message: msg,
          language: coachLang,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(formatApiError(data, `HTTP ${res.status}`));
      }
      if (data.available === false || data.error) {
        coachMessages = [
          ...coachMessages,
          {
            sender: 'Koç (Uyarı)',
            text: formatApiError(data, 'Model şu an yanıt veremedi.'),
            meta: data?.error?.reason || '',
          },
        ];
      } else {
        coachMessages = [
          ...coachMessages,
          {
            sender: 'Koç',
            text: data.answer || 'Yanıt boş.',
            meta: data.model ? `Model: ${data.model}` : '',
          },
        ];
      }
    } catch (e: any) {
      coachMessages = [...coachMessages, { sender: 'Koç (Hata)', text: e?.message || 'Bağlantı hatası' }];
    } finally {
      coachBusy = false;
    }
  }

  onMount(() => {
    selectAgent('aspasia');
    void loadAspasiaState();
  });
</script>

<div class="aspasia-page">
  <div class="section-head">
    <div>
      <h2 class="section-title">Aspasia ile Sohbet &amp; Danışman</h2>
      <p class="section-intro">
        Analiz sonuçları hakkında normal Türkçe soru sorun; graf, hafıza veya şirket sorgularını doğrudan konuşarak yaptırın.
      </p>
    </div>

    <div class="head-actions">
      {#if aspasiaState?.budget}
        <span class="pill pill-indigo">
          Harcama: ${Number(aspasiaState.budget.spend_usd || 0).toFixed(3)} / ${Number(aspasiaState.budget.cap_usd || 0).toFixed(2)}
        </span>
      {/if}
      <button type="button" class="btn btn-ghost btn-sm" on:click={loadAspasiaState} disabled={stateLoading}>
        <Icon name="refresh" size={0.85} />
        <span>Durum</span>
      </button>
    </div>
  </div>

  {#if $vaultLocked}
    <div class="alert-banner warn">
      <Icon name="lock" size={0.95} />
      <span>
        Kasa şu an kilitli olduğu için Aspasia dış yapay zekâ modellerine bağlanamaz.
        <button type="button" class="inline-link" on:click={onToggleVault}>Kasayı Aç</button>
        veya
        <button type="button" class="inline-link" on:click={onOpenSettings}>Ayarlardan Anahtar Ekle</button>.
      </span>
    </div>
  {/if}

  <div class="mode-tabs">
    <button type="button" class="btn btn-sm" class:btn-primary={mode === 'chat'} class:btn-secondary={mode !== 'chat'} on:click={() => (mode = 'chat')}>
      <Icon name="message" size={0.85} />
      <span>Aspasia Ana Sohbet</span>
    </button>
    <button type="button" class="btn btn-sm" class:btn-primary={mode === 'coach'} class:btn-secondary={mode !== 'coach'} on:click={() => (mode = 'coach')}>
      <Icon name="phone" size={0.85} />
      <span>Hızlı İletişim Koçu</span>
    </button>
    <button
      type="button"
      class="btn btn-sm"
      class:btn-primary={mode === 'sessions'}
      class:btn-secondary={mode !== 'sessions'}
      on:click={() => {
        mode = 'sessions';
        void loadSessions();
      }}
    >
      <Icon name="scroll" size={0.85} />
      <span>Diyalog Oturumları</span>
    </button>
  </div>

  {#if mode === 'chat'}
    <div class="card chat-shell">
      <div class="starter-row">
        {#each STARTERS as s}
          <button
            type="button"
            class="chip-btn"
            on:click={() => {
              selectAgent('aspasia');
              inputMessage = s;
            }}
          >
            {s}
          </button>
        {/each}
      </div>

      <div class="full-feed">
        {#each chatMessages as msg}
          <div class="msg-row" class:user={msg.sender === 'SÖZ'}>
            <div class="msg-box" class:user={msg.sender === 'SÖZ'} class:lilith={msg.sender === 'Lilith'}>
              <div class="msg-head">
                <strong>{msg.sender === 'SÖZ' ? 'Siz' : msg.sender}</strong>
                <span>{msg.ts}</span>
              </div>
              <div class="msg-body">{msg.text}</div>
            </div>
          </div>
        {/each}
      </div>

      <div class="composer-row">
        <input
          type="text"
          class="field-input"
          bind:value={inputMessage}
          placeholder="Aspasia'ya ne sormak veya ne yaptırmak istersiniz?"
          disabled={isSending}
          on:keydown={(e) => {
            if (e.key === 'Enter') {
              selectAgent('aspasia');
              sendAspasiaMessage();
            }
          }}
        />
        <button
          type="button"
          class="btn btn-primary"
          on:click={() => {
            selectAgent('aspasia');
            sendAspasiaMessage();
          }}
          disabled={isSending || !inputMessage.trim()}
        >
          <Icon name={isSending ? 'refresh' : 'send'} size={0.9} />
          <span>{isSending ? 'Yazıyor...' : 'Gönder'}</span>
        </button>
      </div>
    </div>
  {:else if mode === 'coach'}
    <div class="card chat-shell">
      <p class="section-intro">Kısa, pratik iletişim tavsiyeleri almak için Mobil Koç hattını kullanın.</p>
      <div class="full-feed">
        {#each coachMessages as cm}
          <div class="msg-row" class:user={cm.sender === 'Siz'}>
            <div class="msg-box" class:user={cm.sender === 'Siz'}>
              <div class="msg-head">
                <strong>{cm.sender}</strong>
                {#if cm.meta}<span class="code-mono">{cm.meta}</span>{/if}
              </div>
              <div class="msg-body">{cm.text}</div>
            </div>
          </div>
        {:else}
          <div class="empty-state">Koça bir durum anlatın; hemen yanıt önersin.</div>
        {/each}
      </div>

      <div class="composer-row">
        <select class="field-select" style="width: 110px;" bind:value={coachLang}>
          <option value="tr">Türkçe</option>
          <option value="en">English</option>
        </select>
        <input
          type="text"
          class="field-input"
          bind:value={coachInput}
          placeholder="Örn: Karşı taraf mesajıma geç döndü, ne yazmalıyım?"
          disabled={coachBusy}
          on:keydown={(e) => {
            if (e.key === 'Enter') sendMobileCoach();
          }}
        />
        <button type="button" class="btn btn-primary" on:click={sendMobileCoach} disabled={coachBusy || !coachInput.trim()}>
          <Icon name="send" size={0.9} />
          <span>{coachBusy ? 'Bekleyin...' : 'Koça Sor'}</span>
        </button>
      </div>
    </div>
  {:else}
    <div class="card">
      <div class="section-head">
        <h3>Açık Diyalog Oturumları</h3>
        <button type="button" class="btn btn-secondary btn-sm" on:click={loadSessions} disabled={sessionsLoading}>
          Yenile
        </button>
      </div>
      {#if sessionsLoading}
        <div class="empty-state">Yükleniyor...</div>
      {:else if !sessionsData || !(sessionsData.sessions || []).length}
        <div class="empty-state">Kayıtlı aktif diyalog oturumu bulunmuyor.</div>
      {:else}
        <pre class="code-mono" style="font-size: 12px; white-space: pre-wrap;">{JSON.stringify(sessionsData, null, 2)}</pre>
      {/if}
    </div>
  {/if}
</div>

<style>
  .aspasia-page {
    display: flex;
    flex-direction: column;
    gap: 14px;
    height: 100%;
  }

  .head-actions,
  .mode-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }

  .inline-link {
    background: none;
    border: none;
    color: var(--accent);
    font: inherit;
    font-weight: 700;
    text-decoration: underline;
    cursor: pointer;
    margin: 0 3px;
  }

  .chat-shell {
    display: flex;
    flex-direction: column;
    gap: 12px;
    flex: 1;
    min-height: 460px;
  }

  .starter-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .chip-btn {
    padding: 5px 11px;
    border-radius: 999px;
    border: 1px solid var(--border-strong);
    background: var(--bg-elevated);
    color: var(--text-secondary);
    font-family: inherit;
    font-size: 12px;
    cursor: pointer;
  }

  .chip-btn:hover {
    border-color: var(--accent);
    color: var(--text-primary);
  }

  .full-feed {
    flex: 1;
    min-height: 280px;
    max-height: 55vh;
    overflow-y: auto;
    padding: 12px;
    border-radius: 10px;
    background: var(--bg-input);
    border: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .msg-row {
    display: flex;
    justify-content: flex-start;
  }

  .msg-row.user {
    justify-content: flex-end;
  }

  .msg-box {
    max-width: 82%;
    padding: 10px 13px;
    border-radius: 11px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
  }

  .msg-box.user {
    background: var(--accent-soft);
    border-color: rgba(16, 185, 129, 0.4);
  }

  .msg-box.lilith {
    background: var(--pink-soft);
    border-color: rgba(236, 72, 153, 0.4);
  }

  .msg-head {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    font-size: 11px;
    color: var(--text-muted);
    margin-bottom: 4px;
  }

  .msg-body {
    font-size: 13.5px;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--text-primary);
  }

  .composer-row {
    display: flex;
    gap: 8px;
  }
</style>
