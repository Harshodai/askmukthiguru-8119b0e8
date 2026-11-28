import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const auth = vi.hoisted(() => ({ getAccessToken: vi.fn() }));
vi.mock('@/lib/chat/auth', () => auth);
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { DiscourseVideoModal } from '@/components/chat/CitationCard';

const CITATION = {
  index: 1,
  url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
  title: 'On Stillness',
  pointId: '0b6f1d52-6a7c-5f3e-9d3a-1c2b3d4e5f60',
  videoId: 'dQw4w9WgXcQ',
  startTimestamp: 76,
  quote: 'Be still.',
};

const submitReport = async () => {
  render(<DiscourseVideoModal isOpen onClose={() => {}} citation={CITATION} />);
  fireEvent.click(screen.getByTestId('report-clip-trigger'));
  fireEvent.click(screen.getByTestId('report-clip-submit'));
};

describe('clip report submission', () => {
  beforeEach(() => {
    auth.getAccessToken.mockReset().mockResolvedValue('tok');
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('sends the bearer token and clip ids, then confirms', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true, status: 201 });
    await submitReport();
    await waitFor(() => expect(screen.getByTestId('report-success-msg')).toBeInTheDocument());
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(String(url)).toMatch(/\/api\/feedback\/clip-report$/);
    expect(init.headers).toMatchObject({ Authorization: 'Bearer tok' });
    expect(JSON.parse(init.body)).toMatchObject({
      served_point_id: CITATION.pointId,
      video_id: CITATION.videoId,
      reason_category: 'wrong teacher',
    });
  });

  it('asks to sign in instead of posting when there is no session', async () => {
    auth.getAccessToken.mockResolvedValue(undefined);
    await submitReport();
    await screen.findByText('chat.clipReport.signInRequired');
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByTestId('report-success-msg')).toBeNull();
  });

  it('shows an error, not success, when the server answers 503', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: false, status: 503 });
    await submitReport();
    await screen.findByText('chat.clipReport.failed');
    expect(screen.queryByTestId('report-success-msg')).toBeNull();
  });
});
