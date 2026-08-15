/**
 * Progressive anonymous access route contracts.
 *
 * - Public content pages render without redirecting to /auth.
 * - /chat mounts for anonymous users (with optional-auth hook).
 * - Static file extensions are served directly, not rewritten to index.html.
 */
import { test, expect } from '@playwright/test';

const PUBLIC_CONTENT_ROUTES = [
  '/practices',
  '/practices/serene-mind',
  '/guides/serene-mind-practice',
  '/guides/beautiful-state-meditation',
  '/guides/spirit-guides',
  '/guides/ai-spiritual-companion',
  '/guides/self-centric-thinking',
  '/guides/spiritual-guide-for-anxiety',
  '/guides/suffering-to-beautiful-state',
];

for (const route of PUBLIC_CONTENT_ROUTES) {
  test(`public page renders without auth redirect: ${route}`, async ({ page }) => {
    await page.goto(route, { waitUntil: 'networkidle' });
    const finalPathname = new URL(page.url()).pathname;
    expect(finalPathname, `expected ${route} but redirected to ${finalPathname}`).toBe(route);
    await expect(page.locator('body')).toBeVisible();
    // PublicShell always renders the marketing footer.
    await expect(page.locator('footer, [class*="footer"]').first()).toBeVisible();
  });
}

test('chat route mounts without auth redirect for anonymous users', async ({ page }) => {
  await page.goto('/chat', { waitUntil: 'networkidle' });
  const finalPathname = new URL(page.url()).pathname;
  expect(finalPathname).toBe('/chat');
  await expect(page.locator('body')).toBeVisible();
});

test('static js/css files are served directly, not rewritten to index.html', async ({ page }) => {
  // Vite build produces hashed assets. Request a non-existent static file and
  // assert the server returns 404 for the file itself, not 200 HTML fallback.
  const res = await page.request.get('/assets/nonexistent-12345.js');
  expect(res.status()).toBe(404);
});

test('responsive public page on mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/practices', { waitUntil: 'networkidle' });
  await expect(page.locator('body')).toBeVisible();
  // Sanity: no horizontal overflow from unintended full-width elements.
  const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
  expect(bodyWidth).toBeLessThanOrEqual(390);
});
