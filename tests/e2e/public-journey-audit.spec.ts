import { test, expect, type Page } from '@playwright/test';
import { dismissSafetyDisclaimer } from './support';

const PHONE   = { width: 390, height: 844 };
const DESKTOP = { width: 1440, height: 900 };

const PUBLIC_ROUTES = [
  '/',
  '/practices',
  '/practices/serene-mind',
  '/practices/wisdom-reflection',
  '/practices/soul-sync',
  '/practices/beautiful-state',
  '/knowledge-graph',
  '/wisdom-map',
  '/notebooks',
  '/second-brain',
  '/guides',
  '/guides/spirit-guides',
  '/guides/ai-spiritual-companion',
  '/guides/beautiful-state-meditation',
  '/guides/serene-mind-practice',
  '/guides/self-centric-thinking',
  '/guides/spiritual-guide-for-anxiety',
  '/guides/suffering-to-beautiful-state',
  '/auth',
  '/reset-password',
  '/privacy',
  '/terms',
  '/this-route-does-not-exist',
] as const;

async function preparePage(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('askmukthiguru_tour_completed', '1');
    localStorage.setItem('askmukthiguru_consent_v1', 'rejected');
  });
  await page.route('**/realtime/v1/websocket**', (r) => r.abort());
  await page.route('**/supabase.co/realtime/**', (r) => r.abort());
}

async function hasHorizontalOverflow(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    return Array.from(document.querySelectorAll('*')).some((el) => {
      const e = el as HTMLElement;
      if (e.scrollWidth <= e.clientWidth + 2) return false;
      if (e.clientWidth === 0) return false;
      const s = getComputedStyle(e);
      return s.overflowX !== 'hidden' && s.overflowX !== 'auto' && s.overflowX !== 'clip';
    });
  });
}

function isFatal(e: string): boolean {
  const safelist = [
    'React Router Future Flag',
    'Download the React DevTools',
    'hydrat',
    'Failed to load resource',
    'Failed to preconnect',
    '[GSI_LOGGER]',
    '__cf_bm',
    '/realtime/v1/websocket',
    'useMeditationAudio',
    '.mp3',
    'net::ERR_ABORTED',
    'net::ERR_FAILED',
    'supabase',
    'accounts.google.com',
    'ERR_CONNECTION_REFUSED',
  ];
  return !safelist.some((pat) => e.toLowerCase().includes(pat.toLowerCase()));
}

for (const viewport of [PHONE, DESKTOP]) {
  const vpLabel = viewport.width < 800 ? 'phone' : 'desktop';

  test.describe(`Route audit — ${vpLabel}`, () => {
    for (const route of PUBLIC_ROUTES) {
      test(`${route}`, async ({ page }) => {
        const errors: string[] = [];
        page.on('pageerror', (e) => errors.push(e.message));
        page.on('console', (m) => {
          if (m.type() === 'error') errors.push(m.text());
        });

        await page.setViewportSize(viewport);
        await preparePage(page);
        await page.goto(route, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await dismissSafetyDisclaimer(page);

        await expect(page.locator('body')).toBeVisible();

        const fatal = errors.filter(isFatal);
        expect(fatal, `Fatal errors on ${route} [${vpLabel}]:\n${fatal.join('\n')}`).toHaveLength(0);

        const overflow = await hasHorizontalOverflow(page);
        expect(overflow, `Horizontal overflow on ${route} [${vpLabel}]`).toBe(false);

        const hasContent = await page.locator('h1, h2, main, [role="main"]').count() > 0;
        expect(hasContent, `No landmark content on ${route} [${vpLabel}]`).toBe(true);
      });
    }
  });
}

test.describe('Public navigation flows', () => {
  test('landing hero CTA navigates to /chat', async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await preparePage(page);
    await page.goto('/');
    await dismissSafetyDisclaimer(page);
    const cta = page.getByRole('link', { name: /ask your first question|start chat/i }).last();
    await expect(cta).toBeVisible();
    await cta.click();
    await expect(page).toHaveURL(/\/chat/);
    await expect(page.getByRole('textbox', { name: /your message/i })).toBeVisible();
  });

  test('practices list shows heading, Serene Mind card links to detail', async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await preparePage(page);
    await page.goto('/practices');
    await dismissSafetyDisclaimer(page);
    await expect(page.locator('h1, h2').first()).toBeVisible();
    const practiceLink = page.getByRole('link').filter({ hasText: /serene mind/i }).first();
    if (await practiceLink.count() > 0) {
      await practiceLink.click();
      await expect(page.locator('h1, h2').first()).toBeVisible({ timeout: 8_000 });
    }
  });

  test('/second-brain signed-out: heading present, no raw error text', async ({ page }) => {
    await page.setViewportSize(PHONE);
    await preparePage(page);
    await page.goto('/second-brain');
    await dismissSafetyDisclaimer(page);
    const bodyText = await page.locator('body').innerText();
    expect(bodyText).not.toMatch(/uncaught error|500|unexpected.*error/i);
    await expect(page.locator('h1, h2, [role="heading"]').first()).toBeAttached({ timeout: 8_000 });
  });

  test('/knowledge-graph renders SVG, canvas, or fallback heading', async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await preparePage(page);
    await page.route('**/api/**', (r) => r.abort());
    await page.goto('/knowledge-graph');
    await dismissSafetyDisclaimer(page);
    const hasSvg = await page.locator('svg').count() > 0;
    const hasCanvas = await page.locator('canvas').count() > 0;
    const hasHeading = await page.locator('h1, h2').count() > 0;
    expect(hasSvg || hasCanvas || hasHeading, 'No content on /knowledge-graph').toBeTruthy();
  });

  test('404 page has a heading and a return link', async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await preparePage(page);
    await page.goto('/this-route-does-not-exist');
    await dismissSafetyDisclaimer(page);
    await expect(page.locator('h1, h2').first()).toBeAttached({ timeout: 5_000 });
    const homeLink = page.getByRole('link', { name: /home|chat|back/i }).first();
    await expect(homeLink).toBeVisible();
  });

  test('phone: sidebar hidden, chat textarea visible', async ({ page }) => {
    await page.setViewportSize(PHONE);
    await preparePage(page);
    await page.route('**/api/**', (r) => r.abort());
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await dismissSafetyDisclaimer(page);
    const sidebar = page.locator('[data-testid="desktop-sidebar"]');
    if (await sidebar.count() > 0) {
      const box = await sidebar.boundingBox();
      if (box) expect(box.width).toBeLessThan(2);
    }
    await expect(page.getByRole('textbox', { name: /your message/i })).toBeVisible();
  });

  test('auth page: forgot password is accessible', async ({ page }) => {
    await page.setViewportSize(PHONE);
    await preparePage(page);
    await page.goto('/auth');
    await dismissSafetyDisclaimer(page);
    const forgot = page.getByRole('button', { name: /forgot/i })
      .or(page.getByText(/forgot password/i).first());
    if (await forgot.count() > 0) {
      await expect(forgot.first()).toBeVisible();
    }
  });
});
