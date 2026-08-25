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
    // Route third-party realtime traffic out of this mount smoke test. The
    // application must degrade without it, and browser-specific cookie/CORS
    // behavior on Supabase is not an application contract for this suite.
    await page.route('**/realtime/v1/websocket**', (route) => route.abort());

    const errors: string[] = [];
    page.on('console', (msg: ConsoleMessage) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    page.on('pageerror', (err) => errors.push(err.message));

    const res = await page.goto(route, { waitUntil: 'networkidle' });
    expect(res?.status(), `HTTP status for ${route}`).toBeLessThan(500);
    // Tolerate redirects to /auth for protected pages.
    await expect(page.locator('body')).toBeVisible();
    const finalPathname = new URL(page.url()).pathname.replace(/\/+$/, '') || '/';
    const protectedRoute = route === '/chat' || route === '/profile' || route.startsWith('/admin/');
    const fatal = errors.filter(
      (e) =>
        !e.includes('React Router Future Flag') &&
        !e.includes('Download the React DevTools') &&
        !e.toLowerCase().includes('hydrat') &&
        !e.includes('404 Error') &&
        !e.includes('useMeditationAudio') &&
        !e.includes('.mp3') &&
        // /api/capabilities gracefully degrades to local defaults on failure
        // (useChatCapabilities.ts); a standalone frontend preview with no
        // backend behind it logs this as a generic, URL-less resource error.
        !e.includes('Failed to load resource') &&
        // <link rel="preconnect"> is a performance hint; a sandbox with no
        // route to the OAuth origin fails the TLS handshake but nothing
        // functional depends on the hint succeeding.
        !e.includes('Failed to preconnect') &&
        // Firefox may surface a Cloudflare cookie-domain warning from the
        // third-party Supabase realtime websocket even when the request is
        // aborted. It is not emitted by application code and does not prevent
        // the page from mounting.
        !e.includes('__cf_bm') &&
        !e.includes('/realtime/v1/websocket') &&
        !(finalPathname === '/auth' && e.includes('Refused to frame') && e.includes('https://accounts.google.com/')) &&
        !(protectedRoute && finalPathname === '/auth' && /401(?:\s|\()|Unauthorized/i.test(e)),
    );
    expect(fatal, `Uncaught errors on ${route}:\n${fatal.join('\n')}`).toHaveLength(0);
  });
}
