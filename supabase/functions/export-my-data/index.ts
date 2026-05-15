// Export-my-data — returns all rows the caller owns as a JSON download.
// GDPR/DPDP data subject access right.
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.45.0';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
};

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

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_ANON_KEY') ?? '',
      { global: { headers: { Authorization: authHeader } } },
    );

    const { data: userRes, error: userErr } = await supabase.auth.getUser();
    if (userErr || !userRes.user) {
      return new Response(JSON.stringify({ error: 'Invalid session' }), {
        status: 401,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    const userId = userRes.user.id;

    const [profile, conversations, messages, sessions, roles] = await Promise.all([
      supabase.from('profiles').select('*').eq('id', userId).maybeSingle(),
      supabase.from('conversations').select('*').eq('user_id', userId),
      supabase.from('chat_messages').select('*, conversations!inner(user_id)').eq('conversations.user_id', userId),
      supabase.from('meditation_sessions').select('*').eq('user_id', userId),
      supabase.from('user_roles').select('role').eq('user_id', userId),
    ]);

    const payload = {
      exported_at: new Date().toISOString(),
      user: { id: userId, email: userRes.user.email },
      profile: profile.data,
      roles: roles.data ?? [],
      conversations: conversations.data ?? [],
      chat_messages: messages.data ?? [],
      meditation_sessions: sessions.data ?? [],
    };

    return new Response(JSON.stringify(payload, null, 2), {
      headers: {
        ...corsHeaders,
        'Content-Type': 'application/json',
        'Content-Disposition': `attachment; filename="askmukthiguru-export-${userId}.json"`,
      },
    });
  } catch (e) {
    console.error('[export-my-data]', e);
    return new Response(JSON.stringify({ error: e instanceof Error ? e.message : 'unknown' }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
