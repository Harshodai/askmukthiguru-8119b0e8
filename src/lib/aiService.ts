import { guruResponses } from './chatStorage';
import { supabase } from '@/integrations/supabase/client';

export type AIProvider = 'placeholder' | 'custom';

let isRefreshingToken = false;
let refreshTokenPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (isRefreshingToken && refreshTokenPromise) {
    return refreshTokenPromise;
  }

  isRefreshingToken = true;
  refreshTokenPromise = (async () => {
    try {
      const { data, error } = await supabase.auth.refreshSession();
      if (error || !data.session?.access_token) {
        console.error('Token refresh failed:', error);
        return null;
      }
      return data.session.access_token;
    } catch (err) {
      console.error('Token refresh error:', err);
      return null;
    } finally {
      isRefreshingToken = false;
      refreshTokenPromise = null;
    }
  })();
  return refreshTokenPromise;
}

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
}

/** Shape of the proactive Serene Mind trigger object returned by the backend */
export interface ProactiveSereneMindTrigger {
  triggered: boolean;
  level?: string;
  confidence?: number;
  signals?: string[];
  suggested_response?: string;
  /** Krishnaji/Preethaji teaching streamed as a guru message before the modal opens */
  teachings_prelude?: string;
}

// ── Backend health check (cached for 30s, non-blocking) ──
let _healthLastChecked = 0;
let _healthStatus: 'unknown' | 'up' | 'down' = 'unknown';

