import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const { getUser, incognito, rpc } = vi.hoisted(() => ({ getUser: vi.fn(), incognito: vi.fn(), rpc: vi.fn() }));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getUser }, from: vi.fn(), rpc },
}));
vi.mock('@/lib/chatStorage', () => ({ isIncognitoMode: incognito }));

import { FacultyReviewGate, hasFacultyReviewerRole } from '@/components/chat/FacultyReviewGate';

describe('FacultyReviewGate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    incognito.mockReturnValue(false);
    rpc.mockResolvedValue({ data: false, error: null });
    getUser.mockResolvedValue({ data: { user: { id: 'u1', app_metadata: { role: 'faculty_reviewer' } } } });
  });
  afterEach(() => vi.unstubAllEnvs());

  it('renders nothing when the flag is off or absent', async () => {
    vi.stubEnv('VITE_FACULTY_REVIEW_ENABLED', '');
    render(<FacultyReviewGate crisis={false} traceId="t1" />);
    await Promise.resolve();
    expect(screen.queryByRole('group', { name: 'Faculty label' })).toBeNull();
    expect(getUser).not.toHaveBeenCalled();
  });

  it('renders nothing on a crisis answer even with the flag on', async () => {
    vi.stubEnv('VITE_FACULTY_REVIEW_ENABLED', 'true');
    render(<FacultyReviewGate crisis traceId="t1" />);
    await Promise.resolve();
    expect(screen.queryByRole('group', { name: 'Faculty label' })).toBeNull();
  });

  it('renders nothing when signed out or incognito', async () => {
    vi.stubEnv('VITE_FACULTY_REVIEW_ENABLED', 'true');
    getUser.mockResolvedValue({ data: { user: null } });
    const { unmount } = render(<FacultyReviewGate crisis={false} traceId="t1" />);
    await waitFor(() => expect(getUser).toHaveBeenCalled());
    expect(screen.queryByRole('group', { name: 'Faculty label' })).toBeNull();
    unmount();
    getUser.mockResolvedValue({ data: { user: { id: 'u1' } } });
    incognito.mockReturnValue(true);
    render(<FacultyReviewGate crisis={false} traceId="t1" />);
    await waitFor(() => expect(getUser).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('group', { name: 'Faculty label' })).toBeNull();
  });

  it('shows the panel when flag on, signed in, not incognito, not crisis', async () => {
    vi.stubEnv('VITE_FACULTY_REVIEW_ENABLED', 'true');
    render(<FacultyReviewGate crisis={false} traceId="t1" />);
    expect(await screen.findByRole('group', { name: 'Faculty label' })).toBeInTheDocument();
  });

  it('shows the panel for an admin without the reviewer claim', async () => {
    vi.stubEnv('VITE_FACULTY_REVIEW_ENABLED', 'true');
    getUser.mockResolvedValue({ data: { user: { id: 'admin1', app_metadata: {} } } });
    rpc.mockResolvedValue({ data: true, error: null });
    render(<FacultyReviewGate crisis={false} traceId="t1" />);
    expect(await screen.findByRole('group', { name: 'Faculty label' })).toBeInTheDocument();
    expect(rpc).toHaveBeenCalledWith('has_role', { _user_id: 'admin1', _role: 'admin' });
  });

  it('blocks a plain signed-in user and an admin-check error', async () => {
    vi.stubEnv('VITE_FACULTY_REVIEW_ENABLED', 'true');
    getUser.mockResolvedValue({ data: { user: { id: 'u2', app_metadata: {} } } });
    const { unmount } = render(<FacultyReviewGate crisis={false} traceId="t1" />);
    await waitFor(() => expect(rpc).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('group', { name: 'Faculty label' })).toBeNull();
    unmount();
    rpc.mockResolvedValue({ data: true, error: { message: 'boom' } });
    render(<FacultyReviewGate crisis={false} traceId="t1" />);
    await waitFor(() => expect(rpc).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('group', { name: 'Faculty label' })).toBeNull();
  });

  it('never treats an ordinary account or user-editable metadata as a reviewer', () => {
    expect(hasFacultyReviewerRole({ app_metadata: {}, user_metadata: { role: 'faculty_reviewer' } })).toBe(false);
    expect(hasFacultyReviewerRole({ app_metadata: { role: 'teacher' } })).toBe(false);
    expect(hasFacultyReviewerRole({ app_metadata: { role: 'faculty_reviewer' } })).toBe(true);
  });
});
