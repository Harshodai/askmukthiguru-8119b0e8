import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

const translations: Record<string, string> = {
  'mood.title': 'Mood check-in',
  'mood.subtitle': 'A gentle moment.',
  'mood.calm': 'Calm',
  'mood.anxious': 'Anxious',
  'mood.sad': 'Sad',
  'mood.frustrated': 'Frustrated',
  'mood.open': 'Open',
  'mood.reflectionLabel': "What's going on?",
  'mood.reflectionPlaceholder': 'Optional',
  'mood.suggestedPractice': 'A practice that may help',
  'mood.startPractice': 'Start practice',
  'mood.submit': 'Submit check-in',
  'mood.thanks': 'Thanks for sharing. 🙏',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => translations[k] ?? k }),
}));

const { recordMock } = vi.hoisted(() => ({ recordMock: vi.fn().mockResolvedValue({}) }));
vi.mock('@/lib/meditationStorage', () => ({
  recordMoodCheckIn: recordMock,
}));

vi.mock('@/lib/practicesContent', () => ({
  practices: [
    { slug: 'serene-mind', title: 'Serene Mind' },
    { slug: 'beautiful-state', title: 'Beautiful State' },
  ],
}));

import { MoodCheckIn } from '@/components/mood/MoodCheckIn';
import { recordMoodCheckIn } from '@/lib/meditationStorage';

describe('MoodCheckIn', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('suggests serene-mind for anxious mood', async () => {
    render(<BrowserRouter><MoodCheckIn isOpen onClose={vi.fn()} /></BrowserRouter>);
    fireEvent.click(screen.getByLabelText('Anxious'));
    await waitFor(() => expect(screen.getByText('Serene Mind')).toBeInTheDocument());
  });

  it('suggests beautiful-state for sad mood', async () => {
    render(<BrowserRouter><MoodCheckIn isOpen onClose={vi.fn()} /></BrowserRouter>);
    fireEvent.click(screen.getByLabelText('Sad'));
    await waitFor(() => expect(screen.getByText('Beautiful State')).toBeInTheDocument());
  });

  it('writes mood and reflection to meditationStorage on submit', async () => {
    render(<BrowserRouter><MoodCheckIn isOpen onClose={vi.fn()} /></BrowserRouter>);
    fireEvent.click(screen.getByLabelText('Calm'));
    fireEvent.change(screen.getByPlaceholderText('Optional'), { target: { value: 'feeling light' } });
    fireEvent.click(screen.getByText('Submit check-in'));
    await waitFor(() => expect(recordMoodCheckIn).toHaveBeenCalledWith('calm', 'feeling light'));
    await waitFor(() => expect(screen.getByText('Thanks for sharing. 🙏')).toBeInTheDocument());
  });
});
