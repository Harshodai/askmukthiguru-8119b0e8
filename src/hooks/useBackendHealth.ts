import { useState, useEffect } from 'react';
import { BACKEND_URL } from '@/lib/backendUrl';

/**
 * 'degraded'    — the backend answered, but not healthy (typically a cold
 *                 start returning 503 while models load).
 * 'unreachable' — no answer at all (network error, DNS, timeout, service
 *                 scaled down). Telling a seeker it is "waking up" here is
 *                 untrue; nothing is on its way.
 */
export type BackendHealth = 'ok' | 'degraded' | 'unreachable' | 'unknown';

/** Pings `/api/health` once on mount. */
export function useBackendHealth(): BackendHealth {
  const [health, setHealth] = useState<BackendHealth>('unknown');

  useEffect(() => {
    if (!BACKEND_URL) { setHealth('ok'); return; }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 7000);
    let unmounted = false;

    fetch(`${BACKEND_URL}/api/health`, { signal: controller.signal })
      .then((r) => { clearTimeout(timer); setHealth(r.ok ? 'ok' : 'degraded'); })
      .catch(() => { if (!unmounted) setHealth('unreachable'); });

    return () => { unmounted = true; clearTimeout(timer); controller.abort(); };
  }, []);

  return health;
}
