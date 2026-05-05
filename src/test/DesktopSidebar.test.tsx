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
    // Brand name should not be visible in collapsed mode
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

  it('calls onNewConversation when New Conversation is clicked', () => {
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
    expect(items[0].className).toContain('bg-ojas/10');
  });
});
