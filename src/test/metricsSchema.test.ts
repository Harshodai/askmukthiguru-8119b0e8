import { describe, expect, it } from 'vitest';
import { userMetricsSchema } from '@/lib/metricsSchema';

/**
 * Snapshot of `backend/app/schemas/metrics.py` (UserMetrics), generated from
 * `UserMetrics.model_json_schema()` — field name → JSON-schema type kind.
 * Regenerate after editing the pydantic model:
 *
 *   backend/.venv/bin/python -c "..."  # see metrics.py __main__ self-check
 *
 * Field names are snake_case on the backend; the frontend zod schema uses
 * camelCase. The tests below assert the two stay in lock-step.
 */
const backendSchemaSnapshot = {
  active_healing_course: 'string|null',
  average_distress_level: 'number|null',
  course_completion_percent: 'number',
  distress_trend: 'enum(up,down,flat)',
  last_active_at: 'string|null',
  total_conversations: 'integer',
  total_meditation_minutes: 'number',
  total_messages: 'integer',
} as const;

const snakeToCamel = (key: string) => key.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());

const frontendKeys = () => Object.keys(userMetricsSchema.shape).sort();

const validPayload = {
  totalConversations: 12,
  totalMessages: 340,
  totalMeditationMinutes: 45.5,
  averageDistressLevel: 3.2,
  distressTrend: 'down' as const,
  activeHealingCourse: 'healing-mukthi',
  courseCompletionPercent: 64,
  lastActiveAt: '2026-07-30T09:15:00Z',
};

describe('metricsSchema parity with backend', () => {
  it('frontend camelCase keys match backend snake_case fields 1:1', () => {
    const backendKeys = Object.keys(backendSchemaSnapshot).map(snakeToCamel).sort();
    expect(frontendKeys()).toEqual(backendKeys);
  });

  it('exposes exactly the backend fields and no extras', () => {
    const extra = frontendKeys().filter(
      (key) => !Object.keys(backendSchemaSnapshot).map(snakeToCamel).includes(key),
    );
    expect(extra).toEqual([]);
  });

  it('parses a valid backend response payload', () => {
    const parsed = userMetricsSchema.safeParse(validPayload);
    expect(parsed.success).toBe(true);
  });

  it('accepts nulls for the optional backend fields', () => {
    const parsed = userMetricsSchema.safeParse({
      ...validPayload,
      averageDistressLevel: null,
      activeHealingCourse: null,
      lastActiveAt: null,
    });
    expect(parsed.success).toBe(true);
  });

  it('rejects unknown distress trend values', () => {
    const parsed = userMetricsSchema.safeParse({ ...validPayload, distressTrend: 'sideways' });
    expect(parsed.success).toBe(false);
  });

  it('rejects payloads missing required keys', () => {
    const { totalConversations: _omitted, ...missing } = validPayload;
    const parsed = userMetricsSchema.safeParse(missing);
    expect(parsed.success).toBe(false);
  });
});
