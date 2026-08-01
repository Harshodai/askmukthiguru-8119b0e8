import { describe, expect, it } from 'vitest';
import { recommendedCourseSchema } from '@/lib/chat/types';

/**
 * Snapshot of `backend/services/healing_course_service.py:trigger_payload()`,
 * which returns `{"slug": slug, **asdict(trigger)}` for a `CourseTrigger`
 * (fields: signal, pattern, reason) — all plain strings, no snake/camel
 * conversion needed. Regenerate this list if `CourseTrigger` gains or
 * renames a field.
 */
const backendKeys = ['slug', 'signal', 'pattern', 'reason'].sort();

const validPayload = {
  slug: 'quieting-anxiety',
  signal: 'anxiety',
  pattern: 'consecutive_2',
  reason: '2 consecutive distress turns',
};

describe('recommendedCourseSchema parity with backend trigger_payload()', () => {
  it('frontend schema keys match backend payload keys 1:1', () => {
    expect(Object.keys(recommendedCourseSchema.shape).sort()).toEqual(backendKeys);
  });

  it('parses a valid backend payload', () => {
    const parsed = recommendedCourseSchema.safeParse(validPayload);
    expect(parsed.success).toBe(true);
  });

  it('rejects payloads missing required keys', () => {
    const { reason: _omitted, ...missing } = validPayload;
    const parsed = recommendedCourseSchema.safeParse(missing);
    expect(parsed.success).toBe(false);
  });
});
