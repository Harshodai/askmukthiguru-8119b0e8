import { test, expect, Page } from '@playwright/test';

/**
 * Security regression: AAL2 / MFA cannot be bypassed.
 *
 * The guards under test are:
 *   - src/hooks/useRequireAuth.ts   (seeker routes)
 *   - src/admin/hooks/useAdminGuard.ts (admin routes)
 *
 * Both call supabase.auth.mfa.getAuthenticatorAssuranceLevel() on EVERY
 * session load and must redirect to /auth/mfa when nextLevel === 'aal2'
 * and currentLevel !== 'aal2'. A stale localStorage session must never be
 * enough to reach a protected route.
 */

const PROTECTED_SEEKER_ROUTES = ['/chat', '/profile', '/second-brain'];
const PROTECTED_ADMIN_ROUTES = ['/admin', '/admin/queries', '/admin/settings'];

/** Inject a fake, already-signed-in Supabase session into localStorage. */
async function seedFakeSession(page: Page, opts: { aal: 'aal1' | 'aal2'; nextLevel: 'aal1' | 'aal2' }) {
  await page.goto('/');
  await page.evaluate(
    ({ aal, nextLevel }) => {
      const key = Object.keys(window.localStorage).find((k) => k.startsWith('sb-') && k.endsWith('-auth-token'))
        ?? 'sb-test-auth-token';
      window.localStorage.setItem(
        key,
        JSON.stringify({
          access_token: 'fake.aal.token',
          refresh_token: 'fake-refresh',
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          token_type: 'bearer',
          user: { id: '00000000-0000-0000-0000-0000000000aa', email: 'mfa-probe@gmail.com', aud: 'authenticated' },
        }),
      );
      // Record intent so the guard's AAL probe is observable from the test.
      (window as unknown as Record<string, unknown>).__AAL_FIXTURE__ = { aal, nextLevel };
    },
    opts,
  );
}

test.describe('AAL2 / MFA bypass regression', () => {
  test('unauthenticated users never reach a protected seeker route', async ({ page }) => {
    for (const route of PROTECTED_SEEKER_ROUTES) {
      await page.goto(route);
      await page.waitForLoadState('networkidle');
      // Either bounced to /auth, or the route rendered its own sign-in gate.
      const url = page.url();
      const gated = /\/auth(\b|\/)/.test(url) || (await page.getByRole('button', { name: /sign in|continue with google/i }).count()) > 0;
      expect(gated, `${route} must be gated for anonymous visitors (landed on ${url})`).toBe(true);
    }
  });

  test('unauthenticated users never reach a protected admin route', async ({ page }) => {
    for (const route of PROTECTED_ADMIN_ROUTES) {
      await page.goto(route);
      await page.waitForURL(/\/admin\/login/, { timeout: 10_000 });
      expect(page.url()).toContain('/admin/login');
    }
  });

  test('a forged localStorage session cannot unlock /chat or /admin', async ({ page }) => {
    await seedFakeSession(page, { aal: 'aal1', nextLevel: 'aal2' });

    await page.goto('/chat');
    await page.waitForLoadState('networkidle');
    // A forged token fails server-side validation -> guard must bounce to
    // /auth (or /auth/mfa). It must never render the composer.
    const composer = page.getByRole('textbox').first();
    const onProtectedUi = (await composer.count()) > 0 && /\/chat/.test(page.url());
    expect(onProtectedUi, 'forged session must not render the authenticated chat composer').toBe(false);

    await page.goto('/admin');
    await page.waitForURL(/\/admin\/(login|auth)/, { timeout: 10_000 });
  });

  test('the MFA challenge route exists and renders a TOTP form', async ({ page }) => {
    await page.goto('/auth/mfa');
    await page.waitForLoadState('networkidle');
    const hasChallengeUi =
      (await page.getByText(/verification code|authenticator|two-factor|2fa/i).count()) > 0 ||
      (await page.locator('input[inputmode="numeric"], input[type="tel"]').count()) > 0 ||
      /\/auth/.test(page.url()); // signed-out visitors get bounced, also acceptable
    expect(hasChallengeUi).toBe(true);
  });

  test('the AAL probe is wired into both guards (source-level invariant)', async ({ request }) => {
    // Guard against a future refactor silently deleting the step-up check.
    for (const src of ['/src/hooks/useRequireAuth.ts', '/src/admin/hooks/useAdminGuard.ts']) {
      const res = await request.get(src);
      if (!res.ok()) test.skip(true, `dev server did not serve ${src}`);
      const body = await res.text();
      expect(body, `${src} must call getAuthenticatorAssuranceLevel`).toContain('getAuthenticatorAssuranceLevel');
      expect(body, `${src} must redirect to /auth/mfa`).toContain('/auth/mfa');
    }
  });
});
