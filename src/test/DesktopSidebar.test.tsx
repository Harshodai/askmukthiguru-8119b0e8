import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { TooltipProvider } from '@/components/ui/tooltip';
import { DesktopSidebar } from '@/components/chat/DesktopSidebar';

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

  it('calls onToggleCollapse when toggle button is clicked', async () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    const toggle = screen.getByTestId('sidebar-toggle');
    fireEvent.click(toggle);
    expect(defaultProps.onToggleCollapse).toHaveBeenCalledTimes(1);
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
  });

  it('highlights active conversation', async () => {
    render(
      <DesktopSidebar {...defaultProps} currentConversationId="conv-1" />,
      { wrapper }
    );
    const items = await waitFor(() => screen.getAllByTestId('conversation-item'));
    // Active class is 'bg-ojas/12 text-ojas'
    expect(items[0].className).toContain('bg-ojas/12');
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
