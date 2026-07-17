/**
 * Sri Preethaji's Serene Mind protocol — 4 movements of awareness.
 *
 * Source: Sri Preethaji's published teachings on the Serene Mind practice,
 * a short pre-conversation grounding ritual used at O&O Academy.
 *
 *   1. Observe the Body   — settle and feel the body as it is.
 *   2. Observe the Breath — follow the natural breath, 4 in / 6 out.
 *   3. Observe the Sound  — open awareness to ambient sound.
 *   4. Be with Compassion — send a wish of well-being to all life.
 *
 * Total ≈ 3m 56s. Wording is present-tense, gentle, non-instructional.
 *
 * Audio: Preethaji's own voice, extracted from the canonical Serene Mind
 * YouTube video (igSp4H0OWLE), loudnorm-normalized to -16 LUFS. The same
 * asset URL is set on every step so `useMeditationAudio` recognises the src
 * as unchanged and lets the single continuous track play across step
 * transitions while the on-screen flame + text advance on their own timers.
 */
import preethajiAudio from '@/assets/meditation/preethaji-serene-mind.mp3.asset.json';

const PREETHAJI_AUDIO_SRC = preethajiAudio.url;

export interface MeditationStep {
  id: string;
  title: string;
  instruction: string;
  durationSeconds: number;
  breathPattern?: { inhale: number; hold: number; exhale: number };
  /**
   * Optional narrated audio for this step. When every step points at the
   * same URL, `useMeditationAudio` short-circuits and plays a single
   * continuous track — matching the way Sri Preethaji actually guides the
   * practice on the source recording. If absent, the player falls back to
   * browser TTS reading the instruction.
   */
  audioSrc?: string;
}

// Durations scaled from the original 20/45/60/45/45/10 = 225s protocol to
// match the 236s Preethaji recording, so the timeline finishes with the
// narration instead of dropping into silence at "Carry the Stillness".
export const GUIDED_STEPS: MeditationStep[] = [
  {
    id: 'arrive',
    title: 'Arrive',
    instruction:
      'Sit comfortably. Let your eyes close softly. There is nothing to achieve here — only a few minutes of simple awareness.',
    durationSeconds: 21,
    audioSrc: PREETHAJI_AUDIO_SRC,
  },
  {
    id: 'observe-body',
    title: 'Observe the Body',
    instruction:
      'Feel your body as it is, from the crown of your head to the soles of your feet. Notice the weight, the warmth, the points of contact. Do not change anything. Just observe.',
    durationSeconds: 47,
    audioSrc: PREETHAJI_AUDIO_SRC,
  },
  {
    id: 'observe-breath',
    title: 'Observe the Breath',
    instruction:
      'Bring your awareness to the breath. Breathe in for four counts… and let the breath flow out for six. Stay with the breath as it moves on its own.',
    durationSeconds: 63,
    breathPattern: { inhale: 4, hold: 0, exhale: 6 },
    audioSrc: PREETHAJI_AUDIO_SRC,
  },
  {
    id: 'observe-sound',
    title: 'Observe the Sound',
    instruction:
      'Open your awareness to the sounds around you — near and distant, sharp and soft. Receive each sound as it arrives, without naming it.',
    durationSeconds: 47,
    audioSrc: PREETHAJI_AUDIO_SRC,
  },
  {
    id: 'compassion',
    title: 'Be with Compassion',
    instruction:
      'From this stillness, hold a silent wish — May all beings be free of suffering. May all beings be in a beautiful state. Let this wish move through you.',
    durationSeconds: 47,
    audioSrc: PREETHAJI_AUDIO_SRC,
  },
  {
    id: 'complete',
    title: 'Carry the Stillness',
    instruction:
      'Gently bring your awareness back. Carry this serene mind into whatever comes next.',
    durationSeconds: 11,
    audioSrc: PREETHAJI_AUDIO_SRC,
  },
];

export const TOTAL_DURATION_SECONDS = GUIDED_STEPS.reduce(
  (s, step) => s + step.durationSeconds,
  0,
);
