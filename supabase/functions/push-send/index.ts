/**
 * push-send — admin/cron-callable function that broadcasts a daily teaching
 * (or arbitrary payload) to all subscribed users via Web Push (VAPID).
 *
 * Body: { title?: string, body?: string, url?: string, user_id?: string }
 *   - user_id: send to a single user only (optional).
 *
 * Requires secrets: VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT
 */
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.45.4';
import webpush from 'https://esm.sh/web-push@3.6.7';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  // Authorization: require either a shared CRON secret (for scheduled invocation)
  // or an authenticated admin user (via Supabase JWT + has_role check).
  const cronSecret = Deno.env.get('CRON_SECRET');
  const providedSecret = req.headers.get('x-cron-secret');
  let authorized = false;
  if (cronSecret && providedSecret && providedSecret === cronSecret) {
    authorized = true;
  } else {
    const authHeader = req.headers.get('Authorization') ?? '';
    if (authHeader.startsWith('Bearer ')) {
      try {
        const jwt = authHeader.replace('Bearer ', '');
        const sbAuth = createClient(
          Deno.env.get('SUPABASE_URL')!,
          Deno.env.get('SUPABASE_ANON_KEY')!,
        );
        const { data: userData } = await sbAuth.auth.getUser(jwt);
        if (userData?.user?.id) {
          const sbAdmin = createClient(
            Deno.env.get('SUPABASE_URL')!,
            Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
          );
          const { data: isAdmin } = await sbAdmin.rpc('has_role', {
            _user_id: userData.user.id,
            _role: 'admin',
          });
          if (isAdmin === true) authorized = true;
        }
      } catch (_e) {
        // fall through to 401
      }
    }
  }
  if (!authorized) {
    return new Response(JSON.stringify({ error: 'unauthorized' }), {
      status: 401,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  const VAPID_PUBLIC = Deno.env.get('VAPID_PUBLIC_KEY');
  const VAPID_PRIVATE = Deno.env.get('VAPID_PRIVATE_KEY');
  const VAPID_SUBJECT = Deno.env.get('VAPID_SUBJECT') ?? 'mailto:hello@askmukthiguru.app';

  if (!VAPID_PUBLIC || !VAPID_PRIVATE) {
    return new Response(JSON.stringify({ error: 'vapid_not_configured' }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  webpush.setVapidDetails(VAPID_SUBJECT, VAPID_PUBLIC, VAPID_PRIVATE);

  let body: { title?: string; body?: string; url?: string; user_id?: string } = {};
  try {
    body = await req.json();
  } catch {
    // empty body is fine
  }

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
  );

  let query = supabase.from('push_subscriptions').select('id, endpoint, p256dh, auth, user_id');
  if (body.user_id) query = query.eq('user_id', body.user_id);
  const { data: subs, error } = await query;
  if (error) {
    return new Response(JSON.stringify({ error: 'db_error' }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  const payload = JSON.stringify({
    title: body.title ?? 'A teaching for you',
    body: body.body ?? 'Open AskMukthiGuru for today’s message.',
    url: body.url ?? '/chat',
  });

  let sent = 0;
  let failed = 0;
  const stale: string[] = [];

  await Promise.all(
    (subs ?? []).map(async (s) => {
      try {
        await webpush.sendNotification(
          { endpoint: s.endpoint, keys: { p256dh: s.p256dh, auth: s.auth } },
          payload,
        );
        sent += 1;
      } catch (e: unknown) {
        failed += 1;
        const status = (e as { statusCode?: number }).statusCode;
        if (status === 404 || status === 410) stale.push(s.id);
      }
    }),
  );

  if (stale.length) await supabase.from('push_subscriptions').delete().in('id', stale);

  return new Response(JSON.stringify({ sent, failed, cleaned: stale.length }), {
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
});
