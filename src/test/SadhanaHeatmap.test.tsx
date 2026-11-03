import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { getPracticeIntensity, SadhanaHeatmap } from '@/components/profile/SadhanaHeatmap';
import { ProfileStatTiles } from '@/components/profile/ProfileStatTiles';
import type { MeditationStats } from '@/lib/meditationStorage';
import type { NormalizedSession } from '@/lib/meditationMetrics';

describe('Sadhana practice intensity', () => {
  it('derives intensity only from measured completed minutes', () => {
    expect(getPracticeIntensity(0)).toBe('rest');
    expect(getPracticeIntensity(1)).toBe('short');
    expect(getPracticeIntensity(9)).toBe('short');
    expect(getPracticeIntensity(10)).toBe('steady');
    expect(getPracticeIntensity(19)).toBe('steady');
    expect(getPracticeIntensity(20)).toBe('deep');
    expect(getPracticeIntensity(90)).toBe('deep');
  });

  it('never emits Beautiful State, Witnessing, or Conflict Transmuted classifications', () => {
    const allowed = new Set(['rest', 'short', 'steady', 'deep']);
    for (const minutes of [0, 3, 8, 10, 15, 20, 45, 90]) {
      expect(allowed.has(getPracticeIntensity(minutes))).toBe(true);
    }
  });
});

describe('Sadhana Heatmap & Streak > 7 days behavior', () => {
  const highStreakStats: MeditationStats = {
    totalSessions: 18,
    totalMinutes: 240,
    totalCycles: 50,
    streakDays: 10,
    longestStreakDays: 14,
    lastSessionDate: new Date(),
  };

  const lowStreakStats: MeditationStats = {
    totalSessions: 4,
    totalMinutes: 60,
    totalCycles: 15,
    streakDays: 3,
    longestStreakDays: 5,
    lastSessionDate: new Date(),
  };

  const sampleSessions: NormalizedSession[] = [
    {
      at: new Date(),
      durationSeconds: 900,
      breathCycles: 10,
      completed: true,
    },
  ];

  it('renders 20-week GitHub heatmap by default when streak > 7 days', () => {
    render(<ProfileStatTiles stats={highStreakStats} sessions={sampleSessions} />);

    // Heatmap section is present by default
    expect(screen.getByText(/Deep practice rhythm — full GitHub matrix view/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Switch to 7-Day Circle/i })).toBeInTheDocument();
  });

  it('renders 7-day Circle of Presence by default when streak <= 7 days', () => {
    render(<ProfileStatTiles stats={lowStreakStats} sessions={sampleSessions} />);

    // Circle of presence is present by default
    expect(screen.getByText(/Circle of Presence/i)).toBeInTheDocument();
    expect(screen.getByTitle(/View full GitHub-style sadhana heatmap/i)).toBeInTheDocument();
  });

  it('smoothly toggles between Heatmap and 7-day Circle on user action', async () => {
    render(<ProfileStatTiles stats={highStreakStats} sessions={sampleSessions} />);

    // Initial state: Heatmap
    expect(screen.getByText(/Deep practice rhythm/i)).toBeInTheDocument();

    // Click toggle to Circle
    fireEvent.click(screen.getByRole('button', { name: /Switch to 7-Day Circle/i }));
    await waitFor(() => {
      expect(screen.getByText(/Circle of Presence/i)).toBeInTheDocument();
    });

    // Click toggle back to Heatmap
    fireEvent.click(screen.getByTitle(/View full GitHub-style sadhana heatmap/i));
    await waitFor(() => {
      expect(screen.getByText(/Deep practice rhythm/i)).toBeInTheDocument();
    });
  });

  it('renders SadhanaHeatmap component with summary stats', () => {
    render(<SadhanaHeatmap sessions={sampleSessions} weeksToShow={20} />);
    expect(screen.getByText(/Sadhana/i)).toBeInTheDocument();
    expect(screen.getByText(/active days/i)).toBeInTheDocument();
  });
});
