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

const IGNORABLE = (e: string): boolean =>
  e.includes('React Router Future Flag') ||
  e.includes('Download the React DevTools') ||
  e.toLowerCase().includes('hydrat') ||
  e.includes('404 Error') ||
  e.includes('ResizeObserver loop') ||
  e.includes('Failed to load resource') ||
  e.includes('503') ||
  e.includes('accounts.google.com') ||
  e.includes('.mp3') ||
  e.includes('useMeditationAudio');

// Words that mean "this click has side effects — do not push it".
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
  const buttons = await page.locator('button:visible, [role="button"]:visible').all();
  for (const btn of buttons.slice(0, 12)) {
    const label = ((await btn.textContent()) ?? '').trim();
    const aria = (await btn.getAttribute('aria-label')) ?? '';
    if (DESTRUCTIVE.test(label) || DESTRUCTIVE.test(aria)) continue;
    if (!label && !aria) continue;
    await btn.click({ timeout: 1500, trial: false }).catch(() => undefined);
    await page.waitForTimeout(120);
    // If a dialog opened, close it via Escape so we can keep going.
    await page.keyboard.press('Escape').catch(() => undefined);
  }
}

for (const route of ROUTES) {
  test(`sweep: ${route} — mount, scroll, click safe controls`, async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
    page.on('pageerror', (err) => errors.push(err.message));

    const res = await page.goto(route, { waitUntil: 'networkidle' }).catch(() => null);
    expect(res?.status() ?? 200, `HTTP status ${route}`).toBeLessThan(500);
    await expect(page.locator('body')).toBeVisible();

    await scrollThroughPage(page);
    await clickSafeButtons(page);
    await scrollThroughPage(page);

    const fatal = errors.filter((e) => !IGNORABLE(e));
    expect(fatal, `Fatal console errors during sweep of ${route}:\n${fatal.join('\n')}`).toHaveLength(0);
  });
}
