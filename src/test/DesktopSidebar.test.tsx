import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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
  loadConversations: vi.fn(() => [mockConversation]),
  deleteConversation: vi.fn(),
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

  it('renders expanded sidebar with brand name and conversations', () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    expect(screen.getByText('AskMukthiGuru')).toBeInTheDocument();
    expect(screen.getByText('Test conversation about meditation')).toBeInTheDocument();
  });

  it('renders collapsed sidebar without text labels', () => {
    render(<DesktopSidebar {...defaultProps} isCollapsed />, { wrapper });
    expect(screen.queryByText('AskMukthiGuru')).not.toBeInTheDocument();
  });

  it('calls onToggleCollapse when toggle button is clicked', () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    const toggle = screen.getByTestId('sidebar-toggle');
    fireEvent.click(toggle);
    expect(defaultProps.onToggleCollapse).toHaveBeenCalledTimes(1);
  });

  it('shows delete button on conversation hover in expanded mode', () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    const deleteBtn = screen.getByLabelText('Delete conversation');
    expect(deleteBtn).toBeInTheDocument();
  });

  it('calls onNewConversation when New Chat is clicked', () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    const btn = screen.getByText('New Conversation');
    fireEvent.click(btn);
    expect(defaultProps.onNewConversation).toHaveBeenCalledTimes(1);
  });

  it('highlights active conversation', () => {
    render(
      <DesktopSidebar {...defaultProps} currentConversationId="conv-1" />,
      { wrapper }
    );
    const items = screen.getAllByTestId('conversation-item');
    // Active class is 'bg-ojas/12 text-ojas'
    expect(items[0].className).toContain('bg-ojas/12');
  });

  // ── Delete confirmation dialog tests ──────────────────────────────

  it('opens confirmation dialog when delete is clicked', () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    const deleteBtn = screen.getByLabelText('Delete conversation');
    fireEvent.click(deleteBtn);
    expect(screen.getByText('Delete conversation?')).toBeInTheDocument();
  });

  it('cancels deletion when Cancel is clicked in dialog', () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    const deleteBtn = screen.getByLabelText('Delete conversation');
    fireEvent.click(deleteBtn);
    const cancelBtn = screen.getByTestId('delete-cancel');
    fireEvent.click(cancelBtn);
    expect(defaultProps.onDeleteConversation).not.toHaveBeenCalled();
  });

  it('confirms deletion when Delete is clicked in dialog', () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    const deleteBtn = screen.getByLabelText('Delete conversation');
    fireEvent.click(deleteBtn);
    const confirmBtn = screen.getByTestId('delete-confirm');
    fireEvent.click(confirmBtn);
    expect(defaultProps.onDeleteConversation).toHaveBeenCalledWith('conv-1');
  });

  it('shows brand icon Flame instead of guru photo', () => {
    render(<DesktopSidebar {...defaultProps} />, { wrapper });
    // The component uses the Flame icon from lucide-react
    const brandIcon = document.querySelector('.lucide-flame');
    expect(brandIcon).toBeInTheDocument();
  });
});