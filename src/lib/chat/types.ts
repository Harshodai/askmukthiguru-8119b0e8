export type AIProvider = 'placeholder' | 'custom';

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

export type AIErrorCode =
  | 'rate_limited'
  | 'unauthorized'
  | 'server_error'
  | 'timeout'
  | 'network'
  | 'unknown';

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
}

/** Shape of the proactive Serene Mind trigger object returned by the backend */
import type { MeditationStep } from '@/components/meditation/meditationSteps';

export interface ProactiveSereneMindTrigger {
  triggered: boolean;
  level?: string;
  confidence?: number;
  signals?: string[];
  suggested_response?: string;
  /** Krishnaji/Preethaji teaching streamed as a guru message before the modal opens */
  teachings_prelude?: string;
  /** Teachings-infused custom meditation steps (alternative to default Serene Mind) */
  custom_meditation?: {
    source_teaching?: string;
    steps: MeditationStep[];
  };
}

/** Streaming chunk: either a content token, a pipeline status update, or final metadata */
export type StreamChunk =
  | { type: 'token'; text: string }
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
