import { describe, it, expect, vi, beforeEach } from 'vitest';

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: mocks.getSession } },
}));

import { checkConnection, checkBackendHealth, getHealthStatus, resetHealthCache } from '@/lib/chat/health';
import { setAIProvider } from '@/lib/chat/config';

describe('chat/health', () => {
  beforeEach(() => {
    mocks.getSession.mockResolvedValue({ data: { session: null } });
    vi.stubGlobal('fetch', vi.fn());
    resetHealthCache();
    if (typeof AbortSignal.timeout !== 'function') {
      Object.defineProperty(AbortSignal, 'timeout', {
        value: (ms: number) => new AbortController().signal,
        configurable: true,
      });
    }
  });

  it('placeholder provider reports offline mode', async () => {
    setAIProvider({ provider: 'placeholder' });
    const result = await checkConnection();
    expect(result).toEqual({ connected: true, mode: 'Offline Mode' });
  });


  it('caches backend health status for 30 seconds', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ ready: true }) });

    await checkBackendHealth('http://localhost:8000/api/chat');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(getHealthStatus()).toBe('up');

    await checkBackendHealth('http://localhost:8000/api/chat');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('marks health down when fetch throws', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockRejectedValue(new Error('network failure'));

    const status = await checkBackendHealth('http://localhost:8000/api/chat');
    expect(status).toBe('down');
    expect(getHealthStatus()).toBe('down');
  });

  it('checks relative chat endpoints and rejects HTML fallback responses', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => { throw new SyntaxError('HTML'); } });
    expect(await checkBackendHealth('/api/chat')).toBe('down');
    expect(fetchMock.mock.calls[0][0]).toBe(`${window.location.origin}/api/health`);
  });

  it('does not reuse a healthy result for a different teaching service', async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ ready: true }) })
      .mockResolvedValueOnce({ ok: false, status: 502 });
    expect(await checkBackendHealth('https://one.example/api/chat')).toBe('up');
    expect(await checkBackendHealth('https://two.example/api/chat')).toBe('down');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('connection check requires ready=true, not just HTTP 200', async () => {
    setAIProvider({ provider: 'custom', endpoint: '/api/chat' });
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true, json: async () => ({ ready: false }) });
    expect(await checkConnection()).toEqual({ connected: false, mode: 'Unavailable' });
  });
});
