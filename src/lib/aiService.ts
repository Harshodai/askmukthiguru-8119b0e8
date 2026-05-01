import { guruResponses } from './chatStorage';

export type AIProvider = 'placeholder' | 'custom' | 'openai';

export interface AIConfig {
  provider: AIProvider;
  endpoint?: string;
  apiKey?: string;
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

// Default configuration pointing to our FastAPI backend
let currentConfig: AIConfig = {
  provider: 'custom',
  endpoint: '/api/chat',
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
export async function* sendMessageStreaming(
  messages: MessagePayload[],
  userMessage: string,
  meditationStep: number = 0,
): AsyncGenerator<string> {
  const { provider, endpoint, apiKey, systemPrompt } = currentConfig;

  // Streaming only works for the custom backend with SSE support
  if (provider !== 'custom' || !endpoint) {
    throw new Error('Streaming not available for this provider');
  }

  const streamEndpoint = endpoint.replace(/\/?$/, '/stream');
  const trimmedMessages = messages.slice(-10);

  const response = await fetch(streamEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(apiKey && { Authorization: `Bearer ${apiKey}` }),
    },
    body: JSON.stringify({
      messages: [
        { role: 'system', content: systemPrompt },
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

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const text = decoder.decode(value, { stream: true });
      // Parse SSE lines: "data: {...}\n\n"
      const lines = text.split('\n');
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') return;
        try {
          const parsed = JSON.parse(payload);
          const chunk = parsed.choices?.[0]?.delta?.content ?? parsed.token ?? parsed.content ?? '';
          if (chunk) yield chunk;
        } catch {
          // Non-JSON SSE line — yield raw text
          if (payload) yield payload;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}


  messages: MessagePayload[],
  userMessage: string,
  meditationStep: number = 0
): Promise<AIResponse> => {
  const { provider, endpoint, apiKey, systemPrompt, model } = currentConfig;

  if (provider === 'placeholder') {
    await new Promise((resolve) => setTimeout(resolve, 1000 + Math.random() * 1000));
    return { content: getPlaceholderResponse() };
  }

  if (provider === 'custom' && endpoint) {
    try {
      const trimmedMessages = messages.slice(-10);
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey && { Authorization: `Bearer ${apiKey}` }),
        },
        body: JSON.stringify({
          messages: [
            { role: 'system', content: systemPrompt },
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

  if (provider === 'openai' && apiKey) {
    try {
      const response = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model: model || 'gpt-4',
          messages: [
            { role: 'system', content: systemPrompt },
            ...messages,
            { role: 'user', content: userMessage },
          ],
        }),
      });

      if (!response.ok) {
        const errorCode = httpStatusToErrorCode(response.status);
        return {
          content: getPlaceholderResponse(),
          error: `OpenAI API error: ${response.status}`,
          errorCode,
        };
      }

      const data = await response.json();
      return { content: data.choices[0].message.content };
    } catch (error) {
      console.error('OpenAI Service Error:', error);
      return {
        content: getPlaceholderResponse(),
        error: error instanceof Error ? error.message : 'Connection failed',
        errorCode: 'network',
      };
    }
  }

  return { content: getPlaceholderResponse() };
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
