import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const record = vi.fn();
vi.mock('@/lib/meditationStorage', () => ({
  recordMoodCheckIn: (...a: unknown[]) => record(...a),
  getMeditationStats: () => ({ streakDays: 0 }),
}));

import { MoodCheckIn } from '@/components/mood/MoodCheckIn';
import { getJourney } from '@/lib/dailyJourney';

const mic = () => ({
  isListening: false,
  transcript: '',
  start: vi.fn(),
  stop: vi.fn(),
  error: null,
  reset: vi.fn(),
  supported: true,
});

const ui = (isOpen: boolean) => (
  <MemoryRouter>
    <MoodCheckIn isOpen={isOpen} onClose={() => {}} micHook={mic} />
  </MemoryRouter>
);

const submitButton = () => screen.getAllByRole('button').find((b) => b.className.includes('rounded-full bg-gradient')) as HTMLElement;

describe('MoodCheckIn', () => {
  beforeEach(() => {
    localStorage.clear();
    record.mockReset();
  });

  it('saves once on a double tap and starts the journey only after the save is confirmed', async () => {
    let resolve!: () => void;
    record.mockImplementation(() => new Promise<void>((r) => { resolve = r; }));
    render(ui(true));
    fireEvent.click(screen.getByRole('button', { name: /anxious/i }));
    fireEvent.click(submitButton());
    fireEvent.click(submitButton());
    expect(record).toHaveBeenCalledTimes(1);
    expect(getJourney()).toBeNull();
    await act(async () => resolve());
    await waitFor(() => expect(getJourney()?.mood).toBe('anxious'));
  });

  it('keeps the mood and the typed reflection after a failed save and allows a retry', async () => {
    record.mockRejectedValueOnce(new Error('disk full')).mockResolvedValueOnce(undefined);
    render(ui(true));
    fireEvent.click(screen.getByRole('button', { name: /sad/i }));
    const box = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'heavy day' } });
    fireEvent.click(submitButton());
    await screen.findByRole('alert');
    expect(box.value).toBe('heavy day');
    expect(getJourney()).toBeNull();
    fireEvent.click(submitButton());
    await waitFor(() => expect(getJourney()?.mood).toBe('sad'));
    expect(record).toHaveBeenCalledTimes(2);
    expect(record).toHaveBeenLastCalledWith('sad', 'heavy day');
  });

  it('starts clean when reopened after a successful check-in', async () => {
    record.mockResolvedValue(undefined);
    const { rerender } = render(ui(true));
    fireEvent.click(screen.getByRole('button', { name: /calm/i }));
    fireEvent.click(submitButton());
    await waitFor(() => expect(getJourney()?.mood).toBe('calm'));
    rerender(ui(false));
    rerender(ui(true));
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('');
    expect(screen.getByRole('button', { name: /calm/i })).toHaveAttribute('aria-pressed', 'false');
  });
});
