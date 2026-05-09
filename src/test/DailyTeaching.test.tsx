import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { DailyTeaching } from '@/components/chat/DailyTeaching';

// Build chain mock
const mockMaybeSingle = vi.fn().mockResolvedValue({ data: null, error: null });
const mockLimit = vi.fn(() => ({ maybeSingle: mockMaybeSingle }));
const mockOrder = vi.fn(() => ({ limit: mockLimit }));
const mockSelect = vi.fn(() => ({ order: mockOrder }));

// Realtime channel mock — chainable .on().subscribe()
const mockSubscribe = vi.fn(() => ({ unsubscribe: vi.fn() }));
const mockOn = vi.fn(() => ({ subscribe: mockSubscribe }));
const mockChannel = vi.fn(() => ({ on: mockOn }));
const mockRemoveChannel = vi.fn();

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    from: vi.fn(() => ({ select: mockSelect })),
    channel: (...args: unknown[]) => mockChannel(...args),
    removeChannel: (...args: unknown[]) => mockRemoveChannel(...args),
  },
}));

describe('DailyTeaching (database-backed)', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    mockMaybeSingle.mockResolvedValue({ data: null, error: null });
    mockLimit.mockReturnValue({ maybeSingle: mockMaybeSingle });
    mockOrder.mockReturnValue({ limit: mockLimit });
    mockSelect.mockReturnValue({ order: mockOrder });
    mockOn.mockReturnValue({ subscribe: mockSubscribe });
    mockChannel.mockReturnValue({ on: mockOn });
  });

  it('renders teaching when database returns active teaching', async () => {
    mockMaybeSingle.mockResolvedValue({
      data: {
        id: 'test-1',
        image_url: 'https://example.com/teaching.jpg',
        caption: 'Be in your beautiful state',
      },
      error: null,
    });

    render(<DailyTeaching />);
    await waitFor(() => {
      expect(screen.getByText('Be in your beautiful state')).toBeInTheDocument();
    });
    expect(screen.getByTestId('daily-teaching')).toBeInTheDocument();
  });

  it('does not render when no active teaching exists', async () => {
    render(<DailyTeaching />);
    await waitFor(() => {
      expect(mockSelect).toHaveBeenCalled();
    });
    expect(screen.queryByTestId('daily-teaching')).not.toBeInTheDocument();
  });

  it('does not render when user dismissed this exact teaching id', async () => {
    localStorage.setItem('askmukthiguru_teaching_dismissed_id', 'test-1');
    mockMaybeSingle.mockResolvedValue({
      data: { id: 'test-1', image_url: 'https://example.com/teaching.jpg', caption: 'X' },
      error: null,
    });

    render(<DailyTeaching />);
    await waitFor(() => {
      expect(mockSelect).toHaveBeenCalled();
    });
    expect(screen.queryByTestId('daily-teaching')).not.toBeInTheDocument();
  });

  it('re-shows when a NEW teaching id arrives (different from dismissed)', async () => {
    localStorage.setItem('askmukthiguru_teaching_dismissed_id', 'old-id');
    mockMaybeSingle.mockResolvedValue({
      data: { id: 'new-id', image_url: 'https://example.com/x.jpg', caption: 'Fresh wisdom' },
      error: null,
    });

    render(<DailyTeaching />);
    await waitFor(() => {
      expect(screen.getByText('Fresh wisdom')).toBeInTheDocument();
    });
  });

  it('subscribes to realtime daily_teachings INSERT events', async () => {
    render(<DailyTeaching />);
    await waitFor(() => {
      expect(mockChannel).toHaveBeenCalledWith('daily-teachings-feed');
      expect(mockOn).toHaveBeenCalled();
      expect(mockSubscribe).toHaveBeenCalled();
    });
  });
});
