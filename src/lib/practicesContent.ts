/**
 * Static catalog of meditation practices.
 * Each practice has a dedicated detail page with embedded YouTube media.
 *
 * The static English content here is the **canonical source** for SEO/meta tags
 * (used by `usePageMeta` and `schema.org/HowTo` JSON-LD before user language
 * preference is known). The colloquial, localised copy lives in `src/locales/*`
 * under the `practices.<slug>.{title|tagline|purpose|howItWorks|benefits|duration}`
 * keys (see `src/locales/en.json`). At render time, `getLocalizedPractice()`
 * merges the localised strings on top of the static catalog when a non-English
 * language is active; otherwise the static English is used directly.
 *
 * YouTube IDs were chosen from publicly available teachings of
 * Sri Preethaji & Sri Krishnaji and the One Consciousness/EkamUSA channel.
 */
export interface Practice {
  slug: string;
  title: string;
  tagline: string;
  durationLabel: string;
  intentions: string[];
  purpose: string;
  howItWorks: string[];
  benefits: string[];
  videoId: string; // YouTube video ID (embed)
  audioId?: string; // optional separate audio-only YouTube ID
  accent: 'ojas' | 'prana' | 'tejas' | 'lotus';
  inApp?: { label: string; path: string }; // optional link to in-app version
  i18nKey?: string; // translation subtree key — when set, the corresponding
                    // en/hi/te entries take precedence over the static fields.
}

export const practices: Practice[] = [
  {
    slug: 'soul-sync',
    title: 'Soul Sync',
    tagline: 'Reconnect with the deeper intelligence within.',
    durationLabel: '15–20 min',
    intentions: ['Inner connection', 'Calm', 'Clarity'],
    purpose:
      'Soul Sync is a contemplative practice that gently turns attention inward, helping you reconnect with the silent presence beneath thoughts. It is the foundation for moving from a stressful state into a Beautiful State.',
    howItWorks: [
      'Conscious Breathing (8 cycles): Sit comfortably with hands resting on thighs, palms facing upward. Close your eyes and take 8 slow, deep breaths. Count them by touching your thumb to each finger (index to pinky, then back) for a total of 8 breaths.',
      'Humming Vibration (8 cycles): Connect your index finger and thumb in Jnana Mudra. Inhale deeply, and as you exhale, make a low-pitched humming sound like a bee (Bhramari Pranayama). Do this for 8 breath cycles, feeling the vibration resonate in your head and calming your nervous system.',
      'Observe the Silent Pause: Quietly observe the natural, peaceful pause that occurs between each inhalation and exhalation. Do not force it; rest in this space of stillness.',
      'Repeat Aham (I Am): With every exhalation, mentally repeat the mantra "Aham" (meaning "I am" or "boundless consciousness"). Connect with the feeling of simple presence and existence.',
      'Dissolve & Expand: Visualize your physical body, the immediate surroundings, and the entire universe dissolving and expanding into a limitless ocean of pure golden light. Feel that there is no separation between you and the rest of existence.',
      'Focus on your Intention: In this expanded, beautiful state, bring your heartfelt intention (such as healing, harmony, or a specific life goal) to mind. Visualize it manifesting, feel the positive emotions as if it has already occurred, and close the practice with a feeling of deep gratitude.',
    ],
    benefits: [
      'Reduces Stress and Anxiety: Calms the amygdala (the brain\'s fear center) and lowers cortisol levels.',
      'Enhances Mental Clarity: Shifts brainwave activity from high-frequency Beta (associated with stress and overthinking) to calm, cohesive Alpha waves.',
      'Boosts Synchronicity & Manifestation: Aligns your internal consciousness with your external goals, allowing you to manifest positive outcomes and synchronicities.',
      'Cultivates a Beautiful State: Dissolves self-obsessed suffering states, leading to an open heart filled with love, connection, and peace.',
    ],
    videoId: '69IrsSXeBTg',
    accent: 'ojas',
    i18nKey: 'practices.soulSync',
  },
  {
    slug: 'serene-mind',
    title: 'Serene Mind',
    tagline: 'A 3-minute reset for an agitated heart.',
    durationLabel: '3 min',
    intentions: ['Stress relief', 'Quick reset', 'Breath awareness'],
    purpose:
      'Serene Mind is a short, guided breathing practice that uses a calming 4-in / 6-out rhythm and a flame visualization to release tension and return to a quiet, clear mind.',
    howItWorks: [
      'Focus on Breath: Close your eyes, sit upright, and bring your complete, undivided attention to the flow of your breath entering and leaving your nostrils.',
      'Scan Your Inner State: Notice your current emotions and thoughts without trying to push them away. Ask yourself: "What exact emotion am I feeling right now?" (e.g., anxiety, anger, sadness, peace).',
      'Acknowledge Without Judgment: Gently label the emotion you feel. Avoid judging yourself, fighting the feeling, or trying to change it. Observe it with soft awareness.',
      'Observe the Focus of Your Mind: Notice if your mind is obsessed with past regrets, future worries, or self-centered thoughts. Gently acknowledge this state of separation.',
      'Flame Visualization: Visualize a steady, golden flame of light at the center of your forehead (between the eyebrows). Slowly guide this light inward to the center of your brain, seeing it glow and bring stability to the darkness.',
      'Complete with a Smile: Let a gentle, warm smile rest on your face. Take a final deep breath, feel the shift in your state, and slowly open your eyes.',
    ],
    benefits: [
      'Instant Amygdala Calm: Quickly de-escalates emotional agitation, panic, or anger in just three minutes.',
      'Increases Self-Awareness: Promotes mindfulness by encouraging you to label emotions without judgment, which reduces their emotional charge (cognitive reappraisal).',
      'Strengthens Focus & Presence: The flame visualization builds concentration and draws energy away from chaotic, racing thoughts back to a singular, centered focus.',
      'Physiological Reset: Activates the parasympathetic nervous system, lowering heart rate and bringing a sense of calm to the physical body.',
    ],
    videoId: 'igSp4H0OWLE',
    accent: 'tejas',
    inApp: { label: 'Open in chat', path: '/chat' },
    i18nKey: 'practices.sereneMind',
  },
  {
    slug: 'beautiful-state',
    title: 'Beautiful State',
    tagline: 'Step out of suffering, into love and connection.',
    durationLabel: '10–15 min',
    intentions: ['Compassion', 'Joy', 'Connection'],
    purpose:
      'A Beautiful State is the natural state of the heart — calm, joyful, and connected. This practice trains the mind to dissolve self-centred suffering and return again and again to that state.',
    howItWorks: [
      'Recall Connection: Bring to mind a person, a moment, or nature you love deeply. Connect with the warm feeling of safety and affection.',
      'Expand the Feeling: Let the warmth and love expand in the heart-space, filling your entire body.',
      'Send Well-Being: Wish well-being for yourself, then for others, then for all life in the universe.',
      'Carry the Warmth: Gently transition back to your daily activity, keeping the open-hearted feeling.',
    ],
    benefits: [
      'Dissolves self-centered suffering and emotional pain.',
      'Strengthens compassion, empathy, and connection with others.',
      'Promotes emotional resilience and increases daily feelings of joy.',
      'Supports heart health by inducing physiological coherence.',
    ],
    videoId: 'TqxxCYnAxo8',
    accent: 'lotus',
    i18nKey: 'practices.beautifulState',
  },
  {
    slug: 'daily-reflection',
    title: 'Daily Reflection',
    tagline: 'Close the day with awareness and gratitude.',
    durationLabel: '5–10 min',
    intentions: ['Gratitude', 'Awareness', 'Release'],
    purpose:
      'A short evening practice that helps you review the day with kindness — honouring what nourished you, acknowledging what hurt, and gently releasing both before sleep.',
    howItWorks: [
      'Settle in Stillness: Sit or lie down in stillness, allowing the body to relax.',
      'Recall Gratitude: Recall three moments from today that brought peace, joy, or learning.',
      'Acknowledge Struggles: Acknowledge any moment of struggle or pain today without judgment.',
      'Offer Gratitude: Offer gratitude for the day as a whole, and let it go as you prepare for rest.',
    ],
    benefits: [
      'Fosters gratitude and shifts perspective towards positive daily events.',
      'Allows mindful closure of the day, releasing tension and stress.',
      'Improves sleep quality by calming the mind before bedtime.',
      'Builds self-compassion by reviewing mistakes without judgment.',
    ],
    videoId: 'O-6f5wQXSu8',
    accent: 'prana',
    i18nKey: 'practices.dailyReflection',
  },
];

