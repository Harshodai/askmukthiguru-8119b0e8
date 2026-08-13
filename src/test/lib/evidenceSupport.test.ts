import { describe, expect, it } from 'vitest';
import { evidenceSupport } from '@/lib/chat/evidenceSupport';

describe('evidenceSupport', () => {
  it('uses labels rather than exposing raw verifier scores', () => {
    expect(evidenceSupport(8.4).label).toBe('Teaching-supported');
    expect(evidenceSupport(5).label).toBe('Partially supported');
    expect(evidenceSupport(4.9).label).toBe('Limited support');
  });

  it('fails safely for missing, non-finite, and negative scores', () => {
    expect(evidenceSupport(undefined).label).toBe('Limited support');
    expect(evidenceSupport(null).label).toBe('Limited support');
    expect(evidenceSupport(Number.NaN).label).toBe('Limited support');
    expect(evidenceSupport(-1).label).toBe('Limited support');
  });
});
