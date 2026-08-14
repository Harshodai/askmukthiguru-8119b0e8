/**
 * Central backend URL resolution.
 *
 * Priority:
 *   1. VITE_BACKEND_URL env var (self-hosted / staging overrides).
 *   2. Production Railway URL when running on an exact prod host.
 *   3. Empty string — callers fall back to relative /api or dev localhost.
 *
 * Every module that hits the FastAPI backend should import `BACKEND_URL` from
 * here instead of reading `import.meta.env.VITE_BACKEND_URL` directly so that
 * hosted frontends automatically talk to the Railway backend.
 */

import { Capacitor } from '@capacitor/core';

export const PROD_RAILWAY_URL =
  'https://askmukthiguru-8119b0e8-production.up.railway.app';

/** Exact prod frontend hostnames. Any other host (staging branches,
 *  previews, localhost) must NOT resolve to the prod backend. */
const PROD_HOSTNAMES: ReadonlySet<string> = new Set([
  'askmukthiguru-8119b0e8-production.up.railway.app',
  // Published Lovable frontend — the SPA host serves no /api, so relative
  // calls returned the HTML shell instead of FastAPI JSON (QA P0).
  'askmukthiguru.lovable.app',
  'www.askmukthiguru.com',
  'askmukthiguru.com',
]);

export function isProdHost(hostname: string): boolean {
  return PROD_HOSTNAMES.has(hostname);
}

const isNative = typeof Capacitor !== 'undefined' && Capacitor.isNativePlatform();

const ENV_URL =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_BACKEND_URL) || '';

/** Native builds never silently hit prod: they need an explicit
 *  VITE_NATIVE_BACKEND=prod opt-in (or a VITE_BACKEND_URL override). */
const nativeUsesProd =
  isNative &&
  ((typeof import.meta !== 'undefined' && import.meta.env?.VITE_NATIVE_BACKEND) || '')
    .trim()
    .toLowerCase() === 'prod';

const currentHostname =
  typeof window !== 'undefined' ? window.location.hostname : '';

let resolvedUrl: string =
  ENV_URL || (nativeUsesProd || isProdHost(currentHostname) ? PROD_RAILWAY_URL : '');

if (!resolvedUrl && isNative && !nativeUsesProd) {
  console.warn(
    '[backendUrl] Native build without VITE_BACKEND_URL or VITE_NATIVE_BACKEND=prod — backend calls will fail closed instead of silently hitting prod.',
  );
  resolvedUrl = '';
}

export const BACKEND_URL: string = resolvedUrl;

/** For dev tools that need a local fallback (e.g. useStudyNotebooks).
 * In production, BACKEND_URL is always set (Railway), so the localhost
 * fallback is dev-only — Vite tree-shakes it from the production bundle. */
export const BACKEND_URL_OR_LOCAL: string =
  BACKEND_URL || (import.meta.env.DEV ? 'http://localhost:8000' : '');
