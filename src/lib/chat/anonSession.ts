import { BACKEND_URL } from '../backendUrl';
import { getAccessToken } from './auth';

/**
 * M5 frontend half: anonymous seekers must send a server-signed session
 * token (minted by POST /api/auth/anon-session) instead of a client-asserted
 * conversation id, because resolve_anon_identity() rejects unsigned ids.
 *
 * The token is cached in localStorage so the identity is stable across
 * reloads — job ownership (X-Session-Id on poll/stream) depends on the
 * resolved anon:<payload> id matching what the POST /api/chat call used.
 */

const STORAGE_KEY = 'askmukthi.anon.session.v1';

let inFlight: Promise<string | null> | null = null;

async function mintAnonSessionToken(): Promise<string | null> {
  const baseUrl = BACKEND_URL || '';
  try {
    const res = await fetch(`${baseUrl}/api/auth/anon-session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return typeof data?.token === 'string' && data.token ? data.token : null;
  } catch {
    // Backend unreachable or endpoint absent (older backend) — caller
    // falls back to the legacy session id, which older backends accept.
    return null;
  }
}

async function mintAndCacheAnonSessionToken(): Promise<string | null> {
  const token = await mintAnonSessionToken();
  if (token) {
    try {
      localStorage.setItem(STORAGE_KEY, token);
    } catch {
      // storage unavailable — token still usable this page load
    }
  }
  return token;
}

async function awaitAnonSessionToken(forceRefresh = false): Promise<string | null> {
  if (forceRefresh) {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // storage unavailable — minting remains valid for this page load
    }
  }
  if (!inFlight) {
    inFlight = mintAndCacheAnonSessionToken();
  }
  try {
    return await inFlight;
  } finally {
    inFlight = null;
  }
}

/** Signed anonymous-session token, or null when the user is authenticated,
 *  the backend cannot mint one, or this browser has no storage. */
export async function getAnonSessionToken(): Promise<string | null> {
  const accessToken = await getAccessToken();
  if (accessToken) return null;

  if (typeof localStorage === 'undefined') return null;
  try {
    const cached = localStorage.getItem(STORAGE_KEY);
    if (cached) return cached;
  } catch {
    // storage unavailable (private mode) — mint per page load
  }

  return awaitAnonSessionToken();
}

/**
 * Discard the cached token and mint a new one after the backend rejects it.
 * This is intentionally separate from getAnonSessionToken so a transient 401
 * does not cause every normal request to mint a new identity.
 */
export async function refreshAnonSessionToken(): Promise<string | null> {
  return awaitAnonSessionToken(true);
}

/** session id to send on chat/job calls: the signed anon token for
 *  anonymous users, the caller-provided id otherwise. */
export async function resolveSessionId(sessionId?: string): Promise<string | undefined> {
  if (!sessionId) return undefined;
  const anonToken = await getAnonSessionToken();
  return anonToken ?? sessionId;
}
