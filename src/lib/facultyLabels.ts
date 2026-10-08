import { supabase } from '@/integrations/supabase/client';
import { isIncognitoMode } from '@/lib/chatStorage';

export type FaithfulLabel = 'yes' | 'partly' | 'no';

export interface FacultyLabelInput {
  faithful: FaithfulLabel;
  safe: boolean;
  helpful: number;
  note?: string;
}

export interface FacultyAnswerContext {
  traceId?: string | null;
  requestId?: string | null;
  messageId?: string | null;
  model?: string | null;
  /** The response's release_manifest (public projection), if present. */
  releaseManifest?: Record<string, unknown> | null;
}

export const FACULTY_NOTE_MAX = 2000;

const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v : null);

/** Build the table row. Throws if the answer cannot be keyed (no trace/request id). */
export function buildFacultyLabelRow(userId: string, ctx: FacultyAnswerContext, input: FacultyLabelInput) {
  const traceId = str(ctx.traceId);
  const requestId = str(ctx.requestId);
  if (!traceId && !requestId) throw new Error('faculty label needs a trace_id or request_id');
  if (!Number.isInteger(input.helpful) || input.helpful < 1 || input.helpful > 5) {
    throw new Error('helpful must be an integer 1-5');
  }
  const manifest = ctx.releaseManifest ?? {};
  const releaseId = str(manifest.release_id);
  const note = input.note?.trim().slice(0, FACULTY_NOTE_MAX) || null;
  return {
    user_id: userId,
    trace_id: traceId,
    request_id: requestId,
    message_id: str(ctx.messageId),
    model: str(ctx.model),
    policy_id: str(manifest.policy_version) ?? releaseId,
    release_id: releaseId,
    faithful: input.faithful,
    safe: input.safe,
    helpful: input.helpful,
    note,
    updated_at: new Date().toISOString(),
  };
}

/** Upsert one label (re-labelling the same answer replaces it). Resolves to an error message or null. */
export async function submitFacultyLabel(ctx: FacultyAnswerContext, input: FacultyLabelInput): Promise<string | null> {
  // Incognito promises nothing leaves the device.
  if (isIncognitoMode()) return 'incognito';
  const { data: auth } = await supabase.auth.getUser();
  const userId = auth?.user?.id;
  if (!userId) return 'not_signed_in';
  const row = buildFacultyLabelRow(userId, ctx, input);
  // Table is newer than the generated Supabase types.
  const client = supabase as unknown as {
    from: (t: string) => {
      upsert: (r: unknown, o: { onConflict: string }) => Promise<{ error: { message: string } | null }>;
    };
  };
  const { error } = await client.from('faculty_answer_labels').upsert(row, { onConflict: 'user_id,answer_key' });
  return error ? error.message : null;
}
