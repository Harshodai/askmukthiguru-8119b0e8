/**
 * Local profile storage — no server, no auth.
 * All data lives in the browser's localStorage.
 */

export type GuruTone = 'gentle' | 'direct' | 'poetic';
export type ThemePreference = 'light' | 'dark' | 'system';

export interface UserProfile {
  id: string;
  displayName: string;
  avatarDataUrl: string | null; // base64 data URL (kept small, validated)
  bio: string;
  preferredLanguage: 'en' | 'hi' | 'te' | 'ml';
  guruTone: GuruTone;
  theme: ThemePreference;
  ttsEnabled: boolean;
  ttsRate: number; // 0.5–1.5
  meditationReminders: boolean;
  reminderTimeMinutes: number; // minutes since midnight
  createdAt: Date;
  updatedAt: Date;
}

const PROFILE_KEY = 'askmukthiguru_profile';
const MAX_AVATAR_BYTES = 200 * 1024; // 200KB cap to avoid quota issues

const generateId = (): string =>
  Math.random().toString(36).substring(2, 12) + Date.now().toString(36);

export const createDefaultProfile = (): UserProfile => {
  const now = new Date();
  return {
    id: generateId(),
    displayName: 'Seeker',
    avatarDataUrl: null,
    bio: '',
    preferredLanguage: 'en',
    guruTone: 'gentle',
    theme: 'system',
    ttsEnabled: false,
    ttsRate: 0.9,
    meditationReminders: false,
    reminderTimeMinutes: 7 * 60, // 7:00 AM
    createdAt: now,
    updatedAt: now,
  };
};

export const loadProfile = (): UserProfile => {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) {
      const fresh = createDefaultProfile();
      saveProfile(fresh);
      return fresh;
    }
    const parsed = JSON.parse(raw);
    return {
      ...createDefaultProfile(),
      ...parsed,
      createdAt: new Date(parsed.createdAt),
      updatedAt: new Date(parsed.updatedAt),
    };
  } catch {
    return createDefaultProfile();
  }
};

export const saveProfile = (profile: UserProfile): void => {
  try {
    const next = { ...profile, updatedAt: new Date() };
    localStorage.setItem(PROFILE_KEY, JSON.stringify(next));
    window.dispatchEvent(new CustomEvent('profile:updated', { detail: next }));
  } catch (err) {
    console.error('Failed to save profile', err);
  }
};

export const updateProfile = (patch: Partial<UserProfile>): UserProfile => {
  const current = loadProfile();
  const next = { ...current, ...patch, updatedAt: new Date() };
  saveProfile(next);
  return next;
};

export const resetProfile = (): UserProfile => {
  const fresh = createDefaultProfile();
  saveProfile(fresh);
  return fresh;
};

/**
 * Validate an uploaded avatar file.
 * - Must be image/* mime
 * - Must be under MAX_AVATAR_BYTES once base64-encoded
 */
export const readAvatarFile = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    if (!file.type.startsWith('image/')) {
      reject(new Error('Please select an image file.'));
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      reject(new Error('Image too large. Please choose one under 200KB.'));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== 'string') {
        reject(new Error('Could not read image.'));
        return;
      }
      resolve(result);
    };
    reader.onerror = () => reject(new Error('Could not read image.'));
    reader.readAsDataURL(file);
  });

export interface ExportBundle {
  profile: UserProfile;
  conversations: unknown;
  meditationSessions: unknown;
  exportedAt: string;
  version: 1;
}

export const exportAllData = (): ExportBundle => {
  const conversations = JSON.parse(
    localStorage.getItem('askmukthiguru_conversations') || '[]',
  );
  const meditationSessions = JSON.parse(
    localStorage.getItem('askmukthiguru_meditation_sessions') || '[]',
  );
  return {
    profile: loadProfile(),
    conversations,
    meditationSessions,
    exportedAt: new Date().toISOString(),
    version: 1,
  };
};

export const deleteAllData = (): void => {
  const keys = [
    'askmukthiguru_profile',
    'askmukthiguru_conversations',
    'askmukthiguru_current_conversation',
    'askmukthiguru_chat_history',
    'askmukthiguru_meditation_sessions',
  ];
  keys.forEach((k) => localStorage.removeItem(k));
  window.dispatchEvent(new CustomEvent('profile:updated'));
};

export const getInitials = (name: string): string => {
  const trimmed = name.trim();
  if (!trimmed) return 'S';
  const parts = trimmed.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
};
