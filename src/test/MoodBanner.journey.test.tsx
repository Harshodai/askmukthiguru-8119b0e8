import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MoodBanner } from '@/components/mood/MoodBanner';
import { completeStep, getJourney, startJourney } from '@/lib/dailyJourney';

const navigate = vi.fn();
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => navigate,
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_k: string, d?: string | Record<string, unknown>, o?: Record<string, string>) => {
      const text = typeof d === 'string' ? d : _k;
      return text.replace(/\{\{(\w+)\}\}/g, (_m, name) => (o ?? (d as Record<string, string>))?.[name] ?? '');
    },
  }),
}));
vi.mock('@/components/mood/MoodCheckIn', () => ({ MoodCheckIn: () => null }));

const renderBanner = () => render(<MemoryRouter><MoodBanner /></MemoryRouter>);

describe('MoodBanner daily journey', () => {
  beforeEach(() => {
    localStorage.clear();
    navigate.mockClear();
    // A recent check-in keeps the plain check-in banner hidden.
    localStorage.setItem('askmukthiguru_last_mood_checkin', String(Date.now()));
  });

  it('shows nothing without a started journey', () => {
    renderBanner();
    expect(screen.queryByTestId('journey-resume')).toBeNull();
  });

  it('points at the teaching step first and opens chat with a mood-based question', () => {
    startJourney('anxious', 'serene-mind');
    renderBanner();
    fireEvent.click(screen.getByTestId('journey-resume-cta'));
    expect(navigate).toHaveBeenCalledTimes(1);
    expect(navigate.mock.calls[0][0]).toMatch(/^\/chat\?q=/);
    expect(decodeURIComponent(navigate.mock.calls[0][0])).toContain('anxious');
    // Opening chat alone proves nothing.
    expect(getJourney()?.done.teaching).toBeUndefined();
  });

  it('moves on to the reflection step after the teaching and practice are confirmed', () => {
    startJourney('sad', 'beautiful-state');
    renderBanner();
    act(() => { completeStep('teaching'); });
    act(() => { completeStep('practice'); });
    fireEvent.click(screen.getByTestId('journey-resume-cta'));
    expect(navigate).toHaveBeenCalledWith('/profile?tab=memory');
  });

  it('hides the banner once every step is done', () => {
    startJourney('calm', 'beautiful-state');
    renderBanner();
    act(() => { completeStep('teaching'); completeStep('practice'); completeStep('reflection'); });
    expect(screen.queryByTestId('journey-resume')).toBeNull();
  });
});
