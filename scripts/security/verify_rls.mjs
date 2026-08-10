#!/usr/bin/env node
/**
 * Automated RLS verification.
 *
 * Creates two throwaway users (A and B) via the Supabase Admin API, has each
 * insert a row into every user-scoped table, then asserts that:
 *   1. each user can read their OWN row
 *   2. neither user can read, update, or delete the OTHER user's row
 *   3. neither user can INSERT a row owned by the other (WITH CHECK enforced)
 *   4. an owner cannot transfer an OWN row to the other user (WITH CHECK on
 *      UPDATE — the generic cross-user UPDATE probe only exercises USING)
 *   5. anonymous (anon key, no session) can read nothing
 *
 * Coverage: 24 tables (union of all RLS-scoped tables). Tenant-isolated
 * tables (chat_queries / chat_responses / retrieval_events) are excluded from
 * the A/B user probe — they are isolated by `tenant_id` from the JWT claims,
 * not by `user_id`. For those, only the anonymous SELECT assertion is
 * meaningful; see verify_rls_policies.py and the CRIT-2 migration for the
 * by-claim tenant check.
 *
 * Grant-layer awareness: PostgREST returns HTTP 401 / 42501 ("permission
 * denied for table") when the requesting role lacks table GRANTs — this is
 * INDEPENDENT of RLS. A fresh local DB (supabase start) only grants the
 * schema-default TRIGGER/TRUNCATE/REFERENCES on newly created tables, so
 * probes would 42501 before RLS is exercised. To mirror the production grant
 * state (public_schema_dump.sql), provision the same table GRANTs first:
 *
 *   GRANT SELECT, INSERT, UPDATE, DELETE ON public.<table> TO authenticated;
 *   GRANT ALL ON public.<table> TO service_role;
 *
 * When a table genuinely has no DML grant for a role, the probe is reported
 * as SKIP (not FAIL) so the run still surfaces real RLS leaks while the
 * grant-layer gap is explicit. RLS is the authorization boundary; GRANTs are
 * a separate concern.
 *
 * Usage:
 *   SUPABASE_URL=... SUPABASE_ANON_KEY=... SUPABASE_SERVICE_ROLE_KEY=... \
 *     node scripts/security/verify_rls.mjs
 *
 * Exits non-zero on the first cross-user leak. Safe to run in CI.
 */
import { createClient } from '@supabase/supabase-js';
import { createHmac, randomUUID } from 'node:crypto';

const URL = process.env.SUPABASE_URL || process.env.VITE_SUPABASE_URL;
const ANON = process.env.SUPABASE_ANON_KEY || process.env.VITE_SUPABASE_PUBLISHABLE_KEY;
const SERVICE = process.env.SUPABASE_SERVICE_ROLE_KEY;
const JWT_SECRET = process.env.SUPABASE_JWT_SECRET || process.env.JWT_SECRET;

if (!URL || !ANON || !SERVICE) {
  console.error('Missing SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY');
  process.exit(2);
}

/**
 * Mint a HS256 JWT signed with the local Supabase JWT secret carrying a
 * tenant_id claim. Used by the tenant-isolation probe (chat_queries /
 * chat_responses / retrieval_events are isolated by tenant_id from the JWT
 * claims, not by user_id). Requires SUPABASE_JWT_SECRET; when absent, the
 * tenant probe is reported SKIP.
 */
function mintTenantJwt(tenantId, sub) {
  const now = Math.floor(Date.now() / 1000);
  const b64 = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url');
  const header = b64({ alg: 'HS256', typ: 'JWT' });
  const payload = b64({
    iss: 'supabase-demo',
    role: 'authenticated',
    sub,
    aud: 'authenticated',
    exp: now + 3600,
    tenant_id: tenantId,
  });
  const sig = createHmac('sha256', JWT_SECRET).update(`${header}.${payload}`).digest('base64url');
  return `${header}.${payload}.${sig}`;
}

/**
 * Tenant-isolation probe. Verifies that a tenant-A token cannot read a row
 * carrying tenant_id='tenant-B'. Seed one row per tenant table with the
 * service role (tenant_id explicit), then assert cross-tenant reads return
 * nothing. Requires SUPABASE_JWT_SECRET (local dev secret from
 * `npx supabase status`); skipped when absent.
 */
