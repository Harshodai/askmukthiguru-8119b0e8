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

/**
 * Google One Tap / GSI nonce helpers. Supabase's signInWithIdToken() expects
 * the RAW nonce (it hashes it internally to compare against the ID token's
 * `nonce` claim); Google's accounts.id.initialize() expects the SHA-256 HASH
 * of that same raw value (it goes into the token's `nonce` claim verbatim).
 * Mixing these up -- passing the same value to both, whichever it is --
 * produces a deterministic "Nonces mismatch" on every real sign-in attempt,
 * not an intermittent race. Confirmed live 2026-09-19.
 */
export const generateNonce = (): string => {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let nonce = '';
  const cryptoObj = typeof window !== 'undefined' ? window.crypto : (typeof crypto !== 'undefined' ? crypto : null);
  if (cryptoObj?.getRandomValues) {
    const values = new Uint32Array(16);
    cryptoObj.getRandomValues(values);
    for (let i = 0; i < values.length; i++) {
      nonce += chars[values[i] % chars.length];
    }
  } else if (cryptoObj?.randomUUID) {
    nonce = cryptoObj.randomUUID().replace(/-/g, '').slice(0, 16);
  }
  return nonce;
};

export const sha256Hex = async (input: string): Promise<string | null> => {
  const webCrypto = typeof window !== 'undefined' ? window.crypto : undefined;
  if (!webCrypto?.subtle) {
    // Web Crypto may be unavailable on an insecure (non-HTTPS) origin --
    // skip the optional prompt rather than throwing a page-level error or
    // weakening nonce validation.
    return null;
  }
  const encoder = new TextEncoder();
  const data = encoder.encode(input);
  const hashBuffer = await webCrypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
};
