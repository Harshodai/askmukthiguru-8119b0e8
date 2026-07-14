// Lightweight health probe. Returns 200 when DB + LOVABLE_API_KEY reachable.
// Used by README badge (shields.io endpoint) and external uptime monitors.
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.45.0';

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Cache-Control': 'no-store',
};

type Check = { name: string; ok: boolean; latency_ms: number; detail?: string };

const time = async <T,>(name: string, fn: () => Promise<T>): Promise<Check> => {
  const start = Date.now();
  try {
    await fn();
    return { name, ok: true, latency_ms: Date.now() - start };
  } catch (e) {
    // Log full error server-side only; return generic status to callers.
    console.error(`[healthz] ${name} check failed:`, (e as Error).message);
    return { name, ok: false, latency_ms: Date.now() - start, detail: 'unreachable' };
  }
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors });

  const url = Deno.env.get('SUPABASE_URL') ?? '';
  const key = Deno.env.get('SUPABASE_ANON_KEY') ?? '';
  const lovableKey = Deno.env.get('LOVABLE_API_KEY');

  const checks: Check[] = await Promise.all([
    time('database', async () => {
      const sb = createClient(url, key);
      const { error } = await sb.from('kb_sources').select('id', { head: true, count: 'exact' }).limit(1);
      if (error) throw new Error(error.message);
    }),
    time('ai_gateway', async () => {
      if (!lovableKey) throw new Error('missing key');
      // Cheap auth ping — head request to gateway base URL
      const r = await fetch('https://ai.gateway.lovable.dev/v1/models', {
        headers: { Authorization: `Bearer ${lovableKey}` },
      });
      if (!r.ok) throw new Error(`status ${r.status}`);
      await r.text();
    }),
  ]);

  const ok = checks.every((c) => c.ok);
  // Shields.io endpoint format support: ?format=shield
  const params = new URL(req.url).searchParams;
  if (params.get('format') === 'shield') {
    return new Response(
      JSON.stringify({
        schemaVersion: 1,
        label: 'status',
        message: ok ? 'healthy' : 'degraded',
        color: ok ? 'brightgreen' : 'red',
      }),
      { headers: { ...cors, 'Content-Type': 'application/json' }, status: 200 },
    );
  }

  return new Response(JSON.stringify({ ok, checks, timestamp: new Date().toISOString() }, null, 2), {
    status: ok ? 200 : 503,
    headers: { ...cors, 'Content-Type': 'application/json' },
  });
});
