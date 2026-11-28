/**
 * The backend answers a stale/rotated-secret anonymous token with
 * 400 {"detail":"Invalid anonymous session token"} (auth_service.verify_anon_session_token),
 * not 401. Detect that exact body so callers can re-mint once instead of
 * surfacing a permanent error from the cached token.
 */
export async function isAnonTokenRejected(response: Response): Promise<boolean> {
  if (response.status !== 400) return false;
  try {
    const body = await response.clone().json();
    return body?.detail === 'Invalid anonymous session token';
  } catch {
    return false;
  }
}
