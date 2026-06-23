import { supabase } from '@/integrations/supabase/client';
import type { RecordMetricInput } from './types';

/**
 * Best-effort client-side telemetry. Strictly validates that `userMessageId`
 * is present before invoking the edge function. Silently no-ops on missing IDs
 * or transport failure — telemetry must never break the chat UX.
 */
export async function recordMetric(metric: RecordMetricInput): Promise<void> {
  const userMessageId = metric.userMessageId?.trim();
  if (!userMessageId) return; // hard guard — never call telemetry without an id
  try {
    const { error } = await supabase.functions.invoke('telemetry', {
      body: {
        user_message_id: userMessageId,
        last_message_id: metric.lastMessageId ?? null,
        session_id: metric.sessionId ?? null,
        metric_type: metric.type,
        metric_value: metric.value,
        tags: metric.tags ?? {},
      },
    });
    if (error) {
      console.warn('[telemetry] invoke error', error);
      const { telemetryEvents } = await import('@/lib/telemetryEvents');
      telemetryEvents.emitFailure('Telemetry submission failed', error.message || 'Could not record usage metric.');
    }
  } catch (e) {
    console.warn('[telemetry] network error', e);
    const { telemetryEvents } = await import('@/lib/telemetryEvents');
    telemetryEvents.emitFailure('Telemetry unavailable', 'Usage metrics could not be recorded. Chat is unaffected.');
  }
}
