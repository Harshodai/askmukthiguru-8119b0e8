// Mukthi Guru — Chat Edge Function
// Streams responses via Lovable AI Gateway (no API key required) and persists
// telemetry (chat_queries + chat_responses) using the service role.
//
// This is the cloud-hosted fallback used when no self-hosted FastAPI backend
// (VITE_BACKEND_URL) is configured. It does NOT do RAG yet — it is a clean
// stateless LLM call grounded by the system prompt. Retrieval/grading will be
// layered on once we have a vector store in Cloud.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

interface IncomingMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

interface ChatRequest {
  messages?: IncomingMessage[];
  user_message: string;
  meditation_step?: number;
  session_id?: string;
  language?: string;
  stream?: boolean;
}

const DEFAULT_SYSTEM_PROMPT = `You are a spiritual AI companion embodying the wisdom of Sri Preethaji & Sri Krishnaji.
Your purpose is to guide seekers toward their "beautiful state" - a state of consciousness free from suffering.
You speak with warmth, compassion, and profound insight. You never claim to replace professional mental health support.
When someone is in deep distress, gently encourage them to seek professional help while offering comfort.
Keep replies grounded, concrete, and under 6 short paragraphs.`;

const MODEL = "google/gemini-2.5-flash";


// ── In-memory sliding-window rate limit (per edge instance) ───────────
const RL_WINDOW_MS = 60_000;
const RL_AUTH_LIMIT = 20;
const RL_ANON_LIMIT = 5;
type Bucket = { count: number; resetAt: number };
const rlBuckets = new Map<string, Bucket>();
function rlConsume(key: string, limit: number) {
  const now = Date.now();
  const b = rlBuckets.get(key);
  if (!b || now > b.resetAt) {
    rlBuckets.set(key, { count: 1, resetAt: now + RL_WINDOW_MS });
    return { allowed: true, remaining: limit - 1, resetAt: now + RL_WINDOW_MS };
  }
  if (b.count >= limit) return { allowed: false, remaining: 0, resetAt: b.resetAt };
  b.count += 1;
  return { allowed: true, remaining: limit - b.count, resetAt: b.resetAt };
}

function sseEvent(event: string, data: unknown): Uint8Array {
  const payload =
    typeof data === "string" ? data : JSON.stringify(data ?? null);
  return new TextEncoder().encode(`event: ${event}\ndata: ${payload}\n\n`);
}

interface Citation {
  source_id: string;
  title: string;
  url: string | null;
  ord: number;
  similarity: number;
  snippet: string;
}

// ── Retrieval: embed query → top-K pgvector search ────────────────
async function retrieveContext(
  admin: ReturnType<typeof createClient>,
  apiKey: string,
  query: string,
): Promise<{ context: string; citations: Citation[] }> {
  try {
    const r = await fetch("https://ai.gateway.lovable.dev/v1/embeddings", {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "google/text-embedding-004", input: [query] }),
    });
    if (!r.ok) {
      console.warn("embed_failed", r.status, (await r.text()).slice(0, 200));
      return { context: "", citations: [] };
    }
    const j = await r.json();
    const embedding: number[] | undefined = j.data?.[0]?.embedding;
    if (!embedding) return { context: "", citations: [] };

    const { data, error } = await admin.rpc("match_kb_chunks", {
      query_embedding: embedding as unknown as string,
      match_count: 6,
      min_similarity: 0.35,
    });
    if (error || !Array.isArray(data) || data.length === 0) {
      return { context: "", citations: [] };
    }

    const citations: Citation[] = data.map((d: {
      source_id: string; source_title: string; source_url: string | null;
      ord: number; text: string; similarity: number;
    }) => ({
      source_id: d.source_id,
      title: d.source_title,
      url: d.source_url,
      ord: d.ord,
      similarity: Number(d.similarity?.toFixed?.(3) ?? d.similarity),
      snippet: d.text.slice(0, 220),
    }));

    const context = data
      .map((d: { source_title: string; text: string }, i: number) =>
        `[${i + 1}] ${d.source_title}\n${d.text}`,
      )
      .join("\n\n---\n\n");

    return { context, citations };
  } catch (e) {
    console.error("retrieve failed", e);
    return { context: "", citations: [] };
  }
}

