import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { mockIsNativePlatform } = vi.hoisted(() => ({
  mockIsNativePlatform: vi.fn(() => false),
}));

vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: mockIsNativePlatform },
}));

async function loadBackendUrl() {
  return import('@/lib/backendUrl');
}
beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("VITE_BACKEND_URL", "");
  vi.stubEnv("VITE_NATIVE_BACKEND", "");
});

/** jsdom refuses hostname assignment AND history.replaceState across origins
 *  (SecurityError). Swap the location object itself — backendUrl only reads
 *  window.location.hostname. */
function setHostname(hostname: string) {
  const u = new URL(`https://${hostname}/`);
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: {
      hostname: u.hostname,
      href: u.href,
      origin: u.origin,
      protocol: u.protocol,
      host: u.host,
      pathname: u.pathname,
      search: u.search,
      hash: u.hash,
    },
  });
}

afterEach(() => {
  vi.resetModules();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  mockIsNativePlatform.mockReturnValue(false);
  setHostname('localhost');
});

describe('isProdHost (exact-match prod hostnames)', () => {
  it('matches only the exact prod hosts', async () => {
    const { isProdHost } = await loadBackendUrl();
    expect(isProdHost('askmukthiguru-8119b0e8-production.up.railway.app')).toBe(true);
  });

  it('rejects staging/preview/legacy Lovable hosts — they must not hit prod', async () => {
    const { isProdHost } = await loadBackendUrl();
    expect(isProdHost('askmukthiguru-staging.lovable.app')).toBe(false);
    expect(isProdHost('preview--askmukthiguru.lovable.app')).toBe(false);
    expect(isProdHost('askmukthiguru.lovable.app')).toBe(false);
    expect(isProdHost('localhost')).toBe(false);
    expect(isProdHost('askmukthiguru.lovable.dev')).toBe(false);
  });
});

describe('web host resolution', () => {
  it('exact prod host resolves to the Railway prod backend', async () => {
    setHostname('askmukthiguru-8119b0e8-production.up.railway.app');
    const { BACKEND_URL, PROD_RAILWAY_URL } = await loadBackendUrl();
    expect(BACKEND_URL).toBe(PROD_RAILWAY_URL);
  });

  it('legacy Lovable host does NOT resolve to prod (fail-closed to empty)', async () => {
    setHostname('askmukthiguru.lovable.app');
    const { BACKEND_URL } = await loadBackendUrl();
    expect(BACKEND_URL).toBe('');
  });

  it('staging Lovable host does NOT resolve to prod (fail-closed to empty)', async () => {
    setHostname('askmukthiguru-staging.lovable.app');
    const { BACKEND_URL } = await loadBackendUrl();
    expect(BACKEND_URL).toBe('');
  });

  it('VITE_BACKEND_URL override wins over host detection', async () => {
    vi.stubEnv('VITE_BACKEND_URL', 'https://staging.example.com');
    setHostname('askmukthiguru-8119b0e8-production.up.railway.app');
    const { BACKEND_URL } = await loadBackendUrl();
    expect(BACKEND_URL).toBe('https://staging.example.com');
  });
});

describe('native (Capacitor) resolution', () => {
  beforeEach(() => {
    mockIsNativePlatform.mockReturnValue(true);
  });

  it('uses the VITE_BACKEND_URL override first', async () => {
    vi.stubEnv('VITE_BACKEND_URL', 'https://api.example.com');
    const { BACKEND_URL } = await loadBackendUrl();
    expect(BACKEND_URL).toBe('https://api.example.com');
  });

  it('without opt-in, fails closed (empty) with a warning instead of silently hitting prod', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { BACKEND_URL } = await loadBackendUrl();
    expect(BACKEND_URL).toBe('');
    expect(warnSpy).toHaveBeenCalled();
  });

  it('VITE_NATIVE_BACKEND=prod opts native builds into the prod backend', async () => {
    vi.stubEnv('VITE_NATIVE_BACKEND', 'prod');
    const { BACKEND_URL, PROD_RAILWAY_URL } = await loadBackendUrl();
    expect(BACKEND_URL).toBe(PROD_RAILWAY_URL);
  });
});
