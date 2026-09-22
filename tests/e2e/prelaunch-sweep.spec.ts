/**
 * Pre-launch sweep: for every critical route, mount the page, scroll to
 * the bottom, and click every visible non-destructive button/link.
 * Asserts no uncaught console errors accumulate.
 *
 * This is the "would a curious user break it in 30 seconds?" check.
 * It complements the intent-driven specs (seeker-journey, full-regression)
 * with a brute-force interaction pass modeled on how large web products
 * (Shopify, Vercel, Linear) run a nightly Playwright regression: visit
 * everything, click everything safe, screenshot on failure.
 *
 * Run:  npm run test:e2e -- prelaunch-sweep
 */
import { test, expect, type Page } from '@playwright/test';
import { dismissSafetyDisclaimer } from './support';

const ROUTES = [
  '/',
  '/auth',
  '/practices',
  '/practices/serene-mind',
  '/knowledge-graph',
  '/second-brain',
  '/chat',
  '/profile',
  '/privacy',
  '/terms',
];

const isGoogleOrYouTubeAccountUrl = (message: string): boolean => {
  const urls = message.match(/https?:\/\/[^\s"'`<>]+/g);
  if (!urls) return false;
  return urls.some((raw) => {
    try {
      const { hostname } = new URL(raw);
      return hostname === 'accounts.google.com' || hostname === 'accounts.youtube.com';
    } catch {
      return false;
    }
  });
};

const isCiMockSupabaseError = (message: string): boolean =>
  // The E2E build deliberately uses an unreachable mock Supabase hostname.
  // Chromium/WebKit surface this as websocket errors, DNS errors, or fetch
  // access-control diagnostics depending on browser/version. Keep the match
  // constrained to the known mock hostname so real Supabase failures still
  // fail the sweep.
  message.includes('mock-supabase.supabase.co') &&
  (
    message.includes('ERR_NAME_NOT_RESOLVED') ||
    message.includes('Error resolving') ||
    message.includes('due to access control checks')
  );

const isCiOAuthPreconnectError = (message: string): boolean =>
  message.includes('Failed to preconnect to https://oauth.askmukthiguru.lovable.app/');

const IGNORABLE = (e: string): boolean =>
  e.includes('React Router Future Flag') ||
  e.includes('Download the React DevTools') ||
  e.toLowerCase().includes('hydrat') ||
  e.includes('404 Error') ||
  e.includes('ResizeObserver loop') ||
  e.includes('Failed to load resource') ||
  e.includes('503') ||
  isGoogleOrYouTubeAccountUrl(e) ||
  isCiMockSupabaseError(e) ||
  isCiOAuthPreconnectError(e) ||
  e.includes('requestStorageAccess: Permission denied.') ||
  e.includes('.mp3') ||
  e.includes('useMeditationAudio');

const APP_ORIGIN = new URL(process.env.BASE_URL || 'http://localhost:4173').origin;

const DESTRUCTIVE = /sign\s*out|log\s*out|delete|remove|clear|reset|cancel|leave|discard/i;

async function scrollThroughPage(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const step = window.innerHeight * 0.9;
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 60));
    }
    window.scrollTo(0, 0);
  });
}

async function clickSafeButtons(page: Page): Promise<void> {
  const buttons = page.locator('button:visible, [role="button"]:visible');
  const count = Math.min(await buttons.count(), 12);
  const targets: Array<{ index: number; label: string; aria: string }> = [];

  for (let index = 0; index < count; index += 1) {
    const button = buttons.nth(index);
    const label = ((await button.textContent({ timeout: 1500 }).catch(() => '')) ?? '').trim();
    const aria = (await button.getAttribute('aria-label', { timeout: 1500 }).catch(() => '')) ?? '';
    targets.push({ index, label, aria });
  }

  for (const target of targets) {
    if (DESTRUCTIVE.test(target.label) || DESTRUCTIVE.test(target.aria)) continue;
    if (!target.label && !target.aria) continue;
    await buttons.nth(target.index).click({ timeout: 1500 }).catch(() => undefined);
    await page.waitForTimeout(120);
    await page.keyboard.press('Escape').catch(() => undefined);
  }
}

for (const route of ROUTES) {
  test(`sweep: ${route} — mount, scroll, click safe controls`, async ({ page }) => {
    const errors: string[] = [];
    const serverErrors: string[] = [];
    const origin = APP_ORIGIN;
    page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
    page.on('pageerror', (err) => errors.push(err.message));
    page.on('response', (response) => {
      if (new URL(response.url()).origin === origin && response.status() >= 500) {
        serverErrors.push(`${response.status()} ${response.url()}`);
      }
    });

    const res = await page.goto(route, { waitUntil: 'networkidle' }).catch(() => null);
    await dismissSafetyDisclaimer(page);
    expect(res?.status() ?? 200, `HTTP status ${route}`).toBeLessThan(500);
    await expect(page.locator('body')).toBeVisible();

    await scrollThroughPage(page);
    await clickSafeButtons(page);
    await scrollThroughPage(page);

    const fatal = errors.filter((e) => !IGNORABLE(e));
    expect(serverErrors, `Same-origin 5xx responses during sweep of ${route}:\n${serverErrors.join('\n')}`).toHaveLength(0);
    expect(fatal, `Fatal console errors during sweep of ${route}:\n${fatal.join('\n')}`).toHaveLength(0);
  });
}
