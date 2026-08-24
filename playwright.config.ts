import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30 * 1000,
  expect: {
    timeout: 5000,
  },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
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
    command: 'VITE_BACKEND_URL= VITE_NATIVE_BACKEND= VITE_GOOGLE_CLIENT_ID= VITE_ENABLE_E2E_DIAGNOSTICS=true npm run build && npm run preview -- --host 127.0.0.1',
    port: 4173,
    reuseExistingServer: !process.env.CI,
  },
});