async function checkBackendHealth(endpoint: string): Promise<'up' | 'down'> {
  const now = Date.now();
  if (now - _healthLastChecked < 30_000) return _healthStatus as 'up' | 'down';
  _healthLastChecked = now;
  try {
    const baseUrl = new URL(endpoint).origin;
    const resp = await fetch(`${baseUrl}/api/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(5_000),
    });
    _healthStatus = resp.ok ? 'up' : 'down';
  } catch {
    _healthStatus = 'down';
  }
  return _healthStatus;
}

// Auto-detect backend URL:
//   1. VITE_BACKEND_URL (self-hosted FastAPI) — preferred for full RAG
//   2. Lovable Cloud edge function `guru-chat` — cloud fallback (LLM-only, no RAG yet)
//   3. Relative `/api/chat` — last resort, requires reverse-proxy
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
const EDGE_CHAT_URL = SUPABASE_URL
  ? `${SUPABASE_URL.replace(/\/$/, '')}/functions/v1/guru-chat`
  : '';
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '';
const DEFAULT_ENDPOINT = BACKEND_URL
  ? `${BACKEND_URL}/api/chat`
  : EDGE_CHAT_URL || '/api/chat';

const getInitialLanguage = (): string => {
  if (typeof window === 'undefined') return 'en';
  try {
    const raw = localStorage.getItem('askmukthiguru_profile');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.preferredLanguage) {
        return parsed.preferredLanguage;
      }
    }
  } catch {
    // ignore
  }
  return 'en';
};

let currentConfig: AIConfig = {
  provider: 'custom',
  endpoint: DEFAULT_ENDPOINT,
  language: getInitialLanguage(),
  systemPrompt: `You are a spiritual AI companion embodying the wisdom of Sri Preethaji & Sri Krishnaji.
Your purpose is to guide seekers toward their "beautiful state" - a state of consciousness free from suffering.
You speak with warmth, compassion, and profound insight. You never claim to replace professional mental health support.
When someone is in deep distress, gently encourage them to seek professional help while offering comfort.`,
};


export const setAIProvider = (config: Partial<AIConfig>): void => {
  currentConfig = { ...currentConfig, ...config };
};

export const getAIConfig = (): AIConfig => {
  return { ...currentConfig };
};

export const setLanguage = (language: string): void => {
  currentConfig.language = language;
  if (typeof window !== 'undefined') {
    try {
      const raw = localStorage.getItem('askmukthiguru_profile');
      if (raw) {
        const parsed = JSON.parse(raw);
        parsed.preferredLanguage = language;
        localStorage.setItem('askmukthiguru_profile', JSON.stringify(parsed));
      }
    } catch {
      // ignore
    }
  }
};

const getPlaceholderResponse = (): string => {
  const randomIndex = Math.floor(Math.random() * guruResponses.length);
  return guruResponses[randomIndex];
};

const httpStatusToErrorCode = (status: number): AIErrorCode => {
  if (status === 401 || status === 403) return 'unauthorized';
  if (status === 429) return 'rate_limited';
  if (status >= 500) return 'server_error';
  return 'unknown';
};

interface RecordMetricInput {
  type: string;
  value: number;
  userMessageId?: string | null;
  lastMessageId?: string | null;
  sessionId?: string | null;
  tags?: Record<string, string>;
}

/**
 * Best-effort client-side telemetry. Strictly validates that `userMessageId`
 * is present before invoking the edge function. Silently no-ops on missing IDs
 * or transport failure — telemetry must never break the chat UX.
 */
async function recordMetric(metric: RecordMetricInput): Promise<void> {
  const userMessageId = metric.userMessageId?.trim();
  if (!userMessageId) return; // hard guard — never call telemetry without an id
  try {
    await supabase.functions.invoke('telemetry', {
      body: {
        user_message_id: userMessageId,
        last_message_id: metric.lastMessageId ?? null,
        session_id: metric.sessionId ?? null,
        metric_type: metric.type,
        metric_value: metric.value,
        tags: metric.tags ?? {},
      },
    });
  } catch {
    // swallow — telemetry is fire-and-forget
  }
}

/**
 * Streaming variant of sendMessage. Yields content chunks as they arrive
 * from an SSE/chunked endpoint. Falls back by throwing if streaming is
 * unavailable (caller should catch and use sendMessage instead).
 */
/** Streaming chunk: either a content token, a pipeline status update, or final metadata */
export type StreamChunk =
  | { type: 'token'; text: string }
  | { type: 'status'; text: string }
  | { type: 'done'; intent: string; citations: string[]; meditationStep: number; blocked?: boolean; blockReason?: string | null; proactiveSereneMind?: ProactiveSereneMindTrigger | null }
  | { type: 'error'; text: string };

export async function* sendMessageStreaming(
  messages: MessagePayload[],
  userMessage: string,
  meditationStep: number = 0,
  summary?: string,
  sessionId?: string,
  /** Unix ms of last completed Serene Mind session (from localStorage) */
  lastSereneMindAt?: number | null,
  /** Pre-fetched relevant memories, injected into guru-chat as seeker_context. */
  seekerContext?: string,
  /** Optional AbortSignal — when aborted, fetch + reader exit cleanly. */
  signal?: AbortSignal,
  /** Stable id of the user message being sent — required for telemetry. */
  userMessageId?: string,
  /** Stable id of the previous assistant message (if any) — for telemetry context. */
  lastMessageId?: string,
): AsyncGenerator<StreamChunk> {
  const { provider, endpoint, systemPrompt } = currentConfig;

  // Streaming only works for the custom backend with SSE support
  if (provider !== 'custom' || !endpoint) {
    const err = new Error('Streaming not available for this provider');
    (err as any).errorCode = 'unknown';
    throw err;
  }

  const streamEndpoint = endpoint.replace(/\/?$/, '/stream');
  const trimmedMessages = messages.slice(-20);

  const buildBody = () => JSON.stringify({
    messages: [
      { role: 'system', content: systemPrompt },
      ...(summary ? [{ role: 'system' as const, content: `SUMMARY OF PREVIOUS CONVERSATION: ${summary}` }] : []),
      ...trimmedMessages,
    ],
    user_message: userMessage,
    meditation_step: meditationStep,
    session_id: sessionId,
    language: currentConfig.language || 'en',
    stream: true,
    ...(lastSereneMindAt != null
      ? { last_serene_mind_at: lastSereneMindAt / 1000 }
      : {}),
    ...(seekerContext ? { seeker_context: seekerContext } : {}),
  });

  const doFetch = (tok: string | undefined) =>
    fetch(streamEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
      },
      body: buildBody(),
      signal,
    });

  const { data: { session } } = await supabase.auth.getSession();
  let token = session?.access_token;

  const startMs = Date.now();
  let response = await doFetch(token);

  // Auto-retry on 401 with a refreshed token (mirrors non-stream path)
  if (response.status === 401 && token) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      token = refreshed;
      response = await doFetch(token);
    }
  }

  if (!response.ok || !response.body) {
    let errorDetail = `Streaming failed: ${response.status}`;
    try {
      const errorData = await response.clone().json();
      if (errorData?.detail) {
        errorDetail += ` - ${errorData.detail}`;
      }
    } catch {
      // Ignore JSON parse errors
    }
    const error = new Error(errorDetail);
    (error as any).status = response.status;
    (error as any).errorCode = httpStatusToErrorCode(response.status);
    throw error;
  }

  // Guard against Vite/SPA HTML fallback (when backend isn't running, the dev
  // server returns index.html for /api/chat/stream, which the SSE parser will
  // happily hang on). Detect it early and surface a clear error.
  const contentType = response.headers?.get?.('content-type') || '';
  if (contentType && !contentType.includes('text/event-stream') && !contentType.includes('application/x-ndjson')) {
    const err = new Error(
      `Backend not reachable at ${streamEndpoint} (got content-type: ${contentType}). ` +
      `Set VITE_BACKEND_URL to your FastAPI URL.`,
    );
    (err as any).errorCode = 'network';
    throw err;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = 'message'; // tracks the SSE event type

  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const sseLines = buffer.split('\n');
      buffer = sseLines.pop() || '';
      for (const line of sseLines) {
        // Parse SSE event type lines
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
          continue;
        }
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6);
        if (payload.trim() === '[DONE]') {
          await recordMetric({ type: 'ai_response_time', value: Date.now() - startMs, tags: { provider: 'custom', endpoint: 'stream' } });
          return;
        }

        // Yield status events as pipeline step updates
        if (currentEvent === 'status') {
          yield { type: 'status', text: payload.trim() };
          currentEvent = 'message'; // reset for next event
          continue;
        }

        // Handle done event with final metadata (intent, citations, meditation_step)
        if (currentEvent === 'done') {
          currentEvent = 'message';
          try {
            const meta = JSON.parse(payload);
            yield {
              type: 'done',
              intent: meta.intent ?? 'CASUAL',
              citations: meta.citations ?? [],
              meditationStep: meta.meditation_step ?? 0,
              blocked: meta.blocked ?? false,
              blockReason: meta.block_reason ?? null,
              proactiveSereneMind: meta.proactive_serene_mind ?? null,
            };
          } catch {
            // Ignore malformed done payload
          }
          continue;
        }

        // Handle error events
        if (currentEvent === 'error') {
          currentEvent = 'message';
          yield { type: 'error', text: payload.trim() };
          continue;
        }

        // Yield token events as content — unescape \\n back to real newlines
        currentEvent = 'message'; // reset
        try {
          const parsed = JSON.parse(payload);
          const chunk = parsed.choices?.[0]?.delta?.content ?? parsed.token ?? parsed.content ?? '';
          if (chunk) yield { type: 'token', text: chunk.replace(/\\n/g, '\n') };
        } catch {
          // Non-JSON SSE line — yield raw text (unescape newlines)
          if (payload) yield { type: 'token', text: payload.replace(/\\n/g, '\n') };
        }
      }
    }
    await recordMetric({ type: 'ai_response_time', value: Date.now() - startMs, tags: { provider: 'custom', endpoint: 'stream' } });
  } finally {
    reader.releaseLock();
  }
}


export const sendMessage = async (
  messages: MessagePayload[],
  userMessage: string,
  meditationStep: number = 0,
  summary?: string,
  sessionId?: string,
  /** Unix ms of last completed Serene Mind session (from localStorage) */
  lastSereneMindAt?: number | null,
  seekerContext?: string,
): Promise<AIResponse> => {
  const { provider, endpoint, systemPrompt } = currentConfig;

  if (provider === 'placeholder') {
    await new Promise((resolve) => setTimeout(resolve, 1000 + Math.random() * 1000));
    return { content: getPlaceholderResponse() };
  }

  if (provider === 'custom' && endpoint) {
    const trimmedMessages = messages.slice(-20);
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;

    const buildBody = () => JSON.stringify({
      messages: [
        { role: 'system', content: systemPrompt },
        ...(summary ? [{ role: 'system' as const, content: `SUMMARY OF PREVIOUS CONVERSATION: ${summary}` }] : []),
        ...trimmedMessages,
      ],
      user_message: userMessage,
      meditation_step: meditationStep,
      session_id: sessionId,
      language: currentConfig.language || 'en',
      ...(lastSereneMindAt != null
        ? { last_serene_mind_at: lastSereneMindAt / 1000 }
        : {}),
      ...(seekerContext ? { seeker_context: seekerContext } : {}),
    });

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120_000);

    const doFetch = (signal?: AbortSignal) =>
      fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: buildBody(),
        signal: signal || controller.signal,
      });

    const startMs = Date.now();
    try {
      let response = await doFetch();

      if (!response.ok) {
        if (response.status === 504) {
          return {
            content: '',
            error: 'The Guru took too long to respond. Please retry your question.',
            errorCode: 'timeout',
          };
        }

        // Auto-retry on 401 with token refresh
        if (response.status === 401 && token) {
          const newToken = await refreshAccessToken();
          if (newToken) {
            const retryResponse = await fetch(endpoint, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${newToken}`,
              },
              body: buildBody(),
            });

            if (retryResponse.ok) {
              response = retryResponse;
            } else {
              return {
                content: '',
                error: `API error: ${retryResponse.status}`,
                errorCode: httpStatusToErrorCode(retryResponse.status),
              };
            }
          }
        } else {
          const errorCode = httpStatusToErrorCode(response.status);
          let errorDetail = `API error: ${response.status}`;
          try {
            const errorData = await response.clone().json();
            if (errorData?.detail) {
              errorDetail += ` - ${errorData.detail}`;
            }
          } catch {
            // Ignore JSON parse errors
          }
          return {
            content: '',
            error: errorDetail,
            errorCode,
          };
        }
      }

      const data = await response.json();
      await recordMetric({ type: 'ai_response_time', value: Date.now() - startMs, tags: { provider: 'custom', endpoint: 'non-stream' } });
      return {
        content: data.response || data.choices?.[0]?.message?.content || data.content,
        intent: data.intent,
        citations: data.citations || [],
        meditationStep: data.meditation_step || 0,
        blocked: data.blocked || false,
        blockReason: data.block_reason,
        proactiveSereneMind: data.proactive_serene_mind ?? null,
      };
    } catch (err: any) {
      let code: AIErrorCode = 'network';
      let message = err?.message || 'Connection failed';
      if (err?.name === 'AbortError') {
        code = 'timeout';
        message = 'The request timed out before the Guru could respond.';
      } else if (err instanceof TypeError && /fetch|network/i.test(message)) {
        code = 'network';
        // Fire-and-forget health check to update cached status for next request
        checkBackendHealth(endpoint);
        message = _healthStatus === 'down'
          ? 'Cannot reach the Guru — backend is unavailable. Please try again later.'
          : 'Network or backend is unreachable. Please check your connection.';
      } else if (err instanceof DOMException && err.name === 'NotFoundError') {
        code = 'unknown';
        message = 'Could not resolve the backend server address.';
      }
      return {
        content: '',
        error: message,
        errorCode: code,
      };
    } finally {
      clearTimeout(timeoutId);
    }
  }

  // OpenAI direct client-side calls removed for security.
  // API keys must never be stored or used in the browser.
  // Use a server-side proxy (Edge Function) if OpenAI integration is needed.

  // Final fallback: no provider matched or unreachable code path.
  // Return empty content so ChatInterface renders the error state.
  return { content: '', errorCode: 'unknown' as AIErrorCode };
};

