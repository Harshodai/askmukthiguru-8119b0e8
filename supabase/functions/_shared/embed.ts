/**
 * Shared embedding utility for all Mukthi Guru edge functions.
 *
 * Routing logic (both produce 1024-dimensional vectors):
 *
 *   LOVABLE_API_KEY set  →  Lovable AI Gateway → gemini-embedding-001 (MRL@1024)
 *   LOVABLE_API_KEY unset →  Local Ollama       → bge-m3                (1024d)
 *
 * Local Ollama setup (one-time):
 *   brew install ollama          # or: curl https://ollama.ai/install.sh | sh
 *   ollama pull bge-m3
 *   ollama serve                 # runs at http://localhost:11434
 *
 * Override Ollama URL via env:  OLLAMA_URL=http://host:11434
 *
 * Both paths use the OpenAI-compatible /v1/embeddings endpoint so the code
 * is identical — only the base URL, Authorization header, and model name differ.
 */

const GATEWAY_URL  = "https://ai.gateway.lovable.dev/v1/embeddings";
const GATEWAY_MODEL = "google/gemini-embedding-001";
const GATEWAY_DIMS  = 1024; // Must match public.guru_memories embedding vector(1024).

const OLLAMA_MODEL  = "bge-m3"; // 1024d, matches public.guru_memories.
const OLLAMA_DEFAULT = "http://localhost:11434";

export interface EmbedResult {
  embedding: number[];
  /** Which backend was used — useful for logging */
  backend: "lovable" | "ollama";
}

/**
 * Embed a single text string.
 * Throws on failure — callers decide whether to swallow or propagate.
 */
export async function embedText(text: string): Promise<EmbedResult> {
  const apiKey = Deno.env.get("LOVABLE_API_KEY");

  if (apiKey) {
    return embedViaGateway([text], apiKey).then((vecs) => ({
      embedding: vecs[0],
      backend: "lovable",
    }));
  }

  return embedViaOllama([text]).then((vecs) => ({
    embedding: vecs[0],
    backend: "ollama",
  }));
}

/**
 * Embed a batch of strings (up to 16 at a time for the gateway).
 * Returns an array of 1024-dim vectors in the same order as `texts`.
 */
export async function embedBatch(
  texts: string[],
  apiKey?: string,
): Promise<number[][]> {
  const key = apiKey ?? Deno.env.get("LOVABLE_API_KEY");
  if (key) return embedViaGateway(texts, key);
  return embedViaOllama(texts);
}

// ── Private ───────────────────────────────────────────────────────────────

async function embedViaGateway(
  texts: string[],
  apiKey: string,
): Promise<number[][]> {
  const r = await fetch(GATEWAY_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: GATEWAY_MODEL,
      input: texts,
      dimensions: GATEWAY_DIMS, // MRL: 768d from 3072d, via Matryoshka truncation
    }),
  });

  if (!r.ok) {
    const err = await r.text().catch(() => "");
    throw new Error(`[embed/gateway] ${r.status}: ${err.slice(0, 200)}`);
  }

  const j = await r.json();
  const vectors = (j.data as { embedding: number[] }[]).map((d) => d.embedding);
  if (vectors.some((vector) => !Array.isArray(vector) || vector.length !== GATEWAY_DIMS)) {
    throw new Error(`[embed/gateway] expected ${GATEWAY_DIMS}-dimensional vectors`);
  }
  return vectors;
}

async function embedViaOllama(texts: string[]): Promise<number[][]> {
  const base = (Deno.env.get("OLLAMA_URL") ?? OLLAMA_DEFAULT).replace(/\/$/, "");

  // Ollama's /v1/embeddings accepts a single string or an array.
  // We call it once per text to avoid quirks with batch ordering in some versions.
  const results: number[][] = [];
  for (const text of texts) {
    const r = await fetch(`${base}/v1/embeddings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: OLLAMA_MODEL, input: text }),
    });

    if (!r.ok) {
      const err = await r.text().catch(() => "");
      throw new Error(
        `[embed/ollama] ${r.status}: ${err.slice(0, 200)}\n` +
        `Hint: run "ollama pull nomic-embed-text && ollama serve" locally.`,
      );
    }

    const j = await r.json();
    // OpenAI-compat: { data: [{ embedding: [...] }] }
    const vec: number[] = j.data?.[0]?.embedding ?? j.embedding;
    if (!Array.isArray(vec) || vec.length !== GATEWAY_DIMS) {
      throw new Error(`[embed/ollama] expected ${GATEWAY_DIMS}-dimensional vector`);
    }
    results.push(vec);
  }
  return results;
}