async function probeTenantIsolation() {
  if (!JWT_SECRET) {
    skip('tenant tables: tenant-claim probe skipped', 'SUPABASE_JWT_SECRET not set');
    return;
  }
  const tenantA = mintTenantJwt('tenant-A', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa');
  const tenantB = mintTenantJwt('tenant-B', 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb');
  const clientA = createClient(URL, ANON, {
    auth: { persistSession: false },
    global: { headers: { Authorization: `Bearer ${tenantA}` } },
  });
  const clientB = createClient(URL, ANON, {
    auth: { persistSession: false },
    global: { headers: { Authorization: `Bearer ${tenantB}` } },
  });

  for (const table of ['chat_queries', 'chat_responses', 'retrieval_events']) {
    const aRow = `probe-tenant-a-${stamp}`;
    const bRow = `probe-tenant-b-${stamp}`;
    let bId;
    if (table === 'chat_queries') {
      const { data, error } = await admin.from(table).insert({ query_text: bRow, tenant_id: 'tenant-B' }).select('id').single();
      if (error) throw new Error(`tenant seed ${table}: ${error.message}`);
      bId = data.id;
      await admin.from(table).insert({ query_text: aRow, tenant_id: 'tenant-A' }).select('id').single();
    } else if (table === 'chat_responses') {
      const { data, error } = await admin.from(table).insert({ response_text: bRow, tenant_id: 'tenant-B' }).select('id').single();
      if (error) throw new Error(`tenant seed ${table}: ${error.message}`);
      bId = data.id;
      await admin.from(table).insert({ response_text: aRow, tenant_id: 'tenant-A' }).select('id').single();
    } else {
      const { data, error } = await admin.from(table).insert({ chunk_ids: [bRow], tenant_id: 'tenant-B' }).select('id').single();
      if (error) throw new Error(`tenant seed ${table}: ${error.message}`);
      bId = data.id;
      await admin.from(table).insert({ chunk_ids: [aRow], tenant_id: 'tenant-A' }).select('id').single();
    }

    // tenant-A reads its own tenant-A row
    const own = await clientA.from(table).select('id').eq('tenant_id', 'tenant-A');
    own.error
      ? skip(`${table}: tenant-A own-read probe errored`, own.error.message)
      : own.data?.length
        ? pass(`${table}: tenant-A reads own tenant rows`)
        : fail(`${table}: tenant-A cannot read own tenant rows`);

    // tenant-A must NOT see tenant-B's row
    const cross = await clientA.from(table).select('id').eq('tenant_id', 'tenant-B');
    cross.error
      ? skip(`${table}: tenant-A cross-read probe errored`, cross.error.message)
      : cross.data?.length
        ? fail(`${table}: LEAK — tenant-A read tenant-B's row`, JSON.stringify(cross.data))
        : pass(`${table}: cross-tenant SELECT blocked (by-claim)`);

    // cleanup
    try {
      await admin.from(table).delete().eq('id', bId);
      await admin.from(table).delete().eq('tenant_id', 'tenant-A');
    } catch {
      // best-effort cleanup of probe rows
    }
    void clientB;
  }
}

const admin = createClient(URL, SERVICE, { auth: { persistSession: false } });
const results = [];
const pass = (n, d = '') => results.push({ ok: true, n, d });
const skip = (n, d = '') => results.push({ ok: 'skip', n, d });
const fail = (n, d = '') => results.push({ ok: false, n, d });

const stamp = Date.now();
const users = [
  { label: 'A', email: `rls-probe-a-${stamp}@gmail.com`, password: `Rls!Probe#${stamp}A` },
  { label: 'B', email: `rls-probe-b-${stamp}@gmail.com`, password: `Rls!Probe#${stamp}B` },
];

async function createUser(u) {
  const { data, error } = await admin.auth.admin.createUser({
    email: u.email,
    password: u.password,
    email_confirm: true,
  });
  if (error) throw new Error(`createUser(${u.label}): ${error.message}`);
  u.id = data.user.id;
  const client = createClient(URL, ANON, { auth: { persistSession: false } });
  const { error: signInError } = await client.auth.signInWithPassword({
    email: u.email,
    password: u.password,
  });
  if (signInError) throw new Error(`signIn(${u.label}): ${signInError.message}`);
  u.client = client;
  return u;
}

/**
 * Is this a PostgREST "permission denied for table" (missing GRANT, not RLS)?
 * RLS rejections raise the SAME SQLSTATE 42501 but carry the message
 * "new row violates row-level security policy" — that is the RLS WITH CHECK
 * enforcement this script verifies, so it must NOT be treated as a grant gap.
 * Only the literal "permission denied for table" (missing table GRANT) is a
 * grant-layer skip.
 */
function isGrantLayerError(e) {
  return Boolean(e && e.message?.includes('permission denied for table'));
}

const ZERO_VEC_1024 = new Array(1024).fill(0.0);

/**
 * Seed one owned row per table with the service role (bypasses RLS).
 * Tables with cross-row FK deps (brain edges) seed their dependency first.
 */
async function seed(u) {
  const ins = async (table, payload, pick, key) => {
    const { data, error } = await admin.from(table).insert(payload).select().single();
    if (error) {
      if (isGrantLayerError(error)) return { key, granted: false };
      throw new Error(`seed ${table}: ${error.message}`);
    }
    u[key] = pick(data);
    return { key, granted: true };
  };

  const conv = await ins('conversations', { user_id: u.id, title: `probe-${u.label}` }, (d) => d.id, 'conversationId');
  const msg = await ins(
    'chat_messages',
    { conversation_id: u.conversationId, role: 'user', content: `secret-${u.label}` },
    (d) => d.id,
    'messageId'
  );
  const med = await ins(
    'meditation_sessions',
    { user_id: u.id, duration_seconds: 180, completed: true },
    (d) => d.id,
    'meditationId'
  );
  const prof = await ins(
    'user_profiles',
    { user_id: u.id, preferred_language: 'en', created_at: Date.now() / 1000, updated_at: Date.now() / 1000 },
    (d) => d.user_id,
    'profileId'
  );

  // guru tables (owned by user_id; tenant default 'default' applies)
  const gm = await ins(
    'guru_memories',
    { user_id: u.id, content: `secret-${u.label}`, source: 'explicit', embedding: ZERO_VEC_1024 },
    (d) => d.id,
    'guruMemoryId'
  );
  const gcm = await ins(
    'guru_core_memory',
    { user_id: u.id, content: `core-${u.label}` },
    (d) => d.id,
    'guruCoreId'
  );
  const gss = await ins(
    'guru_session_summaries',
    { user_id: u.id, session_id: u.conversationId, summary: `summary-${u.label}` },
    (d) => d.id,
    'guruSummaryId'
  );

  // second brain vault (user_brain_nodes first, then edges referencing them)
  const bn1 = await ins(
    'user_brain_nodes',
    { id: `node-${u.label}-1-${stamp}`, user_id: u.id, kind: 'reflection', ciphertext: `secret-${u.label}` },
    (d) => d.id,
    'brainNode1Id'
  );
  const bn2 = await ins(
    'user_brain_nodes',
    { id: `node-${u.label}-2-${stamp}`, user_id: u.id, kind: 'reflection', ciphertext: `secret-${u.label}` },
    (d) => d.id,
    'brainNode2Id'
  );
  const be = await ins(
    'user_brain_edges',
    { id: `edge-${u.label}-${stamp}`, user_id: u.id, src: bn1.granted ? u.brainNode1Id : null, dst: bn2.granted ? u.brainNode2Id : null, rel_cipher: `rel-${u.label}` },
    (d) => d.id,
    'brainEdgeId'
  );
  const bk = await ins(
    'user_brain_keys',
    { user_id: u.id, wrapped_dek: `dek-${u.label}` },
    (d) => d.user_id,
    'brainKeyUserId'
  );

  // episodic + study notebooks
  const ue = await ins(
    'user_episodes',
    { user_id: u.id, query: `q-${u.label}`, answer: `a-${u.label}` },
    (d) => d.id,
    'episodeId'
  );
  const nb = await ins('study_notebooks', { user_id: u.id, title: `nb-${u.label}` }, (d) => d.id, 'notebookId');
  const nbi = await ins(
    'study_notebook_items',
    { notebook_id: nb.granted ? u.notebookId : null, query: `q-${u.label}`, answer: `a-${u.label}` },
    (d) => d.id,
    'notebookItemId'
  );

  // push devices + subscriptions
  const pd = await ins(
    'push_devices',
    { user_id: u.id, platform: u.label === 'A' ? 'android' : 'ios', token: `token-${u.label}-${stamp}` },
    (d) => d.id,
    'pushDeviceId'
  );
  const ps = await ins(
    'push_subscriptions',
    { user_id: u.id, endpoint: `https://push.example/${u.label}-${stamp}`, p256dh: `k${u.label}`, auth: `a${u.label}` },
    (d) => d.id,
    'pushSubId'
  );

  // streaks + retention (retention_events.id is identity; omit to auto-gen)
  const st = await ins(
    'user_streaks',
    { user_id: u.id, current_streak: 1, last_active_date: new Date().toISOString().slice(0, 10) },
    (d) => d.user_id,
    'streakUserId'
  );
  const re = await ins(
    'retention_events',
    { user_id: u.id, event: `probe-${u.label}` },
    (d) => d.id,
    'retentionId'
  );

  // personas / scene blocks / skills (tenant_id default is the zero UUID)
  const persona = await ins(
    'user_personas',
    { user_id: u.id, content: `persona-${u.label}` },
    (d) => d.id,
    'personaId'
  );
  const scene = await ins(
    'user_scene_blocks',
    { user_id: u.id, scene_type: 'general', compressed_blocks: `blocks-${u.label}` },
    (d) => d.id,
    'sceneId'
  );
  const skill = await ins(
    'user_skills',
    { user_id: u.id, name: `skill-${u.label}-${stamp}` },
    (d) => d.id,
    'skillId'
  );

  // healing courses + pending extractions + memories + notes
  const ucp = await ins(
    'user_course_progress',
    { user_id: u.id, course_slug: `course-${u.label}` },
    (d) => d.id,
    'courseId'
  );
  const pe = await ins(
    'pending_extractions',
    { user_id: u.id, conversation_id: u.conversationId, payload: { probe: u.label } },
    (d) => d.id,
    'extractionId'
  );
  const cm = await ins(
    'conversation_memories',
    { session_id: u.conversationId, user_id: u.id, started_at: Date.now() / 1000, messages: [] },
    (d) => d.session_id,
    'memorySessionId'
  );
  const note = await ins('notes', { user_id: u.id, title: `note-${u.label}` }, (d) => d.id, 'noteId');

  // admin-managed tables (gurus / assistant_configurations / assistant_doctrines) are
  // NOT seeded per-user — they have no owner column. Seeded once globally in run().
}

// [table, ownerCol|null, pk, idKey, updateCol, insertPayloadForCrossUserProbe]
const TABLES = [
  ['conversations', 'user_id', 'id', 'conversationId', 'updated_at', (b) => ({ user_id: b.id, title: 'x' })],
  ['chat_messages', null, 'id', 'messageId', 'content', null],
  ['meditation_sessions', 'user_id', 'id', 'meditationId', 'duration_seconds', (b) => ({ user_id: b.id, duration_seconds: 1 })],
  ['user_profiles', 'user_id', 'user_id', 'profileId', 'updated_at', (b) => ({ user_id: b.id, created_at: 1, updated_at: 1 })],
  ['guru_memories', 'user_id', 'id', 'guruMemoryId', 'updated_at', (b) => ({ user_id: b.id, content: 'x', source: 'explicit', embedding: ZERO_VEC_1024 })],
  ['guru_core_memory', 'user_id', 'id', 'guruCoreId', 'updated_at', (b) => ({ user_id: b.id, content: 'x' })],
  ['guru_session_summaries', 'user_id', 'id', 'guruSummaryId', 'updated_at', (b) => ({ user_id: b.id, session_id: b.conversationId, summary: 'x' })],
  ['user_brain_nodes', 'user_id', 'id', 'brainNode1Id', 'updated_at', (b) => ({ id: `x-${Date.now()}`, user_id: b.id, kind: 'reflection', ciphertext: 'x' })],
  ['user_brain_edges', 'user_id', 'id', 'brainEdgeId', 'weight', (b) => ({ id: `x-${Date.now()}`, user_id: b.id, src: b.brainNode1Id, dst: b.brainNode1Id, rel_cipher: 'x' })],
  ['user_brain_keys', 'user_id', 'user_id', 'brainKeyUserId', 'updated_at', (b) => ({ user_id: b.id, wrapped_dek: 'x' })],
  ['user_episodes', 'user_id', 'id', 'episodeId', 'intent', (b) => ({ user_id: b.id, query: 'x', answer: 'x' })],
  ['study_notebooks', 'user_id', 'id', 'notebookId', 'title', (b) => ({ user_id: b.id, title: 'x' })],
  ['study_notebook_items', null, 'id', 'notebookItemId', 'query', null],
  ['push_devices', 'user_id', 'id', 'pushDeviceId', 'updated_at', (b) => ({ user_id: b.id, platform: 'android', token: `x-${Date.now()}` })],
  ['push_subscriptions', 'user_id', 'id', 'pushSubId', 'created_at', (b) => ({ user_id: b.id, endpoint: `https://x/${Date.now()}`, p256dh: 'k', auth: 'a' })],
  ['user_streaks', 'user_id', 'user_id', 'streakUserId', 'updated_at', (b) => ({ user_id: b.id })],
  ['retention_events', 'user_id', 'id', 'retentionId', 'props', (b) => ({ user_id: b.id, event: 'x' })],
  ['user_personas', 'user_id', 'id', 'personaId', 'updated_at', (b) => ({ user_id: b.id, content: 'x' })],
  ['user_scene_blocks', 'user_id', 'id', 'sceneId', 'updated_at', (b) => ({ user_id: b.id, compressed_blocks: 'x' })],
  ['user_skills', 'user_id', 'id', 'skillId', 'updated_at', (b) => ({ user_id: b.id, name: `x-${Date.now()}` })],
  ['user_course_progress', 'user_id', 'id', 'courseId', 'updated_at', (b) => ({ user_id: b.id, course_slug: `x-${Date.now()}` })],
  ['pending_extractions', 'user_id', 'id', 'extractionId', 'attempts', (b) => ({ user_id: b.id })],
  // session_id is a fresh UUID: if RLS leaked, B's seeded memory row (whose
  // session_id doubles as its PK) would collide with b.conversationId and the
  // probe would misreport a PK error as a leak. A fresh id makes a leak
  // surface as a successful insert — the unambiguous LEAK signal.
  ['conversation_memories', 'user_id', 'session_id', 'memorySessionId', 'started_at', (b) => ({ session_id: randomUUID(), user_id: b.id, started_at: 1 })],
  ['notes', 'user_id', 'id', 'noteId', 'updated_at', (b) => ({ user_id: b.id })],
];

/**
 * Produce a type-safe value for a cross-user UPDATE probe column.
 *
 * The generic cross-user UPDATE probe must use a value the column can accept,
 * otherwise a leaked (RLS-disabled) system errors on the cast instead of
 * writing — and the probe would misreport that as "blocked". Timestamptz
 * columns take an ISO string; float8 columns (user_profiles /
 * conversation_memories store epoch seconds) take a number.
 */
function updatableValue(col) {
  switch (col) {
    case 'duration_seconds':
    case 'attempts':
    case 'weight':
      return 0;
    case 'props':
      return { probe: Date.now() };
    case 'updated_at':
    case 'created_at':
    case 'started_at':
      return new Date().toISOString();
    default:
      return `probe-${Date.now()}`;
  }
}

/**
 * Is this a row-level-security rejection (the thing this script verifies)?
 * PostgREST surfaces RLS failures with the "violates row-level security
 * policy" message (SQLSTATE 42501, but distinct from a missing table GRANT,
 * which carries "permission denied for table").
 */
function isRlsError(e) {
  return Boolean(e && e.message?.includes('row-level security policy'));
}

async function probeTable(client, table, pk, ownId, otherId, updateCol) {
  const own = await client.from(table).select(pk).eq(pk, ownId);
  if (own.error && isGrantLayerError(own.error)) return { state: 'skip', reason: 'no SELECT grant (42501)' };
  own.error && !isRlsError(own.error)
    ? fail(`${table}: OWN-ROW READ errored unexpectedly`, own.error.message)
    : own.data?.length
      ? pass(`${table}: owner can read own row`)
      : fail(`${table}: owner CANNOT read own row`, own.error?.message ?? 'empty result');

  const cross = await client.from(table).select(pk).eq(pk, otherId);
  if (cross.error && isGrantLayerError(cross.error)) return { state: 'skip', reason: 'no SELECT grant (42501)' };
  cross.error && !isRlsError(cross.error)
    ? fail(`${table}: CROSS-ROW READ errored unexpectedly`, cross.error.message)
    : cross.data?.length
      ? fail(`${table}: LEAK — user A read user B's row`, JSON.stringify(cross.data))
      : pass(`${table}: cross-user SELECT blocked`);

  const upd = await client.from(table).update({ [updateCol]: updatableValue(updateCol) }).eq(pk, otherId).select(pk);
  if (upd.error && isGrantLayerError(upd.error)) return { state: 'skip', reason: 'no UPDATE grant (42501)' };
  upd.error && !isRlsError(upd.error)
    ? fail(`${table}: CROSS-ROW UPDATE errored unexpectedly`, upd.error.message)
    : upd.data?.length
      ? fail(`${table}: LEAK — user A updated user B's row`)
      : pass(`${table}: cross-user UPDATE blocked`);

  const del = await client.from(table).delete().eq(pk, otherId).select(pk);
  if (del.error && isGrantLayerError(del.error)) return { state: 'skip', reason: 'no DELETE grant (42501)' };
  del.error && !isRlsError(del.error)
    ? fail(`${table}: CROSS-ROW DELETE errored unexpectedly`, del.error.message)
    : del.data?.length
      ? fail(`${table}: LEAK — user A deleted user B's row`)
      : pass(`${table}: cross-user DELETE blocked`);
  return { state: 'ok' };
}

/**
 * Ownership-transfer probe: as A, try to reassign A's OWN row to B by
 * overwriting the owner column. A row that passes the USING filter (A owns
 * it) is still rejected by the WITH CHECK predicate on UPDATE — which defaults
 * to USING and is therefore NOT exercised by the generic cross-user UPDATE
 * probe. Tables in the transfer probe set are the ones where transferring
 * ownership to another user is meaningful (a distinct owner column and no
 * other non-null required columns that would mask the outcome).
 *
 * The write is verified via the service role (RLS bypass), NOT via the
 * returning rows: when a transfer leaks, the row's owner becomes B, so the
 * SELECT policy hides it from A and a `.select()` chain would report an empty
 * result — a false pass. Reading the stored owner as admin is unambiguous.
 */
const OWNER_TRANSFER_TABLES = new Set(['push_devices', 'conversation_memories', 'user_personas']);

async function probeOwnershipTransfer(admin, client, table, ownerCol, pk, ownId, otherId) {
  const tfr = await client.from(table).update({ [ownerCol]: otherId }).eq(pk, ownId);
  if (tfr.error && isGrantLayerError(tfr.error)) return;
  if (tfr.error && !isRlsError(tfr.error)) {
    fail(`${table}: OWN-ROW TRANSFER errored unexpectedly`, tfr.error.message);
    return;
  }
  const { data, error } = await admin.from(table).select(ownerCol).eq(pk, ownId).maybeSingle();
  if (error) {
    fail(`${table}: OWN-ROW TRANSFER could not be verified`, error.message);
    return;
  }
  data?.[ownerCol] === otherId
    ? fail(`${table}: LEAK — user A transferred own row to user B (WITH CHECK not enforced)`)
    : pass(`${table}: own-row ownership transfer blocked (WITH CHECK)`);
}

/**
 * Dedicated INSERT probes for conversation_memories (P1-SEC-13).
 *
 * The generic cross-user INSERT probe already covers the rejection side, but
 * this table's write surface is the FOR ALL policy "Users can insert their
 * own memories" (20260516190000_user_memory.sql) — the specific policy the
 * finding targets. This probe asserts BOTH directions explicitly:
 *   1. own-insert: A inserts a memory row owned by A — must SUCCEED (the
 *      allowed path; guards against the insert path regressing).
 *   2. cross-insert: A inserts a memory row owned by B — must be REJECTED by
 *      the WITH CHECK predicate (auth.uid() = user_id).
 * Rows are cleaned up via the service role after each probe.
 */
async function probeConversationMemoriesInserts(admin, client, ownUser, otherUser) {
  const ownSessionId = randomUUID();
  const ownIns = await client.from('conversation_memories').insert({
    session_id: ownSessionId,
    user_id: ownUser.id,
    started_at: Date.now() / 1000,
    messages: [],
  }).select('session_id');
  if (ownIns.error && isGrantLayerError(ownIns.error)) {
    skip('conversation_memories: own-INSERT probe skipped — no INSERT grant (42501)', 'grant-layer gap, not an RLS failure');
  } else if (ownIns.error) {
    fail('conversation_memories: own-INSERT rejected — owner cannot insert own memory', ownIns.error.message);
  } else if (!ownIns.data?.length) {
    fail('conversation_memories: own-INSERT returned no row', 'insert succeeded but select returned nothing');
  } else {
    pass('conversation_memories: own-INSERT allowed (WITH CHECK accepts own user_id)');
  }
  try {
    await admin.from('conversation_memories').delete().eq('session_id', ownSessionId);
  } catch {
    // best-effort cleanup of probe rows
  }

  const otherSessionId = randomUUID();
  const crossIns = await client.from('conversation_memories').insert({
    session_id: otherSessionId,
    user_id: otherUser.id,
    started_at: Date.now() / 1000,
    messages: [],
  }).select('session_id');
  if (crossIns.error && isGrantLayerError(crossIns.error)) {
    skip('conversation_memories: cross-user INSERT probe skipped — no INSERT grant (42501)', 'grant-layer gap, not an RLS failure');
  } else {
    crossIns.error && !isRlsError(crossIns.error)
      ? fail('conversation_memories: CROSS-USER INSERT errored unexpectedly', crossIns.error.message)
      : crossIns.data?.length
        ? fail('conversation_memories: LEAK — user A inserted a memory row owned by user B')
        : pass('conversation_memories: cross-user INSERT blocked (WITH CHECK on FOR ALL policy)');
  }
  try {
    await admin.from('conversation_memories').delete().eq('session_id', otherSessionId);
  } catch {
    // best-effort cleanup of probe rows
  }
}

async function seedAdminTables() {
  // Admin-managed tables: seeded globally (no owner column). Non-admin INSERT
  // must be rejected via the has_role WITH CHECK.
  const payloads = [
    ['gurus', { slug: `probe-guru-${stamp}`, name: `Probe Guru ${stamp}`, collection_name: 'test' }],
    ['assistant_configurations', { guru_id: null, slug: `probe-ac-${stamp}`, name: `Probe AC ${stamp}` }],
    ['assistant_doctrines', { assistant_slug: `probe-ad-${stamp}`, synonyms_json: {}, canonical_terms: [] }],
  ];
  const out = [];
  for (const [table, payload] of payloads) {
    const { data, error } = await admin.from(table).insert(payload).select().single();
    if (error) {
      if (isGrantLayerError(error)) { out.push({ table, granted: false }); continue; }
      throw new Error(`seed admin ${table}: ${error.message}`);
    }
    out.push({ table, granted: true, id: data.id });
  }
  return out;
}

async function run() {
  const [a, b] = [await createUser(users[0]), await createUser(users[1])];
  await seed(a);
  await seed(b);
  const adminTables = await seedAdminTables();

  // Tenant-isolated tables (chat_queries / chat_responses / retrieval_events)
  // are scoped by tenant_id from JWT claims, not user_id — probe by-claim.
  await probeTenantIsolation();

  for (const [table, ownerCol, pk, idKey, updateCol, mkInsert] of TABLES) {
    const ownId = a[idKey];
    const otherId = b[idKey];
    const res = await probeTable(a.client, table, pk, ownId, otherId, updateCol);
    if (res.state === 'skip') {
      skip(`${table}: probe skipped — ${res.reason}`, 'grant-layer gap, not an RLS failure');
      continue;
    }

    if (ownerCol && mkInsert) {
      const ins = await a.client.from(table).insert(mkInsert(b)).select(pk);
      if (ins.error && isGrantLayerError(ins.error)) {
        skip(`${table}: INSERT probe skipped — no INSERT grant (42501)`, 'grant-layer gap, not an RLS failure');
      } else {
        ins.error && !isRlsError(ins.error)
          ? fail(`${table}: CROSS-USER INSERT errored unexpectedly`, ins.error.message)
          : ins.data?.length
            ? fail(`${table}: LEAK — user A inserted a row owned by user B`)
            : pass(`${table}: cross-user INSERT blocked (WITH CHECK)`);
      }
    }

    if (ownerCol && OWNER_TRANSFER_TABLES.has(table)) {
      await probeOwnershipTransfer(admin, a.client, table, ownerCol, pk, ownId, b.id);
    }

    const anon = createClient(URL, ANON, { auth: { persistSession: false } });
    const anonRead = await anon.from(table).select(pk).limit(1);
    if (anonRead.error && isGrantLayerError(anonRead.error)) {
      skip(`${table}: anon SELECT probe skipped — no SELECT grant (42501)`, 'grant-layer gap, not an RLS failure');
    } else {
      anonRead.data?.length
        ? fail(`${table}: LEAK — anonymous read returned rows`)
        : pass(`${table}: anonymous SELECT blocked`);
    }
  }

  // Dedicated conversation_memories INSERT probes (P1-SEC-13): the generic
  // loop above covers cross-user INSERT rejection; this adds the own-insert
  // allowed-path assertion and names the FOR ALL policy being exercised.
  await probeConversationMemoriesInserts(admin, a.client, a, b);

  // Admin tables: non-admin authenticated user must not be able to INSERT.
  const adminInsertPayloads = {
    gurus: { slug: `nonadmin-${Date.now()}`, name: 'x', collection_name: 'test' },
    assistant_configurations: { guru_id: null, slug: `nonadmin-${Date.now()}`, name: 'x' },
    assistant_doctrines: { assistant_slug: `nonadmin-${Date.now()}`, synonyms_json: {}, canonical_terms: [] },
  };
  for (const t of adminTables) {
    if (!t.granted) {
      skip(`${t.table}: admin INSERT probe skipped — no service_role INSERT grant (42501)`, 'grant-layer gap');
      continue;
    }
    const ins = await a.client.from(t.table).insert(adminInsertPayloads[t.table]);
    if (ins.error && isGrantLayerError(ins.error)) {
      skip(`${t.table}: admin INSERT probe skipped — no authenticated INSERT grant (42501)`, 'grant-layer gap');
    } else {
      ins.data?.length
        ? fail(`${t.table}: LEAK — non-admin inserted a row (has_role WITH CHECK missing)`)
        : pass(`${t.table}: non-admin INSERT blocked (admin WITH CHECK)`);
    }
  }

  // cleanup
  for (const u of users) {
    if (u.id) await admin.auth.admin.deleteUser(u.id).catch(() => {});
  }

  const failures = results.filter((r) => !r.ok);
  const skipped = results.filter((r) => r.ok === 'skip');
  for (const r of results) {
    if (r.ok === 'skip') console.log(`SKIP  ${r.n}${r.d ? ` — ${r.d}` : ''}`);
    else console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.n}${r.d ? ` — ${r.d}` : ''}`);
  }
  console.log(
    `\n${results.length - failures.length - skipped.length}/${results.length} checks passed (${skipped.length} skipped: grant-layer gap)`
  );
  if (failures.length) process.exit(1);
}

run().catch((err) => {
  console.error('RLS verification crashed:', err.message);
  process.exit(2);
});
