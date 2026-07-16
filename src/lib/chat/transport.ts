import { supabase } from '@/integrations/supabase/client';
import { getCurrentConfig } from './config';
import { getAccessToken, refreshAccessToken } from './auth';
import { buildAssistantContext } from './assistant';
import { httpStatusToErrorCode } from './errors';
import { recordMetric } from './telemetry';
import { placeholderReply } from './placeholder';
import { checkBackendHealth, getHealthStatus } from './health';
import type { AIErrorCode, AIResponse, MessagePayload } from './types';

const buildRequestBody = (
  systemPrompt: string | undefined,
  messages: MessagePayload[],
  userMessage: string,
  meditationStep: number,
  sessionId: string | undefined,
  summary: string | undefined,
  lastSereneMindAt: number | null | undefined,
  seekerContext: string | undefined,
) => {
  const date = new Date();
  const timeZone = typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata' : 'Asia/Kolkata';
  let localTimeStr = '12:00:00';
  try {
    localTimeStr = date.toLocaleTimeString('en-US', { timeZone, hour12: false });
  } catch { /* fallback */ }
  const localHour = parseInt(localTimeStr.split(':')[0], 10) || 12;
  
  let timeOfDay = 'night';
  if (localHour >= 5 && localHour < 12) timeOfDay = 'morning';
  else if (localHour >= 12 && localHour < 17) timeOfDay = 'afternoon';
  else if (localHour >= 17 && localHour < 21) timeOfDay = 'evening';

  const slug = (typeof window !== 'undefined' ? window.localStorage.getItem('askmukthi.assistant.slug') : null) || 'general';
  const greetingWord = slug === 'sadhguru' ? 'Namaskaram' : (timeOfDay === 'morning' ? 'Suprabhat' : timeOfDay === 'evening' ? 'Shubh Sandhya' : 'Namaste');

  const formattedSystemPrompt = `${systemPrompt || ''}\n\nSeeker Environment:\n- Local Time: ${date.toLocaleString('en-US', { timeZone })}\n- Time Zone: ${timeZone}\n- Greeting Word: "${greetingWord}"\n- Rule: When greeting the user, align your opening greeting with the Local Time and Greeting Word. Never use a double "Ji" suffix for "Sri Preethaji" or "Sri Krishnaji" (i.e. do not write "Sri Preethaji Ji" or "Sri Krishnaji Ji", only use "Sri Preethaji" and "Sri Krishnaji").`;

  return JSON.stringify({
    messages: [
      { role: 'system', content: formattedSystemPrompt },
      ...(summary ? [{ role: 'system' as const, content: `SUMMARY OF PREVIOUS CONVERSATION: ${summary}` }] : []),
      ...messages.slice(-20),
    ],
    user_message: userMessage,
    meditation_step: meditationStep,
    session_id: sessionId,
    language: getCurrentConfig().language || 'en',
    ...(lastSereneMindAt != null
      ? { last_serene_mind_at: lastSereneMindAt / 1000 }
      : {}),
    ...(seekerContext ? { seeker_context: seekerContext } : {}),
    ...buildAssistantContext(),
  });
};

