/**
 * Accessibility checks for states the route-level smoke test never reaches
 * (NEW-A11Y-1 to 9). Each test maps to an AC-A11Y row in
 * audits/audit-output-2026-11-04/specifications/ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md.
 *
 * Network is blocked, so these run against the built frontend alone. Anything
 * that needs a real backend or Supabase session is out of scope here.
 */
import { test, expect, type Page } from '@playwright/test';
import { dismissSafetyDisclaimer } from './support';

async function openChat(page: Page, opts: { consent?: 'rejected' | null } = {}) {
  await page.addInitScript((consent) => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem('askmukthiguru_tour_completed', '1');
    if (consent) localStorage.setItem('askmukthiguru_consent_v1', consent);
  }, opts.consent ?? null);
  await page.route('**/api/**', (r) => r.abort());
  await page.route('**/realtime/v1/**', (r) => r.abort());
  await page.route('**/supabase.co/**', (r) => r.abort());
  await page.goto('/chat', { waitUntil: 'domcontentloaded' });
  await dismissSafetyDisclaimer(page);
}

test('AC-A11Y-10: the cookie banner does not cover Send at 390 px', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await openChat(page);
  const banner = page.locator('[role="dialog"][aria-label*="cookies" i]');
  await expect(banner).toBeVisible({ timeout: 10_000 });
  // Let the entrance animation finish so the geometry is the resting one.
  await page.waitForTimeout(600);

  await page.getByRole('textbox', { name: /your message/i }).fill('hello');
  const send = page.getByRole('button', { name: /^send message$/i });
  await expect(send).toBeVisible();
  const box = (await send.boundingBox())!;
  const topmost = await page.evaluate(
    ([x, y]) => {
      const el = document.elementFromPoint(x, y);
      return !!el?.closest('button[aria-label="Send message"]');
    },
    [box.x + box.width / 2, box.y + box.height / 2],
  );
  expect(topmost, 'the cookie banner sits on top of the Send button').toBe(true);
});
