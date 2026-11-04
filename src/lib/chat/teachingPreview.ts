import type { Citation, TeachingPreview } from '@/lib/chat/types';
import { resolveAttributionLabel } from '@/lib/chat/types';

export const teachingPreviewsFromCitations = (citations?: Citation[]): TeachingPreview[] =>
  (citations ?? [])
    .filter((citation) => Boolean(citation.title || citation.quote || citation.textSnippet))
    .slice(0, 3)
    .map((citation) => ({
      title: citation.title || citation.source || 'Teaching source',
      teacher: resolveAttributionLabel(citation) ?? null,
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

export interface EditorialTeachingCitationGroup {
  citation: Citation;
  /** Zero-based position of the first source citation in the original array. */
  citationIndex: number;
}

type CitationWithSourceIdentity = Citation & Record<string, unknown>;

const nonEmptyString = (...values: unknown[]): string | undefined => {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return undefined;
};

const canonicalYouTubeVideoId = (value: string): string | undefined => {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/^www\./, '');
    let id: string | null = null;
    if (host === 'youtu.be') id = url.pathname.split('/').filter(Boolean)[0] ?? null;
    if (host === 'youtube.com' || host === 'youtube-nocookie.com') {
      id = url.searchParams.get('v');
      if (!id) {
        const parts = url.pathname.split('/').filter(Boolean);
        if (['embed', 'shorts', 'live'].includes(parts[0] ?? '')) id = parts[1] ?? null;
      }
    }
    return id && /^[A-Za-z0-9_-]{11}$/.test(id) ? id : undefined;
  } catch {
    return undefined;
  }
};

const verifiedVideoId = (citation: Citation, raw: CitationWithSourceIdentity): string | undefined => {
  const claimed = nonEmptyString(raw.video_id, citation.videoId);
  const sourceIds = [citation.url, citation.playbackUrl, raw.video_url, raw.source_url, raw.playback_url]
    .filter((value): value is string => typeof value === 'string')
    .map(canonicalYouTubeVideoId)
    .filter((value): value is string => Boolean(value));
  if (sourceIds.length === 0 || sourceIds.some((id) => id !== sourceIds[0])) return undefined;
  return claimed && claimed !== sourceIds[0] ? undefined : sourceIds[0];
};

const finiteIndex = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : undefined;

const citationQuote = (citation: Citation, raw: CitationWithSourceIdentity): string => {
  for (const value of [citation.quote, citation.textSnippet, raw.verbatim_text]) {
    if (typeof value === 'string' && value.trim()) return value;
  }
  return '';
};

/**
 * Group only explicit first-person citations from the same source video. The
 * quote is the ordered, verbatim child-span join; no prose is introduced.
 */
export const groupEditorialTeachingCitations = (
  citations: Citation[],
): EditorialTeachingCitationGroup[] => {
  type Item = {
    citation: Citation;
    index: number;
    sourceSpanIndex: number;
  };
  const groups = new Map<string, Item[]>();
  const ungrouped: EditorialTeachingCitationGroup[] = [];
  citations.forEach((citation, index) => {
    const raw = citation as CitationWithSourceIdentity;
    const videoId = verifiedVideoId(citation, raw);
    const parentUnitId = nonEmptyString(raw.parent_unit_id, citation.parentUnitId);
    const sourceSpanIndex = finiteIndex(raw.source_span_index ?? citation.sourceSpanIndex);
    const sourceSpanId = nonEmptyString(raw.source_span_id, citation.sourceSpanId);
    const teacherId = nonEmptyString(raw.teacher_id, raw.guru_id, citation.teacherId);
    const speakerId = nonEmptyString(raw.speaker_id, citation.speakerId);
    const speaker = nonEmptyString(citation.speaker);
    if (
      !videoId
      || !parentUnitId
      || !sourceSpanId
      || sourceSpanIndex === undefined
      || !teacherId
      || !speakerId
      || !speaker
      || citation.isVerbatim !== true
      || citation.rightsCleared !== true
    ) {
      ungrouped.push({ citation, citationIndex: index });
      return;
    }
    const key = [
      videoId,
      parentUnitId,
      teacherId ?? '',
      speakerId ?? '',
      speaker ?? '',
      citation.speakerVerified === true ? 'verified' : 'unverified',
    ].join('\u0000');
    const item = { citation, index, sourceSpanIndex };
    const group = groups.get(key);
    if (group) group.push(item);
    else groups.set(key, [item]);
  });

  type OrderedGroup = EditorialTeachingCitationGroup & {
    orderBucket: number;
    orderSpan: number;
  };
  const result: OrderedGroup[] = ungrouped.map((group) => ({
    ...group,
    orderBucket: group.citationIndex,
    orderSpan: group.citationIndex,
  }));
  for (const items of groups.values()) {
    const orderBucket = Math.min(...items.map((item) => item.index));
    items.sort((left, right) => left.sourceSpanIndex - right.sourceSpanIndex || left.index - right.index);
    const runs: Item[][] = [];
    for (const item of items) {
      const previousRun = runs[runs.length - 1];
      const previous = previousRun?.[previousRun.length - 1];
      if (previous && item.sourceSpanIndex === previous.sourceSpanIndex + 1) previousRun.push(item);
      else runs.push([item]);
    }

    for (const run of runs) {
      const first = run[0].citation;
      const firstRaw = first as CitationWithSourceIdentity;
      const quoteSegments = run.map(({ citation }) =>
        citationQuote(citation, citation as CitationWithSourceIdentity));
      if (quoteSegments.some((segment) => !segment.trim())) continue;
      const quote = quoteSegments.join(' ');
      const starts = run
        .map(({ citation }) => {
          const raw = citation as CitationWithSourceIdentity;
          return citation.playbackStartSeconds
            ?? citation.timestampSeconds
            ?? (typeof raw.start_ms === 'number' && Number.isFinite(raw.start_ms)
              ? raw.start_ms / 1000
              : undefined);
        })
        .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
      const ends = run
        .map(({ citation }) => {
          const raw = citation as CitationWithSourceIdentity;
          const seconds = citation.playbackEndSeconds
            ?? (typeof citation.endMs === 'number' ? citation.endMs / 1000 : undefined);
          return typeof seconds === 'number' && Number.isFinite(seconds)
            ? seconds
            : typeof raw.end_ms === 'number' && Number.isFinite(raw.end_ms)
              ? raw.end_ms / 1000
              : undefined;
        })
        .filter((value): value is number => typeof value === 'number');
      const mergedCitation: Citation = {
        ...first,
        videoId: verifiedVideoId(first, firstRaw),
        quote,
        textSnippet: quote,
        quoteSegments,
        isVerbatim: run.every(({ citation }) => citation.isVerbatim === true),
        rightsCleared: run.every(({ citation }) => citation.rightsCleared === true),
        timestampSeconds: starts.length ? Math.min(...starts) : first.timestampSeconds,
        playbackStartSeconds: starts.length ? Math.min(...starts) : first.playbackStartSeconds,
        playbackEndSeconds: ends.length ? Math.max(...ends) : first.playbackEndSeconds,
        playbackUrl: starts.length
          ? `https://www.youtube.com/watch?v=${verifiedVideoId(first, firstRaw)}&t=${Math.floor(Math.min(...starts))}s`
          : first.playbackUrl,
        speakerVerified: run.every(({ citation }) => citation.speakerVerified === true),
      };
      result.push({
        citation: mergedCitation,
        citationIndex: Math.min(...run.map((item) => item.index)),
        orderBucket,
        orderSpan: run[0].sourceSpanIndex,
      });
    }
  }

  return result
    .sort((left, right) => left.orderBucket - right.orderBucket
      || left.orderSpan - right.orderSpan
      || left.citationIndex - right.citationIndex)
    .map(({ citation, citationIndex }) => ({ citation, citationIndex }));
};