export const sendMessage = async (
  messages: MessagePayload[],
  userMessage: string,
  meditationStep: number = 0,
  summary?: string,
  sessionId?: string,
  /** Unix ms of last completed Serene Mind session (from localStorage) */
  lastSereneMindAt?: number | null,
  seekerContext?: string,
  userMessageId?: string,
  lastMessageId?: string,
): Promise<AIResponse> => {
  const { provider, endpoint, systemPrompt } = getCurrentConfig();

  if (provider === 'placeholder') {
    return placeholderReply();
  }

  if (provider === 'custom' && endpoint) {
    const token = await getAccessToken();

    const buildBody = () => buildRequestBody(
      systemPrompt,
      messages,
      userMessage,
      meditationStep,
      sessionId,
      summary,
      lastSereneMindAt,
      seekerContext,
    );

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120_000);

    const doFetch = (signal?: AbortSignal) =>
      fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: buildBody(),
        signal: signal || controller.signal,
      });

    const startMs = Date.now();
    try {
      let response = await doFetch();

      // Queue integration: 202 Accepted → poll job endpoint until completed/failed
      if (response.status === 202) {
        const jobData = await response.json();
        const jobId = jobData.job_id;
        if (!jobId) {
          return { content: '', error: 'Queue returned 202 but no job_id', errorCode: 'unknown' };
        }
        // poll_url from the backend is host-relative — resolve it against baseUrl
        // (see streaming.ts) so cross-origin deploys (Lovable + Railway) don't
        // fetch it against the frontend's own origin.
        const baseUrl = endpoint.replace(/\/api\/chat\/?$/, '');
        const rawPollUrl = jobData.poll_url || `/api/jobs/${jobId}`;
        const pollUrl = /^https?:\/\//.test(rawPollUrl) ? rawPollUrl : `${baseUrl}${rawPollUrl}`;
        const pollStart = Date.now();
        while (Date.now() - pollStart < 120_000) {
          await new Promise(r => setTimeout(r, 2000));
          try {
            const pollResp = await fetch(pollUrl, {
              headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (pollResp.ok) {
              const job = await pollResp.json();
              if (job.status === 'completed') {
                const result = job.result;
                await recordMetric({ type: 'ai_response_time', value: Date.now() - startMs, userMessageId, lastMessageId, sessionId, tags: { provider: 'custom', endpoint: 'non-stream-queue' } });
                return {
                  content: result.response || result.content || '',
                  intent: result.intent,
                  citations: result.citations || [],
                  meditationStep: result.meditation_step || 0,
                  blocked: result.blocked || false,
                  blockReason: result.block_reason,
                  proactiveSereneMind: result.proactive_serene_mind ?? null,
                };
              }
              if (job.status === 'failed') {
                return { content: '', error: job.error || 'Job processing failed', errorCode: 'server_error' };
              }
            }
          } catch {
            // Network hiccup — keep polling
          }
        }
        return { content: '', error: 'The Guru took too long to respond. Please retry your question.', errorCode: 'timeout' };
      }

      if (!response.ok) {
        if (response.status === 504) {
          return {
            content: '',
            error: 'The Guru took too long to respond. Please retry your question.',
            errorCode: 'timeout',
          };
        }

        // Auto-retry on 401 with token refresh
        if (response.status === 401 && token) {
          const newToken = await refreshAccessToken();
          if (newToken) {
            const retryResponse = await fetch(endpoint, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${newToken}`,
              },
              body: buildBody(),
            });

            if (retryResponse.ok) {
              response = retryResponse;
            } else {
              return {
                content: '',
                error: `API error: ${retryResponse.status}`,
                errorCode: httpStatusToErrorCode(retryResponse.status),
              };
            }
          }
        } else {
          const errorCode = httpStatusToErrorCode(response.status);
          let errorDetail = `API error: ${response.status}`;
          try {
            const errorData = await response.clone().json();
            if (errorData?.detail) {
              errorDetail += ` - ${errorData.detail}`;
            }
          } catch {
            // Ignore JSON parse errors
          }
          return {
            content: '',
            error: errorDetail,
            errorCode,
          };
        }
      }

      const data = await response.json();
      await recordMetric({ type: 'ai_response_time', value: Date.now() - startMs, userMessageId, lastMessageId, sessionId, tags: { provider: 'custom', endpoint: 'non-stream' } });
      return {
        content: data.response || data.choices?.[0]?.message?.content || data.content,
        intent: data.intent,
        citations: data.citations || [],
        meditationStep: data.meditation_step || 0,
        blocked: data.blocked || false,
        blockReason: data.block_reason,
        proactiveSereneMind: data.proactive_serene_mind ?? null,
        followUpSuggestions: data.follow_up_suggestions ?? [],
      };
    } catch (err: any) {
      let code: AIErrorCode = 'network';
      let message = err?.message || 'Connection failed';
      if (err?.name === 'AbortError') {
        code = 'timeout';
        message = 'The request timed out before the Guru could respond.';
      } else if (err instanceof TypeError && /fetch|network/i.test(message)) {
        code = 'network';
        // Fire-and-forget health check to update cached status for next request
        checkBackendHealth(endpoint);
        message = getHealthStatus() === 'down'
          ? 'Cannot reach the Guru — backend is unavailable. Please try again later.'
          : 'Network or backend is unreachable. Please check your connection.';
      } else if (err instanceof DOMException && err.name === 'NotFoundError') {
        code = 'unknown';
        message = 'Could not resolve the backend server address.';
      }
      return {
        content: '',
        error: message,
        errorCode: code,
      };
    } finally {
      clearTimeout(timeoutId);
    }
  }

  // OpenAI direct client-side calls removed for security.
  // API keys must never be stored or used in the browser.
  // Use a server-side proxy (Edge Function) if OpenAI integration is needed.

  // Final fallback: no provider matched or unreachable code path.
  // Return empty content so ChatInterface renders the error state.
  return { content: '', errorCode: 'unknown' as AIErrorCode };
};

export const generateSummary = async (messages: MessagePayload[]): Promise<string> => {
  const { provider, endpoint } = getCurrentConfig();
  if (provider !== 'custom' || !endpoint) return '';

  try {
    const token = await getAccessToken();

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        messages: [
          {
            role: 'system',
            content: 'You are a summarizer. Provide a concise 2-3 sentence summary of the key spiritual insights and user concerns discussed in this conversation history. Focus on maintaining teaching continuity.'
          },
          ...messages.slice(-10),
        ],
        user_message: 'Summarize our conversation so far.',
      }),
    });

    if (!response.ok) return '';
    const data = await response.json();
    return data.response || data.choices?.[0]?.message?.content || data.content || '';
  } catch (error) {
    console.error('Failed to generate summary:', error);
    return '';
  }
};

export const generateConversationTitle = async (firstUserMessage: string): Promise<string> => {
  const { provider, endpoint } = getCurrentConfig();
  const fallback = firstUserMessage.trim().slice(0, 48);
  if (!fallback) return 'New conversation';


  // Custom endpoint (calls synchronous /chat/title)
  if (provider === 'custom' && endpoint) {
    try {
      const token = await getAccessToken();
      const titleUrl = endpoint.endsWith('/chat')
        ? endpoint + '/title'
        : endpoint.replace(/\/$/, '') + '/chat/title';

      const response = await fetch(titleUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          first_message: firstUserMessage,
        }),
      });

      if (!response.ok) return fallback;
      const data = await response.json();
      const title = (data.title || fallback)
        .split('\n')[0]
        .replace(/^[\"'`]+|[\"'`.]+$/g, '')
        .trim();
      return title.length > 60 ? `${title.slice(0, 57)}...` : title || fallback;
    } catch {
      return fallback;
    }
  }

  return fallback;
};

export const submitFeedbackToBackend = async (payload: {
  query: string;
  answer: string;
  rating: number;
  comment?: string;
}) => {
  const { provider, endpoint } = getCurrentConfig();
  if (provider !== 'custom' || !endpoint) return;

  try {
    // Usually endpoint is /api/chat. We replace it with /api/feedback.
    const feedbackEndpoint = endpoint.replace(/\/chat\/?$/, '/feedback');
    const token = await getAccessToken();

    await fetch(feedbackEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    console.error('Failed to submit feedback to server:', error);
  }
};

export const translateText = async (
  text: string,
  targetLanguage: string,
  sourceLanguage: string = 'en-IN',
): Promise<string | null> => {
  const { endpoint } = getCurrentConfig();
  if (!endpoint) return null;

  try {
    const token = await getAccessToken();
    const baseUrl = endpoint.replace(/\/api\/chat\/?$/, '');
    const translateUrl = `${baseUrl}/api/translate`;

    const response = await fetch(translateUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        text,
        source_language_code: sourceLanguage,
        target_language_code: targetLanguage,
      }),
    });

    if (!response.ok) return null;
    const data = await response.json();
    return data.translated_text || null;
  } catch {
    return null;
  }
};

/**
 * Fire-and-forget: insert a memory-extraction job into pending_extractions
 * for the Supabase Edge Function to drain.  Runs silently, never blocks
 * the chat, and swallows all errors.
 */
export const queueMemoryExtraction = async (payload: {
  userMessage: string;
  assistantMessage: string;
  conversationId?: string;
}): Promise<void> => {
  try {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    await supabase.from('pending_extractions').insert({
      user_id: session.user?.id,
      payload: {
        user_message: payload.userMessage,
        assistant_message: payload.assistantMessage,
        conversation_id: payload.conversationId,
      },
      status: 'pending',
      attempts: 0,
    });
  } catch {
    // Silent — memory extraction is best-effort
  }
};
