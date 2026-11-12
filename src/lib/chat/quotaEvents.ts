/**
 * UX-011: the free-turn counter. The backend puts `quota: {remaining, limit}` on the 202 reply
 * to an anonymous turn (and X-Quota-* headers). The stream code publishes it here and a small
 * component listens. Signed-in users get no `quota` field, so no counter is ever shown to them.
 */
export interface QuotaInfo {
  remaining: number;
  limit: number;
}

export const QUOTA_EVENT = 'mg:quota';

/** Returns a clean QuotaInfo, or null for anything that is not two finite non-negative numbers. */
export function parseQuota(raw: unknown): QuotaInfo | null {
  if (!raw || typeof raw !== 'object') return null;
  const { remaining, limit } = raw as Record<string, unknown>;
  if (typeof remaining !== 'number' || typeof limit !== 'number') return null;
  if (!Number.isFinite(remaining) || !Number.isFinite(limit) || limit <= 0) return null;
  return { remaining: Math.max(0, Math.floor(remaining)), limit: Math.floor(limit) };
}

export function publishQuota(raw: unknown): void {
  const info = parseQuota(raw);
  if (!info || typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent<QuotaInfo>(QUOTA_EVENT, { detail: info }));
}
