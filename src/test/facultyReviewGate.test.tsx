import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const { getUser, incognito } = vi.hoisted(() => ({ getUser: vi.fn(), incognito: vi.fn() }));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getUser }, from: vi.fn() },
}));
vi.mock('@/lib/chatStorage', () => ({ isIncognitoMode: incognito }));

import { FacultyReviewGate } from '@/components/chat/FacultyReviewGate';

describe('FacultyReviewGate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    incognito.mockReturnValue(false);
    getUser.mockResolvedValue({ data: { user: { id: 'u1' } } });
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
});
