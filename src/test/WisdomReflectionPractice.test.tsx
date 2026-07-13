import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { WisdomReflectionPractice } from '@/components/meditation/WisdomReflectionPractice';

const { useDailyTeaching } = vi.hoisted(() => ({ useDailyTeaching: vi.fn() }));

vi.mock('@/hooks/useDailyTeaching', () => ({ useDailyTeaching }));
vi.mock('@/components/meditation/FlashcardPractice', () => ({
  FlashcardPractice: () => <div data-testid="mock-flashcard-practice" />
}));

afterEach(() => vi.useRealTimers());

describe('WisdomReflectionPractice', () => {
  it('uses a clearly labelled fallback when no daily teaching is available', () => {
    useDailyTeaching.mockReturnValue({ teaching: null, loading: false });

    render(<WisdomReflectionPractice />);

    expect(screen.getByText(/no active Daily Teaching is available/i)).toBeInTheDocument();
    expect(screen.getByText(/Take a quiet moment to notice/i)).toBeInTheDocument();
  });

  it('shows post-practice check-in without requiring an account', () => {
    useDailyTeaching.mockReturnValue({
      teaching: { id: 'today', image_url: 'https://example.test/teaching.jpg', caption: 'Authentic teaching text' },
      loading: false,
    });

    render(<WisdomReflectionPractice />);
    expect(screen.getByText('Authentic teaching text')).toBeInTheDocument();
    expect(screen.getByText(/Source: Daily Teaching/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /ready to check in/i }));
    fireEvent.click(screen.getByRole('button', { name: 'More settled' }));

    expect(screen.getByText(/Thank you for noticing/i)).toBeInTheDocument();
  });

  it('finishes after three minutes and reset cancels the countdown', () => {
    vi.useFakeTimers();
    useDailyTeaching.mockReturnValue({ teaching: null, loading: false });
    render(<WisdomReflectionPractice />);

    fireEvent.click(screen.getByRole('button', { name: 'Begin' }));
    act(() => vi.advanceTimersByTime(5_000));
    fireEvent.click(screen.getByRole('button', { name: /reset/i }));
    act(() => vi.advanceTimersByTime(180_000));
    expect(screen.getByText('3:00')).toBeInTheDocument();
    expect(screen.queryByText(/Reflection complete/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Begin' }));
    act(() => vi.advanceTimersByTime(180_000));
    expect(screen.getByText(/Reflection complete/i)).toBeInTheDocument();
  });
});
