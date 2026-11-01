import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import {
  VideoServingToggle,
  buildDecisionPayload,
  decisionBlocksServing,
} from "./VideoReviewControls";
import * as api from "@/admin/lib/api";
import type { VideoHumanDecision } from "@/admin/types";
import { toast } from "sonner";

vi.mock("@/admin/lib/api", () => ({ saveVideoDecision: vi.fn(), getVideoReview: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const saveMock = vi.mocked(api.saveVideoDecision);
const getMock = vi.mocked(api.getVideoReview);
const storedAs = (d: VideoHumanDecision | null) =>
  getMock.mockResolvedValue({ video: { decision: d } as never, audit: [] });

const decision = (over: Partial<VideoHumanDecision> = {}): VideoHumanDecision => ({
  video_id: "abcdefghijk",
  admin_approved: null,
  human_speaker_check: null,
  grade: "A",
  notes: "kept",
  updated_by: "admin",
  updated_at: "2026-11-01T00:00:00Z",
  reason: "r",
  ...over,
});

describe("decisionBlocksServing", () => {
  it("mirrors the backend rule: approval false or speaker check rejected", () => {
    expect(decisionBlocksServing(null)).toBe(false);
    expect(decisionBlocksServing(decision())).toBe(false);
    expect(decisionBlocksServing(decision({ admin_approved: true }))).toBe(false);
    expect(decisionBlocksServing(decision({ admin_approved: false }))).toBe(true);
    expect(decisionBlocksServing(decision({ human_speaker_check: "rejected" }))).toBe(true);
    expect(decisionBlocksServing(decision({ human_speaker_check: "confirmed" }))).toBe(false);
  });
});

describe("buildDecisionPayload", () => {
  it("keeps stored fields so a partial change cannot wipe the rest of the decision", () => {
    expect(buildDecisionPayload(decision({ admin_approved: true }), { admin_approved: false, reason: "x" })).toEqual({
      admin_approved: false,
      human_speaker_check: null,
      grade: "A",
      notes: "kept",
      reason: "x",
    });
    expect(buildDecisionPayload(null, {})).toEqual({
      admin_approved: null,
      human_speaker_check: null,
      grade: null,
      notes: null,
      reason: null,
    });
  });
});

describe("VideoServingToggle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    saveMock.mockResolvedValue({ ok: true, decision: null, blocks_serving: true });
    storedAs(decision());
  });

  it("excludes a video with a reason and keeps the other decision fields", async () => {
    const onSaved = vi.fn();
    render(<VideoServingToggle videoId="abcdefghijk" decision={decision()} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole("button", { name: /Exclude from serving/ }));
    const confirm = await screen.findByRole("button", { name: "Exclude" });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "not the teacher" } });
    fireEvent.click(confirm);
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
    expect(saveMock).toHaveBeenCalledWith("abcdefghijk", {
      admin_approved: false,
      human_speaker_check: null,
      grade: "A",
      notes: "kept",
      reason: "not the teacher",
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it("offers Allow serving for an excluded video and restores it", async () => {
    storedAs(decision({ admin_approved: false }));
    saveMock.mockResolvedValue({ ok: true, decision: null, blocks_serving: false });
    render(<VideoServingToggle videoId="abcdefghijk" decision={decision({ admin_approved: false })} />);
    fireEvent.click(screen.getByRole("button", { name: /Allow serving/ }));
    fireEvent.change(await screen.findByLabelText("Reason"), { target: { value: "checked again" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Allow serving" }).at(-1)!);
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
    expect(saveMock.mock.calls[0][1]).toMatchObject({ admin_approved: true, reason: "checked again" });
  });

  it("warns when a rejected speaker check keeps blocking after allowing", async () => {
    render(
      <VideoServingToggle
        videoId="abcdefghijk"
        decision={decision({ admin_approved: false, human_speaker_check: "rejected" })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Allow serving/ }));
    expect(await screen.findByText(/speaker check is still Rejected/)).toBeInTheDocument();
  });

  it("writes over the stored decision, not the stale props", async () => {
    storedAs(decision({ grade: "F", notes: "edited by someone else" }));
    render(<VideoServingToggle videoId="abcdefghijk" decision={decision()} />);
    fireEvent.click(screen.getByRole("button", { name: /Exclude from serving/ }));
    fireEvent.change(await screen.findByLabelText("Reason"), { target: { value: "not the teacher" } });
    fireEvent.click(screen.getByRole("button", { name: "Exclude" }));
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
    expect(saveMock.mock.calls[0][1]).toMatchObject({ grade: "F", notes: "edited by someone else" });
  });

  it("does not claim success when the video stays blocked after allowing", async () => {
    storedAs(decision({ admin_approved: false, human_speaker_check: "rejected" }));
    saveMock.mockResolvedValue({ ok: true, decision: null, blocks_serving: true });
    render(
      <VideoServingToggle
        videoId="abcdefghijk"
        decision={decision({ admin_approved: false, human_speaker_check: "rejected" })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Allow serving/ }));
    fireEvent.change(await screen.findByLabelText("Reason"), { target: { value: "second look" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Allow serving" }).at(-1)!);
    await waitFor(() => expect(saveMock).toHaveBeenCalled());
    expect(toast.warning).toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("aborts the save when the stored decision cannot be read", async () => {
    getMock.mockRejectedValue(new Error("503"));
    render(<VideoServingToggle videoId="abcdefghijk" decision={decision()} />);
    fireEvent.click(screen.getByRole("button", { name: /Exclude from serving/ }));
    fireEvent.change(await screen.findByLabelText("Reason"), { target: { value: "not the teacher" } });
    fireEvent.click(screen.getByRole("button", { name: "Exclude" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(saveMock).not.toHaveBeenCalled();
  });
});