export const getPracticeBySlug = (slug: string): Practice | undefined =>
  practices.find((p) => p.slug === slug);

/**
 * Resolve the localised copy of a practice given an i18n `t` function and
 * language code. Falls back gracefully to the static English catalog when
 * translation keys are missing (e.g. partial locale coverage).
 *
 * Ponytail: returns a new Practice object — never mutates the static catalog
 * (which is the canonical source for SEO/meta and must stay language-neutral).
 */
export const getLocalizedPractice = (
  practice: Practice,
  t: (key: string, opts?: unknown) => string,
  lang: string = 'en',
): Practice => {
  if (!practice.i18nKey || lang === 'en') return practice;

  // Helper: read an i18n key, returning the *same* fallback string when the key
  // is missing in the active locale (i18next returns the key itself when no
  // translation is found — we use that signal to detect missing keys).
  const pick = (key: string, fallback: string): string => {
    const value = t(key);
    if (!value || value === key) return fallback;
    return value;
  };

  const pickList = (key: string, fallback: string[]): string[] => {
    // i18next returns objects/lists natively — use returnObjects option.
    const value = t(key, { returnObjects: true }) as unknown;
    if (Array.isArray(value) && value.length === fallback.length) {
      return value as string[];
    }
    return fallback;
  };

  return {
    ...practice,
    title: pick(`${practice.i18nKey}.title`, practice.title),
    tagline: pick(`${practice.i18nKey}.tagline`, practice.tagline),
    durationLabel: pick(`${practice.i18nKey}.duration`, practice.durationLabel),
    purpose: pick(`${practice.i18nKey}.purpose`, practice.purpose),
    howItWorks: pickList(`${practice.i18nKey}.howItWorks`, practice.howItWorks),
    benefits: pickList(`${practice.i18nKey}.benefits`, practice.benefits),
  };
};

