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

export interface AIResponse {
  content: string;
  error?: string;
}

// Default configuration
let currentConfig: AIConfig = {
  provider: 'placeholder',
  language: 'en',
  systemPrompt: `You are a spiritual AI companion embodying the wisdom of Sri Preethaji & Sri Krishnaji. 
Your purpose is to guide seekers toward their "beautiful state" - a state of consciousness free from suffering.
You speak with warmth, compassion, and profound insight. You never claim to replace professional mental health support.
When someone is in deep distress, gently encourage them to seek professional help while offering comfort.`,
};

/**
 * Configure the AI service provider
 */
export const setAIProvider = (config: Partial<AIConfig>): void => {
  currentConfig = { ...currentConfig, ...config };
};

/**
 * Get current AI configuration
 */
export const getAIConfig = (): AIConfig => {
  return { ...currentConfig };
};

/**
 * Set the language for AI responses
 */
export const setLanguage = (language: string): void => {
  currentConfig.language = language;
};

/**
 * Get a placeholder response (for demo/offline mode)
 */
const getPlaceholderResponse = (): string => {
  const randomIndex = Math.floor(Math.random() * guruResponses.length);
  return guruResponses[randomIndex];
};

/**
 * Send a message to the AI and get a response
 */
export const sendMessage = async (
  messages: MessagePayload[],
  userMessage: string
): Promise<AIResponse> => {
  const { provider, endpoint, apiKey, systemPrompt, model } = currentConfig;

  // Placeholder mode - return static responses
  if (provider === 'placeholder') {
    // Simulate network delay
    await new Promise((resolve) => setTimeout(resolve, 1000 + Math.random() * 1000));
    return { content: getPlaceholderResponse() };
  }

  // Custom endpoint mode
  if (provider === 'custom' && endpoint) {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey && { Authorization: `Bearer ${apiKey}` }),
        },
        body: JSON.stringify({
          messages: [
            { role: 'system', content: systemPrompt },
            ...messages,
            { role: 'user', content: userMessage },
          ],
          model: model || 'default',
          language: currentConfig.language,
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      return { content: data.choices?.[0]?.message?.content || data.content || data.response };
    } catch (error) {
      console.error('AI Service Error:', error);
      // Fallback to placeholder on error
      return { 
        content: getPlaceholderResponse(),
        error: error instanceof Error ? error.message : 'Connection failed'
      };
    }
  }

  // OpenAI mode
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
        throw new Error(`OpenAI API error: ${response.status}`);
      }

      const data = await response.json();
      return { content: data.choices[0].message.content };
    } catch (error) {
      console.error('OpenAI Service Error:', error);
      return { 
        content: getPlaceholderResponse(),
        error: error instanceof Error ? error.message : 'Connection failed'
      };
    }
  }

  // Default fallback
  return { content: getPlaceholderResponse() };
};

/**
 * Check if the AI service is connected/available
 */
export const checkConnection = async (): Promise<{ connected: boolean; mode: string }> => {
  const { provider, endpoint } = currentConfig;

  if (provider === 'placeholder') {
    return { connected: true, mode: 'Offline Mode' };
  }

  if (provider === 'custom' && endpoint) {
    try {
      const response = await fetch(endpoint, { method: 'HEAD' });
      return { connected: response.ok, mode: 'Connected to Guru' };
    } catch {
      return { connected: false, mode: 'Connecting...' };
    }
  }

  return { connected: true, mode: 'Cloud Mode' };
};
