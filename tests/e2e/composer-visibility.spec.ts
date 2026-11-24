import { test, expect } from '@playwright/test';
import { dismissSafetyDisclaimer } from './support';

/**
 * Pins both composer-disappearance fixes (see
 * .claude/tasks/composer-disappearance-fix.md):
 *  1. ChatPage must not hide the composer behind a full-screen spinner while
 *     the anon-session mint waits on a cold/hung backend.
 *  2. The sticky footer card stack is capped so a tall stack (healing card,
 *     quota prompt, queue tray) on a short viewport can never push the
 *     composer below the overflow-hidden fold.
 */

async function seedLanding(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem('askmukthiguru_tour_completed', '1');
    localStorage.setItem('askmukthiguru_consent_v1', 'rejected');
    localStorage.setItem('askmukthiguru_disclaimer_accepted', 'true');
  });
}

test.describe('Composer visibility', () => {
  test('renders the composer even when anon-session never resolves', async ({ page }) => {
    await seedLanding(page);
    // A cold backend behaves like this: the mint request hangs with no response.
    await page.route('**/api/auth/anon-session', () => {
      /* hold open for the whole test */
    });
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });

    const textarea = page.getByRole('textbox', { name: /your message/i });
    await expect(textarea).toBeVisible({ timeout: 5000 });
    // Auth is still unresolved — the UI must be usable anyway.
    await expect(page.getByText(/loading your session/i)).toHaveCount(0);
  });

  test('tall footer stack never pushes the composer out of the viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 480 });
    await seedLanding(page);
    await page.route('**/api/chat**', (r) => r.abort());
    await page.goto('/chat', { waitUntil: 'domcontentloaded' });
    await dismissSafetyDisclaimer(page);

    // Move to chat mode so the sticky footer composer mounts.
    const textarea = page.getByRole('textbox', { name: /your message/i });
    await textarea.fill('hello');
    await textarea.press('Enter');
    await expect(textarea).toBeVisible();

    // Inject a card stack taller than the viewport where the healing card /
    // quota / queue render (inside the footer, above the composer).
    await page.evaluate(() => {
      const ta = document.querySelector('textarea[name="message"]');
      const composer = ta?.closest('form')?.parentElement; // PromptInput wrapper
      const shrinkWrap = composer?.parentElement; // shrink-0 wrapper
      const footer = shrinkWrap?.parentElement;
      const cards = footer?.firstElementChild;
      if (!cards || !composer) throw new Error('footer structure not found');
      const fake = document.createElement('div');
      fake.id = 'tall-footer-stack';
      fake.style.cssText = 'height:800px;border:1px solid red;border-radius:16px';
      cards.insertBefore(fake, cards.firstChild);
    });

    const box = await textarea.boundingBox();
    const viewport = page.viewportSize();
    expect(box, 'composer must be rendered').toBeTruthy();
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height);
    expect(box!.y).toBeGreaterThanOrEqual(0);
  });
});
