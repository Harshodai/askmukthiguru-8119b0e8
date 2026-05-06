import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { DailyTeaching } from '@/components/chat/DailyTeaching';

// Build chain mock
const mockMaybeSingle = vi.fn().mockResolvedValue({ data: null, error: null });
const mockLimit = vi.fn(() => ({ maybeSingle: mockMaybeSingle }));
const mockOrder = vi.fn(() => ({ limit: mockLimit }));
const mockSelect = vi.fn(() => ({ order: mockOrder }));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    from: vi.fn(() => ({ select: mockSelect })),
  },
}));

describe('DailyTeaching (database-backed)', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    // Reset chain
    mockMaybeSingle.mockResolvedValue({ data: null, error: null });
    mockLimit.mockReturnValue({ maybeSingle: mockMaybeSingle });
    mockOrder.mockReturnValue({ limit: mockLimit });
    mockSelect.mockReturnValue({ order: mockOrder });
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

  it('does not render when user already dismissed today', () => {
    const today = new Date().toISOString().slice(0, 10);
    localStorage.setItem('askmukthiguru_teaching_dismissed', today);

    render(<DailyTeaching />);
    expect(screen.queryByTestId('daily-teaching')).not.toBeInTheDocument();
  });
});
