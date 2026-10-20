import { renderHook, waitFor } from '@testing-library/react';
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

  it('does not request a protected teaching when signed out', async () => {
    getSession.mockResolvedValue({ data: { session: null } });
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const { result } = renderHook(() => useBreathTeaching('serene_mind'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.current.error).toBe(false);
  });
});