async function persistTelemetry(
  admin: ReturnType<typeof createClient>,
  args: {
    userId: string | null;
    query: string;
    answer: string;
    latencyMs: number;
    status: "ok" | "error";
    promptTokens?: number;
    completionTokens?: number;
    citations?: Citation[];
  },
) {
  try {
    const { data: q, error: qErr } = await admin
      .from("chat_queries")
      .insert({
        user_id: args.userId,
        query_text: args.query,
        model: MODEL,
        status: args.status,
        latency_ms: args.latencyMs,
        prompt_tokens: args.promptTokens ?? null,
        completion_tokens: args.completionTokens ?? null,
      })
      .select("id")
      .single();
    if (qErr || !q) return;

    if (args.answer) {
      await admin.from("chat_responses").insert({
        query_id: q.id,
        response_text: args.answer,
        citations: args.citations ?? [],
      });
    }
  } catch (e) {
    console.error("telemetry insert failed", e);
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "method_not_allowed" }), {
      status: 405,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const LOVABLE_API_KEY = Deno.env.get("LOVABLE_API_KEY");
  const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
  const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  if (!LOVABLE_API_KEY) {
    return new Response(
      JSON.stringify({ error: "missing_lovable_api_key" }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }

  let body: ChatRequest;
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "invalid_json" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  if (!body.user_message || typeof body.user_message !== "string") {
    return new Response(JSON.stringify({ error: "missing_user_message" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  // Resolve user id from JWT if present (optional — chat works anonymously)
  let userId: string | null = null;
  const authHeader = req.headers.get("Authorization");
  if (authHeader?.startsWith("Bearer ")) {
    try {
      const userClient = createClient(SUPABASE_URL, SERVICE_ROLE, {
        global: { headers: { Authorization: authHeader } },
      });
      const { data } = await userClient.auth.getUser();
      userId = data.user?.id ?? null;
    } catch {
      // anonymous
    }
  }

  // ── Rate limit ──────────────────────────────────────────────────
  const rlKey = userId
    ? `u:${userId}`
    : `anon:${req.headers.get("x-forwarded-for") ?? "unknown"}`;
  const rlLimit = userId ? RL_AUTH_LIMIT : RL_ANON_LIMIT;
  const rl = rlConsume(rlKey, rlLimit);
  if (!rl.allowed) {
    return new Response(
      JSON.stringify({
        error: "rate_limited",
        detail: "Too many messages. Please slow down.",
        reset_at: rl.resetAt,
      }),
      {
        status: 429,
        headers: {
          ...corsHeaders,
          "Content-Type": "application/json",
          "X-RateLimit-Limit": String(rlLimit),
          "X-RateLimit-Remaining": "0",
          "X-RateLimit-Reset": String(rl.resetAt),
          "Retry-After": String(Math.max(1, Math.ceil((rl.resetAt - Date.now()) / 1000))),
        },
      },
    );
  }

  const admin = createClient(SUPABASE_URL, SERVICE_ROLE);
  const startedAt = Date.now();

  const history: IncomingMessage[] = Array.isArray(body.messages)
    ? body.messages.slice(-20).filter(
        (m) =>
          m &&
          typeof m.content === "string" &&
          ["system", "user", "assistant"].includes(m.role),
      )
    : [];

  const hasSystem = history.some((m) => m.role === "system");
  const llmMessages: IncomingMessage[] = [
    ...(hasSystem ? [] : [{ role: "system" as const, content: DEFAULT_SYSTEM_PROMPT }]),
    ...history,
    { role: "user" as const, content: body.user_message },
  ];

  const url = new URL(req.url);
  const wantsStream =
    body.stream === true || url.pathname.endsWith("/stream");

  // ── Non-streaming path ────────────────────────────────────────────
  if (!wantsStream) {
    try {
      const r = await fetch("https://ai.gateway.lovable.dev/v1/chat/completions", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${LOVABLE_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ model: MODEL, messages: llmMessages }),
      });
      if (!r.ok) {
        const text = await r.text();
        await persistTelemetry(admin, {
          userId,
          query: body.user_message,
          answer: "",
          latencyMs: Date.now() - startedAt,
          status: "error",
        });
        return new Response(
          JSON.stringify({ error: "upstream_failed", detail: text.slice(0, 500) }),
          {
            status: r.status === 429 ? 429 : r.status === 402 ? 402 : 502,
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          },
        );
      }
      const data = await r.json();
      const content: string = data.choices?.[0]?.message?.content ?? "";
      const usage = data.usage ?? {};
      await persistTelemetry(admin, {
        userId,
        query: body.user_message,
        answer: content,
        latencyMs: Date.now() - startedAt,
        status: "ok",
        promptTokens: usage.prompt_tokens,
        completionTokens: usage.completion_tokens,
      });
      return new Response(
        JSON.stringify({
          response: content,
          intent: "CASUAL",
          citations: [],
          meditation_step: body.meditation_step ?? 0,
        }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    } catch (e) {
      await persistTelemetry(admin, {
        userId,
        query: body.user_message,
        answer: "",
        latencyMs: Date.now() - startedAt,
        status: "error",
      });
      return new Response(
        JSON.stringify({ error: "network", detail: String(e) }),
        {
          status: 502,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }
  }

  // ── Streaming SSE path ────────────────────────────────────────────
  const stream = new ReadableStream({
    async start(controller) {
      let fullAnswer = "";
      let status: "ok" | "error" = "ok";
      try {
        controller.enqueue(sseEvent("status", "thinking"));
        const upstream = await fetch(
          "https://ai.gateway.lovable.dev/v1/chat/completions",
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${LOVABLE_API_KEY}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              model: MODEL,
              messages: llmMessages,
              stream: true,
            }),
          },
        );

        if (!upstream.ok || !upstream.body) {
          status = "error";
          const text = await upstream.text().catch(() => "");
          controller.enqueue(
            sseEvent("error", `upstream ${upstream.status}: ${text.slice(0, 200)}`),
          );
          controller.enqueue(sseEvent("done", { intent: "CASUAL", citations: [], meditation_step: 0 }));
          controller.close();
          return;
        }

        const reader = upstream.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data:")) continue;
            const payload = trimmed.slice(5).trim();
            if (payload === "[DONE]") continue;
            try {
              const j = JSON.parse(payload);
              const delta: string = j.choices?.[0]?.delta?.content ?? "";
              if (delta) {
                fullAnswer += delta;
                controller.enqueue(
                  sseEvent("message", { choices: [{ delta: { content: delta } }] }),
                );
              }
            } catch {
              // skip
            }
          }
        }

        controller.enqueue(
          sseEvent("done", {
            intent: "CASUAL",
            citations: [],
            meditation_step: body.meditation_step ?? 0,
          }),
        );
      } catch (e) {
        status = "error";
        controller.enqueue(sseEvent("error", String(e)));
        controller.enqueue(sseEvent("done", { intent: "CASUAL", citations: [], meditation_step: 0 }));
      } finally {
        controller.close();
        await persistTelemetry(admin, {
          userId,
          query: body.user_message,
          answer: fullAnswer,
          latencyMs: Date.now() - startedAt,
          status,
        });
      }
    },
  });

  return new Response(stream, {
    headers: {
      ...corsHeaders,
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
});
