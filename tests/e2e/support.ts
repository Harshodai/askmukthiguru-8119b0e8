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
