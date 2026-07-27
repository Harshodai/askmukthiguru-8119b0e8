/**
 * Accessibility smoke check — axe-core against the critical routes.
 *
 * Ponytail: no page objects, no custom rule engine. axe already knows the
 * WCAG rules; we just point it at the routes a seeker actually walks and
 * fail on serious/critical violations only (moderate/minor are reported
 * but non-blocking, so the gate stays actionable).
 *
 * Run:  npx playwright test --project=chromium tests/e2e/a11y-smoke.spec.ts
 */
import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page, type BrowserContext } from '@playwright/test';

const CRITICAL_ROUTES = [
  '/',
  '/auth',
  '/chat',
  '/profile',
  '/practices',
  '/practices/serene-mind',
  '/knowledge-graph',
];

/** Routes that require an authenticated session (otherwise redirect to /auth). */
const PROTECTED_ROUTES = new Set(['/chat', '/profile', '/practices', '/practices/serene-mind', '/knowledge-graph']);

/** Rules we knowingly do not gate on (third-party iframes, animated canvas). */
const DISABLED_RULES = ['frame-title', 'color-contrast-enhanced'];

type Violation = {
  id: string;
  impact?: string | null;
  help: string;
  nodes: { target: unknown[] }[];
};

async function analyze(page: Page) {
  return new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .disableRules(DISABLED_RULES)
    .analyze();
}

function format(violations: Violation[]): string {
  return violations
    .map(
      (v) =>
        `[${v.impact ?? 'unknown'}] ${v.id} — ${v.help}\n    ` +
        v.nodes
          .slice(0, 3)
          .map((n) => JSON.stringify(n.target))
          .join('\n    '),
    )
    .join('\n');
}

/**
 * Seed a fake Supabase session so protected routes render instead of
 * redirecting to /auth. Mirrors the pattern in session-auth.spec.ts and
 * google-auth-flow.spec.ts. The key name must match the Supabase client's
 * storage key (sb-<project-ref>-auth-token).
 */
async function seedAuth(context: BrowserContext) {
  const fakeKey = 'sb-fynkjimvuimakgtidvuq-auth-token';
  await context.addInitScript((k) => {
    localStorage.setItem(
      k,
      JSON.stringify({ access_token: 'fake', refresh_token: 'fake', user: { id: 'a11y-test' } }),
    );
  }, fakeKey);
}

for (const route of CRITICAL_ROUTES) {
  test(`a11y: ${route} has no serious/critical violations`, async ({ page, context }, testInfo) => {
    if (PROTECTED_ROUTES.has(route)) {
      await seedAuth(context);
    }
    await page.goto(route, { waitUntil: 'networkidle' });
    await expect(page.locator('body')).toBeVisible();

    // Verify the page reached the intended route (not bounced to /auth for
    // protected routes). For protected routes, assert the URL is still the
    // intended route; for public routes, assert the URL matches the target.
    await expect(page).toHaveURL(new RegExp(route.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') || '^/$'), { timeout: 10_000 });

    const results = await analyze(page);
    const violations = results.violations as unknown as Violation[];
    const blocking = violations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical',
    );
    const advisory = violations.filter((v) => !blocking.includes(v));

    await testInfo.attach(`axe-${route.replace(/\W+/g, '_') || 'root'}.json`, {
      body: JSON.stringify(violations, null, 2),
      contentType: 'application/json',
    });

    if (advisory.length) {
      console.log(`ℹ️ advisory a11y findings on ${route}:\n${format(advisory)}`);
    }

    expect(
      blocking,
      `Serious/critical accessibility violations on ${route}:\n${format(blocking)}`,
    ).toHaveLength(0);
  });
}

test('a11y: meditation flow (Serene Mind player) is accessible once opened', async ({
  page,
}, testInfo) => {
  await page.goto('/practices/serene-mind', { waitUntil: 'networkidle' });

  // The start control (header "Serene Mind" button) must be present and
  // successfully clicked — do not swallow visibility or click failures.
  const start = page
    .getByRole('button', { name: /serene|begin|start|play/i })
    .first();
  await expect(start).toBeVisible({ timeout: 10_000 });
  await start.click({ timeout: 5_000 });

  // Player-ready assertion: the GuidedMeditationFlow full-screen overlay
  // has opened. The overlay renders a close button (X icon) at top-right
  // that only exists when the flow is open. Wait for it before auditing.
  const playerReady = page.locator('[role="dialog"], .fixed.inset-0.z-50 button:has(svg)').first();
  await expect(playerReady).toBeVisible({ timeout: 10_000 });

  const results = await analyze(page);
  const violations = results.violations as unknown as Violation[];
  const blocking = violations.filter(
    (v) => v.impact === 'serious' || v.impact === 'critical',
  );

  await testInfo.attach('axe-meditation-flow.json', {
    body: JSON.stringify(violations, null, 2),
    contentType: 'application/json',
  });

  expect(
    blocking,
    `Serious/critical accessibility violations in meditation flow:\n${format(blocking)}`,
  ).toHaveLength(0);
});
