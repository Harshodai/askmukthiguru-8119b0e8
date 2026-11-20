import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import WaitlistSubscribersPage from '@/admin/pages/WaitlistSubscribersPage';
import { listWaitlistSubscribers } from '@/admin/lib/waitlistSubscribers';

const { fromMock } = vi.hoisted(() => ({ fromMock: vi.fn() }));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { from: fromMock },
}));

const mockUseWaitlistSubscribers = vi.fn();
vi.mock('@/admin/hooks/useAdminData', () => ({
  useWaitlistSubscribers: () => mockUseWaitlistSubscribers(),
}));

describe('listWaitlistSubscribers loader', () => {
  beforeEach(() => {
    fromMock.mockReset();
  });

  it('queries waitlist_entries with required columns and newest-first ordering', async () => {
    const limitMock = vi.fn().mockResolvedValue({
      data: [
        {
          id: '1',
          email: 'seeker1@example.com',
          source: 'guide_ai_spiritual_companion',
          consented_at: '2026-11-20T08:00:00Z',
        },
      ],
      error: null,
    });
    const orderMock = vi.fn().mockReturnValue({ limit: limitMock });
    const selectMock = vi.fn().mockReturnValue({ order: orderMock });
    fromMock.mockReturnValue({ select: selectMock });

    const result = await listWaitlistSubscribers(100);

    expect(fromMock).toHaveBeenCalledWith('waitlist_entries');
    expect(selectMock).toHaveBeenCalledWith('id,email,source,consented_at');
    expect(orderMock).toHaveBeenCalledWith('consented_at', { ascending: false });
    expect(limitMock).toHaveBeenCalledWith(100);
    expect(result).toHaveLength(1);
    expect(result[0].email).toBe('seeker1@example.com');
  });

  it('throws a generic error that contains no email address on failure', async () => {
    const limitMock = vi.fn().mockResolvedValue({
      data: null,
      error: { message: 'permission denied for table waitlist_entries' },
    });
    const orderMock = vi.fn().mockReturnValue({ limit: limitMock });
    const selectMock = vi.fn().mockReturnValue({ order: orderMock });
    fromMock.mockReturnValue({ select: selectMock });

    await expect(listWaitlistSubscribers(50)).rejects.toThrow(
      'Could not load launch subscribers. Retry, or confirm admin MFA is active.',
    );
  });
});

describe('WaitlistSubscribersPage component', () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const renderPage = () =>
    render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <WaitlistSubscribersPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

  it('renders loading skeleton when loading', () => {
    mockUseWaitlistSubscribers.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    const { container } = renderPage();
    expect(container.querySelectorAll('.animate-pulse')).not.toHaveLength(0);
  });

  it('renders error state without echoing any email address', () => {
    mockUseWaitlistSubscribers.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Could not load launch subscribers. Retry, or confirm admin MFA is active.'),
      refetch: vi.fn(),
    });

    renderPage();
    expect(screen.getByText('Subscribers unavailable')).toBeInTheDocument();
    expect(
      screen.getByText('Could not load launch subscribers. Retry, or confirm admin MFA is active.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/@/)).not.toBeInTheDocument();
  });

  it('renders empty state when there are no subscribers', () => {
    mockUseWaitlistSubscribers.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    expect(screen.getAllByText('No subscribers yet').length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Email sending is not configured/i),
    ).toBeInTheDocument();
  });

  it('renders table with subscriber entries and no send button', () => {
    mockUseWaitlistSubscribers.mockReturnValue({
      data: [
        {
          id: 'sub-1',
          email: 'seeker1@example.com',
          source: 'guide_ai_spiritual_companion',
          consented_at: '2026-11-20T08:00:00Z',
        },
        {
          id: 'sub-2',
          email: 'seeker2@example.com',
          source: 'guide_serene_mind',
          consented_at: '2026-11-20T07:30:00Z',
        },
      ],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    expect(screen.getByText('2 subscribers')).toBeInTheDocument();
    expect(screen.getByText('seeker1@example.com')).toBeInTheDocument();
    expect(screen.getByText('guide_ai_spiritual_companion')).toBeInTheDocument();
    expect(screen.getByText('seeker2@example.com')).toBeInTheDocument();
    expect(screen.getByText('guide_serene_mind')).toBeInTheDocument();

    // Verify sending is NOT configured and no send button exists
    expect(
      screen.getByText(/Email sending is not configured\. These addresses are collected only/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /send/i })).not.toBeInTheDocument();
  });
});
