import AsyncStorage from '@react-native-async-storage/async-storage';
import type { ResponsePreferences } from './types';

const PREFS_KEY = 'askmukthiguru.expo.response_preferences.v1';
const INCOGNITO_KEY = 'askmukthiguru.expo.incognito.v1';

export const DEFAULT_RESPONSE_PREFERENCES: ResponsePreferences = {
  mode: 'balanced_guidance',
  includePractice: true,
  includeReflection: true,
  actionDepth: 'one_step',
};

export async function loadPreferences(): Promise<ResponsePreferences> {
  try {
    const raw = await AsyncStorage.getItem(PREFS_KEY);
    if (!raw) return { ...DEFAULT_RESPONSE_PREFERENCES };
    const parsed = JSON.parse(raw) as Partial<ResponsePreferences>;
    return {
      mode: parsed.mode === 'concise' || parsed.mode === 'reflective_guidance' || parsed.mode === 'teaching_explanation'
        ? parsed.mode
        : 'balanced_guidance',
      includePractice: parsed.includePractice !== false,
      includeReflection: parsed.includeReflection !== false,
      actionDepth: parsed.actionDepth === 'none' ? 'none' : 'one_step',
    };
  } catch {
    return { ...DEFAULT_RESPONSE_PREFERENCES };
  }
}

export async function savePreferences(value: ResponsePreferences): Promise<void> {
  await AsyncStorage.setItem(PREFS_KEY, JSON.stringify(value));
}

export async function setIncognitoStorage(enabled: boolean): Promise<void> {
  await AsyncStorage.setItem(INCOGNITO_KEY, enabled ? '1' : '0');
}

export async function loadIncognitoStorage(): Promise<boolean> {
  return (await AsyncStorage.getItem(INCOGNITO_KEY)) === '1';
}
