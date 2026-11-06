/**
 * NEW-A11Y-6 (A11Y-08, A11Y-13): one polite announcement per arrived answer,
 * no quote text in it, and focus returns to the composer when the first-run
 * notice closes.
 */
import { describe, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { describeArrival, useAnswerAnnouncement } from '@/lib/answerAnnouncement';
import type { Message } from '@/lib/chatStorage';

const guru = (over: Partial<Message> = {}): Message => ({
  id: 'g1',
  role: 'guru',
  content: 'A long verbatim quote that must never be read aloud.',
  timestamp: new Date(0),
  ...over,
});

describe('describeArrival', () => {
  it('announces a normal answer without reading its text', () => {
    const text = describeArrival(guru());
    expect(text).toMatch(/answer/i);
    expect(text).not.toContain('verbatim quote');
  });

  it('announces an abstain as no close match', () => {
    expect(describeArrival(guru({ groundingState: 'abstained' }))).toMatch(/no close match/i);
  });

  it('stays silent for user messages, the welcome message and errors', () => {
    expect(describeArrival({ ...guru(), role: 'user' })).toBeNull();
    expect(describeArrival(guru({ isWelcome: true }))).toBeNull();
    // errors already render role="alert"; a second announcement would double up
    expect(describeArrival(guru({ error: { kind: 'network' } as never }))).toBeNull();
  });
});

describe('useAnswerAnnouncement', () => {
  it('updates once per new guru message and not while loading', () => {
    const user: Message = { ...guru({ id: 'u1' }), role: 'user' };
    const { result, rerender } = renderHook(
      ({ messages, busy }) => useAnswerAnnouncement(messages, busy),
      { initialProps: { messages: [user] as Message[], busy: true } },
    );
    expect(result.current).toBe('');

    act(() => rerender({ messages: [user, guru({ id: 'g1' })], busy: true }));
    expect(result.current).toBe('');

    act(() => rerender({ messages: [user, guru({ id: 'g1' })], busy: false }));
    const first = result.current;
    expect(first).toMatch(/answer/i);

    // a re-render with the same last message must not change the text
    act(() => rerender({ messages: [user, guru({ id: 'g1' })], busy: false }));
    expect(result.current).toBe(first);
  });

  it('does not announce messages that were already there on load', () => {
    const { result } = renderHook(() => useAnswerAnnouncement([guru({ id: 'old' })], false));
    expect(result.current).toBe('');
  });
});
