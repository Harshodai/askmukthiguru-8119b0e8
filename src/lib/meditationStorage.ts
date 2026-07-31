import { z } from 'zod';
import { supabase } from '@/integrations/supabase/client';
import { computeMetrics, type NormalizedSession } from '@/lib/meditationMetrics';
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

/** Adapt a stored session into the shared metric shape. */
const toNormalized = (s: MeditationSession): NormalizedSession => ({
  at: new Date(s.completedAt ?? s.startedAt),
  durationSeconds: s.durationSeconds ?? 0,
  breathCycles: s.breathCycles ?? 0,
  completed: s.completed,
});

/**
 * Get meditation statistics from localStorage.
 * All arithmetic lives in `meditationMetrics` so the DB path can't drift.
 */
export const getMeditationStats = (): MeditationStats =>
  computeMetrics(loadMeditationSessions().map(toNormalized));

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
      .order('completed_at', { ascending: false });

    if (error || !data) return getMeditationStats();

    // Same normalization, same calculator as the localStorage path — a signed-in
    // seeker and an anonymous one can never see different arithmetic.
    return computeMetrics(
      data.map((s) => ({
        at: new Date((s.completed_at ?? s.started_at) as string),
        durationSeconds: s.duration_seconds ?? 0,
        breathCycles: s.breath_cycles ?? 0,
        completed: s.completed ?? false,
      })),
    );
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