export const generateSummary = async (messages: MessagePayload[]): Promise<string> => {
  const { provider, endpoint } = currentConfig;
  if (provider !== 'custom' || !endpoint) return '';

  try {
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        messages: [
          {
            role: 'system',
            content: 'You are a summarizer. Provide a concise 2-3 sentence summary of the key spiritual insights and user concerns discussed in this conversation history. Focus on maintaining teaching continuity.'
          },
          ...messages.slice(-10),
        ],
        user_message: 'Summarize our conversation so far.',
      }),
    });

    if (!response.ok) return '';
    const data = await response.json();
    return data.response || data.choices?.[0]?.message?.content || data.content || '';
  } catch (error) {
    console.error('Failed to generate summary:', error);
    return '';
  }
};

export const generateConversationTitle = async (firstUserMessage: string): Promise<string> => {
  const { provider, endpoint } = currentConfig;
  const fallback = firstUserMessage.trim().slice(0, 48);
  if (provider !== 'custom' || !endpoint || !fallback) return fallback || 'New conversation';

  try {
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        messages: [
          {
            role: 'system',
            content: 'Create a concise chat title. Return only the title, no quotes, no punctuation at the end.',
          },
        ],
        user_message: `Title this conversation in 3 to 6 words: ${firstUserMessage}`,
        language: 'en',
      }),
    });

    if (!response.ok) return fallback;
    const data = await response.json();
    const raw = String(data.response || data.choices?.[0]?.message?.content || data.content || fallback);
    const title = raw
      .split('\n')[0]
      .replace(/^["'`]+|["'`.]+$/g, '')
      .trim();
    return title.length > 60 ? `${title.slice(0, 57)}...` : title || fallback;
  } catch {
    return fallback;
  }
};


