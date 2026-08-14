import type { ResponsePreferenceMode, ResponsePreferences } from './types';

const STORAGE_KEY = 'askmukthiguru.response_preferences.v1';

export const DEFAULT_RESPONSE_PREFERENCES: ResponsePreferences = {
  mode: 'balanced_guidance',
  includePractice: true,
  includeReflection: true,
  actionDepth: 'one_step',
};

const MODES: readonly ResponsePreferenceMode[] = [
  'balanced_guidance',
  'concise',
  'reflective_guidance',
  'teaching_explanation',
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

export function normalizeResponsePreferences(value: unknown): ResponsePreferences {
  if (!isRecord(value)) return { ...DEFAULT_RESPONSE_PREFERENCES };
  const mode = MODES.includes(value.mode as ResponsePreferenceMode)
    ? (value.mode as ResponsePreferenceMode)
    : DEFAULT_RESPONSE_PREFERENCES.mode;
  return {
    mode,
    includePractice: typeof value.includePractice === 'boolean'
      ? value.includePractice
      : DEFAULT_RESPONSE_PREFERENCES.includePractice,
    includeReflection: typeof value.includeReflection === 'boolean'
      ? value.includeReflection
      : DEFAULT_RESPONSE_PREFERENCES.includeReflection,
    actionDepth: value.actionDepth === 'none' ? 'none' : 'one_step',
  };
}

export function loadResponsePreferences(): ResponsePreferences {
  if (typeof window === 'undefined') return { ...DEFAULT_RESPONSE_PREFERENCES };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? normalizeResponsePreferences(JSON.parse(raw)) : { ...DEFAULT_RESPONSE_PREFERENCES };
  } catch {
    return { ...DEFAULT_RESPONSE_PREFERENCES };
  }
}

export function saveResponsePreferences(value: ResponsePreferences): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalizeResponsePreferences(value)));
  } catch {
    // Local storage can be unavailable in private browsing; the request still works.
  }
}

export function clearResponsePreferences(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Best effort only; no response content is stored here.
  }
}
