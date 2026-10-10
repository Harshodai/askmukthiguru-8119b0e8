import { describe, it, expect } from 'vitest';
import { firstPersonResponseSchema } from '@/lib/firstPersonService';

const baseCitation = {
  video_id: 'abc123',
  start_ms: 0,
  end_ms: 4000,
  timestamp_seconds: 0,
  speaker: 'Sri Krishnaji',
  teacher_id: 'krishnaji',
  transcript_hash: 'hash',
  verbatim_text: 'The Beautiful State is a state of consciousness.',
  text_snippet: 'The Beautiful State is a state of consciousness.',
  source_url: 'https://www.youtube.com/watch?v=abc123&t=0s',
  video_url: 'https://www.youtube.com/watch?v=abc123',
  confidence: 0.95,
  is_verbatim: true,
  provenance_kind: 'speech_turn_clip',
  caption_status: 'auto_transcript',
};

const baseResponse = {
  answer_text: 'quote',
  citations: [baseCitation],
  status: 'success',
  is_direct_answer: true,
  latency_ms: 100,
  cached: false,
  error: null,
};

describe('firstPersonService schema (W5)', () => {
  it('preserves backend-emitted point_id/title/url on citations', () => {
    const parsed = firstPersonResponseSchema.safeParse({
      ...baseResponse,
      citations: [{ ...baseCitation, point_id: 'p1', title: 'Clip title', url: 'https://youtu.be/x?t=1s' }],
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.citations[0].point_id).toBe('p1');
      expect(parsed.data.citations[0].title).toBe('Clip title');
      expect(parsed.data.citations[0].url).toBe('https://youtu.be/x?t=1s');
    }
  });

  it('accepts citations without point_id/title/url (backend may emit null)', () => {
    const parsed = firstPersonResponseSchema.safeParse({
      ...baseResponse,
      citations: [{ ...baseCitation, point_id: null }],
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.citations[0].point_id).toBeNull();
      expect(parsed.data.citations[0].title).toBeUndefined();
    }
  });
});
