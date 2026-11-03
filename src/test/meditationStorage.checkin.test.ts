import { beforeEach, describe, expect, it, vi } from 'vitest';

const { from } = vi.hoisted(() => ({
  from: vi.fn(() => ({ insert: vi.fn().mockResolvedValue({}) })),
}));
vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: { getSession: vi.fn().mockResolvedValue({ data: { session: { user: { id: 'u1' } } } }) },
    from,
  },
}));

import {
  completeMeditationSession,
  getLastCompletedMeditationTimestamp,
  getMeditationStats,
  recordMoodCheckIn,
  startMeditationSession,
} from '@/lib/meditationStorage';

describe('mood check-in vs practice', () => {
  beforeEach(() => {
    localStorage.clear();
    from.mockClear();
  });

  it('does not change practice counts, minutes or streaks', async () => {
    await recordMoodCheckIn('anxious', 'tight chest');
    const stats = getMeditationStats();
    expect(stats.totalSessions).toBe(0);
    expect(stats.totalMinutes).toBe(0);
    expect(stats.streakDays).toBe(0);
  });

  it('does not stamp the Serene Mind cooldown sent to the backend', async () => {
    await recordMoodCheckIn('sad');
    expect(getLastCompletedMeditationTimestamp()).toBeNull();
  });

  it('does not write a fake completed session to the signed-in database', async () => {
    await recordMoodCheckIn('sad');
    expect(from).not.toHaveBeenCalled();
  });

  it('still stamps the cooldown and stores a real practice', async () => {
    const s = startMeditationSession();
    await completeMeditationSession(s.id, 300, 20, undefined, true);
    expect(getLastCompletedMeditationTimestamp()).not.toBeNull();
    expect(from).toHaveBeenCalledWith('meditation_sessions');
    expect(getMeditationStats().totalSessions).toBe(1);
  });
});
