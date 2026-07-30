#!/usr/bin/env node
/**
 * Automated RLS verification.
 *
 * Creates two throwaway users (A and B) via the Supabase Admin API, has each
 * insert a row into every user-scoped table, then asserts that:
 *   1. each user can read their OWN row
 *   2. neither user can read, update, or delete the OTHER user's row
 *   3. neither user can INSERT a row owned by the other (WITH CHECK enforced)
 *   4. anonymous (anon key, no session) can read nothing
 *
 * Usage:
 *   SUPABASE_URL=... SUPABASE_ANON_KEY=... SUPABASE_SERVICE_ROLE_KEY=... \
 *     node scripts/security/verify_rls.mjs
 *
 * Exits non-zero on the first cross-user leak. Safe to run in CI.
 */
import { createClient } from '@supabase/supabase-js';

const URL = process.env.SUPABASE_URL || process.env.VITE_SUPABASE_URL;
const ANON = process.env.SUPABASE_ANON_KEY || process.env.VITE_SUPABASE_PUBLISHABLE_KEY;
const SERVICE = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!URL || !ANON || !SERVICE) {
  console.error('Missing SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY');
  process.exit(2);
}

const admin = createClient(URL, SERVICE, { auth: { persistSession: false } });
const results = [];
const pass = (n, d = '') => results.push({ ok: true, n, d });
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

/** Seed one owned row per table with the service role (bypasses RLS). */
async function seed(u) {
  const conv = await admin
    .from('conversations')
    .insert({ user_id: u.id, title: `probe-${u.label}` })
    .select('id')
    .single();
  if (conv.error) throw new Error(`seed conversations: ${conv.error.message}`);
  u.conversationId = conv.data.id;

  const msg = await admin
    .from('chat_messages')
    .insert({ conversation_id: u.conversationId, role: 'user', content: `secret-${u.label}` })
    .select('id')
    .single();
  if (msg.error) throw new Error(`seed chat_messages: ${msg.error.message}`);
  u.messageId = msg.data.id;

  const med = await admin
    .from('meditation_sessions')
    .insert({ user_id: u.id, duration_seconds: 180, completed: true })
    .select('id')
    .single();
  if (med.error) throw new Error(`seed meditation_sessions: ${med.error.message}`);
  u.meditationId = med.data.id;

  const prof = await admin
    .from('user_profiles')
    .upsert({ user_id: u.id, preferred_language: 'en' }, { onConflict: 'user_id' })
    .select('user_id')
    .single();
  if (prof.error) throw new Error(`seed user_profiles: ${prof.error.message}`);
}

const TABLES = [
  { table: 'conversations', ownerCol: 'user_id', pk: 'id', idKey: 'conversationId' },
  { table: 'chat_messages', ownerCol: null, pk: 'id', idKey: 'messageId' },
  { table: 'meditation_sessions', ownerCol: 'user_id', pk: 'id', idKey: 'meditationId' },
  { table: 'user_profiles', ownerCol: 'user_id', pk: 'user_id', idKey: 'id' },
];

async function run() {
  const [a, b] = [await createUser(users[0]), await createUser(users[1])];
  await seed(a);
  await seed(b);

  for (const t of TABLES) {
    const ownId = a[t.idKey];
    const otherId = b[t.idKey];

    // 1. own row readable
    const own = await a.client.from(t.table).select(t.pk).eq(t.pk, ownId);
    own.data?.length
      ? pass(`${t.table}: owner can read own row`)
      : fail(`${t.table}: owner CANNOT read own row`, own.error?.message ?? 'empty result');

    // 2. other user's row NOT readable
    const cross = await a.client.from(t.table).select(t.pk).eq(t.pk, otherId);
    cross.data?.length
      ? fail(`${t.table}: LEAK — user A read user B's row`, JSON.stringify(cross.data))
      : pass(`${t.table}: cross-user SELECT blocked`);

    // 3. other user's row NOT updatable
    const upd = await a.client.from(t.table).update({ updated_at: new Date().toISOString() }).eq(t.pk, otherId).select(t.pk);
    upd.data?.length
      ? fail(`${t.table}: LEAK — user A updated user B's row`)
      : pass(`${t.table}: cross-user UPDATE blocked`);

    // 4. other user's row NOT deletable
    const del = await a.client.from(t.table).delete().eq(t.pk, otherId).select(t.pk);
    del.data?.length
      ? fail(`${t.table}: LEAK — user A deleted user B's row`)
      : pass(`${t.table}: cross-user DELETE blocked`);

    // 5. cannot INSERT a row owned by the other user (WITH CHECK)
    if (t.ownerCol) {
      const ins = await a.client.from(t.table).insert({ [t.ownerCol]: b.id }).select(t.pk);
      ins.data?.length
        ? fail(`${t.table}: LEAK — user A inserted a row owned by user B`)
        : pass(`${t.table}: cross-user INSERT blocked (WITH CHECK)`);
    }

    // 6. anonymous reads nothing
    const anon = createClient(URL, ANON, { auth: { persistSession: false } });
    const anonRead = await anon.from(t.table).select(t.pk).limit(1);
    anonRead.data?.length
      ? fail(`${t.table}: LEAK — anonymous read returned rows`)
      : pass(`${t.table}: anonymous SELECT blocked`);
  }

  // cleanup
  for (const u of users) {
    if (u.id) await admin.auth.admin.deleteUser(u.id).catch(() => {});
  }

  const failures = results.filter((r) => !r.ok);
  for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.n}${r.d ? ` — ${r.d}` : ''}`);
  console.log(`\n${results.length - failures.length}/${results.length} checks passed`);
  if (failures.length) process.exit(1);
}

run().catch((err) => {
  console.error('RLS verification crashed:', err.message);
  process.exit(2);
});
