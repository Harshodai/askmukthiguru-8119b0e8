import { defineConfig, devices } from '@playwright/test';
import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';

// rls-cross-user.spec.ts provisions Alice/Bob directly against local
// Supabase's Auth REST API (via `npx supabase status`) and that part always
// worked — but the *browser* signs in through the built frontend bundle,
// which only knows the Supabase project baked into it at `npm run build`
// time via VITE_SUPABASE_URL/VITE_SUPABASE_PUBLISHABLE_KEY. Without this,
// the preview build silently falls back to whatever `.env` picks up (the
// production project), so the UI tries to sign Bob in against a project
// where Bob was never created and hangs on `waitForURL` until timeout.
// SUPABASE_URL/SUPABASE_ANON_KEY (CI) already take precedence, matching the
// spec's own discovery order; local `supabase status` is the fallback.
//
// Also exports the resolved origin via process.env.E2E_SUPABASE_ORIGIN,
// inherited by the test-runner worker processes (not just the build's child
// process) — security-aal2.spec.ts intercepts Supabase Auth network calls
// with page.route() against a specific origin, and that origin must match
// whatever the build actually points at or the mocks silently never fire,
// letting a forged test JWT hit the real (local or prod) Supabase Auth
// instead of the mocked response the test is asserting against.
function discoverLocalSupabaseEnv(): string {
  if (process.env.SUPABASE_URL && process.env.SUPABASE_ANON_KEY) {
    process.env.E2E_SUPABASE_ORIGIN = process.env.SUPABASE_URL.replace(/\/$/, '');
    return `VITE_SUPABASE_URL=${process.env.SUPABASE_URL} VITE_SUPABASE_PUBLISHABLE_KEY=${process.env.SUPABASE_ANON_KEY}`;
  }
  const dockerBin = '/Users/harshodaikolluru/.docker/bin';
  const path = existsSync(dockerBin) ? `${dockerBin}:${process.env.PATH ?? ''}` : process.env.PATH;
  try {
    const out = execSync('npx supabase status --output json', {
      env: { ...process.env, PATH: path },
      encoding: 'utf8',
      timeout: 60_000,
    });
    const json = JSON.parse(out.slice(out.indexOf('{')));
    if (json.API_URL && json.ANON_KEY) {
      process.env.E2E_SUPABASE_ORIGIN = String(json.API_URL).replace(/\/$/, '');
      return `VITE_SUPABASE_URL=${json.API_URL} VITE_SUPABASE_PUBLISHABLE_KEY=${json.ANON_KEY}`;
    }
  } catch {
    // Local Supabase isn't running — fall through to the build's own
    // .env default. rls-cross-user.spec.ts will report its own clear
    // error in that case; every other spec is unaffected either way.
  }
  return '';
}

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30 * 1000,
  expect: {
    timeout: 5000,
  },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // Unbounded local parallelism (Playwright's default heuristic, ~half of
  // CPU cores) reproducibly caused widespread false failures on this
  // machine: 15 failing specs at full parallelism, all "Test timeout of
  // 30000ms exceeded" across unrelated features, dropping to 5 (genuine)
  // at workers=3 — a resource-contention artifact from running many
  // Chromium instances alongside Docker (backend + local Supabase), not
  // real bugs. A conservative local cap trades some wall-clock time for
  // a suite that reports real failures instead of environment noise.
  workers: process.env.CI ? 1 : 3,
  // Always leave a debuggable trail: HTML report for humans, JSON + JUnit for CI.
  reporter: process.env.CI
    ? [
        ['list'],
        ['html', { open: 'never', outputFolder: 'playwright-report' }],
        ['json', { outputFile: 'playwright-report/results.json' }],
        ['junit', { outputFile: 'playwright-report/junit.xml' }],
      ]
    : [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  outputDir: 'test-results',
  use: {
    actionTimeout: 0,
    // Debuggability over disk space: any failing spec ships a screenshot,
    // a video and a full trace (network + DOM snapshots) into test-results/.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    baseURL: process.env.BASE_URL || 'http://localhost:4173',
    // E2E must observe the freshly built bundle; a stale service worker can
    // otherwise mask source fixes and replay old route chunks.
    serviceWorkers: 'block',
  },

  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Escape hatch for sandboxes/CI images that already ship a Chromium
        // build instead of Playwright's pinned download.
        launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
          ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
          : {},
      },
    },

    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],
  webServer: process.env.BASE_URL ? undefined : {
    // Local preview is frontend-only. Clear production endpoint overrides so
    // capability probes stay same-origin and do not create false CORS failures.
    // Point the built bundle at local Supabase when discoverable, so
    // rls-cross-user.spec.ts's UI sign-in test authenticates against the
    // same project its Alice/Bob accounts were actually created in.
    command: `VITE_BACKEND_URL= VITE_NATIVE_BACKEND= VITE_GOOGLE_CLIENT_ID= VITE_ENABLE_E2E_DIAGNOSTICS=true ${discoverLocalSupabaseEnv()} npm run build && npm run preview -- --host 127.0.0.1`,
    port: 4173,
    reuseExistingServer: !process.env.CI,
  },
});
