/**
 * Time-of-day + persona-aware greeting helpers.
 *
 * Personas:
 *  - Sri Preethaji / Sri Krishnaji → Indic time greeting + ", {name} Ji"
 *  - Sadhguru                      → always "Namaskaram" + ", {name}" (no Ji)
 */

export type TimeOfDay = 'morning' | 'afternoon' | 'evening' | 'night';

const MORNING_START_HOUR = 5;
const AFTERNOON_START_HOUR = 12;
const EVENING_START_HOUR = 17;
const NIGHT_START_HOUR = 21;

const TIME_GREETINGS: Record<TimeOfDay, string> = {
  morning: 'Suprabhat',
  afternoon: 'Namaste',
  evening: 'Shubh Sandhya',
  night: 'Namaste',
};

const JI_PERSONAS = new Set(['sri_preethaji', 'sri_krishnaji']);

export const timeOfDay = (date: Date = new Date()): TimeOfDay => {
  const hour = date.getHours();
  if (hour >= MORNING_START_HOUR && hour < AFTERNOON_START_HOUR) return 'morning';
  if (hour >= AFTERNOON_START_HOUR && hour < EVENING_START_HOUR) return 'afternoon';
  if (hour >= EVENING_START_HOUR && hour < NIGHT_START_HOUR) return 'evening';
  return 'night';
};

export const greetingPrefix = (slug: string | undefined, date: Date = new Date()): string => {
  if (slug === 'sadhguru') return 'Namaskaram';
  return TIME_GREETINGS[timeOfDay(date)];
};

export const greetingSuffix = (slug: string | undefined, name: string): string => {
  const trimmed = (name ?? '').trim();
  if (slug && JI_PERSONAS.has(slug)) return trimmed ? `, ${trimmed} Ji` : ' Ji';
  return trimmed ? `, ${trimmed}` : '';
};

/** Full display greeting, e.g. "Suprabhat, Harshoda Ji". */
export const buildGreeting = (slug: string | undefined, name: string, date: Date = new Date()): string =>
  `${greetingPrefix(slug, date)}${greetingSuffix(slug, name)}`;
