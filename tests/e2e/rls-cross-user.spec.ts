/**
 * RLS cross-user isolation: Alice's conversations and chat messages must
 * never be readable, updatable, or deletable by Bob — through the UI or
 * through the Supabase REST API.
 *
 * The API-level assertions mirror `backend/scripts/verify_rls_policies.py`
 * (the reference for what RLS isolation should look like) but run from
 * Playwright with real browser sessions.
 *
 * Environment:
 *   - Runs against LOCAL Supabase (`npx supabase status`), unless
 *     SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY are set
 *     (e.g. in CI), which take precedence.
 *   - The Vite dev server must be started with
 *     VITE_SUPABASE_URL=<local> VITE_SUPABASE_PUBLISHABLE_KEY=<local>.
 *
 * CRITICAL: service workers must be blocked — a stale SW could serve the
 * production-configured bundle (prod Supabase URL), silently testing the
 * wrong backend. Playwright's `page.route()` cannot intercept SW fetches.
 */
import { test as base, expect, type Page } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { randomUUID } from 'node:crypto';

interface SupabaseConfig {
  supabaseUrl: string;
  anonKey: string;
  serviceRoleKey: string;
}

interface RlsUser {
  email: string;
  password: string;
  id: string;
  accessToken: string;
}

interface RlsUsers {
  alice: RlsUser;
  bob: RlsUser;
  supabaseUrl: string;
  anonKey: string;
  serviceRoleKey: string;
  seededIds: { conversations: string[]; chat_messages: string[] };
}

// Ephemeral local-Supabase test account password. Override via E2E_TEST_PASSWORD
// for CI environments. The fallback value is only valid against a local
// ephemeral Supabase instance — it is NOT a production credential.
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'Password123!x'; // gitleaks:allow
const DOCKER_BIN = '/Users/harshodaikolluru/.docker/bin';

function runSupabaseStatus(): string | null {
  const paths: string[] = [process.env.PATH ?? ''];
  if (existsSync(DOCKER_BIN)) paths.unshift(`${DOCKER_BIN}:${paths[0]}`);
  for (const path of paths) {
    try {
      const out = spawnSync('npx', ['supabase', 'status', '--output', 'json'], {
        env: { ...process.env, PATH: path },
        encoding: 'utf8',
        timeout: 60_000,
      });
      if (out.status === 0 && out.stdout?.includes('{')) return out.stdout;
    } catch {
      // try the next PATH candidate
    }
  }
  return null;
}

async function discoverSupabaseConfig(): Promise<SupabaseConfig> {
  const envUrl = process.env.SUPABASE_URL;
  const envAnon = process.env.SUPABASE_ANON_KEY;
  const envService = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (envUrl && envAnon && envService) {
    return { supabaseUrl: envUrl.replace(/\/$/, ''), anonKey: envAnon, serviceRoleKey: envService };
  }
  const stdout = runSupabaseStatus();
  if (!stdout) {
    throw new Error(
      'RLS spec: cannot discover local Supabase keys. Start local Supabase (' +
        'npx supabase start) or set SUPABASE_URL/SUPABASE_ANON_KEY/SUPABASE_SERVICE_ROLE_KEY.',
    );
  }
  const json = JSON.parse(stdout.slice(stdout.indexOf('{')));
  return {
    supabaseUrl: String(json.API_URL).replace(/\/$/, ''),
    anonKey: String(json.ANON_KEY),
    serviceRoleKey: String(json.SERVICE_ROLE_KEY),
  };
}

function makeEmail(prefix: string): string {
  // AuthPage blocks sign-in for non-whitelisted domains — gmail.com only.
  return `${prefix}-${randomUUID().replace(/-/g, '').slice(0, 12)}@gmail.com`;
}

function adminHeaders(cfg: SupabaseConfig): Record<string, string> {
  return {
    apikey: cfg.serviceRoleKey,
    Authorization: `Bearer ${cfg.serviceRoleKey}`,
    'Content-Type': 'application/json',
    Prefer: 'return=representation',
  };
}

function userHeaders(cfg: SupabaseConfig, token: string): Record<string, string> {
  return {
    apikey: cfg.anonKey,
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    Prefer: 'return=representation',
  };
}

async function createUser(cfg: SupabaseConfig, email: string, password: string): Promise<string> {
  const res = await fetch(`${cfg.supabaseUrl}/auth/v1/admin/users`, {
    method: 'POST',
    headers: adminHeaders(cfg),
    body: JSON.stringify({ email, password, email_confirm: true }),
  });
  if (!res.ok) throw new Error(`createUser ${email} failed: ${res.status} ${await res.text()}`);
  return (await res.json()).id as string;
}

