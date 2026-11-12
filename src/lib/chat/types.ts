import { z } from 'zod';

export type AIProvider = 'placeholder' | 'custom';
export type GroundingState = 'grounded' | 'abstained' | 'safety_redirect' | 'system_error';

export interface AIConfig {
  provider: AIProvider;
  endpoint?: string;
  systemPrompt?: string;
  model?: string;
  language?: string;
}

export interface MessagePayload {
  role: 'user' | 'assistant' | 'system';
  content: string;
}
export type ResponsePreferenceMode = 'balanced_guidance' | 'concise' | 'reflective_guidance' | 'teaching_explanation';
export interface ResponsePreferences {
  mode: ResponsePreferenceMode;
  includePractice: boolean;
  includeReflection: boolean;
  actionDepth: 'none' | 'one_step';
}

export type AIErrorCode =
  | 'rate_limited'
  | 'unauthorized'
  | 'server_error'
  | 'timeout'
  | 'network'
  | 'quota_exceeded'
  | 'context_exhausted'
  | 'stream_interrupted'
  | 'unknown';

/** Healing course recommended by the backend (streak-based assignment).
 *  Mirrors `healing_course_service.trigger_payload()` 1:1 — the zod schema is
 *  the runtime guard, the type is derived from it so they can't drift. */
export const recommendedCourseSchema = z.object({
  slug: z.string(),
  signal: z.string(),
  pattern: z.string(),
  reason: z.string(),
});

export type RecommendedCourse = z.infer<typeof recommendedCourseSchema>;
/** A time-bounded event, booking, or schedule link returned from an official source. */
export interface LiveLogisticsEvent {
  event_name: string;
  official_source_url: string;
  booking_url?: string | null;
  verified_at: string;
  expires_at: string;
}

export interface TeachingAttribution {
  label: string;
  source_backed: boolean;
  teacher_name?: string | null;
}

export interface ActionStep {
  title: string;
  instruction: string;
  optional: boolean;
  safety_note?: string | null;
}

export interface GuidancePlan {
  response_mode: string;
  language: string;
  attribution: TeachingAttribution;
  action_step?: ActionStep | null;
  reflection_prompt?: string | null;
}

export interface AnswerEvidence {
  corpus_id: string;
  release_version?: number | null;
  model_policy_id: string;
  evidence_support_label: string;
  source_count: number;
  top_source_score?: number | null;
  citations_verified?: boolean | null;
}

export interface PersonalizationProvenance {
  used: boolean;
  profile_preferences?: boolean;
  personal_memory?: boolean;
  private_graph_links?: number;
}


export type BackendMetadata = Record<string, unknown>;

export type EditorialSetStatus = 'supported' | 'partial' | 'conflicted' | 'insufficient';
export type EditorialFacetCoverage = 'direct' | 'indirect' | 'absent';
export interface EditorialSetMetadata {
  status: EditorialSetStatus;
  primary_intent?: string;
  candidate_facets?: string[];
  teacher_scope?: string | null;
  facet_coverage?: Record<string, EditorialFacetCoverage>;
  candidate_contexts?: number;
  selected_contexts?: number;
  planner_version?: string;
  selector_version?: string;
}

/** A single cited source. `title` is the real video/article title resolved
 *  server-side from the retrieved document; null/absent for sources the
 *  backend could not resolve a title for (renderers fall back to the domain). */
export interface Citation {
  url: string;
  /** Canonical source video ID when supplied by a first-person citation. */
  videoId?: string;
  teacherId?: string;
  speakerId?: string;
  parentUnitId?: string;
  sourceSpanId?: string;
  sourceSpanIndex?: number;
  /** True only when this exact citation body is source-verbatim. */
  isVerbatim?: boolean;
  /** True only when the rights gate cleared this exact source span. */
  rightsCleared?: boolean;
  /** Exact child-span text nodes used by grouped editorial teaching cards. */
  quoteSegments?: string[];
  startMs?: number;
  endMs?: number;
  title?: string | null;
  quote?: string;
  /** BCP-47 language of the quote, when the clip record says so (NEW-A11Y-5). Never inferred. */
  language?: string;
  channel_name?: string;
  source?: string;
  speaker?: string;
  /** Whether the speaker was verified against official teacher voiceprints.
   *  Falsy means the speaker label is model-inferred, not payload-grounded —
   *  renderers must downgrade bare teacher names (see resolveAttributionLabel). */
  speakerVerified?: boolean;
  /** `transcript_status` / `caption_status` from the payload. Absent => the UI labels the
   *  quote "Auto-transcript"; only an explicit reviewed status drops the label. */
  transcriptStatus?: string;
  /** Second offset into the source video, when the backend has one. 0 is a
   *  valid, playable start — only absence (undefined) means "no timestamp". */
  timestampSeconds?: number;
  textSnippet?: string;
  /** Clip start minus the 0.25 s playback pad, floored at 0.
   *  Prefer this over timestampSeconds for playback when present. */
  playbackStartSeconds?: number;
  /** Clip end plus the 0.25 s pad, capped at the video duration. */
  playbackEndSeconds?: number;
  /** YouTube deep link built from playbackStartSeconds. */
  playbackUrl?: string;
  personalized_for?: boolean;
  /** @deprecated legacy camelCase alias — read via `isPersonalizedCitation`. */
  personalizedFor?: boolean;
}

