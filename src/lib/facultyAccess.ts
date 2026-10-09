/**
 * Faculty preview access code.
 *
 * Build-time switch VITE_FACULTY_GATE_ENABLED=true shows a passcode screen before
 * the app. The code lives in sessionStorage only (cleared when the tab closes) and
 * is sent as X-Faculty-Code on backend requests. The real enforcement is on the
 * server (FACULTY_ACCESS_CODE, app/middleware/faculty_gate.py): this file only
 * collects and forwards the code. Nothing here is a secret.
 */
import { BACKEND_URL } from '@/lib/backendUrl';

const STORAGE_KEY = 'faculty-access-code';
export const FACULTY_HEADER = 'X-Faculty-Code';

export const facultyGateEnabled = (): boolean => import.meta.env.VITE_FACULTY_GATE_ENABLED === 'true';

export function getFacultyCode(): string {
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? '';
  } catch {
    return '';
  }
}

export function setFacultyCode(code: string): void {
  try {
    if (code) sessionStorage.setItem(STORAGE_KEY, code);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage blocked: the gate will simply ask again */
  }
}

export type CodeCheck = 'ok' | 'wrong' | 'unreachable';

/** Ask the backend whether this code passes the gate. 401 = wrong; any other HTTP answer = the gate let us through. */
export async function checkFacultyCode(code: string, fetchImpl: typeof fetch = fetch): Promise<CodeCheck> {
  try {
    const res = await fetchImpl(`${BACKEND_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', [FACULTY_HEADER]: code },
      body: '{}',
    });
    return res.status === 401 ? 'wrong' : 'ok';
  } catch {
    return 'unreachable';
  }
}

function isBackendRequest(url: string): boolean {
  if (BACKEND_URL) return url.startsWith(BACKEND_URL);
  return url.startsWith('/api/');
}

let installed = false;

/** Attach the stored code to every backend request. Idempotent; no-op when the gate is off. */
export function installFacultyFetchHeader(): void {
  if (installed || !facultyGateEnabled() || typeof window === 'undefined') return;
  installed = true;
  const original = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const code = getFacultyCode();
    if (!code || !isBackendRequest(url)) return original(input, init);
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    if (!headers.has(FACULTY_HEADER)) headers.set(FACULTY_HEADER, code);
    return original(input, { ...init, headers });
  };
}
