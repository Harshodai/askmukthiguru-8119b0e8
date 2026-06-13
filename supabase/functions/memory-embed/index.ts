/**
 * memory-embed — JWT-guarded embedding endpoint.
 *
 * Auto-routes (via _shared/embed.ts):
 *   LOVABLE_API_KEY set  →  Lovable AI Gateway → gemini-embedding-001 @768d MRL
 *   LOVABLE_API_KEY unset →  local Ollama       → nomic-embed-text     @768d
 *
 * Request:  POST { text: string }
 * Response: { embedding: number[], backend: "lovable"|"ollama" }
 *
 * Never exposes LOVABLE_API_KEY to the client.
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";
import { embedText } from "../_shared/embed.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);

  const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
  const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

  // ── Auth: require a valid Supabase JWT ────────────────────────────
  const authHeader = req.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) return json({ error: "unauthorized" }, 401);

  try {
    const userClient = createClient(SUPABASE_URL, SERVICE_ROLE, {
      global: { headers: { Authorization: authHeader } },
    });
    const { data: { user }, error } = await userClient.auth.getUser();
    if (error || !user) return json({ error: "unauthorized" }, 401);
  } catch {
    return json({ error: "unauthorized" }, 401);
  }

  // ── Parse body ────────────────────────────────────────────────────
  let body: { text?: string };
  try {
    body = await req.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }

  const text = (body.text ?? "").toString().trim();
  if (!text) return json({ error: "text_required" }, 400);
  if (text.length > 8000) return json({ error: "text_too_long" }, 400);

  // ── Embed ─────────────────────────────────────────────────────────
  try {
    const result = await embedText(text);
    return json({ embedding: result.embedding, backend: result.backend });
  } catch (e) {
    console.error("[memory-embed] embed failed", e);
    return json({ error: "embed_failed", detail: (e as Error).message }, 502);
  }
});
