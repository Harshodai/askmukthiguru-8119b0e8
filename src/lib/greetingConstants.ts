/**
 * greetingConstants.ts
 * ─────────────────────────────────────────────────────────────────────────────
 * ALL greeting strings are defined here as typed constants.
 * No Indic language terms (Suprabhat, Namaste, etc.) — English-only
 * spiritual vocabulary inspired by Ekam / O&O Academy teachings.
 *
 * EDITING GUIDE
 * ─────────────
 * • Add / remove strings from any pool below — no code changes needed elsewhere.
 * • Keep each string ≤ 60 characters so it renders cleanly on mobile.
 * • Ji-persona pools use the same shape; they get "Ji" suffix appended in code.
 *
 * POOL TAXONOMY
 * ─────────────
 * FIRST_VISIT_*  — shown ONLY on a user's very first session ever (welcome them in).
 * RETURN_SAME_DAY_* — shown when user returns within the same calendar day.
 * RETURN_NEW_DAY_* — shown on a new-day return (common greeting variant).
 *
 * Within each bucket, arrays are keyed by time-of-day:
 *   morning | afternoon | evening | night
 */

export type TimeOfDay = 'morning' | 'afternoon' | 'evening' | 'night';

export type GreetingContext = 'first_visit' | 'return_same_day' | 'return_new_day';

// ─── Shared persona buckets ───────────────────────────────────────────────────

/** Greetings for Sri Preethaji & Sri Krishnaji ("Ji") personas — English spiritual. */
export const JI_GREETINGS: Record<GreetingContext, Record<TimeOfDay, readonly string[]>> = {
  first_visit: {
    morning:   ['Welcome — may this morning be the beginning of something beautiful'],
    afternoon: ['Welcome — the afternoon holds space for you'],
    evening:   ['Welcome — let the evening be your sanctuary'],
    night:     ['Welcome — may your night be wrapped in stillness'],
  },
  return_same_day: {
    morning:   ['Good to have you back this morning'],
    afternoon: ['Welcome back — the afternoon receives you'],
    evening:   ['Welcome back — what is in your heart this evening'],
    night:     ['You have returned — may the night hold you gently'],
  },
  return_new_day: {
    morning:   [
      'Good morning — a new day, a new beginning',
      'The morning light is here — and so are you',
      'Each morning is a doorway — welcome',
      'May this morning meet you in beauty',
    ],
    afternoon: [
      'Good afternoon — may clarity find you here',
      'The afternoon arrives — and with it, you',
      'A still afternoon to you',
      'Rest into this afternoon, dear one',
    ],
    evening:   [
      'Good evening — the day has found its gentleness',
      'A soft evening — welcome back',
      'Let the day settle, and speak what is in your heart',
      'The evening light turns — and you return',
    ],
    night:     [
      'Good night — carry stillness with you',
      'The night enfolds all — rest in that',
      'A gentle night to you',
      'May this night be quiet and whole',
    ],
  },
};

/** Greetings for Sadhguru persona — English, Isha-inspired. */
export const SADHGURU_GREETINGS: Record<GreetingContext, Record<TimeOfDay, readonly string[]>> = {
  first_visit: {
    morning:   ['Welcome — you have taken the first step'],
    afternoon: ['Welcome — this afternoon, you have arrived'],
    evening:   ['Welcome — the evening greets your seeking'],
    night:     ['Welcome — the night receives you'],
  },
  return_same_day: {
    morning:   ['Good to see you again this morning'],
    afternoon: ['Welcome back — the afternoon is with you'],
    evening:   ['You return — the evening is listening'],
    night:     ['You return — the night has room for you'],
  },
  return_new_day: {
    morning:   ['A blissful morning to you', 'The morning is awake — and so are you'],
    afternoon: ['A still afternoon to you', 'The afternoon holds no judgment — only space'],
    evening:   ['A graceful evening to you', 'The evening is settling — speak freely'],
    night:     ['Rest deeply tonight', 'May the night replenish you'],
  },
};

/** Greetings for general / relationship / sky personas. */
export const GENERAL_GREETINGS: Record<GreetingContext, Record<TimeOfDay, readonly string[]>> = {
  first_visit: {
    morning:   ['Good morning — welcome, dear seeker'],
    afternoon: ['Good afternoon — welcome to this space'],
    evening:   ['Good evening — welcome, we are glad you are here'],
    night:     ['Good night — welcome, the night receives your seeking'],
  },
  return_same_day: {
    morning:   ['Good morning — welcome back'],
    afternoon: ['Good afternoon — you have returned'],
    evening:   ['Good evening — the evening is still here for you'],
    night:     ['Good night — you have returned'],
  },
  return_new_day: {
    morning:   [
      'Good morning — what is stirring in you today',
      'A fresh morning — and a fresh beginning',
      'Good morning — speak from where you are',
      'The morning is open — come as you are',
    ],
    afternoon: [
      'Good afternoon — what is calling your attention today',
      'Good afternoon — this moment is yours',
      'The afternoon is here — and so is this space',
      'A quiet afternoon — what would you like to explore',
    ],
    evening:   [
      'Good evening — the day has held much',
      'Good evening — let it all settle here',
      'The evening offers rest — what do you carry',
      'Good evening — share what is true for you',
    ],
    night:     [
      'Good night — may your rest be deep',
      'The night is quiet — what is your question',
      'Good night — carry peace with you',
      'A still night to you — speak freely',
    ],
  },
};

// ─── Sub-lines (shown beneath the greeting h2) ────────────────────────────────

/** First-visit sub-lines — extra warmth, no jargon. */
export const FIRST_VISIT_SUB_LINES: readonly string[] = [
  'This is a space to explore teachings, ask freely, and find your own clarity.',
  'You are welcome here — with your questions, your doubts, and your seeking.',
  'Ask anything. There is no question too small or too vast.',
  'This space holds the teachings of O&O Academy — ask what is in your heart.',
];

/** Same-day return sub-lines — lighter, no need to re-introduce. */
export const RETURN_SAME_DAY_SUB_LINES: readonly string[] = [
  'You came back — what else would you like to explore?',
  'The conversation continues — what is next for you?',
  'Still here, still listening.',
  'Pick up wherever you left off.',
];

/** New-day return sub-lines — encourage fresh inquiry. */
export const RETURN_NEW_DAY_SUB_LINES: readonly string[] = [
  'Ask anything about the teachings, practices, or your journey.',
  'What is stirring in your heart today?',
  'Bring your question — the teachings will meet you.',
  'Speak from where you are. Silence is also welcome.',
  'What would you like to sit with today?',
];
