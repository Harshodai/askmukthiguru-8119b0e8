import { describe, it, expect } from 'vitest';
import { resolveResumeAnchor } from '@/lib/resumeScroll';

describe('resolveResumeAnchor', () => {
  const msgs = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];

  it('returns the explicit lastMessageId when present', () => {
    expect(resolveResumeAnchor(msgs, 'b')).toBe('b');
  });

  it('falls back to last message when lastMessageId is missing', () => {
    expect(resolveResumeAnchor(msgs, null)).toBe('c');
    expect(resolveResumeAnchor(msgs, undefined)).toBe('c');
  });

  it('falls back to last message when lastMessageId is not found', () => {
    expect(resolveResumeAnchor(msgs, 'deleted-id')).toBe('c');
  });

  it('returns null for an empty list', () => {
    expect(resolveResumeAnchor([], 'a')).toBeNull();
  });

  it('handles a single-message list', () => {
    expect(resolveResumeAnchor([{ id: 'only' }], undefined)).toBe('only');
    expect(resolveResumeAnchor([{ id: 'only' }], 'only')).toBe('only');
  });
});
