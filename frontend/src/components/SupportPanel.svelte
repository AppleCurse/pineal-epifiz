<script lang="ts">
  /**
   * [B0 · DESTEKLE DEVAM KOKPİTİ] Açık destek talepleri + güvenli devam.
   *
   * Kaynak: kalıcı checkpoint (`GET /api/tasks/{id}/support`) — WS yeniden
   * bağlanınca `refreshSupport` ile geri yüklenir. Gösterilen alanlar:
   * görev, talep kimliği, ENGEL (reason), İHTİYAÇ (options/next_action),
   * sonraki adım. Sunucu zaten hassas alan döndürmez (input/anahtar/çerez);
   * bu bileşen ayrıca yalnızca alanları render eder.
   *
   * Eylemler:
   *  · “Desteği uygula” → POST .../support/{sid} {action:"provide"}
   *    (çift yanıt sunucuda 409; engel kalkmadan talep kapanmaz).
   *  · “Görevi devam ettir” → POST .../resume (istemciden TaskStatus GÖNDERİLMEZ).
   */
  import { supportRequests, supportTaskId, refreshSupport, apiFetch } from '../store';

  let busySid: string | null = null;
  let resumeBusy = false;
  let notice = '';

  function shortId(sid: string | null | undefined): string {
    if (!sid) return '—';
    return sid.length > 26 ? sid.slice(0, 26) + '…' : sid;
  }

  async function provide(sid: string | undefined) {
    if (!sid || busySid) return;
    busySid = sid;
    notice = '';
    try {
      const res = await apiFetch(`/api/tasks/${encodeURIComponent($supportTaskId || '')}/support/${encodeURIComponent(sid)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'provide', note: 'kokpit' }),
      });
      if (res.status === 409) notice = 'Yanıt reddedildi: talep zaten kapalı veya koşul sağlanmadı.';
      else if (res.status === 423) notice = 'Kasa kilitli: destek engeli kaldırılmadan talep kapanamaz.';
      else if (!res.ok) notice = 'Destek yanıtı başarısız (' + res.status + ').';
      else notice = 'Destek kaydedildi.';
      await refreshSupport($supportTaskId);
    } catch {
      notice = 'Sunucuya ulaşılamadı.';
    } finally {
      busySid = null;
    }
  }

  async function resume() {
    if (resumeBusy || !$supportTaskId) return;
    resumeBusy = true;
    notice = '';
    try {
      const res = await apiFetch(`/api/tasks/${encodeURIComponent($supportTaskId)}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const body = await res.json().catch(() => ({}));
      if (res.status === 409) {
        const code = body?.error?.code || 'CONFLICT';
        notice =
          code === 'RESUME_SUPPORT_MISSING'
            ? 'Bloklayan destek talepleri açık: önce gereken desteği sağlayın.'
            : code === 'RESUME_ALREADY_RUNNING'
              ? 'Bu görev için zaten bir devam çalışması var.'
              : 'Resume reddedildi (' + code + ').';
      } else if (res.status === 423) {
        notice = 'Kasa yeniden kilitlendi: devam yetkisi yok (423).';
      } else if (res.status === 403) {
        notice = 'Bu görevin sahibi değilsiniz (403).';
      } else if (!res.ok) {
        notice = 'Resume başlatılamadı (' + res.status + ').';
      } else {
        notice = 'Görev kaldığı yerden devam ediyor.';
      }
      await refreshSupport($supportTaskId);
    } catch {
      notice = 'Sunucuya ulaşılamadı.';
    } finally {
      resumeBusy = false;
    }
  }
</script>

{#if $supportRequests.length > 0 && $supportTaskId}
  <aside class="support-panel" data-testid="support-panel" aria-label="Açık destek talepleri">
    <header>
      <strong>DESTEK TALEPLERİ</strong>
      <span class="task">görev: {$supportTaskId}</span>
    </header>

    {#each $supportRequests as req (req.support_id)}
      <article class:resolved={req.status !== 'pending'} data-testid="support-card">
        <div class="row">
          <span class="sid" title={req.support_id}>talep: {shortId(req.support_id)}</span>
          <span class="badge" class:open={req.status === 'pending'}>
            {req.status === 'pending' ? 'AÇIK' : 'KAPANDI'}
          </span>
        </div>
        <div class="field"><span>ajan:</span> {req.agent_name || '—'}</div>
        <div class="field"><span>engel:</span> {req.reason || '—'}</div>
        <div class="field"><span>ihtiyaç:</span> {(req.options || []).join(', ') || '—'}</div>
        <div class="field"><span>sonraki adım:</span> {req.next_action || '—'}</div>
        <div class="field" class:muted={req.blocks_resume === false}>
          <span>resume:</span> {req.blocks_resume ? 'bloklayıcı' : 'bilgilendirici'}
        </div>
        {#if req.status === 'pending'}
          <button
            data-testid="support-provide"
            disabled={busySid === req.support_id}
            on:click={() => provide(req.support_id)}
          >
            {busySid === req.support_id ? '…' : 'Desteği uygula'}
          </button>
        {/if}
      </article>
    {/each}

    <footer>
      <button class="resume" data-testid="support-resume" disabled={resumeBusy} on:click={resume}>
        {resumeBusy ? 'DEVAM EDİYOR…' : 'GÖREVİ DEVAM ETTİR'}
      </button>
      {#if notice}<p class="notice" data-testid="support-notice">{notice}</p>{/if}
    </footer>
  </aside>
{/if}

<style>
  .support-panel {
    position: fixed;
    right: 18px;
    bottom: 62px;
    width: min(420px, 34vw);
    max-height: min(60vh, 560px);
    overflow: auto;
    z-index: 62;
    padding: 10px 12px;
    font-family: 'JetBrains Mono', 'Courier New', monospace;
    font-size: 11px;
    color: #d9e6f2;
    background: rgba(3, 5, 10, 0.94);
    border: 1px solid rgba(212, 175, 55, 0.5);
    border-radius: 6px;
  }
  header {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    color: #d4af37;
    margin-bottom: 8px;
  }
  header .task { opacity: 0.75; overflow: hidden; text-overflow: ellipsis; }
  article {
    border: 1px solid rgba(120, 140, 170, 0.35);
    border-radius: 4px;
    padding: 8px;
    margin-bottom: 8px;
  }
  article.resolved { opacity: 0.6; }
  .row { display: flex; justify-content: space-between; gap: 6px; margin-bottom: 4px; }
  .sid { color: #8fb7e0; overflow: hidden; text-overflow: ellipsis; }
  .badge { color: #666; }
  .badge.open { color: #ffb347; font-weight: 700; }
  .field { margin: 2px 0; line-height: 1.35; word-break: break-word; }
  .field > span { color: #9ab2c8; }
  .field.muted { opacity: 0.65; }
  button {
    margin-top: 6px;
    width: 100%;
    padding: 6px 8px;
    font: inherit;
    font-weight: 700;
    color: #0b0e14;
    background: #d4af37;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }
  button:disabled { opacity: 0.55; cursor: wait; }
  button.resume { background: #57c785; margin-top: 4px; }
  footer .notice { margin-top: 6px; color: #ffb347; }
</style>
