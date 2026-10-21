/**
 * memory-extract-drain — background cron that processes pending_extractions.
 *
 * Runs every minute via cron job. Pulls up to 50 pending rows,
 * runs the same LLM extraction as memory-extract, embeds, dedupes,
 * inserts memories, and marks rows done/failed.
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";
import { embedText } from "../_shared/embed.ts";

const DEDUP_SIMILARITY = 0.92;
const BATCH_SIZE = 50;

const Lovable_API_KEY_ENV = "LOVABLE_API_KEY";
const MODEL = "google/gemini-2.5-flash";
const GATEWAY_CHAT = "https://ai.gateway.lovable.dev/v1/chat/completions";
const OLLAMA_CHAT_DEFAULT = "http://localhost:11434/v1/chat/completions";
const OLLAMA_CHAT_MODEL = "gemma3";

// Service-role workers bypass RLS, so every job must independently verify the
// authoritative, tenant-scoped consent receipt before extracting or persisting.
async function hasActiveMemoryConsent(
  sb: ReturnType<typeof createClient>,
  userId: string,
  tenantId: string,
): Promise<boolean> {
  if (!userId || !tenantId) return false;
  const { data, error } = await sb
    .from("memory_consent_receipts")
    .select("id")
    .eq("user_id", userId)
    .eq("tenant_id", tenantId)
    .eq("consent_version", "memory-v1")
    .eq("granted", true)
    .is("revoked_at", null)
    .limit(1);
  return !error && Boolean(data?.length);
}

async function extractFacts(userMessage: string, assistantMessage: string): Promise<string[]> {
  const LOVABLE_API_KEY = Deno.env.get(Lovable_API_KEY_ENV);
  const extractionPrompt = `You are a memory curator for a spiritual AI companion.
Read this conversation exchange and extract 0 to 3 stable, first-person facts about the seeker.
A "fact" is something durable: a life situation, a named spiritual practice, a long-standing struggle,
a stated goal, or a clear preference. Skip ephemeral feelings or single-session context.
Return ONLY valid JSON: {"facts": ["fact 1", "fact 2"]}. Return {"facts": []} if nothing durable.

User: ${userMessage}
Assistant: ${assistantMessage}`;

  let facts: string[] = [];
  try {
    if (LOVABLE_API_KEY) {
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
        facts = JSON.parse(raw).facts ?? [];
      }
    } else {
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
        facts = JSON.parse(raw).facts ?? [];
      }
    }
  } catch (e) {
    console.error("[memory-extract-drain] extraction error", e);
  }
  return facts;
}

Deno.serve(async (req) => {
  const cronSecret = Deno.env.get("CRON_SECRET");
  const provided = req.headers.get("x-cron-secret");
  if (!cronSecret || provided !== cronSecret) {
    return new Response(JSON.stringify({ error: "unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
  const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const sb = createClient(SUPABASE_URL, SERVICE_ROLE);

  // Pull pending rows
  const { data: rows } = await sb
    .from("pending_extractions")
    .select("*")
    .eq("status", "pending")
    .order("created_at", { ascending: true })
    .limit(BATCH_SIZE);

  if (!rows || rows.length === 0) {
    return new Response(JSON.stringify({ processed: 0 }), { status: 200 });
  }

  let processed = 0;
  for (const row of rows) {
    const { user_id, payload } = row;
    const tenantId = typeof row.tenant_id === "string" ? row.tenant_id : "oneness";
    const userMsg = payload?.user_message ?? "";
    const assistantMsg = payload?.assistant_message ?? "";

    try {
      // Delete—not merely mark done—jobs whose consent is absent or unverifiable
      // so a revoked user message is not retained indefinitely in the queue.
      if (!(await hasActiveMemoryConsent(sb, user_id, tenantId))) {
        const { error: deleteError } = await sb
          .from("pending_extractions")
          .delete()
          .eq("id", row.id);
        if (deleteError) {
          console.error("[memory-extract-drain] could not discard unconsented job", deleteError.code ?? "db_error");
        }
        processed++;
        continue;
      }

      const facts = await extractFacts(userMsg, assistantMsg);
      if (facts.length === 0) {
        await sb.from("pending_extractions").update({ status: "done", processed_at: new Date().toISOString() }).eq("id", row.id);
        processed++;
        continue;
      }

      for (const fact of facts.slice(0, 3)) {
        const text = fact.toString().trim();
        if (!text || text.length < 10) continue;
        try {
          const { embedding } = await embedText(text);
          // Dedup via RPC
          const { data: dupes } = await sb.rpc("match_user_memories", {
            p_query_embedding: embedding as unknown as string,
            p_k: 1,
            p_min_sim: DEDUP_SIMILARITY,
          });
          if (Array.isArray(dupes) && dupes.length > 0) {
            console.log("[memory-extract-drain] skipping duplicate fact (length=%d)", text.length);
            continue;
          }
          // Re-check immediately before a service-role insert; consent may be
          // revoked while this job is waiting on the extraction or embedding model.
          if (!(await hasActiveMemoryConsent(sb, user_id, tenantId))) {
            const { error: deleteError } = await sb
              .from("pending_extractions")
              .delete()
              .eq("id", row.id);
            if (deleteError) {
              console.error("[memory-extract-drain] could not discard revoked job", deleteError.code ?? "db_error");
            }
            break;
          }
          const { error } = await sb.from("guru_memories").insert({
            user_id,
            tenant_id: tenantId,
            content: text,
            embedding: embedding as unknown as string,
            source: "extracted",
          });
          if (error) console.error("[memory-extract-drain] insert error", error.code ?? "db_error");
        } catch (e) {
          console.error("[memory-extract-drain] embed/insert failed", e instanceof Error ? e.name : "unknown_error");
        }
      }

      await sb.from("pending_extractions").update({ status: "done", processed_at: new Date().toISOString() }).eq("id", row.id);
      processed++;
    } catch (e) {
      const errorStr = (e as Error).message?.slice(0, 200) ?? "";
      await sb.from("pending_extractions").update({
        status: "failed",
        attempts: row.attempts + 1,
        last_error: errorStr,
        processed_at: new Date().toISOString(),
      }).eq("id", row.id);
    }
  }

  return new Response(JSON.stringify({ processed }), { status: 200 });
});
