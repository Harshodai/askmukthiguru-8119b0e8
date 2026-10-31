import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ClipReportsPage from "./ClipReportsPage";
import { useClipReports } from "@/admin/hooks/useAdminData";

vi.mock("@/admin/hooks/useAdminData", () => ({
  useClipReports: vi.fn(),
}));

const mockedHook = vi.mocked(useClipReports);

function renderPage() {
  return render(
    <MemoryRouter>
      <ClipReportsPage />
    </MemoryRouter>,
  );
}

const ROW = {
  ts: "2026-10-15T10:00:00Z",
  served_point_id: "pt_abc123",
  question: "What is the beautiful state?",
  reason: "Clip starts mid-sentence",
  reporter: "faculty-1",
  reporter_user_id: "user-9",
};

const okState = (data: unknown[]) => ({
  data,
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
  isFetching: false,
});

describe("ClipReportsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders rows with header and PII notice", () => {
    mockedHook.mockReturnValue(okState([ROW]) as never);
    renderPage();

    expect(screen.getByText("Clip Reports")).toBeInTheDocument();
    expect(screen.getByText(/confidential/i)).toBeInTheDocument();
    expect(screen.getByText("What is the beautiful state?")).toBeInTheDocument();
    expect(screen.getByText("Clip starts mid-sentence")).toBeInTheDocument();
    expect(screen.getByText("faculty-1")).toBeInTheDocument();
  });

  it("renders loading skeletons while fetching", () => {
    mockedHook.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: true,
    } as never);
    const { container } = renderPage();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it("renders the empty state when there are no reports", () => {
    mockedHook.mockReturnValue(okState([]) as never);
    renderPage();
    expect(screen.getByText("No clip reports in this window")).toBeInTheDocument();
  });

  it("renders the denied state on 403 with a login link", () => {
    mockedHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("Admin access required"),
      refetch: vi.fn(),
      isFetching: false,
    } as never);
    renderPage();
    expect(screen.getByText("You do not have access to this area.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Admin Login" })).toHaveAttribute(
      "href",
      "/admin/login",
    );
  });

  it("renders a retryable error on non-auth failure", () => {
    const refetch = vi.fn();
    mockedHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("500 Internal Server Error"),
      refetch,
      isFetching: false,
    } as never);
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("escapes reporter free text instead of injecting markup", () => {
    mockedHook.mockReturnValue(
      okState([
        { ...ROW, question: "<script>alert(1)</script>", reason: '<img src=x onerror="alert(2)">' },
      ]) as never,
    );
    const { container } = renderPage();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
  });

  it("wires Next/Previous to limit/offset pagination", () => {
    const fullPage = Array.from({ length: 20 }, (_, i) => ({
      ...ROW,
      served_point_id: `pt_${i}`,
      ts: `2026-10-15T10:${String(i).padStart(2, "0")}:00Z`,
    }));
    mockedHook.mockReturnValue(okState(fullPage) as never);
    renderPage();

    expect(mockedHook).toHaveBeenCalledWith(20, 0);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(mockedHook).toHaveBeenCalledWith(20, 20);
  });

  it("disables Next on a short (final) page", () => {
    mockedHook.mockReturnValue(okState([ROW]) as never);
    renderPage();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
  });

  it("renders cross-linking action links to speaker attribution and video approval", () => {
    mockedHook.mockReturnValue(okState([ROW]) as never);
    renderPage();

    const attributionLink = screen.getByTitle("Inspect in Speaker Attribution");
    expect(attributionLink).toBeInTheDocument();
    expect(attributionLink.getAttribute("href")).toContain("/admin/ingestion?tab=attribution&videoId=pt_abc123");

    const approvalLink = screen.getByTitle("Inspect in Video Approval");
    expect(approvalLink).toBeInTheDocument();
    expect(approvalLink.getAttribute("href")).toContain("/admin/ingestion?tab=video-approval&videoId=pt_abc123");
  });

  it("renders point id as an interactive button to inspect provenance", () => {
    mockedHook.mockReturnValue(okState([ROW]) as never);
    renderPage();

    const pointBtn = screen.getByTitle("Inspect provenance for pt_abc123");
    expect(pointBtn).toBeInTheDocument();
  });
});
