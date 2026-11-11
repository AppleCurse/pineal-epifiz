// Atlas Observatory · DÜRÜSTLÜK SÖZLEŞMESİ
//
// Neden var: varsayılan açılış yüzeyi "VERİ YOKSA UYDURMAZ" rozeti taşırken
// TAMAMEN sabit rakamlarla doluydu — "TOPLAM VERİ: 448.721", "Instagram 842K",
// "RİSK %42/%37/%21", "CASE #AT-2025-0918 TAMAMLANDI". Hiçbiri bir API'ye
// dayanmıyordu. Ayrıca ana düğme `POST /api/tasks` çağırıyordu; o uç backend'de
// YOK (405), yani görev başlatma hiçbir koşulda çalışmıyordu.
//
// Bu testler bileşeni GERÇEKTEN monte eder, gerçek düğmeye basar ve
// (a) hangi uca gidildiğini, (b) ekranda hangi metnin göründüğünü ölçer.
// Kaynak metni grep'lemez.

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import AtlasObservatory from '../components/AtlasObservatory.svelte';
import { clientId } from '../store';

type Call = { path: string; method: string };

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
    calls.push({ path, method });
    return route(path, init) ?? jsonResponse({});
  }) as unknown as typeof fetch;
  return calls;
}

const TELEMETRY = {
  core: true,
  gateway: false,
  scraper: false,
  vault: false,
  search_engine: false,
  x_scraper: false,
  instagram_scraper: false,
  instagram_session: false,
  browser_installed: false,
  llm_spend_usd: 1.25,
  llm_spend_cap_usd: 10,
  llm_unpriced_calls: 0,
  vault_locked: true,
  x_scraper_reason: 'gate_disabled:ENABLE_X_SENSOR',
  agent_statuses: {
    osint_investigator: { agent_id: 'osint_investigator', status: 'Active' },
    depth_analyst: { agent_id: 'depth_analyst', status: 'Wait' },
  },
};

const TASKS = {
  tasks: [
    // API eskiden yeniye döndürür; kart EN YENİ görevi göstermeli.
    { task_id: 'op_20261111090000_aaaaaaaa', last_updated: '2026-11-11T09:00:00+00:00', evidence_count: 2, memory_state: 'READY' },
    { task_id: 'op_20261111093000_bbbbbbbb', last_updated: '2026-11-11T09:30:00+00:00', evidence_count: 7, memory_state: 'READY' },
  ],
  active_tasks: [],
};

const GRAPH = { available: true, node_count: 5, edge_count: 4, nodes: [], edges: [] };

function standardRoute(path: string): Response | undefined {
  if (path === '/api/telemetry') return jsonResponse(TELEMETRY);
  if (path.startsWith('/api/tasks?')) return jsonResponse(TASKS);
  if (/\/graph\?/.test(path) || path.endsWith('/graph')) return jsonResponse(GRAPH);
  return undefined;
}

beforeEach(() => {
  clientId.set('test_client');
});

describe('Atlas Observatory dürüstlük sözleşmesi', () => {
  it('sabit/uydurma değerleri GÖSTERMEZ', async () => {
    installFetch(standardRoute);
    render(AtlasObservatory);
    // Gerçek veri geldikten sonra ölç: kanıt toplamı (2+7=9) ekrana basılmalı.
    await waitFor(() => expect(screen.getAllByText('9').length).toBeGreaterThan(0));

    const text = document.body.textContent || '';
    for (const fake of ['448.721', '97.346', '61.208', '1.2M', '842K', '421K', 'AT-2025-0918', '%42', '%37', '%21']) {
      expect(text, `uydurma değer ekranda: ${fake}`).not.toContain(fake);
    }
  });

  it('gerçek telemetri ve görev verisini ekrana basar', async () => {
    installFetch(standardRoute);
    render(AtlasObservatory);

    // Graf: gerçek düğüm/bağ sayısı (5/4)
    await waitFor(() => expect(screen.getAllByText(/5 düğüm \/ 4 bağ/).length).toBeGreaterThan(0));
    // Kanıt toplamı = 2 + 7
    expect(screen.getAllByText('9').length).toBeGreaterThan(0);
    // LLM harcaması gerçek değerden
    expect(screen.getByText(/\$1\.2500/)).toBeTruthy();
    // Aktif ajan sayısı gerçek durumdan (1 Active / 2)
    expect(screen.getByText(/AJAN YUVASI \(1\/2\)/)).toBeTruthy();
  });

  it('SON GÖREV kartı EN YENİ görevi gösterir (API sırasına güvenmez)', async () => {
    installFetch(standardRoute);
    render(AtlasObservatory);
    await waitFor(() => expect(screen.getByText(/op_20261111093000_bbbbbbbb/)).toBeTruthy());
    expect(screen.queryByText(/op_20261111090000_aaaaaaaa/)).toBeNull();
  });

  it('görev başlatma /api/initiate çağırır — var olmayan POST /api/tasks DEĞİL', async () => {
    const calls = installFetch((path, init) => {
      if (path === '/api/initiate' && String(init.method).toUpperCase() === 'POST') {
        return jsonResponse({ status: 'started', task_id: 'op_20261111100000_cccccccc' });
      }
      return standardRoute(path);
    });

    render(AtlasObservatory);
    const input = document.querySelector('.target-quick-bar input') as HTMLInputElement;
    await fireEvent.input(input, { target: { value: '@hedef' } });
    await fireEvent.click(document.querySelector('.scan-trigger-btn') as HTMLElement);

    await waitFor(() => {
      const initiate = calls.find((c) => c.path.startsWith('/api/initiate'));
      expect(initiate, `çağrılar: ${calls.map((c) => c.method + ' ' + c.path).join(', ')}`).toBeTruthy();
      expect(initiate!.method).toBe('POST');
    });

    // Eski hata: backend'de olmayan uç (405).
    expect(calls.some((c) => c.path === '/api/tasks' && c.method === 'POST')).toBe(false);
  });

  it('kasa kilidi (423) yanıtını AYNEN gösterir, sahte başarı üretmez', async () => {
    const alerts: string[] = [];
    const origAlert = globalThis.alert;
    globalThis.alert = ((msg: string) => { alerts.push(String(msg)); }) as any;

    try {
      installFetch((path, init) => {
        if (path === '/api/initiate' && String(init.method).toUpperCase() === 'POST') {
          return jsonResponse(
            { error: { code: 'VAULT_LOCKED', message: 'VAULT KİLİTLİ: Operatör anahtarı çevrilmeden istek çıkamaz.' } },
            423,
          );
        }
        return standardRoute(path);
      });

      render(AtlasObservatory);
      const input = document.querySelector('.target-quick-bar input') as HTMLInputElement;
      await fireEvent.input(input, { target: { value: '@hedef' } });
      await fireEvent.click(document.querySelector('.scan-trigger-btn') as HTMLElement);

      await waitFor(() => expect(alerts.length).toBeGreaterThan(0));
      expect(alerts[0]).toContain('VAULT KİLİTLİ');
      expect(alerts[0]).not.toContain('başarıyla');
    } finally {
      globalThis.alert = origAlert;
    }
  });
});
