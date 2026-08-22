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


export type BackendMetadata = Record<string, unknown>;

export interface AIResponse {
  content: string;
  error?: string;
  errorCode?: AIErrorCode;
  intent?: string;
  citations?: string[];
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
      type: 'done';
      intent: string;
      citations: string[];
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
    }
  | { type: 'error'; text: string };

export interface RecordMetricInput {
  type: string;
  value: number;
  userMessageId?: string | null;
  lastMessageId?: string | null;
  sessionId?: string | null;
  tags?: Record<string, string>;
}
