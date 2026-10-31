import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { TraceDrawer } from "./TraceDrawer";
import { useQueryTrace } from "@/admin/hooks/useAdminData";
import { upsertGoldenQuestion } from "@/admin/lib/api";

vi.mock("@/admin/hooks/useAdminData", () => ({
  useQueryTrace: vi.fn(),
  useCorpusProvenance: vi.fn(() => ({ data: null, isLoading: false })),
}));

vi.mock("@/admin/lib/api", () => ({
  upsertGoldenQuestion: vi.fn(),
}));

const mockQueryTrace = vi.mocked(useQueryTrace);
const mockUpsertGolden = vi.mocked(upsertGoldenQuestion);

const TRACE_MOCK = {
  query: {
    id: "query-abc",
    session_id: "sess-1",
    anon_user_id: "u-1",
    query_text: "What is silence?",
    prompt_version_id: "p1",
    model: "gemini-flash",
    prompt_tokens: 10,
    completion_tokens: 20,
    cost_estimate: 0.001,
    latency_ms: 250,
    status: "success",
    created_at: "2026-10-25T10:00:00Z",
  },
  prompt: { id: "p1", name: "v1", version: "1" },
  retrieval: {
    id: "r1",
    query_id: "query-abc",
    chunk_ids: ["pt-chunk-42"],
    source_docs: ["doc_silence_intro"],
    scores: [0.92],
    top_k: 1,
    retrieval_hit: true,
  },
  response: {
    id: "res-1",
    query_id: "query-abc",
    response_text: "Silence is your true nature.",
    citations: [],
    faithfulness: 0.98,
    answer_relevancy: 0.95,
    context_precision: 0.92,
    context_recall: 0.9,
    confidence: 0.95,
  },
  spans: [],
  triggers: [],
  feedback: null,
  safety: [],
};

describe("TraceDrawer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("wires Promote to golden button to upsertGoldenQuestion", async () => {
    mockQueryTrace.mockReturnValue({
      data: TRACE_MOCK,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as never);

    mockUpsertGolden.mockResolvedValue({ ok: true, id: "gq-1" });

    render(<TraceDrawer queryId="query-abc" onClose={vi.fn()} />);

    expect(screen.getByText("What is silence?")).toBeInTheDocument();
    const promoteBtn = screen.getByRole("button", { name: "Promote to golden" });
    expect(promoteBtn).toBeInTheDocument();

    fireEvent.click(promoteBtn);

    await waitFor(() => {
      expect(mockUpsertGolden).toHaveBeenCalledWith(
        expect.objectContaining({
          question: "What is silence?",
          expected_answer: "Silence is your true nature.",
          expected_sources: ["doc_silence_intro"],
          active: true,
        })
      );
    });
  });

  it("renders retrieved chunks with click-to-inspect provenance affordance", () => {
    mockQueryTrace.mockReturnValue({
      data: TRACE_MOCK,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as never);

    render(<TraceDrawer queryId="query-abc" onClose={vi.fn()} />);

    expect(screen.getByText("Click chunk to inspect provenance")).toBeInTheDocument();
    const chunkItem = screen.getByTitle("Click to inspect provenance for pt-chunk-42");
    expect(chunkItem).toBeInTheDocument();
  });
});
