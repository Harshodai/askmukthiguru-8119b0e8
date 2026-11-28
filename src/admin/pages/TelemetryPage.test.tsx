import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import TelemetryPage from "./TelemetryPage";

// Mock the hook from useAdminData
vi.mock("@/admin/hooks/useAdminData", () => ({
  useQueries: vi.fn().mockReturnValue({
    data: [
      {
        id: "query-1",
        model: "deepseek/deepseek-chat",
        prompt_tokens: 100,
        completion_tokens: 40,
        cost_estimate: 0.0012,
        latency_ms: 1250,
        status: "ok",
        created_at: "2026-06-19T12:00:00Z",
      },
    ],
  }),
  useTelemetryEvents: vi.fn().mockReturnValue({
    data: {
      count: 2,
      data: [
        {
          id: "event-1",
          created_at: "2026-06-19T12:00:00Z",
          metric_type: "ai_response_time",
          metric_value: 125,
          user_id: "user-123",
          session_id: "session-456",
          user_message_id: "msg-789",
          tags: { model: "gpt-4" },
        },
        {
          id: "event-2",
          created_at: "2026-06-19T12:05:00Z",
          metric_type: "token_usage",
          metric_value: 450,
          user_id: "user-123",
          session_id: "session-456",
          user_message_id: "msg-789",
          tags: { tokens: "completion" },
        },
      ],
    },
    isLoading: false,
  }),
}));

describe("TelemetryPage", () => {
  it("renders the telemetry page header and filters", () => {
    render(<TelemetryPage />);

    expect(screen.getByText("Telemetry Events")).toBeInTheDocument();
    expect(screen.getByText("Raw telemetry events — AI response times, token usage, and pipeline latencies.")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("msg_abc123…")).toBeInTheDocument();
  });

  it("renders the telemetry event rows correctly", () => {
    render(<TelemetryPage />);

    expect(screen.getByText("ai_response_time")).toBeInTheDocument();
    expect(screen.getByText("125ms")).toBeInTheDocument();
    expect(screen.getByText("token_usage")).toBeInTheDocument();
    expect(screen.getByText("450")).toBeInTheDocument();
  });

  it("renders per-turn model usage and cost fields", () => {
    render(<TelemetryPage />);

    expect(screen.getByText("Recent model usage")).toBeInTheDocument();
    expect(screen.getByText("deepseek/deepseek-chat")).toBeInTheDocument();
    expect(screen.getByText("$0.00120")).toBeInTheDocument();
    expect(screen.getByText("1.25s")).toBeInTheDocument();
  });
});
