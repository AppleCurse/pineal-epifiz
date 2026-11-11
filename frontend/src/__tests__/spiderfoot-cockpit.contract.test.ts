// SpiderFoot Cockpit · API SÖZLEŞME TESTLERİ
//
// Neden var: bu bileşen bir zamanlar (a) `POST /api/override` ile görev
// durdurduğunu SANIYORDU (o uç hafıza ucudur, `fact`+`tag` bekler → 422;
// hata `catch {}` ile yutuluyordu) ve (b) kasa anahtarı yokken 423 dönen
// `unlock` çağrısından sonra göstergeyi koşulsuz "AÇIK" yapıyordu.
//
// Bu testler bileşeni GERÇEKTEN monte eder, gerçek düğmelere basar ve
// `fetch` çağrılarının yolunu/gövdesini ölçer. Kaynak metni grep'lemez:
// iddiaların hepsi kullanıcı eylemi → ağ isteği → ekrandaki metin zincirinden
// okunur.

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import SpiderFootCockpit from '../components/SpiderFootCockpit.svelte';
import { clientId, vaultLocked, isProcessing, taskStatus } from '../store';
import { get } from 'svelte/store';

type Call = { path: string; method: string; body: unknown };

function jsonResponse(body: any, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function installFetch(
  route: (path: string, init: RequestInit) => Response | undefined,
): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = vi.fn(async (input: any, init: RequestInit = {}) => {
    const url = new URL(String(input), 'http://localhost');
    const path = url.pathname + url.search;
    const method = String(init.method || 'GET').toUpperCase();
    let parsed: unknown = undefined;
    if (typeof init.body === 'string') {
      try {
        parsed = JSON.parse(init.body);
      } catch {
        parsed = init.body;
      }
    }
    calls.push({ path, method, body: parsed });
    return route(path, init) ?? jsonResponse({});
  }) as unknown as typeof fetch;
  return calls;
}

async function launchMission() {
  const input = screen.getByPlaceholderText(/@kullanici_adi/);
  await fireEvent.input(input, { target: { value: '@hedef_kullanici' } });
  const button = screen.getByRole('button', { name: /GÖREVİ BAŞLAT/ });
  await fireEvent.click(button);
  return button;
}

function chatText(): string {
  return document.body.textContent || '';
}

beforeEach(() => {
  clientId.set('test_client');
  vaultLocked.set(true);
  isProcessing.set(false);
});

describe('görev durdurma sözleşmesi', () => {
  it('GERÇEK görev kimliğiyle /api/tasks/{id}/halt çağırır, /api/override çağırmaz', async () => {
    const calls = installFetch((path) => {
      if (path === '/api/initiate') {
        return jsonResponse({ status: 'started', task_id: 'tsk_abc123' });
      }
      if (path.startsWith('/api/tasks/tsk_abc123/halt')) {
        return jsonResponse({ status: 'halted_user', task_id: 'tsk_abc123', outcome: 'TERMINATED' });
      }
      return undefined;
    });

    render(SpiderFootCockpit);
    await launchMission();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /GÖREVİ DURDUR/ })).toBeTruthy();
    });

    await fireEvent.click(screen.getByRole('button', { name: /GÖREVİ DURDUR/ }));

    await waitFor(() => {
      const halt = calls.find((c) => c.path.startsWith('/api/tasks/tsk_abc123/halt'));
      expect(halt, `çağrılar: ${calls.map((c) => c.path).join(', ')}`).toBeTruthy();
      expect(halt!.method).toBe('POST');
      expect(halt!.path).toContain('client_id=test_client');
    });

    // Eski hata: yanlış uç. Artık hiçbir koşulda /api/override'a gidilmemeli.
    expect(calls.some((c) => c.path.startsWith('/api/override'))).toBe(false);

    // Başarılı durdurmadan sonra arayüz "koşuyor" görünümünden çıkmalı.
    await waitFor(() => {
      expect(isProcessingSubscription()).toBe(false);
      expect(chatText()).toContain('durduruldu (tsk_abc123)');
    });

    // Denetim izi: müdahale KAYDI ayrı uca yazılır (durdurma yerine değil).
    const audit = calls.find((c) => c.path === '/api/executor/intervene');
    expect(audit).toBeTruthy();
    expect((audit!.body as any).action_type).toBe('HALT');
    expect((audit!.body as any).parameters.task_id).toBe('tsk_abc123');
  });

  it('durdurma başarısızsa "durduruldu" DEMEZ; görev koşuyor kabul edilir', async () => {
    installFetch((path) => {
      if (path === '/api/initiate') {
        return jsonResponse({ status: 'started', task_id: 'tsk_fail1' });
      }
      if (path.startsWith('/api/tasks/tsk_fail1/halt')) {
        return jsonResponse(
          { error: { code: 'TASK_NOT_FOUND', message: 'Task not found' } },
          404,
        );
      }
      return undefined;
    });

    render(SpiderFootCockpit);
    await launchMission();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /GÖREVİ DURDUR/ })).toBeTruthy();
    });

    await fireEvent.click(screen.getByRole('button', { name: /GÖREVİ DURDUR/ }));

    await waitFor(() => {
      expect(chatText()).toContain('DURDURULAMADI (HTTP 404)');
    });
    expect(chatText()).not.toContain('durduruldu (tsk_fail1)');
    // Arayüz hâlâ "işlem sürüyor" göstermeli: backend görevi kapatmadı.
    expect(isProcessingSubscription()).toBe(true);
    expect(screen.getByRole('button', { name: /GÖREVİ DURDUR/ })).toBeTruthy();
  });

  it('görev kimliği gelmezse hiçbir durdurma isteği göndermez ve dürüst uyarır', async () => {
    const calls = installFetch((path) => {
      if (path === '/api/initiate') {
        return jsonResponse(
          { error: { code: 'VAULT_LOCKED', message: 'Kasa kilitli' } },
          423,
        );
      }
      return undefined;
    });

    render(SpiderFootCockpit);
    await launchMission();

    await waitFor(() => {
      expect(chatText()).toContain('Başlatma engellendi (HTTP 423)');
    });
    // Başlatma düşünce kronometre/durdurma düğmesi asılı kalmamalı.
    expect(screen.queryByRole('button', { name: /GÖREVİ DURDUR/ })).toBeNull();
    expect(isProcessingSubscription()).toBe(false);
    expect(calls.filter((c) => c.path.includes('/halt'))).toHaveLength(0);
  });
});

