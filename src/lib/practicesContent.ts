/**
 * Static catalog of meditation practices.
 * Each practice has a dedicated detail page with embedded YouTube media.
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
  videoId: string; // YouTube video ID (embed)
  audioId?: string; // optional separate audio-only YouTube ID
  accent: 'ojas' | 'prana' | 'tejas' | 'lotus';
  inApp?: { label: string; path: string }; // optional link to in-app version
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
      'Sit comfortably with eyes softly closed.',
      'Become aware of your natural breath without changing it.',
      'When the mind drifts, lovingly bring attention back to the breath.',
      'Rest in the awareness that watches both breath and thought.',
    ],
    videoId: '69IrsSXeBTg',
    accent: 'ojas',
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
      'Breathe in for 4 counts through the nose.',
      'Breathe out for 6 counts through the mouth.',
      'Watch the flame in your mind softly steady itself.',
      'Continue for 9 cycles, then sit in the silence that follows.',
    ],
    videoId: 'igSp4H0OWLE',
    accent: 'tejas',
    inApp: { label: 'Open in chat', path: '/chat' },
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
      'Bring to mind a person, a moment, or nature you love.',
      'Let the feeling expand in the heart-space.',
      'Wish well-being for yourself, then for others, then for all life.',
      'Carry the warmth into the next activity of your day.',
    ],
    videoId: 'TqxxCYnAxo8',
    accent: 'lotus',
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
      'Sit or lie down in stillness.',
      'Recall three moments from today that brought peace or learning.',
      'Acknowledge any moment of struggle without judgement.',
      'Offer gratitude and let the day go.',
    ],
    videoId: 'O-6f5wQXSu8',
    accent: 'prana',
  },
];

export const getPracticeBySlug = (slug: string): Practice | undefined =>
  practices.find((p) => p.slug === slug);
