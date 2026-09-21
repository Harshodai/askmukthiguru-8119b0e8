import type { Citation, TeachingPreview } from '@/lib/chat/types';

export const teachingPreviewsFromCitations = (citations?: Citation[]): TeachingPreview[] =>
  (citations ?? [])
    .filter((citation) => Boolean(citation.title || citation.quote || citation.textSnippet))
    .slice(0, 3)
    .map((citation) => ({
      title: citation.title || citation.source || 'Teaching source',
      teacher: citation.speaker ?? null,
      url: citation.url || null,
      excerpt: citation.quote || citation.textSnippet || null,
    }));

/**
 * Decide which "teaching evidence" preview to attach to a committed message.
 *
 * `finalCitations` are post-grading/post-verification (backend's
 * `extract_citations` runs after `verify_answer`), so they reflect what the
 * answer actually cites. `rawStreamedPreview` is a retrieval-time candidate
 * list streamed before CRAG grading/reranking/verification even run — it can
 * name documents the final answer never used. The UI's "Verified Sacred
 * Teaching" badge is driven by `citationsVerified`, independent of which
 * array populates the card, so showing the raw preview first can label
 * unverified candidates as verified. Citations-derived preview must win
 * whenever it exists; the raw preview is only a fallback for answers with no
 * final citations at all (abstained/partial responses).
 */
export const resolveTeachingPreview = (
  finalCitations: Citation[] | undefined,
  rawStreamedPreview: TeachingPreview[],
  previousPreview: TeachingPreview[],
): TeachingPreview[] | undefined => {
  const fromCitations = teachingPreviewsFromCitations(finalCitations);
  if (fromCitations.length > 0) return fromCitations;
  if (rawStreamedPreview.length > 0) return rawStreamedPreview;
  if (previousPreview.length > 0) return previousPreview;
  return undefined;
};