const normalizeQuoteSegments = (value: unknown): string[] | undefined => {
  if (!Array.isArray(value)) return undefined;
  const segments: string[] = [];
  let totalLength = 0;
  for (const segment of value) {
    if (
      typeof segment !== 'string'
      || !segment.trim()
      || segment.length > 12000
      || segments.length >= 20
      || totalLength + segment.length > 25000
    ) return undefined;
    segments.push(segment);
    totalLength += segment.length;
  }
  return segments.length > 0 ? segments : undefined;
};

/** Canonical read of the backend personalize flag. `personalized_for`
 *  (snake_case wire shape) is the single source of truth; `personalizedFor`
 *  is a compat alias. Prefer this over ad-hoc `||` checks so renames land
 *  in one place. */
export const isPersonalizedCitation = (
  c: Pick<Citation, 'personalized_for' | 'personalizedFor'> | undefined | null,
): boolean => c?.personalized_for === true || c?.personalizedFor === true;

/** Maps the backend's snake_case citation wire shape (`timestamp_seconds`,
 *  `text_snippet`, plus the existing fields) to the camelCase `Citation`
 *  shape the UI reads. A bare string citation (URL-only, some fallback
 *  paths) is passed through as `{ url }`. Non-finite/absent timestamps stay
 *  undefined rather than becoming a fabricated 0. */
export const normalizeCitations = (raw: unknown): Citation[] => {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((entry): Citation | null => {
      if (typeof entry === 'string') {
        return entry ? { url: entry } : null;
      }
      if (!entry || typeof entry !== 'object') return null;
      const c = entry as Record<string, unknown>;
      const url = c.url ?? c.source_url;
      if (typeof url !== 'string' || !url) return null;
      let ts = typeof c.timestamp_seconds === 'number' && Number.isFinite(c.timestamp_seconds)
        ? c.timestamp_seconds
        : typeof c.timestampSeconds === 'number' && Number.isFinite(c.timestampSeconds)
        ? c.timestampSeconds
        : undefined;
      if (ts === undefined) {
        const ms = c.start_ms ?? c.startMs;
        if (typeof ms === 'number' && Number.isFinite(ms)) {
          ts = Math.floor(ms / 1000);
        }
      }
      const pbs = c.playback_start_seconds ?? c.playbackStartSeconds ?? ts;
      const pbe = c.playback_end_seconds ?? c.playbackEndSeconds;
      const sv = c.speaker_verified ?? c.speakerVerified;
      const verbatim = c.is_verbatim ?? c.isVerbatim;
      const rightsCleared = c.rights_cleared ?? c.rightsCleared;
      const rawTs = c.transcript_status ?? c.transcriptStatus ?? c.caption_status ?? c.captionStatus;
      const pf = typeof c.personalized_for === 'boolean' ? c.personalized_for : typeof c.personalizedFor === 'boolean' ? c.personalizedFor : undefined;
      let playbackUrl = (c.playback_url as string | undefined) ?? (c.playbackUrl as string | undefined);
      if (!playbackUrl && url && ts !== undefined) {
        try {
          const u = new URL(url);
          u.searchParams.set('t', `${ts}s`);
          playbackUrl = u.toString();
        } catch {
          // Malformed source URL: leave playbackUrl unset rather than guess one.
        }
      }
      return {
        url,
        videoId: typeof c.video_id === 'string' ? c.video_id : typeof c.videoId === 'string' ? c.videoId : undefined,
        teacherId: typeof c.teacher_id === 'string'
          ? c.teacher_id
          : typeof c.guru_id === 'string'
            ? c.guru_id
            : typeof c.teacherId === 'string'
              ? c.teacherId
              : undefined,
        speakerId: typeof c.speaker_id === 'string' ? c.speaker_id : typeof c.speakerId === 'string' ? c.speakerId : undefined,
        parentUnitId: typeof c.parent_unit_id === 'string' ? c.parent_unit_id : typeof c.parentUnitId === 'string' ? c.parentUnitId : undefined,
        sourceSpanId: typeof c.source_span_id === 'string' ? c.source_span_id : typeof c.sourceSpanId === 'string' ? c.sourceSpanId : undefined,
        sourceSpanIndex: typeof (c.source_span_index ?? c.sourceSpanIndex) === 'number' && Number.isInteger(c.source_span_index ?? c.sourceSpanIndex) && Number(c.source_span_index ?? c.sourceSpanIndex) >= 0 ? Number(c.source_span_index ?? c.sourceSpanIndex) : undefined,
        isVerbatim: typeof verbatim === 'boolean' ? verbatim : undefined,
        rightsCleared: typeof rightsCleared === 'boolean' ? rightsCleared : undefined,
        quoteSegments: normalizeQuoteSegments(c.quote_segments ?? c.quoteSegments),
        startMs: typeof (c.start_ms ?? c.startMs) === 'number' && Number.isFinite(c.start_ms ?? c.startMs) ? Number(c.start_ms ?? c.startMs) : undefined,
        endMs: typeof (c.end_ms ?? c.endMs) === 'number' && Number.isFinite(c.end_ms ?? c.endMs) ? Number(c.end_ms ?? c.endMs) : undefined,
        title: (c.title as string | null | undefined) ?? undefined,
        quote: (c.quote as string | undefined) ?? (c.verbatim_text as string | undefined) ?? undefined,
        // Only an explicit clip language; never the UI language (D-PA11Y4 decides the backend field).
        language: typeof (c.quote_language ?? c.quoteLanguage) === 'string' && String(c.quote_language ?? c.quoteLanguage).trim() ? String(c.quote_language ?? c.quoteLanguage) : undefined,
        channel_name: (c.channel_name as string | undefined) ?? undefined,
        source: (c.source as string | undefined) ?? undefined,
        speaker: (c.speaker as string | null | undefined) ?? undefined,
        speakerVerified: typeof sv === 'boolean' ? sv : undefined,
        transcriptStatus: typeof rawTs === 'string' && rawTs.trim() ? rawTs : undefined,
        timestampSeconds: ts,
        textSnippet: (c.text_snippet as string | null | undefined) ?? (c.textSnippet as string | undefined) ?? (c.verbatim_text as string | undefined) ?? undefined,
        playbackStartSeconds: typeof pbs === 'number' && Number.isFinite(pbs) ? pbs : undefined,
        playbackEndSeconds: typeof pbe === 'number' && Number.isFinite(pbe) ? pbe : undefined,
        playbackUrl: playbackUrl ?? undefined,
        personalized_for: pf,
        personalizedFor: pf,
      };
    })
    .filter((c): c is Citation => c !== null);
};