describe('kasa mandalı sözleşmesi', () => {
  it('423 dönen unlock göstergeyi AÇIK yapmaz', async () => {
    installFetch((path) => {
      if (path === '/api/vault/status') {
        return jsonResponse(
          { error: { code: 'VAULT_LOCKED', message: 'Kasada anahtar yok, once /api/vault ile anahtar girin' } },
          423,
        );
      }
      return undefined;
    });

    render(SpiderFootCockpit);
    const toggle = screen.getByRole('button', { name: /KASA:/ });
    expect(toggle.textContent).toContain('KİLİTLİ');

    await fireEvent.click(toggle);

    await waitFor(() => {
      expect(chatText()).toContain('Kasa açılamadı (HTTP 423)');
    });
    expect(get(vaultLocked)).toBe(true);
    expect(toggle.textContent).toContain('KİLİTLİ');
  });

  it('başarılı unlock göstergeyi yanıttan okunan duruma çeker', async () => {
    const calls = installFetch((path, init) => {
      if (path === '/api/vault/status' && String(init.method).toUpperCase() === 'POST') {
        return jsonResponse({ status: 'unlocked', can_scrape: true });
      }
      if (path.startsWith('/api/vault/status') && String(init.method || 'GET').toUpperCase() === 'GET') {
        return jsonResponse({ locked: false, can_scrape: true });
      }
      return undefined;
    });

    render(SpiderFootCockpit);
    await fireEvent.click(screen.getByRole('button', { name: /KASA:/ }));

    await waitFor(() => {
      expect(get(vaultLocked)).toBe(false);
    });
    // Doğrulama okuması da yapılmalı (tahminle değil, ölçümle kapatma).
    expect(calls.some((c) => c.method === 'GET' && c.path.startsWith('/api/vault/status'))).toBe(true);
    expect(screen.getByRole('button', { name: /KASA:/ }).textContent).toContain('AÇIK');
  });
});

