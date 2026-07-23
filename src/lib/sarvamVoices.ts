/**
 * Single source of truth for Sarvam bulbul:v3 voice names.
 * v2 names (anushka, deepika, sangeetha, arvind) are invalid against v3 and
 * fail silently/robotically — see docs/RUTHLESS_ONE_SHOT_BLUEPRINT.md.
 */

export const SARVAM_VOICES = [
  { id: 'priya', label: 'Priya', gender: 'female', hint: 'Warm, natural' },
  { id: 'ishita', label: 'Ishita', gender: 'female', hint: 'Calm, soothing' },
  { id: 'mani', label: 'Mani', gender: 'male', hint: 'Deep, composed' },
  { id: 'shubh', label: 'Shubh', gender: 'male', hint: 'Clear, default' },
] as const;

export type SarvamVoiceId = typeof SARVAM_VOICES[number]['id'];

export const DEFAULT_SARVAM_VOICE: SarvamVoiceId = 'priya';

const VALID_VOICE_IDS = new Set<string>(SARVAM_VOICES.map((v) => v.id));

export function normalizeSarvamVoice(voice?: string | null): SarvamVoiceId {
  if (voice && VALID_VOICE_IDS.has(voice)) {
    return voice as SarvamVoiceId;
  }
  return DEFAULT_SARVAM_VOICE;
}
