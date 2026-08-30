import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SadhanaHeatmap } from '@/components/profile/SadhanaHeatmap';
import type { NormalizedSession } from '@/lib/meditationMetrics';

describe('SadhanaHeatmap', () => {
  it('renders correctly with empty sessions list', () => {
    render(<SadhanaHeatmap sessions={[]} weeksToShow={4} />);
    expect(screen.getByText(/Sadhana & Consciousness Matrix/i)).toBeInTheDocument();
    expect(screen.getByText(/0 days active/i)).toBeInTheDocument();
    expect(screen.getByText(/0.0 hrs total/i)).toBeInTheDocument();
  });

  it('calculates active days and total hours from completed sessions', () => {
    const today = new Date();
    const sessions: NormalizedSession[] = [
      {
        at: today,
        durationSeconds: 1800, // 30 mins -> sadhana state
        breathCycles: 20,
        completed: true,
      },
      {
        at: new Date(today.getTime() - 24 * 60 * 60 * 1000), // 1 day ago
        durationSeconds: 900, // 15 mins
        breathCycles: 10,
        completed: true,
      },
      {
        at: new Date(today.getTime() - 48 * 60 * 60 * 1000), // 2 days ago, incomplete
        durationSeconds: 600,
        breathCycles: 5,
        completed: false,
      },
    ];

    render(<SadhanaHeatmap sessions={sessions} weeksToShow={4} />);
    expect(screen.getByText(/2 days active/i)).toBeInTheDocument();
    expect(screen.getByText(/0.8 hrs total/i)).toBeInTheDocument();
  });

  it('filters matrix states on filter button click', () => {
    render(<SadhanaHeatmap sessions={[]} weeksToShow={4} />);
    const filterButtons = screen.getAllByRole('button');
    const sadhanaFilter = filterButtons.find((btn) => btn.textContent?.includes('Dedicated Sadhana'));
    expect(sadhanaFilter).toBeDefined();
    if (sadhanaFilter) {
      fireEvent.click(sadhanaFilter);
      expect(sadhanaFilter.className).toContain('bg-ojas/15');
    }
  });
});
