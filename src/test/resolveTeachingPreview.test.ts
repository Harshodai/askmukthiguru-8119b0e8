import { describe, it, expect } from 'vitest';
import { resolveTeachingPreview } from '@/lib/chat/teachingPreview';
import type { Citation, TeachingPreview } from '@/lib/chat/types';

// Regression test for the trust bug found in ruthless review 2026-09-21:
// the streaming commit path previously preferred the raw, pre-verification
// retrieval-time `teachingPreview` over the post-verification `citations`
// array, so the UI could label unverified retrieval candidates as
// "Verified Sacred Teaching". Citations-derived evidence must always win
// when it exists.

const rawPreview: TeachingPreview[] = [
  { title: 'Raw candidate (pre-verification)', teacher: null, url: null, excerpt: 'candidate excerpt' },
];

const finalCitations: Citation[] = [
  { title: 'Final cited source', quote: 'verified excerpt', speaker: 'Sri Preethaji', url: 'https://example.com' } as Citation,
];

describe('resolveTeachingPreview', () => {
  it('prefers citations-derived preview over the raw streamed preview when both exist', () => {
    const result = resolveTeachingPreview(finalCitations, rawPreview, []);
    expect(result?.[0].title).toBe('Final cited source');
  });

  it('falls back to the raw streamed preview when there are no final citations', () => {
    const result = resolveTeachingPreview(undefined, rawPreview, []);
    expect(result?.[0].title).toBe('Raw candidate (pre-verification)');
  });

  it('falls back to the previous preview when neither citations nor a fresh streamed preview exist', () => {
    const previous: TeachingPreview[] = [{ title: 'Previous turn preview', teacher: null, url: null, excerpt: null }];
    const result = resolveTeachingPreview(undefined, [], previous);
    expect(result?.[0].title).toBe('Previous turn preview');
  });

  it('returns undefined when there is nothing to show', () => {
    const result = resolveTeachingPreview(undefined, [], []);
    expect(result).toBeUndefined();
  });
});
