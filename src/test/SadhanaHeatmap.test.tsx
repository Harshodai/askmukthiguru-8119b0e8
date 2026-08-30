import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SadhanaHeatmap } from '@/components/profile/SadhanaHeatmap';
import type { NormalizedSession } from '@/lib/meditationMetrics';
import { localDayKey } from '@/lib/meditationMetrics';

describe('SadhanaHeatmap', () => {
  it('renders correctly with empty sessions list', () => {
    render(<SadhanaHeatmap sessions={[]} weeksToShow={4} />);
    expect(screen.getByText(/Sadhana & Practice Matrix/i)).toBeInTheDocument();
    expect(screen.getByText(/0 days active/i)).toBeInTheDocument();
    expect(screen.getByText(/0.0 hrs total/i)).toBeInTheDocument();
    expect(screen.getByText(/0 completed sessions/i)).toBeInTheDocument();
    expect(screen.getByText(/0d streak \(best: 0d\)/i)).toBeInTheDocument();
  });

  it('calculates active days, total hours, session count, and streaks from completed sessions', () => {
    const today = new Date();
    const sessions: NormalizedSession[] = [
      {
        at: today,
        durationSeconds: 1800, // 30 mins -> deep sadhana
        breathCycles: 24,
        completed: true,
      },
      {
        at: new Date(today.getTime() - 24 * 60 * 60 * 1000), // 1 day ago
        durationSeconds: 1200, // 20 mins -> deep sadhana
        breathCycles: 16,
        completed: true,
      },
      {
        at: new Date(today.getTime() - 2 * 24 * 60 * 60 * 1000), // 2 days ago
        durationSeconds: 600, // 10 mins -> dedicated practice
        breathCycles: 8,
        completed: true,
      },
      {
        at: new Date(today.getTime() - 3 * 24 * 60 * 60 * 1000), // 3 days ago, incomplete and < STREAK_MIN_SECONDS
        durationSeconds: 15,
        breathCycles: 1,
        completed: false,
      },
    ];

    render(<SadhanaHeatmap sessions={sessions} weeksToShow={4} />);
    expect(screen.getByText(/3 days active/i)).toBeInTheDocument();
    expect(screen.getByText(/1.0 hrs total/i)).toBeInTheDocument();
    expect(screen.getByText(/3 completed sessions/i)).toBeInTheDocument();
    expect(screen.getByText(/3d streak \(best: 3d\)/i)).toBeInTheDocument();
  });

  it('correctly categorizes intensity buckets: gentle, dedicated, deep, and rest', () => {
    const today = new Date();
    const dayAgo1 = new Date(today.getTime() - 24 * 60 * 60 * 1000);
    const dayAgo2 = new Date(today.getTime() - 2 * 24 * 60 * 60 * 1000);
    const sessions: NormalizedSession[] = [
      {
        at: today,
        durationSeconds: 1500, // 25 mins -> Deep Sadhana (20+ min)
        breathCycles: 20,
        completed: true,
      },
      {
        at: dayAgo1,
        durationSeconds: 720, // 12 mins -> Dedicated Practice (10-20 min)
        breathCycles: 10,
        completed: true,
      },
      {
        at: dayAgo2,
        durationSeconds: 300, // 5 mins -> Gentle Practice (1-10 min)
        breathCycles: 5,
        completed: true,
      },
    ];

    render(<SadhanaHeatmap sessions={sessions} weeksToShow={4} />);

    // Verify aria-labels on day buttons
    const todayKey = localDayKey(today);
    const day1Key = localDayKey(dayAgo1);
    const day2Key = localDayKey(dayAgo2);

    expect(screen.getByLabelText(`${todayKey}: 25 min`)).toBeInTheDocument();
    expect(screen.getByLabelText(`${day1Key}: 12 min`)).toBeInTheDocument();
    expect(screen.getByLabelText(`${day2Key}: 5 min`)).toBeInTheDocument();
  });

  it('filters matrix by intensity bucket on filter button click', () => {
    render(<SadhanaHeatmap sessions={[]} weeksToShow={4} />);
    const filterButtons = screen.getAllByRole('button');

    const deepFilter = filterButtons.find((btn) => btn.textContent?.includes('Deep Sadhana'));
    expect(deepFilter).toBeDefined();
    if (deepFilter) {
      fireEvent.click(deepFilter);
      expect(deepFilter.className).toContain('bg-ojas/15');
    }

    const dedicatedFilter = filterButtons.find((btn) => btn.textContent?.includes('Dedicated Practice'));
    expect(dedicatedFilter).toBeDefined();
    if (dedicatedFilter) {
      fireEvent.click(dedicatedFilter);
      expect(dedicatedFilter.className).toContain('bg-ojas/15');
    }

    const gentleFilter = filterButtons.find((btn) => btn.textContent?.includes('Gentle Practice'));
    expect(gentleFilter).toBeDefined();
    if (gentleFilter) {
      fireEvent.click(gentleFilter);
      expect(gentleFilter.className).toContain('bg-ojas/15');
    }

    const allFilter = filterButtons.find((btn) => btn.textContent?.includes('All Days'));
    expect(allFilter).toBeDefined();
    if (allFilter) {
      fireEvent.click(allFilter);
      expect(allFilter.className).toContain('bg-ojas/15');
    }
  });

  it('accurately distinguishes historical longest streak from current streak with gaps', () => {
    const today = new Date();
    // 5-day historical streak from 20 to 16 days ago
    // Gap on days 15..2
    // 2-day current streak (today and 1 day ago)
    const sessions: NormalizedSession[] = [
      // Current streak: 2 days
      { at: today, durationSeconds: 600, breathCycles: 5, completed: true },
      { at: new Date(today.getTime() - 24 * 60 * 60 * 1000), durationSeconds: 600, breathCycles: 5, completed: true },
      // Historical streak: 5 days
      { at: new Date(today.getTime() - 16 * 24 * 60 * 60 * 1000), durationSeconds: 600, breathCycles: 5, completed: true },
      { at: new Date(today.getTime() - 17 * 24 * 60 * 60 * 1000), durationSeconds: 600, breathCycles: 5, completed: true },
      { at: new Date(today.getTime() - 18 * 24 * 60 * 60 * 1000), durationSeconds: 600, breathCycles: 5, completed: true },
      { at: new Date(today.getTime() - 19 * 24 * 60 * 60 * 1000), durationSeconds: 600, breathCycles: 5, completed: true },
      { at: new Date(today.getTime() - 20 * 24 * 60 * 60 * 1000), durationSeconds: 600, breathCycles: 5, completed: true },
    ];

    render(<SadhanaHeatmap sessions={sessions} weeksToShow={4} />);
    expect(screen.getByText(/7 days active/i)).toBeInTheDocument();
    expect(screen.getByText(/7 completed sessions/i)).toBeInTheDocument();
    expect(screen.getByText(/2d streak \(best: 5d\)/i)).toBeInTheDocument();
  });

  it('aggregates multiple sessions on the same day into cumulative minutes and breath cycles', () => {
    const today = new Date();
    const sessions: NormalizedSession[] = [
      { at: today, durationSeconds: 600, breathCycles: 8, completed: true }, // 10 min
      { at: today, durationSeconds: 900, breathCycles: 12, completed: true }, // 15 min -> 25 min total (Deep Sadhana)
    ];

    render(<SadhanaHeatmap sessions={sessions} weeksToShow={4} />);
    expect(screen.getByText(/1 days active/i)).toBeInTheDocument();
    expect(screen.getByText(/2 completed sessions/i)).toBeInTheDocument();
    expect(screen.getByLabelText(`${localDayKey(today)}: 25 min`)).toBeInTheDocument();
  });
});
