/**
 * Shared embedding utility for legacy guru_memories.
 *
 * This table is vector(1024) and its query RPCs use BAAI BGE-M3. Equal vector
 * dimensions do NOT make two models' vectors semantically comparable, so this
 * writer intentionally does not fall back to Gemini embeddings. Set OLLAMA_URL
 * to a reachable Ollama-compatible BGE-M3 endpoint in every deployed Edge
 * Function environment; keep that model aligned with backend MemoryService.
 *
 * Local setup:
 *   ollama pull bge-m3
 *   ollama serve
 *   export OLLAMA_URL=http://localhost:11434
 */

const OLLAMA_MODEL = "bge-m3";
const EXPECTED_DIMS = 1024;

export interface EmbedResult {
  embedding: number[];
  backend: "ollama";
}

export async function embedText(text: string): Promise<EmbedResult> {
  const vectors = await embedBatch([text]);
  return { embedding: vectors[0], backend: "ollama" };
}

export async function embedBatch(texts: string[], _apiKey?: string): Promise<number[][]> {
  if (!Array.isArray(texts) || texts.length === 0) return [];
  const configuredUrl = Deno.env.get("OLLAMA_URL")?.trim();
  if (!configuredUrl) {
    // Fail closed. Managed Edge runtimes cannot reach the developer's
    // localhost, and using Gemini vectors here would mix incompatible spaces
    // in the shared BGE-M3 database table.
    throw new Error("memory_embedding_endpoint_not_configured");
  }
  const base = configuredUrl.replace(/\/$/, "");
  const results: number[][] = [];
  for (const text of texts) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20_000);
    try {
      const r = await fetch(`${base}/v1/embeddings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: OLLAMA_MODEL, input: text }),
        signal: controller.signal,
      });
      if (!r.ok) {
        // Never surface provider response bodies; they may contain request data.
        throw new Error(`memory_embedding_provider_failed_${r.status}`);
      }
      const payload: unknown = await r.json();
      const obj = payload && typeof payload === "object"
        ? payload as { data?: Array<{ embedding?: unknown }>; embedding?: unknown; embeddings?: unknown }
        : {};
      const candidate = obj.data?.[0]?.embedding ?? obj.embedding ??
        (Array.isArray(obj.embeddings) && Array.isArray(obj.embeddings[0]) ? obj.embeddings[0] : undefined);
      if (
        !Array.isArray(candidate) ||
        candidate.length !== EXPECTED_DIMS ||
        candidate.some((n) => typeof n !== "number" || !Number.isFinite(n))
      ) {
        throw new Error("memory_embedding_vector_contract_mismatch");
      }
      results.push(candidate as number[]);
    } finally {
      clearTimeout(timeout);
    }
  }
  return results;
}
