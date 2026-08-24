import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const seriousOrCritical = ['serious', 'critical'];

async function waitForSettledLanding(page: import('@playwright/test').Page) {
  // The navbar animates from opacity 0. Axe otherwise samples the page during
  // that transition and reports blended colors that users never encounter.
  await expect(page.locator('nav').first()).toHaveCSS('opacity', '1');
}

async function expectNoSeriousA11yViolations(page: import('@playwright/test').Page) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();

  const blocking = results.violations.filter((violation) =>
    seriousOrCritical.includes(violation.impact ?? ''),
  );
  expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
}

test.describe('landing accessibility', () => {
  test('hero has no serious WCAG 2 A/AA violations', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading').first()).toBeVisible();
    await waitForSettledLanding(page);

    await expectNoSeriousA11yViolations(page);
  });

  test('interactive product demo action has an accessible dialog', async ({ page }) => {
    await page.goto('/');
    await waitForSettledLanding(page);
    await page.getByRole('button', { name: /see how askmukthiguru works/i }).first().click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('button', { name: /close tour/i })).toBeVisible();
    await expect(dialog.getByRole('button', { name: /next tour step/i })).toBeVisible();

    await expectNoSeriousA11yViolations(page);
  });
});
