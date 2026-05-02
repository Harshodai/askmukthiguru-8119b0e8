export interface MeditationStep {
  id: string;
  title: string;
  instruction: string;
  durationSeconds: number;
  breathPattern?: { inhale: number; hold: number; exhale: number };
}

export const GUIDED_STEPS: MeditationStep[] = [
  {
    id: 'welcome',
    title: 'Welcome',
    instruction: 'Find a comfortable position. Close your eyes gently and let your body settle.',
    durationSeconds: 15,
  },
  {
    id: 'settle',
    title: 'Settle In',
    instruction: 'Bring your awareness to your heart space. Feel the warmth there, like a gentle sunrise within.',
    durationSeconds: 30,
  },
  {
    id: 'breathe',
    title: 'Conscious Breathing',
    instruction: 'Breathe in peace… hold with gratitude… breathe out all that no longer serves you.',
    durationSeconds: 60,
    breathPattern: { inhale: 4, hold: 2, exhale: 6 },
  },
  {
    id: 'observe',
    title: 'Observe',
    instruction: 'Simply observe whatever arises — thoughts, sensations, emotions. Let them flow without grasping.',
    durationSeconds: 45,
  },
  {
    id: 'integrate',
    title: 'Integrate',
    instruction: 'Feel the stillness. You are awareness itself. Rest in this beautiful state.',
    durationSeconds: 30,
  },
  {
    id: 'complete',
    title: 'Namaste',
    instruction: 'Gently bring your awareness back. Carry this peace with you. You are complete.',
    durationSeconds: 10,
  },
];

export const TOTAL_DURATION_SECONDS = GUIDED_STEPS.reduce((s, step) => s + step.durationSeconds, 0);
