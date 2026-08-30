import { describe, expect, it } from 'vitest';
import { getPracticeIntensity } from '@/components/profile/SadhanaHeatmap';

describe('getPracticeIntensity', () => {
  it('uses only measured minutes to choose an activity bucket', () => {
    expect(getPracticeIntensity(0)).toBe('rest');
    expect(getPracticeIntensity(1)).toBe('short');
    expect(getPracticeIntensity(9)).toBe('short');
    expect(getPracticeIntensity(10)).toBe('steady');
    expect(getPracticeIntensity(19)).toBe('steady');
    expect(getPracticeIntensity(20)).toBe('deep');
    expect(getPracticeIntensity(60)).toBe('deep');
  });

  it('does not expose any consciousness-state classification', () => {
    const valid = new Set(['rest', 'short', 'steady', 'deep']);
    for (const minutes of [0, 3, 8, 10, 15, 20, 45, 90]) {
      expect(valid.has(getPracticeIntensity(minutes))).toBe(true);
    }
  });
});
