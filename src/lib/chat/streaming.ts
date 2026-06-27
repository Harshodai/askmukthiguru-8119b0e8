import { getCurrentConfig } from './config';
import { getAccessToken, refreshAccessToken } from './auth';
import { buildAssistantContext } from './assistant';
import { httpStatusToErrorCode } from './errors';
import { recordMetric } from './telemetry';
import type { MessagePayload, StreamChunk } from './types';

/**
 * Streaming variant of sendMessage. Yields content chunks as they arrive
 * from an SSE/chunked endpoint. Falls back by throwing if streaming is
 * unavailable (caller should catch and use sendMessage instead).
 */
export async function* sendMessageStreaming(
  messages: MessagePayload[],
  userMessage: string,
  meditationStep: number = 0,
  summary?: string,
  sessionId?: string,
  /** Unix ms of last completed Serene Mind session (from localStorage) */
  lastSereneMindAt?: number | null,
  /** Pre-fetched relevant memories, injected into guru-chat as seeker_context. */
  seekerContext?: string,
  /** Optional AbortSignal — when aborted, fetch + reader exit cleanly. */
  signal?: AbortSignal,
  /** Stable id of the user message being sent — required for telemetry. */
  userMessageId?: string,
  /** Stable id of the previous assistant message (if any) — for telemetry context. */
  lastMessageId?: string,
): AsyncGenerator<StreamChunk> {
  const { provider, endpoint, systemPrompt } = getCurrentConfig();

  // Streaming only works for the custom backend with SSE support
  if (provider !== 'custom' || !endpoint) {
    const err = new Error('Streaming not available for this provider');
    (err as any).errorCode = 'unknown';
    throw err;
  }

  const streamEndpoint = endpoint.replace(/\/?$/, '/stream');
  const trimmedMessages = messages.slice(-20);

  const buildBody = () => JSON.stringify({
    messages: [
      { role: 'system', content: systemPrompt },
      ...(summary ? [{ role: 'system' as const, content: `SUMMARY OF PREVIOUS CONVERSATION: ${summary}` }] : []),
      ...trimmedMessages,
    ],
    user_message: userMessage,
    meditation_step: meditationStep,
    session_id: sessionId,
    language: getCurrentConfig().language || 'en',
    stream: true,
    ...(lastSereneMindAt != null
      ? { last_serene_mind_at: lastSereneMindAt / 1000 }
      : {}),
    ...(seekerContext ? { seeker_context: seekerContext } : {}),
    ...buildAssistantContext(),
  });

  const doFetch = (tok: string | undefined) =>
    fetch(streamEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
      },
      body: buildBody(),
      signal,
    });

  let token = await getAccessToken();

  const startMs = Date.now();
  let response = await doFetch(token);

  // Auto-retry on 401 with a refreshed token (mirrors non-stream path)
  if (response.status === 401 && token) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      token = refreshed;
      response = await doFetch(token);
    }
  }

  // Queue integration: 202 Accepted → connect to job SSE stream
  if (response.status === 202) {
    const jobData = await response.json();
    const jobId = jobData.job_id;
    if (!jobId) {
      const err = new Error('Queue returned 202 but no job_id');
      (err as any).errorCode = 'unknown';
      throw err;
    }
    const pos = jobData.queue_position;
    yield {
      type: 'status' as const,
      text: pos && pos > 1
        ? `Queued at position ${pos}…`
        : 'Request queued…',
    };
    const baseUrl = endpoint.replace(/\/api\/chat\/?$/, '');
    const streamUrl = jobData.stream_url || `${baseUrl}/api/chat/stream/${jobId}`;
    response = await fetch(streamUrl, {
      method: 'GET',
      headers: {
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      signal,
    });
    if (!response.ok || !response.body) {
      let errorDetail = `Job stream failed: ${response.status}`;
      try {
        const errorData = await response.clone().json();
        if (errorData?.detail) {
          errorDetail += ` - ${errorData.detail}`;
        }
      } catch {
        // Ignore JSON parse errors
      }
      const err = new Error(errorDetail);
      (err as any).status = response.status;
      (err as any).errorCode = httpStatusToErrorCode(response.status);
      throw err;
    }
  }

  if (!response.ok || !response.body) {
    let errorDetail = `Streaming failed: ${response.status}`;
    try {
      const errorData = await response.clone().json();
      if (errorData?.detail) {
        errorDetail += ` - ${errorData.detail}`;
      }
    } catch {
      // Ignore JSON parse errors
    }
    const error = new Error(errorDetail);
    (error as any).status = response.status;
    (error as any).errorCode = httpStatusToErrorCode(response.status);
    throw error;
  }

  // Guard against Vite/SPA HTML fallback (when backend isn't running, the dev
  // server returns index.html for /api/chat/stream, which the SSE parser will
  // happily hang on). Detect it early and surface a clear error.
  const contentType = response.headers?.get?.('content-type') || '';
  if (contentType && !contentType.includes('text/event-stream') && !contentType.includes('application/x-ndjson')) {
    const err = new Error(
      `Backend not reachable at ${streamEndpoint} (got content-type: ${contentType}). ` +
      `Set VITE_BACKEND_URL to your FastAPI URL.`,
    );
    (err as any).errorCode = 'network';
    throw err;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = 'message'; // tracks the SSE event type

  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const sseLines = buffer.split('\n');
      buffer = sseLines.pop() || '';
      for (const line of sseLines) {
        // Parse SSE event type lines
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
          continue;
        }
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6);
        if (payload.trim() === '[DONE]') {
          await recordMetric({ type: 'ai_response_time', value: Date.now() - startMs, userMessageId, lastMessageId, sessionId, tags: { provider: 'custom', endpoint: 'stream' } });
          return;
        }

        // Yield status events as pipeline step updates
        if (currentEvent === 'status') {
          yield { type: 'status', text: payload.trim() };
          currentEvent = 'message'; // reset for next event
          continue;
        }

        // Handle done event with final metadata (intent, citations, meditation_step)
        if (currentEvent === 'done') {
          currentEvent = 'message';
          try {
            const meta = JSON.parse(payload);
            yield {
              type: 'done',
              intent: meta.intent ?? 'CASUAL',
              citations: meta.citations ?? [],
              meditationStep: meta.meditation_step ?? 0,
              blocked: meta.blocked ?? false,
              blockReason: meta.block_reason ?? null,
              proactiveSereneMind: meta.proactive_serene_mind ?? null,
              followUpSuggestions: meta.follow_up_suggestions ?? [],
            };
          } catch {
            // Ignore malformed done payload
          }
          continue;
        }

        // Handle error events
        if (currentEvent === 'error') {
          currentEvent = 'message';
          yield { type: 'error', text: payload.trim() };
          continue;
        }

        // Yield token events as content — unescape \\n back to real newlines
        currentEvent = 'message'; // reset
        try {
          const parsed = JSON.parse(payload);
          const chunk = parsed.choices?.[0]?.delta?.content ?? parsed.token ?? parsed.content ?? '';
          if (chunk) yield { type: 'token', text: chunk.replace(/\\n/g, '\n') };
        } catch {
          // Non-JSON SSE line — yield raw text (unescape newlines)
          if (payload) yield { type: 'token', text: payload.replace(/\\n/g, '\n') };
        }
      }
    }
    await recordMetric({ type: 'ai_response_time', value: Date.now() - startMs, userMessageId, lastMessageId, sessionId, tags: { provider: 'custom', endpoint: 'stream' } });
  } finally {
    reader.releaseLock();
  }
}
