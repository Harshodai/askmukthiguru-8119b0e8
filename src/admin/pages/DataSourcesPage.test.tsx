import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import DataSourcesPage from "./DataSourcesPage";
import { useDataStores, useQdrantHealth } from "@/admin/hooks/useAdminData";
import { optimizeQdrant } from "@/admin/lib/api";

vi.mock("@/admin/hooks/useAdminData", () => ({
  useDataStores: vi.fn(),
  useQdrantHealth: vi.fn(),
}));

vi.mock("@/admin/lib/api", () => ({
  optimizeQdrant: vi.fn(),
}));

const mockDataStores = vi.mocked(useDataStores);
const mockQdrantHealth = vi.mocked(useQdrantHealth);
const mockOptimize = vi.mocked(optimizeQdrant);

describe("DataSourcesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders Qdrant vector health metrics and triggers optimize vector index", async () => {
    mockDataStores.mockReturnValue({
      data: {
        qdrant: {
          chat_corpus: { status: "green", points: 4197, indexed_vectors: 4197, vector_size: 1024 },
        },
        neo4j: { total_nodes: 50, total_relationships: 80, nodes_by_label: {}, relationships_by_type: {} },
        lightrag: { initialized: true, chunk_token_size: 512, cache_size: 10, embedding_dim: 1024 },
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as never);

    mockQdrantHealth.mockReturnValue({
      data: {
        status: "green",
        collection: "chat_corpus",
        points_count: 4197,
        segments_count: 3,
        fragmentation_pct: 0,
        optimizer_status: "ok",
        dimension: 1024,
      },
      isLoading: false,
      refetch: vi.fn(),
    } as never);

    mockOptimize.mockResolvedValue({
      actions: ["optimizer_triggered", "hnsw_updated"],
      before: { status: "green", collection: "chat_corpus" },
      after: { status: "green", collection: "chat_corpus" },
    });

    render(<DataSourcesPage />);

    expect(screen.getByText(/Qdrant Vector Index & Segments/i)).toBeInTheDocument();
    expect(screen.getByText("Optimize Vector Index")).toBeInTheDocument();
    expect(screen.getByText("Segment Count")).toBeInTheDocument();
    expect(screen.getByText("Fragmentation")).toBeInTheDocument();
    expect(screen.getByText("0%")).toBeInTheDocument();

    const optimizeBtn = screen.getByRole("button", { name: /Optimize Vector Index/i });
    fireEvent.click(optimizeBtn);

    await waitFor(() => {
      expect(mockOptimize).toHaveBeenCalledTimes(1);
    });
  });
});
