import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { LinkSearchModal } from '@/components/chat/LinkSearchModal';

const INSPECT_ERROR_TEXT: Record<number, string> = {
  403: 'This source is not cleared for display here.',
  404: 'This source is not available.',
  429: 'Too many requests. Please try again shortly.',
};
import type { Citation } from '@/lib/chat/types';

const citation = { url: 'https://example.org/v', title: 'T' } as Citation;

const mockFetch = (status: number, body: unknown = {}) =>
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: status === 200, status, json: async () => body }),
  );

const open = () => render(<LinkSearchModal isOpen onClose={() => {}} citation={citation} />);

afterEach(() => vi.unstubAllGlobals());

describe('LinkSearchModal inspect-source refusals', () => {
  it.each([403, 404, 429])('shows an honest message for %i', async (status) => {
    mockFetch(status);
    open();
    expect(await screen.findByRole('alert')).toHaveTextContent(INSPECT_ERROR_TEXT[status]);
  });

  it('renders chunks and no alert on 200', async () => {
    mockFetch(200, {
      url: citation.url,
      title: 'Real title',
      total_chunks: 1,
      full_text: '',
      chunks: [{ id: 'c1', chunk_index: 0, text: 'passage text here' }],
    });
    open();
    expect(await screen.findByText('passage text here')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  });
});
