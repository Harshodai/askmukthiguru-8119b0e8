import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import QualityPage from "./QualityPage";
import { useQuality, useSafetyEvents, useAnnotations } from "@/admin/hooks/useAdminData";

vi.mock("@/admin/hooks/useAdminData", () => ({
  useQuality: vi.fn(),
  useSafetyEvents: vi.fn(),
  useAnnotations: vi.fn(),
  useAdminFilters: vi.fn(() => ({ filters: {} })),
  useRangeKey: vi.fn(() => ["7d"]),
}));

vi.mock("@/admin/components/RagasHeatmap", () => ({
  RagasHeatmap: () => <div data-testid="ragas-heatmap">Heatmap</div>,
}));

const mockQuality = vi.mocked(useQuality);
const mockSafety = vi.mocked(useSafetyEvents);
const mockAnnos = vi.mocked(useAnnotations);

describe("QualityPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSafety.mockReturnValue({ data: [], isLoading: false } as never);
    mockAnnos.mockReturnValue({ data: [], isLoading: false } as never);
  });

  it("renders the Abstentions & Guardrails card breaking down the failure taxonomy", () => {
    mockQuality.mockReturnValue({
      data: {
        faithfulness: 0.94,
        relevancy: 0.91,
        safety_score: 0.99,
        manual_review_score: 0.88,
        disagreements: [],
        low_confidence: [],
        abstentions: {
          crisis_redirect: 14,
          serving_contract_violation: 3,
          unverified_speaker: 19,
          empty_retrieval: 8,
          total: 44,
        },
      },
      isLoading: false,
    } as never);

    render(<QualityPage />);

    expect(screen.getByText("Abstentions & Guardrails")).toBeInTheDocument();
    expect(screen.getByText("Crisis Redirect")).toBeInTheDocument();
    expect(screen.getByText("Contract Violation")).toBeInTheDocument();
    expect(screen.getByText("Unverified Speaker")).toBeInTheDocument();
    expect(screen.getByText("Empty Retrieval")).toBeInTheDocument();
    expect(screen.getByText("44")).toBeInTheDocument();
  });
});
