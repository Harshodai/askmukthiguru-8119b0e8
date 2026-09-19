/**
 * Auth-related constants for AskMukthiGuru client-side login flows.
 */

export const GOOGLE_STEP_KEY = 'askmukthiguru_google_step';
export const ONBOARDED_FLAG_KEY = 'askmukthiguru_onboarded';
export const NATIVE_REDIRECT = 'com.askmukthiguru.app://auth-callback';

// Google Identity Services (GIS) / GSI SDK URL
export const GOOGLE_GSI_SDK_URL = 'https://accounts.google.com/gsi/client';

/**
 * Google OAuth Client ID fallback. Client IDs are public identifiers, not
 * secrets (unlike a client secret) — Google's own docs embed them directly
 * in client-side code. Lovable's hosted build has no mechanism to inject a
 * custom VITE_* env var (confirmed 2026-09-19: it only auto-injects vars for
 * its native Supabase integration), so VITE_GOOGLE_CLIENT_ID is silently
 * absent from that build and this fallback is what actually renders the
 * Google button there. Same value as VITE_GOOGLE_CLIENT_ID in .env.production.
 */
export const GOOGLE_CLIENT_ID_FALLBACK =
  '1004985929687-iic001qgjb54vfd2gi3stu2uticc6ats.apps.googleusercontent.com';
