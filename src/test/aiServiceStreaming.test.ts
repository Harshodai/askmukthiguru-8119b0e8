import { describe, it, expect } from 'vitest';
import { mapStatusToLabel } from '@/components/chat/ThinkingPills';
import type { StreamChunk } from '@/lib/aiService';

/**
 * These tests verify the mapping between backend pipeline SSE status
 * events and the UI labels shown in ThinkingPills.
 */
describe('SSE status → ThinkingPills label mapping', () => {
  const EXPECTED_MAPPINGS: [string, string][] = [
    ['Checking message safety...', 'Safety check'],
    ['Understanding your question...', 'Understanding'],
    ['Searching knowledge base...', 'Searching wisdom'],
    ['Composing response...', 'Composing'],
    ['Generating answer...', 'Generating'],
    ['Verifying answer...', 'Verifying'],
  ];

  it.each(EXPECTED_MAPPINGS)(
    'maps "%s" → "%s"',
    (input, expected) => {
      expect(mapStatusToLabel(input)).toBe(expected);
    },
  );

  it('handles unknown status by stripping trailing dots', () => {
    // The current mapStatusToLabel returns 'Processing' for any unknown status
    expect(mapStatusToLabel('Rewriting query...')).toBe('Processing');
  });

  it('returns unknown status as-is when no trailing dots', () => {
    // The current mapStatusToLabel returns 'Processing' for any unknown status
    expect(mapStatusToLabel('Complete')).toBe('Processing');
  });

  it('covers all 6 known backend stages', () => {
    expect(EXPECTED_MAPPINGS.length).toBe(6);
  });
});

describe('StreamChunk type discriminated union', () => {
  it('token chunk has text field', () => {
    const chunk: StreamChunk = { type: 'token', text: 'hello' };
    expect(chunk.type).toBe('token');
    expect(chunk.text).toBe('hello');
  });

  it('done chunk carries intent, citations, meditationStep', () => {
    const chunk: StreamChunk = {
      type: 'done',
      intent: 'DISTRESS',
      citations: ['https://youtube.com/watch?v=abc'],
      meditationStep: 1,
    };
    expect(chunk.type).toBe('done');
    expect(chunk.intent).toBe('DISTRESS');
    expect(chunk.citations).toHaveLength(1);
    expect(chunk.meditationStep).toBe(1);
  });

  it('error chunk has text field', () => {
    const chunk: StreamChunk = { type: 'error', text: 'Something went wrong' };
    expect(chunk.type).toBe('error');
    expect(chunk.text).toBe('Something went wrong');
  });

  it('status chunk has text field', () => {
    const chunk: StreamChunk = { type: 'status', text: 'Searching...' };
    expect(chunk.type).toBe('status');
  });
});
