import { test, expect } from '@playwright/test';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const outputDir = path.resolve(__dirname, '../../playwright-screenshots');

const session = {
  access_token:
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjo5OTk5OTk5OTk5LCJzdWIiOiJtb2NrLXVzZXItdXVpZCIsImVtYWlsIjoic2Vla2VyQGdtYWlsLmNvbSIsInJvbGUiOiJhdXRoZW50aWNhdGVkIn0.signature',
  token_type: 'bearer',
  expires_in: 3600,
  expires_at: 9999999999,
  refresh_token: 'mock-refresh-token',
  user: {
    id: 'mock-user-uuid',
    aud: 'authenticated',
    role: 'authenticated',
    email: 'seeker@gmail.com',
    email_confirmed_at: '2026-05-20T00:00:00Z',
    user_metadata: { full_name: 'Devoted Seeker', age_confirmed: true },
    app_metadata: { provider: 'email' },
    created_at: '2026-05-20T00:00:00Z',
  },
};

const json = (body: unknown, headers: Record<string, string> = {}) => ({
  status: 200,
  contentType: 'application/json',
  headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': 'content-range', ...headers },
  body: JSON.stringify(body),
});

test('Port 80 Docker Container - Profile Memory, Governance & Serene Mind Verification', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1000 });

  await page.route(/\/auth\/v1\/user/, (route) => route.fulfill(json(session.user)));
  await page.route(/\/auth\/v1\/factors/, (route) => route.fulfill(json({ all: [], totp: [] })));
  await page.route(/\/rest\/v1\//, (route) => route.fulfill(json([], { 'content-range': '*/0' })));

  let isConsentGranted = false;
  await page.route(/\/api\/memory\/consent/, (route) => {
    if (route.request().method() === 'POST') {
      isConsentGranted = true;
      return route.fulfill(json({ granted: true }));
    }
    return route.fulfill(json({ granted: isConsentGranted }));
  });
  await page.route(/\/api\/memory\/list/, (route) => route.fulfill(json({ memories: [], total: 0 })));
  await page.route(/\/api\/memory\/core/, (route) => route.fulfill(json(null)));
  await page.route(/\/api\/memory\/summaries/, (route) => route.fulfill(json([])));
  await page.route(/\/api\/memory\/conversations/, (route) => route.fulfill(json([])));
  await page.route(/\/api\/memory\/persona/, (route) => route.fulfill(json({ content: '' })));
  await page.route(/\/api\/memory\/skills/, (route) => route.fulfill(json([])));
  await page.route(/\/api\/kg\/personal-subgraph/, (route) => route.fulfill(json({ nodes: [], edges: [] })));

  await page.addInitScript(
    ([s]) => {
      const value = JSON.stringify(s);
      for (const key of [
        'sb-ozmjeuqbholoxypfxixb-auth-token',
        'sb-fynkjimvuimakgtidvuq-auth-token',
        'sb-supabase-demo-auth-token',
        'sb-localhost-auth-token',
        'sb-127.0.0.1-auth-token',
        'sb-127-auth-token',
      ]) {
        localStorage.setItem(key, value);
      }
      localStorage.setItem('askmukthiguru_tour_completed', '1');
      localStorage.setItem('askmukthiguru_consent_v1', 'rejected');
      localStorage.setItem('askmukthiguru_disclaimer_accepted', 'true');
    },
    [session],
  );

  // Navigate to Port 80
  await page.goto('http://localhost:80/profile?tab=memory&subtab=guru', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);

  // Take screenshot of Docker port 80 Profile Memory page
  const dockerProfilePath = path.join(outputDir, 'docker_port80_profile_memory.png');
  await page.screenshot({ path: dockerProfilePath, fullPage: true });

  // Verify elements are present
  await expect(page.getByRole('heading', { name: 'Devoted Seeker' })).toBeVisible();

  // Verify Connection Pill is Connected
  const connectionPill = page.locator('div[role="button"]:has-text("Connected")');
  await expect(connectionPill).toBeVisible();

  // Click Approve & Enable Memory
  const approveBtn = page.getByRole('button', { name: /Approve & Enable Memory/i }).first();
  await expect(approveBtn).toBeVisible();
  await approveBtn.click();
  await page.waitForTimeout(1500);

  // Take screenshot of approved blooming state
  const dockerBloomingPath = path.join(outputDir, 'docker_port80_profile_blooming.png');
  await page.screenshot({ path: dockerBloomingPath, fullPage: true });

  // Verify blooming state with the 3 sacred inquiry cards
  await expect(page.getByText('Your Personal Wisdom Map is Blooming')).toBeVisible();
  await expect(page.getByText('How do I shift from a suffering state to a beautiful state?')).toBeVisible();
});
