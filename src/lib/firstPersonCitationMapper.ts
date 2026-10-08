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
    // First-person clips come from the voice-verified clip index — the only
    // route allowed to name a speaker without an explicit flag — so mark them
    // verified to keep the attribution-downgrade rule (resolveAttributionLabel)
    // byte-identical here. Unverified chat citations carry no such guarantee.
    // An explicit `speaker_verified: false` from the payload always wins.
    speakerVerified: (citation as { speaker_verified?: boolean | null }).speaker_verified !== false,
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
