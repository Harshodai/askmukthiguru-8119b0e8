/** Runtime-safe Vite feature flags for progressive frontend rollouts. */
const enabled = (value: unknown, fallback = true): boolean => {
  if (value === undefined || value === null || value === '') return fallback;
  return !['0', 'false', 'off', 'no'].includes(String(value).trim().toLowerCase());
};

const env = (typeof import.meta !== 'undefined' ? import.meta.env : {}) as Record<string, unknown>;

export const FEATURE_FLAGS = Object.freeze({
  wisdomTips: enabled(env?.VITE_ENABLE_WISDOM_TIPS, true),
  suggestedFollowUps: enabled(env?.VITE_ENABLE_SUGGESTED_FOLLOWUPS, true),
  responseProvenance: enabled(env?.VITE_ENABLE_RESPONSE_PROVENANCE, true),
  // Off by default: the "Deepen & Tune" panel shows engineering labels
  // (Memgraph, bolt://, "Pattern A") and a hand-written concept list with
  // per-teacher attributions that no source backs, presented as "extracted
  // from discourse". Not seeker-ready until each concept carries a citation.
  deepenAndTuneBar: enabled(env?.VITE_ENABLE_DEEPEN_BAR, false),
});
