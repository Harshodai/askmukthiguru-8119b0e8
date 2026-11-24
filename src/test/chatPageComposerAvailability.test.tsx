import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import ChatPage from '@/pages/ChatPage';

// Auth is deliberately stuck at loading:true. This pins the regression from
// composer-disappearance fix #1: ChatPage used to render a full-screen
// "Loading your session…" spinner (no composer) for as long as the anon-session
// mint waited on a cold/hung backend.
vi.mock('@/hooks/useOptionalAuth', () => ({
  useOptionalAuth: () => ({ loading: true, user: null, mode: 'loading', anonToken: null }),
}));
vi.mock('@/components/chat/ChatInterface', () => ({
  ChatInterface: () => <div data-testid="chat-interface" />,
}));
vi.mock('@/components/chat/PrePracticeGate', () => ({
  PrePracticeGate: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock('@/hooks/useBackendHealth', () => ({ useBackendHealth: () => 'ok' }));
vi.mock('@/hooks/usePageMeta', () => ({ usePageMeta: () => undefined }));
vi.mock('@/components/onboarding/GuidedTour', () => ({ GuidedTour: () => null }));
vi.mock('@/integrations/supabase/client', () => ({
  supabase: { auth: { getSession: vi.fn(), onAuthStateChange: vi.fn() }, from: vi.fn() },
}));
vi.mock('@/lib/chat/health', () => ({ requestBackendHealth: vi.fn() }));

describe('ChatPage while auth is still loading', () => {
  it('renders the chat UI instead of a blocking spinner', () => {
    const { container } = render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('chat-interface')).toBeInTheDocument();
    expect(screen.queryByText('Loading your session…')).not.toBeInTheDocument();
    expect(container.querySelector('.animate-spin')).not.toBeInTheDocument();
  });
});
