/** Runtime-safe Vite feature flags for progressive frontend rollouts. */
const enabled = (value: unknown, fallback = true): boolean => {
  if (value === undefined || value === null || value === '') return fallback;
  return !['0', 'false', 'off', 'no'].includes(String(value).trim().toLowerCase());
};

const env = typeof import.meta !== 'undefined' ? import.meta.env : {};

export const FEATURE_FLAGS = Object.freeze({
  wisdomTips: enabled(env?.VITE_ENABLE_WISDOM_TIPS, true),
  suggestedFollowUps: enabled(env?.VITE_ENABLE_SUGGESTED_FOLLOWUPS, true),
  responseProvenance: enabled(env?.VITE_ENABLE_RESPONSE_PROVENANCE, true),
});
