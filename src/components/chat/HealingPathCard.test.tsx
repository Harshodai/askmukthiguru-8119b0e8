import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { HealingPathCard, detectCourseTrigger } from './HealingPathCard';

const mocks = vi.hoisted(() => ({
  progress: {} as Record<string, { course_slug: string; completed_lessons: string[]; current_lesson_index: number; status: string }>,
  enroll: vi.fn(),
  completeLesson: vi.fn(),
  fetch: vi.fn(),
}));

vi.mock('@/hooks/useHealingCourse', () => ({
  useHealingCourse: () => ({
    progress: mocks.progress,
    activeCourse: null,
    loading: false,
    enroll: mocks.enroll,
    completeLesson: mocks.completeLesson,
  }),
}));

vi.mock('@/lib/chat/auth', () => ({
  getAccessToken: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@/lib/backendUrl', () => ({
  BACKEND_URL: 'http://test.local',
}));

const noop = () => {};

beforeEach(() => {
  mocks.progress = {};
  mocks.enroll.mockClear();
  mocks.completeLesson.mockClear();
  mocks.fetch.mockReset().mockRejectedValue(new Error('offline'));
  vi.stubGlobal('fetch', mocks.fetch);
});

describe('detectCourseTrigger', () => {
  it('returns null for empty history', () => {
    expect(detectCourseTrigger([])).toBeNull();
    expect(detectCourseTrigger(undefined)).toBeNull();
    expect(detectCourseTrigger(null)).toBeNull();
  });

  it('returns null for calm turns only', () => {
    expect(detectCourseTrigger([{ text: 'What is the beautiful state?' }])).toBeNull();
    expect(
      detectCourseTrigger([
        { text: 'Hello' },
        { text: 'Tell me about meditation' },
        { text: 'Thank you' },
      ]),
    ).toBeNull();
  });

  it('returns null for a single distress turn (streak required)', () => {
    expect(detectCourseTrigger([{ text: 'I feel so anxious' }])).toBeNull();
    expect(detectCourseTrigger([{ text: 'I am grieving my father' }])).toBeNull();
  });

  it('triggers consecutive_2 on two consecutive distress turns', () => {
    const trigger = detectCourseTrigger([
      { text: 'What is peace?' },
      { text: 'I feel so anxious' },
      { text: 'Still anxious, can you help' },
    ]);
    expect(trigger).not.toBeNull();
    expect(trigger?.pattern).toBe('consecutive_2');
    expect(trigger?.signal).toBe('anxiety');
  });

  it('triggers freq_3_of_5 on a three-turn same-signal streak', () => {
    const trigger = detectCourseTrigger([
      { text: 'so anxious' },
      { text: 'anxious again' },
      { text: 'still anxious' },
    ]);
    expect(trigger?.pattern).toBe('freq_3_of_5');
    expect(trigger?.signal).toBe('anxiety');
  });

  it('does not trigger when the distress run is interrupted and not repeated within 24h', () => {
    const now = Date.now();
    expect(
      detectCourseTrigger([
        { text: 'I feel anxious', timestamp: now - 25 * 3600 * 1000 },
        { text: 'What is peace?', timestamp: now - 24 * 3600 * 1000 },
        { text: 'I feel anxious', timestamp: now },
      ]),
    ).toBeNull();
  });

  it('triggers freq_3_of_5 on distress in 3 of the last 5 turns', () => {
    const trigger = detectCourseTrigger([
      { text: 'so anxious' },
      { text: 'What is peace?' },
      { text: 'anxious again' },
      { text: 'Tell me a teaching' },
      { text: 'I am overwhelmed' },
    ]);
    expect(trigger?.pattern).toBe('freq_3_of_5');
    expect(trigger?.signal).toBe('anxiety');
  });

  it('does not trigger freq_3_of_5 with distress in only 2 of 5 turns', () => {
    const now = Date.now();
    expect(
      detectCourseTrigger([
        { text: 'so anxious', timestamp: now - 25 * 3600 * 1000 },
        { text: 'What is peace?', timestamp: now - 24 * 3600 * 1000 },
        { text: 'Teach me gratitude', timestamp: now - 23 * 3600 * 1000 },
        { text: 'Tell me a teaching', timestamp: now - 2 * 3600 * 1000 },
        { text: 'I am overwhelmed', timestamp: now },
      ]),
    ).toBeNull();
  });

  it('triggers escalation on sustained distress with shifting signals', () => {
    const trigger = detectCourseTrigger([
      { text: 'I lost my mother, I am grieving' },
      { text: 'And now I feel so anxious about everything' },
      { text: 'Grief keeps returning' },
    ]);
    expect(trigger?.pattern).toBe('escalation');
  });

  it('triggers repeated_signal when the same signal appears twice within 24h', () => {
    const now = Date.now();
    const trigger = detectCourseTrigger([
      { text: 'I feel anxious', timestamp: now - 2 * 3600 * 1000 },
      { text: 'Things are okay', timestamp: now - 1 * 3600 * 1000 },
      { text: 'Anxious again tonight', timestamp: now },
    ]);
    expect(trigger?.pattern).toBe('repeated_signal');
    expect(trigger?.signal).toBe('anxiety');
  });

  it('does not trigger repeated_signal when repeats are older than 24h', () => {
    const now = Date.now();
    expect(
      detectCourseTrigger([
        { text: 'I feel anxious', timestamp: now - 25 * 3600 * 1000 },
        { text: 'Things are calm', timestamp: now - 1 * 3600 * 1000 },
        { text: 'Anxious again', timestamp: now },
      ]),
    ).toBeNull();
  });
});

