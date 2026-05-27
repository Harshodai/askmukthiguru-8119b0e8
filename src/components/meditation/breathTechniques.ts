/**
 * Breathing technique presets for the Serene Mind breathing tab.
 *
 * Architecture inspired by breathly-app (mmazzarolo/breathly-app) and
 * inbreeze (waozixyz/inbreeze) — techniques are pure config objects so the
 * GuidedMeditationFlow state machine works for any pattern without code changes.
 *
 * Teachings are NOT hardcoded here. They are fetched dynamically from
 * GET /api/breath-teaching/{technique_id} which uses the Qdrant RAG pipeline
 * to retrieve authentic passages from Sri Preethaji and Sri Krishnaji's
 * ingested knowledge base.
 *
 * Timing units: seconds.
 * A "hold2" phase (post-exhale hold) of 0 means it is skipped.
 */

export interface BreathTechnique {
  id: string;
  name: string;
  description: string;
  /** Inhale duration in seconds */
  inhale: number;
  /** Hold after inhale in seconds (0 = skip) */
  hold1: number;
  /** Exhale duration in seconds */
  exhale: number;
  /** Hold after exhale in seconds (0 = skip) */
  hold2: number;
  /** Recommended total session seconds */
  sessionSeconds: number;
}

/**
 * Serene Mind default — the 4-2-6 ratio used in Sri Preethaji's guided practice.
 * Inhale activates, the short hold sustains, the long exhale releases.
 */
const SERENE_MIND: BreathTechnique = {
  id: 'serene_mind',
  name: 'Serene Mind',
  description: '4 · 2 · 6',
  inhale: 4,
  hold1: 2,
  exhale: 6,
  hold2: 0,
  sessionSeconds: 10,
};

/**
 * Box Breathing — 4·4·4·4.
 * Equal-phase square breathing for mental clarity.
 */
const BOX_BREATHING: BreathTechnique = {
  id: 'box',
  name: 'Box Breathing',
  description: '4 · 4 · 4 · 4',
  inhale: 4,
  hold1: 4,
  exhale: 4,
  hold2: 4,
  sessionSeconds: 10,
};

/**
 * 4-7-8 Breathing — deep parasympathetic activation.
 * Aligns with Preethaji's teaching on the power of the long exhale.
 */
const FOUR_SEVEN_EIGHT: BreathTechnique = {
  id: '4_7_8',
  name: '4-7-8 Deep Rest',
  description: '4 · 7 · 8',
  inhale: 4,
  hold1: 7,
  exhale: 8,
  hold2: 0,
  sessionSeconds: 10,
};

/**
 * Deep Vitality — energising prana activation.
 * Gentle inbreeze-inspired technique (waozixyz/inbreeze).
 */
const DEEP_VITALITY: BreathTechnique = {
  id: 'deep_vitality',
  name: 'Deep Vitality',
  description: '4 · 4 · 4 · 0',
  inhale: 4,
  hold1: 4,
  exhale: 4,
  hold2: 0,
  sessionSeconds: 10,
};

export const BREATH_TECHNIQUES: BreathTechnique[] = [
  SERENE_MIND,
  BOX_BREATHING,
  FOUR_SEVEN_EIGHT,
  DEEP_VITALITY,
];

export const DEFAULT_TECHNIQUE = SERENE_MIND;

/** Helper: total cycle duration in seconds for one breath cycle */
export const cycleDuration = (t: BreathTechnique): number =>
  t.inhale + t.hold1 + t.exhale + t.hold2;
