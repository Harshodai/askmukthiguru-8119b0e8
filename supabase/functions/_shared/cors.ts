/**
 * Shared CORS origin resolver for all Mukthi Guru edge functions.
 *
 * These functions authenticate via `Authorization: Bearer <token>` or a
 * shared secret header, never cookies — a wildcard
 * Access-Control-Allow-Origin does not by itself let a malicious page forge
 * or read another origin's bearer token, so this was hygiene debt rather
 * than an active exploit path. Still closing it: set ALLOWED_ORIGINS
 * (comma-separated) via `supabase secrets set` to restrict; leaving it unset
 * preserves the previous "*" behavior, so this is a strict opt-in
 * tightening, never a breaking rollout. (OH-P1-06, 2026-08-25)
 */
export function resolveAllowOrigin(req: Request): string {
  const configured = (Deno.env.get('ALLOWED_ORIGINS') ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  if (configured.length === 0) return '*';
  const origin = req.headers.get('origin') ?? '';
  return configured.includes(origin) ? origin : configured[0];
}
