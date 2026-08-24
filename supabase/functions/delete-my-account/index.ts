import { createClient, type SupabaseClient } from 'https://esm.sh/@supabase/supabase-js@2.45.0';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

type DeleteTable =
  | 'user_course_progress'
  | 'user_brain_edges'
  | 'user_brain_nodes'
  | 'user_brain_keys'
  | 'push_subscriptions'
  | 'push_devices'
  | 'chat_sessions'
  | 'chat_queries'
  | 'user_retention_cards'
  | 'user_streaks'
  | 'retention_events'
  | 'study_notebooks'
  | 'user_episodes'
  | 'user_personas'
  | 'user_scene_blocks'
  | 'user_skills'
  | 'memory_consent_receipts'
  | 'memory_outbox'
  | 'memory_deletion_receipts'
  | 'exit_surveys'
  | 'save_offers'
  | 'cancellations'
  | 'user_profiles'
  | 'conversation_memories';

async function deleteUserRows(
  admin: SupabaseClient,
  table: DeleteTable,
  userId: string,
): Promise<void> {
  const { error } = await admin.from(table).delete().eq('user_id', userId);
  if (error) throw new Error(`failed to delete ${table}: ${error.message}`);
}

// The Postgres table list below is not the whole story: the FastAPI backend
// separately owns Qdrant vectors, Neo4j graph nodes, Redis ephemeral memory,
// and three guru_* Postgres tables (guru_core_memory, guru_memories,
// guru_session_summaries) that this function has no reach into. Purge those
// first, while the caller's bearer token is still valid — deleteUser() below
// invalidates it. (OH-P0-02, 2026-08-24)
//
// Requires the BACKEND_URL secret to be set on this function
// (`supabase secrets set BACKEND_URL=...`). If it is unset, this step is
// skipped with a warning rather than blocking account deletion outright —
// Postgres deletion still proceeds as it did before this change.
async function purgeBackendMemory(authHeader: string): Promise<string | null> {
  const backendUrl = Deno.env.get('BACKEND_URL');
  if (!backendUrl) {
    console.warn('[delete-my-account] BACKEND_URL not configured — skipping Qdrant/Neo4j/Redis purge');
    return 'BACKEND_URL not configured; Qdrant/Neo4j/Redis memory was not purged';
  }
  const res = await fetch(`${backendUrl.replace(/\/$/, '')}/api/account/purge-memory`, {
    method: 'DELETE',
    headers: { Authorization: authHeader },
  });
  if (!res.ok) {
    throw new Error(`backend memory purge failed: ${res.status} ${await res.text()}`);
  }
  return null;
}

async function deleteConversations(
  admin: SupabaseClient,
  userId: string,
): Promise<void> {
  const { data: conversations, error: conversationLookupError } = await admin
    .from('conversations')
    .select('id')
    .eq('user_id', userId);
  if (conversationLookupError) {
    throw new Error(`failed to list conversations: ${conversationLookupError.message}`);
  }

  const conversationIds = (conversations ?? []).map((conversation) => conversation.id);
  if (conversationIds.length > 0) {
    const { error: messageError } = await admin
      .from('chat_messages')
      .delete()
      .in('conversation_id', conversationIds);
    if (messageError) throw new Error(`failed to delete chat_messages: ${messageError.message}`);
  }

  const { error: conversationError } = await admin
    .from('conversations')
    .delete()
    .eq('user_id', userId);
  if (conversationError) throw new Error(`failed to delete conversations: ${conversationError.message}`);
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const authHeader = req.headers.get('Authorization');
    if (!authHeader) {
      return new Response(JSON.stringify({ error: 'Missing Authorization header' }), {
        status: 401,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const userClient = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_ANON_KEY') ?? '',
      { global: { headers: { Authorization: authHeader } } },
    );

    const { data: userRes, error: userErr } = await userClient.auth.getUser();
    if (userErr || !userRes.user) {
      return new Response(JSON.stringify({ error: 'Invalid session' }), {
        status: 401,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    const userId = userRes.user.id;

    const admin = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
      { auth: { persistSession: false } },
    );

    // Delete child/telemetry rows before Auth deletion. Every operation is checked;
    // a partial purge must never be reported as a successful account deletion.
    const memoryWarning = await purgeBackendMemory(authHeader);
    await deleteConversations(admin, userId);
    for (const table of [
      'user_course_progress',
      'user_brain_edges',
      'user_brain_nodes',
      'user_brain_keys',
      'push_subscriptions',
      'push_devices',
      'chat_sessions',
      'chat_queries',
      'user_retention_cards',
      'user_streaks',
      'retention_events',
      'study_notebooks',
      'user_episodes',
      'user_personas',
      'user_scene_blocks',
      'user_skills',
      'memory_consent_receipts',
      'memory_outbox',
      'memory_deletion_receipts',
      'exit_surveys',
      'save_offers',
      'cancellations',
      'user_profiles',
      'conversation_memories',
    ] as DeleteTable[]) {
      await deleteUserRows(admin, table, userId);
    }

    const { error: meditationError } = await admin
      .from('meditation_sessions')
      .delete()
      .eq('user_id', userId);
    if (meditationError) throw new Error(`failed to delete meditation_sessions: ${meditationError.message}`);

    const { error: rolesError } = await admin.from('user_roles').delete().eq('user_id', userId);
    if (rolesError) throw new Error(`failed to delete user_roles: ${rolesError.message}`);

    const { error: profileError } = await admin.from('profiles').delete().eq('id', userId);
    if (profileError) throw new Error(`failed to delete profiles: ${profileError.message}`);

    const { error: delErr } = await admin.auth.admin.deleteUser(userId);
    if (delErr) throw delErr;

    return new Response(
      JSON.stringify(memoryWarning ? { ok: true, warning: memoryWarning } : { ok: true }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } },
    );
  } catch (e) {
    console.error('[delete-my-account]', e);
    return new Response(
      JSON.stringify({ error: 'Account deletion did not complete. Please contact support.' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } },
    );
  }
});
