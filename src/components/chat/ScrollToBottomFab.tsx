import { ChevronsDown } from 'lucide-react';
import { FloatingActionButton } from '@/components/common/ui/FloatingActionButton';

interface ScrollToBottomFabProps {
  visible: boolean;
  unreadCount: number;
  onClick: () => void;
}

/**
 * Floating "Jump to latest" button. Shows when user scrolls up
 * more than 200px from the bottom of the messages area.
 * Positioned at bottom-right of the chat column (not the sidebar).
 */
export const ScrollToBottomFab = ({ visible, unreadCount, onClick }: ScrollToBottomFabProps) => (
  <FloatingActionButton
    visible={visible}
    onClick={onClick}
    icon={<ChevronsDown className="w-4 h-4 text-ojas" />}
    label={unreadCount > 0 ? `${unreadCount} new` : 'Latest'}
    ariaLabel={`Jump to latest message${unreadCount > 0 ? ` (${unreadCount} new)` : ''}`}
  />
);