describe('gölge analizi ve hafıza kristali sözleşmesi', () => {
  it('gölge sekmesinde /api/experimental/shadow/analyze ve /api/memory/{target} çağırır', async () => {
    const calls = installFetch((path) => {
      if (path.startsWith('/api/experimental/shadow/analyze')) {
        return jsonResponse({
          narcissism: 0.8,
          machiavellianism: 0.7,
          psychopathy: 0.2,
          exploitability: 0.85,
        });
      }
      if (path.startsWith('/api/memory/')) {
        return jsonResponse({ target: 'hedef_kullanici', summary: 'test crystal' });
      }
      return undefined;
    });

    render(SpiderFootCockpit);
    const tabBtn = screen.getByRole('button', { name: /HEDEF PSİKOLOJİSİ & GÖLGE/ });
    await fireEvent.click(tabBtn);

    const analyzeBtn = screen.getByRole('button', { name: /ANALİZİ TETİKLE/ });
    await fireEvent.click(analyzeBtn);

    await waitFor(() => {
      const call = calls.find((c) => c.path.startsWith('/api/experimental/shadow/analyze'));
      expect(call).toBeTruthy();
      expect(call!.method).toBe('POST');
    });

    const crystalBtn = screen.getByRole('button', { name: /KRİSTALİ ÇEK/ });
    await fireEvent.click(crystalBtn);

    await waitFor(() => {
      const call = calls.find((c) => c.path.startsWith('/api/memory/'));
      expect(call).toBeTruthy();
    });
  });

  it('gerçek kanıt grafını /api/tasks/{id}/graph ucundan çeker', async () => {
    const calls = installFetch((path) => {
      if (path.startsWith('/api/initiate')) {
        return jsonResponse({ task_id: 'task_graph_99' }, 202);
      }
      if (path.startsWith('/api/tasks/task_graph_99/graph')) {
        return jsonResponse({
          available: true,
          nodes: [
            { id: 'target:test', label: 'test', kind: 'target', weight: 1, evidence_count: 3 },
            { id: 'host:instagram.com', label: 'instagram.com', kind: 'host', weight: 2, evidence_count: 2 },
          ],
          edges: [
            { source: 'target:test', target: 'host:instagram.com', weight: 2, relation: 'co_occurrence' },
          ],
          node_count: 2,
          edge_count: 1,
          machine_note: 'ok',
        });
      }
      return undefined;
    });

    render(SpiderFootCockpit);
    await launchMission();

    const refreshBtn = screen.getByRole('button', { name: /Gerçek Kanıt Grafını Yenile/i });
    expect(refreshBtn).toBeTruthy();
    await fireEvent.click(refreshBtn);

    await waitFor(() => {
      const call = calls.find((c) => c.path.startsWith('/api/tasks/task_graph_99/graph'));
      expect(call).toBeTruthy();
      expect(call!.method).toBe('GET');
    });

    await waitFor(() => {
      expect(screen.getByText(/2 düğüm, 1 bağ/i)).toBeTruthy();
    });
  });

  // [SMOKE 2026-11-11] Gerçek tarayıcıda ölçülen boşluk: görev kimliği YALNIZ bu
  // bileşenin kendi "GÖREVİ BAŞLAT" düğmesinden geliyordu. Operatör varsayılan
  // ATLAS yüzeyinden görev başlattığında `/api/tasks/{id}/graph` hiç
  // çağrılmıyor, backend'de hazır olan gerçek graf (5 düğüm / 4 bağ) ekrana
  // ulaşmıyordu. Sözleşme: canlı WS anlık görüntüsündeki görev kimliği de
  // grafın kimlik kaynağıdır.
  it('görev kimliği WS anlık görüntüsünden gelirse grafı kendiliğinden çeker', async () => {
    const calls = installFetch((path) => {
      if (path.startsWith('/api/tasks/task_from_ws/graph')) {
        return jsonResponse({
          available: true,
          nodes: [
            { id: 'target:test', label: 'test', kind: 'target', weight: 1, evidence_count: 1 },
            { id: 'engine:pineal_7pillar', label: 'pineal_7pillar', kind: 'engine', weight: 1, evidence_count: 1 },
            { id: 'engine:life_rupture', label: 'life_rupture', kind: 'engine', weight: 1, evidence_count: 1 },
          ],
          edges: [
            { source: 'engine:pineal_7pillar', target: 'target:test', weight: 1, relation: 'co_occurrence' },
            { source: 'engine:life_rupture', target: 'target:test', weight: 1, relation: 'co_occurrence' },
          ],
          node_count: 3,
          edge_count: 2,
          machine_note: 'ok',
        });
      }
      return undefined;
    });

    // Bileşen HİÇ görev başlatmıyor: kimlik yalnız WS anlık görüntüsünden gelir.
    taskStatus.set({ task_id: 'task_from_ws', status: 'processing' });
    render(SpiderFootCockpit);

    await fireEvent.click(screen.getByRole('button', { name: /İLİŞKİ AĞI GRAFİĞİ/i }));

    await waitFor(() => {
      const call = calls.find((c) => c.path.startsWith('/api/tasks/task_from_ws/graph'));
      expect(call, `çağrılar: ${calls.map((c) => c.path).join(', ')}`).toBeTruthy();
    });

    await waitFor(() => {
      expect(screen.getByText(/3 düğüm, 2 bağ/i)).toBeTruthy();
    });

    taskStatus.set(null);
  });
});


function isProcessingSubscription(): boolean {
  let value = false;
  const unsubscribe = isProcessing.subscribe((v) => (value = v));
  unsubscribe();
  return value;
}
