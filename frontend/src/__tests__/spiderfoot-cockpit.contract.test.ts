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
import { clientId, vaultLocked, isProcessing } from '../store';
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

function isProcessingSubscription(): boolean {
  let value = false;
  const unsubscribe = isProcessing.subscribe((v) => (value = v));
  unsubscribe();
  return value;
}
