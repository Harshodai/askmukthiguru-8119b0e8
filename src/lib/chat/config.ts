import type { AIConfig } from './types';

// Auto-detect backend URL:
//   1. VITE_BACKEND_URL (self-hosted FastAPI) — preferred for full RAG
//   2. Lovable Cloud edge function `guru-chat` — cloud fallback (LLM-only, no RAG yet)
//   3. Relative `/api/chat` — last resort, requires reverse-proxy
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
const EDGE_CHAT_URL = SUPABASE_URL
  ? `${SUPABASE_URL.replace(/\/$/, '')}/functions/v1/guru-chat`
  : '';
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '';
export const DEFAULT_ENDPOINT = BACKEND_URL
  ? `${BACKEND_URL}/api/chat`
  : EDGE_CHAT_URL || '/api/chat';

export const getInitialLanguage = (): string => {
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

/** Internal accessor for modules that share the mutable config. */
export const getCurrentConfig = (): AIConfig => currentConfig;