/** Bare teacher-name attribution (what the downgrade rule guards). */
const TEACHER_NAME_RE = /\bsri\s+(preetha|krishna)ji\b/i;

/** Placeholder-ish source values that carry no provenance ("Unknown Channel"). */
const UNKNOWN_SOURCE_RE = /^\s*(unknown|n\/a|none|-)\b/i;

export interface AttributionInput {
  speaker?: string | null;
  speakerVerified?: boolean | null;
  channelName?: string | null;
  channel_name?: string | null;
  source?: string | null;
}

/** Presentation rule for citation speaker labels (2026-10-04 eval F-E/Q2:
 *  a third-party vlog clip was served as bare "Sri Krishnaji" with
 *  speaker_verified=null + title=null).
 *
 *  - Verified citations (`speakerVerified === true`) render byte-identical.
 *  - A bare teacher name with falsy verification is never kept, even on a
 *    teacher-owned channel (owner ruling 2026-10-16: host and guest speech share
 *    those channels); it is downgraded to `shared in <channel>` (known source)
 *    or `unverified clip` (unknown source) — never a bare "Sri <Name>".
 *  - Non-teacher speakers pass through untouched; the rule guards teacher
 *    names, it does not invent them. Idempotent: downgraded labels never
 *    match TEACHER_NAME_RE, so re-applying is a no-op. */
export const resolveAttributionLabel = (c: AttributionInput): string | undefined => {
  const speaker = (c.speaker ?? '').trim();
  if (!speaker) return undefined;
  if (c.speakerVerified === true) return speaker;
  if (!TEACHER_NAME_RE.test(speaker)) return speaker;
  const channel = (c.channelName ?? c.channel_name ?? c.source ?? '').trim();
  if (channel && !UNKNOWN_SOURCE_RE.test(channel)) return `shared in ${channel}`;
  return 'unverified clip';
};


export interface TeachingPreview {
  title: string;
  teacher?: string | null;
  url?: string | null;
  excerpt?: string | null;
  audio_slice_url?: string | null;
  audio_start_ms?: number | null;
}

