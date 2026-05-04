import { motion, AnimatePresence } from 'framer-motion';
import { ChevronsDown } from 'lucide-react';

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
  <AnimatePresence>
    {visible && (
      <motion.button
        initial={{ opacity: 0, y: 16, scale: 0.9 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 16, scale: 0.9 }}
        transition={{ type: 'spring', stiffness: 400, damping: 28 }}
        onClick={onClick}
        className="absolute bottom-24 right-6 z-30 flex items-center gap-1.5 px-4 py-2 rounded-full bg-card/95 backdrop-blur-md border border-border/60 text-foreground shadow-lg hover:shadow-xl hover:border-ojas/30 transition-all focus:outline-none focus:ring-2 focus:ring-ojas/40"
        aria-label={`Jump to latest message${unreadCount > 0 ? ` (${unreadCount} new)` : ''}`}
      >
        <ChevronsDown className="w-4 h-4 text-ojas" />
        <span className="text-xs font-medium whitespace-nowrap">
          {unreadCount > 0 ? `${unreadCount} new` : 'Latest'}
        </span>
      </motion.button>
    )}
  </AnimatePresence>
);
