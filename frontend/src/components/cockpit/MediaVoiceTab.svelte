<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '../Icon.svelte';
  import { apiFetch, clientId, speechState, taskStatus } from '../../store';
  import { reasonLabel } from '../../lib/channelStatus';

  export let targetUrl: string = '';

  let mediaStatus: any = null;
  let speechStatus: any = null;
  let statusLoading = false;

  // Video / Medya Analiz Formu
  let mediaSource = '';
  let sampleEvery = 5;
  let topK = 5;
  let mediaModes: Record<'fetch' | 'frames' | 'transcript' | 'similarity', boolean> = {
    fetch: true,
    frames: true,
    transcript: true,
    similarity: false,
  };
  let mediaBusy = false;
  let mediaError = '';
  let mediaResult: any = null;

  // Sesli Okuma ve Dinleme
  let sayText = '';
  let voiceName = '';
  let speakRate = 1.0;
  let speechBusy = false;
  let speechNotice = '';
  let speechError = '';

  let listenLang = 'tr';
  let selectedAudioFile: File | null = null;
  let listenBusy = false;
  let listenResult: any = null;
  let listenError = '';

  const MEDIA_MODE_LABELS: Record<string, string> = {
    fetch: 'Videoyu İndir / Al',
    frames: 'Video Karelerini Çıkar',
    transcript: 'Konuşmaları Yazıya Dök',
    similarity: 'Görsel Benzerlik Kontrolü',
  };

  async function refreshStatuses() {
    statusLoading = true;
    try {
      const [mRes, sRes] = await Promise.all([
        apiFetch('/api/media/status'),
        apiFetch('/api/speech/status'),
      ]);
      if (mRes.ok) mediaStatus = await mRes.json();
      if (sRes.ok) speechStatus = await sRes.json();
    } catch {
      /* sessizce geç */
    } finally {
      statusLoading = false;
    }
  }

  async function runMediaAnalyze() {
    const src = mediaSource.trim();
    if (!src || mediaBusy) return;
    const modes = (Object.keys(mediaModes) as Array<'fetch' | 'frames' | 'transcript' | 'similarity'>).filter(
      (k) => mediaModes[k]
    );
    if (modes.length === 0) {
      mediaError = 'Lütfen en az bir analiz seçeneğini işaretleyin.';
      return;
    }

    mediaBusy = true;
    mediaError = '';
    mediaResult = null;
    try {
      const res = await apiFetch('/api/media/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source: src,
          client_id: $clientId || 'default',
          modes,
          sample_every: Number(sampleEvery) || 5,
          top_k: Number(topK) || 5,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        mediaError = data?.error?.message || data?.detail || `Medya analizi başlatılamadı (${res.status}).`;
      } else {
        mediaResult = data;
      }
    } catch {
      mediaError = 'Sunucuyla bağlantı kurulamadı.';
    } finally {
      mediaBusy = false;
    }
  }

  async function speakCustomText() {
    const txt = sayText.trim();
    if (!txt || speechBusy) return;
    speechBusy = true;
    speechNotice = '';
    speechError = '';
    try {
      const res = await apiFetch('/api/speech/say', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: txt,
          voice: voiceName.trim() || undefined,
          rate: Number(speakRate) || 1.0,
          client_id: $clientId || 'default',
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        speechError = data?.error?.message || data?.detail || `Sesli okuma başarısız (${res.status}).`;
      } else {
        speechNotice = 'Metin seslendirildi.';
      }
    } catch {
      speechError = 'Ses motoruna bağlanılamadı.';
    } finally {
      speechBusy = false;
    }
  }

  async function speakCurrentReport() {
    if (speechBusy) return;
    speechBusy = true;
    speechNotice = '';
    speechError = '';
    try {
      const res = await apiFetch('/api/speech/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: $clientId || 'default',
          report: ($taskStatus as any)?.output_summary || ($taskStatus as any) || {},
          text: sayText.trim() || undefined,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        speechError = data?.error?.message || data?.detail || `Rapor seslendirilemedi (${res.status}).`;
      } else {
        speechNotice = 'Aktif analiz özeti seslendirildi.';
      }
    } catch {
      speechError = 'Ses motoruna bağlanılamadı.';
    } finally {
      speechBusy = false;
    }
  }

  async function stopSpeech() {
    speechNotice = '';
    speechError = '';
    try {
      const cid = encodeURIComponent($clientId || 'default');
      await apiFetch(`/api/speech/stop?client_id=${cid}`, { method: 'POST' });
      speechNotice = 'Sesli okuma durduruldu.';
    } catch {
      speechError = 'Durdurma isteği gönderilemedi.';
    }
  }

  function handleFileChange(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    selectedAudioFile = input?.files?.[0] || null;
  }

  async function transcribeAudio() {
    if (!selectedAudioFile || listenBusy) return;
    listenBusy = true;
    listenError = '';
    listenResult = null;
    try {
      const form = new FormData();
      form.append('file', selectedAudioFile);
      const cid = encodeURIComponent($clientId || 'default');
      const lang = encodeURIComponent(listenLang || 'tr');
      const res = await apiFetch(`/api/speech/listen?client_id=${cid}&language=${lang}`, {
        method: 'POST',
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        listenError = data?.error?.message || data?.detail || `Ses çözümlenemedi (${res.status}).`;
      } else {
        listenResult = data;
      }
    } catch {
      listenError = 'Ses dosyası gönderilemedi.';
    } finally {
      listenBusy = false;
    }
  }

  onMount(() => {
    if (!mediaSource && targetUrl && targetUrl.startsWith('http')) {
      mediaSource = targetUrl;
    }
    refreshStatuses();
  });
</script>

<div class="tab-wrap">
  <div class="section-head">
    <div>
      <h2 class="section-title">Video, Görsel ve Ses Merkezi</h2>
      <p class="section-intro">
        Videolardaki konuşmaları yazıya dökün, kareleri inceleyin veya analiz sonuçlarını bilgisayarınıza sesli okutun.
      </p>
    </div>
    <button
      type="button"
      class="btn btn-secondary btn-sm"
      on:click={refreshStatuses}
      disabled={statusLoading}
    >
      <Icon name="refresh" size={0.9} />
      {statusLoading ? 'Yenileniyor...' : 'Araç Durumunu Yenile'}
    </button>
  </div>

  {#if mediaStatus || speechStatus}
    <div class="card status-panel">
      <div class="tool-chips">
        {#if mediaStatus?.tools}
          {#each Object.entries(mediaStatus.tools) as [name, ok]}
            <span class="pill" class:pill-ok={Boolean(ok)} class:pill-warn={!ok}>
              {name}: {ok ? 'Hazır' : 'Kurulu Değil'}
            </span>
          {/each}
        {/if}
        {#if speechStatus}
          <span class="pill" class:pill-ok={speechStatus.available} class:pill-warn={!speechStatus.available}>
            Sesli Okuma: {speechStatus.available ? 'Hazır' : reasonLabel(speechStatus.reason || 'blocked')}
          </span>
        {/if}
        <span class="pill">Canlı Ses Durumu: {$speechState}</span>
      </div>
    </div>
  {/if}

  <div class="split-grid">
    <!-- SOL: Video ve Görsel Analiz -->
    <section class="card panel-card">
      <div class="panel-title-row">
        <Icon name="film" size={1.1} />
        <h3>Video ve Görsel Çözümleme</h3>
      </div>
      <p class="panel-sub">
        Bir video internet bağlantısı veya bilgisayarınızdaki medya dosya yolunu girin; sistem konuşmaları ve önemli kareleri çıkarsın.
      </p>

      <label class="field-label">
        <span>Video Bağlantısı veya Dosya Yolu</span>
        <input
          type="text"
          class="field-input"
          bind:value={mediaSource}
          placeholder="Örn: https://... veya C:\video.mp4"
        />
      </label>

      <div class="two-col">
        <label class="field-label">
          <span>Kaç Saniyede Bir Kare Alınsın?</span>
          <input type="number" class="field-input" min="1" max="120" bind:value={sampleEvery} />
        </label>
        <label class="field-label">
          <span>En Fazla Kare / Sonuç</span>
          <input type="number" class="field-input" min="1" max="50" bind:value={topK} />
        </label>
      </div>

      <div class="checks-wrap">
        {#each Object.entries(MEDIA_MODE_LABELS) as [modeKey, label]}
          <label class="check-chip" class:active={mediaModes[modeKey as keyof typeof mediaModes]}>
            <input type="checkbox" bind:checked={mediaModes[modeKey as keyof typeof mediaModes]} />
            <span>{label}</span>
          </label>
        {/each}
      </div>

      <button
        type="button"
        class="btn btn-primary"
        on:click={runMediaAnalyze}
        disabled={mediaBusy || !mediaSource.trim()}
      >
        <Icon name="play" size={0.95} />
        {mediaBusy ? 'Medya işleniyor...' : 'Medyayı İncele'}
      </button>

      {#if mediaError}
        <div class="alert-banner err">{mediaError}</div>
      {/if}

      {#if mediaResult}
        <div class="result-stack">
          <div class="summary-line">
            <strong>Toplam Bulgu:</strong>
            <span class="pill pill-ok">{mediaResult.evidence_total ?? 0} kayıt</span>
          </div>
          {#each Object.entries(mediaResult.modes || {}) as [modeKey, info]}
            {@const detail = info as any}
            <div class="sub-result">
              <div class="sub-result-head">
                <strong>{MEDIA_MODE_LABELS[modeKey] || modeKey}</strong>
                <span class="pill" class:pill-ok={detail.available} class:pill-warn={!detail.available}>
                  {detail.available ? 'Tamam' : reasonLabel(detail.denied_by || detail.reason || 'blocked')}
                </span>
              </div>
              {#if detail.notes}
                <p class="small-muted">{detail.notes}</p>
              {/if}
              {#if Array.isArray(detail.evidence) && detail.evidence.length > 0}
                <ul class="mini-list">
                  {#each detail.evidence.slice(0, 12) as item}
                    <li>{typeof item === 'string' ? item : item.text || item.summary || item.path || JSON.stringify(item)}</li>
                  {/each}
                </ul>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    </section>

    <!-- SAĞ: Sesli Okuma ve Ses Dosyası Yazıya Dökme -->
    <section class="card panel-card">
      <div class="panel-title-row">
        <Icon name="volume" size={1.1} />
        <h3>Sesli Okuma ve Ses Yazıya Dökme</h3>
      </div>
      <p class="panel-sub">
        İstediğiniz bir metni sesli dinleyin, aktif analizin özetini okutun ya da bir ses kaydını yazıya çevirin.
      </p>

      <label class="field-label">
        <span>Okunacak Metin</span>
        <textarea
          class="field-textarea"
          bind:value={sayText}
          placeholder="Buraya sesli okunmasını istediğiniz metni yazın..."
        ></textarea>
      </label>

      <div class="two-col">
        <label class="field-label">
          <span>Ses Seçimi (İsteğe Bağlı)</span>
          <input type="text" class="field-input" bind:value={voiceName} placeholder="Varsayılan ses" />
        </label>
        <label class="field-label">
          <span>Okuma Hızı</span>
          <input type="number" step="0.1" min="0.5" max="2.0" class="field-input" bind:value={speakRate} />
        </label>
      </div>

      <div class="btn-group">
        <button
          type="button"
          class="btn btn-primary"
          on:click={speakCustomText}
          disabled={speechBusy || !sayText.trim()}
        >
          <Icon name="volume" size={0.95} />
          Metni Sesli Oku
        </button>
        <button
          type="button"
          class="btn btn-secondary"
          on:click={speakCurrentReport}
          disabled={speechBusy}
        >
          <Icon name="scroll" size={0.95} />
          Aktif Raporu Oku
        </button>
        <button type="button" class="btn btn-ghost" on:click={stopSpeech}>
          <Icon name="stop" size={0.95} />
          Durdur
        </button>
      </div>

      {#if speechNotice}
        <div class="alert-banner ok">{speechNotice}</div>
      {/if}
      {#if speechError}
        <div class="alert-banner err">{speechError}</div>
      {/if}

      <div class="divider"></div>

      <div class="panel-title-row">
        <Icon name="mic" size={1.05} />
        <h4>Ses Kaydını Yazıya Çevir</h4>
      </div>

      <div class="two-col">
        <label class="field-label">
          <span>Ses Dosyası Seçin</span>
          <input type="file" accept="audio/*,video/*" class="field-input" on:change={handleFileChange} />
        </label>
        <label class="field-label">
          <span>Konuşma Dili</span>
          <select class="field-select" bind:value={listenLang}>
            <option value="tr">Türkçe</option>
            <option value="en">İngilizce</option>
            <option value="auto">Otomatik Algıla</option>
          </select>
        </label>
      </div>

      <button
        type="button"
        class="btn btn-secondary"
        on:click={transcribeAudio}
        disabled={listenBusy || !selectedAudioFile}
      >
        <Icon name="mic" size={0.95} />
        {listenBusy ? 'Ses yazıya çevriliyor...' : 'Ses Dosyasını Yazıya Çevir'}
      </button>

      {#if listenError}
        <div class="alert-banner err">{listenError}</div>
      {/if}
      {#if listenResult}
        <div class="sub-result">
          <strong>Çözümlenen Konuşma:</strong>
          <p class="transcript-box">{listenResult.text || listenResult.transcript || JSON.stringify(listenResult)}</p>
        </div>
      {/if}
    </section>
  </div>
</div>

<style>
  .tab-wrap {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .status-panel,
  .panel-card {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .tool-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .split-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
    gap: 16px;
  }

  .panel-title-row {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-primary);
  }

  .panel-title-row h3,
  .panel-title-row h4 {
    font-size: 15px;
    font-weight: 700;
  }

  .panel-sub {
    font-size: 12.5px;
    color: var(--text-muted);
    line-height: 1.45;
  }

  .two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  @media (max-width: 560px) {
    .two-col {
      grid-template-columns: 1fr;
    }
  }

  .checks-wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .check-chip {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 6px 11px;
    border-radius: 8px;
    border: 1px solid var(--border-strong);
    background: var(--bg-input);
    font-size: 12.5px;
    cursor: pointer;
  }

  .check-chip.active {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .btn-group {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .divider {
    height: 1px;
    background: var(--border);
    margin: 4px 0;
  }

  .result-stack {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .summary-line {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .sub-result {
    padding: 10px 12px;
    border-radius: 9px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .sub-result-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 13px;
  }

  .small-muted {
    font-size: 12px;
    color: var(--text-muted);
  }

  .mini-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: var(--text-secondary);
    max-height: 180px;
    overflow-y: auto;
  }

  .mini-list li {
    padding: 5px 8px;
    border-radius: 6px;
    background: var(--bg-input);
  }

  .transcript-box {
    font-size: 13px;
    color: var(--text-primary);
    white-space: pre-wrap;
    line-height: 1.5;
  }
</style>
