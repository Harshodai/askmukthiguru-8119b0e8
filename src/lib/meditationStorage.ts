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
const LAST_COMPLETED_KEY = 'askmukthiguru_last_serene_mind_at';

/**
 * Returns the Unix timestamp (ms) of the last *fully completed* Serene Mind
 * session, or null if the user has never completed one on this device.
 */
export const getLastCompletedMeditationTimestamp = (): number | null => {
  const raw = localStorage.getItem(LAST_COMPLETED_KEY);
  if (!raw) return null;
  const ts = parseInt(raw, 10);
  return isNaN(ts) ? null : ts;
};

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
  extras?: { mood?: string; reflection?: string; gratitude?: string },
  /** Whether the user fully completed (true) or exited early (false). Defaults to true. */
  completed = true
): Promise<MeditationSession> => {
  const sessions = loadMeditationSessions();
  const existingIndex = sessions.findIndex(s => s.id === sessionId);

  const completedSession: MeditationSession = {
    id: sessionId,
    startedAt: existingIndex >= 0 ? sessions[existingIndex].startedAt : new Date(),
    completedAt: new Date(),
    durationSeconds,
    breathCycles,
    completed,
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
        completed,
      });
    }
  } catch (err) {
    console.error('Failed to persist meditation session to DB:', err);
  }

  // Record timestamp of fully completed session for cooldown guard
  if (completed && typeof window !== 'undefined') {
    localStorage.setItem(LAST_COMPLETED_KEY, String(Date.now()));
  }

  // Dispatch event so UI components (like DailyTeaching) can react and reward the user
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('askmukthiguru:meditation_completed'));
  }

  return completedSession;
};

/**
 * Calculate streak days from sessions
 */
const calculateStreak = (sessions: MeditationSession[]): number => {
  if (sessions.length === 0) return 0;

  // Forgiving streak: any genuine sit keeps the streak alive — a full session OR a
  // partial of at least 30s (Insight-Timer pattern). Zero-duration rows (mood
  // check-ins are stored as completed 0s sessions) do NOT count, so they can't
  // silently inflate the streak.
  const STREAK_MIN_SECONDS = 30;
  const completedSessions = sessions.filter(
    s => s.durationSeconds >= STREAK_MIN_SECONDS || (s.completed && s.durationSeconds > 0),
  );
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
 * DB-backed meditation stats for authenticated users. Falls back to localStorage
 * stats when the user is not signed in or the query fails.
 */
export const getMeditationStatsFromDb = async (): Promise<MeditationStats> => {
  try {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session?.user) return getMeditationStats();

    const { data, error } = await supabase
      .from('meditation_sessions')
      .select('duration_seconds, breath_cycles, completed, completed_at, started_at')
      .eq('user_id', session.user.id)
      .eq('completed', true)
      .order('completed_at', { ascending: false });

    if (error || !data) return getMeditationStats();

    const totalSeconds = data.reduce((a, s) => a + (s.duration_seconds ?? 0), 0);
    const totalCycles = data.reduce((a, s) => a + (s.breath_cycles ?? 0), 0);

    // Streak from DB rows
    const dates = new Set(
      data
        .map((s) => (s.completed_at ?? s.started_at)?.toString().slice(0, 10))
        .filter(Boolean) as string[],
    );
    let streak = 0;
    const cur = new Date();
    while (dates.has(cur.toISOString().slice(0, 10))) {
      streak++;
      cur.setDate(cur.getDate() - 1);
    }

    return {
      totalSessions: data.length,
      totalMinutes: Math.round(totalSeconds / 60),
      totalCycles,
      streakDays: streak,
      lastSessionDate: data[0]?.completed_at
        ? new Date(data[0].completed_at)
        : data[0]?.started_at
          ? new Date(data[0].started_at)
          : null,
    };
  } catch {
    return getMeditationStats();
  }
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

const MOOD_CHECKIN_KEY = 'askmukthiguru_last_mood_checkin';

/**
 * Returns the Unix timestamp (ms) of the last mood check-in, or null if never.
 */
export const getLastMoodCheckIn = (): number | null => {
  try {
    const raw = localStorage.getItem(MOOD_CHECKIN_KEY);
    if (!raw) return null;
    const ts = parseInt(raw, 10);
    return isNaN(ts) ? null : ts;
  } catch {
    return null;
  }
};

/**
 * Record a mood check-in as a zero-duration meditation session carrying
 * `mood` + `reflection` in `extras`, and stamp the check-in timestamp.
 */
export const recordMoodCheckIn = async (
  mood: string,
  reflection?: string,
): Promise<MeditationSession> => {
  const session = startMeditationSession();
  // Zero-duration session flagged completed so it is captured in stats/history.
  const completed = await completeMeditationSession(session.id, 0, 0, { mood, reflection }, true);
  try {
    localStorage.setItem(MOOD_CHECKIN_KEY, String(Date.now()));
  } catch (error) {
    console.error('Failed to stamp mood check-in:', error);
  }
  return completed;
};
