import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('@capacitor/core', () => ({ Capacitor: { isNativePlatform: () => false } }));

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  vi.stubEnv('VITE_BACKEND_URL', 'https://api.test');
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('FacultyAccessGate', () => {
  it('renders children untouched when the gate is off', async () => {
    vi.stubEnv('VITE_FACULTY_GATE_ENABLED', 'false');
    const { FacultyAccessGate } = await import('@/components/common/FacultyAccessGate');
    render(<FacultyAccessGate><p>app</p></FacultyAccessGate>);
    expect(screen.getByText('app')).toBeTruthy();
  });

  it('hides the app, rejects a wrong code, and unlocks on a right one', async () => {
    vi.stubEnv('VITE_FACULTY_GATE_ENABLED', 'true');
    const fetchMock = vi.fn(async (_u: string, init?: RequestInit) => {
      const h = new Headers(init?.headers);
      return new Response('{}', { status: h.get('X-Faculty-Code') === 'good' ? 422 : 401 });
    });
    vi.stubGlobal('fetch', fetchMock);
    const { FacultyAccessGate } = await import('@/components/common/FacultyAccessGate');
    render(<FacultyAccessGate><p>app</p></FacultyAccessGate>);
    expect(screen.queryByText('app')).toBeNull();

    const input = screen.getByLabelText('Access code');
    fireEvent.change(input, { target: { value: 'bad' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.queryByText('app')).toBeNull();

    fireEvent.change(input, { target: { value: 'good' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(screen.getByText('app')).toBeTruthy());
    expect(sessionStorage.getItem('faculty-access-code')).toBe('good');
  });

  it('reports an unreachable server instead of unlocking', async () => {
    vi.stubEnv('VITE_FACULTY_GATE_ENABLED', 'true');
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network'); }));
    const { FacultyAccessGate } = await import('@/components/common/FacultyAccessGate');
    render(<FacultyAccessGate><p>app</p></FacultyAccessGate>);
    fireEvent.change(screen.getByLabelText('Access code'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Could not reach'));
    expect(screen.queryByText('app')).toBeNull();
  });
});

describe('installFacultyFetchHeader', () => {
  it('adds the code to backend requests only', async () => {
    vi.stubEnv('VITE_FACULTY_GATE_ENABLED', 'true');
    sessionStorage.setItem('faculty-access-code', 'good');
    const base = vi.fn(async () => new Response('{}'));
    vi.stubGlobal('fetch', base);
    window.fetch = base as unknown as typeof fetch;
    const mod = await import('@/lib/facultyAccess');
    mod.installFacultyFetchHeader();
    await window.fetch('https://api.test/api/chat', { method: 'POST' });
    await window.fetch('https://other.test/x');
    const calls = base.mock.calls as unknown as [string, RequestInit | undefined][];
    expect(new Headers(calls[0][1]?.headers).get('X-Faculty-Code')).toBe('good');
    expect(calls[1][1]).toBeUndefined();
  });
});
