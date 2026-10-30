import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import VideoApprovalPage from "./VideoApprovalPage";
import * as api from "@/admin/lib/api";
import type { VideoReviewList, VideoReviewRow } from "@/admin/types";

vi.mock("@/admin/lib/api", () => ({
  listVideoReview: vi.fn(),
  getVideoReview: vi.fn(),
  saveVideoDecision: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const listMock = vi.mocked(api.listVideoReview);
const getMock = vi.mocked(api.getVideoReview);
const saveMock = vi.mocked(api.saveVideoDecision);

const row = (over: Partial<VideoReviewRow> = {}): VideoReviewRow => ({
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
  ...over,
});

const list = (rows: VideoReviewRow[], over: Partial<VideoReviewList> = {}): VideoReviewList => ({
  total: rows.length,
  limit: 25,
  offset: 0,
  rows,
  channels: ["Sri Preethaji & Sri Krishnaji", "Times Now"],
  live: true,
  collection: "first_person_v10",
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
  ...over,
});

describe("VideoApprovalPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue(list([row()]));
    getMock.mockResolvedValue({ video: row(), audit: [] });
    saveMock.mockResolvedValue({ ok: true, decision: null, blocks_serving: true });
  });

  it("shows machine evidence next to the human decision", async () => {
    render(<VideoApprovalPage />);
    expect(await screen.findByText("Calm Mind")).toBeInTheDocument();
    expect(screen.getByText(/\/ 4 spans verified/, { selector: "div" })).toBeInTheDocument();
    expect(screen.getByText(/min window cosine 0.64/)).toBeInTheDocument();
    expect(screen.getByText("No decision", { selector: "div" })).toBeInTheDocument();
  });

  it("sends filters to the API and resets to the first page", async () => {
    render(<VideoApprovalPage />);
    await screen.findByText("Calm Mind");
    fireEvent.change(screen.getByLabelText("My decision"), { target: { value: "rejected" } });
    fireEvent.change(screen.getByLabelText("In v10"), { target: { value: "false" } });
    fireEvent.change(screen.getByLabelText("Machine speaker check"), { target: { value: "none" } });
    fireEvent.change(screen.getByLabelText("Channel"), { target: { value: "Times Now" } });
    await waitFor(() => {
      const last = listMock.mock.calls.at(-1)![0]!;
      expect(last).toMatchObject({
        approved: "rejected",
        in_v10: false,
        verified: "none",
        channel: "Times Now",
        offset: 0,
      });
    });
  });

  it("requires a reason before a rejection can be saved, then saves the full decision", async () => {
    render(<VideoApprovalPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    const panel = await screen.findByLabelText("Review abcdefghijk");
    fireEvent.change(within(panel).getByLabelText(/Serve this video/), { target: { value: "rejected" } });
    const save = within(panel).getByRole("button", { name: "Save decision" });
    expect(save).toBeDisabled();

    fireEvent.change(within(panel).getByPlaceholderText(/Why are you changing/), {
      target: { value: "host voice, not the teacher" },
    });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
    expect(saveMock).toHaveBeenCalledWith("abcdefghijk", {
      admin_approved: false,
      human_speaker_check: null,
      grade: null,
      notes: null,
      reason: "host voice, not the teacher",
    });
  });

  it("never sends the machine speaker field", async () => {
    render(<VideoApprovalPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    const panel = await screen.findByLabelText("Review abcdefghijk");
    fireEvent.change(within(panel).getByLabelText(/Grade/), { target: { value: "B" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Save decision" }));
    await waitFor(() => expect(saveMock).toHaveBeenCalled());
    const payload = saveMock.mock.calls[0][1] as unknown as Record<string, unknown>;
    expect(Object.keys(payload).sort()).toEqual(
      ["admin_approved", "grade", "human_speaker_check", "notes", "reason"].sort(),
    );
  });

  it("explains that approval does not override a failed machine check", async () => {
    render(<VideoApprovalPage />);
    expect(await screen.findByText(/Approving never overrides a failed machine check/)).toBeInTheDocument();
  });

  it("shows an error with retry when the list cannot load", async () => {
    listMock.mockRejectedValueOnce(new Error("Admin access denied. Verify your role and MFA."));
    render(<VideoApprovalPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Admin access denied");
    listMock.mockResolvedValueOnce(list([row()]));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Calm Mind")).toBeInTheDocument();
  });

  it("flags a snapshot when live evidence is unavailable", async () => {
    listMock.mockResolvedValue(
      list([row({ machine: { ...row().machine, source: "inventory", min_window_cosine: null } })], { live: false }),
    );
    render(<VideoApprovalPage />);
    expect(await screen.findByText(/snapshot, not live/)).toBeInTheDocument();
    expect(screen.getByText(/Live evidence is unavailable/)).toBeInTheDocument();
  });
});
