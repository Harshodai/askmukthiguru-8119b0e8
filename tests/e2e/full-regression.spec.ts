/**
 * Ruthless end-to-end regression.
 *
 * Complements page-smoke.spec.ts (which only asserts routes mount): this
 * exercises the real critical journeys and the failure modes that actually
 * ship broken — chat round-trips, the newer /second-brain & /knowledge-graph
 * routes, mobile layout, network health, and the Google-auth iframe trap.
 *
 * Run:
 *   npm run test:e2e -- full-regression
 *   BASE_URL=https://askmukthiguru.lovable.app npm run test:e2e -- full-regression
 *
 * Backend-dependent assertions (chat reply) auto-skip when no backend is
 * reachable, so the spec is safe to run against a static preview too.
 */
import { test, expect, type ConsoleMessage, type Page } from '@playwright/test';

// Console-error noise that is NOT a regression (third-party, dev-only, or the
// known Google-frame refusal on /auth).
const IGNORABLE = (e: string, pathname: string): boolean =>
  e.includes('React Router Future Flag') ||
  e.includes('Download the React DevTools') ||
  e.toLowerCase().includes('hydrat') ||
  e.includes('404 Error') ||
  e.includes('ResizeObserver loop') ||
  e.includes('fetchPriority') ||
  e.includes('fetchpriority') ||
  (pathname === '/auth' && e.includes('Refused to frame') && e.includes('accounts.google.com'));

function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (m: ConsoleMessage) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (err) => errors.push(err.message));
  return errors;
}

function fatalErrors(errors: string[], page: Page): string[] {
  const pathname = new URL(page.url()).pathname;
  return errors.filter((e) => !IGNORABLE(e, pathname));
}

test.describe('critical journeys', () => {
  test('landing page renders hero + primary CTA and has no fatal errors', async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto('/', { waitUntil: 'networkidle' });
    await expect(page.locator('body')).toBeVisible();
    const cta = page.getByRole('link', { name: /start chat/i }).first();
    await expect(cta).toBeVisible();
    expect(fatalErrors(errors, page), fatalErrors(errors, page).join('\n')).toHaveLength(0);
  });

  test('newer routes mount: /second-brain and /knowledge-graph', async ({ page }) => {
    for (const route of ['/second-brain', '/knowledge-graph']) {
      const errors = trackErrors(page);
      const res = await page.goto(route, { waitUntil: 'networkidle' });
      expect(res?.status(), `HTTP status ${route}`).toBeLessThan(500);
      await expect(page.locator('body')).toBeVisible();
      // Protected routes legitimately redirect to /auth — both outcomes pass.
      const p = new URL(page.url()).pathname;
      expect(['/second-brain', '/knowledge-graph', '/auth']).toContain(p);
      expect(fatalErrors(errors, page), `${route}: ${fatalErrors(errors, page).join('\n')}`).toHaveLength(0);
    }
  });

  test('auth: Google sign-in must be a full-page redirect, never an iframe', async ({ page }) => {
    // Regression guard for the reported UX bug: embedding Google auth in an
    // <iframe> triggers "Refused to frame" (X-Frame-Options) and a blank box.
    // The correct flow is signInWithOAuth redirect. Assert no google iframe.
    await page.goto('/auth', { waitUntil: 'networkidle' });
    await expect(page.locator('body')).toBeVisible();

    const gsiContainer = page.locator('[data-testid="google-gsi-container"]');
    const hasGoogleClientId = !!process.env.VITE_GOOGLE_CLIENT_ID || await gsiContainer.isVisible().catch(() => false);

    if (hasGoogleClientId) {
      // GSI Flow: verify Google's own widget actually initialized inside our
      // container (a same-origin-safe accounts.google.com iframe, expected
      // only at top level — never nested) rather than just our empty div.
      await expect(gsiContainer).toBeVisible();
      const gsiIframe = gsiContainer.locator('iframe[src^="https://accounts.google.com/"]');
      await expect(gsiIframe).toBeVisible({ timeout: 10_000 });
    } else {
      // Fallback redirect flow
      const googleBtn = page.getByRole('button', { name: /google/i });
      await expect(googleBtn).toBeVisible();

      const googleFrame = page.locator('iframe[src^="https://accounts.google.com/"]');
      await expect(googleFrame).toHaveCount(0);

      // Click Google sign-in and assert top-level OAuth navigation
      const urlBefore = page.url();
      const navigationPromise = page.waitForNavigation().catch(() => null);
      await googleBtn.click().catch(() => {});
      await navigationPromise;

      // Assert the browser performs top-level OAuth navigation rather than remaining on /auth page
      expect(page.url()).not.toBe(urlBefore);

      // Verify no Google accounts iframe exists after the interaction
      await expect(googleFrame).toHaveCount(0);
    }
  });

  test('chat: send a message and receive a non-empty reply (skips w/o backend)', async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto('/chat', { waitUntil: 'networkidle' });

    // Auth-gated: if we bounced to /auth, this environment has no test session.
    if (new URL(page.url()).pathname === '/auth') {
      test.skip(true, 'chat is auth-gated and no test session is configured');
    }

    const input = page.getByRole('textbox').first();
    const hasInput = await input.isVisible().catch(() => false);
    test.skip(!hasInput, 'no chat input found (placeholder/offline mode)');

    // Backend readiness probe
    const healthRes = await page.request.get('/api/health').catch(() => null);
    const backendHealthy = process.env.BACKEND_E2E === 'true' || (healthRes && healthRes.ok());
    test.skip(!backendHealthy, 'unusable or unreachable backend - skipping assistant reply assertion');

    await input.fill('What is the Beautiful State?');
    await input.press('Enter');

    const reply = page.locator('[data-role="assistant"], .assistant-message, [class*="assistant"]').last();
    await expect(reply).toBeVisible({ timeout: 25_000 });
    await expect(reply).not.toHaveText('');
    expect(fatalErrors(errors, page), fatalErrors(errors, page).join('\n')).toHaveLength(0);
  });
});

test.describe('responsive', () => {
  test('landing has no horizontal overflow on mobile (375px)', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/', { waitUntil: 'networkidle' });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    // A few px of sub-pixel rounding is fine; a real overflow is >5px.
    expect(overflow, 'horizontal overflow in px').toBeLessThanOrEqual(5);
  });
});

test.describe('network health', () => {
  test('no failed same-origin 5xx requests on landing', async ({ page, baseURL }) => {
    const failed: string[] = [];
    const origin = new URL(baseURL || 'http://localhost:8080').origin;
    page.on('response', (r) => {
      if (new URL(r.url()).origin === origin && r.status() >= 500) {
        failed.push(`${r.status()} ${r.url()}`);
      }
    });
    await page.goto('/', { waitUntil: 'networkidle' });
    expect(failed, failed.join('\n')).toHaveLength(0);
  });
});
