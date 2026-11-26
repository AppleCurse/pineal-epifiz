import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import UnifiedPinealCockpit from '../components/UnifiedPinealCockpit.svelte';
import { activeTab, theme } from '../lib/theme';
import { armEngaged, clientId, formatApiError, isProcessing, powerEngaged, recordEngaged, taskStatus } from '../store';

function installMemoryStorage() {
  const mem = new Map<string, string>();
  const storageStub = {
    getItem: (k: string) => (mem.has(k) ? mem.get(k)! : null),
    setItem: (k: string, v: string) => {
      mem.set(k, String(v));
    },
    removeItem: (k: string) => {
      mem.delete(k);
    },
    clear: () => mem.clear(),
    key: (i: number) => Array.from(mem.keys())[i] ?? null,
    get length() {
      return mem.size;
    },
  };
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: storageStub,
  });
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: storageStub,
  });
}

installMemoryStorage();

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

beforeEach(() => {
  localStorage.clear();
  theme.set('dark');
  activeTab.set('home');
  clientId.set('test_room');
  powerEngaged.set(true);
  armEngaged.set(false);
  recordEngaged.set(true);
  isProcessing.set(false);
  taskStatus.set(null);
});

afterEach(() => {
  activeTab.set('home');
  theme.set('dark');
});

