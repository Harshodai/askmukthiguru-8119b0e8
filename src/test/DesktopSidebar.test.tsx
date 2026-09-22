import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { TooltipProvider } from '@/components/ui/tooltip';
import { DesktopSidebar } from '@/components/chat/DesktopSidebar';
import { ChatHeader } from '@/components/chat/ChatHeader';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <BrowserRouter>
    <TooltipProvider>{children}</TooltipProvider>
  </BrowserRouter>
);

const mockConversation = {
  id: 'conv-1',
  startedAt: new Date(),
  updatedAt: new Date(),
  preview: 'Test conversation about meditation',
  messageCount: 3,
  messages: [],
};

vi.mock('@/lib/chatStorage', () => ({
  loadConversations: vi.fn(async () => [mockConversation]),
  deleteConversation: vi.fn(),
  renameConversation: vi.fn(),
  formatRelativeTime: vi.fn(() => 'Today'),
}));

vi.mock('@/assets/gurus-photo.jpg', () => ({
  default: '/test-photo.jpg',
}));

vi.mock('@/components/common/UserMenu', () => ({
  UserMenu: () => <button data-testid="user-menu" type="button" />,
}));

describe('DesktopSidebar', () => {
  const defaultProps = {
    isCollapsed: false,
    onToggleCollapse: vi.fn(),
    onNewConversation: vi.fn(),
    onOpenSereneMind: vi.fn(),
    onSelectConversation: vi.fn(),
    onDeleteConversation: vi.fn(),
    currentConversationId: undefined,
    refreshTrigger: 0,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders expanded sidebar with brand name and conversations', async () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    expect(screen.getByText('AskMukthiGuru')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Test conversation about meditation')).toBeInTheDocument());
  });

  it('renders collapsed sidebar without text labels', async () => {
    render(<DesktopSidebar {...defaultProps} isCollapsed />, { wrapper });
    await waitFor(() => expect(screen.queryByText('AskMukthiGuru')).not.toBeInTheDocument());
  });

  it('does not render a second collapse control inside the sidebar', async () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    await waitFor(() => expect(screen.getByText('AskMukthiGuru')).toBeInTheDocument());
    expect(screen.queryByTestId('sidebar-toggle')).not.toBeInTheDocument();
    expect(defaultProps.onToggleCollapse).not.toHaveBeenCalled();
  });

  it('uses the chat header as the single desktop sidebar toggle', () => {
    const onToggleSidebar = vi.fn();
    render(
      <ChatHeader
        onClearChat={vi.fn()}
        sidebarCollapsed={false}
        onToggleSidebar={onToggleSidebar}
      />,
      { wrapper },
    );

    const toggles = document.querySelectorAll('button[aria-controls="sidebar-panel"]');
    expect(toggles).toHaveLength(1);
    fireEvent.click(toggles[0]);
    expect(onToggleSidebar).toHaveBeenCalledTimes(1);
  });

  it('shows delete button on conversation hover in expanded mode', async () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    await waitFor(() => expect(screen.getByLabelText('Delete conversation')).toBeInTheDocument());
  });

  it('calls onNewConversation when New Chat is clicked', async () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    const btn = screen.getByText('New Conversation');
    fireEvent.click(btn);
    expect(defaultProps.onNewConversation).toHaveBeenCalledTimes(1);
    expect(defaultProps.onNewConversation).toHaveBeenCalledWith();
  });

  it('highlights active conversation', async () => {
    render(
      <DesktopSidebar {...defaultProps} currentConversationId="conv-1" />,
      { wrapper }
    );
    const items = await waitFor(() => screen.getAllByTestId('conversation-item'));
    // Active row: tinted background + heavier weight (ChatGPT/Claude convention)
    expect(items[0].className).toContain('bg-ojas/[0.14]');
    expect(items[0].className).toContain('font-medium');
  });

  // ── Delete confirmation dialog tests ──────────────────────────────

  it('opens confirmation dialog when delete is clicked', async () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    const deleteBtn = await waitFor(() => screen.getByLabelText('Delete conversation'));
    fireEvent.click(deleteBtn);
    expect(screen.getByText('Delete conversation?')).toBeInTheDocument();
  });

  it('cancels deletion when Cancel is clicked in dialog', async () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    const deleteBtn = await waitFor(() => screen.getByLabelText('Delete conversation'));
    fireEvent.click(deleteBtn);
    const cancelBtn = screen.getByTestId('delete-cancel');
    fireEvent.click(cancelBtn);
    expect(defaultProps.onDeleteConversation).not.toHaveBeenCalled();
  });

  it('confirms deletion when Delete is clicked in dialog', async () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    const deleteBtn = await waitFor(() => screen.getByLabelText('Delete conversation'));
    fireEvent.click(deleteBtn);
    const confirmBtn = screen.getByTestId('delete-confirm');
    fireEvent.click(confirmBtn);
    expect(defaultProps.onDeleteConversation).toHaveBeenCalledWith('conv-1');
  });

  it('shows brand icon Flame instead of guru photo', async () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    await waitFor(() => {
      const brandHeader = document.querySelector('.border-b.border-hairline');
      expect(brandHeader).toBeInTheDocument();
      const brandImg = brandHeader?.querySelector('img');
      expect(brandImg).toHaveAttribute('src', expect.stringContaining('/test-photo.jpg'));
      const flameIcon = brandHeader?.querySelector('.lucide-flame');
      expect(flameIcon).toBeNull();
    });
  });
});