describe('HealingPathCard', () => {
  it('renders nothing for a single distress message (streak required)', () => {
    render(
      <HealingPathCard
        lastUserText="I feel so anxious"
        userTurnHistory={[{ text: 'I feel so anxious' }]}
        onAskGuru={noop}
        onOpenSereneMind={noop}
      />,
    );
    expect(screen.queryByRole('region', { name: 'Healing path' })).toBeNull();
  });

  it('renders the course card when a streak is detected in turn history', () => {
    render(
      <HealingPathCard
        lastUserText="Still anxious"
        userTurnHistory={[
          { text: 'I feel so anxious' },
          { text: 'Still anxious, can you help' },
        ]}
        onAskGuru={noop}
        onOpenSereneMind={noop}
      />,
    );
    expect(screen.getByRole('region', { name: 'Healing path' })).toBeInTheDocument();
    expect(screen.getByText('Quieting Anxiety')).toBeInTheDocument();
  });

  it('prefers the backend recommendedCourse over local detection', () => {
    render(
      <HealingPathCard
        lastUserText="I feel so anxious"
        userTurnHistory={[{ text: 'I feel so anxious' }]}
        recommendedCourse={{
          slug: 'walking-through-grief',
          title: 'Walking Through Grief',
          reason: '2 consecutive distress turns',
          trigger_signal: 'grief',
        }}
        onAskGuru={noop}
        onOpenSereneMind={noop}
      />,
    );
    expect(screen.getByText('Walking Through Grief')).toBeInTheDocument();
    expect(screen.getByText('2 consecutive distress turns')).toBeInTheDocument();
    expect(screen.queryByText('Quieting Anxiety')).toBeNull();
  });

  it('keeps showing the active enrolled course', () => {
    mocks.progress = {
      'quieting-anxiety': {
        course_slug: 'quieting-anxiety',
        completed_lessons: ['ax-1'],
        current_lesson_index: 0,
        status: 'active',
      },
    };
    render(
      <HealingPathCard
        lastUserText="Just saying hello"
        userTurnHistory={[{ text: 'Just saying hello' }]}
        onAskGuru={noop}
        onOpenSereneMind={noop}
      />,
    );
    expect(screen.getByRole('region', { name: 'Healing path' })).toBeInTheDocument();
    expect(screen.getByText('Quieting Anxiety')).toBeInTheDocument();
  });

  it('dismisses the card when the X button is clicked', async () => {
    render(
      <HealingPathCard
        lastUserText="Still anxious"
        userTurnHistory={[
          { text: 'I feel so anxious' },
          { text: 'Still anxious, can you help' },
        ]}
        onAskGuru={noop}
        onOpenSereneMind={noop}
      />,
    );
    expect(screen.getByRole('region', { name: 'Healing path' })).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Dismiss healing path'));
    await waitFor(() =>
      expect(screen.queryByRole('region', { name: 'Healing path' })).toBeNull(),
    );
  });

  it('fires the backend assign call when showing an un-enrolled course', async () => {
    render(
      <HealingPathCard
        lastUserText="Still anxious"
        userTurnHistory={[
          { text: 'I feel so anxious' },
          { text: 'Still anxious, can you help' },
        ]}
        onAskGuru={noop}
        onOpenSereneMind={noop}
      />,
    );
    await waitFor(() => expect(mocks.fetch).toHaveBeenCalled());
    expect(mocks.fetch).toHaveBeenCalledWith(
      'http://test.local/api/healing-course/assign',
      expect.objectContaining({ method: 'POST' }),
    );
    const body = JSON.parse((mocks.fetch.mock.calls[0][1] as RequestInit).body as string);
    expect(body.history).toHaveLength(2);
  });
});
