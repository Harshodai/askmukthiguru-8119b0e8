import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { DailyTeaching } from '@/components/chat/DailyTeaching';

// Mock Supabase client
const mockMaybeSingle = vi.fn();
const mockLimit = vi.fn(() => ({ maybeSingle: mockMaybeSingle }));
const mockOrder = vi.fn(() => ({ limit: mockLimit }));
const mockSelect = vi.fn(() => ({ order: mockOrder }));
const mockFrom = vi.fn(() => ({ select: mockSelect }));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    from: () => ({ select: mockSelect }),
  },
}));

describe('DailyTeaching (database-backed)', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
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
    mockMaybeSingle.mockResolvedValue({ data: null, error: null });

    render(<DailyTeaching />);
    // Wait a tick for async effect
    await waitFor(() => {
      expect(mockFrom).toHaveBeenCalledWith('daily_teachings');
    });
    expect(screen.queryByTestId('daily-teaching')).not.toBeInTheDocument();
  });

  it('does not render when user already dismissed today', async () => {
    const today = new Date().toISOString().slice(0, 10);
    localStorage.setItem('askmukthiguru_teaching_dismissed', today);

    render(<DailyTeaching />);
    // Should not even fetch from database
    expect(mockFrom).not.toHaveBeenCalled();
    expect(screen.queryByTestId('daily-teaching')).not.toBeInTheDocument();
  });
});