describe('Modern modular cockpit', () => {
  it('toggles dark/light theme and persists choice to DOM and localStorage', async () => {
    installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: true });
      return undefined;
    });

    render(UnifiedPinealCockpit);
    expect(document.documentElement.dataset.theme).toBe('dark');

    const toggleBtn = screen.getByTestId('theme-toggle-btn');
    await fireEvent.click(toggleBtn);
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(localStorage.getItem('pineal_theme')).toBe('light');

    await fireEvent.click(toggleBtn);
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(localStorage.getItem('pineal_theme')).toBe('dark');
  });

  it('navigates smoothly across all 9 sidebar sections', async () => {
    installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path.startsWith('/api/brain/capabilities')) return jsonResponse({ capabilities: [] });
      if (path === '/api/company/status') return jsonResponse({ any_available: true, modes: [] });
      if (path === '/api/media/status') return jsonResponse({ tools: {} });
      if (path === '/api/speech/status') return jsonResponse({ available: false, reason: 'no_engine' });
      if (path.startsWith('/api/browser/state')) return jsonResponse({ open: false });
      if (path.startsWith('/api/hook/archetypes')) return jsonResponse({ archetypes: [] });
      if (path.startsWith('/api/tasks')) return jsonResponse({ tasks: [] });
      if (path === '/api/report/status') return jsonResponse({ formats: [] });
      if (path.startsWith('/api/report/list')) return jsonResponse({ reports: [] });
      if (path === '/api/public/demo-reports') return jsonResponse({ reports: [] });
      return undefined;
    });

    const { container } = render(UnifiedPinealCockpit);
    const navBtn = (tab: string) => {
      const btn = container.querySelector<HTMLButtonElement>(`button[data-tab="${tab}"]`);
      if (!btn) throw new Error(`Sidebar button not found for tab: ${tab}`);
      return btn;
    };

    await fireEvent.click(navBtn('cross'));
    expect(await screen.findByText(/Çapraz Tarama & Kimlik İz Sürme/i)).toBeTruthy();

    await fireEvent.click(navBtn('aspasia'));
    expect(await screen.findByText(/Aspasia ile Sohbet & Danışman/i)).toBeTruthy();

    await fireEvent.click(navBtn('lilith'));
    expect(await screen.findByText(/İlk Mesaj Üretici/i)).toBeTruthy();

    await fireEvent.click(navBtn('company'));
    expect(await screen.findByText(/Şirket & İnternet Sitesi Taraması/i)).toBeTruthy();

    await fireEvent.click(navBtn('media'));
    expect(await screen.findByText(/Video, Görsel ve Ses Merkezi/i)).toBeTruthy();

    await fireEvent.click(navBtn('browser'));
    expect(await screen.findByText(/Canlı Tarayıcı ve Oturum Girişi/i)).toBeTruthy();

    await fireEvent.click(navBtn('reports'));
    expect(await screen.findByText(/Raporlar, Geçmiş ve Hafıza Arşivi/i)).toBeTruthy();

    await fireEvent.click(navBtn('system'));
    expect(await screen.findByText(/28 Yetenek Durum Tablosu/i)).toBeTruthy();

    await fireEvent.click(navBtn('home'));
    expect(await screen.findByPlaceholderText(/Hedef Profil URL/i)).toBeTruthy();
  });

  it('triggers Maigret username scan and Holehe email scan from CrossScanTab', async () => {
    const calls = installFetch((path, init) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path.startsWith('/api/brain/capabilities')) return jsonResponse({ capabilities: [] });
      if (path === '/api/experimental/maigret/scan' && init?.method === 'POST') {
        return jsonResponse({ username: 'ornekuser', found_count: 1, results: [{ site: 'GitHub', url: 'https://github.com/ornekuser' }] });
      }
      if (path === '/api/experimental/holehe/scan' && init?.method === 'POST') {
        return jsonResponse({ email: 'deneme@alan.com', used_services: [{ name: 'Spotify' }] });
      }
      return undefined;
    });

    const { container } = render(UnifiedPinealCockpit);
    const crossBtn = container.querySelector<HTMLButtonElement>('button[data-tab="cross"]');
    expect(crossBtn).toBeTruthy();
    await fireEvent.click(crossBtn!);

    const userInput = await screen.findByPlaceholderText(/Örn: ornek_kullanici/i);
    await fireEvent.input(userInput, { target: { value: 'ornekuser' } });
    await fireEvent.click(screen.getByRole('button', { name: /Kullanıcı Adını Tara/i }));

    const emailInput = screen.getByPlaceholderText(/ornek@alanadi\.com/i);
    await fireEvent.input(emailInput, { target: { value: 'deneme@alan.com' } });
    await fireEvent.click(screen.getByRole('button', { name: /E-postayı Tara/i }));

    await waitFor(() => {
      expect(calls.some((c) => c.method === 'POST' && c.path === '/api/experimental/maigret/scan')).toBe(true);
      expect(calls.some((c) => c.method === 'POST' && c.path === '/api/experimental/holehe/scan')).toBe(true);
    });
  });

  it('loads hook archetypes and generates opening hooks in LilithStudioTab', async () => {
    const calls = installFetch((path, init) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path === '/api/hook/archetypes') {
        return jsonResponse({
          archetypes: [
            { id: 'authentic_connection', title: 'Samimi Köprü', description: 'Doğal başlangıç' },
          ],
        });
      }
      if (path === '/api/hook/generate' && init?.method === 'POST') {
        return jsonResponse({
          opening_message: 'Merhaba, paylaştığın fotoğraf çok tanıdık geldi.',
          rationale: 'Doğal ortak zemin',
          branches: [{ condition: 'Olumlu yanıt', reply: 'Devam sorusu' }],
        });
      }
      return undefined;
    });

    render(UnifiedPinealCockpit);
    await fireEvent.click(screen.getByRole('button', { name: /Lilith & İlk Mesaj/i }));

    expect(await screen.findByText(/Samimi Köprü/i)).toBeTruthy();

    await fireEvent.click(screen.getByRole('button', { name: /İLK MESAJ ÜRET/i }));

    await waitFor(() => {
      expect(calls.some((c) => c.method === 'GET' && c.path === '/api/hook/archetypes')).toBe(true);
      expect(calls.some((c) => c.method === 'POST' && c.path === '/api/hook/generate')).toBe(true);
    });
    expect(await screen.findByText(/paylaştığın fotoğraf çok tanıdık geldi/i)).toBeTruthy();
  });

  it('filters and searches capabilities in SystemToolsTab using /api/telemetry', async () => {
    installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path.startsWith('/api/telemetry')) {
        return jsonResponse({
          capabilities: [
            { id: 'sensor.identity.maigret', available: true, reason: null },
            { id: 'voice.tts.local', available: false, reason: 'no_engine' },
          ],
        });
      }
      if (path.startsWith('/api/brain/capabilities')) return jsonResponse({ profiles: {}, wired_pipelines: {} });
      return undefined;
    });

    const { container } = render(UnifiedPinealCockpit);
    const sysBtn = container.querySelector<HTMLButtonElement>('button[data-tab="system"]');
    await fireEvent.click(sysBtn!);

    expect(await screen.findByText(/Tümü \(2\)/i)).toBeTruthy();
    expect(screen.getByText(/Hazır \(1\)/i)).toBeTruthy();
    expect(screen.getByText(/Eksik \(1\)/i)).toBeTruthy();

    await fireEvent.click(screen.getByRole('button', { name: /Hazır \(1\)/i }));
    expect(screen.queryByText(/no_engine/i)).toBeNull();
    expect(container.querySelectorAll('.cap-card')).toHaveLength(1);

    await fireEvent.click(screen.getByRole('button', { name: /Eksik \(1\)/i }));
    expect((await screen.findAllByText(/no_engine/i)).length).toBeGreaterThanOrEqual(1);
    expect(container.querySelectorAll('.cap-card')).toHaveLength(1);

    await fireEvent.click(screen.getByRole('button', { name: /Tümü \(2\)/i }));
    expect(container.querySelectorAll('.cap-card')).toHaveLength(2);
    const searchInput = screen.getByPlaceholderText(/Yetenek veya eksik nedeni ara/i);
    await fireEvent.input(searchInput, { target: { value: 'no_engine' } });
    expect(screen.getAllByText(/no_engine/i).length).toBeGreaterThanOrEqual(1);
    expect(container.querySelectorAll('.cap-card')).toHaveLength(1);
  });

  it('renders JuryConsensusPanel empty state and populated jury output', async () => {
    installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path.startsWith('/api/telemetry')) return jsonResponse({ capabilities: [] });
      return undefined;
    });

    const { container } = render(UnifiedPinealCockpit);
    const sysBtn = container.querySelector<HTMLButtonElement>('button[data-tab="system"]');
    await fireEvent.click(sysBtn!);

    expect(await screen.findByText(/Henüz jüri raporu yayınlanmadı/i)).toBeTruthy();

    taskStatus.set({
      task_id: 'tsk-jury-1',
      status: 'completed',
      output_summary: {
        status: 'verified',
        confidence: 0.88,
        data_confidence: true,
        unknown_claims: 1,
        jurors: ['juror-alpha', 'juror-beta'],
        dropped_juror: ['juror-gamma'],
        consensus: {
          claims_audited: 4,
          mismatches: 0,
          quorum_met_claims: 4,
          quorum_required: 2,
          mean_strength: 0.91,
          binding: true,
          machine_note: 'Oy birliği sağlandı.',
        },
        vote_accounting: { evet: 2, hayir: 0 },
        decision_rule: 'Çoğunluk esası',
        verifications: [{ claim: 'Hesap aktif', verdict: 'verified', note: 'Son paylaşım güncel' }],
      },
    });

    expect(await screen.findByText('juror-alpha')).toBeTruthy();
    expect(screen.getByText('juror-gamma')).toBeTruthy();
    expect(screen.getByText(/Oy birliği sağlandı/i)).toBeTruthy();
    expect(screen.getByText(/Hesap aktif/i)).toBeTruthy();
  });

  it('advances through the 3-step onboarding guide and dismisses it', async () => {
    installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: true });
      return undefined;
    });

    render(UnifiedPinealCockpit);
    expect(screen.getByText(/Anahtarı ve Kasayı Açın/i)).toBeTruthy();

    await fireEvent.click(screen.getByRole('button', { name: 'Sonraki' }));
    expect(await screen.findByText(/Hedefi Yazıp Onay Verin/i)).toBeTruthy();

    await fireEvent.click(screen.getByRole('button', { name: 'Sonraki' }));
    expect(await screen.findByText(/Analizi Başlatın ve Odaları Gezin/i)).toBeTruthy();

    await fireEvent.click(screen.getByRole('button', { name: /Anladım, Gizle/i }));
    expect(screen.queryByText(/Analizi Başlatın ve Odaları Gezin/i)).toBeNull();
    expect(localStorage.getItem('pineal_guide_dismissed')).toBe('1');
  });

  it('formats FastAPI 422 detail arrays and error objects cleanly without [object Object]', () => {
    const out422 = formatApiError(
      { detail: [{ loc: ['body', 'evidence'], msg: 'Input should be a valid string', type: 'string_type' }] },
      'Fallback'
    );
    expect(out422).toContain('evidence: Input should be a valid string');
    expect(out422).not.toContain('[object Object]');

    expect(formatApiError({ error: { message: 'Kasa kilitli' }, detail: 'ignored' }, 'Fallback')).toBe('Kasa kilitli');
    expect(formatApiError({ detail: 'Geçersiz istek' }, 'Fallback')).toBe('Geçersiz istek');
    expect(formatApiError({}, 'Fallback mesajı')).toBe('Fallback mesajı');
  });

  it('sends client_id query parameter when ACIL DUR halt button is clicked', async () => {
    const calls = installFetch((path) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path.startsWith('/api/tasks/task_xyz/halt')) return jsonResponse({ halted: true });
      return undefined;
    });

    taskStatus.set({ task_id: 'task_xyz', status: 'running' });
    isProcessing.set(true);
    render(UnifiedPinealCockpit);

    await fireEvent.click(screen.getByRole('button', { name: /ACİL DUR/i }));
    await waitFor(() => {
      expect(calls.some((c) => c.method === 'POST' && c.path === '/api/tasks/task_xyz/halt?client_id=test_room')).toBe(true);
    });
  });

  it('sends string evidence to /api/jury/vote and structured target_profile to shadow endpoints', async () => {
    const calls = installFetch((path, init) => {
      if (path.startsWith('/api/vault/status')) return jsonResponse({ locked: false });
      if (path.startsWith('/api/telemetry')) return jsonResponse({ capabilities: [] });
      if (path === '/api/jury/vote' && init?.method === 'POST') return jsonResponse({ available: true, consensus: true });
      if (path === '/api/experimental/shadow/analyze' && init?.method === 'POST') return jsonResponse({ narcissism: 0 });
      if (path === '/api/experimental/shadow/generate' && init?.method === 'POST') return jsonResponse({ strategy: 'mirroring' });
      return undefined;
    });

    const { container } = render(UnifiedPinealCockpit);
    const sysBtn = container.querySelector<HTMLButtonElement>('button[data-tab="system"]');
    await fireEvent.click(sysBtn!);

    // Jury vote payload contract
    await fireEvent.input(screen.getByPlaceholderText(/Doğrulanacak iddia/i), { target: { value: 'Örnek iddia' } });
    await fireEvent.input(screen.getByPlaceholderText(/Dayanak kanıt metni/i), { target: { value: 'Somut gözlem' } });
    await fireEvent.click(screen.getByRole('button', { name: /Jüriye Sor/i }));

    await waitFor(() => {
      const req = calls.find((c) => c.path === '/api/jury/vote' && c.method === 'POST');
      expect(req).toBeTruthy();
      expect(typeof req!.body.evidence).toBe('string');
      expect(req!.body.evidence).toBe('Somut gözlem');
    });

    // Shadow analyze payload contract
    await fireEvent.input(screen.getByPlaceholderText(/Kişi \/ konu/i), { target: { value: 'ornek_kisi' } });
    await fireEvent.input(screen.getByPlaceholderText(/Örnek yazılar veya üslup notu/i), {
      target: { value: 'Birinci paylaşım\nİkinci paylaşım' },
    });
    await fireEvent.click(screen.getByRole('button', { name: /Çalıştır/i }));

    await waitFor(() => {
      const req = calls.find((c) => c.path === '/api/experimental/shadow/analyze' && c.method === 'POST');
      expect(req).toBeTruthy();
      expect(req!.body.posts).toEqual(['Birinci paylaşım', 'İkinci paylaşım']);
      expect(req!.body.recent_texts).toBeUndefined();
    });

    // Shadow generate payload contract
    const selects = container.querySelectorAll<HTMLSelectElement>('select.field-select');
    const shadowSelect = Array.from(selects).find((s) =>
      Array.from(s.options).some((o) => o.value === 'generate')
    );
    expect(shadowSelect).toBeTruthy();
    await fireEvent.change(shadowSelect!, { target: { value: 'generate' } });
    await fireEvent.input(await screen.findByPlaceholderText(/Bu mesajda amacınız nedir/i), {
      target: { value: 'Doğal merhaba' },
    });
    await fireEvent.click(screen.getByRole('button', { name: /Çalıştır/i }));

    await waitFor(() => {
      const req = calls.find((c) => c.path === '/api/experimental/shadow/generate' && c.method === 'POST');
      expect(req).toBeTruthy();
      expect(req!.body.target_profile).toEqual({
        username: 'ornek_kisi',
        bio: 'Birinci paylaşım\nİkinci paylaşım',
        posts: ['Birinci paylaşım', 'İkinci paylaşım'],
      });
      expect(req!.body.goal).toBe('Doğal merhaba');
    });
  });
});
