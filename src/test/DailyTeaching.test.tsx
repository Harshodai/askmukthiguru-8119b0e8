import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DailyTeaching, setDailyTeaching, getDailyTeaching } from '@/components/chat/DailyTeaching';

describe('DailyTeaching', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('returns null when no teaching is set', () => {
    const { container } = render(<DailyTeaching />);
    expect(container.firstChild).toBeNull();
  });

  it('renders teaching when data exists', () => {
    setDailyTeaching({
      id: 't1',
      imageUrl: '/test-image.jpg',
      caption: 'The Beautiful State awaits you',
      date: new Date().toISOString().slice(0, 10),
    });
    render(<DailyTeaching />);
    expect(screen.getByText("Today's Teaching")).toBeInTheDocument();
    expect(screen.getByText('The Beautiful State awaits you')).toBeInTheDocument();
  });

  it('dismisses when close button is clicked', () => {
    setDailyTeaching({
      id: 't1',
      imageUrl: '/test-image.jpg',
      caption: 'Test teaching',
      date: new Date().toISOString().slice(0, 10),
    });
    render(<DailyTeaching />);
    const dismissBtn = screen.getByLabelText('Dismiss teaching');
    fireEvent.click(dismissBtn);
    expect(screen.queryByText("Today's Teaching")).not.toBeInTheDocument();
  });

  it('setDailyTeaching and getDailyTeaching round-trip correctly', () => {
    const data = {
      id: 't1',
      imageUrl: '/test.jpg',
      caption: 'Test',
      date: '2026-05-05',
    };
    setDailyTeaching(data);
    const result = getDailyTeaching();
    expect(result).toEqual(data);
  });
});
