import { getCurrentConfig } from './config';

let _healthLastChecked = 0;
let _healthStatus: 'unknown' | 'up' | 'down' = 'unknown';
let _healthEndpoint = '';

export type ServiceHealth = 'ok' | 'degraded' | 'unreachable';

/** HTTP 200 alone is not readiness: a proxy can serve HTML or ready=false. */
export async function requestBackendHealth(endpoint: string, signal: AbortSignal): Promise<ServiceHealth> {
  try {
    const url = new URL(endpoint, window.location.origin);
    const response = await fetch(`${url.origin}/api/health`, { method: 'GET', signal });
    if ([404, 502, 504].includes(response.status)) return 'unreachable';
    if (!response.ok) return 'degraded';
    const payload: unknown = await response.json();
    if (!payload || typeof payload !== 'object' || !('ready' in payload)) return 'unreachable';
    return payload.ready === true ? 'ok' : 'degraded';
  } catch {
    return 'unreachable';
  }
}

export function getHealthStatus(): 'unknown' | 'up' | 'down' {
  return _healthStatus;
}

/** Exported for tests so each test can start with a cold cache. */
export function resetHealthCache(): void {
  _healthLastChecked = 0;
  _healthStatus = 'unknown';
  _healthEndpoint = '';
}

export async function checkBackendHealth(endpoint: string): Promise<'up' | 'down'> {
  const now = Date.now();
  if (_healthEndpoint === endpoint && _healthStatus !== 'unknown' && now - _healthLastChecked < 30_000) return _healthStatus;
  const status = await requestBackendHealth(endpoint, AbortSignal.timeout(5_000));
  _healthStatus = status === 'ok' ? 'up' : 'down';
  _healthEndpoint = endpoint;
  _healthLastChecked = Date.now();
  return _healthStatus;
}

export async function checkConnection(): Promise<{ connected: boolean; mode: string }> {
  const { provider, endpoint } = getCurrentConfig();

  if (provider === 'placeholder') {
    return { connected: true, mode: 'Offline Mode' };
  }

  if (provider === 'custom' && endpoint) {
    // Edge-function endpoints don't expose /api/health — treat as connected.
    if (endpoint.includes('/functions/v1/')) {
      return { connected: true, mode: 'Connected' };
    }
    const status = await requestBackendHealth(endpoint, AbortSignal.timeout(5_000));
    return { connected: status === 'ok', mode: status === 'ok' ? 'Connected' : 'Unavailable' };
  }

  return { connected: true, mode: 'Cloud Mode' };
}
