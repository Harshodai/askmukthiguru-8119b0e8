import { useState, useEffect } from 'react';
import { BACKEND_URL } from '@/lib/backendUrl';
import { requestBackendHealth } from '@/lib/chat/health';

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
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 7000);
    let unmounted = false;

    void requestBackendHealth(`${BACKEND_URL}/api/chat`, controller.signal)
      .then((status) => { clearTimeout(timer); if (!unmounted) setHealth(status); });

    return () => { unmounted = true; clearTimeout(timer); controller.abort(); };
  }, []);

  return health;
}
