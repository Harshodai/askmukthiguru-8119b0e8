import { expect, test, type Page } from '@playwright/test';

/**
 * Memory provenance links on Profile > Memory and the personal Wisdom Map.
 *
 * Everything the page reads is mocked (Supabase REST, auth, backend /api), so the
 * spec proves the UI contract only: a link when the API proves a source, an honest
 * "Source unavailable" otherwise, and keyboard access. It does NOT prove the real
 * Supabase column or the live backend; those stay UNPROVEN until a run against them.
 */

// First paint of a lazy route can exceed the 5 s default expect timeout on a cold server.
const LOAD = { timeout: 20_000 };

const CONVERSATION_ID = '3f2b8c1e-9a4d-4e6f-8a1b-2c3d4e5f6a7b';

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
    user_metadata: { full_name: 'Test Seeker', age_confirmed: true },
    app_metadata: { provider: 'email' },
    created_at: '2026-05-20T00:00:00Z',
  },
};

const conversations = [
  {
    id: CONVERSATION_ID,
    startedAt: '2026-10-30T09:00:00.000Z',
    updatedAt: '2026-10-30T09:05:00.000Z',
    preview: 'Breathing origin conversation',
    messageCount: 1,
    messages: [
      {
        id: '00000000-0000-4000-8000-000000000011',
        role: 'user',
        content: 'ORIGIN: I practise breathing every morning',
        timestamp: '2026-10-30T09:00:00.000Z',
      },
    ],
  },
];

const memories = [
  {
    id: 'm1',
    content: 'I practise breathing every morning',
    source: 'extracted',
    created_at: '2026-10-30T10:00:00Z',
    source_conversation_id: CONVERSATION_ID,
  },
  {
    id: 'm2',
    content: 'I live in Pune',
    source: 'extracted',
    created_at: '2026-10-01T10:00:00Z',
    source_conversation_id: null,
  },
];

const graph = {
  nodes: [
    { id: 'user:1', label: 'You', type: 'User' },
    {
      id: 'memory:m1',
      label: 'Breathing',
      type: 'Memory',
      content_preview: 'I practise breathing every morning',
      source_ref: { kind: 'conversation', id: CONVERSATION_ID },
    },
    { id: 'memory:m2', label: 'Pune', type: 'Memory', content_preview: 'I live in Pune', source_ref: null },
    { id: 'concept:Stillness', label: 'Stillness', type: 'Concept' },
  ],
  edges: [
    { source: 'user:1', target: 'memory:m1', label: 'HAS_MEMORY' },
    { source: 'user:1', target: 'memory:m2', label: 'HAS_MEMORY' },
    { source: 'memory:m1', target: 'concept:Stillness', label: 'MENTIONS_CONCEPT' },
  ],
  count: 4,
};

const json = (body: unknown, headers: Record<string, string> = {}) => ({
  status: 200,
  contentType: 'application/json',
  headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': 'content-range', ...headers },
  body: JSON.stringify(body),
});

