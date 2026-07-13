/**
 * Central backend URL resolution.
 *
 * Priority:
 *   1. VITE_BACKEND_URL env var (self-hosted / staging overrides).
 *   2. Production Railway URL when running on a Lovable / prod host.
 *   3. Empty string — callers fall back to relative /api or dev localhost.
 *
 * Every module that hits the FastAPI backend should import `BACKEND_URL` from
 * here instead of reading `import.meta.env.VITE_BACKEND_URL` directly so that
 * the Lovable-hosted frontend automatically talks to the Railway backend.
 */

export const PROD_RAILWAY_URL =
  'https://askmukthiguru-8119b0e8-production.up.railway.app';

const isProdHost =
  typeof window !== 'undefined' &&
  /\.lovable\.(app|dev)$|askmukthiguru\./.test(window.location.hostname);

const ENV_URL =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_BACKEND_URL) || '';

export const BACKEND_URL: string = ENV_URL || (isProdHost ? PROD_RAILWAY_URL : '');

/** For dev tools that need a local fallback (e.g. useStudyNotebooks). */
export const BACKEND_URL_OR_LOCAL: string = BACKEND_URL || 'http://localhost:8000';
