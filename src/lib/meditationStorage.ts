export interface MeditationSession {
  id: string;
  startedAt: Date;
  completedAt: Date | null;
  durationSeconds: number;
  breathCycles: number;
  completed: boolean;
}

export interface MeditationStats {
  totalSessions: number;
  totalMinutes: number;
  totalCycles: number;
  streakDays: number;
  lastSessionDate: Date | null;
}

const STORAGE_KEY = 'askmukthiguru_meditation_sessions';

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
      const sessions = JSON.parse(stored);
      return sessions.map((session: MeditationSession) => ({
        ...session,
        startedAt: new Date(session.startedAt),
        completedAt: session.completedAt ? new Date(session.completedAt) : null,
      }));
    }
  } catch (error) {
    console.error('Failed to load meditation sessions:', error);
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
 * Complete and save a meditation session
 */
export const completeMeditationSession = (
  sessionId: string,
  durationSeconds: number,
  breathCycles: number
): void => {
  const sessions = loadMeditationSessions();
  const existingIndex = sessions.findIndex(s => s.id === sessionId);
  
  const completedSession: MeditationSession = {
    id: sessionId,
    startedAt: existingIndex >= 0 ? sessions[existingIndex].startedAt : new Date(),
    completedAt: new Date(),
    durationSeconds,
    breathCycles,
    completed: true,
  };

  if (existingIndex >= 0) {
    sessions[existingIndex] = completedSession;
  } else {
    sessions.push(completedSession);
  }

  saveSessions(sessions);
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
