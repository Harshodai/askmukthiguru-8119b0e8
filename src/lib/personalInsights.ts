/**
 * Personal insights derivation.
 *
 * Every insight is derived only from observed practice/memory data. The copy is
 * intentionally careful not to turn a proxy signal (for example mood history)
 * into an unmeasured spiritual-state claim.
 */

import type { MeditationSession } from '@/lib/meditationStorage';
import type { GuruMemory } from '@/lib/memoryApi';

export type InsightKind =
  | 'rhythm'
  | 'time_of_day'
  | 'mood_delta'
  | 'memory_echo'
  | 'streak'
  | 'welcome';

export interface PersonalInsight {
  kind: InsightKind;
  /** Human-readable, ≤140 chars. */
  text: string;
  /** Lower = more important. UI sorts ascending. */
  weight: number;
}

const DAY_MS = 24 * 60 * 60 * 1000;

const MOOD_SCORE: Record<string, number> = {
  calm: 1,
  anxious: -2,
  sad: -1,
  frustrated: -2,
  open: 0,
};

function startOfDay(d: Date): number {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x.getTime();
}

function sessionsWithin(
  sessions: MeditationSession[],
  days: number,
  now = Date.now(),
): MeditationSession[] {
  const cutoff = now - days * DAY_MS;
  return sessions.filter((s) => {
    const t = (s.completedAt ?? s.startedAt).getTime?.() ?? 0;
    return s.completed && t >= cutoff;
  });
}

function rhythmInsight(sessions: MeditationSession[]): PersonalInsight | null {
  const thisWeek = sessionsWithin(sessions, 7).length;
  const lastWeek = sessionsWithin(sessions, 14).length - thisWeek;
  if (thisWeek === 0 && lastWeek === 0) return null;
  if (thisWeek > lastWeek && lastWeek >= 0) {
    return {
      kind: 'rhythm',
      text:
        lastWeek === 0
          ? `You've practiced ${thisWeek}× this week — a new beginning.`
          : `You've practiced ${thisWeek}× this week vs ${lastWeek}× last week. The rhythm is deepening.`,
      weight: 2,
    };
  }
  if (thisWeek < lastWeek) {
    return {
      kind: 'rhythm',
      text: `${lastWeek - thisWeek} fewer sessions this week. A short pause can also be a teacher.`,
      weight: 3,
    };
  }
  return {
    kind: 'rhythm',
    text: `Steady at ${thisWeek} sessions this week. Consistency is its own kind of grace.`,
    weight: 4,
  };
}

function timeOfDayInsight(sessions: MeditationSession[]): PersonalInsight | null {
  const recent = sessionsWithin(sessions, 30);
  if (recent.length < 3) return null;
  const buckets = { morning: 0, afternoon: 0, evening: 0, night: 0 };
  for (const s of recent) {
    const hour = (s.completedAt ?? s.startedAt).getHours?.() ?? 0;
    if (hour < 6) buckets.night += 1;
    else if (hour < 12) buckets.morning += 1;
    else if (hour < 17) buckets.afternoon += 1;
    else if (hour < 22) buckets.evening += 1;
    else buckets.night += 1;
  }
  const dominant = Object.entries(buckets).sort((a, b) => b[1] - a[1])[0];
  const total = recent.length;
  if (!dominant || dominant[1] / total < 0.5) return null;
  const labels: Record<string, string> = {
    morning: 'in the early hours',
    afternoon: 'in the afternoon',
    evening: 'in the evening',
    night: 'in the quiet of night',
  };
  return {
    kind: 'time_of_day',
    text: `You tend to find stillness ${labels[dominant[0]]} — a window you return to often.`,
    weight: 5,
  };
}

function moodDeltaInsight(sessions: MeditationSession[]): PersonalInsight | null {
  const withMood = sessions
    .filter((s) => s.completed && s.mood)
    .sort((a, b) => {
      const ta = (a.completedAt ?? a.startedAt).getTime?.() ?? 0;
      const tb = (b.completedAt ?? b.startedAt).getTime?.() ?? 0;
      return tb - ta;
    });
  if (withMood.length < 4) return null;
  const recent = withMood.slice(0, 3);
  const prior = withMood.slice(3, 8);
  if (prior.length === 0) return null;
  const avg = (arr: MeditationSession[]) =>
    arr.reduce((s, x) => s + (MOOD_SCORE[x.mood ?? ''] ?? 0), 0) / arr.length;
  const delta = avg(recent) - avg(prior);
  if (Math.abs(delta) < 0.6) return null;
  if (delta > 0) {
    return {
      kind: 'mood_delta',
      text: 'Your reported mood has been trending lighter across recent sessions.',
      weight: 1,
    };
  }
  return {
    kind: 'mood_delta',
    text: 'Your reported mood has been heavier across recent sessions. Meeting it gently may help.',
    weight: 1,
  };
}

function memoryEchoInsight(memories: GuruMemory[]): PersonalInsight | null {
  if (!memories || memories.length === 0) return null;
  const ranked = [...memories]
    .filter((m) => (m.decay_score ?? 0) > 0.3)
    .sort(
      (a, b) =>
        (b.decay_score ?? 0) * (b.confidence ?? 0) -
        (a.decay_score ?? 0) * (a.confidence ?? 0),
    );
  const top = ranked[0];
  if (!top) return null;
  return {
    kind: 'memory_echo',
    text: `You once shared: "${top.claim ?? top.content}". Has anything shifted since?`,
    weight: 2,
  };
}

function streakInsight(sessions: MeditationSession[]): PersonalInsight | null {
  if (sessions.length === 0) return null;
  const dayStamps = new Set(
    sessions
      .filter((s) => s.completed)
      .map((s) => startOfDay(s.completedAt ?? s.startedAt)),
  );
  let streak = 0;
  let cursor = startOfDay(new Date());
  if (!dayStamps.has(cursor)) cursor -= DAY_MS;
  while (dayStamps.has(cursor)) {
    streak += 1;
    cursor -= DAY_MS;
  }
  if (streak < 3) return null;
  return {
    kind: 'streak',
    text: `${streak} days of completed practice in a row. Small returns add up.`,
    weight: 3,
  };
}

export interface DeriveInsightsInput {
  sessions: MeditationSession[];
  memories?: GuruMemory[];
}

export const derivePersonalInsights = ({
  sessions,
  memories = [],
}: DeriveInsightsInput): PersonalInsight[] => {
  const completed = sessions.filter((s) => s.completed);
  if (completed.length === 0 && memories.length === 0) {
    return [
      {
        kind: 'welcome',
        text: 'Your practice record is just beginning. Each completed session adds a clearer picture of your rhythm.',
        weight: 10,
      },
    ];
  }

  const raw = [
    moodDeltaInsight(completed),
    memoryEchoInsight(memories),
    rhythmInsight(completed),
    streakInsight(completed),
    timeOfDayInsight(completed),
  ].filter((x): x is PersonalInsight => x !== null);

  return raw.sort((a, b) => a.weight - b.weight).slice(0, 4);
};
