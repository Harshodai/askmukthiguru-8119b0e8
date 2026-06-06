/**
 * Lightweight client-side OAuth/auth timing telemetry.
 *
 * Captures per-step durations for sign-in flows (especially Google OAuth which
 * round-trips through an external provider) and persists them to localStorage
 * so a dashboard at /auth/latency can render them without a backend.
 *
 * No PII is stored — only step names, timestamps (epoch ms), durations (ms),
 * outcome, and optional error message strings.
 */

const STORAGE_KEY = 'askmukthiguru_auth_telemetry_v1';
const ACTIVE_KEY = 'askmukthiguru_auth_telemetry_active';
const MAX_RUNS = 25;

export type AuthStepName =
  | 'click_google'
  | 'click_facebook'
  | 'google_one_tap'
  | 'oauth_init'           // lovable.auth.signInWithOAuth() call
  | 'provider_redirect'    // browser leaving for Google
  | 'provider_return'      // we're back from Google (page reload)
  | 'session_hydrate'      // supabase getSession / onAuthStateChange fired
  | 'profile_ensure'       // ensure_profile_and_role RPC
  | 'profile_fetch'        // fetchProfileFromServer
  | 'navigate'             // navigate(/chat or /profile)
  | 'email_signin'
  | 'email_signup'
  | 'run_error';           // terminal failure attached to the run


export type AuthStepStatus = 'ok' | 'error' | 'pending';

export interface AuthStep {
  name: AuthStepName;
  status: AuthStepStatus;
  startedAt: number;
  durationMs: number | null;
  error?: string;
  meta?: Record<string, string | number | boolean | null>;
}

export interface AuthRun {
  id: string;
  provider: 'google' | 'email' | 'unknown';
  startedAt: number;
  endedAt: number | null;
  totalMs: number | null;
  status: 'ok' | 'error' | 'in_progress';
  steps: AuthStep[];
  userAgent: string;
}

const safeWindow = (): Window | null => (typeof window === 'undefined' ? null : window);

