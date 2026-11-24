import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getAnonSessionToken } from '@/lib/chat/anonSession';

// Anonymous minting only happens when Supabase has no session.
vi.mock('@/lib/chat/auth', () => ({
  getAccessToken: vi.fn(async () => null),
}));

describe('getAnonSessionToken', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('mints with a bounded AbortSignal so a hung backend cannot stall auth', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true,
      json: async () => ({ token: 'signed-token' }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const token = await getAnonSessionToken();

    expect(token).toBe('signed-token');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0][1];
    expect(init?.signal).toBeInstanceOf(AbortSignal);
  });

  it('returns null when the mint fails instead of throwing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('terminated');
      }),
    );

    await expect(getAnonSessionToken()).resolves.toBeNull();
  });
});
