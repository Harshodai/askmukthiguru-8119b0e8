/**
 * Local profile storage — no server, no auth.
 * All data lives in the browser's localStorage.
 */

export type GuruTone = 'gentle' | 'direct' | 'poetic';
export type ThemePreference = 'light' | 'dark' | 'system';

/** What the seeker did right before opening the chat. */
export type PrePracticeAnswer = 'soul_sync' | 'serene_mind' | 'both' | 'none';

export interface PrePracticeEntry {
  answer: PrePracticeAnswer;
  at: string; // ISO timestamp
}

export interface PrePracticeLog {
  /** Running counters for quick analytics. */
  counts: {
    soul_sync: number;
    serene_mind: number;
    both: number;
    none: number;
  };
  /** Most recent answer (for greeting personalisation). */
  lastAnswer: PrePracticeAnswer | null;
  lastAnsweredAt: string | null;
  /** Bounded history (last 50 entries) for trend insights. */
  history: PrePracticeEntry[];
}

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
  prePracticeLog: PrePracticeLog;
  createdAt: Date;
  updatedAt: Date;
}

const EMPTY_PRE_PRACTICE_LOG: PrePracticeLog = {
  counts: { soul_sync: 0, serene_mind: 0, both: 0, none: 0 },
  lastAnswer: null,
  lastAnsweredAt: null,
  history: [],
};

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
    prePracticeLog: { ...EMPTY_PRE_PRACTICE_LOG, counts: { ...EMPTY_PRE_PRACTICE_LOG.counts }, history: [] },
    createdAt: now,
    updatedAt: now,
  };
};

const MAX_HISTORY = 50;

/**
 * Record a pre-chat practice answer and return the updated profile.
 * Pure storage helper — no UI side-effects.
 */
export const recordPrePractice = (answer: PrePracticeAnswer): UserProfile => {
  const current = loadProfile();
  const log: PrePracticeLog = current.prePracticeLog ?? {
    ...EMPTY_PRE_PRACTICE_LOG,
    counts: { ...EMPTY_PRE_PRACTICE_LOG.counts },
    history: [],
  };
  const at = new Date().toISOString();
  const nextCounts = { ...log.counts, [answer]: (log.counts[answer] ?? 0) + 1 };
  const nextHistory = [...log.history, { answer, at }].slice(-MAX_HISTORY);
  const nextLog: PrePracticeLog = {
    counts: nextCounts,
    lastAnswer: answer,
    lastAnsweredAt: at,
    history: nextHistory,
  };
  const next: UserProfile = { ...current, prePracticeLog: nextLog, updatedAt: new Date() };
  saveProfile(next);
  return next;
};

/**
 * Derive lightweight intelligence from the pre-practice log.
 * Used to personalise the greeting and surface gentle nudges.
 */
export interface PrePracticeInsights {
  totalPrepared: number; // soul_sync + serene_mind + both
  totalAsked: number;
  preparedRate: number; // 0..1
  favourite: 'soul_sync' | 'serene_mind' | null;
  streakPrepared: number; // consecutive recent answers that weren't "none"
  encouragement: string;
}

export const derivePrePracticeInsights = (
  log: PrePracticeLog | undefined,
): PrePracticeInsights => {
  const safe = log ?? EMPTY_PRE_PRACTICE_LOG;
  const { soul_sync, serene_mind, both, none } = safe.counts;
  const totalPrepared = soul_sync + serene_mind + both;
  const totalAsked = totalPrepared + none;
  const preparedRate = totalAsked === 0 ? 0 : totalPrepared / totalAsked;

  const ssWeight = soul_sync + both;
  const smWeight = serene_mind + both;
  let favourite: PrePracticeInsights['favourite'] = null;
  if (ssWeight > smWeight) favourite = 'soul_sync';
  else if (smWeight > ssWeight) favourite = 'serene_mind';

  let streakPrepared = 0;
  for (let i = safe.history.length - 1; i >= 0; i -= 1) {
    if (safe.history[i].answer === 'none') break;
    streakPrepared += 1;
  }

  let encouragement = 'A calm mind hears the Guru more clearly. Take a breath before we begin.';
  if (totalAsked === 0) {
    encouragement = 'Welcome, dear seeker. A short practice before we talk deepens every word.';
  } else if (streakPrepared >= 5) {
    encouragement = `Your beautiful state is taking root — ${streakPrepared} sessions prepared in a row.`;
  } else if (preparedRate >= 0.6) {
    encouragement = 'You arrive ready. The Guru meets you where you are.';
  } else if (preparedRate > 0 && preparedRate < 0.3) {
    encouragement = 'Even one minute of stillness changes the conversation. Try a quick practice.';
  }

  return { totalPrepared, totalAsked, preparedRate, favourite, streakPrepared, encouragement };
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
