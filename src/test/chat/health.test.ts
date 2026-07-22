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
    fetchMock.mockResolvedValue({ ok: true });

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
});
