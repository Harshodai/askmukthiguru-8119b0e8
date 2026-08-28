import { describe, it, expect } from 'vitest';
import { mapStatusToLabel, mapNodeToLabel } from '@/components/chat/ThinkingPills';
import type { StreamChunk } from '@/lib/aiService';

/**
 * These tests verify the mapping between backend pipeline SSE status & stage
 * events and the UI labels shown in ThinkingPills.
 */
describe('SSE status → ThinkingPills label mapping', () => {
  const EXPECTED_MAPPINGS: [string, string][] = [
    ['Checking message safety...', 'Safety check'],
    ['Understanding your question...', 'Understanding query'],
    ['Searching knowledge base...', 'Searching sacred wisdom'],
    ['Composing response...', 'Composing guidance'],
    ['Generating answer...', 'Synthesizing wisdom'],
    ['Verifying answer...', 'Verifying sacred teachings'],
  ];

  it.each(EXPECTED_MAPPINGS)(
    'maps "%s" → "%s"',
    (input, expected) => {
      expect(mapStatusToLabel(input)).toBe(expected);
    },
  );

  it('handles unknown status by returning default label', () => {
    expect(mapStatusToLabel('Rewriting query...')).toBe('Contemplating');
    expect(mapStatusToLabel('Complete')).toBe('Contemplating');
  });

  it('covers all 6 known backend stages', () => {
    expect(EXPECTED_MAPPINGS.length).toBe(6);
  });
});

describe('Graph node → ThinkingPills label mapping', () => {
  it('maps node names to user-facing labels', () => {
    expect(mapNodeToLabel('input_guardrail')).toBe('Safety check');
    expect(mapNodeToLabel('intent_router')).toBe('Understanding query');
    expect(mapNodeToLabel('retrieve_documents')).toBe('Searching sacred wisdom');
    expect(mapNodeToLabel('rerank_documents')).toBe('Refining relevance');
    expect(mapNodeToLabel('grade_documents')).toBe('Filtering relevance');
    expect(mapNodeToLabel('generate_answer')).toBe('Composing guidance');
    expect(mapNodeToLabel('verify_answer')).toBe('Verifying sacred teachings');
  });
});

describe('StreamChunk type discriminated union', () => {
  it('token chunk has text field', () => {
    const chunk: StreamChunk = { type: 'token', text: 'hello' };
    expect(chunk.type).toBe('token');
    expect(chunk.text).toBe('hello');
  });

  it('stage chunk carries node, step, total_steps, and strategy', () => {
    const chunk: StreamChunk = {
      type: 'stage',
      node: 'retrieve_documents',
      step: 3,
      total_steps: 8,
      strategy: 'standard',
    };
    expect(chunk.type).toBe('stage');
    expect(chunk.node).toBe('retrieve_documents');
    expect(chunk.step).toBe(3);
    expect(chunk.total_steps).toBe(8);
    expect(chunk.strategy).toBe('standard');
  });

  it('done chunk carries intent, citations, meditationStep', () => {
    const chunk: StreamChunk = {
      type: 'done',
      intent: 'DISTRESS',
      citations: [{ url: 'https://youtube.com/watch?v=abc' }],
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
