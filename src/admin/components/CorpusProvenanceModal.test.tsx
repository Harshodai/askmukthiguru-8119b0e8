import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CorpusProvenanceModal } from "./CorpusProvenanceModal";
import { useCorpusProvenance } from "@/admin/hooks/useAdminData";

vi.mock("@/admin/hooks/useAdminData", () => ({
  useCorpusProvenance: vi.fn(),
}));

const mockedHook = vi.mocked(useCorpusProvenance);

const PROVENANCE_MOCK = {
  point_id: "pt_test_123",
  source_url: "https://www.youtube.com/watch?v=mock_video",
  source_release_version: 2,
  content_checksum: "sha256:abc123mockhash456789",
  embedding_model: "text-embedding-3-large",
  embedding_dimension: 1024,
  chunker_version: "boundary_v1:512:64",
  gate_verdict: "pass",
  gate_reason: "clean_verbatim_transcript",
  asr_method: "whisper_timestamped_v3",
  align_method: "gentle_forced_aligner",
  rights_status: "licensed",
  parent_id: "parent_node_99",
  parent_id_scheme: "hierarchical_v2",
  created_at: "2026-10-25T12:00:00Z",
  ingested_at: "2026-10-25T12:05:00Z",
  audio_start_ms: 30000,
  audio_end_ms: 65000,
};

describe("CorpusProvenanceModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing or closed when pointId is null", () => {
    mockedHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as never);

    const { queryByText } = render(
      <CorpusProvenanceModal pointId={null} onClose={vi.fn()} />
    );
    expect(queryByText("Corpus Point Provenance")).toBeNull();
  });

  it("renders provenance details: chunker version, rights status, ASR coordinates, embedding model, and content checksum", () => {
    mockedHook.mockReturnValue({
      data: PROVENANCE_MOCK,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as never);

    render(<CorpusProvenanceModal pointId="pt_test_123" onClose={vi.fn()} />);

    expect(screen.getByText("Corpus Point Provenance")).toBeInTheDocument();
    expect(screen.getByText("pt_test_123")).toBeInTheDocument();
    expect(screen.getByText("licensed")).toBeInTheDocument();
    expect(screen.getByText("boundary_v1:512:64")).toBeInTheDocument();
    expect(screen.getByText("text-embedding-3-large")).toBeInTheDocument();
    expect(screen.getByText("1024 dimensions")).toBeInTheDocument();
    expect(screen.getByText("sha256:abc123mockhash456789")).toBeInTheDocument();
    expect(screen.getByText("00:30.000")).toBeInTheDocument();
    expect(screen.getByText("01:05.000")).toBeInTheDocument();
  });

  it("renders loading skeletons while fetching", () => {
    mockedHook.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    } as never);

    render(<CorpusProvenanceModal pointId="pt_loading" onClose={vi.fn()} />);
    expect(document.body.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it("renders error state with retry when request fails", () => {
    const refetch = vi.fn();
    mockedHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Vector store unavailable"),
      refetch,
    } as never);

    render(<CorpusProvenanceModal pointId="pt_err" onClose={vi.fn()} />);
    expect(screen.getByText("Failed to load point provenance")).toBeInTheDocument();
    expect(screen.getByText("Vector store unavailable")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});
