import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import FeedbackPage from "./FeedbackPage";
import { useFeedback } from "@/admin/hooks/useAdminData";

vi.mock("@/admin/hooks/useAdminData", () => ({
  useFeedback: vi.fn(),
  useQueryTrace: vi.fn(() => ({ data: null, isLoading: false })),
}));

vi.mock("@/admin/components/TraceDrawer", () => ({
  TraceDrawer: ({ queryId }: { queryId: string | null }) => (
    <div data-testid="trace-drawer">TraceDrawer: {queryId}</div>
  ),
}));

const mockFeedback = vi.mocked(useFeedback);

describe("FeedbackPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders feedback entries with action links to view trace and deep link", () => {
    mockFeedback.mockReturnValue({
      data: [
        {
          id: "fb-123",
          user_id: "user-1",
          rating: 1,
          query_text: "Who am I?",
          answer_text: "You are pure consciousness.",
          feedback_text: "Very clear answer",
          comment: null,
          metadata_json: { query_id: "q-trace-999" },
          created_at: "2026-10-20T10:00:00Z",
        },
      ],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never);

    render(
      <MemoryRouter>
        <FeedbackPage />
      </MemoryRouter>
    );

    expect(screen.getByText("User Feedback")).toBeInTheDocument();
    expect(screen.getByText("Very clear answer")).toBeInTheDocument();
    expect(screen.getByText("View Trace")).toBeInTheDocument();

    const link = screen.getByTitle("Inspect in Queries page");
    expect(link).toBeInTheDocument();
    expect(link.getAttribute("href")).toContain("/admin/queries?traceId=q-trace-999");

    // Click View Trace to open drawer
    fireEvent.click(screen.getByText("View Trace"));
    expect(screen.getByTestId("trace-drawer")).toHaveTextContent("q-trace-999");
  });
});
