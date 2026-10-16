import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { JourneyOverview } from '@/components/profile/JourneyOverview';
import type { MeditationStats } from '@/lib/meditationStorage';
import type { Conversation } from '@/lib/chatStorage';

const stats: MeditationStats = {
  totalSessions: 12,
  totalMinutes: 180,
  totalCycles: 40,
  streakDays: 5,
  longestStreakDays: 9,
  lastSessionDate: new Date(),
};

const zeroStats: MeditationStats = {
  totalSessions: 0,
  totalMinutes: 0,
  totalCycles: 0,
  streakDays: 0,
  longestStreakDays: 0,
  lastSessionDate: null,
};

const conversations = [
  { id: 'c1', preview: 'What is the beautiful state?', updatedAt: new Date() },
  { id: 'c2', preview: 'How to calm anxiety?', updatedAt: new Date() },
] as unknown as Conversation[];

const baseProps = {
  displayName: 'Maya',
  email: 'maya@example.com',
  familiarityLevel: 'Seeker',
  languageLabel: 'English',
  toneLabel: 'Gentle',
  avatarDataUrl: null,
  avatarUrl: null,
  stats,
  conversations,
  personalInsights: [{ kind: 'rhythm', text: 'Steady practice this week.' }],
  metrics: null,
  dailyWisdom: null,
  onNavigate: vi.fn(),
  onContinueChat: vi.fn(),
  onPractice: vi.fn(),
  onKnowledgeGraph: vi.fn(),
} as unknown as Parameters<typeof JourneyOverview>[0];

describe('JourneyOverview (Profile UX overhaul)', () => {
  it('renders a single Sacred Minimal hero: name, email, streak metrics', () => {
    render(<JourneyOverview {...baseProps} />);

    expect(screen.getByRole('heading', { name: 'Maya' })).toBeInTheDocument();
    expect(screen.getByText('maya@example.com')).toBeInTheDocument();
    // Metric tiles carry real values.
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('180')).toBeInTheDocument();

    // Hero is flat Sacred Minimal: rounded-2xl card, no gradient panel.
    const hero = document.querySelector('section[aria-labelledby="journey-name"]');
    expect(hero).not.toBeNull();
    expect(hero?.className).toContain('rounded-2xl');
    expect(hero?.className).not.toContain('rounded-3xl');
    expect(hero?.className).not.toContain('bg-gradient-to-br');
  });

  it('hides the zero-stats row when every count is zero', () => {
    render(<JourneyOverview {...baseProps} stats={zeroStats} conversations={[]} personalInsights={[]} />);
    const hero = document.querySelector('section[aria-labelledby="journey-name"]');
    expect(hero).not.toBeNull();
    // No metric tiles rendered for a fresh seeker.
    expect(hero?.textContent).not.toMatch(/Practice sessions/);
    expect(hero?.textContent).not.toMatch(/Conversations/);
  });

  it('shows exactly one next-step action: continue when practiced, choose when fresh', () => {
    const { rerender } = render(<JourneyOverview {...baseProps} />);
    expect(screen.getByText('Continue your practice')).toBeInTheDocument();
    expect(screen.queryByText('Choose a practice')).toBeNull();

    rerender(<JourneyOverview {...baseProps} stats={zeroStats} />);
    expect(screen.getByText('Choose a practice')).toBeInTheDocument();
    expect(screen.queryByText('Continue your practice')).toBeNull();
  });

  it('merges conversations and reflections into one recent-activity list', () => {
    render(<JourneyOverview {...baseProps} />);
    expect(screen.getByText('Recent activity')).toBeInTheDocument();
    expect(screen.getByText('What is the beautiful state?')).toBeInTheDocument();
    expect(screen.getByText('Steady practice this week.')).toBeInTheDocument();
    // Old split cards are gone.
    expect(screen.queryByText('Recent conversations')).toBeNull();
    expect(screen.queryByText('Recent reflections')).toBeNull();
    expect(screen.queryByText('Your spaces')).toBeNull();
    expect(screen.queryByText('How your guidance is personalized')).toBeNull();
  });

  it('routes empty and populated conversation states without dead ends', () => {
    const { rerender } = render(<JourneyOverview {...baseProps} />);
    expect(screen.getByText('What is the beautiful state?')).toBeInTheDocument();

    rerender(<JourneyOverview {...baseProps} conversations={[]} personalInsights={[]} />);
    expect(screen.getByText('Start your first conversation')).toBeInTheDocument();
  });

  it('explains personalization through a single link to the profile tab', () => {
    const onNavigate = vi.fn();
    render(<JourneyOverview {...baseProps} conversations={[]} personalInsights={[]} onNavigate={onNavigate} />);
    fireEvent.click(screen.getByText('How personalization works'));
    expect(onNavigate).toHaveBeenCalledTimes(1);
    expect(onNavigate).toHaveBeenCalledWith('profile');
  });
});
