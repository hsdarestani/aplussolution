import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, consumeOAuth, login } from '../api';

const response = (status: number, body: any) => ({
  status,
  ok: status >= 200 && status < 300,
  json: vi.fn().mockResolvedValue(body),
}) as unknown as Response;

describe('API client', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('stores both login tokens', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, { access: 'a', refresh: 'r', user: { role: 'worker' } })));
    const user = await login('a@example.com', 'password');
    expect(user.role).toBe('worker');
    expect(localStorage.getItem('access')).toBe('a');
    expect(localStorage.getItem('refresh')).toBe('r');
  });

  it('refreshes once after a 401 and retries the original request', async () => {
    localStorage.setItem('access', 'expired');
    localStorage.setItem('refresh', 'refresh-token');
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(401, { detail: 'expired' }))
      .mockResolvedValueOnce(response(200, { access: 'new-access', refresh: 'new-refresh' }))
      .mockResolvedValueOnce(response(200, { ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(api('dashboard/')).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(localStorage.getItem('access')).toBe('new-access');
  });

  it('emits auth-lost when refresh fails', async () => {
    localStorage.setItem('access', 'expired');
    localStorage.setItem('refresh', 'bad');
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(response(401, { detail: 'expired' }))
      .mockResolvedValueOnce(response(401, { detail: 'bad refresh' })));
    const handler = vi.fn();
    window.addEventListener('auth-lost', handler);
    await expect(api('dashboard/')).rejects.toThrow('expired');
    expect(handler).toHaveBeenCalledOnce();
    expect(localStorage.getItem('access')).toBeNull();
  });

  it('preserves FormData content type handling', async () => {
    localStorage.setItem('access', 'token');
    const fetchMock = vi.fn().mockResolvedValue(response(200, { ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    const form = new FormData();
    form.append('file', new Blob(['x']), 'x.txt');
    await api('documents/', { method: 'POST', body: form });
    const headers = fetchMock.mock.calls[0][1].headers;
    expect(headers['Content-Type']).toBeUndefined();
    expect(headers.Authorization).toBe('Bearer token');
  });

  it('consumes OAuth callback tokens', () => {
    window.history.replaceState({}, '', '/auth/callback?access=a&refresh=r');
    expect(consumeOAuth()).toBe(true);
    expect(localStorage.getItem('access')).toBe('a');
    expect(window.location.pathname).toBe('/');
  });
});
