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

beforeEach(() => {
  clientId.set('test_room');
  powerEngaged.set(true);
  armEngaged.set(false);
  recordEngaged.set(true);
  isProcessing.set(false);
  taskStatus.set(null);
});

describe('UnifiedPinealCockpit controls and honesty', () => {
  it('renders PWR, ARM, REC switches and toggles stores', async () => {
    installFetch((path) => {
      if (path === '/api/vault/status') return jsonResponse({ locked: true });
      return undefined;
    });

    render(UnifiedPinealCockpit);
    const armBtn = screen.getByRole('button', { name: /ARM/i });
    const pwrBtn = screen.getByRole('button', { name: /PWR/i });
    const recBtn = screen.getByRole('button', { name: /REC/i });

    expect(get(armEngaged)).toBe(false);
    await fireEvent.click(armBtn);
    expect(get(armEngaged)).toBe(true);

    await fireEvent.click(pwrBtn);
    expect(get(powerEngaged)).toBe(false);

    await fireEvent.click(recBtn);
    expect(get(recordEngaged)).toBe(false);
  });

  it('ACİL STOP calls /api/tasks/{id}/halt and disarms ARM', async () => {
    const calls = installFetch((path) => {
      if (path === '/api/vault/status') return jsonResponse({ locked: true });
      if (path === '/api/tasks/op_test_123/halt') return jsonResponse({ status: 'halted' });
      return undefined;
    });

    armEngaged.set(true);
    isProcessing.set(true);
    taskStatus.set({ task_id: 'op_test_123', status: 'processing' });

    render(UnifiedPinealCockpit);
    const stopBtn = screen.getByRole('button', { name: /ACİL STOP/i });
    await fireEvent.click(stopBtn);

    await waitFor(() => {
      expect(calls.some((c) => c.method === 'POST' && c.path === '/api/tasks/op_test_123/halt')).toBe(true);
    });
    expect(get(armEngaged)).toBe(false);
    expect(get(isProcessing)).toBe(false);
  });

  it('does not render fabricated 847 Hz or 94% while processing', () => {
    installFetch((path) => {
      if (path === '/api/vault/status') return jsonResponse({ locked: true });
      return undefined;
    });

    isProcessing.set(true);
    const { container } = render(UnifiedPinealCockpit);
    expect(container.textContent).not.toContain('847 Hz');
    expect(container.textContent).not.toContain('94%');
  });

  it('renders phone OSINT dossier card when phone probe returns metadata', async () => {
    const calls = installFetch((path) => {
      if (path === '/api/vault/status') return jsonResponse({ locked: false });
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
    await fireEvent.click(probeBtn);

    await waitFor(() => {
      expect(calls.some((c) => c.method === 'POST' && c.path === '/api/commander/phone-probe')).toBe(true);
    });

    expect(await screen.findByText(/TELEFON OSINT İSTİHBARATI/i)).toBeTruthy();
    expect(screen.getByText('Turkcell')).toBeTruthy();
    expect(screen.getAllByText(/WhatsApp/i).length).toBeGreaterThanOrEqual(1);
  });

  it('renders direct dispatch inputs and posts to /api/commander/dispatch', async () => {
    const calls = installFetch((path) => {
      if (path === '/api/vault/status') return jsonResponse({ locked: false });
      if (path === '/api/commander/dispatch') {
        return jsonResponse({
          status: 'unavailable',
          error: { code: 'DIRECT_AGENT_DISPATCH_UNAVAILABLE', message: 'Doğrudan ajan yürütmesi bağlı değil' },
        }, 503);
      }
      return undefined;
    });

    render(UnifiedPinealCockpit);
    const instrInput = screen.getByPlaceholderText(/özel emir veya soru/i);
    await fireEvent.input(instrInput, { target: { value: 'Profili analiz et' } });

    const dispatchBtn = screen.getByRole('button', { name: /GÖREVİ VER/i });
    await fireEvent.click(dispatchBtn);

    await waitFor(() => {
      expect(calls.some((c) => c.method === 'POST' && c.path === '/api/commander/dispatch')).toBe(true);
    });
    expect((await screen.findAllByText(/Doğrudan ajan yürütmesi bağlı değil/i)).length).toBeGreaterThanOrEqual(1);
  });
});
