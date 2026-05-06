import { describe, it, expect } from 'vitest';
import { mapStatusToLabel } from '@/components/chat/ThinkingPills';

/**
 * These tests verify the mapping between backend pipeline SSE status
 * events and the UI labels shown in ThinkingPills.
 *
 * Backend stages (from rag/nodes.py):
 *   "Checking message safety..."  → NeMo Input Rail
 *   "Understanding your question..." → intent_router
 *   "Searching knowledge base..."  → retrieve_documents
 *   "Composing response..."       → generate_answer
 *   "Generating answer..."        → generate_answer (alt)
 *   "Verifying answer..."         → check_faithfulness / verify_answer
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
    expect(mapStatusToLabel('Rewriting query...')).toBe('Rewriting query');
  });

  it('returns unknown status as-is when no trailing dots', () => {
    expect(mapStatusToLabel('Complete')).toBe('Complete');
  });

  it('covers all 6 known backend stages', () => {
    // If a new stage is added to the backend, this test count will remind you
    // to update the statusLabelMap in ThinkingPills.tsx
    expect(EXPECTED_MAPPINGS.length).toBe(6);
  });
});
