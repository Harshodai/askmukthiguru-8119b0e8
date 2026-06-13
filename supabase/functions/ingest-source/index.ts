// Ingestion — chunks + embeds text via shared embed utility (auto-routes:
//   LOVABLE_API_KEY set  →  Lovable AI Gateway, gemini-embedding-001 @768d MRL
//   LOVABLE_API_KEY unset →  local Ollama, nomic-embed-text @768d)
// Upserts into kb_sources / kb_chunks, records an ingestion_runs telemetry row.
// Admin-only. Accepts { title, url?, kind?, text? } or { source } (treated as text or URL).
import { createClient } from "npm:@supabase/supabase-js@2";
import { embedBatch } from "../_shared/embed.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const CHUNK_SIZE = 900;
const CHUNK_OVERLAP = 120;
const BATCH = 16;

function chunkText(s: string): string[] {
  const clean = s.replace(/\s+/g, " ").trim();
  if (!clean) return [];
  const out: string[] = [];
  let i = 0;
  while (i < clean.length) {
    const end = Math.min(i + CHUNK_SIZE, clean.length);
    out.push(clean.slice(i, end));
    if (end === clean.length) break;
    i = end - CHUNK_OVERLAP;
  }
  return out;
}



function validateExternalUrl(raw: string): URL {
  const u = new URL(raw);
  if (!["http:", "https:"].includes(u.protocol)) throw new Error("invalid_url_protocol");
  const host = u.hostname.toLowerCase();
  const blocked =
    host === "localhost" || host === "0.0.0.0" || host === "::1" ||
    host.endsWith(".localhost") ||
    /^127\./.test(host) || /^10\./.test(host) || /^192\.168\./.test(host) ||
    /^169\.254\./.test(host) || /^172\.(1[6-9]|2[0-9]|3[01])\./.test(host) ||
    /^f[cd][0-9a-f]{2}:/i.test(host) || /^fe80:/i.test(host);
  if (blocked) throw new Error("private_url_blocked");
  return u;
}

async function fetchUrlText(url: string): Promise<string> {
  const safe = validateExternalUrl(url);
  const r = await fetch(safe.toString(), { headers: { "User-Agent": "MukthiGuruIngest/1.0" }, redirect: "follow" });
  if (!r.ok) throw new Error(`fetch_failed_${r.status}`);
  const ct = r.headers.get("content-type") ?? "";
  const body = await r.text();
  if (!ct.includes("html")) return body;
  return body
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&");
}


Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  const started = Date.now();
  try {
    const authHeader = req.headers.get("Authorization");
    if (!authHeader?.startsWith("Bearer ")) return json({ error: "Unauthorized" }, 401);

    const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
    const ANON = Deno.env.get("SUPABASE_ANON_KEY")!;
    const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const LOVABLE_API_KEY = Deno.env.get("LOVABLE_API_KEY");
    // LOVABLE_API_KEY is optional: shared embed utility falls back to Ollama when absent.

    const userClient = createClient(SUPABASE_URL, ANON, {
      global: { headers: { Authorization: authHeader } },
    });
    const token = authHeader.replace("Bearer ", "");
    const { data: claims } = await userClient.auth.getClaims(token);
    const userId = claims?.claims?.sub;
    if (!userId) return json({ error: "Unauthorized" }, 401);
    const { data: isAdmin } = await userClient.rpc("has_role", {
      _user_id: userId,
      _role: "admin",
    });
    if (!isAdmin) return json({ error: "Forbidden" }, 403);

    const body = await req.json().catch(() => ({}));
    let title: string = (body.title ?? "").toString().trim();
    let url: string | null = body.url ? String(body.url).trim() : null;
    const kind: string = (body.kind ?? (url ? "url" : "text")).toString();
    let text: string = (body.text ?? "").toString();

    // Back-compat: { source } can be either URL or raw text
    if (!text && !url && body.source) {
      const s = String(body.source).trim();
      if (/^https?:\/\//i.test(s)) url = s;
      else text = s;
    }

    if (!text && url) text = await fetchUrlText(url);
    if (!title) title = url ?? `Source ${new Date().toISOString().slice(0, 10)}`;
    if (!text || text.length < 40) return json({ error: "text_too_short" }, 400);

    const admin = createClient(SUPABASE_URL, SERVICE);

    // Create source row
    const { data: src, error: srcErr } = await admin
      .from("kb_sources")
      .insert({
        title,
        url,
        kind,
        status: "ingesting",
        created_by: userId,
        metadata: { length: text.length },
      })
      .select()
      .single();
    if (srcErr || !src) { console.error("[ingest-source] source insert", srcErr); return json({ error: "Failed to create source." }, 500); }

    const chunks = chunkText(text);
    let inserted = 0;
    try {
      for (let i = 0; i < chunks.length; i += BATCH) {
        const slice = chunks.slice(i, i + BATCH);
        const vectors = await embedBatch(slice);
        const rows = slice.map((t, j) => ({
          source_id: src.id,
          ord: i + j,
          text: t,
          token_count: Math.ceil(t.length / 4),
          embedding: vectors[j] as unknown as string,
        }));
        const { error: cErr } = await admin.from("kb_chunks").insert(rows);
        if (cErr) { console.error("[ingest-source] chunk insert", cErr); throw new Error("chunk_insert_failed"); }
        inserted += slice.length;
      }
      await admin.from("kb_sources").update({ status: "ready", chunk_count: inserted }).eq("id", src.id);
    } catch (e) {
      console.error("[ingest-source] embed/insert exception", e);
      await admin.from("kb_sources").update({ status: "error", chunk_count: inserted }).eq("id", src.id);
      await admin.from("ingestion_runs").insert({
        source: title,
        status: "failed",
        chunks_added: inserted,
        duration_ms: Date.now() - started,
        error_log: e instanceof Error ? e.message : "unknown",
        details: { source_id: src.id, kind, by: userId },
      });
      return json({ error: "Ingestion failed. Please try again.", source_id: src.id, chunks_added: inserted }, 500);
    }

    await admin.from("ingestion_runs").insert({
      source: title,
      status: "completed",
      chunks_added: inserted,
      duration_ms: Date.now() - started,
      details: { source_id: src.id, kind, by: userId },
    });

    return json({ ok: true, source_id: src.id, chunks_added: inserted });
  } catch (e) {
    console.error("[ingest-source] exception", e);
    return json({ error: "An error occurred. Please try again." }, 500);
  }
});

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}
