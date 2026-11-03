import type { IngestionVideoContext } from "@/admin/components/IngestionWorkflowDAG";
import type { VideoReviewRow } from "@/admin/types";

/**
 * Builds the DAG's video context from a Video Approval row. Every field is copied from the
 * backend row; nothing is defaulted to a plausible value, so a missing measurement shows as
 * "not reported" instead of an invented one.
 */
export function rowToVideoContext(row: VideoReviewRow): IngestionVideoContext {
  return {
    videoId: row.video_id,
    title: row.title || row.video_id,
    channel: row.channel,
    url: row.youtube_url,
    verifiedSpans: row.machine?.speaker_verified_spans,
    totalSpans: row.machine?.child_spans,
    minWindowCosine: row.machine?.min_window_cosine ?? null,
    speakerStatus: row.machine?.speaker_status,
    guruIds: row.machine?.guru_ids,
    approved: row.decision?.admin_approved,
    inV10: row.in_v10,
    decision: row.decision ?? null,
  };
}
