import { useState } from "react";
import { Ban, CheckCircle2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getVideoReview, saveVideoDecision } from "@/admin/lib/api";
import type {
  HumanSpeakerCheck,
  VideoDecisionPayload,
  VideoHumanDecision,
} from "@/admin/types";

const MIN_REASON_LEN = 3;

/** True when the stored decision keeps this video out of every serving lane. */
export function decisionBlocksServing(decision: VideoHumanDecision | null | undefined): boolean {
  return decision?.admin_approved === false || decision?.human_speaker_check === "rejected";
}

/**
 * The PUT replaces the whole human decision (null clears a field), so every save starts
 * from the stored decision and overrides only what the reviewer changed.
 */
export function buildDecisionPayload(
  current: VideoHumanDecision | null | undefined,
  overrides: Partial<VideoDecisionPayload>,
): VideoDecisionPayload {
  return {
    admin_approved: current?.admin_approved ?? null,
    human_speaker_check: current?.human_speaker_check ?? null,
    grade: current?.grade ?? null,
    notes: current?.notes ?? null,
    reason: null,
    ...overrides,
  };
}

/**
 * The PUT replaces the whole decision, so a payload built from props could silently undo a
 * grade or note another admin saved after the list loaded. Re-read the stored decision
 * right before writing. A failed read aborts the save instead of guessing.
 */
async function currentDecision(videoId: string): Promise<VideoHumanDecision | null> {
  const detail = await getVideoReview(videoId);
  return detail.video.decision ?? null;
}

interface ControlProps {
  videoId: string;
  decision: VideoHumanDecision | null | undefined;
  /** Called after the backend accepted the decision. */
  onSaved?: () => void;
}

/**
 * One-click serving governance. "Exclude" stores admin_approved=false, which the backend
 * turns into a block on first-person retrieval, general RAG retrieval and the media
 * stream. "Allow serving" stores admin_approved=true; it never loosens a machine gate.
 * A speaker check of "rejected" also blocks, so it must be cleared in the review panel.
 */
export function VideoServingToggle({ videoId, decision, onSaved }: ControlProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  const blocked = decisionBlocksServing(decision);
  const rejectedBySpeakerCheck = decision?.human_speaker_check === "rejected";
  const nextApproved = blocked ? true : false;
  const reasonOk = reason.trim().length >= MIN_REASON_LEN;

  const submit = async () => {
    setSaving(true);
    try {
      const stored = await currentDecision(videoId);
      const res = await saveVideoDecision(
        videoId,
        buildDecisionPayload(stored, { admin_approved: nextApproved, reason: reason.trim() }),
      );
      if (nextApproved && res.blocks_serving) {
        // The speaker check is still "rejected": saving succeeded but nothing was unblocked.
        toast.warning("Saved, but this video is still blocked by its rejected speaker check.");
      } else {
        toast.success(nextApproved ? "Video allowed for serving" : "Video excluded from serving");
      }
      setOpen(false);
      setReason("");
      onSaved?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save the decision");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        className={`gap-1.5 ${blocked ? "" : "text-destructive border-destructive/40 hover:bg-destructive/10 hover:text-destructive"}`}
        onClick={() => setOpen(true)}
        data-testid={`serving-toggle-${videoId}`}
      >
        {blocked ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Ban className="h-3.5 w-3.5" />}
        {blocked ? "Allow serving" : "Exclude from serving"}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {nextApproved ? "Allow this video to be served?" : "Exclude this video from serving?"}
            </DialogTitle>
            <DialogDescription>
              {nextApproved
                ? "Machine gates (speaker verification, rights, integrity) still apply. This only removes the admin block."
                : "Seekers will no longer receive clips, passages or the media file from this video. You can allow it again at any time."}
              {rejectedBySpeakerCheck && nextApproved
                ? " The speaker check is still Rejected, which keeps blocking it until you change that in the review panel."
                : ""}
            </DialogDescription>
          </DialogHeader>
          <Input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason (required, 3+ characters)"
            aria-label="Reason"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={() => void submit()} disabled={saving || !reasonOk}>
              {saving ? "Saving…" : nextApproved ? "Allow serving" : "Exclude"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

const SPEAKER_OPTIONS: ReadonlyArray<{ value: HumanSpeakerCheck | "review"; label: string; hint: string }> = [
  { value: "confirmed", label: "Confirmed", hint: "I listened; the machine-attributed teacher is right." },
  { value: "rejected", label: "Rejected", hint: "Wrong or mixed speaker. Blocks serving." },
  { value: "review", label: "Needs review", hint: "No human verdict yet." },
];

/**
 * Human-in-the-loop verdict on the machine's speaker attribution. It records a human
 * decision next to the machine evidence; it never rewrites `speaker_verified` or the
 * teacher id, which come from the voice match only.
 */
export function VideoHitlPanel({ videoId, decision, onSaved }: ControlProps) {
  const [check, setCheck] = useState<HumanSpeakerCheck | "review">(
    decision?.human_speaker_check ?? "review",
  );
  const [notes, setNotes] = useState(decision?.notes ?? "");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  const nextCheck = check === "review" ? null : check;
  const checkChanged = nextCheck !== (decision?.human_speaker_check ?? null);
  const reasonOk = !checkChanged || reason.trim().length >= MIN_REASON_LEN;

  const submit = async () => {
    setSaving(true);
    try {
      const stored = await currentDecision(videoId);
      await saveVideoDecision(
        videoId,
        buildDecisionPayload(stored, {
          human_speaker_check: nextCheck,
          notes: notes.trim() === "" ? null : notes,
          reason: reason.trim() === "" ? null : reason.trim(),
        }),
      );
      toast.success("Human review saved");
      setReason("");
      onSaved?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save the review");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4 text-xs" data-testid="hitl-panel">
      <div className="space-y-2">
        <p className="flex items-center gap-1.5 font-semibold text-foreground">
          <ShieldCheck className="h-3.5 w-3.5 text-primary" /> Speaker attribution verdict
        </p>
        <div className="grid gap-2">
          {SPEAKER_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className={`flex cursor-pointer items-start gap-2 rounded-lg border p-2.5 ${
                check === opt.value ? "border-primary bg-primary/5" : "border-border"
              }`}
            >
              <input
                type="radio"
                name={`speaker-check-${videoId}`}
                className="mt-0.5"
                checked={check === opt.value}
                onChange={() => setCheck(opt.value)}
              />
              <span>
                <span className="font-medium text-foreground">{opt.label}</span>
                <span className="block text-muted-foreground">{opt.hint}</span>
              </span>
            </label>
          ))}
        </div>
        <p className="text-muted-foreground">
          The teacher label comes from the voice match, never from a human edit. To dispute it, reject
          the speaker check.
        </p>
      </div>
      <Textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Notes for the next reviewer (optional)"
        aria-label="Notes"
        className="min-h-[72px]"
      />
      <Input
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder={checkChanged ? "Reason (required, 3+ characters)" : "Reason (optional)"}
        aria-label="Reason"
      />
      <div className="flex items-center justify-between gap-2">
        <VideoServingToggle videoId={videoId} decision={decision} onSaved={onSaved} />
        <Button size="sm" onClick={() => void submit()} disabled={saving || !reasonOk}>
          {saving ? "Saving…" : "Save review"}
        </Button>
      </div>
    </div>
  );
}
