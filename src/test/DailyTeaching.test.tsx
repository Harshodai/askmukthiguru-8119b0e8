import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DailyTeaching, setDailyTeaching, getDailyTeaching, clearDailyTeaching } from '@/components/chat/DailyTeaching';

describe('DailyTeaching TTL', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('returns null when no teaching is stored', () => {
    expect(getDailyTeaching()).toBeNull();
  });

  it('stores and retrieves teaching for today', () => {
    const today = new Date().toISOString().slice(0, 10);
    setDailyTeaching({
      id: 'test-1',
      imageUrl: 'data:image/png;base64,abc',
      caption: 'Test teaching',
      date: today,
    });
    const result = getDailyTeaching();
    expect(result).not.toBeNull();
    expect(result!.caption).toBe('Test teaching');
  });

  it('returns null and cleans up for expired teaching (yesterday)', () => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const dateStr = yesterday.toISOString().slice(0, 10);

    setDailyTeaching({
      id: 'old',
      imageUrl: 'data:image/png;base64,old',
      caption: 'Old',
      date: dateStr,
    });

    const result = getDailyTeaching();
    expect(result).toBeNull();
    // Should also have cleaned up localStorage
    expect(localStorage.getItem('askmukthiguru_daily_teaching')).toBeNull();
  });

  it('clearDailyTeaching removes both teaching and dismissed state', () => {
    const today = new Date().toISOString().slice(0, 10);
    setDailyTeaching({
      id: 'test-2',
      imageUrl: 'data:image/png;base64,xyz',
      date: today,
    });
    localStorage.setItem('askmukthiguru_teaching_dismissed', today);

    clearDailyTeaching();
    expect(getDailyTeaching()).toBeNull();
    expect(localStorage.getItem('askmukthiguru_teaching_dismissed')).toBeNull();
  });

  it('renders teaching banner for today', () => {
    const today = new Date().toISOString().slice(0, 10);
    setDailyTeaching({
      id: 'render-test',
      imageUrl: 'data:image/png;base64,render',
      caption: 'Be in your beautiful state',
      date: today,
    });

    render(<DailyTeaching />);
    expect(screen.getByText('Be in your beautiful state')).toBeInTheDocument();
    expect(screen.getByTestId('daily-teaching')).toBeInTheDocument();
  });

  it('does not render for expired teaching', () => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    setDailyTeaching({
      id: 'expired',
      imageUrl: 'data:image/png;base64,exp',
      caption: 'Expired',
      date: yesterday.toISOString().slice(0, 10),
    });

    render(<DailyTeaching />);
    expect(screen.queryByTestId('daily-teaching')).not.toBeInTheDocument();
  });
});