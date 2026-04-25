import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SpanWaterfall } from "./SpanWaterfall";
import type { TraceSpan } from "@/admin/types";

const spans: TraceSpan[] = [
  { id: "1", query_id: "q", parent_span_id: null, name: "embed", start_ms: 0, duration_ms: 50, attributes: {} },
  { id: "2", query_id: "q", parent_span_id: null, name: "vector_search", start_ms: 50, duration_ms: 100, attributes: {} },
  { id: "3", query_id: "q", parent_span_id: null, name: "llm", start_ms: 150, duration_ms: 400, attributes: {} },
];

describe("SpanWaterfall", () => {
  it("renders empty state when no spans", () => {
    render(<SpanWaterfall spans={[]} />);
    expect(screen.getByText(/no spans/i)).toBeInTheDocument();
  });

  it("renders one row per span with name and duration", () => {
    render(<SpanWaterfall spans={spans} />);
    expect(screen.getByText("embed")).toBeInTheDocument();
    expect(screen.getByText("vector_search")).toBeInTheDocument();
    expect(screen.getByText("llm")).toBeInTheDocument();
    expect(screen.getByText("50ms")).toBeInTheDocument();
    expect(screen.getByText("400ms")).toBeInTheDocument();
  });

  it("shows total duration", () => {
    render(<SpanWaterfall spans={spans} />);
    expect(screen.getByText(/550ms/)).toBeInTheDocument();
  });
});
