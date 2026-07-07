/**
 * Time-of-day + persona-aware greeting helpers with spiritual variants.
 *
 * Design intent: greetings feel like a devotional welcome, not a generic
 * "Good morning". Ships a deterministic (per-day) rotation of spiritual
 * lines rooted in Sri Preethaji & Sri Krishnaji's teachings.
 */

export type TimeOfDay = 'morning' | 'afternoon' | 'evening' | 'night';

const MORNING_START_HOUR = 5;
const AFTERNOON_START_HOUR = 12;
const EVENING_START_HOUR = 17;
const NIGHT_START_HOUR = 21;

const JI_PERSONAS = new Set(['sri_preethaji', 'sri_krishnaji', 'general', 'relationship', 'sky']);

/** Spiritual greeting lines rotated deterministically by day-of-year. */
const SPIRITUAL_GREETINGS: Record<TimeOfDay, readonly string[]> = {
  morning: [
    'Suprabhat',
    'A calm morning to you',
    'May this morning meet you in stillness',
    'Namaste — begin gently',
  ],
  afternoon: [
    'Namaste',
    'May this hour hold you kindly',
    'Rest into this afternoon',
    'Peace to you',
  ],
  evening: [
    'Shubh Sandhya',
    'A soft evening to you',
    'Let the day settle',
    'Peace, as the light softens',
  ],
  night: [
    'Shubh Ratri',
    'Rest well tonight',
    'May the night be gentle',
    'Namaste — carry stillness into rest',
  ],
};

const SADHGURU_GREETINGS: Record<TimeOfDay, readonly string[]> = {
  morning: ['Namaskaram', 'A blissful morning to you', 'Namaskaram — receive the morning'],
  afternoon: ['Namaskaram', 'Namaskaram — a still afternoon'],
  evening: ['Namaskaram', 'Namaskaram — a graceful evening'],
  night: ['Namaskaram', 'Namaskaram — rest deeply'],
};

export const timeOfDay = (date: Date = new Date()): TimeOfDay => {
  const hour = date.getHours();
  if (hour >= MORNING_START_HOUR && hour < AFTERNOON_START_HOUR) return 'morning';
  if (hour >= AFTERNOON_START_HOUR && hour < EVENING_START_HOUR) return 'afternoon';
  if (hour >= EVENING_START_HOUR && hour < NIGHT_START_HOUR) return 'evening';
  return 'night';
};

/** Day-of-year (0-365) — stable seed so the greeting doesn't flicker across renders. */
const dayOfYear = (date: Date): number => {
  const start = new Date(date.getFullYear(), 0, 0);
  return Math.floor((date.getTime() - start.getTime()) / 86_400_000);
};

export const greetingPrefix = (slug: string | undefined, date: Date = new Date()): string => {
  const tod = timeOfDay(date);
  const pool = slug === 'sadhguru' ? SADHGURU_GREETINGS[tod] : SPIRITUAL_GREETINGS[tod];
  return pool[dayOfYear(date) % pool.length];
};

/** Returns only the first word/token of a display name. "Harshoda Kolluru" → "Harshoda". */
export const firstName = (name: string): string => {
  const trimmed = (name ?? '').trim();
  return trimmed.split(/\s+/)[0] ?? '';
};

export const greetingSuffix = (slug: string | undefined, name: string): string => {
  const first = firstName(name);
  if (slug && JI_PERSONAS.has(slug)) return first ? `, ${first} Ji` : '';
  return first ? `, ${first}` : '';
};

/** Full display greeting, e.g. "Suprabhat, Harshoda Ji" (always uses first name only). */
export const buildGreeting = (slug: string | undefined, name: string, date: Date = new Date()): string =>
  `${greetingPrefix(slug, date)}${greetingSuffix(slug, name)}`;

/** A short spiritual sub-line to appear under the greeting on empty state. */
const SUB_LINES: readonly string[] = [
  'Ask anything about the teachings, practices, or your journey.',
  'What is stirring in your heart today?',
  'Bring your question — the teachings will meet you.',
  'Speak from where you are. Silence is also welcome.',
  'What would you like to sit with today?',
];

export const buildGreetingSubline = (date: Date = new Date()): string =>
  SUB_LINES[dayOfYear(date) % SUB_LINES.length];
