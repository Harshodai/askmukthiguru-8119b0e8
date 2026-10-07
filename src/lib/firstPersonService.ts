import { z } from 'zod';
import { BACKEND_URL } from './backendUrl';
import { getAccessToken } from './chat/auth';

/**
 * Typed client for POST /api/first-person/query (backend/app/api/first_person.py).
 * Mirrors FirstPersonQueryResponse / FirstPersonPipelineResult.to_dict() —
 * see backend/services/first_person_pipeline.py's `_build_citation`.
 */
export const firstPersonCitationSchema = z.object({
  video_id: z.string(),
  start_ms: z.number(),
  end_ms: z.number(),
  timestamp_seconds: z.number(),
  // The real speaker as returned by the backend — never hardcode this.
  speaker: z.string(),
  teacher_id: z.string().nullable().optional(),
  transcript_hash: z.string(),
  verbatim_text: z.string(),
  text_snippet: z.string(),
  source_url: z.string(),
  video_url: z.string(),
  playback_start_seconds: z.number().optional(),
  playback_end_seconds: z.number().optional(),
  playback_url: z.string().optional(),
  confidence: z.number(),
  is_verbatim: z.boolean(),
  provenance_kind: z.string(),
  caption_status: z.string(),
});

export const firstPersonStatusSchema = z.enum([
  'success',
  'weak_match',
  'abstained',
  'crisis_redirect',
  'error',
]);

export const firstPersonResponseSchema = z.object({
  answer_text: z.string(),
  citations: z.array(firstPersonCitationSchema),
  status: firstPersonStatusSchema,
  is_direct_answer: z.boolean(),
  latency_ms: z.number(),
  cached: z.boolean().default(false),
  error: z.string().nullable().optional(),
});

export type FirstPersonCitation = z.infer<typeof firstPersonCitationSchema>;
export type FirstPersonStatus = z.infer<typeof firstPersonStatusSchema>;
export type FirstPersonResponse = z.infer<typeof firstPersonResponseSchema>;

export type FirstPersonErrorCode =
  | 'disabled'      // 404 — FIRST_PERSON_ROUTE_ENABLED / FIRST_PERSON_MODE is off
  | 'rate_limited'  // 429
  | 'unavailable'   // 503, or any other non-OK status
  | 'invalid_response'
  | 'network';

export class FirstPersonError extends Error {
  code: FirstPersonErrorCode;
  status?: number;
  retryAfterSeconds?: number;

  constructor(code: FirstPersonErrorCode, message: string, status?: number, retryAfterSeconds?: number) {
    super(message);
    this.name = 'FirstPersonError';
    this.code = code;
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export interface QueryFirstPersonOptions {
  teacherId?: 'preethaji' | 'krishnaji' | 'both';
  maxClips?: number;
  signal?: AbortSignal;
}

export async function queryFirstPerson(
  query: string,
  options?: QueryFirstPersonOptions,
): Promise<FirstPersonResponse> {
  const endpoint = `${BACKEND_URL}/api/first-person/query`;
  const token = await getAccessToken();

  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        query,
        teacher_id: options?.teacherId ?? 'both',
        max_clips: options?.maxClips ?? 3,
      }),
      signal: options?.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    throw new FirstPersonError('network', 'Could not reach the backend. Check your connection and try again.');
  }

  if (response.status === 404) {
    throw new FirstPersonError('disabled', 'First-person verbatim mode is currently disabled.', 404);
  }
  if (response.status === 429) {
    const retryAfter = Number(response.headers.get('Retry-After'));
    throw new FirstPersonError(
      'rate_limited',
      'Too many requests — please wait a moment and try again.',
      429,
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : undefined,
    );
  }
  if (response.status === 503) {
    throw new FirstPersonError('unavailable', 'First-person retrieval is temporarily unavailable.', 503);
  }
  if (!response.ok) {
    throw new FirstPersonError('unavailable', `Unexpected error (${response.status}).`, response.status);
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new FirstPersonError('invalid_response', 'The server returned an unparseable response.');
  }

  const parsed = firstPersonResponseSchema.safeParse(data);
  if (!parsed.success) {
    throw new FirstPersonError('invalid_response', 'The server returned an unexpected response shape.');
  }
  return parsed.data;
}
