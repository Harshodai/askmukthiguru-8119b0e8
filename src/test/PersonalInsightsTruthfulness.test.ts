import { describe, expect, it } from 'vitest';
import { derivePersonalInsights } from '@/lib/personalInsights';
import type { MeditationSession } from '@/lib/meditationStorage';

const session = (mood: MeditationSession['mood'], daysAgo: number): MeditationSession => ({
  id: `s-${daysAgo}`,
  startedAt: new Date(Date.now() - daysAgo * 24 * 60 * 60 * 1000),
  completedAt: new Date(Date.now() - daysAgo * 24 * 60 * 60 * 1000),
  durationSeconds: 900,
  breathCycles: 10,
  completed: true,
  mood,
});

describe('personal insight truthfulness', () => {
  it('describes mood movement without asserting an unmeasured spiritual state', () => {
    const insights = derivePersonalInsights({
      sessions: [
        session('calm', 0),
        session('calm', 1),
        session('calm', 2),
        session('anxious', 4),
        session('sad', 5),
      ],
    });

    const moodInsight = insights.find((insight) => insight.kind === 'mood_delta');
    expect(moodInsight?.text).toMatch(/reported mood|mood has been/i);
    expect(moodInsight?.text).not.toMatch(/beautiful state|witnessing presence|conflict transmuted/i);
  });
});
