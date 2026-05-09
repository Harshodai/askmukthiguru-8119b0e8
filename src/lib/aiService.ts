import { guruResponses } from './chatStorage';
import { supabase } from '@/integrations/supabase/client';

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
}

// Auto-detect backend URL: VITE_BACKEND_URL for local dev, relative path for production
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '';

let currentConfig: AIConfig = {
  provider: 'custom',
  endpoint: `${BACKEND_URL}/api/chat`,
  language: 'en',
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

/**
 * Streaming variant of sendMessage. Yields content chunks as they arrive
 * from an SSE/chunked endpoint. Falls back by throwing if streaming is
 * unavailable (caller should catch and use sendMessage instead).
 */
/** Streaming chunk: either a content token, a pipeline status update, or final metadata */
export type StreamChunk =
  | { type: 'token'; text: string }
  | { type: 'status'; text: string }
  | { type: 'done'; intent: string; citations: string[]; meditationStep: number }
  | { type: 'error'; text: string };

export async function* sendMessageStreaming(
  messages: MessagePayload[],
  userMessage: string,
  meditationStep: number = 0,
  summary?: string,
): AsyncGenerator<StreamChunk> {
  const { provider, endpoint, systemPrompt } = currentConfig;

  // Streaming only works for the custom backend with SSE support
  if (provider !== 'custom' || !endpoint) {
    throw new Error('Streaming not available for this provider');
  }

  const streamEndpoint = endpoint.replace(/\/?$/, '/stream');
  const trimmedMessages = messages.slice(-20);

  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;

  const response = await fetch(streamEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      messages: [
        { role: 'system', content: systemPrompt },
        ...(summary ? [{ role: 'system' as const, content: `SUMMARY OF PREVIOUS CONVERSATION: ${summary}` }] : []),
        ...trimmedMessages,
      ],
      user_message: userMessage,
      meditation_step: meditationStep,
      stream: true,
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Streaming failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = 'message'; // tracks the SSE event type

  try {
    while (true) {
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
        if (payload.trim() === '[DONE]') return;

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
  } finally {
    reader.releaseLock();
  }
}


export const sendMessage = async (
  messages: MessagePayload[],
  userMessage: string,
  meditationStep: number = 0,
  summary?: string,
): Promise<AIResponse> => {
  const { provider, endpoint, systemPrompt } = currentConfig;

  if (provider === 'placeholder') {
    await new Promise((resolve) => setTimeout(resolve, 1000 + Math.random() * 1000));
    return { content: getPlaceholderResponse() };
  }

  if (provider === 'custom' && endpoint) {
    try {
      const trimmedMessages = messages.slice(-20);
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
            { role: 'system', content: systemPrompt },
            ...(summary ? [{ role: 'system' as const, content: `SUMMARY OF PREVIOUS CONVERSATION: ${summary}` }] : []),
            ...trimmedMessages,
          ],
          user_message: userMessage,
          meditation_step: meditationStep,
        }),
      });

      if (!response.ok) {
        const errorCode = httpStatusToErrorCode(response.status);
        return {
          content: getPlaceholderResponse(),
          error: `API error: ${response.status}`,
          errorCode,
        };
      }

      const data = await response.json();
      return {
        content: data.response || data.choices?.[0]?.message?.content || data.content,
        intent: data.intent,
        citations: data.citations || [],
        meditationStep: data.meditation_step || 0,
        blocked: data.blocked || false,
        blockReason: data.block_reason,
      };
    } catch (error) {
      console.error('AI Service Error:', error);
      return {
        content: getPlaceholderResponse(),
        error: error instanceof Error ? error.message : 'Connection failed',
        errorCode: 'network',
      };
    }
  }

  // OpenAI direct client-side calls removed for security.
  // API keys must never be stored or used in the browser.
  // Use a server-side proxy (Edge Function) if OpenAI integration is needed.

  return { content: getPlaceholderResponse() };
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


export const checkConnection = async (): Promise<{ connected: boolean; mode: string }> => {
  const { provider, endpoint } = currentConfig;

  if (provider === 'placeholder') {
    return { connected: true, mode: 'Offline Mode' };
  }

  if (provider === 'custom' && endpoint) {
    try {
      // Handle both relative and absolute endpoints safely
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
