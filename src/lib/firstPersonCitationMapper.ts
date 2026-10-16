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
    // Verified only when the backend says so: only 665 of 3,236 v7 clips (685 of 1,801 v8)
    // carry a voice check, so a missing or false flag must render as "unverified clip".
    speakerVerified: citation.speaker_verified === true,
    startTimestamp: citation.timestamp_seconds,
    playbackStartSeconds: citation.playback_start_seconds,
    playbackEndSeconds: citation.playback_end_seconds,
    endTimestamp: citation.end_ms / 1000,
    quote: citation.verbatim_text,
    // `transcript_status` ("auto-transcript" | "reviewed") wins over legacy `caption_status`.
    transcriptStatus:
      (citation as { transcript_status?: string | null }).transcript_status || citation.caption_status,
  };
}
