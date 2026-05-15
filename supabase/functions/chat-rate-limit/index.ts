// Sliding-window rate limit advisor for the chat endpoint.
// Returns { allowed, remaining, reset_at }. Authenticated: 20/min, anon: 5/min.
// In-memory store — adequate for per-edge-instance throttling; users hitting
// multiple cold starts get effectively the per-instance budget.
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.45.0';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
};

const WINDOW_MS = 60_000;
const AUTH_LIMIT = 20;
const ANON_LIMIT = 5;

type Bucket = { count: number; resetAt: number };
const buckets = new Map<string, Bucket>();

const consume = (key: string, limit: number) => {
  const now = Date.now();
  const b = buckets.get(key);
  if (!b || now > b.resetAt) {
    const fresh = { count: 1, resetAt: now + WINDOW_MS };
    buckets.set(key, fresh);
    return { allowed: true, remaining: limit - 1, reset_at: fresh.resetAt };
  }
  if (b.count >= limit) {
    return { allowed: false, remaining: 0, reset_at: b.resetAt };
  }
  b.count += 1;
  return { allowed: true, remaining: limit - b.count, reset_at: b.resetAt };
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const authHeader = req.headers.get('Authorization');
    let key: string;
    let limit: number;

    if (authHeader) {
      const supabase = createClient(
        Deno.env.get('SUPABASE_URL') ?? '',
        Deno.env.get('SUPABASE_ANON_KEY') ?? '',
        { global: { headers: { Authorization: authHeader } } },
      );
      const { data: userRes } = await supabase.auth.getUser();
      key = userRes.user?.id ?? `anon:${req.headers.get('x-forwarded-for') ?? 'unknown'}`;
      limit = userRes.user ? AUTH_LIMIT : ANON_LIMIT;
    } else {
      key = `anon:${req.headers.get('x-forwarded-for') ?? 'unknown'}`;
      limit = ANON_LIMIT;
    }

    const result = consume(key, limit);
    return new Response(JSON.stringify({ ...result, limit }), {
      status: result.allowed ? 200 : 429,
      headers: {
        ...corsHeaders,
        'Content-Type': 'application/json',
        'X-RateLimit-Limit': String(limit),
        'X-RateLimit-Remaining': String(result.remaining),
        'X-RateLimit-Reset': String(result.reset_at),
      },
    });
  } catch (e) {
    console.error('[chat-rate-limit]', e);
    return new Response(JSON.stringify({ error: 'rate-limit-error', allowed: true }), {
      status: 200,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
