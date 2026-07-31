import { describe, it, expect } from 'vitest';
import {
  computeMetrics,
  computeStreak,
  dailySeries,
  localDayKey,
  type NormalizedSession,
} from '@/lib/meditationMetrics';

const NOW = new Date(2026, 6, 31, 23, 30); // 31 Jul 2026, 11:30pm local
const daysAgo = (n: number, hour = 21) => {
  const d = new Date(NOW.getFullYear(), NOW.getMonth(), NOW.getDate(), hour);
  d.setDate(d.getDate() - n);
  return d;
};
const sit = (at: Date, durationSeconds: number, breathCycles = 0, completed = true): NormalizedSession => ({
  at,
  durationSeconds,
  breathCycles,
  completed,
});

describe('meditationMetrics', () => {
  it('buckets a late-night sit on the local day, not the UTC day', () => {
    // 11:30pm local in IST is already "tomorrow" in UTC — the old bug.
    expect(localDayKey(NOW)).toBe('2026-07-31');
  });

  it('excludes zero-duration mood check-ins from every total', () => {
    const m = computeMetrics([sit(daysAgo(0), 180, 12), sit(daysAgo(0), 0, 0)], NOW);
    expect(m.totalSessions).toBe(1);
    expect(m.totalCycles).toBe(12);
  });

  it('rounds minutes once over summed seconds', () => {
    // Six 40s sits = 240s = 4 minutes, not 6 (per-session rounding bug).
    const sessions = Array.from({ length: 6 }, () => sit(daysAgo(0), 40));
    expect(computeMetrics(sessions, NOW).totalMinutes).toBe(4);
  });

  it('counts consecutive local days', () => {
    expect(computeStreak([sit(daysAgo(0), 120), sit(daysAgo(1), 120), sit(daysAgo(2), 120)], NOW)).toBe(3);
  });

  it("keeps the streak alive when today's sit hasn't happened yet", () => {
    expect(computeStreak([sit(daysAgo(1), 120), sit(daysAgo(2), 120)], NOW)).toBe(2);
  });

  it('breaks the streak after a two-day gap', () => {
    expect(computeStreak([sit(daysAgo(3), 120), sit(daysAgo(4), 120)], NOW)).toBe(0);
  });

  it('does not let a mood check-in prop up a streak', () => {
    expect(computeStreak([sit(daysAgo(0), 0)], NOW)).toBe(0);
  });

  it('daily series total matches the summed-seconds caption', () => {
    const sessions = [sit(daysAgo(0), 100), sit(daysAgo(0), 100), sit(daysAgo(3), 200)];
    const series = dailySeries(sessions, 7, NOW);
    expect(series).toHaveLength(7);
    expect(series[6].seconds).toBe(200);
    const total = Math.round(series.reduce((s, d) => s + d.seconds, 0) / 60);
    expect(total).toBe(computeMetrics(sessions, NOW).totalMinutes);
  });
});
