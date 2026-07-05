import { describe, expect, it } from 'vitest';

import { buildGreeting, greetingPrefix, greetingSuffix, timeOfDay } from '@/lib/greeting';

const at = (hour: number) => new Date(2026, 6, 5, hour, 30, 0);

describe('timeOfDay', () => {
  it('maps hours to the four windows', () => {
    expect(timeOfDay(at(5))).toBe('morning');
    expect(timeOfDay(at(11))).toBe('morning');
    expect(timeOfDay(at(12))).toBe('afternoon');
    expect(timeOfDay(at(16))).toBe('afternoon');
    expect(timeOfDay(at(17))).toBe('evening');
    expect(timeOfDay(at(20))).toBe('evening');
    expect(timeOfDay(at(21))).toBe('night');
    expect(timeOfDay(at(4))).toBe('night');
  });
});

describe('greetingPrefix', () => {
  it('uses Indic time greetings for Preethaji/Krishnaji personas', () => {
    expect(greetingPrefix('sri_preethaji', at(8))).toBe('Suprabhat');
    expect(greetingPrefix('sri_krishnaji', at(14))).toBe('Namaste');
    expect(greetingPrefix('sri_preethaji', at(18))).toBe('Shubh Sandhya');
    expect(greetingPrefix('sri_krishnaji', at(23))).toBe('Namaste');
  });

  it('always greets Namaskaram for Sadhguru regardless of hour', () => {
    expect(greetingPrefix('sadhguru', at(8))).toBe('Namaskaram');
    expect(greetingPrefix('sadhguru', at(19))).toBe('Namaskaram');
  });

  it('falls back to time greeting for unknown personas', () => {
    expect(greetingPrefix(undefined, at(8))).toBe('Suprabhat');
  });
});

describe('greetingSuffix', () => {
  it('adds ", {name} Ji" for Preethaji/Krishnaji personas', () => {
    expect(greetingSuffix('sri_preethaji', 'Harshoda')).toBe(', Harshoda Ji');
    expect(greetingSuffix('sri_krishnaji', 'Harshoda')).toBe(', Harshoda Ji');
  });

  it('adds " Ji" without a name for Ji personas', () => {
    expect(greetingSuffix('sri_preethaji', '')).toBe(' Ji');
  });

  it('omits Ji for Sadhguru and unknown personas', () => {
    expect(greetingSuffix('sadhguru', 'Harshoda')).toBe(', Harshoda');
    expect(greetingSuffix(undefined, 'Harshoda')).toBe(', Harshoda');
    expect(greetingSuffix('sadhguru', '')).toBe('');
  });
});

describe('buildGreeting', () => {
  it('composes the full display greeting', () => {
    expect(buildGreeting('sri_preethaji', 'Harshoda', at(7))).toBe('Suprabhat, Harshoda Ji');
    expect(buildGreeting('sri_krishnaji', 'Harshoda', at(18))).toBe('Shubh Sandhya, Harshoda Ji');
    expect(buildGreeting('sadhguru', 'Harshoda', at(7))).toBe('Namaskaram, Harshoda');
  });
});
