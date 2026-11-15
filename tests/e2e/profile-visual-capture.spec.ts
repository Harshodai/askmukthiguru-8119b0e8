import { test, expect, type Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const outputDir = path.resolve(__dirname, '../../playwright-screenshots');

const session = {
  access_token:
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjo5OTk5OTk5OTk5LCJzdWIiOiJtb2NrLXVzZXItdXVpZCIsImVtYWlsIjoic2Vla2VyQGdtYWlsLmNvbSIsInJvbGUiOiJhdXRoZW50aWNhdGVkIn0.c2lnbmF0dXJl',
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

async function mockSeekerEnvironment(page: Page) {
  const mockDbSessions: Array<{
    id: string;
    user_id: string;
    started_at: string;
    completed_at: string;
    duration_seconds: number;
    breath_cycles: number;
    completed: boolean;
  }> = [];
  const now = new Date();
  for (let i = 0; i < 25; i++) {
    const d = new Date(now);
    d.setDate(now.getDate() - i);
    mockDbSessions.push({
      id: `sess-${i}`,
      user_id: 'mock-user-uuid',
      started_at: d.toISOString(),
      completed_at: d.toISOString(),
      duration_seconds: 900,
      breath_cycles: 12,
      completed: true,
    });
  }

  await page.route(/\/auth\/v1\/user/, (route) => route.fulfill(json(session.user)));
  await page.route(/\/auth\/v1\/factors/, (route) => route.fulfill(json({ all: [], totp: [] })));
  // Catch-all goes FIRST so specific routes registered AFTER take precedence
  await page.route(/\/rest\/v1\//, (route) => route.fulfill(json([], { 'content-range': '*/0' })));
  await page.route(/\/rest\/v1\/meditation_sessions/, (route) =>
    route.fulfill(json(mockDbSessions, { 'content-range': `0-${mockDbSessions.length - 1}/${mockDbSessions.length}` })),
  );
  // Register catch-all FIRST so specific routes registered AFTER take precedence
  await page.route(/\/api\//, (route) =>
    route.request().method() === 'OPTIONS'
      ? route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*' } })
      : route.fulfill(json({})),
  );

  let isConsentGranted = false;
  await page.route(/\/api\/memory\/consent/, (route) => {
    if (route.request().method() === 'POST') {
      isConsentGranted = true;
      return route.fulfill(json({ granted: true }));
    }
    return route.fulfill(json({ granted: isConsentGranted }));
  });
  await page.route(/\/api\/memory\/list/, (route) =>
    route.fulfill(json({ memories: [], total: 0 })),
  );
  await page.route(/\/api\/memory\/core/, (route) =>
    route.fulfill(json(null)),
  );
  await page.route(/\/api\/memory\/summaries/, (route) =>
    route.fulfill(json([])),
  );
  await page.route(/\/api\/memory\/conversations/, (route) =>
    route.fulfill(json([])),
  );
  await page.route(/\/api\/memory\/persona/, (route) =>
    route.fulfill(json({ content: '' })),
  );
  await page.route(/\/api\/memory\/skills/, (route) =>
    route.fulfill(json([])),
  );

  await page.route(/\/api\/health/, (route) =>
    route.fulfill(json({ ready: true, status: 'healthy' })),
  );

  await page.route(/\/api\/profile/, (route) =>
    route.fulfill(
      json({
        display_name: 'Devoted Seeker',
        bio: 'Exploring inner stillness and the beautiful state through daily sadhana.',
        preferred_language: 'en',
        guru_tone: 'gentle',
        familiarity_level: 'seeker',
      }),
    ),
  );

  await page.route(/\/api\/kg\/personal-subgraph/, (route) =>
    route.fulfill(json({ nodes: [], edges: [] })),
  );
  await page.route(/\/api\/kg\/subgraph/, (route) =>
    route.fulfill(json({ nodes: [], edges: [] })),
  );

  await page.addInitScript(
    ([s, dbSessions]) => {
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
      sessionStorage.setItem('auth_explicit_login', 'true');
      sessionStorage.setItem('askmukthiguru_pre_practice_asked', '1');

      // Seed valid sessions conforming to MeditationSessionSchema
      const localSessions = dbSessions.map((item) => ({
        id: item.id,
        startedAt: item.started_at,
        completedAt: item.completed_at,
        durationSeconds: item.duration_seconds,
        breathCycles: item.breath_cycles,
        completed: item.completed,
      }));
      localStorage.setItem('askmukthiguru_meditation_sessions', JSON.stringify(localSessions));

      // Seed profile
      localStorage.setItem(
        'askmukthiguru_profile',
        JSON.stringify({
          displayName: 'Devoted Seeker',
          bio: 'Exploring inner stillness and the beautiful state through daily sadhana.',
          preferredLanguage: 'en',
          guruTone: 'gentle',
          familiarityLevel: 'seeker',
          theme: 'dark',
        }),
      );
    },
    [session, mockDbSessions] as const,
  );
}

test.describe('Profile Visual Capture', () => {
  test('Capture Profile Page Heatmap, Circle toggle, and Knowledge Graph', async ({ page }) => {
    page.on('console', (msg) => {
      if (msg.type() === 'error' || msg.text().includes('meditation')) {
        console.log(`[PAGE ${msg.type().toUpperCase()}] ${msg.text()}`);
      }
    });

    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }

    await mockSeekerEnvironment(page);
    await page.setViewportSize({ width: 1280, height: 950 });

    // Step 1: Navigate to /profile with streak > 7 (GitHub heatmap active by default)
    await page.goto('/profile');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    console.log('[DEBUG] Current URL:', page.url());
    console.log('[DEBUG] Page Title:', await page.title());

    // Expect to be on /profile (not bounced to /auth)
    expect(page.url()).toContain('/profile');

    const heatmapScreenshot = path.join(outputDir, 'profile_journey_heatmap_default.png');
    await page.screenshot({ path: heatmapScreenshot, fullPage: true });
    console.log(`[VISUAL CAPTURE] Saved: ${heatmapScreenshot}`);

    // Step 2: Toggle to 7-Day Circle of Presence
    const switchCircleBtn = page.getByRole('button', { name: /Circle/i }).first();
    await expect(switchCircleBtn).toBeVisible({ timeout: 5000 });
    await switchCircleBtn.click();
    await page.waitForTimeout(600);

    const circleScreenshot = path.join(outputDir, 'profile_journey_circle_toggle.png');
    await page.screenshot({ path: circleScreenshot, fullPage: true });
    console.log(`[VISUAL CAPTURE] Saved: ${circleScreenshot}`);

    // Step 3: Navigate to Memory Tab -> Guru's Living Memory & Knowledge Graph
    await page.goto('/profile?tab=memory&subtab=guru');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);

    const memoryGraphScreenshot = path.join(outputDir, 'profile_memory_knowledge_graph.png');
    await page.screenshot({ path: memoryGraphScreenshot, fullPage: true });
    console.log(`[VISUAL CAPTURE] Saved: ${memoryGraphScreenshot}`);

    // Step 4: Click "Approve & Enable Memory" banner button if present to show the active blooming graph
    const approveBtn = page.getByRole('button', { name: /Approve & Enable Memory/i }).first();
    if (await approveBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await approveBtn.click();
      await page.waitForTimeout(1500);
      const memoryApprovedScreenshot = path.join(outputDir, 'profile_memory_approved_blooming.png');
      await page.screenshot({ path: memoryApprovedScreenshot, fullPage: true });
      console.log(`[VISUAL CAPTURE] Saved: ${memoryApprovedScreenshot}`);
    }

    // Step 5: Test Serene Mind guided flow in Chat
    await page.goto('/chat');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1500);

    // Open Serene Mind via top header or shortcut
    const sereneMindBtn = page.getByRole('button', { name: /Serene Mind/i }).first();
    if (await sereneMindBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await sereneMindBtn.click();
      await page.waitForTimeout(1500);
      const sereneMindScreenshot = path.join(outputDir, 'serene_mind_preethaji_guided_flow.png');
      await page.screenshot({ path: sereneMindScreenshot, fullPage: true });
      console.log(`[VISUAL CAPTURE] Saved: ${sereneMindScreenshot}`);
    }
  });
});
