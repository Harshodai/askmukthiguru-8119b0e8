// Telemetry edge function: stores client-side metrics keyed by user_message_id.
// verify_jwt = false (default). Accepts anonymous + authenticated. Best-effort writes.
import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

interface MetricBody {
  user_message_id?: string;
  last_message_id?: string | null;
  session_id?: string | null;
  metric_type?: string;
  metric_value?: number;
  tags?: Record<string, unknown>;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "method_not_allowed" }), {
      status: 405,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  let body: MetricBody;
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "invalid_json" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const { user_message_id, last_message_id, session_id, metric_type, metric_value, tags } = body;
  if (!user_message_id || typeof user_message_id !== "string") {
    return new Response(JSON.stringify({ error: "missing_user_message_id" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
  if (!metric_type || typeof metric_type !== "string") {
    return new Response(JSON.stringify({ error: "missing_metric_type" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
  const value = typeof metric_value === "number" && Number.isFinite(metric_value) ? metric_value : 0;

  // Resolve user (optional)
  let userId: string | null = null;
  const authHeader = req.headers.get("Authorization");
  if (authHeader?.startsWith("Bearer ")) {
    try {
      const userClient = createClient(
        Deno.env.get("SUPABASE_URL")!,
        Deno.env.get("SUPABASE_ANON_KEY")!,
        { global: { headers: { Authorization: authHeader } } },
      );
      const { data } = await userClient.auth.getUser();
      userId = data.user?.id ?? null;
    } catch {
      // ignore — anonymous telemetry still allowed
    }
  }

  const admin = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  const { error } = await admin.from("telemetry_events").insert({
    user_id: userId,
    session_id: session_id ?? null,
    user_message_id,
    last_message_id: last_message_id ?? null,
    metric_type,
    metric_value: value,
    tags: tags ?? {},
  });

  if (error) {
    console.error("telemetry insert failed", error);
    return new Response(JSON.stringify({ error: "insert_failed" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  return new Response(JSON.stringify({ ok: true }), {
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
});
