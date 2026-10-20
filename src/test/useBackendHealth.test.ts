import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/backendUrl', () => ({ BACKEND_URL: '' }));

import { useBackendHealth } from '@/hooks/useBackendHealth';

describe('useBackendHealth', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('reports unreachable, not "waking up", when the request never gets an answer', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const { result } = renderHook(() => useBackendHealth());
    await waitFor(() => expect(result.current).toBe('unreachable'));
  });

  it('reports degraded when the backend answers but is not healthy', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    const { result } = renderHook(() => useBackendHealth());
    await waitFor(() => expect(result.current).toBe('degraded'));
  });

  it('reports ok on a healthy answer', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ready: true }) });
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useBackendHealth());
    await waitFor(() => expect(result.current).toBe('ok'));
    expect(fetchMock.mock.calls[0][0]).toBe(`${window.location.origin}/api/health`);
  });

  it('does not report ready=false as healthy even on HTTP 200', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ready: false }) }));
    const { result } = renderHook(() => useBackendHealth());
    await waitFor(() => expect(result.current).toBe('degraded'));
  });

  it('reports a failed proxy as unreachable, not starting up', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 502 }));
    const { result } = renderHook(() => useBackendHealth());
    await waitFor(() => expect(result.current).toBe('unreachable'));
  });
});
