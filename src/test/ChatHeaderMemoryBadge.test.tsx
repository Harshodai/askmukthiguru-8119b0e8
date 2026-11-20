import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Live 2026-11-19: the owner (active consent in the DB) saw "Memory Paused" on
// every page load until the consent check returned. Unknown must not read as paused.
vi.mock('@/hooks/useChatCapabilities', () => ({ useChatCapabilities: () => ({ capabilities: null }) }));

import { ChatHeader } from '@/components/chat/ChatHeader';

const renderHeader = (memoryActive: boolean | null) =>
  render(
    <MemoryRouter>
      <ChatHeader isPersonalized memoryActive={memoryActive} onOpenMemorySettings={vi.fn()} onClearChat={vi.fn()} />
    </MemoryRouter>,
  );

describe('ChatHeader memory badge', () => {
  it('shows no badge while consent is unknown', () => {
    renderHeader(null);
    expect(screen.queryByTestId('personalization-badge')).toBeNull();
  });

  it('shows Paused only when consent is known to be off', () => {
    renderHeader(false);
    expect(screen.getByTestId('personalization-badge').textContent).toContain('Memory Paused');
  });

  it('shows Active when consent is granted', () => {
    renderHeader(true);
    expect(screen.getByTestId('personalization-badge').textContent).toContain('Memory Active');
  });
});