export const checkConnection = async (): Promise<{ connected: boolean; mode: string }> => {
  const { provider, endpoint } = currentConfig;

  if (provider === 'placeholder') {
    return { connected: true, mode: 'Offline Mode' };
  }

  if (provider === 'custom' && endpoint) {
    // Edge-function endpoints don't expose /api/health — treat as connected.
    if (endpoint.includes('/functions/v1/')) {
      return { connected: true, mode: 'Connected to Guru' };
    }
    try {
      const healthUrl = endpoint.startsWith('http')
        ? new URL('/api/health', new URL(endpoint).origin).href
        : '/api/health';

      const response = await fetch(healthUrl);
      return { connected: response.ok, mode: response.ok ? 'Connected to Guru' : 'Reconnecting…' };
    } catch (e) {
      console.error("Health check failed:", e);
      return { connected: false, mode: 'Reconnecting…' };
    }
  }


  return { connected: true, mode: 'Cloud Mode' };
};

export const submitFeedbackToBackend = async (payload: {
  query: string;
  answer: string;
  rating: number;
  comment?: string;
}) => {
  const { provider, endpoint } = currentConfig;
  if (provider !== 'custom' || !endpoint) return;

  try {
    // Usually endpoint is /api/chat. We replace it with /api/feedback.
    const feedbackEndpoint = endpoint.replace(/\/chat\/?$/, '/feedback');
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;

    await fetch(feedbackEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    console.error('Failed to submit feedback to server:', error);
  }
};

/**
 * Fire-and-forget: insert a memory-extraction job into pending_extractions
 * for the Supabase Edge Function to drain.  Runs silently, never blocks
 * the chat, and swallows all errors.
 */
export const queueMemoryExtraction = async (payload: {
  userMessage: string;
  assistantMessage: string;
  conversationId?: string;
}): Promise<void> => {
  try {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    await supabase.from('pending_extractions').insert({
      user_id: session.user?.id,
      payload: {
        user_message: payload.userMessage,
        assistant_message: payload.assistantMessage,
        conversation_id: payload.conversationId,
      },
      status: 'pending',
      attempts: 0,
    });
  } catch {
    // Silent — memory extraction is best-effort
  }
};
