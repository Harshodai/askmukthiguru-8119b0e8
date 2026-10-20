import { renderHook, waitFor, act } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useBreathTeaching } from '@/hooks/useBreathTeaching';

const { getSession } = vi.hoisted(() => ({ getSession: vi.fn() }));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession } },
}));

afterEach(() => vi.restoreAllMocks());

describe('useBreathTeaching', () => {
  it('exposes an unavailable state when the verified-teaching API is down', async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: 'test-access-token' } },
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Verified teaching retrieval is unavailable.' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const { result } = renderHook(() => useBreathTeaching('serene_mind'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.teaching).toBeNull();
    expect(result.current.error).toBe(true);
  });

  it('fetches once per technique change and cancels the previous request', async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: 'test-access-token' } },
    });
    const requests: Array<{ url: string; signal: AbortSignal }> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = String(input);
      const signal = init?.signal as AbortSignal;
      requests.push({ url, signal });
      const technique = url.split('/').pop();
      return Promise.resolve(new Response(
        JSON.stringify({ teaching: `Recorded passage for ${technique}` }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ));
    });

    const { result, rerender } = renderHook(
      ({ techniqueId }) => useBreathTeaching(techniqueId),
      { initialProps: { techniqueId: 'box' } },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.teaching).toContain('box');
    expect(requests.filter((r) => r.url.endsWith('/box'))).toHaveLength(1);

    act(() => rerender({ techniqueId: '4_7_8' }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.teaching).toContain('4_7_8');
    expect(requests.filter((r) => r.url.endsWith('/4_7_8'))).toHaveLength(1);
    expect(requests).toHaveLength(2);
    expect(requests[0].signal.aborted).toBe(true);
  });

  it('does not request a protected teaching when signed out', async () => {
    getSession.mockResolvedValue({ data: { session: null } });
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const { result } = renderHook(() => useBreathTeaching('serene_mind'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.current.error).toBe(false);
  });
});
