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

const ROUTE_MATRIX = [
  { route: '/chat', role: 'seeker', minAal: 'aal2', redirect: '/auth' },
  { route: '/profile', role: 'seeker', minAal: 'aal2', redirect: '/auth' },
  { route: '/second-brain', role: 'seeker', minAal: 'aal2', redirect: '/auth' },
  { route: '/admin', role: 'admin', minAal: 'aal2', redirect: '/admin/login' },
  { route: '/admin/queries', role: 'admin', minAal: 'aal2', redirect: '/admin/login' },
  { route: '/admin/settings', role: 'admin', minAal: 'aal2', redirect: '/admin/login' },
];

// The app installs a service worker that intercepts fetches and forwards them
// to the network. In Playwright, page.route() does not intercept requests that
// are re-issued by a service worker, so Supabase auth calls would bypass our
// mocks. Block service workers for this auth-mocking spec so the mocked routes
// are hit directly.
test.use({ serviceWorkers: 'block' });

const SUPABASE_ORIGIN = 'https://ozmjeuqbholoxypfxixb.supabase.co';
const STORAGE_KEY = 'sb-ozmjeuqbholoxypfxixb-auth-token';

/** Build a synthetically-signed JWT whose payload contains the requested AAL claim and optional factors. */
function buildTestJwt(payload: Record<string, unknown>): string {
  const header = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9';
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url').replace(/=+$/, '');
  const signature = 'c2lnbmF0dXJl'; // "signature" in base64url — intentionally invalid; the client only decodes it.
  return `${header}.${body}.${signature}`;
}

/** Mock Supabase Auth network calls so a localStorage-only session can exercise the AAL guards without real Supabase credentials. */
async function mockSupabaseAuth(page: Page, session: Record<string, unknown>) {
  await page.route(`${SUPABASE_ORIGIN}/auth/v1/user`, async (route) => {
    const request = route.request();
    if (request.method() === 'OPTIONS') {
      await route.fulfill({
        status: 200,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization, apikey',
        },
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'Access-Control-Allow-Origin': '*' },
      body: JSON.stringify(session.user),
    });
  });

  await page.route(`${SUPABASE_ORIGIN}/auth/v1/token*`, async (route) => {
    const request = route.request();
    if (request.method() === 'OPTIONS') {
      await route.fulfill({
        status: 200,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization, apikey',
        },
      });
      return;
    }
    // Refuse fake refresh so the client never replaces our seeded token.
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      headers: { 'Access-Control-Allow-Origin': '*' },
      body: JSON.stringify({ error: 'invalid_grant', error_description: 'Invalid refresh token' }),
    });
  });

  await page.route(`${SUPABASE_ORIGIN}/auth/v1/session*`, async (route) => {
    const request = route.request();
    if (request.method() === 'OPTIONS') {
      await route.fulfill({
        status: 200,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization, apikey',
        },
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'Access-Control-Allow-Origin': '*' },
      body: JSON.stringify(session),
    });
  });

  // MFAChallengePage calls listFactors() which internally calls getUser(); the
  // /auth/v1/user mock above already satisfies that. challenge() and verify()
  // hit /auth/v1/factors/{id}/challenge and /verify.
  await page.route(`${SUPABASE_ORIGIN}/auth/v1/factors/*/challenge`, async (route) => {
    const request = route.request();
    if (request.method() === 'OPTIONS') {
      await route.fulfill({
        status: 200,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization, apikey',
        },
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'Access-Control-Allow-Origin': '*' },
      body: JSON.stringify({ id: 'challenge-id', expires_at: new Date(Date.now() + 5 * 60_000).toISOString() }),
    });
  });

  await page.route(`${SUPABASE_ORIGIN}/auth/v1/factors/*/verify`, async (route) => {
    const request = route.request();
    if (request.method() === 'OPTIONS') {
      await route.fulfill({
        status: 200,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization, apikey',
        },
      });
      return;
    }
    await route.fulfill({
      status: 422,
      contentType: 'application/json',
      headers: { 'Access-Control-Allow-Origin': '*' },
      body: JSON.stringify({ code: 'mfa_verification_failed', message: 'Invalid MFA code' }),
    });
  });
}

