import { describe, expect, it } from 'vitest';

import {
  buildGreeting,
  buildGreetingSubline,
  firstName,
  greetingPrefix,
  greetingSuffix,
  timeOfDay,
} from '@/lib/greeting';

const at = (hour: number) => new Date(2026, 6, 5, hour, 30, 0); // Jul 5 2026

// ─── timeOfDay ────────────────────────────────────────────────────────────────
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

// ─── firstName ────────────────────────────────────────────────────────────────
describe('firstName', () => {
  it('returns only the first word', () => {
    expect(firstName('Harshoda Kolluru')).toBe('Harshoda');
    expect(firstName('Harshoda')).toBe('Harshoda');
    expect(firstName('  Sri Preethaji  ')).toBe('Sri');
    expect(firstName('')).toBe('');
    expect(firstName('   ')).toBe('');
  });
});

// ─── greetingSuffix ───────────────────────────────────────────────────────────
describe('greetingSuffix', () => {
  it('adds ", {firstName} Ji" for Ji personas', () => {
    expect(greetingSuffix('sri_preethaji', 'Harshoda')).toBe(', Harshoda Ji');
    expect(greetingSuffix('sri_krishnaji', 'Harshoda Kolluru')).toBe(', Harshoda Ji');
  });

  it('returns empty string without a name for Ji personas', () => {
    expect(greetingSuffix('sri_preethaji', '')).toBe('');
  });

  it('omits Ji for Sadhguru and unknown personas', () => {
    expect(greetingSuffix('sadhguru', 'Harshoda')).toBe(', Harshoda');
    expect(greetingSuffix(undefined, 'Harshoda')).toBe(', Harshoda');
    expect(greetingSuffix('sadhguru', '')).toBe('');
  });
});

// ─── greetingPrefix (English-only, context-aware) ────────────────────────────
describe('greetingPrefix', () => {
  it('returns a non-empty English string for every persona × context × tod combo', () => {
    const slugs = ['sri_preethaji', 'sri_krishnaji', 'sadhguru', 'general', undefined];
    const contexts = ['first_visit', 'return_same_day', 'return_new_day'] as const;
    const hours = [6, 13, 18, 22];

    for (const slug of slugs) {
      for (const context of contexts) {
        for (const hour of hours) {
          const result = greetingPrefix(slug, context, at(hour));
          expect(result.length).toBeGreaterThan(5);
          // Must not contain common Indic terms
          expect(result).not.toMatch(/suprabhat|namaste|namaskaram|shubh/i);
        }
      }
    }
  });

  it('returns "first_visit" welcome string for first visit', () => {
    const result = greetingPrefix('sri_preethaji', 'first_visit', at(8));
    expect(result.toLowerCase()).toContain('welcome');
  });

  it('returns "return_same_day" string for same-day return', () => {
    const result = greetingPrefix('sri_preethaji', 'return_same_day', at(8));
    expect(result.toLowerCase()).toMatch(/good to have you back|welcome back/);
  });
});

// ─── buildGreeting ────────────────────────────────────────────────────────────
describe('buildGreeting', () => {
  it('composes greeting with first name only, English terms', () => {
    const g = buildGreeting('sri_preethaji', 'Harshoda Kolluru', 'return_new_day', at(7));
    expect(g).toContain('Harshoda Ji');
    expect(g).not.toContain('Kolluru');
    expect(g).not.toMatch(/suprabhat|namaste|namaskaram/i);
  });

  it('produces a welcome greeting on first visit', () => {
    const g = buildGreeting('general', 'Harshoda', 'first_visit', at(9));
    expect(g.toLowerCase()).toContain('welcome');
  });
});

// ─── buildGreetingSubline ────────────────────────────────────────────────────
describe('buildGreetingSubline', () => {
  it('returns different pools per context', () => {
    const first = buildGreetingSubline('first_visit');
    const same  = buildGreetingSubline('return_same_day');
    const newDay = buildGreetingSubline('return_new_day');

    // First visit — should mention space / welcome
    expect(first.toLowerCase()).toMatch(/space|welcome|ask/);
    // Same day — should reference returning
    expect(same.toLowerCase()).toMatch(/back|continue|still|left off/);
    // New day — should encourage new inquiry
    expect(newDay.length).toBeGreaterThan(5);
  });
});
