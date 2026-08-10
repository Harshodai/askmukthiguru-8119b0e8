/**
 * Shared storage for the Serene Mind mid-session resume payload.
 *
 * Kept as a tiny standalone module (no component dependencies) so sign-out
 * purge can be wired from anywhere without pulling the meditation UI graph
 * into auth/lib modules. See docs/runbooks/PRIVACY.md.
 */

/** localStorage key for the Serene Mind mid-session resume payload. */
export const MEDITATION_RESUME_KEY = 'serene_mind_resume_v1';

/** Remove the meditation resume payload. Called on sign-out to prevent
 *  cross-user leaks on shared devices (P1-FE-15). */
export const clearMeditationResume = (): void => {
  try {
    localStorage.removeItem(MEDITATION_RESUME_KEY);
  } catch {
    /* noop */
  }
};
