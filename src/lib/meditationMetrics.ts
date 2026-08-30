/**
 * Single source of truth for every meditation metric shown in the UI.
 *
 * Both the localStorage path (anonymous seekers) and the Supabase path
 * (signed-in seekers) normalize into `NormalizedSession[]` and run through the
 * exact same arithmetic here, so a number can never differ depending on which
 * store answered.
 *
 * Rules, deliberately chosen and enforced in one place:
 *  1. Days are bucketed in the seeker's LOCAL timezone. UTC bucketing made an
 *     11pm IST sit land on "tomorrow" and silently broke streaks.
 *  2. A mood check-in is persisted as a completed 0-second session. It is a
 *     journal entry, not a sit — it never counts toward sessions, minutes,
 *     breaths, or streaks.
 *  3. Minutes are summed in SECONDS and rounded once at the end. Rounding each
 *     session first turned six 40-second sits into 6 minutes instead of 4.
 *  4. The streak tolerates "not yet today": it anchors on today, or yesterday
 *     if today has no sit, matching every mainstream habit app.
 */

export interface NormalizedSession {
  /** When the sit finished (falls back to start time). */
  at: Date;
  durationSeconds: number;
  breathCycles: number;
  completed: boolean;
}

export interface MeditationMetrics {
  totalSessions: number;
  totalMinutes: number;
  totalCycles: number;
  streakDays: number;
  longestStreakDays?: number;
  lastSessionDate: Date | null;
}

/** Minimum sit length that keeps a streak alive (Insight Timer pattern). */
export const STREAK_MIN_SECONDS = 30;

/** Local-timezone day key, e.g. "2026-07-31". Never use toISOString() here. */
export const localDayKey = (d: Date): string => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};

/** A real sit: completed with actual time on the cushion. Excludes check-ins. */
export const isCountableSit = (s: NormalizedSession): boolean =>
  s.completed && s.durationSeconds > 0;

/** Qualifies for streak credit: a full sit, or a genuine partial ≥ 30s. */
const keepsStreakAlive = (s: NormalizedSession): boolean =>
  s.durationSeconds >= STREAK_MIN_SECONDS || isCountableSit(s);

export const computeStreak = (sessions: NormalizedSession[], now: Date = new Date()): number => {
  const days = new Set(sessions.filter(keepsStreakAlive).map((s) => localDayKey(s.at)));
  if (days.size === 0) return 0;

  const cursor = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  // Anchor on today, or yesterday when today's sit hasn't happened yet.
  if (!days.has(localDayKey(cursor))) {
    cursor.setDate(cursor.getDate() - 1);
    if (!days.has(localDayKey(cursor))) return 0;
  }

  let streak = 0;
  while (days.has(localDayKey(cursor))) {
    streak++;
    cursor.setDate(cursor.getDate() - 1);
  }
  return streak;
};

export const computeLongestStreak = (sessions: NormalizedSession[]): number => {
  const dayKeys = Array.from(
    new Set(sessions.filter(keepsStreakAlive).map((s) => localDayKey(s.at)))
  ).sort();
  if (dayKeys.length === 0) return 0;

  let maxStreak = 1;
  let currentStreak = 1;

  for (let i = 1; i < dayKeys.length; i++) {
    const [yPrev, mPrev, dPrev] = dayKeys[i - 1].split('-').map(Number);
    const prevDate = new Date(yPrev, mPrev - 1, dPrev);
    const expectedNext = new Date(prevDate);
    expectedNext.setDate(expectedNext.getDate() + 1);
    const expectedKey = localDayKey(expectedNext);

    if (dayKeys[i] === expectedKey) {
      currentStreak++;
      if (currentStreak > maxStreak) {
        maxStreak = currentStreak;
      }
    } else {
      currentStreak = 1;
    }
  }

  return maxStreak;
};

export const computeMetrics = (
  sessions: NormalizedSession[],
  now: Date = new Date(),
): MeditationMetrics => {
  const sits = sessions.filter(isCountableSit);
  const totalSeconds = sits.reduce((a, s) => a + s.durationSeconds, 0);
  const latest = sits.reduce<Date | null>(
    (acc, s) => (!acc || s.at.getTime() > acc.getTime() ? s.at : acc),
    null,
  );

  return {
    totalSessions: sits.length,
    totalMinutes: Math.round(totalSeconds / 60),
    totalCycles: sits.reduce((a, s) => a + s.breathCycles, 0),
    streakDays: computeStreak(sessions, now),
    longestStreakDays: computeLongestStreak(sessions),
    lastSessionDate: latest,
  };
};

export interface DayBucket {
  key: string;
  label: string;
  minutes: number;
  seconds: number;
}

/**
 * Trailing `days`-day series (oldest → newest) in local time. Seconds are
 * summed per day and rounded once, so the sparkline total always equals the
 * "N minutes over 7 days" caption.
 */
export const dailySeries = (
  sessions: NormalizedSession[],
  days = 7,
  now: Date = new Date(),
): DayBucket[] => {
  const secondsByDay = new Map<string, number>();
  for (const s of sessions.filter(isCountableSit)) {
    const key = localDayKey(s.at);
    secondsByDay.set(key, (secondsByDay.get(key) ?? 0) + s.durationSeconds);
  }

  const out: DayBucket[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    d.setDate(d.getDate() - i);
    const key = localDayKey(d);
    const seconds = secondsByDay.get(key) ?? 0;
    out.push({
      key,
      label: d.toLocaleDateString(undefined, { weekday: 'narrow' }),
      minutes: Math.round(seconds / 60),
      seconds,
    });
  }
  return out;
};
