import { z } from 'zod';

/**
 * Shared UserMetrics contract — frontend mirror of
 * `backend/app/schemas/metrics.py` (UserMetrics).
 *
 * Backend serializes snake_case; the frontend consumes camelCase. The
 * key parity between the two is enforced by `src/test/metricsSchema.test.ts`
 * against a snapshot generated from the pydantic model's JSON schema.
 */
export const userMetricsSchema = z.object({
  totalConversations: z.number(),
  totalMessages: z.number(),
  totalMeditationMinutes: z.number(),
  averageDistressLevel: z.number().nullable(),
  distressTrend: z.enum(['up', 'down', 'flat']),
  activeHealingCourse: z.string().nullable(),
  courseCompletionPercent: z.number(),
  lastActiveAt: z.string().nullable(),
});

export type UserMetrics = z.infer<typeof userMetricsSchema>;
