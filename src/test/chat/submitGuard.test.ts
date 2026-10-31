import { describe, expect, it } from 'vitest';
import { DUPLICATE_SUBMIT_WINDOW_MS, isDuplicateSubmit } from '@/lib/chat/submitGuard';

describe('isDuplicateSubmit', () => {
  it('allows the first send', () => {
    expect(isDuplicateSubmit(null, 'hello', 1000)).toBe(false);
  });
  it('drops an identical repeat inside the window, ignoring surrounding whitespace', () => {
    expect(isDuplicateSubmit({ text: 'hello', at: 1000 }, 'hello ', 1100)).toBe(true);
  });
  it('allows the same text after the window', () => {
    expect(isDuplicateSubmit({ text: 'hello', at: 1000 }, 'hello', 1000 + DUPLICATE_SUBMIT_WINDOW_MS)).toBe(false);
  });
  it('allows different text immediately', () => {
    expect(isDuplicateSubmit({ text: 'hello', at: 1000 }, 'hello again', 1100)).toBe(false);
  });
});

import { decideSubmit, resolveTurnFiles } from '@/lib/chat/submitGuard';

describe('decideSubmit', () => {
  const base = { text: 'hi', active: false, forceImmediate: false, contextExhausted: false, quotaExceeded: false };
  it('queues while an answer is active, interrupts only when forced', () => {
    expect(decideSubmit({ ...base, active: true })).toBe('queue');
    expect(decideSubmit({ ...base, active: true, forceImmediate: true })).toBe('interrupt');
    expect(decideSubmit(base)).toBe('send');
  });
  it('refuses a full context or exhausted quota instead of interrupting the active answer', () => {
    const active = { ...base, active: true, forceImmediate: true };
    expect(decideSubmit({ ...active, contextExhausted: true })).toBe('blocked_context');
    expect(decideSubmit({ ...active, quotaExceeded: true })).toBe('blocked_quota');
  });
  it('ignores blank text', () => {
    expect(decideSubmit({ ...base, text: '  ' })).toBe('empty');
  });
});

describe('resolveTurnFiles', () => {
  it('uses the composer files only when there is no override', () => {
    expect(resolveTurnFiles(undefined, ['draft.txt'])).toEqual(['draft.txt']);
  });
  it('lets a queued turn with no files stay file-free', () => {
    expect(resolveTurnFiles([], ['draft.txt'])).toEqual([]);
  });
});
