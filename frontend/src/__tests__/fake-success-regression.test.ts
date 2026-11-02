import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { tick } from 'svelte';
import Atlas from '../components/AtlasPinealCockpit.svelte';
import Spider from '../components/SpiderFootCockpit.svelte';
import { clientId, taskStatus, vaultLocked } from '../store';

function response(data: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => data } as Response;
}

beforeEach(() => { clientId.set('proof'); taskStatus.set(null); vaultLocked.set(true); });

describe('Atlas vault and evidence', () => {
  it('requests the backend and refuses to claim an unlock on 423', async () => {
    const fetcher = vi.fn(async (_url: string, init?: RequestInit) => init?.method === 'POST'
      ? response({error:{message:'Kasada anahtar yok'}}, 423)
      : response({locked:true}));
    vi.stubGlobal('fetch', fetcher);
    render(Atlas);
    await screen.findByRole('button', {name: /KASA KİLİTLİ/});
    await fireEvent.click(screen.getByRole('button', {name: /KASA KİLİTLİ/}));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Kasada anahtar yok'));
    expect(get(vaultLocked)).toBe(true);
    expect(fetcher.mock.calls.some(([url, init]) => url.includes('/api/vault/status') && init?.method === 'POST')).toBe(true);
    expect(screen.queryByRole('button', {name: /KASA AÇIK/})).toBeNull();
  });

  it('shows only a confirmed lock result', async () => {
    let locked = false;
    const fetcher = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') { locked = true; return response({status:'locked'}); }
      return response({locked});
    });
    vi.stubGlobal('fetch', fetcher);
    render(Atlas);
    await screen.findByRole('button', {name: /KASA AÇIK/});
    await fireEvent.click(screen.getByRole('button', {name: /KASA AÇIK/}));
    await screen.findByRole('button', {name: /KASA KİLİTLİ/});
    expect(get(vaultLocked)).toBe(true);
  });

  it('shows an unreachable server as unknown', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    render(Atlas);
    await screen.findByRole('button', {name:/KASA DURUMU BİLİNMİYOR/});
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('offline'));
  });

  it('does not show invented Lilith metrics', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({locked:true})));
    render(Atlas);
    const metrics = screen.getByLabelText('Lilith ölçümleri');
    expect(metrics.textContent).toContain('ölçümü mevcut değil');
    expect(metrics.textContent).not.toContain('2.84');
    expect(metrics.textContent).not.toContain('85%');
  });

  it('says stored but not injected when server only stores evidence', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url.includes('/api/commander/inject')
      ? response({status:'stored',applied_to_agent:false}) : response({locked:true})));
    render(Atlas);
    await fireEvent.input(screen.getByPlaceholderText(/Kanıtı girin/), {target:{value:'proof'}});
    await fireEvent.click(screen.getByRole('button', {name:/KANITI KAYDET/}));
    await waitFor(() => expect(document.body.textContent).toContain('Kanıt kaydedildi [TWIN_URL]; ajana veya göreve aktarım henüz bağlı değil.'));
    expect(document.body.textContent).toContain('KAYDEDİLEN KANITLAR:');
    expect(document.body.textContent).not.toContain('Gerçeklik Enjekte Edildi');
  });

  it('does not show successful evidence on failed storage', async () => {
    vi.stubGlobal('alert', vi.fn());
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url.includes('/api/commander/inject')
      ? response({error:{message:'Kanıt kaydedilemedi'}},500) : response({locked:true})));
    render(Atlas);
    await fireEvent.input(screen.getByPlaceholderText(/Kanıtı girin/), {target:{value:'proof'}});
    await fireEvent.click(screen.getByRole('button', {name:/KANITI KAYDET/}));
    await waitFor(() => expect(vi.mocked(alert)).toHaveBeenCalled());
    expect(document.body.textContent).not.toContain('KAYDEDİLEN KANITLAR:');
  });
});

describe('SpiderFoot evidence and confidence', () => {
  it('does not invent confidence and preserves a real zero', async () => {
    vi.stubGlobal('fetch', vi.fn());
    render(Spider);
    await fireEvent.click(screen.getByRole('button', {name:/İLK TEMAS & KANCA/}));
    expect(document.querySelector('.badge-conf')?.textContent).toBe('Veri yok');
    taskStatus.set({holistic_profile:{bridge:{confidence:0}}}); await tick();
    expect(document.querySelector('.badge-conf')?.textContent).toBe('%0');
  });

  it('does not call a detected URL verified, and deduplicates updates', async () => {
    vi.stubGlobal('fetch', vi.fn());
    render(Spider);
    taskStatus.set({target_profile:{detected_urls:['https://example.com/unverified']}}); await tick();
    taskStatus.set({target_profile:{detected_urls:['https://example.com/unverified']}}); await tick();
    await fireEvent.click(screen.getByRole('button', {name:/TOPLANAN KANITLAR/}));
    expect(document.querySelectorAll('.evidence-row')).toHaveLength(1);
    expect(document.querySelector('.evidence-row')?.textContent).toContain('doğrulanmadı');
    expect(document.querySelector('.evidence-row')?.textContent).not.toContain('Instagram Ghost Scraper');
  });

  it('does not mark every step done just because the task completed', async () => {
    vi.stubGlobal('fetch', vi.fn());
    render(Spider);
    taskStatus.set({status:'completed',runs:{osint_investigator:{status:'failed'}}}); await tick();
    expect(document.querySelectorAll('.step-card.done')).toHaveLength(0);
  });

  it('shows the model fallback warning returned by the backend', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({opening_message:'şablon', rationale:'şablon', dialogue_tree:[], data_confidence:false, fallback_reason:'llm_unavailable_template_fallback'})));
    render(Spider);
    await fireEvent.click(screen.getByRole('button', {name:/İLK TEMAS & KANCA/}));
    await fireEvent.click(screen.getByRole('button', {name:/HEDEFE ÖZEL KANCA ÜRET/}));
    await waitFor(() => expect(document.body.textContent).toContain('llm_unavailable_template_fallback'));
  });
});
