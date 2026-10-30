import { localDayKey } from '@/lib/meditationMetrics';

/**
 * Optional daily journey: check-in → teaching → practice → reflection.
 * A step is only marked done when its own action is confirmed; skipping or
 * leaving never completes anything. State is per local day and per device.
 */
export type JourneyStep = 'checkin' | 'teaching' | 'practice' | 'reflection';

export const JOURNEY_STEPS: readonly JourneyStep[] = ['checkin', 'teaching', 'practice', 'reflection'];

export interface JourneyState {
  day: string;
  mood: string;
  practiceSlug?: string;
  done: Partial<Record<JourneyStep, number>>;
  skipped: boolean;
}

export const JOURNEY_KEY = 'askmukthiguru_daily_journey';
/** Fired on window when a step becomes done, so open banners can refresh. */
export const JOURNEY_EVENT = 'askmukthiguru:journey_updated';

const read = (): JourneyState | null => {
  try {
    const raw = localStorage.getItem(JOURNEY_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as JourneyState;
    return parsed && typeof parsed.day === 'string' && parsed.done ? parsed : null;
  } catch {
    return null;
  }
};

const write = (state: JourneyState): void => {
  try {
    localStorage.setItem(JOURNEY_KEY, JSON.stringify(state));
  } catch {
    // Storage may be unavailable (private mode, quota); the journey is best-effort.
  }
};

/** Today's journey, or null when none was started today. */
export const getJourney = (now: Date = new Date()): JourneyState | null => {
  const state = read();
  return state && state.day === localDayKey(now) ? state : null;
};

/** Start today's journey after a CONFIRMED check-in save. Replaces an older day's state. */
export const startJourney = (mood: string, practiceSlug?: string, now: Date = new Date()): JourneyState => {
  const state: JourneyState = {
    day: localDayKey(now),
    mood,
    practiceSlug,
    done: { checkin: now.getTime() },
    skipped: false,
  };
  write(state);
  return state;
};

/** Mark one step done. No-op without a started, unskipped journey for today. */
export const completeStep = (step: JourneyStep, now: Date = new Date()): JourneyState | null => {
  const state = getJourney(now);
  if (!state || state.skipped) return state;
  if (state.done[step]) return state;
  const next = { ...state, done: { ...state.done, [step]: now.getTime() } };
  write(next);
  try {
    window.dispatchEvent(new CustomEvent(JOURNEY_EVENT, { detail: { step } }));
  } catch {
    // Non-browser environments have no window; the state is already saved.
  }
  return next;
};

export const skipJourney = (now: Date = new Date()): void => {
  const state = getJourney(now);
  if (state) write({ ...state, skipped: true });
};

/**
 * First step not yet done, or null when finished or skipped. The practice step is
 * left out when the check-in offered no practice, so the journey never points at nothing.
 */
export const nextPendingStep = (state: JourneyState | null): JourneyStep | null => {
  if (!state || state.skipped) return null;
  return (
    JOURNEY_STEPS.find((s) => !state.done[s] && !(s === 'practice' && !state.practiceSlug)) ?? null
  );
};
