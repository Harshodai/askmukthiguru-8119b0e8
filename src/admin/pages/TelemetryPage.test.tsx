import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import TelemetryPage from "./TelemetryPage";

describe("TelemetryPage", () => {
  it("uses the default local Jaeger URL", () => {
    vi.stubEnv("VITE_JAEGER_UI_URL", "");

    render(<TelemetryPage />);

    expect(screen.getByTitle("Jaeger Telemetry")).toHaveAttribute(
      "src",
      "http://localhost:16686",
    );
  });

  it("uses VITE_JAEGER_UI_URL when configured", () => {
    vi.stubEnv("VITE_JAEGER_UI_URL", "http://localhost:9999");

    render(<TelemetryPage />);

    expect(screen.getByTitle("Jaeger Telemetry")).toHaveAttribute(
      "src",
      "http://localhost:9999",
    );
    expect(screen.getByRole("link", { name: /open jaeger/i })).toHaveAttribute(
      "href",
      "http://localhost:9999",
    );
  });

  it("shows a direct-open fallback when the iframe is unavailable", () => {
    vi.stubEnv("VITE_JAEGER_UI_URL", "http://localhost:9999");
    render(<TelemetryPage />);

    expect(screen.getByText(/embedded view is unavailable/i)).toBeInTheDocument();
  });
});
