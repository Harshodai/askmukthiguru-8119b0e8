import type { DiscourseCitation } from '@/components/chat/CitationCard';
import type { FirstPersonCitation } from './firstPersonService';

/**
 * Maps a first-person verbatim citation onto CitationCard's DiscourseCitation
 * shape so the existing citation UI (speaker, exact-second embed, verbatim
 * quote) can be reused as-is.
 *
 * `timestamp_seconds: 0` is a valid, playable start — assign it directly,
 * never `|| 0` / truthiness-check it away.
 */
export function mapFirstPersonCitationToDiscourseCitation(
  citation: FirstPersonCitation,
  index: number,
): DiscourseCitation {
  return {
    index,
    url: citation.playback_url || citation.source_url || citation.video_url,
    speaker: citation.speaker,
    startTimestamp: citation.timestamp_seconds,
    playbackStartSeconds: citation.playback_start_seconds,
    playbackEndSeconds: citation.playback_end_seconds,
    endTimestamp: citation.end_ms / 1000,
    quote: citation.verbatim_text,
  };
}
