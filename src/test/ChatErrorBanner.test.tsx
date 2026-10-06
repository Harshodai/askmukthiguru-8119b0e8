/**
 * Faculty review P1-3: a failed message showed its error three times (top
 * banner with the raw code, the in-message card, a verification row). The
 * banner is now only for errors no message owns, and the machine code sits
 * under Details.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';
import { ChatErrorBanner } from '@/components/chat/ChatErrorBanner';
import { chatErrorBus } from '@/lib/chatErrorBus';

const networkError = {
  kind: 'network' as const,
  title: 'Connection problem',
  description: 'AskMukthiGuru could not be reached. Check your connection and retry.',
  retryable: true,
  actionLabel: 'retry' as const,
};

function renderBanner() {
  return render(
    <MemoryRouter>
      <ChatErrorBanner onRetry={() => {}} />
    </MemoryRouter>,
  );
}

afterEach(() => act(() => chatErrorBus.dismiss()));

describe('ChatErrorBanner', () => {
  it('stays hidden when a chat message already shows the error', () => {
    renderBanner();
    act(() => chatErrorBus.publishFromMessage(networkError, 'msg-1'));
    expect(screen.queryByText('Connection problem')).not.toBeInTheDocument();
  });

  it('shows an error no message owns, with the code only under Details', () => {
    renderBanner();
    act(() => chatErrorBus.publishFromMessage({ ...networkError, title: 'Offline now' }));
    expect(screen.getByText('Offline now')).toBeInTheDocument();
    expect(screen.queryByText('NET_OFFLINE')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { expanded: false }));
    expect(screen.getAllByText(/NET_OFFLINE/).length).toBeGreaterThan(0);
  });
});
