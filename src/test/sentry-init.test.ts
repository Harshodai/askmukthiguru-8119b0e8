/**
 * P1-FE-5 unit tests: Sentry init gate (DSN + production build).
 *
 * Substituted for tests/e2e/sentry-init.spec.ts — the e2e harness needs a
 * running dev server (BASE_URL) and cannot mock import.meta.env/DSN; mocking
 * @sentry/react + web-vitals under vitest/jsdom covers the same gate with
 * deterministic assertions.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { mockSentry, mockWebVitals } = vi.hoisted(() => ({
  mockSentry: {
    init: vi.fn(),
    addBreadcrumb: vi.fn(),
    captureException: vi.fn(),
    withScope: vi.fn((cb: (scope: unknown) => void) =>
      cb({ setTag: vi.fn(), setContext: vi.fn() }),
    ),
    browserTracingIntegration: vi.fn(() => ({ name: 'browserTracing' })),
    replayIntegration: vi.fn(() => ({ name: 'replay' })),
  },
  mockWebVitals: {
    onLCP: vi.fn(),
    onINP: vi.fn(),
    onCLS: vi.fn(),
    onFCP: vi.fn(),
    onTTFB: vi.fn(),
  },
}));

vi.mock('@sentry/react', () => ({ ...mockSentry }));
vi.mock('web-vitals', () => ({ ...mockWebVitals }));

async function loadSentry() {
  return import('@/lib/sentry');
}

async function loadWebVitals() {
  return import('@/lib/webVitals');
}

const DSN = 'https://abc@sentry.io/123';

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.resetModules();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('sentryEnabled gate (VITE_SENTRY_DSN + PROD)', () => {
  it('disabled when no DSN configured, even in a prod build', async () => {
    vi.stubEnv('PROD', true);
    const { sentryEnabled } = await loadSentry();
    expect(sentryEnabled()).toBe(false);
  });

  it('disabled when DSN set but not a prod build', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', DSN);
    const { sentryEnabled } = await loadSentry();
    expect(sentryEnabled()).toBe(false);
  });

  it('enabled only when DSN set AND prod build', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', DSN);
    vi.stubEnv('PROD', true);
    const { sentryEnabled } = await loadSentry();
    expect(sentryEnabled()).toBe(true);
  });
});

describe('initSentry', () => {
  it('calls Sentry.init with the DSN when enabled (Railway host or native WebView)', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', DSN);
    vi.stubEnv('PROD', true);
    const { initSentry } = await loadSentry();
    initSentry();
    expect(mockSentry.init).toHaveBeenCalledTimes(1);
    expect(mockSentry.init).toHaveBeenCalledWith(expect.objectContaining({ dsn: DSN }));
  });

  it('does not call Sentry.init when disabled', async () => {
    const { initSentry } = await loadSentry();
    initSentry();
    expect(mockSentry.init).not.toHaveBeenCalled();
  });
});

describe('trackPageview', () => {
  it('adds a breadcrumb only when enabled', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', DSN);
    vi.stubEnv('PROD', true);
    const { trackPageview } = await loadSentry();
    trackPageview('/chat');
    expect(mockSentry.addBreadcrumb).toHaveBeenCalledTimes(1);
  });

  it('no-ops when disabled', async () => {
    const { trackPageview } = await loadSentry();
    trackPageview('/chat');
    expect(mockSentry.addBreadcrumb).not.toHaveBeenCalled();
  });
});

describe('captureFeatureError', () => {
  it('reports to Sentry with a feature tag when enabled', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', DSN);
    vi.stubEnv('PROD', true);
    const { captureFeatureError } = await loadSentry();
    const err = new Error('boom');
    captureFeatureError(err, 'chat', { q: 'x' });
    expect(mockSentry.withScope).toHaveBeenCalledTimes(1);
    expect(mockSentry.captureException).toHaveBeenCalledWith(err);
  });

  it('falls back to console.error when disabled', async () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { captureFeatureError } = await loadSentry();
    captureFeatureError(new Error('boom'), 'chat');
    expect(mockSentry.captureException).not.toHaveBeenCalled();
    expect(errSpy).toHaveBeenCalled();
  });
});

describe('initWebVitals (same DSN+PROD gate)', () => {
  it('does not register web-vitals listeners when Sentry disabled', async () => {
    const { initWebVitals } = await loadWebVitals();
    initWebVitals();
    for (const fn of Object.values(mockWebVitals)) {
      expect(fn).not.toHaveBeenCalled();
    }
  });

  it('registers web-vitals listeners when Sentry enabled', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', DSN);
    vi.stubEnv('PROD', true);
    const { initWebVitals } = await loadWebVitals();
    initWebVitals();
    expect(mockWebVitals.onLCP).toHaveBeenCalledTimes(1);
    expect(mockWebVitals.onINP).toHaveBeenCalledTimes(1);
    expect(mockWebVitals.onCLS).toHaveBeenCalledTimes(1);
    expect(mockWebVitals.onFCP).toHaveBeenCalledTimes(1);
    expect(mockWebVitals.onTTFB).toHaveBeenCalledTimes(1);
  });
});
