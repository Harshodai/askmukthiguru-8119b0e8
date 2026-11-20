import { describe, it, expect, vi, beforeEach } from 'vitest';

// Live 2026-11-19: ~17 identical GET /api/profile per page load, one per
// mounted useProfile() hook. Concurrent callers must share one request.
vi.mock('@/lib/backendUrl', () => ({ BACKEND_URL: 'https://backend.test' }));
vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: vi.fn(async () => ({
        data: { session: { access_token: 't', user: { user_metadata: {} } } },
      })),
    },
  },
}));

import { fetchProfileFromServer } from '@/lib/profileStorage';

describe('fetchProfileFromServer', () => {
  beforeEach(() => localStorage.clear());

  it('shares one in-flight request between concurrent callers', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ preferred_language: 'en' }), {
          headers: { 'content-type': 'application/json' },
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await Promise.all([fetchProfileFromServer(), fetchProfileFromServer(), fetchProfileFromServer()]);
    // loadProfile() may also PUT a seeded default profile; count only GETs.
    const gets = () => (fetchMock.mock.calls as unknown[][]).filter((c) => !(c[1] as RequestInit | undefined)?.method).length;
    expect(gets()).toBe(1);

    // A later call (after the first settled) fetches again.
    await fetchProfileFromServer();
    expect(gets()).toBe(2);
    vi.unstubAllGlobals();
  });
});