const readRuns = (): AuthRun[] => {
  const w = safeWindow();
  if (!w) return [];
  try {
    const raw = w.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as AuthRun[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const writeRuns = (runs: AuthRun[]): void => {
  const w = safeWindow();
  if (!w) return;
  try {
    w.localStorage.setItem(STORAGE_KEY, JSON.stringify(runs.slice(-MAX_RUNS)));
  } catch {
    /* quota — ignore */
  }
};

const readActive = (): AuthRun | null => {
  const w = safeWindow();
  if (!w) return null;
  try {
    const raw = w.sessionStorage.getItem(ACTIVE_KEY) ?? w.localStorage.getItem(ACTIVE_KEY);
    return raw ? (JSON.parse(raw) as AuthRun) : null;
  } catch {
    return null;
  }
};

const writeActive = (run: AuthRun | null): void => {
  const w = safeWindow();
  if (!w) return;
  try {
    if (run === null) {
      w.sessionStorage.removeItem(ACTIVE_KEY);
      w.localStorage.removeItem(ACTIVE_KEY);
    } else {
      const payload = JSON.stringify(run);
      // sessionStorage for current tab; localStorage so a full redirect round-trip
      // (which can spawn a fresh tab in some browsers) can still recover it.
      w.sessionStorage.setItem(ACTIVE_KEY, payload);
      w.localStorage.setItem(ACTIVE_KEY, payload);
    }
  } catch {
    /* ignore */
  }
};

const log = (msg: string, data?: unknown): void => {
  // Single, greppable prefix for browser devtools.
  // eslint-disable-next-line no-console
  console.info(`[AuthTelemetry] ${msg}`, data ?? '');
};

export const startAuthRun = (provider: AuthRun['provider']): AuthRun => {
  const run: AuthRun = {
    id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    provider,
    startedAt: Date.now(),
    endedAt: null,
    totalMs: null,
    status: 'in_progress',
    steps: [],
    userAgent: safeWindow()?.navigator.userAgent ?? '',
  };
  writeActive(run);
  log('run started', { provider, id: run.id });
  return run;
};

export const recordStep = (
  name: AuthStepName,
  status: AuthStepStatus,
  durationMs: number | null,
  opts?: { error?: string; meta?: AuthStep['meta'] },
): void => {
  const run = readActive();
  if (!run) return;
  const step: AuthStep = {
    name,
    status,
    startedAt: Date.now() - (durationMs ?? 0),
    durationMs,
    error: opts?.error,
    meta: opts?.meta,
  };
  run.steps.push(step);
  writeActive(run);
  log(`step ${name} ${status}${durationMs != null ? ` (${durationMs}ms)` : ''}`, opts?.error ?? opts?.meta ?? '');
};

/** Time an async function and record the resulting step. */
export const timeStep = async <T,>(
  name: AuthStepName,
  fn: () => Promise<T>,
  opts?: { meta?: AuthStep['meta'] },
): Promise<T> => {
  const t0 = performance.now();
  try {
    const result = await fn();
    recordStep(name, 'ok', Math.round(performance.now() - t0), { meta: opts?.meta });
    return result;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    recordStep(name, 'error', Math.round(performance.now() - t0), { error: message, meta: opts?.meta });
    throw err;
  }
};

export const markPending = (name: AuthStepName, meta?: AuthStep['meta']): void => {
  recordStep(name, 'pending', null, { meta });
};

export const endAuthRun = (status: 'ok' | 'error', error?: string): void => {
  const run = readActive();
  if (!run) return;
  run.endedAt = Date.now();
  run.totalMs = run.endedAt - run.startedAt;
  run.status = status;
  if (error && !run.steps.some((s) => s.error === error)) {
    run.steps.push({ name: 'run_error', status: 'error', startedAt: Date.now(), durationMs: null, error });
  }

  const all = readRuns();
  all.push(run);
  writeRuns(all);
  writeActive(null);
  log(`run ended (${status}, ${run.totalMs}ms)`, run);
};

export const getRuns = (): AuthRun[] => readRuns();

export const getActiveRun = (): AuthRun | null => readActive();

export const clearRuns = (): void => {
  const w = safeWindow();
  if (!w) return;
  w.localStorage.removeItem(STORAGE_KEY);
  writeActive(null);
};

/** Aggregate statistics for the dashboard. */
export interface AuthStats {
  totalRuns: number;
  successRate: number;
  avgTotalMs: number;
  p50TotalMs: number;
  p95TotalMs: number;
  slowestRunMs: number;
  errorCount: number;
  perStep: Array<{ name: AuthStepName; avgMs: number; p95Ms: number; errorRate: number; samples: number }>;
}

const percentile = (sorted: number[], p: number): number => {
  if (sorted.length === 0) return 0;
  const idx = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length));
  return sorted[idx];
};

export const computeStats = (runs: AuthRun[]): AuthStats => {
  const completed = runs.filter((r) => r.totalMs != null);
  const totals = completed
    .map((r) => r.totalMs as number)
    .sort((a, b) => a - b);
  const okRuns = completed.filter((r) => r.status === 'ok');

  const stepMap = new Map<AuthStepName, { durations: number[]; errors: number }>();
  for (const run of runs) {
    for (const step of run.steps) {
      const bucket = stepMap.get(step.name) ?? { durations: [], errors: 0 };
      if (step.durationMs != null) bucket.durations.push(step.durationMs);
      if (step.status === 'error') bucket.errors += 1;
      stepMap.set(step.name, bucket);
    }
  }

  const perStep = Array.from(stepMap.entries()).map(([name, b]) => {
    const sorted = [...b.durations].sort((a, c) => a - c);
    const samples = b.durations.length + b.errors;
    return {
      name,
      avgMs: sorted.length ? Math.round(sorted.reduce((s, x) => s + x, 0) / sorted.length) : 0,
      p95Ms: percentile(sorted, 95),
      errorRate: samples ? b.errors / samples : 0,
      samples,
    };
  });

  return {
    totalRuns: runs.length,
    successRate: completed.length ? okRuns.length / completed.length : 0,
    avgTotalMs: totals.length ? Math.round(totals.reduce((s, x) => s + x, 0) / totals.length) : 0,
    p50TotalMs: percentile(totals, 50),
    p95TotalMs: percentile(totals, 95),
    slowestRunMs: totals.length ? totals[totals.length - 1] : 0,
    errorCount: runs.filter((r) => r.status === 'error').length,
    perStep,
  };
};
