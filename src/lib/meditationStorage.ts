import { z } from 'zod';
import { supabase } from '@/integrations/supabase/client';
export interface MeditationSession {
  id: string;
  startedAt: Date;
  completedAt: Date | null;
  durationSeconds: number;
  breathCycles: number;
  completed: boolean;
  mood?: string;        // e.g. 'peaceful', 'grateful', 'lighter', 'contemplative', 'heavy'
  reflection?: string; // post-meditation journal text
  gratitude?: string;  // gratitude prompt response
}

export interface MeditationStats {
  totalSessions: number;
  totalMinutes: number;
  totalCycles: number;
  streakDays: number;
  lastSessionDate: Date | null;
}

const STORAGE_KEY = 'askmukthiguru_meditation_sessions';

const MeditationSessionSchema = z.object({
  id: z.string(),
  startedAt: z.coerce.date(),
  completedAt: z.coerce.date().nullable(),
  durationSeconds: z.number(),
  breathCycles: z.number(),
  completed: z.boolean(),
  mood: z.string().optional(),
  reflection: z.string().optional(),
  gratitude: z.string().optional(),
});

/**
 * Generate a unique session ID
 */
export const generateSessionId = (): string => {
  return `med_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
};

/**
 * Save all meditation sessions to localStorage
 */
const saveSessions = (sessions: MeditationSession[]): void => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  } catch (error) {
    console.error('Failed to save meditation sessions:', error);
  }
};

/**
 * Load all meditation sessions from localStorage
 */
export const loadMeditationSessions = (): MeditationSession[] => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      const result = z.array(MeditationSessionSchema).safeParse(parsed);
      if (!result.success) {
        console.error('Corrupted meditation sessions — clearing:', result.error.message);
        localStorage.removeItem(STORAGE_KEY);
        return [];
      }
      return result.data as MeditationSession[];
    }
  } catch (error) {
    console.error('Failed to load meditation sessions — clearing corrupted data:', error);
    localStorage.removeItem(STORAGE_KEY);
  }
  return [];
};

/**
 * Start a new meditation session
 */
export const startMeditationSession = (): MeditationSession => {
  const session: MeditationSession = {
    id: generateSessionId(),
    startedAt: new Date(),
    completedAt: null,
    durationSeconds: 0,
    breathCycles: 0,
    completed: false,
  };
  return session;
};

/**
 * Complete and save a meditation session (localStorage + DB if authenticated)
 */
export const completeMeditationSession = async (
  sessionId: string,
  durationSeconds: number,
  breathCycles: number,
  extras?: { mood?: string; reflection?: string; gratitude?: string }
): Promise<void> => {
  const sessions = loadMeditationSessions();
  const existingIndex = sessions.findIndex(s => s.id === sessionId);
  
  const completedSession: MeditationSession = {
    id: sessionId,
    startedAt: existingIndex >= 0 ? sessions[existingIndex].startedAt : new Date(),
    completedAt: new Date(),
    durationSeconds,
    breathCycles,
    completed: true,
    ...(extras ?? {}),
  };

  if (existingIndex >= 0) {
    sessions[existingIndex] = completedSession;
  } else {
    sessions.push(completedSession);
  }

  saveSessions(sessions);

  // Also persist to DB if user is authenticated
  try {
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.user) {
      await supabase.from('meditation_sessions').insert({
        user_id: session.user.id,
        started_at: completedSession.startedAt.toISOString(),
        completed_at: completedSession.completedAt?.toISOString() ?? null,
        duration_seconds: durationSeconds,
        breath_cycles: breathCycles,
        completed: true,
      });
    }
  } catch (err) {
    console.error('Failed to persist meditation session to DB:', err);
  }

  // Dispatch event so UI components (like DailyTeaching) can react and reward the user
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('askmukthiguru:meditation_completed'));
  }
};

/**
 * Calculate streak days from sessions
 */
const calculateStreak = (sessions: MeditationSession[]): number => {
  if (sessions.length === 0) return 0;

  const completedSessions = sessions.filter(s => s.completed);
  if (completedSessions.length === 0) return 0;

  // Get unique dates (only date part, not time)
  const sessionDates = completedSessions
    .map(s => {
      const date = new Date(s.completedAt || s.startedAt);
      return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
    })
    .filter((date, index, arr) => arr.indexOf(date) === index)
    .sort((a, b) => b - a);

  const today = new Date();
  const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const yesterday = todayStart - 86400000;

  // Check if most recent session is today or yesterday
  if (sessionDates[0] !== todayStart && sessionDates[0] !== yesterday) {
    return 0;
  }

  let streak = 1;
  let currentDate = sessionDates[0];

  for (let i = 1; i < sessionDates.length; i++) {
    const expectedPreviousDate = currentDate - 86400000;
    if (sessionDates[i] === expectedPreviousDate) {
      streak++;
      currentDate = sessionDates[i];
    } else {
      break;
    }
  }

  return streak;
};

/**
 * Get meditation statistics
 */
export const getMeditationStats = (): MeditationStats => {
  const sessions = loadMeditationSessions();
  const completedSessions = sessions.filter(s => s.completed);

  const totalSeconds = completedSessions.reduce((acc, s) => acc + s.durationSeconds, 0);
  const totalCycles = completedSessions.reduce((acc, s) => acc + s.breathCycles, 0);

  const sortedSessions = completedSessions.sort(
    (a, b) => new Date(b.completedAt || b.startedAt).getTime() - new Date(a.completedAt || a.startedAt).getTime()
  );

  return {
    totalSessions: completedSessions.length,
    totalMinutes: Math.round(totalSeconds / 60),
    totalCycles,
    streakDays: calculateStreak(sessions),
    lastSessionDate: sortedSessions[0]?.completedAt || sortedSessions[0]?.startedAt || null,
  };
};

/**
 * Clear all meditation data
 */
export const clearMeditationData = (): void => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error('Failed to clear meditation data:', error);
  }
};
