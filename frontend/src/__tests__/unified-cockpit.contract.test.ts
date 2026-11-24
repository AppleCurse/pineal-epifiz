import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import UnifiedPinealCockpit from '../components/UnifiedPinealCockpit.svelte';
import { armEngaged, clientId, isProcessing, powerEngaged, recordEngaged, taskStatus } from '../store';

type Call = { path: string; method: string; body?: any };

function jsonResponse(body: any, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function installFetch(route: (path: string, init: RequestInit) => Response | undefined): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = vi.fn(async (input: any, init: RequestInit = {}) => {
    const url = new URL(String(input), 'http://localhost');
    const path = url.pathname + url.search;
    const method = String(init.method || 'GET').toUpperCase();
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : undefined;
    calls.push({ path, method, body });
    return route(path, init) ?? jsonResponse({});
  }) as unknown as typeof fetch;
  return calls;
}

/**
 * [AUDIT 2026-11-17 · EK H.2-E] 18+ REŞİT beyan kutusu.
 *
 * `0acc47f4` KAZIYI BAŞLAT düğmesine `!isAdultDeclared` kilidi ekledi
 * (Tüzük §2 kırmızı çizgisi) ama sözleşme testleri bu kapıyı bilmiyordu:
 * iki test düğmeye beyan olmadan basıyor, `/api/initiate` hiç çağrılmadığı
 * için "Görev kabul edildi" / "Ön-kontrol engeli" metinleri ekrana
 * gelmiyordu. Kapı **kasıtlı** olduğundan testler yeni sözleşmeyi anlatır;
 * susturulmaz. Aşağıda ayrıca kapının kendisini doğrulayan bir test var.
 */
async function declareAdult(container: HTMLElement): Promise<void> {
  const box = container.querySelector<HTMLInputElement>(
    '.adult-consent-badge input[type="checkbox"]'
  );
  if (!box) throw new Error('18+ REŞİT beyan kutusu bulunamadı (kapı kaldırılmış olabilir)');
  await fireEvent.click(box);
}

beforeEach(() => {
  clientId.set('test_room');
  powerEngaged.set(true);
  armEngaged.set(false);
  recordEngaged.set(true);
  isProcessing.set(false);
  taskStatus.set(null);
});

