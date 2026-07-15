import { useState, useEffect } from 'react';
import { BACKEND_URL } from '@/lib/backendUrl';

export type BackendHealth = 'ok' | 'degraded' | 'unknown';

/**
 * Pings `/api/health` once on mount. Returns 'degraded' if the backend is
 * cold-starting or unreachable — the UI shows a soft "waking up" banner so
 * seekers don't think the app is broken during the 60-90s Railway warmup.
 */
export function useBackendHealth(): BackendHealth {
  const [health, setHealth] = useState<BackendHealth>('unknown');

  useEffect(() => {
    if (!BACKEND_URL) { setHealth('ok'); return; }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 7000);

    fetch(`${BACKEND_URL}/api/health`, { signal: controller.signal })
      .then((r) => { clearTimeout(timer); setHealth(r.ok ? 'ok' : 'degraded'); })
      .catch(() => setHealth('degraded'));

    return () => { clearTimeout(timer); controller.abort(); };
  }, []);

  return health;
}
