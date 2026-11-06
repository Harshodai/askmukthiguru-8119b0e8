/**
 * Accessibility checks for states the route-level smoke test never reaches
 * (NEW-A11Y-1 to 9). Each test maps to an AC-A11Y row in
 * audits/audit-output-2026-11-04/specifications/ACCESSIBILITY_AUDIT_AND_REQUIREMENTS.md.
 *
 * Network is blocked, so these run against the built frontend alone. Anything
 * that needs a real backend or Supabase session is out of scope here.
 */
import AxeBuilder from '@axe-core/playwright';
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

// --- AC-A11Y-2: axe on states the empty page never shows -----------------------

async function auditStates(page: Page, label: string) {
  await page
    .waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running'), undefined, {
      timeout: 5_000,
    })
    .catch(() => undefined);
  await page.waitForTimeout(500); // framer-motion entrances are not always in getAnimations()
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .disableRules(['frame-title', 'color-contrast-enhanced'])
    .exclude('iframe')
    .analyze();
  const blocking = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  const text = blocking
    .map((v) => `[${v.impact}] ${v.id}: ${v.nodes.slice(0, 3).map((n) => JSON.stringify(n.target)).join(' ')}`)
    .join('\n');
  expect(blocking, `${label}: serious/critical axe violations\n${text}`).toHaveLength(0);
}

async function sendQuestion(page: Page, text: string) {
  const box = page.getByRole('textbox', { name: /your message/i });
  await box.fill(text);
  await box.press('Enter');
}

test('AC-A11Y-2d: the error card has no serious or critical violations', async ({ page }) => {
  await openChat(page, { consent: 'rejected' });
  await page.unroute('**/api/**');
  await page.route(/\/api\/chat/, (r) =>
    r.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"boom"}' }),
  );
  await sendQuestion(page, 'What is the nature of attention?');
  await expect(page.getByTestId('error-care-line').first()).toBeVisible({ timeout: 15_000 });
  await auditStates(page, 'error card');
});

test('AC-A11Y-2b: the abstain answer has no serious or critical violations', async ({ page }) => {
  await openChat(page, { consent: 'rejected' });
  await page.unroute('**/api/**');
  await page.route(/\/api\/chat/, (r) =>
    r.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'event: message\n',
        'data: {"content": "I could not find a teaching that answers this directly."}\n\n',
        'event: done\n',
        'data: {"intent": "FACTUAL", "citations": [], "meditation_step": 0, "grounding_state": "abstained"}\n\n',
        'data: [DONE]\n\n',
      ].join(''),
    }),
  );
  await sendQuestion(page, 'What is the capital of France?');
  await expect(page.getByText(/could not find a teaching/i).first()).toBeVisible({ timeout: 15_000 });
  await auditStates(page, 'abstain answer');
});
