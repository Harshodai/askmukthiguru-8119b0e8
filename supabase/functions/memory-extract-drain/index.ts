/**
 * memory-extract-drain — background cron that processes pending_extractions.
 *
 * Runs every minute via cron job. Pulls up to 50 pending rows,
 * runs the same LLM extraction as memory-extract, embeds, dedupes,
 * inserts memories, and marks rows done/failed.
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";
import { embedText } from "../_shared/embed.ts";
import { getActiveMemoryConsentReceipt } from "../_shared/memoryConsent.ts";

const DEDUP_SIMILARITY = 0.92;
const BATCH_SIZE = 50;

const Lovable_API_KEY_ENV = "LOVABLE_API_KEY";
const MODEL = "google/gemini-2.5-flash";
const GATEWAY_CHAT = "https://ai.gateway.lovable.dev/v1/chat/completions";
const OLLAMA_CHAT_DEFAULT = "http://localhost:11434/v1/chat/completions";
const OLLAMA_CHAT_MODEL = "gemma3";

// Service-role workers bypass RLS, so every job independently verifies
// the latest receipt and the exact consent receipt bound to that queue row.
async function currentReceiptMatches(
  sb: ReturnType<typeof createClient>,
  userId: string,
  tenantId: string,
  expectedReceiptId: string | null | undefined,
): Promise<boolean> {
  if (!userId || !tenantId || !expectedReceiptId) return false;
  try {
    const receipt = await getActiveMemoryConsentReceipt(sb, userId, tenantId);
    return Boolean(receipt && receipt.id === expectedReceiptId);
  } catch {
    // Consent lookup failures are a denial, not permission to process.
    return false;
  }
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
    console.error("[memory-extract-drain] extraction failed", e instanceof Error ? e.name : "unknown_error");
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
      if (!(await currentReceiptMatches(sb, user_id, tenantId, row.consent_receipt_id))) {
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
        // Consent could have been revoked while the extraction model was
        // running. Do not retain even an empty-result job under a stale grant.
        if (!(await currentReceiptMatches(sb, user_id, tenantId, row.consent_receipt_id))) {
          const { error: deleteError } = await sb
            .from("pending_extractions")
            .delete()
            .eq("id", row.id);
          if (deleteError) {
            console.error("[memory-extract-drain] could not discard revoked job", deleteError.code ?? "db_error");
          }
          processed++;
          continue;
        }
        const { error: finishError } = await sb
          .from("pending_extractions")
          .update({ payload: {}, status: "done", processed_at: new Date().toISOString() })
          .eq("id", row.id);
        if (finishError) throw new Error("queue_terminal_update_failed");
        processed++;
        continue;
      }

      let revokedDuringProcessing = false;
      for (const fact of facts.slice(0, 3)) {
        const text = fact.toString().trim();
        if (!text || text.length < 10) continue;
        // Revalidate before sending the extracted fact to the embedding provider.
        if (!(await currentReceiptMatches(sb, user_id, tenantId, row.consent_receipt_id))) {
          const { error: deleteError } = await sb
            .from("pending_extractions")
            .delete()
            .eq("id", row.id);
          if (deleteError) {
            console.error("[memory-extract-drain] could not discard revoked job", deleteError.code ?? "db_error");
          }
          revokedDuringProcessing = true;
          break;
        }
        try {
          const { embedding } = await embedText(text);
          // The worker has no end-user JWT, so use the server-only RPC that
          // explicitly scopes de-duplication by both user and tenant. The
          // database schema uses vector(1024), matched by the shared embedder.
          const { data: dupes, error: dedupError } = await sb.rpc("match_user_memories_by_user", {
            p_user_id: user_id,
            p_tenant_id: tenantId,
            p_query_embedding: embedding as unknown as string,
            p_k: 1,
            p_min_sim: DEDUP_SIMILARITY,
          });
          if (dedupError) {
            // Avoid creating a known duplicate when scoped deduplication is
            // unavailable. Let the outer worker mark this job failed safely.
            throw new Error("memory_deduplication_failed");
          }
          if (Array.isArray(dupes) && dupes.length > 0) {
            console.log("[memory-extract-drain] skipping duplicate fact (length=%d)", text.length);
            continue;
          }
          // Re-check immediately before a service-role insert; consent may be
          // revoked while this job is waiting on the extraction or embedding model.
          if (!(await currentReceiptMatches(sb, user_id, tenantId, row.consent_receipt_id))) {
            const { error: deleteError } = await sb
              .from("pending_extractions")
              .delete()
              .eq("id", row.id);
            if (deleteError) {
              console.error("[memory-extract-drain] could not discard revoked job", deleteError.code ?? "db_error");
            }
            revokedDuringProcessing = true;
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

      if (revokedDuringProcessing) {
        processed++;
        continue;
      }
      const { error: finishError } = await sb
        .from("pending_extractions")
        .update({ payload: {}, status: "done", processed_at: new Date().toISOString() })
        .eq("id", row.id);
      if (finishError) throw new Error("queue_terminal_update_failed");
      processed++;
    } catch (e) {
      const errorStr = e instanceof Error ? e.name.slice(0, 80) : "unknown_error";
      const { error: failError } = await sb.from("pending_extractions").update({
        payload: {},
        status: "failed",
        attempts: row.attempts + 1,
        last_error: errorStr,
        processed_at: new Date().toISOString(),
      }).eq("id", row.id);
      if (failError) {
        console.error("[memory-extract-drain] could not terminally clear failed job", failError.code ?? "db_error");
      }
    }
  }

  return new Response(JSON.stringify({ processed }), { status: 200 });
});
