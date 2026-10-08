/** Human-reviewed caption statuses. The backend defaults a missing status to
 *  "auto_transcript" (first_person_pipeline.py), so anything not explicitly
 *  human-reviewed is shown as an auto-transcript. Absent/empty => unknown, no label. */
const HUMAN_REVIEWED = new Set(['manual_caption', 'human_reviewed', 'reviewed']);

export const isAutoTranscript = (status?: string | null): boolean => {
  const s = (status ?? '').trim().toLowerCase();
  return s !== '' && !HUMAN_REVIEWED.has(s);
};

/** Chat citation cards: show "Auto-transcript" unless the payload explicitly says the
 *  transcript was reviewed. Unlike `isAutoTranscript`, an absent status defaults to
 *  auto-transcript (the chat wire shape does not carry the field yet). */
export const isUnreviewedTranscript = (status?: string | null): boolean => {
  const s = (status ?? '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  return !HUMAN_REVIEWED.has(s);
};
