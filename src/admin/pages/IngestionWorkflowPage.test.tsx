import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import IngestionWorkflowPage from "./IngestionWorkflowPage";
import * as api from "@/admin/lib/api";
import type { VideoReviewList, VideoReviewRow } from "@/admin/types";

vi.mock("@/admin/lib/api", () => ({
  listVideoReview: vi.fn(),
  getFirstPersonIngestJob: vi.fn(),
  saveVideoDecision: vi.fn(),
  getVideoReview: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const listMock = vi.mocked(api.listVideoReview);
const jobMock = vi.mocked(api.getFirstPersonIngestJob);

const row: VideoReviewRow = {
  video_id: "abcdefghijk",
  title: "Calm Mind",
  channel: "Sri Preethaji & Sri Krishnaji",
  youtube_url: "https://www.youtube.com/watch?v=abcdefghijk",
  in_v10: true,
  status_note: "",
  machine: {
    source: "live",
    child_spans: 4,
    speaker_verified_spans: 3,
    spans_with_voice_method: 3,
    min_window_cosine: 0.64,
    speaker_status: "partial",
    guru_ids: ["krishnaji"],
  },
  decision: null,
  approval_state: "undecided",
  serving: "gates_apply",
};

const list = (rows: VideoReviewRow[]): VideoReviewList => ({
  total: rows.length,
  limit: 100,
  offset: 0,
  rows,
  channels: [],
  live: true,
  collection: "c",
  summary: {
    videos: rows.length,
    in_v10: rows.length,
    missing_in_v10: 0,
    approved: 0,
    rejected: 0,
    undecided: rows.length,
    blocked_by_admin: 0,
    machine_speaker: { none: 0, partial: rows.length, full: 0, "n/a": 0 },
  },
});

const job = (over: Partial<Awaited<ReturnType<typeof api.getFirstPersonIngestJob>>>) => ({
  job_id: "job-1",
  video_url: "https://www.youtube.com/watch?v=abcdefghijk",
  status: "running",
  stage: "speaker_verification",
  progress_pct: 60,
  clips_indexed: 0,
  ...over,
});

const track = (id = "job-1") => {
  fireEvent.change(screen.getByLabelText("Job id"), { target: { value: id } });
  fireEvent.click(screen.getByRole("button", { name: "Track" }));
};

const nodeState = (id: string) => screen.getByTestId(`dag-node-${id}`).getAttribute("data-run-state");

describe("IngestionWorkflowPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue(list([row]));
  });

  it("loads real videos, not hardcoded samples, and claims nothing before a job is tracked", async () => {
    render(<IngestionWorkflowPage />);
    expect(await screen.findByText("Calm Mind")).toBeInTheDocument();
    expect(screen.getByTestId("job-banner")).toHaveTextContent("No live job tracked");
    expect(screen.queryByText(/0kI4_7Fw1yY/)).toBeNull();
  });

  it("pulses the ECAPA node for a tracked job in speaker_verification", async () => {
    jobMock.mockResolvedValue(job({}));
    render(<IngestionWorkflowPage />);
    await screen.findByText("Calm Mind");
    track();
    await waitFor(() => expect(nodeState("stage-4-attribution")).toBe("active"));
    expect(screen.getByTestId("job-banner")).toHaveTextContent("speaker_verification");
  });

  it("keeps the failing stage when a first-person job fails with stage 'failed'", async () => {
    // First poll: running in speaker_verification. Next poll (2.5 s later): the backend
    // reports stage "failed", which names no node, so the page must remember the last one.
    jobMock.mockResolvedValueOnce(job({}));
    jobMock.mockResolvedValue(job({ status: "failed", stage: "failed", error_message: "boom" }));
    render(<IngestionWorkflowPage />);
    await screen.findByText("Calm Mind");
    track();
    await waitFor(() => expect(nodeState("stage-4-attribution")).toBe("active"));
    await waitFor(() => expect(nodeState("stage-4-attribution")).toBe("failed"), { timeout: 6000 });
    expect(nodeState("stage-3-asr")).toBe("completed");
  }, 10000);

  it("surfaces a poll error instead of leaving a stale running state", async () => {
    jobMock.mockRejectedValue(new Error("502 bad gateway"));
    render(<IngestionWorkflowPage />);
    await screen.findByText("Calm Mind");
    track();
    expect(await screen.findByText("502 bad gateway")).toBeInTheDocument();
  });

  it("warns when the tracked job belongs to a different video", async () => {
    jobMock.mockResolvedValue(job({ video_url: "https://www.youtube.com/watch?v=zzzzzzzzzzz" }));
    render(<IngestionWorkflowPage />);
    await screen.findByText("Calm Mind");
    track();
    expect(await screen.findByTestId("job-mismatch")).toBeInTheDocument();
  });
});
