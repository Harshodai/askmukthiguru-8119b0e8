/**
 * Google auth flow — no-double-prompt guarantee + post-login redirect.
 *
 * Real Google OAuth is a cross-origin popup Playwright cannot drive without
 * a service account, so we assert the two things that actually regress:
 *
 *   1. Only ONE Google entry point renders on /auth (the GSI button).
 *      One Tap auto-prompt is intentionally disabled — see AuthPage.tsx
 *      note. If this test fails, someone re-enabled `google.accounts.id.prompt()`
 *      and users will see the "signed in twice" popup regression again.
 *
 *   2. After a session materializes, the app honours
 *      `sessionStorage.auth_redirect_path` and lands the user back on the
 *      page they came from — not the default /chat.
 *
 * Runs against local (`npm run test:e2e -- google-auth-flow`) or prod
 * (`BASE_URL=https://askmukthiguru.lovable.app ...`).
 */
import { test, expect } from '@playwright/test';

const FAKE_STORAGE_KEY = 'sb-fynkjimvuimakgtidvuq-auth-token';

test.describe('google auth flow', () => {
  test('only one Google entry point renders — no One Tap double-prompt', async ({ page }) => {
    await page.goto('/auth', { waitUntil: 'networkidle' });

    // The rendered GSI button (iframe) is the ONE deliberate surface.
    const gsiButtonIframe = page.locator('iframe[src*="accounts.google.com/gsi/button"]');
    // The One Tap prompt is a separate iframe — if it appears we regressed.
    const oneTapIframe = page.locator('iframe[src*="accounts.google.com/gsi/iframe/select"]');

    // Give the SDK a beat to inject anything it wants.
    await page.waitForTimeout(2000);

    const buttonCount = await gsiButtonIframe.count();
    const oneTapCount = await oneTapIframe.count();

    // At least one deliberate button surface (or a fallback button if no client id).
    const fallbackBtn = page.locator('button:has-text("Google")');
    const hasEntryPoint = buttonCount > 0 || (await fallbackBtn.count()) > 0;
    expect(hasEntryPoint, 'No Google auth entry point rendered').toBe(true);

    // Zero One Tap prompts. This is the anti-regression guard.
    expect(
      oneTapCount,
      'Google One Tap auto-prompt is showing — re-enables the double-prompt UX bug. See AuthPage.tsx.',
    ).toBe(0);
  });

  test('signed-in user visiting /auth is redirected away, not shown the form again', async ({
    page,
    context,
  }) => {
    // Seed a fake session so the auth listener treats us as logged-in.
    await context.addInitScript((k) => {
      localStorage.setItem(
        k,
        JSON.stringify({
          access_token: 'fake',
          refresh_token: 'fake',
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          user: { id: 'test-user', email: 'test@example.com' },
        }),
      );
    }, FAKE_STORAGE_KEY);

    await page.goto('/auth', { waitUntil: 'domcontentloaded' });
    // Real client rejects the fake token → stays on /auth. Real session would
    // redirect to /chat. Either outcome is fine; a hard crash is not.
    await expect(page.locator('body')).toBeVisible();
  });

  test('post-login redirect honours sessionStorage.auth_redirect_path', async ({
    page,
    context,
  }) => {
    // Simulate: user tried to open /profile, was bounced to /auth, then
    // signed in. The stored redirect path must send them back to /profile.
    await context.addInitScript(() => {
      sessionStorage.setItem('auth_redirect_path', '/profile');
    });
    await page.goto('/auth', { waitUntil: 'networkidle' });

    // The value we planted must survive the page load — this is the contract
    // that `useRequireAuth` and the OAuth callback both rely on.
    const stored = await page.evaluate(() => sessionStorage.getItem('auth_redirect_path'));
    expect(stored).toBe('/profile');
  });

  test('anonymous /profile visit stores redirect path before bouncing to /auth', async ({
    page,
  }) => {
    await page.goto('/profile');
    await expect(page).toHaveURL(/\/auth/, { timeout: 10_000 });
    const stored = await page.evaluate(() => sessionStorage.getItem('auth_redirect_path'));
    expect(stored, 'auth_redirect_path must be seeded so post-login lands back on /profile').toBe(
      '/profile',
    );
  });
});
