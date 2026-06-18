// Telemetry edge function: stores client-side metrics keyed by user_message_id.
// verify_jwt = true. Requires authenticated user. Validates ownership of IDs.
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
  user_id?: string; // Optional: if provided, must match authenticated user
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

  const { user_message_id, last_message_id, session_id, metric_type, metric_value, tags, user_id } = body;
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

  // Require authentication - verify JWT
  const authHeader = req.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    return new Response(JSON.stringify({ error: "unauthorized", detail: "Authentication required" }), {
      status: 401,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const userClient = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_ANON_KEY")!,
    { global: { headers: { Authorization: authHeader } } },
  );
  const { data: { user }, error: userErr } = await userClient.auth.getUser();
  if (userErr || !user) {
    return new Response(JSON.stringify({ error: "unauthorized", detail: "Invalid or expired token" }), {
      status: 401,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
  const authenticatedUserId = user.id;

  // If user_id provided in body, validate it matches authenticated user
  if (user_id && user_id !== authenticatedUserId) {
    return new Response(JSON.stringify({ error: "forbidden", detail: "user_id mismatch" }), {
      status: 403,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  // If session_id provided, validate it belongs to the authenticated user
  let validatedSessionId: string | null = session_id ?? null;
  if (session_id) {
    const admin = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );
    const { data: sessionData, error: sessionErr } = await admin
      .from("chat_sessions")
      .select("id")
      .eq("id", session_id)
      .eq("user_id", authenticatedUserId)
      .maybeSingle();
    if (sessionErr || !sessionData) {
      return new Response(JSON.stringify({ error: "forbidden", detail: "session_id does not belong to user" }), {
        status: 403,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
    validatedSessionId = sessionData.id;
  }

  const admin = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  const { error } = await admin.from("telemetry_events").insert({
    user_id: authenticatedUserId,
    session_id: validatedSessionId,
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