async function mockSignedInSeeker(page: Page) {
  await page.route(/\/auth\/v1\/user/, (route) => route.fulfill(json(session.user)));
  // Playwright runs the most recently registered matching route first, so the
  // catch-all goes before the specific one.
  await page.route(/\/rest\/v1\//, (route) => route.fulfill(json([], { 'content-range': '*/0' })));
  await page.route(/\/rest\/v1\/guru_memories/, (route) =>
    route.fulfill(json(memories, { 'content-range': `0-${memories.length - 1}/${memories.length}` })),
  );
  await page.route(/\/api\/kg\/personal-subgraph/, (route) => route.fulfill(json(graph)));
  await page.route(/\/api\/(?!kg\/personal-subgraph)/, (route) =>
    route.request().method() === 'OPTIONS'
      ? route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*' } })
      : route.fulfill(json({})),
  );

  await page.addInitScript(
    ([s, convs, extraKey]) => {
      const value = JSON.stringify(s);
      // Same key spread as seeker-journey.spec.ts, plus an explicit override.
      for (const key of [
        'sb-ozmjeuqbholoxypfxixb-auth-token',
        'sb-supabase-demo-auth-token',
        'sb-localhost-auth-token',
        'sb-127.0.0.1-auth-token',
        'sb-127-auth-token',
        extraKey,
      ]) {
        if (key) localStorage.setItem(key, value);
      }
      localStorage.setItem('askmukthiguru_tour_completed', '1');
      localStorage.setItem('askmukthiguru_consent_v1', 'rejected');
      localStorage.setItem('askmukthiguru_disclaimer_accepted', 'true');
      localStorage.setItem('askmukthiguru_conversations', JSON.stringify(convs));
      sessionStorage.setItem('askmukthiguru_pre_practice_asked', '1');
    },
    [session, conversations, process.env.E2E_SUPABASE_STORAGE_KEY ?? ''] as const,
  );
}

const visibleCount = (page: Page, testId: string) =>
  page.getByTestId(testId).evaluateAll((els) => els.filter((el) => (el as HTMLElement).offsetParent !== null).length);

test.describe('memory source links (mocked API)', () => {
  test.beforeEach(async ({ page }) => {
    await mockSignedInSeeker(page);
  });

  test('Profile > Memory links a proven source and says "Source unavailable" otherwise', async ({ page }) => {
    await page.goto('/profile?tab=memory');
    const link = page.getByTestId('memory-source-link');
    await expect(link).toHaveCount(1, LOAD);
    await expect(page.getByTestId('memory-source-unavailable')).toHaveCount(1);
    await expect(link).toHaveAttribute('href', new RegExp(`^/chat\\?conversation=${CONVERSATION_ID}&returnTo=`));
    const box = await link.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(43.5);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);

    await link.focus();
    await expect(link).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByText(/ORIGIN: I practise breathing/)).toBeVisible();
  });

  test('Wisdom Map shows the link, "Source unavailable", and no source row for ontology nodes', async ({ page }) => {
    await page.goto('/knowledge-graph');
    const node = (label: string) => page.locator(`[data-testid="kg-node"][aria-label="${label}"]`).first();
    await expect(node('Breathing')).toBeVisible(LOAD);

    await node('Breathing').dispatchEvent('click');
    await expect.poll(() => visibleCount(page, 'memory-source-link')).toBe(1);

    await node('Pune').dispatchEvent('click');
    await expect.poll(() => visibleCount(page, 'memory-source-unavailable')).toBe(1);
    expect(await visibleCount(page, 'memory-source-link')).toBe(0);

    await node('Stillness').dispatchEvent('click');
    await expect.poll(() => visibleCount(page, 'memory-source-unavailable')).toBe(0);
    expect(await visibleCount(page, 'memory-source-link')).toBe(0);
  });

  test('Wisdom Map nodes open with Enter, move focus into the details, and Escape closes them', async ({ page }) => {
    await page.goto('/knowledge-graph');
    await expect(page.locator('[data-testid="kg-node"][aria-label="Breathing"]').first()).toBeVisible(LOAD);

    let reached = false;
    for (let i = 0; i < 80 && !reached; i += 1) {
      await page.keyboard.press('Tab');
      reached = await page.evaluate(() => {
        const active = document.activeElement as HTMLElement | null;
        return !!active?.closest('.react-flow__node') && /Breathing/.test(active.textContent ?? '');
      });
    }
    expect(reached).toBe(true);

    await page.keyboard.press('Enter');
    await expect.poll(() => visibleCount(page, 'memory-source-link')).toBe(1);
    expect(await page.evaluate(() => document.activeElement?.hasAttribute('data-kg-detail'))).toBe(true);

    await page.keyboard.press('Escape');
    await expect.poll(() => visibleCount(page, 'memory-source-link')).toBe(0);
  });
});
