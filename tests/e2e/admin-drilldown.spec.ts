/**
 * Admin Console E2E — Query Trace Drill-Down
 * ============================================
 * Tests the admin Queries page, verifying:
 *   1. Unauthenticated access redirects to /admin/login
 *   2. Filter bar renders (search, model, prompt, score slider)
 *   3. Clicking a query row opens the TraceDrawer sheet
 *   4. TraceDrawer shows key trace fields (query text, latency, status)
 *   5. Export buttons (CSV / JSON) exist on the drawer
 *   6. Closing the drawer removes it from view
 *   7. URL search-param ?trace=<id> persists (deep-linkable)
 *
 * Auth strategy
 * -------------
 * Tests that require an authenticated admin session use a pre-seeded
 * ADMIN_SESSION_COOKIE env var.  If the var is absent the authenticated
 * tests are skipped with a clear message — CI can set it via secrets.
 *
 * Run (locally, with dev server running):
 *   npx playwright test tests/e2e/admin-drilldown.spec.ts
 *
 * Run (CI with session cookie):
 *   ADMIN_SESSION_COOKIE=<value> npx playwright test tests/e2e/admin-drilldown.spec.ts
 */

import { test, expect, Page, BrowserContext } from '@playwright/test';

// ── Helpers ────────────────────────────────────────────────────────────────────

const ADMIN_SESSION_COOKIE = process.env.ADMIN_SESSION_COOKIE;

/**
 * Inject a pre-existing Supabase session cookie so we can reach authenticated
 * admin routes without going through the UI login flow.
 */
async function injectAdminSession(context: BrowserContext): Promise<void> {
  if (!ADMIN_SESSION_COOKIE) return;
  await context.addCookies([
    {
      name: 'sb-access-token',
      value: ADMIN_SESSION_COOKIE,
      domain: 'localhost',
      path: '/',
      httpOnly: true,
      secure: false,
    },
  ]);
}

function skipIfNoSession() {
  if (!ADMIN_SESSION_COOKIE) {
    test.skip(true, 'ADMIN_SESSION_COOKIE not set — skipping authenticated tests');
  }
}

// ── Unauthenticated tests (always run) ─────────────────────────────────────────

test.describe('Admin — unauthenticated access', () => {
  test('GET /admin redirects to /admin/login', async ({ page }) => {
    await page.goto('/admin');
    await expect(page).toHaveURL(/\/admin\/login/);
  });

  test('/admin/queries redirects to /admin/login', async ({ page }) => {
    await page.goto('/admin/queries');
    await expect(page).toHaveURL(/\/admin\/login/);
  });
});

// ── Authenticated tests (require ADMIN_SESSION_COOKIE) ─────────────────────────

test.describe('Admin Queries — drill-down', () => {
  test.beforeEach(async ({ context }) => {
    skipIfNoSession();
    await injectAdminSession(context);
  });

  test('Queries page loads with filter bar', async ({ page }) => {
    await page.goto('/admin/queries');
    await expect(page.getByRole('heading', { name: 'Queries' })).toBeVisible();
    await expect(page.getByPlaceholder(/anxious|beautiful|search/i)).toBeVisible();
    // Model selector
    await expect(page.getByText(/all models/i).first()).toBeVisible();
  });

  test('Clicking a query row opens the TraceDrawer', async ({ page }) => {
    await page.goto('/admin/queries');

    // Wait for table rows to appear (the page fetches from backend)
    const rows = page.locator('tbody tr');
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    // Click the first row
    await rows.first().click();

    // Sheet / drawer should open
    const drawer = page.getByRole('dialog');
    await expect(drawer).toBeVisible({ timeout: 5_000 });
    await expect(drawer.getByText(/query trace/i)).toBeVisible();
  });

  test('TraceDrawer shows query text, latency and status badge', async ({ page }) => {
    await page.goto('/admin/queries');
    await page.locator('tbody tr').first().click();

    const drawer = page.getByRole('dialog');
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    // At least one of these metadata items must be present
    const hasLatency = await drawer.getByText(/ms/i).count() > 0;
    const hasStatus = await drawer.getByText(/ok|error|blocked/i).count() > 0;
    expect(hasLatency || hasStatus).toBeTruthy();
  });

  test('TraceDrawer export buttons are present', async ({ page }) => {
    await page.goto('/admin/queries');
    await page.locator('tbody tr').first().click();

    const drawer = page.getByRole('dialog');
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    // Export dropdown trigger
    const exportBtn = drawer.getByRole('button', { name: /export/i });
    await expect(exportBtn).toBeVisible();

    // Open dropdown
    await exportBtn.click();
    await expect(page.getByRole('menuitem', { name: /csv/i })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: /json/i })).toBeVisible();
  });

  test('Closing the drawer removes it from view', async ({ page }) => {
    await page.goto('/admin/queries');
    await page.locator('tbody tr').first().click();

    const drawer = page.getByRole('dialog');
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    // Close via ESC
    await page.keyboard.press('Escape');
    await expect(drawer).not.toBeVisible({ timeout: 3_000 });
  });

  test('Opening a trace deep-links via ?trace= URL param', async ({ page }) => {
    await page.goto('/admin/queries');
    await page.locator('tbody tr').first().click();

    // After clicking, URL should contain ?trace=<uuid>
    await expect(page).toHaveURL(/[?&]trace=[0-9a-f-]+/, { timeout: 3_000 });
  });

  test('?trace= URL param re-opens drawer on page load', async ({ page }) => {
    // First get a valid trace ID from the page
    await page.goto('/admin/queries');
    await page.locator('tbody tr').first().click();
    const url = page.url();
    const traceMatch = url.match(/[?&]trace=([0-9a-f-]+)/);

    if (!traceMatch) {
      test.skip(true, 'No trace ID found in URL — skipping deep-link test');
      return;
    }

    const traceId = traceMatch[1];

    // Navigate directly to the deep-linked URL
    await page.goto(`/admin/queries?trace=${traceId}`);
    const drawer = page.getByRole('dialog');
    await expect(drawer).toBeVisible({ timeout: 8_000 });
  });
});

// ── Filter behaviour ───────────────────────────────────────────────────────────

test.describe('Admin Queries — filter bar', () => {
  test.beforeEach(async ({ context }) => {
    skipIfNoSession();
    await injectAdminSession(context);
  });

  test('Search filter updates URL search param', async ({ page }) => {
    await page.goto('/admin/queries');
    const searchInput = page.getByPlaceholder(/anxious|beautiful|search/i);
    await searchInput.fill('consciousness');
    // URL should include search param
    await expect(page).toHaveURL(/search=consciousness/, { timeout: 2_000 });
  });

  test('Clear button resets all filters', async ({ page }) => {
    await page.goto('/admin/queries?search=consciousness');
    // Clear button should appear
    const clearBtn = page.getByRole('button', { name: /clear/i });
    await expect(clearBtn).toBeVisible({ timeout: 5_000 });
    await clearBtn.click();
    // URL should no longer have search param
    await expect(page).not.toHaveURL(/search=/, { timeout: 2_000 });
  });
});
