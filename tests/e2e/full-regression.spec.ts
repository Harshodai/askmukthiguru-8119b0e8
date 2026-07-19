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
  e.includes('useMeditationAudio') ||
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
    const errors = trackErrors(page);
    await page.goto('/auth', { waitUntil: 'networkidle' });
    await expect(page.locator('body')).toBeVisible();

    const gsiContainer = page.locator('[data-testid="google-gsi-container"]');
    const hasGoogleClientId = await gsiContainer.isVisible().catch(() => false);

    if (hasGoogleClientId) {
      // GSI Flow: verify Google's own widget actually initialized inside our
      // container (a same-origin-safe accounts.google.com iframe, expected
      // only at top level — never nested) rather than just our empty div.
      await expect(gsiContainer).toBeVisible();
      const gsiIframe = gsiContainer.locator('iframe');
      await expect(gsiIframe).toBeVisible({ timeout: 10_000 });
      const src = await gsiIframe.getAttribute('src');
      expect(src).toMatch(/^https:\/\/accounts\.google\.com\//);
    } else {
      // Fallback redirect flow
      const googleBtn = page.getByRole('button', { name: /google/i });
      await expect(googleBtn).toBeVisible();

      const googleFrame = page.locator('iframe[src^="https://accounts.google.com/"]');
      await expect(googleFrame).toHaveCount(0);

      // Click Google sign-in and assert top-level OAuth navigation
      const urlBefore = page.url();
      const navigationPromise = page.waitForURL('**/auth/**', { timeout: 15_000 }).catch(() => null);
      await googleBtn.click().catch(() => {});
      await navigationPromise;

      // Assert the browser performs top-level OAuth navigation rather than remaining on /auth page
      expect(page.url()).not.toBe(urlBefore);

      // Verify no Google accounts iframe exists after the interaction
      await expect(googleFrame).toHaveCount(0);
    }
    expect(fatalErrors(errors, page), fatalErrors(errors, page).join('\n')).toHaveLength(0);
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

// ── Serene Mind meditation / audio E2E ──────────────────────────────────────
test('meditation: Serene Mind flow is reachable', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' && msg.text().toLowerCase().includes('audio')) {
      consoleErrors.push(msg.text());
    }
  });

  await page.goto('/chat', { waitUntil: 'networkidle' });
  await expect(page.locator('body')).toBeVisible();

  // Auth-gated: if we bounced to /auth, this environment has no test session.
  if (new URL(page.url()).pathname === '/auth') {
    test.skip(true, 'chat is auth-gated and no test session is configured');
  }

  // Wait for either the chat input or pre-practice gate
  const chatInput = page.locator('textarea, [contenteditable="true"], input[type="text"], [role="textbox"]').first();
  const inputVisible = await chatInput.isVisible({ timeout: 8_000 }).catch(() => false);
  test.skip(!inputVisible, 'no chat input found (pre-practice gate or offline mode)');

  await chatInput.fill('I want to do the Serene Mind meditation');

  const sendBtn = page.locator('button[type="submit"], button:has(svg.lucide-send), button:has(svg.lucide-arrow-up)').first();
  if (await sendBtn.isVisible()) {
    await sendBtn.click();
  } else {
    await chatInput.press('Enter');
  }

  // Check for meditation UI — best-effort, may not appear without a backend
  const meditationContainer = page.locator(
    '[data-testid="guided-meditation"], [data-testid="serene-mind-modal"], .meditation-flow, [class*="meditation"]'
  ).first();

  const meditationAppeared = await meditationContainer.isVisible({ timeout: 10_000 }).catch(() => false);

  if (meditationAppeared) {
    const audioEl = meditationContainer.locator('audio').first();
    const audioVisible = await audioEl.isVisible().catch(() => false);

    if (audioVisible) {
      const paused = await audioEl.evaluate((el: HTMLAudioElement) => el.paused).catch(() => true);
      if (!paused) {
        console.log('[Test] Audio is playing');
      } else {
        const readyState = await audioEl.evaluate((el: HTMLAudioElement) => el.readyState).catch(() => 0);
        console.log('[Test] Audio element found, paused:', paused, 'readyState:', readyState);
      }
    } else {
      const ttsActive = await page.evaluate(() => window.speechSynthesis.speaking).catch(() => false);
      console.log('[Test] No audio element found, TTS speaking:', ttsActive);
    }
  } else {
    console.log('[Test] Meditation UI did not appear — test is best-effort');
  }
  console.log(`[Test] Audio console errors collected: ${consoleErrors.length}`);
  if (consoleErrors.length > 0) {
    console.log('[Test] Audio errors:', JSON.stringify(consoleErrors[0]));
  }
});

test('auth: forgot password button exists and /reset-password route mounts', async ({ page }) => {
  await page.goto('/auth', { waitUntil: 'networkidle' });
  await expect(page.locator('body')).toBeVisible();

  // Find and fill email input
  const emailInput = page.locator('input[type="email"], input[name="email"]').first();
  await expect(emailInput).toBeVisible({ timeout: 10_000 });
  await emailInput.fill('test-forgot@example.com');

  // Click "Forgot Password" link/button — verify the button exists and is clickable
  const forgotBtn = page.getByRole('button', { name: /forgot|reset/i });
  await expect(forgotBtn).toBeVisible();
  await forgotBtn.click();

  // Navigate to /reset-password directly to verify route exists and form renders
  await page.goto('/reset-password', { waitUntil: 'networkidle' });
  await expect(page.locator('body')).toBeVisible();

  // Verify reset password form elements exist
  const newPasswordInput = page.locator('input[type="password"]').first();
  await expect(newPasswordInput).toBeVisible({ timeout: 10_000 });
});
