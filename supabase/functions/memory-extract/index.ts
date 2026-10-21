/**
 * memory-extract — fire-and-forget fact extraction from a chat turn.
 *
 * Called from ChatInterface.tsx after each assistant response completes.
 * Silently extracts 0–3 durable facts about the seeker, embeds them,
 * deduplicates against existing memories, and inserts new ones.
 *
 * Auto-routes embedding (via _shared/embed.ts):
 *   LOVABLE_API_KEY set  →  Lovable AI Gateway → gemini-embedding-001 @1024d MRL
 *   LOVABLE_API_KEY unset →  local Ollama       → bge-m3               @1024d
 *
 * Request:  POST { user_message: string, assistant_message: string, conversation_id?: string }
 * Response: { inserted: number }   (always 200 — failures are silent on the client)
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";
import { embedText } from "../_shared/embed.ts";
import { getActiveMemoryConsentReceipt } from "../_shared/memoryConsent.ts";
import { parseExtractedFacts } from "../_shared/memoryFacts.ts";
import { resolveAllowOrigin } from "../_shared/cors.ts";

const LOVABLE_API_KEY_ENV = "LOVABLE_API_KEY";
const MODEL = "google/gemini-2.5-flash";
const GATEWAY_CHAT = "https://ai.gateway.lovable.dev/v1/chat/completions";
// Fallback for local dev: Ollama running the same model via its OpenAI-compat endpoint
const OLLAMA_CHAT_DEFAULT = "http://localhost:11434/v1/chat/completions";
const OLLAMA_CHAT_MODEL = "gemma3"; // lightweight local chat model; user can override via OLLAMA_CHAT_MODEL

const DEDUP_SIMILARITY = 0.92; // skip insert if existing memory is ≥92% similar

Deno.serve(async (req) => {
  const corsHeaders = {
    "Access-Control-Allow-Origin": resolveAllowOrigin(req),
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
  };
  const json = (payload: unknown, status = 200) =>
    new Response(JSON.stringify(payload), {
      status,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });

  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);

  const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
  const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const LOVABLE_API_KEY = Deno.env.get(LOVABLE_API_KEY_ENV);

  // ── Auth ──────────────────────────────────────────────────────────
  const authHeader = req.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) return json({ error: "unauthorized" }, 401);

  let userId: string;
  let tenantId = "oneness";
  let userClient;
  try {
    userClient = createClient(SUPABASE_URL, SERVICE_ROLE, {
      global: { headers: { Authorization: authHeader } },
    });
    const { data: { user }, error } = await userClient.auth.getUser();
    if (error || !user) return json({ error: "unauthorized" }, 401);
    userId = user.id;
    const claimedTenant = user.app_metadata?.tenant_id;
    if (typeof claimedTenant === "string" && claimedTenant.trim()) {
      tenantId = claimedTenant.trim();
    }
  } catch {
    return json({ error: "unauthorized" }, 401);
  }

  // This legacy service-role edge function bypasses RLS. Require the same
  // explicit server-side receipt as the backend APIs before sending conversation
  // text to an extraction model or storing an extracted fact.
  const admin = createClient(SUPABASE_URL, SERVICE_ROLE);
  let consentReceipt;
  try {
    consentReceipt = await getActiveMemoryConsentReceipt(admin, userId, tenantId);
  } catch {
    return json({ error: "consent_unavailable" }, 503);
  }
  if (!consentReceipt) return json({ error: "memory_consent_required" }, 403);

  // ── Parse body ────────────────────────────────────────────────────
  let body: { user_message?: string; assistant_message?: string; conversation_id?: string };
  try {
    body = await req.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }

  const userMsg = (body.user_message ?? "").toString().trim().slice(0, 2000);
  const assistantMsg = (body.assistant_message ?? "").toString().trim().slice(0, 4000);

  if (!userMsg || !assistantMsg) return json({ inserted: 0 });

  // ── Step 1: Extract facts via LLM ────────────────────────────────
  const extractionPrompt = `You are a memory curator for a spiritual AI companion.
Read this conversation exchange and extract 0 to 3 stable, first-person facts about the seeker.
A "fact" is something durable: a life situation, a named spiritual practice, a long-standing struggle,
a stated goal, or a clear preference. Skip ephemeral feelings or single-session context.
Return ONLY valid JSON: {"facts": ["fact 1", "fact 2"]}. Return {"facts": []} if nothing durable.

User: ${userMsg}
Assistant: ${assistantMsg}`;

  let facts: string[] = [];
  try {
    if (LOVABLE_API_KEY) {
      // Cloud path: Lovable AI Gateway
      const r = await fetch(GATEWAY_CHAT, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${LOVABLE_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: MODEL,
          messages: [{ role: "user", content: extractionPrompt }],
          response_format: { type: "json_object" },
          temperature: 0.1,
          max_tokens: 256,
        }),
      });
      if (r.ok) {
        const j = await r.json();
        const raw = j.choices?.[0]?.message?.content ?? "{}";
        facts = parseExtractedFacts(raw);
      } else {
        console.warn("[memory-extract] LLM extraction failed (gateway)", r.status);
      }
    } else {
      // Local path: Ollama with a lightweight chat model
      const ollamaBase = (Deno.env.get("OLLAMA_URL") ?? OLLAMA_CHAT_DEFAULT.replace("/v1/chat/completions", "")).replace(/\/$/, "");
      const ollamaModel = Deno.env.get("OLLAMA_CHAT_MODEL") ?? OLLAMA_CHAT_MODEL;
      const r = await fetch(`${ollamaBase}/v1/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: ollamaModel,
          messages: [{ role: "user", content: extractionPrompt }],
          format: "json",
          options: { temperature: 0.1 },
        }),
      });
      if (r.ok) {
        const j = await r.json();
        const raw = j.choices?.[0]?.message?.content ?? "{}";
        facts = parseExtractedFacts(raw);
      } else {
        console.warn("[memory-extract] LLM extraction failed (ollama)", r.status);
      }
    }
  } catch (e) {
    console.error("[memory-extract] extraction failed", e instanceof Error ? e.name : "unknown_error");
    return json({ inserted: 0 }); // silent failure — memory is best-effort
  }

  if (!Array.isArray(facts) || facts.length === 0) return json({ inserted: 0 });

  // ── Step 2: Embed + dedup + insert ───────────────────────────────
  let inserted = 0;

  for (const fact of facts.slice(0, 3)) {
    const text = fact.toString().trim();
    if (!text || text.length < 10) continue;

    try {
      // Never send a fact to another provider after its original grant was
      // withdrawn while extraction was running.
      let beforeEmbedding;
      try {
        beforeEmbedding = await getActiveMemoryConsentReceipt(admin, userId, tenantId);
      } catch {
        break;
      }
      if (!beforeEmbedding || beforeEmbedding.id !== consentReceipt.id) break;

      // Embed (auto-routes to gateway or Ollama)
      const { embedding } = await embedText(text);
      let beforeDedup;
      try {
        beforeDedup = await getActiveMemoryConsentReceipt(admin, userId, tenantId);
      } catch {
        break;
      }
      if (!beforeDedup || beforeDedup.id !== consentReceipt.id) break;

      // Service-side deduplication must be scoped by both the globally
      // unique user ID and the active tenant. The legacy auth.uid() RPC is not
      // tenant-scoped and cannot safely be used for an administrative worker.
      const { data: dupes, error: dedupError } = await admin.rpc("match_user_memories_by_user", {
        p_user_id: userId,
        p_tenant_id: tenantId,
        p_query_embedding: embedding as unknown as string,
        p_k: 1,
        p_min_sim: DEDUP_SIMILARITY,
      });
      if (dedupError) {
        console.error("[memory-extract] tenant-scoped deduplication unavailable", dedupError.code ?? "db_error");
        break;
      }

      const isDupe = Array.isArray(dupes) && dupes.length > 0;
      if (isDupe) {
        console.log("[memory-extract] skipping duplicate fact (length=%d)", text.length);
        continue;
      }

      // Revalidate immediately before the service-role write because RLS does
      // not constrain service-role clients and a user may revoke consent mid-job.
      let currentReceipt;
      try {
        currentReceipt = await getActiveMemoryConsentReceipt(admin, userId, tenantId);
      } catch {
        console.log("[memory-extract] stopped because consent verification is unavailable");
        break;
      }
      // Do not process a job under a different later grant: revocation ends the
      // authority captured when extraction was requested, even after re-consent.
      if (!currentReceipt || currentReceipt.id !== consentReceipt.id) {
        console.log("[memory-extract] stopped because the original consent receipt is no longer active");
        break;
      }

      const { error } = await admin.from("guru_memories").insert({
        user_id: userId,
        tenant_id: tenantId,
        content: text,
        embedding: embedding as unknown as string,
        source: "extracted",
      });

      if (error) {
        console.error("[memory-extract] insert failed", error.code ?? "db_error");
      } else {
        inserted++;
      }
    } catch (e) {
      console.error("[memory-extract] embed/insert failed", e instanceof Error ? e.name : "unknown_error");
    }
  }

  console.log(`[memory-extract] user=${userId} inserted=${inserted}/${facts.length}`);
  return json({ inserted });
});
