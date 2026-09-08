import { describe, it, expect } from 'vitest';
import { getPracticeIntensity } from '@/components/profile/SadhanaHeatmap';

describe('Sadhana practice intensity', () => {
  it('derives intensity only from measured completed minutes', () => {
    expect(getPracticeIntensity(0)).toBe('rest');
    expect(getPracticeIntensity(1)).toBe('short');
    expect(getPracticeIntensity(9)).toBe('short');
    expect(getPracticeIntensity(10)).toBe('steady');
    expect(getPracticeIntensity(19)).toBe('steady');
    expect(getPracticeIntensity(20)).toBe('deep');
    expect(getPracticeIntensity(90)).toBe('deep');
  });

  it('never emits Beautiful State, Witnessing, or Conflict Transmuted classifications', () => {
    const allowed = new Set(['rest', 'short', 'steady', 'deep']);
    for (const minutes of [0, 3, 8, 10, 15, 20, 45, 90]) {
      expect(allowed.has(getPracticeIntensity(minutes))).toBe(true);
    }
  });
});
