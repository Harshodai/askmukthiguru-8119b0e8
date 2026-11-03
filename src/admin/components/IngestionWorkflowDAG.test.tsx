import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within, fireEvent, waitFor } from "@testing-library/react";
import { IngestionWorkflowDAG, type IngestionVideoContext } from "./IngestionWorkflowDAG";
import * as api from "@/admin/lib/api";
import type { VideoHumanDecision } from "@/admin/types";

vi.mock("@/admin/lib/api", () => ({ saveVideoDecision: vi.fn(), getVideoReview: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const saveMock = vi.mocked(api.saveVideoDecision);
const getMock = vi.mocked(api.getVideoReview);

const video: IngestionVideoContext = {
  videoId: "abcdefghijk",
  title: "Calm Mind",
  verifiedSpans: 3,
  totalSpans: 4,
  minWindowCosine: 0.642,
  speakerStatus: "partial",
  guruIds: ["krishnaji"],
  inV10: true,
  decision: null,
};

const nodeState = (id: string) =>
  screen.getByTestId(`dag-node-${id}`).getAttribute("data-run-state");

describe("IngestionWorkflowDAG live highlight", () => {
  beforeEach(() => vi.clearAllMocks());

  it("pulses the ECAPA node and shows Processing while speaker_verification runs", () => {
    render(
      <IngestionWorkflowDAG
        videoContext={video}
        job={{ status: "running", stage: "speaker_verification", progressPct: 55 }}
      />,
    );
    expect(nodeState("stage-4-attribution")).toBe("active");
    expect(nodeState("stage-3-asr")).toBe("completed");
    expect(nodeState("stage-5-sanitization")).toBe("queued");

    const active = screen.getByTestId("dag-node-stage-4-attribution");
    expect(active.className).toContain("animate-pulse");
    expect(active.className).toContain("ring-primary/30");
    expect(within(active).getByText("Processing…")).toBeInTheDocument();
    expect(screen.getAllByTestId("dag-active-indicator")).toHaveLength(1);
    expect(screen.getByTestId("job-banner")).toHaveTextContent("Processing · speaker_verification");
  });

  it("moves the highlight when the job advances", () => {
    const { rerender } = render(
      <IngestionWorkflowDAG videoContext={video} job={{ status: "running", stage: "aligning" }} />,
    );
    expect(nodeState("stage-3-asr")).toBe("active");
    rerender(
      <IngestionWorkflowDAG
        videoContext={video}
        job={{ status: "running", stage: "speaker_verification" }}
      />,
    );
    expect(nodeState("stage-3-asr")).toBe("completed");
    expect(nodeState("stage-4-attribution")).toBe("active");
  });

  it("claims nothing without a job: no active node, no passed badge, neutral banner", () => {
    render(<IngestionWorkflowDAG videoContext={video} />);
    for (const id of ["stage-1-intake", "stage-4-attribution", "stage-8-persistence"]) {
      expect(nodeState(id)).toBe("unknown");
    }
    expect(screen.queryByTestId("dag-active-indicator")).toBeNull();
    expect(screen.queryByText(/8\/8 Passed/)).toBeNull();
    expect(screen.queryByText(/Licensed & Verified/)).toBeNull();
    expect(screen.getByTestId("job-banner")).toHaveTextContent("No live job tracked");
  });

  it("marks the failing stage and nothing as active", () => {
    render(
      <IngestionWorkflowDAG
        videoContext={video}
        job={{ status: "failed", stage: "speaker_verification", errorMessage: "ECAPA model missing" }}
      />,
    );
    expect(nodeState("stage-4-attribution")).toBe("failed");
    expect(screen.queryByTestId("dag-active-indicator")).toBeNull();
    expect(screen.getByTestId("job-banner")).toHaveTextContent("Job failed");
  });

  it("shows an excluded badge when the stored decision blocks serving", () => {
    const decision: VideoHumanDecision = {
      video_id: "abcdefghijk",
      admin_approved: false,
      human_speaker_check: null,
      grade: null,
      notes: null,
      updated_by: "admin",
      updated_at: "2026-11-01T00:00:00Z",
      reason: "test",
    };
    render(<IngestionWorkflowDAG videoContext={{ ...video, decision }} />);
    expect(screen.getByTestId("excluded-badge")).toBeInTheDocument();
  });
});

describe("IngestionWorkflowDAG stage drawer", () => {
  beforeEach(() => vi.clearAllMocks());

  const openAttribution = () => fireEvent.click(screen.getByTestId("dag-node-stage-4-attribution"));
  const openTab = async (name: string) => {
    const tab = await screen.findByRole("tab", { name });
    fireEvent.mouseDown(tab, { button: 0 });
    fireEvent.click(tab);
  };

  it("shows measured evidence only from the backend, with no invented thresholds", async () => {
    render(<IngestionWorkflowDAG videoContext={video} />);
    openAttribution();
    await openTab("Verify");
    const evidence = await screen.findByTestId("verification-evidence");
    expect(evidence).toHaveTextContent("3 / 4");
    expect(evidence).toHaveTextContent("0.642");
    expect(evidence).toHaveTextContent("krishnaji");
    expect(evidence).toHaveTextContent("partial");
  });

  it("says plainly that per-stage logs are not recorded and labels the sample as reference", async () => {
    render(<IngestionWorkflowDAG videoContext={video} />);
    openAttribution();
    await openTab("Logs");
    const logs = await screen.findByTestId("logs-tab");
    expect(logs).toHaveTextContent("does not store per-stage log");
    expect(logs).toHaveTextContent("reference, not from this video");
    expect(logs).not.toHaveTextContent("Sri Preethaji");
  });

  it("saves a human speaker verdict through the shared decision endpoint", async () => {
    saveMock.mockResolvedValue({ ok: true, decision: null, blocks_serving: true });
    const stored: VideoHumanDecision = {
      video_id: "abcdefghijk",
      admin_approved: true,
      human_speaker_check: null,
      grade: "B",
      notes: "earlier note",
      updated_by: "admin",
      updated_at: "2026-11-01T00:00:00Z",
      reason: "earlier",
    };
    getMock.mockResolvedValue({ video: { decision: stored } as never, audit: [] });
    const onSaved = vi.fn();
    render(
      <IngestionWorkflowDAG
        videoContext={{
          ...video,
          decision: stored,
        }}
        onDecisionSaved={onSaved}
      />,
    );
    openAttribution();
    await openTab("Review");
    await screen.findByTestId("hitl-panel");

    fireEvent.click(screen.getByLabelText(/Rejected/));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "wrong speaker" } });
    fireEvent.click(screen.getByRole("button", { name: "Save review" }));

    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
    expect(saveMock).toHaveBeenCalledWith("abcdefghijk", {
      admin_approved: true,
      human_speaker_check: "rejected",
      grade: "B",
      notes: "earlier note",
      reason: "wrong speaker",
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it("requires a reason before a speaker verdict can be saved", async () => {
    render(<IngestionWorkflowDAG videoContext={video} />);
    openAttribution();
    await openTab("Review");
    await screen.findByTestId("hitl-panel");
    fireEvent.click(screen.getByLabelText(/Confirmed/));
    expect(screen.getByRole("button", { name: "Save review" })).toBeDisabled();
  });
});
