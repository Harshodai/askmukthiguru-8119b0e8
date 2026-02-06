export interface MeditationSession {
  id: string;
  startedAt: Date;
  completedAt: Date | null;
  durationSeconds: number;
  breathCycles: number;
  completed: boolean;
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
  
  const sessions = loadMeditationSessions();
  sessions.push(session);
  saveSessions(sessions);
  
  return session;
};

/**
 * Update an existing meditation session
 */
export const updateMeditationSession = (
  sessionId: string,
  updates: Partial<Omit<MeditationSession, 'id' | 'startedAt'>>
): MeditationSession | null => {
  const sessions = loadMeditationSessions();
  const index = sessions.findIndex((s) => s.id === sessionId);
  
  if (index === -1) return null;
  
  sessions[index] = { ...sessions[index], ...updates };
  saveSessions(sessions);
  
  return sessions[index];
};

/**
 * Complete a meditation session
 */
export const completeMeditationSession = (
  sessionId: string,
  durationSeconds: number,
  breathCycles: number
): MeditationSession | null => {
  return updateMeditationSession(sessionId, {
    completedAt: new Date(),
    durationSeconds,
    breathCycles,
    completed: true,
  });
};

/**
 * Get meditation statistics
 */
export const getMeditationStats = (): {
  totalSessions: number;
  completedSessions: number;
  totalMinutes: number;
  totalBreathCycles: number;
  streakDays: number;
} => {
  const sessions = loadMeditationSessions();
  const completedSessions = sessions.filter((s) => s.completed);
  
  const totalMinutes = Math.round(
    completedSessions.reduce((acc, s) => acc + s.durationSeconds, 0) / 60
  );
  
  const totalBreathCycles = completedSessions.reduce((acc, s) => acc + s.breathCycles, 0);
  
  // Calculate streak
  let streakDays = 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  
  const sortedDates = completedSessions
    .map((s) => {
      const date = new Date(s.completedAt!);
      date.setHours(0, 0, 0, 0);
      return date.getTime();
    })
    .filter((v, i, a) => a.indexOf(v) === i)
    .sort((a, b) => b - a);
  
  for (let i = 0; i < sortedDates.length; i++) {
    const expectedDate = new Date(today);
    expectedDate.setDate(expectedDate.getDate() - i);
    
    if (sortedDates[i] === expectedDate.getTime()) {
      streakDays++;
    } else {
      break;
    }
  }
  
  return {
    totalSessions: sessions.length,
    completedSessions: completedSessions.length,
    totalMinutes,
    totalBreathCycles,
    streakDays,
  };
};

/**
 * Clear all meditation sessions
 */
export const clearMeditationSessions = (): void => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error('Failed to clear meditation sessions:', error);
  }
};
