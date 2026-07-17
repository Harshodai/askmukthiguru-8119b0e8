/**
 * Page-open smoke test: visits every public route and confirms the page
 * mounts without an uncaught error in the console. Auth-gated routes
 * (/chat, /profile, admin/*) are expected to redirect to /auth — that's
 * still a successful "page opens" result.
 */
import { test, expect, type ConsoleMessage } from '@playwright/test';

const PUBLIC_ROUTES = [
  '/',
  '/auth',
  '/auth/diagnostics',
  '/auth/latency',
  '/reset-password',
  '/privacy',
  '/terms',
  '/practices',
  '/practices/serene-mind',
  '/chat',
  '/profile',
  '/test-tts',
  '/admin/login',
  '/this-route-does-not-exist',
];

for (const route of PUBLIC_ROUTES) {
  test(`page opens: ${route}`, async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg: ConsoleMessage) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    page.on('pageerror', (err) => errors.push(err.message));

    const res = await page.goto(route, { waitUntil: 'networkidle' });
    expect(res?.status(), `HTTP status for ${route}`).toBeLessThan(500);
    // Tolerate redirects to /auth for protected pages.
    await expect(page.locator('body')).toBeVisible();
    const finalPathname = new URL(page.url()).pathname;
    const fatal = errors.filter(
      (e) =>
        !e.includes('React Router Future Flag') &&
        !e.includes('Download the React DevTools') &&
        !e.toLowerCase().includes('hydrat') &&
        !e.includes('404 Error') &&
        !(finalPathname === '/auth' && e.includes('Refused to frame') && e.includes('https://accounts.google.com/')),
    );
    expect(fatal, `Uncaught errors on ${route}:\n${fatal.join('\n')}`).toHaveLength(0);
  });
}
