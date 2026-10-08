import { expect, type Page } from '@playwright/test';

export async function dismissSafetyDisclaimer(page: Page): Promise<void> {
  const dialog = page.locator('[role="dialog"][aria-labelledby="safety-disclaimer-title"]');
  if (!(await dialog.isVisible().catch(() => false))) return;

  const begin = dialog.getByRole('button', { name: /begin journey/i });
  const close = dialog.getByRole('button', { name: /close/i });
  if (await begin.isVisible().catch(() => false)) {
    await begin.click();
  } else {
    await close.click();
  }
  await expect(dialog).toBeHidden({ timeout: 5_000 });
}

/**
 * Decide the cookie consent banner the way a seeker would. It is fixed to the
 * bottom edge and appears after the safety notice, so on a phone it can sit on
 * top of bottom-of-screen controls until it is dismissed.
 */
export async function dismissCookieBanner(page: Page): Promise<void> {
  const banner = page.locator('[role="dialog"][aria-label*="cookies" i]');
  try {
    await banner.waitFor({ state: 'visible', timeout: 3_000 });
  } catch {
    return;
  }
  await banner.getByRole('button', { name: /reject/i }).click();
  await expect(banner).toBeHidden({ timeout: 5_000 });
}