export interface AIResponse {
  content: string;
  error?: string;
  errorCode?: AIErrorCode;
  /** HTTP status of a failed response, when known (lets the error card
   *  distinguish a 503 shed from other 5xx). */
  status?: number;
  intent?: string;
  citations?: Citation[];
  meditationStep?: number;
  blocked?: boolean;
  blockReason?: string;
  proactiveSereneMind?: ProactiveSereneMindTrigger | null;
  followUpSuggestions?: string[];
  recommendedCourse?: RecommendedCourse | null;
  /** Official-only schedule or booking results, time-bounded by the backend. */
  liveLogisticsEvents?: LiveLogisticsEvent[];
  guidancePlan?: GuidancePlan | null;
  answerEvidence?: AnswerEvidence | null;
  personalizationProvenance?: PersonalizationProvenance | null;
  groundingState?: GroundingState;
  faithfulnessScore?: number | null;
  relevancyScore?: number | null;
  hallucinationFlag?: boolean | null;
  verification?: BackendMetadata | null;
  citationsVerified?: boolean | null;
  orphanCitationsStripped?: boolean | null;
  releaseManifest?: BackendMetadata | null;
  provenanceManifest?: BackendMetadata | null;
  aiProvenance?: BackendMetadata | null;
  traceId?: string | null;
  latencyMs?: number | null;
  modelUsed?: string | null;
  modelProvider?: string | null;
  queryTier?: string | null;
  isFirstPersonAbstain?: boolean | null;
  routeDecision?: string | null;
  /** Platform copy that accompanies a served verbatim clip but is not the
   *  teacher's words (compassion framing, relationship/addiction safety
   *  boundaries, the human support line). Rendered as its own block after the
   *  answer; never concatenated into the answer body. */
  safetyNotices?: string[];
  /** Seconds the client should wait before retrying (429 responses). */
  retryAfterSeconds?: number;
  /** Anonymous quota state from a 429 quota_exceeded response, for the "X of Y used" caption. */
  quotaRemaining?: number;
  quotaTotalLimit?: number;
}

/** Shape of the proactive Serene Mind trigger object returned by the backend */
import type { MeditationStep } from '@/components/meditation/meditationSteps';

export interface ProactiveSereneMindTrigger {
  triggered: boolean;
  level?: string;
  confidence?: number;
  signals?: string[];
  suggested_response?: string;
  /** Teaching shown before any practice invitation; never auto-opens the player. */
  teachings_prelude?: string;
  /** Practice must be explicitly accepted by the user after reading the teaching. */
  requires_consent?: boolean;
  /** Short reason used by the practice card, not a model-generated command. */
  offer_reason?: string;
  /** Approximate guided-practice duration in seconds. */
  duration_seconds?: number;
  /** Teachings-infused custom meditation steps (alternative to default Serene Mind) */
  custom_meditation?: {
    source_teaching?: string;
    steps: MeditationStep[];
  };
}

/** Streaming chunk: either a content token, a pipeline status update, or final metadata */
export type StreamChunk =
  | { type: 'token'; text: string }
  | { type: 'final'; text: string }
  | { type: 'status'; text: string; jobId?: string }
  | {
      type: 'stage';
      node: string;
      step: number;
      total_steps: number;
      strategy?: string;
    }
  | {
      type: 'teaching_preview';
      items: TeachingPreview[];
    }
  | {
      type: 'done';
      intent: string;
      citations: Citation[];
      meditationStep: number;
      blocked?: boolean;
      blockReason?: string | null;
      proactiveSereneMind?: ProactiveSereneMindTrigger | null;
      followUpSuggestions?: string[];
      confidenceScore?: number | null;
      /** E3.2 one-line explainable reason (optional, forward-compat). */
      confidenceReason?: string | null;
      /** Streak-based healing course assignment from the backend. */
      recommendedCourse?: RecommendedCourse | null;
      /** Official-only schedule or booking results, time-bounded by the backend. */
      liveLogisticsEvents?: LiveLogisticsEvent[];
  guidancePlan?: GuidancePlan | null;
      answerEvidence?: AnswerEvidence | null;
      personalizationProvenance?: PersonalizationProvenance | null;
      groundingState?: GroundingState;
      faithfulnessScore?: number | null;
      relevancyScore?: number | null;
      hallucinationFlag?: boolean | null;
      verification?: BackendMetadata | null;
      citationsVerified?: boolean | null;
      orphanCitationsStripped?: boolean | null;
      releaseManifest?: BackendMetadata | null;
      provenanceManifest?: BackendMetadata | null;
      aiProvenance?: BackendMetadata | null;
      traceId?: string | null;
      latencyMs?: number | null;
      modelUsed?: string | null;
      modelProvider?: string | null;
      queryTier?: string | null;
      isFirstPersonAbstain?: boolean | null;
      routeDecision?: string | null;
      safetyNotices?: string[];
    }
  | { type: 'error'; text: string; errorCode?: AIErrorCode };

export interface RecordMetricInput {
  type: string;
  value: number;
  userMessageId?: string | null;
  lastMessageId?: string | null;
  sessionId?: string | null;
  tags?: Record<string, string>;
}