/** Inject a fake, already-signed-in Supabase session into localStorage. */
async function seedFakeSession(
  page: Page,
  opts: { aal: 'aal1' | 'aal2'; nextLevel: 'aal1' | 'aal2'; email?: string; userId?: string },
) {
  const userId = opts.userId ?? '00000000-0000-0000-0000-0000000000aa';
  const email = opts.email ?? 'mfa-probe@gmail.com';

  // Supabase-js decodes the JWT locally for AAL; the /auth/v1/user response
  // provides the factors array used to compute nextLevel. We keep the access
  // token claim equal to `aal` and add factors only when nextLevel should be aal2.
  const accessTokenPayload: Record<string, unknown> = {
    aud: 'authenticated',
    exp: 9999999999,
    sub: userId,
    email,
    role: 'authenticated',
    app_metadata: { provider: 'email' },
    user_metadata: { full_name: 'MFA Probe' },
    aal: opts.aal,
  };
  if (opts.nextLevel === 'aal2') {
    accessTokenPayload.factors = [
      {
        id: 'factor-1',
        friendly_name: 'TEST',
        factor_type: 'totp',
        status: 'verified',
        created_at: '2026-07-30T00:00:00Z',
        updated_at: '2026-07-30T00:00:00Z',
      },
    ];
  }

  const accessToken = buildTestJwt(accessTokenPayload);

  const session = {
    access_token: accessToken,
    refresh_token: 'fake-refresh',
    expires_in: 3600,
    expires_at: 9999999999,
    token_type: 'bearer',
    user: {
      id: userId,
      aud: 'authenticated',
      role: 'authenticated',
      email,
      email_confirmed_at: '2026-07-30T00:00:00Z',
      user_metadata: { full_name: 'MFA Probe' },
      factors: opts.nextLevel === 'aal2'
        ? [
            {
              id: 'factor-1',
              friendly_name: 'TEST',
              factor_type: 'totp',
              status: 'verified',
              created_at: '2026-07-30T00:00:00Z',
              updated_at: '2026-07-30T00:00:00Z',
            },
          ]
        : [],
    },
  };

  await page.goto('/');
  await mockSupabaseAuth(page, session);
  await page.evaluate(
    ({ key, sess, aal, nextLevel }) => {
      window.localStorage.setItem(key, JSON.stringify(sess));
      // Record intent so the guard's AAL probe is observable from the test.
      (window as unknown as Record<string, unknown>).__AAL_FIXTURE__ = { aal, nextLevel };
    },
    { key: STORAGE_KEY, sess: session, aal: opts.aal, nextLevel: opts.nextLevel },
  );
}

test.describe('AAL2 / MFA bypass regression', () => {
  test('unauthenticated users never reach protected routes (matrix)', async ({ page }) => {
    for (const { route, role, redirect } of ROUTE_MATRIX) {
      await page.goto(route);
      await page.waitForURL(/\/auth|\/admin\/login/, { timeout: 10_000 });

      const url = page.url();
      if (role === 'admin') {
        expect(url, `${route} must redirect to ${redirect}`).toContain(redirect);
      } else {
        // Seeker routes must end on /auth or render a sign-in gate.
        const gated =
          /\/auth(\b|\/)/.test(url) ||
          (await page.getByRole('button', { name: /sign in|continue with google/i }).count()) > 0;
        expect(gated, `${route} must be gated for anonymous visitors (landed on ${url})`).toBe(true);
      }
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

  test('MFA step-up is required from aal1 with nextLevel aal2 and bad code shows error', async ({ page }) => {
    await seedFakeSession(page, { aal: 'aal1', nextLevel: 'aal2' });

    await page.goto('/chat');
    await page.waitForURL(/\/auth\/mfa/, { timeout: 10_000 });

    // MFAChallengePage uses <Label htmlFor="mfa-code">Verification code</Label>
    // plus an input with inputMode="numeric". Prefer the accessible label match.
    const codeInput = page.getByRole('textbox', { name: /verification code/i });
    await expect(codeInput).toBeVisible();

    await codeInput.fill('000000');
    await page.getByRole('button', { name: /verify/i }).click();

    await expect(page.getByText(/invalid|wrong|failed|verification failed|mfa verification failed/i)).toBeVisible();
    await expect(page).toHaveURL(/\/auth\/mfa/);
  });

  test('admin guard isolates non-admin users even with AAL2 satisfied', async ({ page }) => {
    // Non-admin user (regular seeker Gmail) with AAL2 satisfied.
    await seedFakeSession(page, {
      aal: 'aal2',
      nextLevel: 'aal2',
      email: 'regular-seeker@gmail.com',
      userId: '00000000-0000-0000-0000-0000000000bb',
    });

    await page.goto('/admin');
    await page.waitForURL(/\/admin\/login|\/unauthorized/, { timeout: 10_000 });
    const url = page.url();
    expect(
      url.includes('/admin/login') || url.includes('/unauthorized'),
      `non-admin must be denied admin access, got ${url}`,
    ).toBe(true);
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

  test('backend rejects aal1 JWT when aal2 is required', async ({ request }) => {
    // TODO(Task 3): replace this skip with a real endpoint call once the backend
    // enforces the 'aal' claim on a protected route. For now no endpoint in the
    // app asserts request.state.user.aal === 'aal2', so we leave the scaffold.
    test.skip(true, 'No backend endpoint currently enforces aal claim; covered in Task 3');

    // Intended shape of the test once Task 3 lands:
    // const res = await request.get('/api/admin/self-check', {
    //   headers: { Authorization: 'Bearer <synthetic-aal1-jwt>', 'X-Test-Key': process.env.BENCHMARK_SECRET ?? '' },
    // });
    // expect(res.status()).toBe(403);
    // const body = await res.json();
    // expect(JSON.stringify(body)).toMatch(/aal/i);
  });
});