describe('UnifiedPinealCockpit controls and honesty', () => {
  it('renders GÜÇ, HAZIR, KAYIT switches and toggles stores', async () => {
    installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: true });
      return undefined;
    });

    render(UnifiedPinealCockpit);
    const armBtn = screen.getByRole('button', { name: /HAZIR/i });
    const pwrBtn = screen.getByRole('button', { name: /GÜÇ/i });
    const recBtn = screen.getByRole('button', { name: /KAYIT/i });

    expect(get(armEngaged)).toBe(false);
    await fireEvent.click(armBtn);
    expect(get(armEngaged)).toBe(true);

    await fireEvent.click(pwrBtn);
    expect(get(powerEngaged)).toBe(false);

    await fireEvent.click(recBtn);
    expect(get(recordEngaged)).toBe(false);
  });

  it('ACİL DUR calls /api/tasks/{id}/halt and disarms HAZIR', async () => {
    const calls = installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: true });
      if (path === '/api/tasks/op_test_123/halt') return jsonResponse({ status: 'halted' });
      return undefined;
    });

    armEngaged.set(true);
    isProcessing.set(true);
    taskStatus.set({ task_id: 'op_test_123', status: 'processing' });

    render(UnifiedPinealCockpit);
    const stopBtn = screen.getByRole('button', { name: /ACİL DUR/i });
    await fireEvent.click(stopBtn);

    await waitFor(() => {
      expect(calls.some((c) => c.method === 'POST' && c.path === '/api/tasks/op_test_123/halt')).toBe(true);
    });
    expect(get(armEngaged)).toBe(false);
    expect(get(isProcessing)).toBe(false);
  });

  it('does not render fabricated 847 Hz or 94% while processing', () => {
    installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: true });
      return undefined;
    });

    isProcessing.set(true);
    const { container } = render(UnifiedPinealCockpit);
    expect(container.textContent).not.toContain('847 Hz');
    expect(container.textContent).not.toContain('94%');
  });

  it('does not mistake empty or status-only summaries for evidence', () => {
    installFetch(() => undefined);
    taskStatus.set({ follower_audit: {}, timing_forensics: { hour_distribution: {} }, depth_report: { status: 'failed' } });
    const { container } = render(UnifiedPinealCockpit);
    expect(container.querySelectorAll('.pillar-column.has-data')).toHaveLength(0);
    expect(container.textContent).not.toContain('KANIT VAR');
    expect(container.textContent).toContain('tek başına doğrulanmış kanıt değildir');
  });

  it('labels actual summary values without claiming verified evidence', () => {
    installFetch(() => undefined);
    taskStatus.set({ follower_audit: { avg_followers: 0 }, osint_footprint: { phone_exposed: false } });
    const { container } = render(UnifiedPinealCockpit);
    expect(container.querySelectorAll('.pillar-column.has-data')).toHaveLength(2);
    expect(container.querySelector('.follower-pillar')?.textContent).toContain('Ortalama: 0');
    expect(container.querySelector('.osint-pillar')?.textContent).toContain('Telefon: Kapalı');
    expect(container.textContent).not.toContain('KANIT VAR');
  });

  it('clears previous results when a new analysis is accepted', async () => {
    installFetch((path) => path === '/api/initiate' ? jsonResponse({ task_id: 'new-task' }) : undefined);
    armEngaged.set(true);
    taskStatus.set({ task_id: 'old-task', follower_audit: { bot_risk: 75 }, evidence_chain: [{ old: true }], channel_status: [{ channel: 'old', status: 'failed' }] });
    const { container } = render(UnifiedPinealCockpit);
    await declareAdult(container);
    await fireEvent.input(screen.getByPlaceholderText(/Hedef Profil URL/i), { target: { value: '@example' } });
    await fireEvent.click(screen.getByRole('button', { name: /ANALİZİ BAŞLAT/i }));
    await waitFor(() => expect(get(taskStatus)?.task_id).toBe('new-task'));
    expect(get(taskStatus).follower_audit).toBeUndefined();
    expect(get(taskStatus).evidence_chain).toBeUndefined();
    expect(get(taskStatus).channel_status).toBeUndefined();
  });

  it('does not overwrite a result that arrives before the start response', async () => {
    installFetch((path) => {
      if (path === '/api/initiate') {
        taskStatus.set({ task_id: 'new-task', status: 'completed', evidence_chain: [{ agent: 'early-result' }] });
        return jsonResponse({ task_id: 'new-task' });
      }
      return undefined;
    });
    armEngaged.set(true);
    const { container } = render(UnifiedPinealCockpit);
    await declareAdult(container);
    await fireEvent.input(screen.getByPlaceholderText(/Hedef Profil URL/i), { target: { value: '@example' } });
    await fireEvent.click(screen.getByRole('button', { name: /ANALİZİ BAŞLAT/i }));
    await waitFor(() => expect(get(taskStatus)?.status).toBe('completed'));
    expect(get(taskStatus).evidence_chain[0].agent).toBe('early-result');
  });

  it('renders phone OSINT dossier card when phone probe returns metadata', async () => {
    const calls = installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path === '/api/commander/phone-probe') {
        return jsonResponse({
          phone_input: '+905551112233',
          metadata: {
            e164: '+905551112233',
            carrier_name: 'Turkcell',
            country_name: 'Turkey',
            line_type: 'MOBILE',
            is_valid: true,
          },
          messaging_probes: [
            { platform: 'WhatsApp', url: 'https://wa.me/905551112233', note: 'wa' },
          ],
          associated_handles: ['testuser'],
          social_probes: [],
        });
      }
      return undefined;
    });

    render(UnifiedPinealCockpit);
    const targetInput = screen.getByPlaceholderText(/Hedef Profil URL/i);
    await fireEvent.input(targetInput, { target: { value: '+905551112233' } });

    const probeBtn = await screen.findByRole('button', { name: /NUMARAYI SORGULA/i });
    // [KVKK · 2026-11-23] Açık rıza beyanı olmadan düğme kilitli ve istek gitmez.
    expect((probeBtn as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.click(probeBtn);
    expect(calls.some((c) => c.method === 'POST' && c.path === '/api/commander/phone-probe')).toBe(false);

    const consentBox = screen.getByRole('checkbox', { name: /AÇIK RIZA ALINDI/i });
    await fireEvent.click(consentBox);
    await waitFor(() => expect((probeBtn as HTMLButtonElement).disabled).toBe(false));
    await fireEvent.click(probeBtn);

    await waitFor(() => {
      expect(calls.some((c) => c.method === 'POST' && c.path === '/api/commander/phone-probe')).toBe(true);
    });

    expect(await screen.findByText(/TELEFON OSINT İSTİHBARATI/i)).toBeTruthy();
    expect(screen.getByText('Turkcell')).toBeTruthy();
    expect(screen.getAllByText(/WhatsApp/i).length).toBeGreaterThanOrEqual(1);
  });

  it('removes dead 503 direct dispatch UI and shows live evidence_chain section', async () => {
    installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      return undefined;
    });

    render(UnifiedPinealCockpit);
    expect(screen.queryByRole('button', { name: /GÖREVİ VER/i })).toBeNull();
    expect(screen.getByText(/CANLI KANIT ZİNCİRİ \(evidence_chain/i)).toBeTruthy();
  });

  it('opens multi-provider settings modal, seals provider_keys, and displays agent model routing', async () => {
    const calls = installFetch((path, init) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path.startsWith('/api/llm/routing')) {
        return jsonResponse({
          provider_keys_set: ['deepseek'],
          has_openrouter: false,
          use_local: false,
          has_tavily: false,
          has_serpapi: false,
          has_exa: false,
          routing: {
            agents: {
              aspasia: { chain: ['anthropic/claude-sonnet-5', 'google/gemini-3.7-flash'], source: 'agent_matrix' },
              authenticity_auditor: { chain: ['deepseek/deepseek-v4-flash'], source: 'agent_matrix' },
            },
          },
        });
      }
      if (path === '/api/vault' && init?.method === 'POST') {
        return jsonResponse({ status: 'ok', message: 'Kasa güncellendi' });
      }
      return undefined;
    });

    render(UnifiedPinealCockpit);
    const gearBtn = screen.getByTestId('open-settings-btn');
    await fireEvent.click(gearBtn);

    expect(await screen.findByText(/Doğrudan Aktif Rota Sağlayıcıları/i)).toBeTruthy();
    const deepseekInput = screen.getByLabelText(/DeepSeek/i);
    await fireEvent.input(deepseekInput, { target: { value: 'sk-deepseek-real-123456' } });

    const saveBtn = screen.getByRole('button', { name: /KAYDET VE UYGULA/i });
    await fireEvent.click(saveBtn);

    await waitFor(() => {
      const post = calls.find((c) => c.method === 'POST' && c.path === '/api/vault');
      expect(post).toBeTruthy();
      expect((post?.body as any)?.provider_keys?.deepseek).toBe('sk-deepseek-real-123456');
    });

    const routingTab = screen.getByRole('button', { name: /Ajan > Model Haritası/i });
    await fireEvent.click(routingTab);
    expect(await screen.findByText(/anthropic\/claude-sonnet-5/i)).toBeTruthy();
  });

  it('does not claim agents are in the field before /api/initiate succeeds and logs task_id after acceptance', async () => {
    let initiateBody: Record<string, unknown> | null = null;
    installFetch((path, init) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path === '/api/initiate' && init?.method === 'POST') {
        try {
          initiateBody = JSON.parse(String(init.body || '{}'));
        } catch {
          initiateBody = {};
        }
        return jsonResponse({ task_id: 'tsk-honest-42', status: 'queued' });
      }
      return undefined;
    });

    const { container } = render(UnifiedPinealCockpit);
    const armBtn = screen.getByRole('button', { name: /HAZIR/i });
    await fireEvent.click(armBtn);

    const targetInput = screen.getByPlaceholderText(/Hedef Profil URL/i);
    await fireEvent.input(targetInput, { target: { value: 'https://www.instagram.com/realuser/' } });
    await declareAdult(container);  // 18+ beyanı olmadan düğme kilitli (Tüzük §2)

    const launchBtn = screen.getByRole('button', { name: /ANALİZİ BAŞLAT/i });
    await fireEvent.click(launchBtn);

    expect(await screen.findByText(/Görev kabul edildi \(ID: tsk-honest-42\)/i)).toBeTruthy();
    expect(screen.queryByText(/12 kişilik ajan timi ve kazıyıcı sensörler sahada/i)).toBeNull();
    expect(initiateBody && initiateBody["subject_consent"]).toBe(true);
  });

  it('warns when a non-IG/X URL is entered while cross_platform_enabled is false', async () => {
    installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path.startsWith('/api/llm/routing')) {
        return jsonResponse({
          provider_keys_set: [],
          cross_platform_enabled: false,
          native_platforms: ['instagram', 'x'],
          routing: { agents: {} },
        });
      }
      return undefined;
    });

    render(UnifiedPinealCockpit);
    const targetInput = screen.getByPlaceholderText(/Hedef Profil URL/i);
    await fireEvent.input(targetInput, { target: { value: 'https://www.tiktok.com/@sample' } });

    expect(await screen.findByText(/ENABLE_CROSS_PLATFORM/i)).toBeTruthy();
  });

  it('opens Task History and Report Factory modal, loads past task, builds report, and lists past reports', async () => {
    const calls = installFetch((path, init) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path.startsWith('/api/tasks?')) {
        return jsonResponse({
          tasks: [
            { task_id: 'tsk-past-1', status: 'completed', evidence_count: 1, confidence: 0.9, last_updated: '2026-11-16T01:00:00Z' },
          ],
          active_tasks: [],
        });
      }
      if (path.startsWith('/api/tasks/tsk-past-1?')) {
        return jsonResponse({
          task_id: 'tsk-past-1',
          status: 'completed',
          confidence: 0.9,
          target_profile: { url: 'https://instagram.com/pastuser' },
          evidence_count: 1,
          evidence_chain: [
            {
              agent: 'authenticity_auditor',
              evidence_type: 'primary',
              epistemic_type: 'observation',
              uncertainty: { confidence: 0.9, data_sufficiency: 'sufficient' },
              result: { authenticity_score: 91 },
            },
          ],
        });
      }
      if (path === '/api/report/status') {
        return jsonResponse({
          gate: 'ENABLE_REPORT_FACTORY',
          report_dir: 'memory/reports',
          formats: [{ format: 'markdown', available: true, reason: '' }],
        });
      }
      if (path.startsWith('/api/report/list')) {
        return jsonResponse({
          gate: 'ENABLE_REPORT_FACTORY',
          gate_enabled: true,
          reports: [
            {
              title: 'Geçmiş Rapor 1',
              subject: 'https://instagram.com/pastuser',
              created_at: '2026-11-16T01:05:00Z',
              evidence_count: 1,
              manifest_sha256: 'abc123def456',
              manifest_url: '/api/report/file/rep.manifest.json',
              artifacts: [{ name: 'rep.md', kind: 'markdown', available: true, bytes: 420, download_url: '/api/report/file/rep.md' }],
            },
          ],
        });
      }
      if (path === '/api/report/build' && init?.method === 'POST') {
        return jsonResponse({
          title: 'Pineal Rapor — tsk-past-1',
          formats: { markdown: { available: true, manifest_sha256: 'deadbeef1234' } },
        });
      }
      return undefined;
    });

    render(UnifiedPinealCockpit);
    const histBtn = screen.getByTestId('open-history-btn');
    await fireEvent.click(histBtn);

    expect(await screen.findByText('tsk-past-1')).toBeTruthy();
    const loadBtn = screen.getByRole('button', { name: 'YÜKLE' });
    await fireEvent.click(loadBtn);

    expect(await screen.findByText(/Geçmiş görev yüklendi: tsk-past-1/i)).toBeTruthy();
    expect(screen.getByText(/KANIT \(1\)/i)).toBeTruthy();

    await fireEvent.click(histBtn);
    const reportTab = screen.getByRole('button', { name: /Rapor Fabrikası/i });
    await fireEvent.click(reportTab);

    expect(await screen.findByText('Geçmiş Rapor 1')).toBeTruthy();
    const buildBtn = screen.getByRole('button', { name: /RAPOR PAKETİ ÜRET/i });
    await fireEvent.click(buildBtn);

    await waitFor(() => {
      expect(calls.some((c) => c.method === 'POST' && c.path === '/api/report/build')).toBe(true);
    });
    expect(await screen.findByText(/ÜRETİLDİ/i)).toBeTruthy();
  });

  it('blocks /api/initiate when /api/target/preflight returns eligible=false', async () => {
    const calls = installFetch((path, init) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path === '/api/target/preflight' && init?.method === 'POST') {
        return jsonResponse({
          eligible: false,
          platform: 'web',
          scraper_type: 'unsupported_web',
          reasons: ['UNSUPPORTED_PLATFORM: Çapraz platform kapalı'],
        });
      }
      return undefined;
    });

    const { container } = render(UnifiedPinealCockpit);
    const armBtn = screen.getByRole('button', { name: /HAZIR/i });
    await fireEvent.click(armBtn);

    const targetInput = screen.getByPlaceholderText(/Hedef Profil URL/i);
    await fireEvent.input(targetInput, { target: { value: 'https://www.tiktok.com/@sample' } });
    await declareAdult(container);  // 18+ beyanı olmadan düğme kilitli (Tüzük §2)

    const launchBtn = screen.getByRole('button', { name: /ANALİZİ BAŞLAT/i });
    await fireEvent.click(launchBtn);

    expect(await screen.findByText(/Ön-kontrol engeli/i)).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST' && c.path === '/api/initiate')).toBe(false);
  });

  it('keeps ANALİZİ BAŞLAT locked until the 18+ adult declaration is ticked (Tüzük §2)', async () => {
    const calls = installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      return undefined;
    });

    const { container } = render(UnifiedPinealCockpit);
    const armBtn = screen.getByRole('button', { name: /HAZIR/i });
    await fireEvent.click(armBtn);

    const targetInput = screen.getByPlaceholderText(/Hedef Profil URL/i);
    await fireEvent.input(targetInput, { target: { value: 'https://www.instagram.com/realuser/' } });

    const launchBtn = screen.getByRole('button', { name: /ANALİZİ BAŞLAT/i }) as HTMLButtonElement;
    // Beyan YOK → düğme kilitli ve `/api/initiate` hiç çağrılmıyor (kırmızı çizgi).
    expect(launchBtn.disabled).toBe(true);
    await fireEvent.click(launchBtn);
    expect(calls.some((c) => c.method === 'POST' && c.path === '/api/initiate')).toBe(false);

    // Beyan VAR → aynı düğme açılır: kapı süs değil, gerçek mandal.
    await declareAdult(container);
    await waitFor(() => expect(launchBtn.disabled).toBe(false));
  });

  it('routes Lilith station messages directly to POST /api/lilith/strategy and renders counter-moves', async () => {
    const calls = installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path === '/api/lilith/strategy') {
        return jsonResponse({
          status: 'ok',
          agent: 'lilith',
          metrics_source: 'model_and_formula',
          lilith: { hook: 'Beklenti kıran kanca', psychological_angle: 'Dopamin boşluğu' },
          neuro_metrics: { viral_coefficient_score: 7.4, dominant_neurotransmitter: 'dopamine' },
          shadow: { strategy: 'mirroring' },
          counter_moves: [{ scenario: 'savunmaci', our_counter_move: 'Sakin net yanıt' }],
        });
      }
      return undefined;
    });

    const { container } = render(UnifiedPinealCockpit);
    const lilithCard = container.querySelector('.lilith-station') as HTMLElement;
    expect(lilithCard).toBeTruthy();
    await fireEvent.click(lilithCard);

    const chatInput = container.querySelector('.chat-input-area input, .chat-input, input[placeholder*="Aspasia"], input[placeholder*="mesaj"], input[placeholder*="sor"]') as HTMLInputElement;
    expect(chatInput).toBeTruthy();
    await fireEvent.input(chatInput, { target: { value: 'Karşı hamle hazırla' } });
    await fireEvent.keyDown(chatInput, { key: 'Enter' });

    await waitFor(() => {
      expect(calls.some((c) => c.method === 'POST' && c.path === '/api/lilith/strategy')).toBe(true);
    });
    expect(calls.some((c) => c.method === 'POST' && c.path === '/api/aspasia/chat')).toBe(false);
    await waitFor(() => {
      expect(screen.getByText(/Beklenti kıran kanca/)).toBeTruthy();
      expect(screen.getByText(/Sakin net yanıt/)).toBeTruthy();
    });
  });

  it('routes graph/memory queries directly to POST /api/brain/route', async () => {
    const calls = installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path === '/api/brain/route') {
        return jsonResponse({
          route: 'graph',
          result: { available: true, node_count: 4, edge_count: 3, machine_note: 'GRAF: 4 düğüm, 3 bağ' },
        });
      }
      return undefined;
    });

    const { container } = render(UnifiedPinealCockpit);
    const chatInput = container.querySelector('.chat-input-area input, .chat-input, input[placeholder*="Aspasia"], input[placeholder*="mesaj"], input[placeholder*="sor"]') as HTMLInputElement;
    expect(chatInput).toBeTruthy();
    await fireEvent.input(chatInput, { target: { value: 'İlişki grafını çiz' } });
    await fireEvent.keyDown(chatInput, { key: 'Enter' });

    await waitFor(() => {
      expect(calls.some((c) => c.method === 'POST' && c.path === '/api/brain/route')).toBe(true);
    });
    await waitFor(() => {
      expect(screen.getByText(/GRAF: 4 düğüm, 3 bağ/)).toBeTruthy();
    });
  });
});
