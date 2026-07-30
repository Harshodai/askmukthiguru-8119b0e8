/**
 * Healing Paths — a short, sequenced course of Sri Preethaji & Sri Krishnaji's
 * teachings prescribed when a seeker is detected to be in a state of suffering.
 *
 * Curriculum lives in code (versioned, reviewable, no admin UI needed);
 * only per-seeker progress is persisted (public.user_course_progress).
 */

export type SufferingSignal =
  | 'grief'
  | 'anxiety'
  | 'anger'
  | 'loneliness'
  | 'meaninglessness'
  | 'general';

export interface HealingLesson {
  id: string;
  title: string;
  /** One-line intention the seeker reads before the lesson. */
  intention: string;
  /** Minutes of practice/listening. */
  minutes: number;
  /** Optional discourse to listen to. */
  videoUrl?: string;
  /** Prompt auto-sent to the guru when the seeker opens this lesson. */
  guruPrompt: string;
  /** Opens the Serene Mind player instead of a chat turn. */
  practice?: 'serene-mind';
}

export interface HealingCourse {
  slug: string;
  title: string;
  subtitle: string;
  signals: SufferingSignal[];
  lessons: HealingLesson[];
}

export const HEALING_COURSES: HealingCourse[] = [
  {
    slug: 'end-of-suffering',
    title: 'The End of Suffering',
    subtitle: 'Four days from self-centric thinking to the beautiful state.',
    signals: ['general', 'meaninglessness'],
    lessons: [
      {
        id: 'es-1',
        title: 'Seeing the two states',
        intention: 'Notice, without judgement, which state you are living in right now.',
        minutes: 6,
        guruPrompt: 'Teach me the difference between the stressful state and the beautiful state, as Sri Preethaji describes it.',
      },
      {
        id: 'es-2',
        title: 'The inner truth of suffering',
        intention: 'All lingering suffering is self-centric thinking. Meet yours honestly.',
        minutes: 8,
        guruPrompt: 'Sri Krishnaji says all lingering suffering is self-centric thinking. Help me see the self-centric thought underneath what I am feeling.',
      },
      {
        id: 'es-3',
        title: 'Serene Mind',
        intention: 'Let the breath carry the thought out of the body.',
        minutes: 3,
        practice: 'serene-mind',
        guruPrompt: 'Guide me through the Serene Mind practice.',
      },
      {
        id: 'es-4',
        title: 'Living in connection',
        intention: 'Carry the beautiful state into one relationship today.',
        minutes: 6,
        guruPrompt: 'How do I stay in the beautiful state in my relationships, according to the teachings?',
      },
    ],
  },
  {
    slug: 'walking-through-grief',
    title: 'Walking Through Grief',
    subtitle: 'A gentle path for loss, separation and heartbreak.',
    signals: ['grief', 'loneliness'],
    lessons: [
      {
        id: 'gr-1',
        title: 'Letting the wave move',
        intention: 'Grief is not a problem to solve. Let it be felt fully.',
        minutes: 7,
        guruPrompt: 'I am grieving. What do Sri Preethaji and Sri Krishnaji teach about moving through grief without resisting it?',
      },
      {
        id: 'gr-2',
        title: 'Serene Mind for a heavy heart',
        intention: 'Three minutes of breath before the mind builds a story.',
        minutes: 3,
        practice: 'serene-mind',
        guruPrompt: 'Guide me through Serene Mind for grief.',
      },
      {
        id: 'gr-3',
        title: 'From separation to connection',
        intention: 'The one you lost is not outside connection.',
        minutes: 8,
        guruPrompt: 'Teach me about connection and oneness when someone I love is gone.',
      },
    ],
  },
  {
    slug: 'quieting-anxiety',
    title: 'Quieting Anxiety',
    subtitle: 'Meet the anxious mind with breath, truth and stillness.',
    signals: ['anxiety'],
    lessons: [
      {
        id: 'ax-1',
        title: 'The three questions',
        intention: 'What state am I in? Where is my mind? Who am I being?',
        minutes: 5,
        guruPrompt: 'Take me through the three-question meditation for an anxious mind.',
      },
      {
        id: 'ax-2',
        title: 'Serene Mind',
        intention: 'Four in, six out. Let the body lead.',
        minutes: 3,
        practice: 'serene-mind',
        guruPrompt: 'Guide me through Serene Mind for anxiety.',
      },
      {
        id: 'ax-3',
        title: 'Living without the future',
        intention: 'Anxiety lives in an imagined tomorrow. Return here.',
        minutes: 7,
        guruPrompt: 'What do the teachings say about a mind that is always living in the future?',
      },
    ],
  },
  {
    slug: 'dissolving-conflict',
    title: 'Dissolving Conflict',
    subtitle: 'For anger, resentment and broken relationships.',
    signals: ['anger'],
    lessons: [
      {
        id: 'cf-1',
        title: 'The other person is not the cause',
        intention: 'Look once at your own inner state before the story.',
        minutes: 7,
        guruPrompt: 'I am angry with someone. What do the teachings say about the true cause of conflict?',
      },
      {
        id: 'cf-2',
        title: 'Serene Mind before you speak',
        intention: 'Three minutes between the trigger and the word.',
        minutes: 3,
        practice: 'serene-mind',
        guruPrompt: 'Guide me through Serene Mind before a difficult conversation.',
      },
      {
        id: 'cf-3',
        title: 'The courage to connect',
        intention: 'Reach out from a beautiful state, not from being right.',
        minutes: 8,
        guruPrompt: 'How do I repair a relationship from the beautiful state?',
      },
    ],
  },
];

const SIGNAL_PATTERNS: Array<[SufferingSignal, RegExp]> = [
  ['grief', /\b(grief|grieving|died|death|passed away|lost (my|her|his)|funeral|widow|miscarriage|heartbreak|breakup|broke up|divorce)\b/i],
  ['anxiety', /\b(anxious|anxiety|panic|worried|worry|overthink|can'?t sleep|insomnia|dread|nervous|overwhelmed)\b/i],
  ['anger', /\b(angry|anger|furious|rage|resent|hate (him|her|them)|betrayed|argument|fight with|can'?t forgive)\b/i],
  ['loneliness', /\b(lonely|alone|no one|nobody (cares|listens)|isolated|abandoned)\b/i],
  ['meaninglessness', /\b(pointless|meaningless|no purpose|empty inside|why (do i|am i) (even |still )?(here|alive)|numb)\b/i],
];

/** Classify a seeker's message into a suffering signal. Returns null when calm. */
export function detectSufferingSignal(text: string): SufferingSignal | null {
  if (!text) return null;
  for (const [signal, pattern] of SIGNAL_PATTERNS) {
    if (pattern.test(text)) return signal;
  }
  return null;
}

export function courseForSignal(signal: SufferingSignal): HealingCourse {
  return (
    HEALING_COURSES.find((c) => c.signals.includes(signal)) ??
    HEALING_COURSES[0]
  );
}

export function getCourse(slug: string): HealingCourse | undefined {
  return HEALING_COURSES.find((c) => c.slug === slug);
}

export function courseMinutes(course: HealingCourse): number {
  return course.lessons.reduce((sum, l) => sum + l.minutes, 0);
}
