// Admin Telemetry Edge Function
// Returns paginated telemetry_events with filters for admin dashboard.
// Requires admin role (service role key used for queries).
import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

interface TelemetryFilters {
  user_id?: string;
  session_id?: string;
  metric_type?: string;
  user_message_id?: string;
  from?: string; // ISO timestamp
  to?: string;   // ISO timestamp
  limit?: number;
  offset?: number;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "method_not_allowed" }), {
      status: 405,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  // Auth: require admin (service role)
  const authHeader = req.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    return new Response(JSON.stringify({ error: "unauthorized" }), {
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
    return new Response(JSON.stringify({ error: "unauthorized" }), {
      status: 401,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  // Check admin role
  const adminClient = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
  const { data: roleData } = await adminClient
    .from("user_roles")
    .select("role")
    .eq("user_id", user.id)
    .eq("role", "admin")
    .maybeSingle();

  if (!roleData) {
    return new Response(JSON.stringify({ error: "forbidden", detail: "Admin access required" }), {
      status: 403,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  let filters: TelemetryFilters;
  try {
    filters = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "invalid_json" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const {
    user_id,
    session_id,
    metric_type,
    user_message_id,
    from,
    to,
    limit = 100,
    offset = 0,
  } = filters;

  // Build query
  let query = adminClient
    .from("telemetry_events")
    .select("id, user_id, session_id, user_message_id, last_message_id, metric_type, metric_value, tags, created_at", { count: "exact" })
    .order("created_at", { ascending: false })
    .range(offset, offset + limit - 1);

  if (user_id) query = query.eq("user_id", user_id);
  if (session_id) query = query.eq("session_id", session_id);
  if (metric_type) query = query.eq("metric_type", metric_type);
  if (user_message_id) query = query.eq("user_message_id", user_message_id);
  if (from) query = query.gte("created_at", from);
  if (to) query = query.lte("created_at", to);

  const { data, error, count } = await query;

  if (error) {
    console.error("admin-telemetry query failed", error);
    return new Response(JSON.stringify({ error: "query_failed" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  return new Response(JSON.stringify({
    data: data ?? [],
    count: count ?? 0,
    limit,
    offset,
  }), {
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
});