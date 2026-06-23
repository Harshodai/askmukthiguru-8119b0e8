import { getCurrentConfig } from './config';

let _healthLastChecked = 0;
let _healthStatus: 'unknown' | 'up' | 'down' = 'unknown';

export function getHealthStatus(): 'unknown' | 'up' | 'down' {
  return _healthStatus;
}

/** Exported for tests so each test can start with a cold cache. */
export function resetHealthCache(): void {
  _healthLastChecked = 0;
  _healthStatus = 'unknown';
}

export async function checkBackendHealth(endpoint: string): Promise<'up' | 'down'> {
  const now = Date.now();
  if (now - _healthLastChecked < 30_000) return _healthStatus as 'up' | 'down';
  _healthLastChecked = now;
  try {
    const baseUrl = new URL(endpoint).origin;
    const resp = await fetch(`${baseUrl}/api/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(5_000),
    });
    _healthStatus = resp.ok ? 'up' : 'down';
  } catch {
    _healthStatus = 'down';
  }
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
      return { connected: true, mode: 'Connected to Guru' };
    }
    try {
      const healthUrl = endpoint.startsWith('http')
        ? new URL('/api/health', new URL(endpoint).origin).href
        : '/api/health';

      const response = await fetch(healthUrl);
      return { connected: response.ok, mode: response.ok ? 'Connected to Guru' : 'Reconnecting…' };
    } catch (e) {
      console.error('Health check failed:', e);
      return { connected: false, mode: 'Reconnecting…' };
    }
  }

  return { connected: true, mode: 'Cloud Mode' };
}
