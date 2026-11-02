import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import AtlasPinealCockpit from '../components/AtlasPinealCockpit.svelte';
import { clientId } from '../store';

function response(data: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => data } as Response;
}

async function send(text: string) {
  await fireEvent.input(screen.getByPlaceholderText(/Aspasia ile konuşun/), { target: { value: text } });
  await fireEvent.click(screen.getByRole('button', { name: 'GÖNDER' }));
}

beforeEach(() => clientId.set('test_client'));

describe('Aspasia command and chat', () => {
  it('acknowledges only a real accepted task', async () => {
    const fetcher = vi.fn(async (url: string) => url.includes('/vault/status') ? response({ locked: true }) : response({ accepted: true, task_id: 'tsk_123' }));
    vi.stubGlobal('fetch', fetcher);
    render(AtlasPinealCockpit);
    await send('analiz et');
    await waitFor(() => expect(document.body.textContent).toContain('Görev: tsk_123'));
    const [url, init] = fetcher.mock.calls.find(([url]) => url.includes('/command')) as unknown as [string, RequestInit];
    expect(url).toContain('/api/aspasia/command');
    expect(JSON.parse(String(init.body))).toEqual({ client_id: 'test_client', user_message: 'analiz et' });
  });

  it('reports refusal and uses the actual chat contract without inventing a task', async () => {
    const fetcher = vi.fn(async (url: string) => url.includes('/vault/status') ? response({ locked: true }) : url.includes('/command')
      ? response({ accepted: false, reason: 'dispatch_rejected' })
      : response({ message: 'Sohbet yanıtı' }));
    vi.stubGlobal('fetch', fetcher);
    render(AtlasPinealCockpit);
    await send('merhaba');
    await waitFor(() => expect(document.body.textContent).toContain('Sohbet yanıtı'));
    expect(document.body.textContent).toContain('dispatch_rejected');
    expect(document.body.textContent).not.toContain('Emir alındı');
    const [url, init] = fetcher.mock.calls.find(([url]) => url.includes('/chat')) as unknown as [string, RequestInit];
    expect(url).toContain('/api/aspasia/chat');
    expect(JSON.parse(String(init.body))).toEqual({ client_id: 'test_client', user_message: 'merhaba' });
  });
});
