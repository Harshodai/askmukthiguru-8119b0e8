const WELCOME_DISMISS_KEY = 'askmukthiguru_welcome_dismissed';

const SPIRITUAL_LINES = [
  "The Beautiful State is not a place to reach, but a truth to realize.",
  "Every breath is an invitation to awaken.",
  "Peace is not the absence of noise, but the presence of stillness.",
  "Suffering is not the truth of who you are.",
  "In stillness, the heart finds its voice.",
  "The journey inward is the greatest adventure.",
  "Let go of what you think you are, and discover what you truly are.",
  "Your inner silence is the doorway to infinite wisdom.",
];

let cachedLine: string | null = null;
let cachedDate = '';

function getTodaySeed(): string {
  return new Date().toISOString().slice(0, 10);
}

function pickDailyLine(): string {
  const today = getTodaySeed();
  if (cachedLine && cachedDate === today) return cachedLine;
  const dayOfYear = Math.floor(
    (Date.now() - new Date(new Date().getFullYear(), 0, 0).getTime()) / 86400000
  );
  cachedLine = SPIRITUAL_LINES[dayOfYear % SPIRITUAL_LINES.length];
  cachedDate = today;
  return cachedLine;
}

export function getDailySpiritualLine(): string {
  return pickDailyLine();
}

export function isWelcomeDismissed(): boolean {
  try {
    const dismissed = localStorage.getItem(WELCOME_DISMISS_KEY);
    if (!dismissed) return false;
    const parsed = JSON.parse(dismissed);
    return parsed === getTodaySeed();
  } catch {
    return false;
  }
}

export function dismissWelcome(): void {
  try {
    localStorage.setItem(WELCOME_DISMISS_KEY, JSON.stringify(getTodaySeed()));
  } catch {
  }
}

export function resetWelcome(): void {
  try {
    localStorage.removeItem(WELCOME_DISMISS_KEY);
  } catch {
  }
}
