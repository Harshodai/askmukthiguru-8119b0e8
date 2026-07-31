import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

const { getSessionMock } = vi.hoisted(() => ({
  getSessionMock: vi.fn(),
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: getSessionMock,
    },
  },
}));

import { useMetrics, ZEROED_METRICS, resetMetricsCache } from '@/hooks/useMetrics';

const validPayload = {
  total_conversations: 12,
  total_messages: 340,
  total_meditation_minutes: 45.5,
  average_distress_level: 3.2,
  distress_trend: 'down',
  active_healing_course: 'healing-mukthi',
  course_completion_percent: 64,
  last_active_at: '2026-07-30T09:15:00Z',
};

const zeroedPayload = {
  total_conversations: 0,
  total_messages: 0,
  total_meditation_minutes: 0,
  average_distress_level: null,
  distress_trend: 'flat',
  active_healing_course: null,
  course_completion_percent: 0,
  last_active_at: null,
};

const jsonResponse = (body: unknown, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

const fetchMock = vi.fn();

describe('useMetrics', () => {
  beforeEach(() => {
    resetMetricsCache();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    getSessionMock.mockReset();
    getSessionMock.mockResolvedValue({
      data: { session: { access_token: 'tok-1' } },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('fetches /api/metrics with the Supabase JWT and parses the payload', async () => {
    fetchMock.mockResolvedValue(jsonResponse(validPayload));

    const { result } = renderHook(() => useMetrics());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/metrics');
    expect((init as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer tok-1',
      Accept: 'application/json',
    });
    expect(result.current.error).toBeNull();
    expect(result.current.metrics).toEqual({
      totalConversations: 12,
      totalMessages: 340,
      totalMeditationMinutes: 45.5,
      averageDistressLevel: 3.2,
      distressTrend: 'down',
      activeHealingCourse: 'healing-mukthi',
      courseCompletionPercent: 64,
      lastActiveAt: '2026-07-30T09:15:00Z',
    });
  });

  it('sets an error when the payload fails zod parsing', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ ...validPayload, distress_trend: 'sideways' }),
    );

    const { result } = renderHook(() => useMetrics());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('Unexpected metrics response');
    expect(result.current.metrics).toBeNull();
  });

  it('sends no auth header for anonymous users and yields the zeroed payload', async () => {
    getSessionMock.mockResolvedValue({ data: { session: null } });
    fetchMock.mockResolvedValue(jsonResponse(zeroedPayload));

    const { result } = renderHook(() => useMetrics());

    await waitFor(() => expect(result.current.loading).toBe(false));
    const [, init] = fetchMock.mock.calls[0];
    expect((init as RequestInit).headers).not.toHaveProperty('Authorization');
    expect(result.current.error).toBeNull();
    expect(result.current.metrics).toEqual(ZEROED_METRICS);
  });

  it('falls back to zeroed metrics on a 401 instead of surfacing an error', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, 401));

    const { result } = renderHook(() => useMetrics());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.metrics).toEqual(ZEROED_METRICS);
  });

  it('refetches when the conversation:updated window event fires', async () => {
    fetchMock.mockResolvedValue(jsonResponse(validPayload));

    const { result } = renderHook(() => useMetrics());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    resetMetricsCache();
    act(() => {
      window.dispatchEvent(new Event('conversation:updated'));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.metrics?.totalConversations).toBe(12));
  });

  it('serves the cached payload without a network call inside the TTL window', async () => {
    fetchMock.mockResolvedValue(jsonResponse(validPayload));

    const first = renderHook(() => useMetrics());
    await waitFor(() => expect(first.result.current.loading).toBe(false));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    first.unmount();
    const second = renderHook(() => useMetrics());
    await waitFor(() => expect(second.result.current.loading).toBe(false));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(second.result.current.metrics?.totalMessages).toBe(340);
  });

  it('surfaces HTTP errors from the backend', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, 503));

    const { result } = renderHook(() => useMetrics());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('HTTP 503');
    expect(result.current.metrics).toBeNull();
  });
});
