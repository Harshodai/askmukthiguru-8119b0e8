// Ingestion stub — records an ingestion_runs row for a source URL/text.
// Real RAG ingestion (chunk/embed/upsert) is offline. This is for admin telemetry visibility.
import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const authHeader = req.headers.get("Authorization");
    if (!authHeader?.startsWith("Bearer ")) return json({ error: "Unauthorized" }, 401);

    const userClient = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_ANON_KEY")!,
      { global: { headers: { Authorization: authHeader } } },
    );
    const token = authHeader.replace("Bearer ", "");
    const { data: claims } = await userClient.auth.getClaims(token);
    if (!claims?.claims?.sub) return json({ error: "Unauthorized" }, 401);
    const { data: isAdmin } = await userClient.rpc("has_role", {
      _user_id: claims.claims.sub,
      _role: "admin",
    });
    if (!isAdmin) return json({ error: "Forbidden" }, 403);

    const body = await req.json().catch(() => ({}));
    const source = (body.source ?? "").toString().trim();
    if (!source) return json({ error: "source required" }, 400);

    const admin = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );

    const started = Date.now();
    const { data: run, error } = await admin
      .from("ingestion_runs")
      .insert({
        source,
        status: "queued",
        chunks_added: 0,
        duration_ms: Date.now() - started,
        details: { queued_by: claims.claims.sub, note: "Queued for offline pipeline" },
      })
      .select()
      .single();

    if (error) return json({ error: error.message }, 500);
    return json({ ok: true, run });
  } catch (e) {
    return json({ error: e instanceof Error ? e.message : "unknown" }, 500);
  }
});

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}
