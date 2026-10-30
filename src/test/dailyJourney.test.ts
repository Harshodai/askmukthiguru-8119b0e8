import { beforeEach, describe, expect, it } from 'vitest';
import {
  completeStep,
  getJourney,
  nextPendingStep,
  skipJourney,
  startJourney,
} from '@/lib/dailyJourney';

const noon = (day: number) => new Date(2026, 9, day, 12, 0, 0);

describe('dailyJourney', () => {
  beforeEach(() => localStorage.clear());

  it('has no journey before a confirmed check-in', () => {
    expect(getJourney(noon(30))).toBeNull();
    expect(completeStep('practice', noon(30))).toBeNull();
  });

  it('starts with only the check-in done; later steps stay pending', () => {
    const state = startJourney('anxious', 'serene-mind', noon(30));
    expect(Object.keys(state.done)).toEqual(['checkin']);
    expect(nextPendingStep(state)).toBe('teaching');
  });

  it('marks only the step that was confirmed', () => {
    startJourney('sad', 'beautiful-state', noon(30));
    const next = completeStep('practice', noon(30));
    expect(next?.done.practice).toBeDefined();
    expect(next?.done.teaching).toBeUndefined();
    expect(next?.done.reflection).toBeUndefined();
  });

  it('resumes after reload on the same day and expires the next day', () => {
    startJourney('calm', 'soul-sync', noon(30));
    expect(getJourney(noon(30))?.practiceSlug).toBe('soul-sync');
    expect(getJourney(noon(31))).toBeNull();
  });

  it('skip ends the journey without completing anything', () => {
    startJourney('open', 'daily-reflection', noon(30));
    skipJourney(noon(30));
    const state = getJourney(noon(30));
    expect(nextPendingStep(state)).toBeNull();
    expect(completeStep('practice', noon(30))?.done.practice).toBeUndefined();
  });

  it('tolerates corrupt stored state', () => {
    localStorage.setItem('askmukthiguru_daily_journey', '{not json');
    expect(getJourney(noon(30))).toBeNull();
  });

  it('skips the practice step when the check-in offered no practice', () => {
    const state = startJourney('calm', undefined, noon(30));
    completeStep('teaching', noon(30));
    expect(nextPendingStep(getJourney(noon(30)))).toBe('reflection');
    expect(state.practiceSlug).toBeUndefined();
  });

  it('emits an event only when a step newly becomes done', () => {
    startJourney('calm', 'beautiful-state', noon(30));
    const seen: string[] = [];
    const on = (e: Event) => seen.push((e as CustomEvent).detail.step);
    window.addEventListener('askmukthiguru:journey_updated', on);
    completeStep('teaching', noon(30));
    completeStep('teaching', noon(30));
    window.removeEventListener('askmukthiguru:journey_updated', on);
    expect(seen).toEqual(['teaching']);
  });
});
