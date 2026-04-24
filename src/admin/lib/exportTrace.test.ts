import { describe, it, expect, beforeEach, vi } from "vitest";
import type { QueryTrace } from "../types";

// Stub out DOM bits used by exportTrace
beforeEach(() => {
  vi.stubGlobal("URL", {
    createObjectURL: vi.fn(() => "blob:mock"),
    revokeObjectURL: vi.fn(),
  });
  document.body.innerHTML = "";
});

const sampleTrace: QueryTrace = {
  query: {
    id: "q_001",
    session_id: "s_001",
    anon_user_id: "u_001",
    query_text: "test query",
    prompt_version_id: "pv_001",
    model: "google/gemini-2.5-flash",
    prompt_tokens: 100,
    completion_tokens: 50,
    cost_estimate: 0.0001,
    latency_ms: 1234,
    status: "ok",
    created_at: "2026-04-24T12:00:00.000Z",
  },
  prompt: {
    id: "pv_001",
    name: "main_chat",
    version: 1,
    content: "system",
    active: true,
    created_at: "2026-04-01T00:00:00.000Z",
  },
  retrieval: {
    id: "ret_001",
    query_id: "q_001",
    chunk_ids: ["c1", "c2"],
    source_docs: ["doc1.pdf", "doc2.pdf"],
    scores: [0.9, 0.8],
    top_k: 2,
    retrieval_hit: true,
  },
  response: {
    id: "resp_001",
    query_id: "q_001",
    response_text: "answer",
    citations: [{ source: "doc1.pdf", snippet: "..." }],
    faithfulness: 0.9,
    answer_relevancy: 0.85,
    context_precision: 0.8,
    context_recall: 0.75,
    hallucination_flag: false,
    judge_reasoning: "ok",
    confidence: 0.9,
    created_at: "2026-04-24T12:00:01.000Z",
  },
  spans: [
    {
      id: "sp_001",
      query_id: "q_001",
      parent_span_id: null,
      name: "llm",
      start_ms: 0,
      duration_ms: 1000,
      attributes: {},
    },
  ],
  triggers: [
    {
      id: "trg_001",
      query_id: "q_001",
      trigger_name: "serene_mind",
      metadata: {},
      created_at: "2026-04-24T12:00:01.000Z",
    },
  ],
  feedback: null,
  safety: [],
};

describe("exportTrace", () => {
  it("JSON export contains the full trace", async () => {
    const { exportTraceJSON } = await import("./exportTrace");
    const { content, filename } = exportTraceJSON(sampleTrace);
    expect(filename).toMatch(/^trace_q_001_\d+\.json$/);
    const parsed = JSON.parse(content);
    expect(parsed.query.id).toBe("q_001");
    expect(parsed.spans).toHaveLength(1);
    expect(parsed.triggers[0].trigger_name).toBe("serene_mind");
  });

  it("CSV export contains all sections", async () => {
    const { exportTraceCSV } = await import("./exportTrace");
    const { content } = exportTraceCSV(sampleTrace);
    expect(content).toContain("# QUERY");
    expect(content).toContain("# PROMPT");
    expect(content).toContain("# SPANS");
    expect(content).toContain("# RETRIEVAL");
    expect(content).toContain("# RESPONSE_AND_JUDGE");
    expect(content).toContain("# TRIGGERS");
    expect(content).toContain("q_001");
    expect(content).toContain("serene_mind");
  });
});
