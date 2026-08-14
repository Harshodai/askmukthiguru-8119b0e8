export type ResponsePreferenceMode =
  | 'balanced_guidance'
  | 'concise'
  | 'reflective_guidance'
  | 'teaching_explanation';

export interface ResponsePreferences {
  mode: ResponsePreferenceMode;
  includePractice: boolean;
  includeReflection: boolean;
  actionDepth: 'none' | 'one_step';
}

export interface CapabilityManifest {
  [key: string]: unknown;
}

export interface Citation {
  title?: string;
  source_url?: string;
  url?: string;
  source_language?: string;
}

export interface GuidancePlan {
  response_mode: string;
  language: string;
  attribution: {
    label: string;
    source_backed: boolean;
    teacher_name?: string | null;
  };
  action_step?: {
    title: string;
    instruction: string;
    optional: boolean;
    safety_note?: string | null;
  } | null;
  reflection_prompt?: string | null;
}

export interface ChatResponse {
  response: string;
  intent?: string;
  blocked?: boolean;
  block_reason?: string | null;
  citations?: Citation[];
  guidance_plan?: GuidancePlan | null;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  user_message: string;
  language: string;
  incognito: boolean;
  response_preferences: {
    mode: ResponsePreferenceMode;
    include_practice: boolean;
    include_reflection: boolean;
    action_depth: 'none' | 'one_step';
  };
}