async function signInToken(cfg: SupabaseConfig, email: string, password: string): Promise<string> {
  const res = await fetch(`${cfg.supabaseUrl}/auth/v1/token?grant_type=password`, {
    method: 'POST',
    headers: { apikey: cfg.anonKey, 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(`signIn ${email} failed: ${res.status} ${await res.text()}`);
  return (await res.json()).access_token as string;
}

async function deleteUser(cfg: SupabaseConfig, userId: string): Promise<void> {
  await fetch(`${cfg.supabaseUrl}/auth/v1/admin/users/${userId}`, {
    method: 'DELETE',
    headers: adminHeaders(cfg),
  });
}

async function deleteRows(cfg: SupabaseConfig, table: string, ids: string[]): Promise<void> {
  if (!ids.length) return;
  const filter = `id=in.(${ids.join(',')})`;
  await fetch(`${cfg.supabaseUrl}/rest/v1/${table}?${filter}`, {
    method: 'DELETE',
    headers: adminHeaders(cfg),
  }).catch(() => undefined);
}

/** Supabase REST helpers — row-level isolation is enforced by Postgres RLS. */
async function selectRows(
  cfg: SupabaseConfig,
  token: string,
  table: string,
  filters: Record<string, string>,
): Promise<Record<string, unknown>[]> {
  const qs = new URLSearchParams();
  for (const [col, val] of Object.entries(filters)) qs.set(col, val);
  const res = await fetch(`${cfg.supabaseUrl}/rest/v1/${table}?${qs.toString()}`, {
    headers: userHeaders(cfg, token),
  });
  if (!res.ok) throw new Error(`select ${table} failed: ${res.status} ${await res.text()}`);
  return (await res.json()) as Record<string, unknown>[];
}

async function insertRow(
  cfg: SupabaseConfig,
  token: string,
  table: string,
  row: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const res = await fetch(`${cfg.supabaseUrl}/rest/v1/${table}`, {
    method: 'POST',
    headers: userHeaders(cfg, token),
    body: JSON.stringify(row),
  });
  if (!res.ok) throw new Error(`insert ${table} failed: ${res.status} ${await res.text()}`);
  const body = (await res.json()) as Record<string, unknown>[];
  if (!body?.length) throw new Error(`insert ${table} returned no rows`);
  return body[0];
}

async function insertAdminRow(
  cfg: SupabaseConfig,
  table: string,
  row: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const res = await fetch(`${cfg.supabaseUrl}/rest/v1/${table}`, {
    method: 'POST',
    headers: adminHeaders(cfg),
    body: JSON.stringify(row),
  });
  if (!res.ok) throw new Error(`admin insert ${table} failed: ${res.status} ${await res.text()}`);
  const body = (await res.json()) as Record<string, unknown>[];
  if (!body?.length) throw new Error(`admin insert ${table} returned no rows`);
  return body[0];
}

async function updateRows(
  cfg: SupabaseConfig,
  token: string,
  table: string,
  patch: Record<string, unknown>,
  filters: Record<string, string>,
): Promise<Record<string, unknown>[]> {
  const qs = new URLSearchParams();
  for (const [col, val] of Object.entries(filters)) qs.set(col, val);
  const res = await fetch(`${cfg.supabaseUrl}/rest/v1/${table}?${qs.toString()}`, {
    method: 'PATCH',
    headers: userHeaders(cfg, token),
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`update ${table} failed: ${res.status} ${await res.text()}`);
  return (await res.json()) as Record<string, unknown>[];
}

async function deleteRowsAs(
  cfg: SupabaseConfig,
  token: string,
  table: string,
  filters: Record<string, string>,
): Promise<Record<string, unknown>[]> {
  const qs = new URLSearchParams();
  for (const [col, val] of Object.entries(filters)) qs.set(col, val);
  const res = await fetch(`${cfg.supabaseUrl}/rest/v1/${table}?${qs.toString()}`, {
    method: 'DELETE',
    headers: userHeaders(cfg, token),
  });
  if (!res.ok) throw new Error(`delete ${table} failed: ${res.status} ${await res.text()}`);
  return (await res.json()) as Record<string, unknown>[];
}

/** Sign in through the real UI (AuthPage email form) and land on /chat. */
async function signInViaUI(page: Page, email: string, password: string): Promise<void> {
  await page.goto('/auth');
  await page.locator('#email').fill(email);
  await page.locator('#password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL((url) => !/^\/auth(\/|$)/.test(url.pathname), { timeout: 25_000 });
  await page.goto('/chat');
  await expect(page.getByRole('textbox', { name: 'Your message' })).toBeVisible({ timeout: 15_000 });
  await dismissPrePracticeGate(page);
}

/**
 * The PrePracticeGate modal (aria-labelledby="pre-practice-title") overlays
 * /chat for fresh sessions and intercepts pointer events — a plain click on
 * the composer's Send button would wait for it forever. Dismiss it like a
 * real user would (Skip) whenever it appears.
 */
async function dismissPrePracticeGate(page: Page): Promise<void> {
  const dialog = page.getByRole('dialog', { name: /soul sync|serene mind|before we begin|chat with the guru/i });
  try {
    await dialog.waitFor({ state: 'visible', timeout: 5_000 });
  } catch {
    return; // gate did not appear — nothing to dismiss
  }
  const skip = dialog.getByRole('button', { name: /^skip(?: tour)?$/i });
  if (await skip.isVisible()) await skip.click();
  await expect(dialog).not.toBeVisible({ timeout: 5_000 });
}

/**
 * Two fresh, isolated users (Alice + Bob) created through the local Supabase
 * Admin API. Teardown removes seeded rows first (FKs block user deletion)
 * and then the users themselves.
 */
const test = base.extend<{ rlsUsers: RlsUsers }>({
  rlsUsers: [
    async ({}, use) => {
      const cfg = await discoverSupabaseConfig();
      const users: RlsUsers = {
        alice: { email: makeEmail('alice'), password: PASSWORD, id: '', accessToken: '' },
        bob: { email: makeEmail('bob'), password: PASSWORD, id: '', accessToken: '' },
        supabaseUrl: cfg.supabaseUrl,
        anonKey: cfg.anonKey,
        serviceRoleKey: cfg.serviceRoleKey,
        seededIds: { conversations: [], chat_messages: [] },
      };
      users.alice.id = await createUser(cfg, users.alice.email, users.alice.password);
      users.bob.id = await createUser(cfg, users.bob.email, users.bob.password);
      users.alice.accessToken = await signInToken(cfg, users.alice.email, users.alice.password);
      users.bob.accessToken = await signInToken(cfg, users.bob.email, users.bob.password);

      await use(users);

      for (const table of ['chat_messages', 'conversations'] as const) {
        await deleteRows(cfg, table, users.seededIds[table]);
      }
      await deleteUser(cfg, users.alice.id);
      await deleteUser(cfg, users.bob.id);
    },
    { scope: 'worker' },
  ],
});

test.use({ serviceWorkers: 'block' });

test.describe('RLS cross-user isolation', () => {
  test('Bob cannot read Alice conversation through the UI', async ({ browser, rlsUsers }) => {
    const users = rlsUsers;
    const aliceCtx = await browser.newContext();
    const bobCtx = await browser.newContext();
    try {
      // ── Alice signs in and sends a message ─────────────────────────────
      const alicePage = await aliceCtx.newPage();
      await signInViaUI(alicePage, users.alice.email, users.alice.password);

      const marker = `alice-rls-secret-${Date.now()}`;
      await alicePage.getByRole('textbox', { name: 'Your message' }).fill(marker);
      await alicePage.getByRole('button', { name: 'Send message' }).click();
      // The marker appears in the message bubble, the sidebar preview, and the
      // thinking pill — any visible occurrence proves the send registered.
      await expect(alicePage.getByText(marker).first()).toBeVisible({ timeout: 20_000 });

      // Extract the conversation id from the local-first store. Note:
      // `expect.poll()` does not resolve to the last polled value on this
      // Playwright version, so capture it via a side effect inside the poll.
      let conversationId: string | null = null;
      await expect
        .poll(
          async () => {
            const id = await alicePage.evaluate((needle) => {
              const raw = localStorage.getItem('askmukthiguru_conversations');
              if (!raw) return null;
              const convs = JSON.parse(raw) as Array<{
                id: string;
                messages: Array<{ content?: string }>;
              }>;
              const hit = (convs ?? []).find(
                (c) =>
                  c.id &&
                  (c.messages ?? []).some(
                    (m) => typeof m.content === 'string' && m.content.includes(needle),
                  ),
              );
              return hit?.id ?? null;
            }, marker);
            if (id) conversationId = id;
            return id;
          },
          { timeout: 15_000 },
        )
        .not.toBeNull();
      expect(conversationId, 'conversation id extracted from local store').not.toBeNull();
      users.seededIds.conversations.push(conversationId!);

      // Cloud sync is fire-and-forget: wait until the message row exists in
      // Supabase so Bob's checks run against a server-side replica.
      await expect
        .poll(
          async () =>
            (
              await selectRows(users, users.alice.accessToken, 'chat_messages', {
                conversation_id: `eq.${conversationId}`,
              })
            ).length,
          { timeout: 30_000 },
        )
        .toBeGreaterThan(0);

      // ── Bob signs in and deep-links to Alice's conversation ────────────
      const bobPage = await bobCtx.newPage();
      await signInViaUI(bobPage, users.bob.email, users.bob.password);

      await bobPage.goto(`/chat?conversation=${conversationId}`);
      await bobPage.waitForLoadState('domcontentloaded');
      // Let the deep-link effect (and any gate) settle before asserting.
      await bobPage.waitForTimeout(2_000);

      // The deep link only loads conversations from the signed-in user's own
      // local store, and RLS hides Alice's rows server-side — so the message
      // must never surface. toHaveCount(0) re-asserts for the full expect
      // timeout, covering any late render.
      await expect(bobPage.getByText(marker)).toHaveCount(0);
      await expect(bobPage.getByText('alice-rls-secret-')).toHaveCount(0);
      // Bob's own composer still renders — no crash, no leak.
      await expect(bobPage.getByRole('textbox', { name: 'Your message' })).toBeVisible();
    } finally {
      await aliceCtx.close();
      await bobCtx.close();
    }
  });

  test('Bob cannot read, update, or delete Alice rows through the REST API (RLS)', async ({
    rlsUsers,
  }) => {
    const users = rlsUsers;

    // Seed Alice-owned rows exactly like verify_rls_policies.py does.
    const conv = await insertAdminRow(users, 'conversations', {
      user_id: users.alice.id,
      title: 'Alice private conv',
    });
    const convId = String(conv.id);
    const msg = await insertAdminRow(users, 'chat_messages', {
      conversation_id: convId,
      role: 'user',
      content: 'Alice private message',
    });
    const msgId = String(msg.id);
    users.seededIds.conversations.push(convId);
    users.seededIds.chat_messages.push(msgId);

    // Positive control: Alice reads her own rows.
    const aliceConv = await selectRows(users, users.alice.accessToken, 'conversations', {
      id: `eq.${convId}`,
    });
    expect(aliceConv, 'Alice must read her own conversation').toHaveLength(1);
    const aliceMsgs = await selectRows(users, users.alice.accessToken, 'chat_messages', {
      id: `eq.${msgId}`,
    });
    expect(aliceMsgs, 'Alice must read her own messages').toHaveLength(1);

    // Bob cannot READ Alice's rows.
    const bobConvRead = await selectRows(users, users.bob.accessToken, 'conversations', {
      id: `eq.${convId}`,
    });
    expect(bobConvRead, 'Bob must not read Alice conversation').toHaveLength(0);
    const bobMsgRead = await selectRows(users, users.bob.accessToken, 'chat_messages', {
      id: `eq.${msgId}`,
    });
    expect(bobMsgRead, 'Bob must not read Alice chat message').toHaveLength(0);

    // Bob cannot UPDATE Alice's rows.
    const bobConvUpdate = await updateRows(
      users,
      users.bob.accessToken,
      'conversations',
      { title: 'Hacked by Bob' },
      { id: `eq.${convId}` },
    );
    expect(bobConvUpdate, 'Bob must not update Alice conversation').toHaveLength(0);
    const bobMsgUpdate = await updateRows(
      users,
      users.bob.accessToken,
      'chat_messages',
      { content: 'Hacked by Bob' },
      { id: `eq.${msgId}` },
    );
    expect(bobMsgUpdate, 'Bob must not update Alice chat message').toHaveLength(0);

    // Bob cannot DELETE Alice's rows.
    const bobConvDelete = await deleteRowsAs(users, users.bob.accessToken, 'conversations', {
      id: `eq.${convId}`,
    });
    expect(bobConvDelete, 'Bob must not delete Alice conversation').toHaveLength(0);
    const bobMsgDelete = await deleteRowsAs(users, users.bob.accessToken, 'chat_messages', {
      id: `eq.${msgId}`,
    });
    expect(bobMsgDelete, 'Bob must not delete Alice chat message').toHaveLength(0);

    // Rows are intact and unmodified for Alice after Bob's attempts.
    const intactConv = await selectRows(users, users.alice.accessToken, 'conversations', {
      id: `eq.${convId}`,
    });
    expect(intactConv, 'Alice conversation must be intact after Bob attempts').toHaveLength(1);
    expect(String(intactConv[0].title)).toBe('Alice private conv');
    const intactMsg = await selectRows(users, users.alice.accessToken, 'chat_messages', {
      id: `eq.${msgId}`,
    });
    expect(intactMsg, 'Alice message must be intact after Bob attempts').toHaveLength(1);
    expect(String(intactMsg[0].content)).toBe('Alice private message');
  });
});
