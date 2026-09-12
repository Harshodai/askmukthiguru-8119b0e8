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

    // The dialog fades in. axe samples computed colours, so running it mid
    // transition measures a BLEND of the start and end colours and reports a
    // contrast failure for a pair that never renders — observed as
    // "#4b4740 on #cea43d" (3.95:1) while the settled pair is #211c12 on
    // #fbbd23. Wait for the dialog's own entrance animations to finish.
    //
    // Scoped to the dialog and to FINITE animations on purpose: the landing
    // page runs looping ambient animations, so waiting on "nothing is running"
    // anywhere never becomes true and times out.
    await page.waitForFunction(
      () => {
        const root = document.querySelector('[role="dialog"]');
        if (!root) return false;
        return document.getAnimations().every((a) => {
          const target = (a.effect as KeyframeEffect | null)?.target;
          if (!target || !root.contains(target)) return true;
          const iterations = (a.effect as KeyframeEffect | null)?.getComputedTiming()?.iterations;
          if (iterations === Infinity) return true;
          return a.playState !== 'running';
        });
      },
      undefined,
      { timeout: 5_000 },
    );

    await expectNoSeriousA11yViolations(page);
  });
});
